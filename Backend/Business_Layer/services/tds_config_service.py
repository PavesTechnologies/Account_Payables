# Backend/Business_Layer/services/tds_config_service.py
"""TDS Configuration: rules, payment natures and deductors.

A TDS "rule" in the UI is one rule VARIANT, stored in the existing generic
tax engine - never a parallel TDS rule schema:

    ap.tax_rule            rule_category='TDS_RATE', tax_type=TDS; rule_code
                           = the UI "Code" (unique per variant), plus
                           old_section/new_section/tds_deductor_id and the
                           threshold_amount/threshold_type on the variant
    ap.tax_rule_condition  PAYMENT_NATURE EQUALS <code> (the "Nature of
                           Payment") + the "Rate Condition" rows
                           (see Business_Layer/utils/tds_rate_condition.py)
    ap.tax_rate_rule       the "Rate", effective-dated

Several variants may share one legal section (194C 1% / 2%); what must be
unique is the variant signature (section + nature + deductor + rate
condition) over overlapping effective dates - see _check_variant_conflicts.

Historical invoice_tds snapshots are never disturbed: a referenced
tax_rate_rule row is never edited in place (it is deactivated and a new row
created), and referenced rules/natures/deductors cannot be hard-deleted -
deactivate them instead.

Conventions (same as tds_determination_service.py): ValueError subclasses
for business-rule violations, service methods own commit/rollback, one
ap.audit_log row per change (CREATE/UPDATE/ACTIVATE/DEACTIVATE/DELETE/IMPORT).
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Optional

from Backend.Business_Layer.utils.tds_rate_condition import (
    PAYMENT_NATURE_CONDITION_TYPE,
    RateCondition,
    parse_rate_condition,
    rate_conditions_from_rows,
    render_rate_condition,
)
from Backend.Data_Access_Layer.dao.tds_config_dao import TdsConfigDAO
from Backend.Data_Access_Layer.dao.tds_dao import TDS_RULE_CATEGORY
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import TaxRateRule, TaxRule, TaxRuleCondition
from Backend.Data_Access_Layer.models.tds import TdsDeductor, TdsPaymentNature

THRESHOLD_TYPE_PER_TRANSACTION = "PER_TRANSACTION"
THRESHOLD_TYPE_AGGREGATE_PERIOD = "AGGREGATE_PERIOD"

# UI "Threshold Period" label <-> stored tax_rule.threshold_type. The codes
# themselves are also accepted on input.
THRESHOLD_PERIOD_LABELS = {
    THRESHOLD_TYPE_PER_TRANSACTION: "Single Transaction",
    THRESHOLD_TYPE_AGGREGATE_PERIOD: "Financial Year (Aggregate)",
}
_THRESHOLD_PERIOD_LOOKUP = {
    **{label.lower(): code for code, label in THRESHOLD_PERIOD_LABELS.items()},
    **{code.lower(): code for code in THRESHOLD_PERIOD_LABELS},
}

CALCULATION_TYPE_PERCENTAGE = "PERCENTAGE"

AUDIT_CREATE = "CREATE"
AUDIT_UPDATE = "UPDATE"
AUDIT_ACTIVATE = "ACTIVATE"
AUDIT_DEACTIVATE = "DEACTIVATE"
AUDIT_DELETE = "DELETE"
AUDIT_IMPORT = "IMPORT"

_MAX_RATE = Decimal("100")
_MAX_THRESHOLD = Decimal("9999999999999999.99")  # NUMERIC(18,2)
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_\-./]*$")
_SECTION_RE = re.compile(r"^[A-Z0-9][A-Z0-9()\-./ ]*$")
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y")


class TdsConfigNotFoundError(ValueError):
    """-> 404"""


class TdsConfigConflictError(ValueError):
    """Duplicate code / conflicting variant / unsafe delete -> 409"""


# =========================================================
# Field parsing (shared by the JSON API and the Excel import so both enforce
# exactly the same rules). Each raises ValueError with a user-facing message.
# =========================================================

def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _parse_decimal(value, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float)):
        result = Decimal(str(value))
    else:
        text = str(value).strip().replace(",", "")
        try:
            result = Decimal(text)
        except InvalidOperation:
            raise ValueError(f"{label} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{label} must be numeric")
    return result


def parse_rate(value) -> Decimal:
    if _blank(value):
        raise ValueError("Rate is required")
    if isinstance(value, str):
        value = value.strip().rstrip("%").strip()
    rate = _parse_decimal(value, "Rate")
    if rate < 0 or rate > _MAX_RATE:
        raise ValueError("Rate must be between 0 and 100")
    if rate.as_tuple().exponent < -4 and rate != rate.quantize(Decimal("0.0001")):
        raise ValueError("Rate can have at most 4 decimal places")
    return rate.quantize(Decimal("0.0001"))


def parse_threshold_amount(value) -> Optional[Decimal]:
    if _blank(value):
        return None
    amount = _parse_decimal(value, "Threshold Amount")
    if amount < 0:
        raise ValueError("Threshold Amount cannot be negative")
    if amount > _MAX_THRESHOLD:
        raise ValueError("Threshold Amount is too large")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Threshold Amount can have at most 2 decimal places")
    return amount.quantize(Decimal("0.01"))


def parse_threshold_period(value) -> Optional[str]:
    if _blank(value):
        return None
    code = _THRESHOLD_PERIOD_LOOKUP.get(str(value).strip().lower())
    if code is None:
        raise ValueError(
            "Threshold Period must be one of: " + ", ".join(f"'{label}'" for label in THRESHOLD_PERIOD_LABELS.values())
        )
    return code


def parse_date(value, label: str) -> Optional[datetime.date]:
    if _blank(value):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if " " in text and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$", text):
        text = text.split(" ")[0]  # "2026-04-01 00:00:00" from a CSV export of a date cell
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{label} '{text}' is not a valid date (use YYYY-MM-DD or DD-MM-YYYY)")


def parse_code(value, label: str = "Code", max_length: int = 100) -> str:
    if _blank(value):
        raise ValueError(f"{label} is required")
    code = str(value).strip().upper()
    if len(code) > max_length:
        raise ValueError(f"{label} cannot exceed {max_length} characters")
    if not _CODE_RE.match(code):
        raise ValueError(f"{label} may contain only letters, digits, '_', '-', '.', '/'")
    return code


def parse_section(value, label: str, required: bool, max_length: int = 20, uppercase: bool = True) -> Optional[str]:
    """Old Section is a bare number (194C) and is normalized to upper case;
    New Section is a full reference under the 2025 Act ("393(1) Table
    6(iii).D(a)") whose casing is meaningful, so it is kept as entered."""
    if _blank(value):
        if required:
            raise ValueError(f"{label} is required")
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # a bare 194 typed into Excel
    section = re.sub(r"\s+", " ", str(value).strip())
    if uppercase:
        section = section.upper()
    if section.upper().startswith("SECTION "):
        section = section[len("SECTION "):].strip()
    if len(section) > max_length:
        raise ValueError(f"{label} cannot exceed {max_length} characters")
    if not _SECTION_RE.match(section.upper()):
        raise ValueError(f"{label} '{section}' is not a valid section number")
    return section


def parse_name(value, label: str = "Name", max_length: int = 150) -> str:
    if _blank(value):
        raise ValueError(f"{label} is required")
    name = str(value).strip()
    if len(name) > max_length:
        raise ValueError(f"{label} cannot exceed {max_length} characters")
    return name


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _ranges_overlap(a_from, a_to, b_from, b_to) -> bool:
    return (a_to is None or b_from <= a_to) and (b_to is None or a_from <= b_to)


# =========================================================
# Normalized rule input
# =========================================================

@dataclass
class RuleInput:
    code: str
    old_section: str
    new_section: Optional[str]
    payment_nature: TdsPaymentNature
    deductor: Optional[TdsDeductor]
    rate_percent: Decimal
    threshold_amount: Optional[Decimal]
    threshold_type: Optional[str]
    rate_conditions: list[RateCondition]
    effective_from: datetime.date
    effective_to: Optional[datetime.date]
    rule_name: Optional[str] = None
    description: Optional[str] = None
    legal_reference: Optional[str] = None
    priority: Optional[int] = None
    is_active: bool = True

    @property
    def rate_condition_text(self) -> Optional[str]:
        return render_rate_condition(self.rate_conditions)

    def signature(self) -> tuple:
        return (
            self.old_section.upper(),
            self.payment_nature.code,
            # code, not id: an import may reference a deductor it has not created yet
            self.deductor.code if self.deductor else None,
            self.rate_condition_text or "",
        )


@dataclass
class FieldError:
    field: str
    message: str


@dataclass
class RuleInputResult:
    value: Optional[RuleInput]
    errors: list[FieldError] = field(default_factory=list)


def rule_signature(rule: TaxRule) -> tuple:
    return (
        (rule.old_section or "").upper(),
        rule_payment_nature_code(rule),
        rule.tds_deductor.code if rule.tds_deductor else None,
        render_rate_condition(rate_conditions_from_rows(rule.conditions or [])) or "",
    )


def rule_payment_nature_code(rule: TaxRule) -> Optional[str]:
    for condition in sorted(rule.conditions or [], key=lambda c: (c.logical_group or 1, c.sequence_no or 1)):
        if condition.condition_type == PAYMENT_NATURE_CONDITION_TYPE:
            return condition.condition_value
    return None


def current_rate_rule(rule: TaxRule) -> Optional[TaxRateRule]:
    """The rate row the UI shows/edits: the latest-starting active one."""
    active = [rr for rr in rule.rate_rules or [] if rr.is_active]
    if not active:
        return None
    return max(active, key=lambda rr: (rr.effective_from, rr.tax_rate_rule_id or 0))


class TdsConfigService:
    def __init__(self, db):
        self.db = db
        self.dao = TdsConfigDAO(db)

    # =========================================================
    # Payment natures / deductors (identical code-name masters)
    # =========================================================

    def list_payment_natures(self, search=None, is_active=None):
        return self.dao.list_payment_natures(search, is_active)

    def get_payment_nature(self, nature_id: int) -> TdsPaymentNature:
        nature = self.dao.get_payment_nature(nature_id)
        if nature is None:
            raise TdsConfigNotFoundError(f"TDS payment nature {nature_id} not found")
        return nature

    def create_payment_nature(self, data, user_id) -> TdsPaymentNature:
        return self._create_master(
            TdsPaymentNature, "tds_payment_nature", "Payment nature", self.dao.get_payment_nature_by_code, data, user_id
        )

    def update_payment_nature(self, nature_id: int, data, user_id) -> TdsPaymentNature:
        return self._update_master(
            lambda: self.dao.get_payment_nature(nature_id, lock=True),
            "tds_payment_nature", "Payment nature", nature_id,
            self.dao.get_payment_nature_by_code, self.dao.count_payment_nature_references, data, user_id,
        )

    def set_payment_nature_status(self, nature_id: int, is_active: bool, user_id) -> TdsPaymentNature:
        return self._set_master_status(
            lambda: self.dao.get_payment_nature(nature_id, lock=True),
            "tds_payment_nature", "Payment nature", nature_id, is_active, user_id,
        )

    def delete_payment_nature(self, nature_id: int, user_id) -> None:
        self._delete_master(
            lambda: self.dao.get_payment_nature(nature_id, lock=True),
            "tds_payment_nature", "Payment nature", nature_id, self.dao.count_payment_nature_references, user_id,
        )

    def list_deductors(self, search=None, is_active=None):
        return self.dao.list_deductors(search, is_active)

    def get_deductor(self, deductor_id: int) -> TdsDeductor:
        deductor = self.dao.get_deductor(deductor_id)
        if deductor is None:
            raise TdsConfigNotFoundError(f"TDS deductor {deductor_id} not found")
        return deductor

    def create_deductor(self, data, user_id) -> TdsDeductor:
        return self._create_master(TdsDeductor, "tds_deductor", "Deductor", self.dao.get_deductor_by_code, data, user_id)

    def update_deductor(self, deductor_id: int, data, user_id) -> TdsDeductor:
        return self._update_master(
            lambda: self.dao.get_deductor(deductor_id, lock=True),
            "tds_deductor", "Deductor", deductor_id,
            self.dao.get_deductor_by_code, self.dao.count_deductor_references, data, user_id,
        )

    def set_deductor_status(self, deductor_id: int, is_active: bool, user_id) -> TdsDeductor:
        return self._set_master_status(
            lambda: self.dao.get_deductor(deductor_id, lock=True), "tds_deductor", "Deductor", deductor_id, is_active, user_id
        )

    def delete_deductor(self, deductor_id: int, user_id) -> None:
        self._delete_master(
            lambda: self.dao.get_deductor(deductor_id, lock=True),
            "tds_deductor", "Deductor", deductor_id, self.dao.count_deductor_references, user_id,
        )

    @staticmethod
    def _master_view(obj) -> dict:
        return {"code": obj.code, "name": obj.name, "description": obj.description, "is_active": obj.is_active}

    def _create_master(self, model, table_name: str, label: str, get_by_code: Callable, data, user_id):
        try:
            code = parse_code(data.code, "Code", max_length=50)
            name = parse_name(data.name)
            if get_by_code(code) is not None:
                raise TdsConfigConflictError(f"{label} with code '{code}' already exists")
            obj = model(
                code=code, name=name, description=(data.description or "").strip() or None,
                is_active=True if data.is_active is None else data.is_active,
            )
            self.dao.add(obj)
            self._audit(table_name, obj.id, AUDIT_CREATE, user_id, None, self._master_view(obj))
            self.db.commit()
            self.db.refresh(obj)
            return obj
        except Exception:
            self.db.rollback()
            raise

    def _update_master(self, load: Callable, table_name, label, obj_id, get_by_code, count_refs, data, user_id):
        try:
            obj = load()
            if obj is None:
                raise TdsConfigNotFoundError(f"{label} {obj_id} not found")
            old = self._master_view(obj)

            code = parse_code(data.code, "Code", max_length=50) if data.code is not None else obj.code
            if code != obj.code:
                clash = get_by_code(code)
                if clash is not None and clash.id != obj.id:
                    raise TdsConfigConflictError(f"{label} with code '{code}' already exists")
                references = count_refs(obj)
                if any(references.values()):
                    # tax_rule_condition stores the payment-nature CODE, and
                    # historical invoices reference the row - renaming the
                    # code would silently orphan/relabel them.
                    raise TdsConfigConflictError(
                        f"{label} code cannot be changed because it is in use ({_describe_references(references)})"
                    )
                obj.code = code
            if data.name is not None:
                obj.name = parse_name(data.name)
            if data.description is not None:
                obj.description = data.description.strip() or None
            if data.is_active is not None:
                obj.is_active = data.is_active
            obj.updated_at = datetime.datetime.now()
            self.db.flush()

            self._audit(table_name, obj.id, AUDIT_UPDATE, user_id, old, self._master_view(obj))
            self.db.commit()
            self.db.refresh(obj)
            return obj
        except Exception:
            self.db.rollback()
            raise

    def _set_master_status(self, load: Callable, table_name, label, obj_id, is_active: bool, user_id):
        try:
            obj = load()
            if obj is None:
                raise TdsConfigNotFoundError(f"{label} {obj_id} not found")
            if obj.is_active != is_active:
                obj.is_active = is_active
                obj.updated_at = datetime.datetime.now()
                self.db.flush()
                self._audit(
                    table_name, obj.id, AUDIT_ACTIVATE if is_active else AUDIT_DEACTIVATE, user_id,
                    {"is_active": not is_active}, {"is_active": is_active},
                )
            self.db.commit()
            self.db.refresh(obj)
            return obj
        except Exception:
            self.db.rollback()
            raise

    def _delete_master(self, load: Callable, table_name, label, obj_id, count_refs, user_id) -> None:
        try:
            obj = load()
            if obj is None:
                raise TdsConfigNotFoundError(f"{label} {obj_id} not found")
            references = count_refs(obj)
            if any(references.values()):
                raise TdsConfigConflictError(
                    f"{label} '{obj.code}' cannot be deleted because it is in use "
                    f"({_describe_references(references)}) - deactivate it instead"
                )
            old = self._master_view(obj)
            self.dao.delete(obj)
            self._audit(table_name, obj_id, AUDIT_DELETE, user_id, old, None)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    # =========================================================
    # TDS rules
    # =========================================================

    def list_rules(self, search=None, status=None, payment_nature=None, effective_date=None, deductor_id=None):
        is_active = None
        if status:
            normalized = status.strip().upper()
            if normalized in ("ACTIVE", "TRUE"):
                is_active = True
            elif normalized in ("INACTIVE", "FALSE"):
                is_active = False
            elif normalized != "ALL":
                raise ValueError("status must be one of ACTIVE, INACTIVE, ALL")
        rules = self.dao.list_rules(search, is_active, payment_nature, effective_date, deductor_id)
        natures_by_code = {n.code: n for n in self.dao.list_payment_natures()}
        return [self.rule_view(rule, natures_by_code) for rule in rules]

    def get_rule(self, tax_rule_id: int) -> dict:
        return self.rule_view(self._require_rule(tax_rule_id))

    def create_rule(self, raw: dict, user_id) -> dict:
        try:
            rule_input = self._normalize_or_raise(raw)
            self._check_code_available(rule_input.code, exclude_rule_id=None)
            self._check_variant_conflicts(rule_input, exclude_rule_id=None)

            rule = self._create_rule_row(rule_input, user_id)
            self._audit("tax_rule", rule.tax_rule_id, AUDIT_CREATE, user_id, None, self._audit_view(rule))
            self.db.commit()
            return self.rule_view(self._require_rule(rule.tax_rule_id))
        except Exception:
            self.db.rollback()
            raise

    def update_rule(self, tax_rule_id: int, raw: dict, user_id) -> dict:
        try:
            rule = self._require_rule(tax_rule_id, lock=True)
            old = self._audit_view(rule)
            rule_input = self._normalize_or_raise(raw)
            rule_input.is_active = rule.is_active  # status changes only via set_rule_status
            self._check_code_available(rule_input.code, exclude_rule_id=rule.tax_rule_id)
            self._check_variant_conflicts(rule_input, exclude_rule_id=rule.tax_rule_id)

            self._apply_rule_input(rule, rule_input, user_id)
            self._audit("tax_rule", rule.tax_rule_id, AUDIT_UPDATE, user_id, old, self._audit_view(rule))
            self.db.commit()
            return self.rule_view(self._require_rule(tax_rule_id))
        except Exception:
            self.db.rollback()
            raise

    def set_rule_status(self, tax_rule_id: int, is_active: bool, user_id) -> dict:
        try:
            rule = self._require_rule(tax_rule_id, lock=True)
            if rule.is_active != is_active:
                if is_active:
                    self._check_variant_conflicts(self._input_from_rule(rule), exclude_rule_id=rule.tax_rule_id)
                rule.is_active = is_active
                rule.updated_by = _user(user_id)
                rule.updated_at = datetime.datetime.now()
                self.db.flush()
                self._audit(
                    "tax_rule", rule.tax_rule_id, AUDIT_ACTIVATE if is_active else AUDIT_DEACTIVATE, user_id,
                    {"is_active": not is_active}, {"is_active": is_active, "rule_code": rule.rule_code},
                )
            self.db.commit()
            return self.rule_view(self._require_rule(tax_rule_id))
        except Exception:
            self.db.rollback()
            raise

    def delete_rule(self, tax_rule_id: int, user_id) -> None:
        try:
            rule = self._require_rule(tax_rule_id, lock=True)
            references = self.dao.count_rule_references(rule)
            if references:
                raise TdsConfigConflictError(
                    f"TDS rule '{rule.rule_code}' is referenced by {references} invoice TDS determination(s) "
                    f"and cannot be deleted - deactivate it instead"
                )
            old = self._audit_view(rule)
            self.dao.delete(rule)  # conditions / rate rules cascade
            self._audit("tax_rule", tax_rule_id, AUDIT_DELETE, user_id, old, None)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    # ---------------------------------------------------------
    # Rule views
    # ---------------------------------------------------------

    def rule_view(self, rule: TaxRule, natures_by_code: Optional[dict] = None) -> dict:
        nature_code = rule_payment_nature_code(rule)
        if natures_by_code is not None:
            nature = natures_by_code.get(nature_code)
        else:
            nature = self.dao.get_payment_nature_by_code(nature_code) if nature_code else None
        rate_row = current_rate_rule(rule)
        conditions = sorted(rule.conditions or [], key=lambda c: (c.logical_group or 1, c.sequence_no or 1, c.tax_rule_condition_id or 0))
        rates = sorted(rule.rate_rules or [], key=lambda rr: (rr.effective_from, rr.tax_rate_rule_id or 0))
        deductor = rule.tds_deductor
        return {
            "id": rule.tax_rule_id,
            "code": rule.rule_code,
            "rule_name": rule.rule_name,
            "description": rule.description,
            "old_section": rule.old_section,
            "new_section": rule.new_section,
            "legal_reference": rule.legal_reference,
            "payment_nature": (
                {"id": nature.id, "code": nature.code, "name": nature.name, "is_active": nature.is_active}
                if nature else ({"id": None, "code": nature_code, "name": nature_code, "is_active": False} if nature_code else None)
            ),
            "deductor": (
                {"id": deductor.id, "code": deductor.code, "name": deductor.name, "is_active": deductor.is_active}
                if deductor else None
            ),
            "rate_percent": rate_row.rate_percent if rate_row else None,
            "calculation_type": rate_row.calculation_type if rate_row else None,
            "current_rate_rule_id": rate_row.tax_rate_rule_id if rate_row else None,
            "threshold_amount": rule.threshold_amount,
            "threshold_period": rule.threshold_type,
            "threshold_period_label": THRESHOLD_PERIOD_LABELS.get(rule.threshold_type) if rule.threshold_type else None,
            "rate_condition": render_rate_condition(rate_conditions_from_rows(conditions)),
            "conditions": [
                {
                    "id": c.tax_rule_condition_id,
                    "condition_type": c.condition_type,
                    "operator": c.operator,
                    "condition_value": c.condition_value,
                    "logical_group": c.logical_group,
                    "sequence_no": c.sequence_no,
                }
                for c in conditions
            ],
            "rates": [
                {
                    "id": rr.tax_rate_rule_id,
                    "rate_percent": rr.rate_percent,
                    "calculation_type": rr.calculation_type,
                    "fixed_amount": rr.fixed_amount,
                    "effective_from": rr.effective_from,
                    "effective_to": rr.effective_to,
                    "is_active": rr.is_active,
                }
                for rr in rates
            ],
            "effective_from": rule.effective_from,
            "effective_to": rule.effective_to,
            "priority": rule.priority,
            "is_active": rule.is_active,
            "status": "ACTIVE" if rule.is_active else "INACTIVE",
            "created_by": rule.created_by,
            "created_at": rule.created_at,
            "updated_by": rule.updated_by,
            "updated_at": rule.updated_at,
        }

    def _audit_view(self, rule: TaxRule) -> dict:
        rate_row = current_rate_rule(rule)
        return _jsonable({
            "rule_code": rule.rule_code,
            "rule_name": rule.rule_name,
            "old_section": rule.old_section,
            "new_section": rule.new_section,
            "payment_nature": rule_payment_nature_code(rule),
            "tds_deductor_id": rule.tds_deductor_id,
            "rate_percent": rate_row.rate_percent if rate_row else None,
            "tax_rate_rule_id": rate_row.tax_rate_rule_id if rate_row else None,
            "threshold_amount": rule.threshold_amount,
            "threshold_type": rule.threshold_type,
            "rate_condition": render_rate_condition(rate_conditions_from_rows(rule.conditions or [])),
            "effective_from": rule.effective_from,
            "effective_to": rule.effective_to,
            "is_active": rule.is_active,
        })

    # ---------------------------------------------------------
    # Rule input normalization / validation
    # ---------------------------------------------------------

    def normalize_rule_input(
        self,
        raw: dict,
        resolve_payment_nature: Optional[Callable] = None,
        resolve_deductor: Optional[Callable] = None,
    ) -> RuleInputResult:
        """raw keys: code, old_section, new_section, payment_nature (id, code or
        name), deductor (id, code or name; optional), rate, threshold_amount,
        threshold_period, rate_condition, effective_from, effective_to, and the
        optional rule_name/description/legal_reference/priority/is_active.
        Errors are keyed by the UI/Excel column label.

        The resolvers default to the strict ones (unknown/inactive -> error),
        which the JSON API uses. The Excel import passes its own resolvers that
        may plan new masters (see tds_config_import_service._MasterPlan)."""
        resolve_payment_nature = resolve_payment_nature or self._resolve_payment_nature
        resolve_deductor = resolve_deductor or self._resolve_deductor
        errors: list[FieldError] = []
        values: dict[str, Any] = {}

        def run(label: str, key: str, fn: Callable):
            try:
                values[key] = fn()
            except ValueError as e:
                errors.append(FieldError(label, str(e)))

        run("Code", "code", lambda: parse_code(raw.get("code")))
        run("Old Section", "old_section", lambda: parse_section(raw.get("old_section"), "Old Section", required=True))
        run("New Section", "new_section", lambda: parse_section(raw.get("new_section"), "New Section", required=False, max_length=100, uppercase=False))
        run("Nature of Payment", "payment_nature", lambda: resolve_payment_nature(raw.get("payment_nature")))
        run("Deductor", "deductor", lambda: resolve_deductor(raw.get("deductor")))
        run("Rate", "rate_percent", lambda: parse_rate(raw.get("rate")))
        run("Threshold Amount", "threshold_amount", lambda: parse_threshold_amount(raw.get("threshold_amount")))
        run("Threshold Period", "threshold_type", lambda: parse_threshold_period(raw.get("threshold_period")))
        run("Rate Condition", "rate_conditions", lambda: parse_rate_condition(raw.get("rate_condition")))
        run("Effective From", "effective_from", lambda: parse_date(raw.get("effective_from"), "Effective From"))
        run("Effective To", "effective_to", lambda: parse_date(raw.get("effective_to"), "Effective To"))

        if "effective_from" in values and values["effective_from"] is None:
            errors.append(FieldError("Effective From", "Effective From is required"))
        if values.get("effective_from") and values.get("effective_to") and values["effective_to"] < values["effective_from"]:
            errors.append(FieldError("Effective To", "Effective To must be on or after Effective From"))

        if "threshold_amount" in values and "threshold_type" in values:
            if values["threshold_amount"] is not None and values["threshold_type"] is None:
                errors.append(FieldError("Threshold Period", "Threshold Period is required when Threshold Amount is set"))
            if values["threshold_amount"] is None and values["threshold_type"] is not None:
                errors.append(FieldError("Threshold Amount", "Threshold Amount is required when Threshold Period is set"))

        rule_name = raw.get("rule_name")
        if rule_name is not None and not _blank(rule_name):
            run("Rule Name", "rule_name", lambda: parse_name(rule_name, "Rule Name", max_length=255))
        legal_reference = raw.get("legal_reference")
        if legal_reference is not None and len(str(legal_reference).strip()) > 50:
            errors.append(FieldError("Legal Reference", "Legal Reference cannot exceed 50 characters"))
        priority = raw.get("priority")
        if priority is not None and (not isinstance(priority, int) or isinstance(priority, bool) or priority < 0):
            errors.append(FieldError("Priority", "Priority must be a non-negative integer"))

        if errors:
            return RuleInputResult(None, errors)

        return RuleInputResult(
            RuleInput(
                code=values["code"],
                old_section=values["old_section"],
                new_section=values["new_section"],
                payment_nature=values["payment_nature"],
                deductor=values["deductor"],
                rate_percent=values["rate_percent"],
                threshold_amount=values["threshold_amount"],
                threshold_type=values["threshold_type"],
                rate_conditions=values["rate_conditions"],
                effective_from=values["effective_from"],
                effective_to=values["effective_to"],
                rule_name=values.get("rule_name"),
                description=(str(raw["description"]).strip() or None) if raw.get("description") is not None else None,
                legal_reference=(str(legal_reference).strip() or None) if legal_reference is not None else None,
                priority=priority,
                is_active=True if raw.get("is_active") is None else bool(raw.get("is_active")),
            )
        )

    def _normalize_or_raise(self, raw: dict) -> RuleInput:
        result = self.normalize_rule_input(raw)
        if result.errors:
            raise ValueError("; ".join(f"{e.field}: {e.message}" for e in result.errors))
        return result.value

    def _resolve_payment_nature(self, value) -> TdsPaymentNature:
        if _blank(value):
            raise ValueError("Nature of Payment is required")
        nature = self._resolve_master(value, self.dao.get_payment_nature, self.dao.get_payment_nature_by_code, self.dao.get_payment_nature_by_name)
        if nature is None:
            raise ValueError(f"Nature of Payment '{value}' does not exist")
        if not nature.is_active:
            raise ValueError(f"Nature of Payment '{nature.code}' is inactive")
        return nature

    def _resolve_deductor(self, value) -> Optional[TdsDeductor]:
        if _blank(value):
            return None
        deductor = self._resolve_master(value, self.dao.get_deductor, self.dao.get_deductor_by_code, self.dao.get_deductor_by_name)
        if deductor is None:
            raise ValueError(f"Deductor '{value}' does not exist")
        if not deductor.is_active:
            raise ValueError(f"Deductor '{deductor.code}' is inactive")
        return deductor

    @staticmethod
    def _resolve_master(value, by_id, by_code, by_name):
        if isinstance(value, int) and not isinstance(value, bool):
            return by_id(value)
        text = str(value).strip()
        return by_code(text) or by_name(text)

    def _check_code_available(self, code: str, exclude_rule_id: Optional[int]) -> None:
        existing = self.dao.get_rule_by_code(code)
        if existing is not None and existing.tax_rule_id != exclude_rule_id:
            if existing.rule_category != TDS_RULE_CATEGORY:
                raise TdsConfigConflictError(f"Code '{code}' is already used by a non-TDS tax rule")
            raise TdsConfigConflictError(f"TDS rule with code '{code}' already exists")

    def _check_variant_conflicts(self, rule_input: RuleInput, exclude_rule_id: Optional[int]) -> None:
        """Two ACTIVE variants with the same section + nature + deductor + rate
        condition over overlapping dates would make determination ambiguous."""
        if not rule_input.is_active:
            return
        signature = rule_input.signature()
        for other in self.dao.list_rules_for_section_and_nature(rule_input.old_section, rule_input.payment_nature.code):
            if other.tax_rule_id == exclude_rule_id or not other.is_active:
                continue
            if rule_signature(other) != signature:
                continue
            if _ranges_overlap(rule_input.effective_from, rule_input.effective_to, other.effective_from, other.effective_to):
                raise TdsConfigConflictError(
                    f"Conflicts with active TDS rule '{other.rule_code}': same section, nature of payment, deductor "
                    f"and rate condition over overlapping effective dates"
                )

    def _input_from_rule(self, rule: TaxRule) -> RuleInput:
        nature_code = rule_payment_nature_code(rule)
        nature = self.dao.get_payment_nature_by_code(nature_code) if nature_code else None
        if nature is None:
            raise ValueError(f"TDS rule '{rule.rule_code}' has no valid nature of payment configured")
        rate_row = current_rate_rule(rule)
        return RuleInput(
            code=rule.rule_code,
            old_section=rule.old_section or "",
            new_section=rule.new_section,
            payment_nature=nature,
            deductor=rule.tds_deductor,
            rate_percent=rate_row.rate_percent if rate_row else Decimal("0"),
            threshold_amount=rule.threshold_amount,
            threshold_type=rule.threshold_type,
            rate_conditions=rate_conditions_from_rows(rule.conditions or []),
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
        )

    # ---------------------------------------------------------
    # Rule persistence (shared with the Excel import)
    # ---------------------------------------------------------

    def _require_rule(self, tax_rule_id: int, lock: bool = False) -> TaxRule:
        rule = self.dao.get_rule(tax_rule_id, lock=lock)
        if rule is None:
            raise TdsConfigNotFoundError(f"TDS rule {tax_rule_id} not found")
        return rule

    @staticmethod
    def default_rule_name(rule_input: RuleInput) -> str:
        name = f"TDS {rule_input.old_section} - {rule_input.payment_nature.name}"
        if rule_input.rate_condition_text:
            name += f" ({rule_input.rate_condition_text})"
        return name[:255]

    def _create_rule_row(self, rule_input: RuleInput, user_id) -> TaxRule:
        tax_type = self.dao.get_tds_tax_type()
        if tax_type is None:
            raise ValueError("TDS tax type is not configured (ap.tax_type tax_code='TDS')")
        rule = TaxRule(
            rule_code=rule_input.code,
            rule_name=rule_input.rule_name or self.default_rule_name(rule_input),
            tax_type_id=tax_type.tax_type_id,
            rule_category=TDS_RULE_CATEGORY,
            description=rule_input.description,
            priority=rule_input.priority if rule_input.priority is not None else 100,
            effective_from=rule_input.effective_from,
            effective_to=rule_input.effective_to,
            is_active=rule_input.is_active,
            legal_reference=rule_input.legal_reference,
            threshold_amount=rule_input.threshold_amount,
            threshold_type=rule_input.threshold_type,
            old_section=rule_input.old_section,
            new_section=rule_input.new_section,
            tds_deductor_id=rule_input.deductor.id if rule_input.deductor else None,
            created_by=_user(user_id),
            updated_by=_user(user_id),
        )
        self.dao.add(rule)
        self._write_conditions(rule, rule_input)
        rule.rate_rules.append(TaxRateRule(
            tax_rule_id=rule.tax_rule_id,
            rate_percent=rule_input.rate_percent,
            calculation_type=CALCULATION_TYPE_PERCENTAGE,
            effective_from=rule_input.effective_from,
            effective_to=rule_input.effective_to,
            is_active=True,
            created_by=_user(user_id),
            updated_by=_user(user_id),
        ))
        self.db.flush()
        return rule

    def _write_conditions(self, rule: TaxRule, rule_input: RuleInput) -> None:
        rule.conditions.append(TaxRuleCondition(
            tax_rule_id=rule.tax_rule_id,
            condition_type=PAYMENT_NATURE_CONDITION_TYPE,
            operator="EQUALS",
            condition_value=rule_input.payment_nature.code,
            logical_group=1,
            sequence_no=1,
        ))
        for index, condition in enumerate(rule_input.rate_conditions, start=2):
            rule.conditions.append(TaxRuleCondition(
                tax_rule_id=rule.tax_rule_id,
                condition_type=condition.condition_type,
                operator=condition.operator,
                condition_value=condition.condition_value,
                logical_group=1,
                sequence_no=index,
            ))

    def _apply_rule_input(self, rule: TaxRule, rule_input: RuleInput, user_id) -> None:
        """Existing rule_name is kept unless one is supplied - legacy rules carry
        hand-written names that verified invoices display."""
        now = datetime.datetime.now()
        rule.rule_code = rule_input.code
        if rule_input.rule_name:
            rule.rule_name = rule_input.rule_name
        if rule_input.description is not None:
            rule.description = rule_input.description
        if rule_input.legal_reference is not None:
            rule.legal_reference = rule_input.legal_reference
        if rule_input.priority is not None:
            rule.priority = rule_input.priority
        rule.old_section = rule_input.old_section
        rule.new_section = rule_input.new_section
        rule.tds_deductor_id = rule_input.deductor.id if rule_input.deductor else None
        rule.threshold_amount = rule_input.threshold_amount
        rule.threshold_type = rule_input.threshold_type
        rule.effective_from = rule_input.effective_from
        rule.effective_to = rule_input.effective_to
        rule.updated_by = _user(user_id)
        rule.updated_at = now

        # Conditions: nothing references tax_rule_condition rows, so replace
        # them only when the nature/rate condition actually changed.
        existing_conditions = list(rule.conditions or [])
        if (rule_payment_nature_code(rule), render_rate_condition(rate_conditions_from_rows(existing_conditions))) != (
            rule_input.payment_nature.code, rule_input.rate_condition_text
        ) or sum(1 for c in existing_conditions if c.condition_type == PAYMENT_NATURE_CONDITION_TYPE) != 1:
            for condition in existing_conditions:
                rule.conditions.remove(condition)
            self.db.flush()
            self._write_conditions(rule, rule_input)

        # Rate: a rate row an invoice snapshot references is never edited in
        # place - it is retired (is_active=false) and a new row created, so
        # the FK'd history keeps its original rate and dates.
        rate_row = current_rate_rule(rule)
        wanted = (rule_input.rate_percent, rule_input.effective_from, rule_input.effective_to)
        if rate_row is None or (
            rate_row.rate_percent, rate_row.effective_from, rate_row.effective_to
        ) != wanted or rate_row.calculation_type != CALCULATION_TYPE_PERCENTAGE:
            if rate_row is not None and not self.dao.is_rate_rule_referenced(rate_row.tax_rate_rule_id):
                rate_row.rate_percent = rule_input.rate_percent
                rate_row.calculation_type = CALCULATION_TYPE_PERCENTAGE
                rate_row.fixed_amount = None
                rate_row.effective_from = rule_input.effective_from
                rate_row.effective_to = rule_input.effective_to
                rate_row.updated_by = _user(user_id)
                rate_row.updated_at = now
            else:
                if rate_row is not None:
                    rate_row.is_active = False
                    rate_row.updated_by = _user(user_id)
                    rate_row.updated_at = now
                rule.rate_rules.append(TaxRateRule(
                    tax_rule_id=rule.tax_rule_id,
                    rate_percent=rule_input.rate_percent,
                    calculation_type=CALCULATION_TYPE_PERCENTAGE,
                    effective_from=rule_input.effective_from,
                    effective_to=rule_input.effective_to,
                    is_active=True,
                    created_by=_user(user_id),
                    updated_by=_user(user_id),
                ))
            # The UI edits one current rate per variant; any other still-active
            # row would still be picked up by the engine for dates it covers, so
            # retire it (never edited - history keeps its values).
            current = current_rate_rule(rule)
            for other in rule.rate_rules:
                if other is current or not other.is_active:
                    continue
                other.is_active = False
                other.updated_by = _user(user_id)
                other.updated_at = now
        self.db.flush()

    def _audit(self, table_name: str, record_id: int, action: str, user_id, old_values, new_values) -> None:
        self.dao.create_audit_log(AuditLog(
            table_name=table_name,
            record_id=record_id,
            action=action,
            changed_by=_user(user_id),
            old_values=_jsonable(old_values) if old_values else None,
            new_values=_jsonable(new_values) if new_values else None,
        ))


def _user(user_id) -> Optional[str]:
    return str(user_id) if user_id is not None else None


def _describe_references(references: dict) -> str:
    return ", ".join(f"{count} {name.replace('_', ' ')}" for name, count in references.items() if count)
