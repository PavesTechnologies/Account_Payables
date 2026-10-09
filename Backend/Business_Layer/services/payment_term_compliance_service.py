# Backend/Business_Layer/services/payment_term_compliance_service.py
"""Payment-term compliance (APM_AUTOMATION_PLAN.md 3.1 / 3.2).

Decides, for one invoice, which payment terms are authoritative, whether the
invoice agrees with them, and the resulting due dates - keeping three dates
apart:

* contractual_due_date - basis date + the authoritative term days
* statutory_due_date   - MSMED Act s.15 limit for MICRO/SMALL suppliers
* effective_due_date   - the earlier of the two; mirrored into invoice.due_date
                         so every existing due-date query keeps working

The actual payment date stays on ap.payment. OVERDUE is never stored - it is
"effective_due_date < today with a balance outstanding", computed by readers.

Authoritative source (first matching rule wins, see decide()):
  PO invoice      -> the linked PO's terms (never silently overridden)
  NON_PO invoice  -> an ACTIVE agreement valid on the invoice date, else the
                     vendor-master term
Missing, ambiguous or conflicting terms are flagged (REVIEW_REQUIRED /
MISMATCH) instead of assuming a default; Finance resolves them with verify(),
which is mandatory before Mark Ready for Payment (require_resolved_for_payment).

This service never commits - callers own the transaction, like the TDS and
approval services.
"""
from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from Backend.Business_Layer.utils import invoice_status
from Backend.Business_Layer.utils.payment_term_parser import (
    BASIS_GRN_DATE,
    BASIS_INVOICE_DATE,
    KIND_AMBIGUOUS,
    KIND_NONE,
    parse_payment_terms,
)
from Backend.Business_Layer.utils.vendor_auto_onboarding import get_numeric_system_config
from Backend.Data_Access_Layer.dao.payment_term_dao import PaymentTermDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.payment_terms import DUE_BASES, InvoicePaymentTerm

STATUS_COMPLIANT = "COMPLIANT"
STATUS_MISMATCH = "MISMATCH"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUS_VERIFIED_OVERRIDE = "VERIFIED_OVERRIDE"
VALIDATION_STATUSES = (STATUS_COMPLIANT, STATUS_MISMATCH, STATUS_REVIEW_REQUIRED, STATUS_VERIFIED_OVERRIDE)
EXCEPTION_STATUSES = (STATUS_MISMATCH, STATUS_REVIEW_REQUIRED)
PAYABLE_TERM_STATUSES = frozenset({STATUS_COMPLIANT, STATUS_VERIFIED_OVERRIDE})

SOURCE_PO = "PO"
SOURCE_AGREEMENT = "AGREEMENT"
SOURCE_VENDOR_MASTER = "VENDOR_MASTER"
SOURCE_MANUAL = "MANUAL"
SOURCE_NONE = "NONE"

REASON_PO_NOT_MATCHED = "PO_NOT_MATCHED"
REASON_PO_TERMS_MISSING = "PO_TERMS_MISSING"
REASON_INVOICE_VS_PO = "INVOICE_VS_PO"
REASON_INVOICE_SILENT_PO_TERMS_APPLIED = "INVOICE_SILENT_PO_TERMS_APPLIED"
REASON_INVOICE_TERMS_MISSING = "INVOICE_TERMS_MISSING"
REASON_INVOICE_TERMS_AMBIGUOUS = "INVOICE_TERMS_AMBIGUOUS"
REASON_VENDOR_MASTER_VS_AGREEMENT = "VENDOR_MASTER_VS_AGREEMENT"
REASON_NO_AUTHORISED_TERMS = "NO_AUTHORISED_TERMS"
REASON_INVOICE_VS_AGREEMENT = "INVOICE_VS_AGREEMENT"
REASON_INVOICE_VS_VENDOR_MASTER = "INVOICE_VS_VENDOR_MASTER"
REASON_AGREEMENT_EXPIRED = "AGREEMENT_EXPIRED"
REASON_IMPLIED_FROM_PRINTED_DUE_DATE = "IMPLIED_FROM_PRINTED_DUE_DATE"
REASON_GRN_DATE_MISSING = "GRN_DATE_MISSING"
REASON_MANUALLY_VERIFIED = "MANUALLY_VERIFIED"

