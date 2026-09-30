# Backend/Business_Layer/services/tds_config_import_service.py
"""TDS rule Excel/CSV import: Upload -> Validate -> Preview -> Confirm -> Import.

validate() never writes anything. import_rules() re-validates the same file
from scratch (a preview is never trusted) and is ALL-OR-NOTHING: one ERROR row
and nothing is persisted; otherwise every NEW/UPDATED row is written in one
transaction.

Matching key: the "Code" column <-> ap.tax_rule.rule_code. Code identifies a
rule VARIANT (several codes may share an Old Section, e.g. TDS_194C_IND /
TDS_194C_OTH), so re-uploading the same file matches every row to the rule
it created and reports it UNCHANGED - never a duplicate. Separately, no two
active variants (file rows or existing rules) may share section + nature +
deductor + rate condition over overlapping dates.

Row outcomes:
    NEW        Code not found -> rule created (active)
    UPDATED    Code found, at least one imported field differs -> rule updated
               (status and rule name are kept - the sheet has no such columns)
    UNCHANGED  Code found, every imported field equal -> untouched
    ERROR      any validation failure -> whole import rejected

Payment natures / deductors: a Nature of Payment or Deductor value that
matches no existing record is PLANNED as a new master (see _MasterPlan for the
deterministic matching rules). validate() only reports them
(new_payment_natures / new_deductors); import_rules() creates them - in the
same transaction as the rules, before them - and only when the caller has
TDS_CONFIG_CREATE (checked by the route, enforced here). Existing masters are
never renamed, described or reactivated by an import.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from Backend.Business_Layer.services.tds_config_service import (
    AUDIT_CREATE,
    AUDIT_IMPORT,
    TdsConfigService,
    _ranges_overlap,
    current_rate_rule,
    rule_payment_nature_code,
    rule_signature,
)
from Backend.Business_Layer.utils.tds_rate_condition import rate_conditions_from_rows, render_rate_condition
from Backend.Data_Access_Layer.models.tds import TdsDeductor, TdsPaymentNature

IMPORT_COLUMNS = (
    "Code",
    "Old Section",
    "New Section",
    "Nature of Payment",
    "Deductor",
    "Rate",
    "Threshold Amount",
    "Threshold Period",
    "Rate Condition",
    "Effective From",
    "Effective To",
)
_COLUMN_TO_KEY = {
    "Code": "code",
    "Old Section": "old_section",
    "New Section": "new_section",
    "Nature of Payment": "payment_nature",
    "Deductor": "deductor",
    "Rate": "rate",
    "Threshold Amount": "threshold_amount",
    "Threshold Period": "threshold_period",
    "Rate Condition": "rate_condition",
    "Effective From": "effective_from",
    "Effective To": "effective_to",
}

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000

ROW_NEW = "NEW"
ROW_UPDATED = "UPDATED"
ROW_UNCHANGED = "UNCHANGED"
ROW_ERROR = "ERROR"


class TdsImportFileError(ValueError):
    """File-level problem (type, size, headers) - no rows were evaluated."""


class TdsImportPermissionError(PermissionError):
    """The file is valid but would create payment natures/deductors and the
    caller lacks TDS_CONFIG_CREATE -> 403. Raised before anything is written."""


MASTER_CODE_MAX_LENGTH = 50
MASTER_NAME_MAX_LENGTH = 150


def _normalize_master_name(value) -> str:
    """Deterministic comparison key: whitespace collapsed, case-folded. No
    fuzzy matching - "Contractor" and "Contractors" are different values."""
    return " ".join(str(value).split()).casefold()


def generate_master_code(value) -> str:
    """Backend-owned code for a new master: upper-case, every run of
    non-alphanumerics -> '_', trimmed. "Director Remuneration" ->
    "DIRECTOR_REMUNERATION"; "Specified Person*" -> "SPECIFIED_PERSON". The
    same name always yields the same code."""
    return re.sub(r"[^A-Z0-9]+", "_", " ".join(str(value).split()).upper()).strip("_")


class _MasterPlan:
    """Resolves one master column (Nature of Payment or Deductor) for a whole
    file, read-only. Loads the table once so every row resolves against the
    same snapshot, and plans - never creates - masters that do not exist.

    Resolution of a cell value V (deterministic, in this order):
      1. existing records whose name equals V (case/whitespace-insensitive)
         or whose code equals V (case-insensitive) - the codes the existing
         template uses keep working;
      2. more than one such record -> error (ambiguous);
      3. V's generated code belongs to a DIFFERENT record than the one matched
         in (1) -> error (ambiguous near-duplicate, e.g. an existing
         "PROFESSIONAL SERVICE" name and an existing PROFESSIONAL_SERVICE code
         on two records);
      4. exactly one match -> use it; if it is inactive -> error (never
         reactivated by an import);
      5. no match, generated code already used by some record -> error (a
         collision is never silently reused);
      6. otherwise -> planned new master {name: V, code: generated}. Several
         rows with the same V share one planned master; two different
         spellings that generate the same code -> error.
    """

    def __init__(self, label: str, column: str, model, existing: list, required: bool):
        self.label = label
        self.column = column
        self.model = model
        self.existing = existing
        self.required = required
        self.planned: dict[str, dict] = {}  # code -> {"obj", "key", "name", "rows"}

    def resolve(self, value, row_number: int):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if value is None or not str(value).strip():
            if self.required:
                raise ValueError(f"{self.column} is required")
            return None

        text = " ".join(str(value).split())
        key = _normalize_master_name(text)
        generated = generate_master_code(text)

        matches = [m for m in self.existing if _normalize_master_name(m.name) == key or m.code.upper() == text.upper()]
        if len(matches) > 1:
            listed = ", ".join(f"'{m.name}' ({m.code})" for m in matches)
            raise ValueError(f"{self.label} '{text}' matches more than one existing {self.label}: {listed} - use the exact code")

        collisions = [m for m in self.existing if m.code.upper() == generated and m not in matches]
        if matches:
            match = matches[0]
            if collisions:
                other = collisions[0]
                raise ValueError(
                    f"{self.label} '{text}' is ambiguous: it matches '{match.name}' ({match.code}) but also resolves to "
                    f"code {other.code} of '{other.name}' - use the exact code"
                )
            if not match.is_active:
                raise ValueError(f"{self.label} '{text}' exists but is inactive. Activate it before importing.")
            return match

        if collisions:
            other = collisions[0]
            raise ValueError(
                f"{self.label} '{text}' does not exist, and the code it would be created with ({generated}) is already "
                f"used by {self.label} '{other.name}'{'' if other.is_active else ' (inactive)'} - use that record's exact "
                f"name or code, or change the value"
            )
        if not generated:
            raise ValueError(f"{self.label} '{text}' must contain letters or digits")
        if len(generated) > MASTER_CODE_MAX_LENGTH:
            raise ValueError(
                f"{self.label} '{text}' is too long to create (its code would exceed {MASTER_CODE_MAX_LENGTH} characters)"
            )
        if len(text) > MASTER_NAME_MAX_LENGTH:
            raise ValueError(f"{self.label} '{text}' cannot exceed {MASTER_NAME_MAX_LENGTH} characters")

        planned = self.planned.get(generated)
        if planned is None:
            planned = {
                "obj": self.model(code=generated, name=text, description=None, is_active=True),
                "key": key,
                "name": text,
                "rows": set(),
            }
            self.planned[generated] = planned
        elif planned["key"] != key:
            rows = ", ".join(str(n) for n in sorted(planned["rows"])) or "another row"
            raise ValueError(
                f"{self.label} '{text}' and '{planned['name']}' (row {rows}) would both be created with code "
                f"{generated} - use one spelling"
            )
        planned["rows"].add(row_number)
        return planned["obj"]

    def summary(self) -> list[dict]:
        return [
            {"name": p["name"], "code": code, "row_numbers": sorted(p["rows"])}
            for code, p in sorted(self.planned.items())
        ]


@dataclass
class _ImportPlan:
    """Everything validate() reports and import_rules() writes - rebuilt from
    the file on every call, never taken from an earlier preview."""
    rows: list
    natures: _MasterPlan
    deductors: _MasterPlan

    @property
    def creates_masters(self) -> bool:
        return bool(self.natures.planned or self.deductors.planned)


@dataclass
class _Row:
    row_number: int
    raw: dict
    code: Optional[str] = None
    rule_input: object = None
    existing: object = None
    status: str = ROW_ERROR
    changes: list = field(default_factory=list)
    errors: list = field(default_factory=list)  # [(field, message)]


class TdsConfigImportService:
    def __init__(self, db):
        self.db = db
        self.config_service = TdsConfigService(db)
        self.dao = self.config_service.dao

    # =========================================================
    # Public
    # =========================================================

    def validate(self, filename: str, content: bytes) -> dict:
        """Read-only: planned payment natures/deductors are reported under
        new_payment_natures/new_deductors, never created."""
        plan = self._evaluate(filename, content)
        return self._report(plan, imported=False)

    def import_rules(self, filename: str, content: bytes, user_id, can_create_masters: bool = False) -> dict:
        """Re-parses and re-resolves the file from scratch, then - only if every
        row is valid and, when new masters are needed, can_create_masters is
        True - writes new masters, then rules, in ONE transaction.

        Row errors are not raised - callers check report['valid']; when it is
        False nothing was written. File-level problems raise TdsImportFileError;
        a valid file that would create masters without permission raises
        TdsImportPermissionError (also before any write)."""
        try:
            plan = self._evaluate(filename, content)
            report = self._report(plan, imported=False)
            if not report["valid"]:
                self.db.rollback()
                return report
            if plan.creates_masters and not can_create_masters:
                self.db.rollback()
                raise TdsImportPermissionError(
                    f"This file would create {len(plan.natures.planned)} payment nature(s) and "
                    f"{len(plan.deductors.planned)} deductor(s) - TDS_CONFIG_CREATE permission is required to import it"
                )

            batch_id = uuid.uuid4().hex
            import_context = {"import_batch_id": batch_id, "import_file": filename}

            # 1) new masters first, so rule rows can reference their ids. The
            #    RuleInputs already hold these same (until now transient)
            #    objects, so flushing them gives every row its id.
            for master_plan, table_name in ((plan.natures, "tds_payment_nature"), (plan.deductors, "tds_deductor")):
                for code, planned in sorted(master_plan.planned.items()):
                    obj = planned["obj"]
                    self.dao.add(obj)
                    self.config_service._audit(
                        table_name, obj.id, AUDIT_CREATE, user_id, None,
                        {**TdsConfigService._master_view(obj), **import_context, "import_rows": sorted(planned["rows"])},
                    )

            # 2) rules
            for row in plan.rows:
                if row.status == ROW_NEW:
                    rule = self.config_service._create_rule_row(row.rule_input, user_id)
                elif row.status == ROW_UPDATED:
                    rule = row.existing
                    self.config_service._apply_rule_input(rule, row.rule_input, user_id)
                else:
                    continue
                self.config_service._audit(
                    "tax_rule", rule.tax_rule_id, AUDIT_IMPORT, user_id,
                    None,
                    {
                        **self.config_service._audit_view(rule),
                        **import_context,
                        "import_row": row.row_number,
                        "import_outcome": row.status,
                        "changed_fields": row.changes or None,
                    },
                )

            self.db.commit()
            report = self._report(plan, imported=True)
            report["import_batch_id"] = batch_id
            return report
        except Exception:
            self.db.rollback()
            raise

    # =========================================================
    # File parsing
    # =========================================================

    def _read_table(self, filename: str, content: bytes) -> list[tuple[int, list]]:
        if not content:
            raise TdsImportFileError("Uploaded file is empty")
        if len(content) > MAX_IMPORT_BYTES:
            raise TdsImportFileError(f"File exceeds the {MAX_IMPORT_BYTES // (1024 * 1024)} MB limit")

        name = (filename or "").lower()
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            return self._read_xlsx(content)
        if name.endswith(".csv"):
            return self._read_csv(content)
        raise TdsImportFileError("Unsupported file type - upload an .xlsx or .csv file")

    @staticmethod
    def _read_xlsx(content: bytes) -> list[tuple[int, list]]:
        try:
            import openpyxl
        except ImportError:  # pragma: no cover - dependency listed in requirements.txt
            raise TdsImportFileError("Excel support is not installed on the server (openpyxl)")
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            raise TdsImportFileError("File could not be read as an Excel workbook")
        try:
            sheet = workbook.worksheets[0]
            return [(index, list(values)) for index, values in enumerate(sheet.iter_rows(values_only=True), start=1)]
        finally:
            workbook.close()

    @staticmethod
    def _read_csv(content: bytes) -> list[tuple[int, list]]:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise TdsImportFileError("CSV file must be UTF-8 encoded")
        return [(index, row) for index, row in enumerate(csv.reader(io.StringIO(text)), start=1)]

    @staticmethod
    def _is_empty(values: list) -> bool:
        return all(v is None or (isinstance(v, str) and not v.strip()) for v in values)

    def _extract_rows(self, filename: str, content: bytes) -> list[_Row]:
        table = self._read_table(filename, content)
        header_index = next((i for i, (_, values) in enumerate(table) if not self._is_empty(values)), None)
        if header_index is None:
            raise TdsImportFileError("File has no header row")

        header_row_number, header_values = table[header_index]
        headers = [str(v).strip() if v is not None else "" for v in header_values]
        while headers and headers[-1] == "":
            headers.pop()

        problems = []
        missing = [c for c in IMPORT_COLUMNS if c not in headers]
        unexpected = [h for h in headers if h and h not in IMPORT_COLUMNS]
        duplicated = sorted({h for h in headers if h and headers.count(h) > 1})
        if missing:
            problems.append("missing column(s): " + ", ".join(missing))
        if unexpected:
            problems.append("unexpected column(s): " + ", ".join(unexpected))
        if duplicated:
            problems.append("duplicated column(s): " + ", ".join(duplicated))
        if "" in headers:
            problems.append("blank column header(s)")
        if problems:
            raise TdsImportFileError(
                f"Invalid header row (row {header_row_number}): " + "; ".join(problems)
                + ". Expected exactly: " + ", ".join(IMPORT_COLUMNS)
            )

        positions = {h: headers.index(h) for h in IMPORT_COLUMNS}
        rows = []
        for row_number, values in table[header_index + 1:]:
            if self._is_empty(values):
                continue
            extra = values[len(headers):]
            raw = {
                _COLUMN_TO_KEY[column]: (values[pos] if pos < len(values) else None)
                for column, pos in positions.items()
            }
            row = _Row(row_number=row_number, raw=raw)
            if not self._is_empty(extra):
                row.errors.append(("Row", "Row has values beyond the last column"))
            rows.append(row)
        if not rows:
            raise TdsImportFileError("File has no data rows")
        if len(rows) > MAX_IMPORT_ROWS:
            raise TdsImportFileError(f"File has {len(rows)} data rows - the limit is {MAX_IMPORT_ROWS}")
        return rows

    # =========================================================
    # Evaluation
    # =========================================================

    def _evaluate(self, filename: str, content: bytes) -> _ImportPlan:
        """Shared by validate() and import_rules(): parse, resolve masters,
        validate rows, classify, check conflicts. Reads only."""
        rows = self._extract_rows(filename, content)
        plan = _ImportPlan(
            rows=rows,
            natures=_MasterPlan("Payment Nature", "Nature of Payment", TdsPaymentNature, self.dao.list_payment_natures(), required=True),
            deductors=_MasterPlan("Deductor", "Deductor", TdsDeductor, self.dao.list_deductors(), required=False),
        )

        # 1) per-row field validation (identical rules to the JSON API, except
        #    that unknown masters are planned instead of rejected)
        for row in rows:
            result = self.config_service.normalize_rule_input(
                row.raw,
                resolve_payment_nature=lambda value, n=row.row_number: plan.natures.resolve(value, n),
                resolve_deductor=lambda value, n=row.row_number: plan.deductors.resolve(value, n),
            )
            row.errors.extend((e.field, e.message) for e in result.errors)
            row.rule_input = result.value
            code = row.rule_input.code if row.rule_input else None
            if code is None and row.raw.get("code") not in (None, ""):
                code = str(row.raw["code"]).strip().upper()
            row.code = code

        # 2) duplicate codes inside the file
        by_code: dict[str, list[_Row]] = {}
        for row in rows:
            if row.code:
                by_code.setdefault(row.code, []).append(row)
        for code, same in by_code.items():
            if len(same) > 1:
                numbers = ", ".join(str(r.row_number) for r in same)
                for row in same:
                    row.errors.append(("Code", f"Duplicate Code '{code}' (rows {numbers})"))

        # 3) match against existing rules, classify NEW / UPDATED / UNCHANGED
        for row in rows:
            if row.rule_input is None or row.errors:
                continue
            existing = self.dao.get_rule_by_code(row.rule_input.code)
            if existing is not None and existing.rule_category != "TDS_RATE":
                row.errors.append(("Code", f"Code '{row.rule_input.code}' is already used by a non-TDS tax rule"))
                continue
            row.existing = existing
            if existing is None:
                row.status = ROW_NEW
                continue
            row.rule_input.is_active = existing.is_active
            row.changes = self._diff(existing, row.rule_input)
            row.status = ROW_UPDATED if row.changes else ROW_UNCHANGED

        # 4) conflicting variants: the post-import state of every active
        #    variant touched by the file vs. every other active variant.
        self._check_variant_conflicts(rows)

        for row in rows:
            if row.errors:
                row.status = ROW_ERROR
        return plan

    @staticmethod
    def _diff(rule, rule_input) -> list[str]:
        rate_row = current_rate_rule(rule)
        current = {
            "Old Section": (rule.old_section or "").upper(),
            "New Section": rule.new_section,
            "Nature of Payment": rule_payment_nature_code(rule),
            "Deductor": rule.tds_deductor.code if rule.tds_deductor else None,
            "Rate": rate_row.rate_percent if rate_row else None,
            "Threshold Amount": rule.threshold_amount,
            "Threshold Period": rule.threshold_type,
            "Rate Condition": render_rate_condition(rate_conditions_from_rows(rule.conditions or [])),
            "Effective From": rule.effective_from,
            "Effective To": rule.effective_to,
        }
        incoming = {
            "Old Section": rule_input.old_section,
            "New Section": rule_input.new_section,
            "Nature of Payment": rule_input.payment_nature.code,
            "Deductor": rule_input.deductor.code if rule_input.deductor else None,
            "Rate": rule_input.rate_percent,
            "Threshold Amount": rule_input.threshold_amount,
            "Threshold Period": rule_input.threshold_type,
            "Rate Condition": rule_input.rate_condition_text,
            "Effective From": rule_input.effective_from,
            "Effective To": rule_input.effective_to,
        }

        def same(a, b):
            if isinstance(a, Decimal) or isinstance(b, Decimal):
                return a is not None and b is not None and Decimal(a) == Decimal(b)
            return a == b

        changed = [label for label in incoming if not same(current[label], incoming[label])]
        if rate_row is not None and rate_row.calculation_type != "PERCENTAGE":
            changed.append("Rate")
        return sorted(set(changed), key=list(incoming).index)

    def _check_variant_conflicts(self, rows: list[_Row]) -> None:
        candidates = [r for r in rows if r.rule_input is not None and not r.errors and r.rule_input.is_active]
        file_codes = {r.rule_input.code for r in candidates}

        # within the file
        for i, a in enumerate(candidates):
            for b in candidates[i + 1:]:
                if a.rule_input.signature() == b.rule_input.signature() and _ranges_overlap(
                    a.rule_input.effective_from, a.rule_input.effective_to,
                    b.rule_input.effective_from, b.rule_input.effective_to,
                ):
                    for row, other in ((a, b), (b, a)):
                        row.errors.append((
                            "Rate Condition",
                            f"Conflicts with row {other.row_number} ('{other.rule_input.code}'): same section, nature of "
                            f"payment, deductor and rate condition over overlapping effective dates",
                        ))

        # against existing active rules the file does not itself redefine
        for row in candidates:
            if row.errors:
                continue
            ri = row.rule_input
            for other in self.dao.list_rules_for_section_and_nature(ri.old_section, ri.payment_nature.code):
                if other.rule_code in file_codes or not other.is_active:
                    continue
                if rule_signature(other) == ri.signature() and _ranges_overlap(
                    ri.effective_from, ri.effective_to, other.effective_from, other.effective_to
                ):
                    row.errors.append((
                        "Rate Condition",
                        f"Conflicts with existing active TDS rule '{other.rule_code}': same section, nature of payment, "
                        f"deductor and rate condition over overlapping effective dates",
                    ))

    # =========================================================
    # Report
    # =========================================================

    @staticmethod
    def _report(plan: _ImportPlan, imported: bool) -> dict:
        rows = plan.rows
        new_natures = plan.natures.summary()
        new_deductors = plan.deductors.summary()
        counts = {status: sum(1 for r in rows if r.status == status) for status in (ROW_NEW, ROW_UPDATED, ROW_UNCHANGED, ROW_ERROR)}
        error_rows = counts[ROW_ERROR]
        return {
            "valid": error_rows == 0,
            "imported": imported,
            "total_rows": len(rows),
            "valid_rows": len(rows) - error_rows,
            "error_rows": error_rows,
            "new_rows": counts[ROW_NEW],
            "updated_rows": counts[ROW_UPDATED],
            "unchanged_rows": counts[ROW_UNCHANGED],
            "errors": [
                {"row": r.row_number, "field": f, "message": m}
                for r in rows for f, m in r.errors
            ],
            "rows": [
                {
                    "row": r.row_number,
                    "code": r.code,
                    "status": r.status,
                    "existing_rule_id": r.existing.tax_rule_id if r.existing is not None else None,
                    "changed_fields": r.changes,
                }
                for r in rows
            ],
            # Set by import_rules() on success. Always present so the 422
            # detail (a raw dict, not passed through the response model) has
            # the same keys as the 200 body.
            "import_batch_id": None,
            # On validate: what import WOULD create. On a successful import:
            # what it DID create. Existing masters matched by name/code never
            # appear here.
            "new_payment_natures": new_natures,
            "new_deductors": new_deductors,
            "new_payment_nature_count": len(new_natures),
            "new_deductor_count": len(new_deductors),
        }