REASON_TEXT = {
    REASON_PO_NOT_MATCHED: "The invoice is a PO invoice but is not linked to a purchase order.",
    REASON_PO_TERMS_MISSING: "The linked purchase order has no usable payment terms.",
    REASON_INVOICE_VS_PO: "The invoice payment terms differ from the purchase order; the PO terms apply.",
    REASON_INVOICE_SILENT_PO_TERMS_APPLIED: "The invoice states no terms; the purchase order terms apply.",
    REASON_INVOICE_TERMS_MISSING: "The invoice states no payment terms and no due date.",
    REASON_INVOICE_TERMS_AMBIGUOUS: "The invoice payment terms cannot be read as a definite number of days.",
    REASON_VENDOR_MASTER_VS_AGREEMENT: "The vendor agreement and the vendor master disagree on payment terms.",
    REASON_NO_AUTHORISED_TERMS: "No valid vendor agreement and no vendor-master payment term to check against.",
    REASON_INVOICE_VS_AGREEMENT: "The invoice payment terms differ from the vendor agreement; the agreement applies.",
    REASON_INVOICE_VS_VENDOR_MASTER: "The invoice payment terms differ from the vendor master; the vendor master applies.",
    REASON_AGREEMENT_EXPIRED: "The vendor has agreements on file but none is valid on the invoice date.",
    REASON_IMPLIED_FROM_PRINTED_DUE_DATE: "No terms printed; the printed due date implies the agreed period.",
    REASON_GRN_DATE_MISSING: "The terms run from the goods-receipt date, but no GRN date is recorded yet.",
    REASON_MANUALLY_VERIFIED: "Payment terms verified manually by Finance.",
}

MSME_MAX_DAYS_CONFIG_KEY = "MSME_MAX_PAYMENT_DAYS"
MSME_DEFAULT_DAYS_CONFIG_KEY = "MSME_DEFAULT_PAYMENT_DAYS"
MSME_STATUTORY_CATEGORIES = frozenset({"MICRO", "SMALL"})

CLOSED_INVOICE_STATUS_CODES = (invoice_status.STATUS_CODE_PAID, invoice_status.STATUS_CODE_REJECTED)

_KEEP = object()


# ---------------------------------------------------------------------------
# Pure decision logic (no DB) - unit-tested directly
# ---------------------------------------------------------------------------

@dataclass
class TermInputs:
    invoice_date: datetime.date
    is_po_invoice: bool
    invoice_term_days: Optional[int] = None
    invoice_term_basis: str = BASIS_INVOICE_DATE
    invoice_terms_ambiguous: bool = False
    invoice_due_date_printed: Optional[datetime.date] = None
    po_linked: bool = False
    po_term_days: Optional[int] = None
    po_term_basis: str = BASIS_INVOICE_DATE
    grn_date: Optional[datetime.date] = None
    agreement_id: Optional[int] = None
    agreement_term_days: Optional[int] = None
    agreement_term_basis: str = BASIS_INVOICE_DATE
    vendor_has_agreement_history: bool = False
    vendor_master_term_days: Optional[int] = None
    msme_category: Optional[str] = None
    msme_max_days: int = 45
    msme_default_days: int = 15


@dataclass
class TermDecision:
    validation_status: str
    reason_code: Optional[str]
    reference_source: str
    applied_term_days: Optional[int]
    suggested_term_days: Optional[int]
    due_basis: str
    basis_date: Optional[datetime.date]
    contractual_due_date: Optional[datetime.date]
    statutory_due_date: Optional[datetime.date]
    statutory_rule: Optional[str]
    effective_due_date: Optional[datetime.date]
    due_date_verified: bool
    invoice_term_days: Optional[int]
    implied_from_due_date: bool = False
    notes: List[str] = field(default_factory=list)


def statutory_limit(
    msme_category: Optional[str], agreed_days: Optional[int], basis_date: Optional[datetime.date],
    max_days: int, default_days: int,
):
    """MSMED Act s.15: pay MICRO/SMALL suppliers by the agreed date, which may not exceed
    max_days (45) from acceptance; default_days (15) when nothing is agreed."""
    if msme_category not in MSME_STATUTORY_CATEGORIES or basis_date is None:
        return None, None
    if agreed_days is None:
        return basis_date + datetime.timedelta(days=default_days), f"MSMED_S15_{default_days}_DAYS_NO_AGREEMENT"
    return basis_date + datetime.timedelta(days=min(agreed_days, max_days)), f"MSMED_S15_{max_days}_DAYS"


def decide(i: TermInputs) -> TermDecision:
    inv_days = i.invoice_term_days
    implied = False
    if inv_days is None and not i.invoice_terms_ambiguous and i.invoice_due_date_printed is not None \
            and i.invoice_due_date_printed >= i.invoice_date:
        inv_days = (i.invoice_due_date_printed - i.invoice_date).days
        implied = True

    status: str
    reason: Optional[str] = None
    source = SOURCE_NONE
    applied: Optional[int] = None
    suggested: Optional[int] = None
    basis = i.invoice_term_basis

    if i.is_po_invoice:
        source, basis = SOURCE_PO, i.po_term_basis
        if not i.po_linked:
            status, reason, suggested = STATUS_REVIEW_REQUIRED, REASON_PO_NOT_MATCHED, inv_days
            basis = i.invoice_term_basis
        elif i.po_term_days is None:
            status, reason, suggested = STATUS_REVIEW_REQUIRED, REASON_PO_TERMS_MISSING, inv_days
            basis = i.invoice_term_basis
        elif inv_days is not None and inv_days != i.po_term_days:
            status, reason, applied = STATUS_MISMATCH, REASON_INVOICE_VS_PO, i.po_term_days
        else:
            status, applied = STATUS_COMPLIANT, i.po_term_days
            if inv_days is None:
                reason = REASON_INVOICE_SILENT_PO_TERMS_APPLIED
            elif implied:
                reason = REASON_IMPLIED_FROM_PRINTED_DUE_DATE
    else:
        agreement_days = i.agreement_term_days if i.agreement_id is not None else None
        reference = agreement_days if agreement_days is not None else i.vendor_master_term_days
        if agreement_days is not None:
            source, basis = SOURCE_AGREEMENT, i.agreement_term_basis
        elif i.vendor_master_term_days is not None:
            source = SOURCE_VENDOR_MASTER

        if inv_days is None:
            status = STATUS_REVIEW_REQUIRED
            reason = REASON_INVOICE_TERMS_AMBIGUOUS if i.invoice_terms_ambiguous else REASON_INVOICE_TERMS_MISSING
            suggested = reference
        elif agreement_days is not None and i.vendor_master_term_days is not None \
                and agreement_days != i.vendor_master_term_days:
            status, reason, applied = STATUS_MISMATCH, REASON_VENDOR_MASTER_VS_AGREEMENT, agreement_days
        elif reference is None:
            status, reason, suggested = STATUS_REVIEW_REQUIRED, REASON_NO_AUTHORISED_TERMS, inv_days
        elif inv_days != reference:
            status, applied = STATUS_MISMATCH, reference
            reason = REASON_INVOICE_VS_AGREEMENT if agreement_days is not None else REASON_INVOICE_VS_VENDOR_MASTER
        elif i.vendor_has_agreement_history and agreement_days is None:
            status, reason, suggested = STATUS_REVIEW_REQUIRED, REASON_AGREEMENT_EXPIRED, reference
        else:
            status, applied = STATUS_COMPLIANT, reference
            reason = REASON_IMPLIED_FROM_PRINTED_DUE_DATE if implied else None

    basis_date: Optional[datetime.date] = i.invoice_date
    if basis == BASIS_GRN_DATE:
        basis_date = i.grn_date
        if basis_date is None and status != STATUS_REVIEW_REQUIRED:
            status, reason = STATUS_REVIEW_REQUIRED, REASON_GRN_DATE_MISSING
            suggested, applied = applied, None

    contractual = None
    if status in (STATUS_COMPLIANT, STATUS_MISMATCH) and applied is not None and basis_date is not None:
        contractual = basis_date + datetime.timedelta(days=applied)

    agreed = applied if applied is not None else suggested
    statutory, statutory_rule = statutory_limit(
        i.msme_category, agreed, basis_date, i.msme_max_days, i.msme_default_days
    )
    candidates = [d for d in (contractual, statutory) if d is not None]
    effective = min(candidates) if candidates else None

    return TermDecision(
        validation_status=status,
        reason_code=reason,
        reference_source=source,
        applied_term_days=applied,
        suggested_term_days=suggested,
        due_basis=basis if basis in DUE_BASES else BASIS_INVOICE_DATE,
        basis_date=basis_date,
        contractual_due_date=contractual,
        statutory_due_date=statutory,
        statutory_rule=statutory_rule,
        effective_due_date=effective,
        due_date_verified=status == STATUS_COMPLIANT,
        invoice_term_days=inv_days,
        implied_from_due_date=implied,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

def _find_key(data: Any, key: str, depth: int = 0):
    """First value for ``key`` in a nested raw-extraction dict (both extraction pipelines
    dump differently-shaped models into inbound_document.raw_extracted_data)."""
    if depth > 4 or not isinstance(data, dict):
        return None
    if key in data and data[key] not in (None, ""):
        value = data[key]
        if isinstance(value, dict) and "value" in value:
            value = value.get("value")
        return value
    for child in data.values():
        if isinstance(child, dict):
            found = _find_key(child, key, depth + 1)
            if found not in (None, ""):
                return found
    return None


def _as_date(value) -> Optional[datetime.date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _user(user_id) -> Optional[str]:
    return str(user_id) if user_id is not None else None


class PaymentTermComplianceService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.dao = PaymentTermDAO(db)
        self._today = today

    @property
    def today(self) -> datetime.date:
        return self._today or datetime.date.today()

    # ---------------------------------------------------------------
    # Evaluation
    # ---------------------------------------------------------------
    def evaluate_invoice(
        self,
        invoice,
        user_id=None,
        *,
        stated_terms_text=_KEEP,
        stated_due_date=_KEEP,
        reset_override: bool = False,
    ) -> InvoicePaymentTerm:
        """(Re)compute and persist (flush only) the invoice's payment-term record, and mirror the
        effective due date into invoice.due_date. ``stated_*`` are what the invoice itself says;
        when omitted, the previously stored values (or the raw extraction) are used. A Finance
        override survives a recheck unless one of its inputs changed or reset_override is set."""
        record = self.dao.get_record(invoice.invoice_id)
        is_new = record is None
        if is_new:
            record = InvoicePaymentTerm(invoice_id=invoice.invoice_id)

        if stated_terms_text is _KEEP:
            stated_terms_text = record.invoice_terms_text if not is_new else self._raw_value(invoice, "payment_terms")
        if stated_due_date is _KEEP:
            stated_due_date = record.invoice_due_date_printed if not is_new else _as_date(
                self._raw_value(invoice, "due_date")
            )
        stated_terms_text = (str(stated_terms_text).strip()[:500] or None) if stated_terms_text else None
        stated_due_date = _as_date(stated_due_date)

        inputs, context = self._gather_inputs(invoice, stated_terms_text, stated_due_date)
        decision = decide(inputs)

        previous_status = None if is_new else record.validation_status
        keep_override = (
            not is_new
            and not reset_override
            and record.validation_status == STATUS_VERIFIED_OVERRIDE
            and self._same_inputs(record, inputs, decision, context)
        )

        record.invoice_terms_text = stated_terms_text
        record.invoice_term_days = inputs.invoice_term_days
        record.invoice_due_date_printed = stated_due_date
        record.po_terms_text = context.get("po_terms_text")
        record.po_term_days = inputs.po_term_days
        record.vendor_master_term_id = context.get("vendor_master_term_id")
        record.vendor_master_term_days = inputs.vendor_master_term_days
        record.agreement_id = inputs.agreement_id
        record.agreement_term_days = inputs.agreement_term_days
        record.checked_at = datetime.datetime.utcnow()
        record.updated_at = datetime.datetime.utcnow()

        if not keep_override:
            override_lost = previous_status == STATUS_VERIFIED_OVERRIDE
            record.reference_source = decision.reference_source
            record.applied_term_days = decision.applied_term_days
            record.suggested_term_days = decision.suggested_term_days
            record.due_basis = decision.due_basis
            record.basis_date = decision.basis_date
            record.contractual_due_date = decision.contractual_due_date
            record.statutory_due_date = decision.statutory_due_date
            record.statutory_rule = decision.statutory_rule
            record.effective_due_date = decision.effective_due_date
            record.due_date_verified = decision.due_date_verified
            record.validation_status = decision.validation_status
            record.reason_code = decision.reason_code
            detail = REASON_TEXT.get(decision.reason_code) if decision.reason_code else None
            if override_lost:
                detail = ("A previous manual verification no longer applies because the source terms changed. "
                          + (detail or ""))
                record.verified_by = record.verified_at = None
                record.verification_remarks = None
            record.reason_detail = detail[:500] if detail else None

        if is_new:
            self.dao.add(record)
        else:
            self.db.flush()

        self._mirror_due_date(invoice, record, inputs)

        if previous_status != record.validation_status:
            self.db.add(AuditLog(
                table_name="invoice",
                record_id=invoice.invoice_id,
                action="INVOICE_PAYMENT_TERMS_CHECKED",
                changed_by=_user(user_id),
                old_values={"validation_status": previous_status} if previous_status else None,
                new_values={
                    "validation_status": record.validation_status,
                    "reason_code": record.reason_code,
                    "reference_source": record.reference_source,
                    "effective_due_date": record.effective_due_date.isoformat() if record.effective_due_date else None,
                },
            ))
        return record

    def evaluate_invoice_id(self, invoice_id: int, user_id=None, reset_override: bool = False) -> InvoicePaymentTerm:
        invoice = self.dao.get_invoice(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        return self.evaluate_invoice(invoice, user_id, reset_override=reset_override)

    def recheck_open_invoices_for_vendor(self, vendor_id: int, user_id=None) -> int:
        count = 0
        for invoice_id in self.dao.list_open_invoice_ids_for_vendor(vendor_id, CLOSED_INVOICE_STATUS_CODES):
            self.evaluate_invoice_id(invoice_id, user_id)
            count += 1
        return count

    # ---------------------------------------------------------------
    # Finance resolution + Ready-for-Payment gate
    # ---------------------------------------------------------------
    def verify(
        self,
        invoice_id: int,
        applied_term_days: Optional[int],
        due_basis: Optional[str],
        remarks: Optional[str],
        user_id,
    ) -> InvoicePaymentTerm:
        invoice = self.dao.get_invoice(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        status_code = invoice.status.status_code if invoice.status else None
        if status_code in CLOSED_INVOICE_STATUS_CODES:
            raise ValueError(f"Payment terms cannot be changed while the invoice is {status_code}")

        record = self.dao.get_record(invoice_id) or self.evaluate_invoice(invoice, user_id)
        remarks = (remarks or "").strip()
        if len(remarks) < 5:
            raise ValueError("Remarks are required (at least 5 characters) to verify payment terms")
        if applied_term_days is None:
            applied_term_days = record.applied_term_days if record.applied_term_days is not None else record.suggested_term_days
        if applied_term_days is None or not (0 <= int(applied_term_days) <= 365):
            raise ValueError("applied_term_days must be between 0 and 365")
        applied_term_days = int(applied_term_days)
        due_basis = (due_basis or record.due_basis or BASIS_INVOICE_DATE).strip().upper()
        if due_basis not in DUE_BASES:
            raise ValueError(f"due_basis must be one of {', '.join(DUE_BASES)}")

        inputs, _ = self._gather_inputs(invoice, record.invoice_terms_text, record.invoice_due_date_printed)
        basis_date = invoice.invoice_date if due_basis == BASIS_INVOICE_DATE else inputs.grn_date
        if basis_date is None:
            raise ValueError("No goods-receipt date is recorded for this invoice; choose INVOICE_DATE or record the GRN first")

        before = {
            "validation_status": record.validation_status,
            "applied_term_days": record.applied_term_days,
            "effective_due_date": record.effective_due_date.isoformat() if record.effective_due_date else None,
        }
        contractual = basis_date + datetime.timedelta(days=applied_term_days)
        statutory, statutory_rule = statutory_limit(
            inputs.msme_category, applied_term_days, basis_date, inputs.msme_max_days, inputs.msme_default_days
        )
        effective = min(d for d in (contractual, statutory) if d is not None)

        matching_source = SOURCE_MANUAL
        if inputs.is_po_invoice and applied_term_days == inputs.po_term_days:
            matching_source = SOURCE_PO
        elif inputs.agreement_id is not None and applied_term_days == inputs.agreement_term_days:
            matching_source = SOURCE_AGREEMENT
        elif applied_term_days == inputs.vendor_master_term_days:
            matching_source = SOURCE_VENDOR_MASTER

        now = datetime.datetime.utcnow()
        record.reference_source = matching_source
        record.applied_term_days = applied_term_days
        record.due_basis = due_basis
        record.basis_date = basis_date
        record.contractual_due_date = contractual
        record.statutory_due_date = statutory
        record.statutory_rule = statutory_rule
        record.effective_due_date = effective
        record.due_date_verified = True
        record.validation_status = STATUS_VERIFIED_OVERRIDE
        record.reason_code = REASON_MANUALLY_VERIFIED
        record.reason_detail = REASON_TEXT[REASON_MANUALLY_VERIFIED]
        record.verified_by = _user(user_id)
        record.verified_at = now
        record.verification_remarks = remarks
        record.updated_at = now
        invoice.due_date = effective
        invoice.updated_by = _user(user_id)
        self.db.add(AuditLog(
            table_name="invoice",
            record_id=invoice.invoice_id,
            action="INVOICE_PAYMENT_TERMS_VERIFIED",
            changed_by=_user(user_id),
            old_values=before,
            new_values={
                "validation_status": STATUS_VERIFIED_OVERRIDE,
                "applied_term_days": applied_term_days,
                "due_basis": due_basis,
                "reference_source": matching_source,
                "effective_due_date": effective.isoformat(),
                "remarks": remarks,
            },
        ))
        self.db.flush()
        return record

    def require_resolved_for_payment(self, invoice, user_id=None) -> InvoicePaymentTerm:
        """Ready-for-Payment gate: an invoice may only be marked ready once its payment terms
        are COMPLIANT or verified by Finance. Evaluates first if the invoice predates this
        feature, so legacy invoices are checked rather than waved through."""
        record = self.dao.get_record(invoice.invoice_id) or self.evaluate_invoice(invoice, user_id)
        if record.validation_status not in PAYABLE_TERM_STATUSES:
            reason = REASON_TEXT.get(record.reason_code or "", record.reason_code or "unresolved")
            raise ValueError(
                f"Payment terms must be verified before invoice {invoice.invoice_id} can be marked ready "
                f"for payment ({record.validation_status}: {reason})"
            )
        return record

    # ---------------------------------------------------------------
    # Read models
    # ---------------------------------------------------------------
    def get_summary(self, invoice_id: int) -> Dict[str, Any]:
        invoice = self.dao.get_invoice(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        record = self.dao.get_record(invoice_id)
        return self.to_dict(record, invoice)

    def to_dict(self, record: Optional[InvoicePaymentTerm], invoice) -> Dict[str, Any]:
        status_code = invoice.status.status_code if getattr(invoice, "status", None) else None
        if record is None:
            return {
                "invoice_id": invoice.invoice_id,
                "evaluated": False,
                "validation_status": None,
                "invoice_status": status_code,
                "due_date": invoice.due_date,
            }
        effective = record.effective_due_date
        days_to_due = (effective - self.today).days if effective else None
        closed = status_code in CLOSED_INVOICE_STATUS_CODES
        data = {
            column.name: getattr(record, column.name) for column in InvoicePaymentTerm.__table__.columns
        }
        data.update(
            evaluated=True,
            invoice_status=status_code,
            due_date=invoice.due_date,
            reason_text=record.reason_detail or REASON_TEXT.get(record.reason_code or ""),
            days_to_due=days_to_due,
            is_overdue=bool(days_to_due is not None and days_to_due < 0 and not closed),
            is_exception=record.validation_status in EXCEPTION_STATUSES,
            blocks_ready_for_payment=record.validation_status not in PAYABLE_TERM_STATUSES,
            msme_statutory=record.statutory_due_date is not None,
        )
        return data

    def list_exceptions(
        self,
        statuses: Optional[Iterable[str]] = None,
        vendor_id: Optional[int] = None,
        reason_code: Optional[str] = None,
        due_from: Optional[datetime.date] = None,
        due_to: Optional[datetime.date] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        statuses = [s.strip().upper() for s in (statuses or EXCEPTION_STATUSES) if s and s.strip()]
        bad = [s for s in statuses if s not in VALIDATION_STATUSES]
        if bad:
            raise ValueError(f"Unknown validation status: {', '.join(bad)}")
        page = max(1, int(page))
        page_size = min(max(1, int(page_size)), 100)
        rows, total = self.dao.list_exceptions(
            statuses, CLOSED_INVOICE_STATUS_CODES, vendor_id, reason_code, due_from, due_to, search, page, page_size
        )
        items = []
        for record, invoice, vendor_name, status_code in rows:
            item = self.to_dict(record, invoice)
            item.update(
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                invoice_type=invoice.invoice_type,
                vendor_id=invoice.vendor_id,
                vendor_name=vendor_name,
                invoice_status=status_code,
                net_amount=invoice.net_amount,
                amount_paid=invoice.amount_paid,
            )
            items.append(item)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ---------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------
    def _raw_value(self, invoice, key: str):
        document = getattr(invoice, "inbound_document", None)
        raw = getattr(document, "raw_extracted_data", None) if document is not None else None
        return _find_key(raw, key) if raw else None

    def _msme_days(self):
        max_days = get_numeric_system_config(self.db, MSME_MAX_DAYS_CONFIG_KEY, Decimal("45"))
        default_days = get_numeric_system_config(self.db, MSME_DEFAULT_DAYS_CONFIG_KEY, Decimal("15"))
        return int(max_days if max_days is not None else 45), int(default_days if default_days is not None else 15)

    def _term_days_of(self, payment_term_id: Optional[int]) -> Optional[int]:
        term = self.dao.get_payment_term(payment_term_id)
        return int(term.due_days) if term is not None else None

    def _gather_inputs(self, invoice, stated_terms_text, stated_due_date):
        context: Dict[str, Any] = {}
        parsed = parse_payment_terms(stated_terms_text)
        invoice_days, invoice_basis = parsed.days, parsed.basis
        ambiguous = parsed.kind == KIND_AMBIGUOUS
        if invoice_days is None and parsed.kind == KIND_NONE and invoice.payment_term_id is not None:
            # A term chosen during OCR review counts as what the invoice says.
            invoice_days = self._term_days_of(invoice.payment_term_id)

        is_po_invoice = (invoice.invoice_type or "").upper() == "PO" or invoice.po_id is not None
        po = self.dao.get_purchase_order(invoice.po_id) if is_po_invoice else None
        po_days, po_basis = None, BASIS_INVOICE_DATE
        grn_date = None
        if po is not None:
            context["po_terms_text"] = po.payment_terms
            po_parsed = parse_payment_terms(po.payment_terms)
            po_days = self._term_days_of(getattr(po, "payment_term_id", None))
            if po_days is None:
                po_days = po_parsed.days
            po_basis = po_parsed.basis
            grn = self.dao.get_goods_receipt(invoice.grn_id) if invoice.grn_id else None
            if grn is None or grn.receipt_date is None:
                grn = self.dao.get_latest_goods_receipt_for_po(po.po_id)
            grn_date = grn.receipt_date if grn is not None else None

        vendor = self.dao.get_vendor(invoice.vendor_id)
        master_days = None
        if vendor is not None and vendor.payment_term_id is not None:
            context["vendor_master_term_id"] = vendor.payment_term_id
            master_days = self._term_days_of(vendor.payment_term_id)

        agreement_id = agreement_days = None
        agreement_basis = BASIS_INVOICE_DATE
        history = False
        if not is_po_invoice and vendor is not None:
            valid = self.dao.get_active_agreements_valid_on(vendor.vendor_id, invoice.invoice_date)
            usable = [a for a in valid if a.term_days is not None or a.payment_term_id is not None]
            if usable:
                agreement = usable[0]
                agreement_id = agreement.agreement_id
                agreement_days = agreement.term_days if agreement.term_days is not None else self._term_days_of(
                    agreement.payment_term_id
                )
                agreement_basis = agreement.due_basis or BASIS_INVOICE_DATE
            history = self.dao.has_any_active_agreement_history(vendor.vendor_id)

        max_days, default_days = self._msme_days()
        inputs = TermInputs(
            invoice_date=invoice.invoice_date,
            is_po_invoice=is_po_invoice,
            invoice_term_days=invoice_days,
            invoice_term_basis=invoice_basis,
            invoice_terms_ambiguous=ambiguous,
            invoice_due_date_printed=stated_due_date,
            po_linked=po is not None,
            po_term_days=po_days,
            po_term_basis=po_basis,
            grn_date=grn_date,
            agreement_id=agreement_id,
            agreement_term_days=agreement_days,
            agreement_term_basis=agreement_basis,
            vendor_has_agreement_history=history,
            vendor_master_term_days=master_days,
            msme_category=(vendor.msme_category if vendor is not None and vendor.msme_registered else None),
            msme_max_days=max_days,
            msme_default_days=default_days,
        )
        return inputs, context

    @staticmethod
    def _same_inputs(record: InvoicePaymentTerm, inputs: TermInputs, decision: TermDecision, context) -> bool:
        return (
            record.invoice_term_days == decision.invoice_term_days
            and record.invoice_due_date_printed == inputs.invoice_due_date_printed
            and record.po_term_days == inputs.po_term_days
            and record.agreement_id == inputs.agreement_id
            and record.agreement_term_days == inputs.agreement_term_days
            and record.vendor_master_term_days == inputs.vendor_master_term_days
        )

    @staticmethod
    def _mirror_due_date(invoice, record: InvoicePaymentTerm, inputs: TermInputs) -> None:
        """invoice.due_date (NOT NULL) = the effective due date when known. Otherwise the best
        invoice-stated date - never the bare invoice date while terms are readable; the record
        stays due_date_verified=False so readers bucket it as 'due date unverified'."""
        if record.effective_due_date is not None:
            invoice.due_date = record.effective_due_date
        elif inputs.invoice_due_date_printed is not None:
            invoice.due_date = inputs.invoice_due_date_printed
        elif record.invoice_term_days is not None:
            invoice.due_date = invoice.invoice_date + datetime.timedelta(days=record.invoice_term_days)
        elif invoice.due_date is None:
            invoice.due_date = invoice.invoice_date


def decision_as_dict(decision: TermDecision) -> Dict[str, Any]:
    return asdict(decision)


def resolve_payment_term_id(db, terms_text: Optional[str]) -> Optional[int]:
    """payment_term row for printed terms: exact name first (case-insensitive), then by the
    parsed number of days - so "Net 30 days" / "30 days credit" map to "Net 30" instead of
    NULL. None when the text is missing or not a definite number of days."""
    if not terms_text or not str(terms_text).strip():
        return None
    from Backend.Data_Access_Layer.models.master import PaymentTerm
    from sqlalchemy import func

    text_value = str(terms_text).strip()
    by_name = (
        db.query(PaymentTerm)
        .filter(func.lower(PaymentTerm.term_name) == text_value.lower(), PaymentTerm.is_active.is_(True))
        .first()
    )
    if by_name is not None:
        return by_name.payment_term_id
    parsed = parse_payment_terms(text_value)
    if parsed.days is None:
        return None
    term = PaymentTermDAO(db).get_active_payment_term_by_days(parsed.days)
    return term.payment_term_id if term is not None else None
