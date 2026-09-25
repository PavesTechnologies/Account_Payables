# Backend/Business_Layer/services/tds_determination_service.py
"""TDS (India withholding-tax) determination for an invoice.

Design (spec section 2):
    Purchase Category -> suggested TdsPaymentNature -> AP Executive
    confirms/corrects -> TDS rule engine (ap.tax_rule/tax_rate_rule, same
    generic framework GST rates use) -> InvoiceTds snapshot -> Finance
    verification.

Follows this codebase's existing conventions exactly (see
invoice_approval_service.py / payment_service.py):
    - plain ValueError for every business-rule violation, no HTTPException
      here (the route layer maps ValueError -> 404/422, see tds_route.py).
    - service methods own db.commit()/db.rollback() (DAOs only add/flush).
    - InvoiceDAO/VendorDAO are reused as-is, not duplicated.

Deliberately NOT wired into InvoiceApprovalService.send_for_approval or
PaymentService.mark_ready_for_payment in this phase - see the implementation
report's "Workflow integration" section for why (in short: those services'
existing unit tests construct them against a hand-rolled FakeDB with no
.query() support at all, so any unconditional new DAO call inside them -
even one gated behind a config flag that defaults off - breaks the whole
existing suite before the flag is ever read). The frontend sequences
determine() before send-for-approval and verify() before mark-ready-for-
payment; a later phase can add a real gate once that reworks (or provides a
DB-backed double for) those tests.
"""
from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from Backend.Business_Layer.utils.vendor_auto_onboarding import GST_ACTIVE_STATUS, call_gst_search
from Backend.Business_Layer.utils.vendor_validator import PAN_REGEX
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.dao.tds_dao import TdsDAO
from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.tds import InvoiceTds, TdsPaymentNature, VendorTdsProfile

DETERMINATION_STATUS_PENDING = "PENDING"
DETERMINATION_STATUS_DETERMINED = "DETERMINED"
DETERMINATION_STATUS_VERIFIED = "VERIFIED"

PAN_STATUS_VALID = "VALID"
PAN_STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"

# Section 206AA statutory floor when PAN is missing/invalid - a Phase 1
# simplification (does not distinguish non-resident/treaty scenarios); see
# the implementation report.
PAN_MISSING_RATE_FLOOR = Decimal("20.0000")

THRESHOLD_TYPE_PER_TRANSACTION = "PER_TRANSACTION"
THRESHOLD_TYPE_AGGREGATE_PERIOD = "AGGREGATE_PERIOD"

# GST registration compliance signal - a warning surfaced alongside the
# determination, never an input to tds_applicable/tds_rate/tds_amount (see
# _check_gst_compliance). Distinct from the vendor's actual status strings
# returned by Sandbox (e.g. "Active", "Cancelled", "Suspended").
GSTIN_STATUS_NOT_ON_FILE = "NOT_ON_FILE"
GSTIN_STATUS_CHECK_UNAVAILABLE = "CHECK_UNAVAILABLE"
GST_TAX_REGISTRATION_TYPES = ("GST", "GSTIN")

# The 4th character of a valid Indian PAN deterministically encodes the
# holder's entity type (Income Tax Dept spec) - same fact vendor_validator.py
# already checks (PAN_ENTITY_TYPE_CODES) when validating a PAN's format, just
# not previously turned into a stored value anywhere. Reused here, not
# duplicated, so a malformed/dummy PAN is rejected the exact same way in both
# places.
_ENTITY_TYPE_BY_PAN_CODE = {
    "P": "INDIVIDUAL",
    "C": "COMPANY",
    "H": "HUF",
    "F": "FIRM",
    "A": "AOP",
    "T": "TRUST",
    "B": "BOI",
    "L": "LOCAL_AUTHORITY",
    "J": "ARTIFICIAL_JURIDICAL_PERSON",
    "G": "GOVERNMENT",
}

_CENTS = Decimal("0.01")


def _round_amount(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _financial_year_bounds(as_of: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Indian financial year: 1 April - 31 March."""
    if as_of.month >= 4:
        return datetime.date(as_of.year, 4, 1), datetime.date(as_of.year + 1, 3, 31)
    return datetime.date(as_of.year - 1, 4, 1), datetime.date(as_of.year, 3, 31)


def _primary_gstin(vendor) -> Optional[str]:
    """The vendor's GST registration number, if any - VendorDAO.get_vendor_by_id
    already eager-loads vendor_address -> vendor_tax, so no extra query is
    needed here. Prefers the primary address; registration_type is matched
    case-sensitively against both spellings actually present in this data
    ('GST' and 'GSTIN' - see vendor_intake_service.py/vendor_auto_onboarding.py,
    which write 'GSTIN' going forward, and older seeded rows using 'GST')."""
    addresses = sorted(vendor.vendor_address or [], key=lambda a: not a.is_primary)
    for address in addresses:
        for tax in address.vendor_tax or []:
            if tax.registration_type in GST_TAX_REGISTRATION_TYPES and tax.registration_number:
                return tax.registration_number
    return None


def compute_payable_amount(net_amount: Decimal, tds: Optional[InvoiceTds]) -> Decimal:
    """What's actually owed to the vendor: net_amount minus TDS when applicable,
    otherwise net_amount unchanged. Shared by PaymentService (enforces this as the
    payment-allocation ceiling / PAID threshold) and InvoiceDetailsService (surfaces
    it for display) so the figure is computed identically everywhere rather than
    duplicated. Deliberately never mutates net_amount itself - see either caller's
    module docstring for why."""
    if tds is not None and tds.tds_applicable and tds.tds_amount:
        return net_amount - tds.tds_amount
    return net_amount


def _extract_gst_status(gst_response: Optional[dict]) -> Optional[str]:
    """Pull just the registration status out of the raw Sandbox response - unlike
    vendor_auto_onboarding.py's extract_vendor_data_from_gst_response, this does
    NOT require a usable name/address, since TDS only needs the status."""
    if not gst_response:
        return None
    outer = gst_response.get("data") or {}
    if str(outer.get("status_cd")) != "1":
        return None
    data = outer.get("data") or {}
    status = (data.get("sts") or "").strip()
    return status or None


def _entity_type_from_pan(pan_number: Optional[str]) -> Optional[str]:
    """Derives entity_type from the PAN's own 4th character - no API call,
    no new field to collect. Returns None (never guesses) for a missing or
    malformed PAN, or a code PAN_REGEX/PAN_ENTITY_TYPE_CODES wouldn't
    recognize - a bad guess here is worse than leaving it unset."""
    if not pan_number:
        return None
    normalized = pan_number.strip().upper()
    if not PAN_REGEX.match(normalized):
        return None
    return _ENTITY_TYPE_BY_PAN_CODE.get(normalized[3])


def _taxable_base(invoice) -> Decimal:
    """TDS base = invoice value excluding GST/other indirect tax - deliberately
    NOT invoice.net_amount (which includes tax_amount) and NOT a single global
    formula reused blindly; this is the one Phase 1 policy function, easy to
    special-case per rule/scenario later without touching every caller."""
    base = (invoice.gross_amount or Decimal("0")) - (invoice.discount_amount or Decimal("0"))
    return base if base > 0 else Decimal("0")


class TDSDeterminationService:
    def __init__(self, db):
        self.db = db
        self.invoice_dao = InvoiceDAO(db)
        self.vendor_dao = VendorDAO(db)
        self.tds_dao = TdsDAO(db)

    # =========================================================
    # Determine / re-determine
    # =========================================================

    def determine(self, invoice_id: int, user_id, payment_nature_code: Optional[str] = None) -> InvoiceTds:
        try:
            invoice = self.invoice_dao.get_invoice_by_id_locked(invoice_id)
            if invoice is None:
                raise ValueError(f"Invoice {invoice_id} not found")

            vendor = self.vendor_dao.get_vendor_by_id(invoice.vendor_id)
            if vendor is None:
                raise ValueError(f"Vendor {invoice.vendor_id} not found")

            existing = self.tds_dao.get_invoice_tds_by_invoice_id_locked(invoice_id)
            if existing is not None and existing.determination_status == DETERMINATION_STATUS_VERIFIED:
                raise ValueError(
                    f"TDS for invoice {invoice_id} has already been verified and can no longer be recalculated"
                )

            profile = self._get_or_create_profile(vendor)

            reasons: list[str] = []
            payment_nature = self._resolve_payment_nature(invoice, payment_nature_code, reasons)

            result = self._blank_result()
            result["pan_status"] = profile.pan_status
            result["entity_type"] = profile.entity_type

            # GST registration compliance - a warning/signal only, appended to
            # whatever determination_reason the branches below produce. It is
            # never read by _apply_rule_engine and never changes
            # tds_applicable/tds_rate/tds_amount (see module docstring).
            gstin_status, gstin_note = self._check_gst_compliance(vendor)
            result["gstin_status"] = gstin_status
            result["gstin_checked_at"] = datetime.datetime.now(datetime.timezone.utc)

            if payment_nature is None:
                result["determination_reason"] = " ".join(reasons) or "No payment nature could be determined for this invoice."
            else:
                result["payment_nature_id"] = payment_nature.id
                if profile.tds_exemption_flag:
                    reason = "Vendor is marked TDS-exempt"
                    if profile.exemption_reason:
                        reason += f" ({profile.exemption_reason})"
                    result["determination_reason"] = reason + "."
                else:
                    self._apply_rule_engine(invoice, vendor, profile, payment_nature, result)

            if gstin_note:
                result["determination_reason"] = (result["determination_reason"] + " " + gstin_note).strip()

            row = self._save(invoice_id, existing, result, user_id)

            self._record_audit(
                invoice_id, "INVOICE_TDS_DETERMINED", user_id,
                {
                    "tds_applicable": row.tds_applicable,
                    "payment_nature_code": payment_nature.code if payment_nature else None,
                    "tds_rule_id": row.tds_rule_id,
                    "tds_rate": str(row.tds_rate) if row.tds_rate is not None else None,
                    "tds_amount": str(row.tds_amount) if row.tds_amount is not None else None,
                    "gstin_status": row.gstin_status,
                    "determination_reason": row.determination_reason,
                },
            )

            self.db.commit()
            self.db.refresh(row)
            return row
        except Exception:
            self.db.rollback()
            raise

    def update_inputs(self, invoice_id: int, user_id, payment_nature_code: str) -> InvoiceTds:
        """AP Executive correction of the suggested payment nature. Never accepts a
        client-supplied amount/rate directly - it always re-runs determine() so the
        stored numbers are always server-calculated (spec section 6)."""
        if not payment_nature_code or not payment_nature_code.strip():
            raise ValueError("payment_nature_code is required to correct a TDS determination")
        return self.determine(invoice_id, user_id, payment_nature_code=payment_nature_code.strip())

    # =========================================================
    # Verify (Finance)
    # =========================================================

    def verify(self, invoice_id: int, user_id, remarks: Optional[str] = None) -> InvoiceTds:
        try:
            row = self.tds_dao.get_invoice_tds_by_invoice_id_locked(invoice_id)
            if row is None:
                raise ValueError(f"TDS determination for invoice {invoice_id} not found - determine it first")
            if row.determination_status == DETERMINATION_STATUS_VERIFIED:
                raise ValueError(f"TDS for invoice {invoice_id} has already been verified")

            now = datetime.datetime.now(datetime.timezone.utc)
            row.determination_status = DETERMINATION_STATUS_VERIFIED
            row.verified_at = now
            row.verified_by = str(user_id) if user_id is not None else None
            if remarks:
                row.remarks = remarks

            self._record_audit(
                invoice_id, "INVOICE_TDS_VERIFIED", user_id,
                {
                    "tds_applicable": row.tds_applicable,
                    "tds_amount": str(row.tds_amount) if row.tds_amount is not None else None,
                    "remarks": remarks,
                },
            )

            self.db.commit()
            self.db.refresh(row)
            return row
        except Exception:
            self.db.rollback()
            raise

    # =========================================================
    # Read
    # =========================================================

    def get(self, invoice_id: int) -> InvoiceTds:
        row = self.tds_dao.get_invoice_tds_by_invoice_id(invoice_id)
        if row is None:
            raise ValueError(f"TDS determination for invoice {invoice_id} not found - determine it first")
        return row

    # =========================================================
    # Internal helpers
    # =========================================================

    def _get_or_create_profile(self, vendor) -> VendorTdsProfile:
        profile = self.tds_dao.get_vendor_tds_profile(vendor.vendor_id)
        if profile is not None:
            return profile
        # No profile has ever been created for this vendor - default it from the
        # PAN signals that already exist on Vendor.pan_number (presence for
        # pan_status, same heuristic used to backfill the initial
        # vendor_tds_profile rows for this project; the 4th character for
        # entity_type - see _entity_type_from_pan). Only happens at profile
        # CREATION time, never on an existing row, so a value someone has
        # since corrected by hand is never silently overwritten by a guess.
        profile = VendorTdsProfile(
            vendor_id=vendor.vendor_id,
            residency_type="RESIDENT",
            pan_status=PAN_STATUS_VALID if vendor.pan_number else PAN_STATUS_NOT_AVAILABLE,
            entity_type=_entity_type_from_pan(vendor.pan_number),
            lower_deduction_available=False,
            tds_exemption_flag=False,
        )
        self.tds_dao.create_vendor_tds_profile(profile)
        self.db.flush()
        return profile

    def _check_gst_compliance(self, vendor) -> tuple[Optional[str], Optional[str]]:
        """GST registration compliance - a warning/signal only (see this module's
        docstring): returns (gstin_status_to_store, human-readable warning or
        None). NEVER raises and NEVER influences tds_applicable/tds_rate/
        tds_amount - a Sandbox outage or a cancelled GSTIN must not block a
        TDS determination that is otherwise perfectly valid.

        Reuses vendor_auto_onboarding.call_gst_search (already handles
        HTTPError/RequestException/unexpected exceptions and never raises)
        rather than calling gst_service.search_gstin directly."""
        gstin = _primary_gstin(vendor)
        if not gstin:
            return GSTIN_STATUS_NOT_ON_FILE, "No GST registration on file for this vendor - GST compliance not checked."

        result = call_gst_search(gstin)
        if not result.verified:
            return (
                GSTIN_STATUS_CHECK_UNAVAILABLE,
                f"GST compliance check unavailable ({result.error_message or 'Sandbox API error'}).",
            )

        status = _extract_gst_status(result.data)
        if status is None:
            return GSTIN_STATUS_CHECK_UNAVAILABLE, "GST compliance check returned an unusable response."

        if status.strip().lower() != GST_ACTIVE_STATUS:
            return status, f"Vendor's GST registration ({gstin}) is not Active (status: {status}) - please verify vendor compliance before payment."

        return status, None

    def _resolve_payment_nature(
        self, invoice, payment_nature_code: Optional[str], reasons: list[str]
    ) -> Optional[TdsPaymentNature]:
        if payment_nature_code:
            nature = self.tds_dao.get_payment_nature_by_code(payment_nature_code)
            if nature is None or not nature.is_active:
                raise ValueError(f"Payment nature '{payment_nature_code}' is not a known active TDS payment nature")
            return nature

        if invoice.purchase_category_id is None:
            reasons.append("Invoice has no purchase category set, so no payment nature could be suggested.")
            return None

        mapping = self.tds_dao.get_default_mapping_for_category(invoice.purchase_category_id)
        if mapping is None:
            reasons.append(
                f"No default TDS payment-nature mapping is configured for purchase category "
                f"{invoice.purchase_category_id}."
            )
            return None

        return mapping.tds_payment_nature

    def _apply_rule_engine(self, invoice, vendor, profile: VendorTdsProfile, payment_nature: TdsPaymentNature, result: dict) -> None:
        as_of = invoice.invoice_date
        rule = self.tds_dao.get_active_tds_rule_for_payment_nature(payment_nature.code, as_of)
        if rule is None:
            result["determination_reason"] = (
                f"No active TDS rule is configured for payment nature '{payment_nature.code}' as of {as_of}."
            )
            return

        rate_rule = self.tds_dao.get_active_tax_rate_rule_for_tax_rule(rule.tax_rule_id, as_of)
        if rate_rule is None:
            result["tds_rule_id"] = rule.tax_rule_id
            result["determination_reason"] = (
                f"TDS rule '{rule.rule_code}' matched but has no active rate configured as of {as_of}."
            )
            return

        result["tds_rule_id"] = rule.tax_rule_id
        result["tds_rate_rule_id"] = rate_rule.tax_rate_rule_id

        taxable_base = _taxable_base(invoice)
        result["taxable_base"] = taxable_base

        threshold_amount = rule.threshold_amount
        threshold_type = rule.threshold_type

        prior_aggregate = Decimal("0")
        if threshold_type == THRESHOLD_TYPE_AGGREGATE_PERIOD:
            fy_start, fy_end = _financial_year_bounds(as_of)
            prior_aggregate = self.tds_dao.sum_prior_transaction_amount(
                vendor.vendor_id, payment_nature.id, fy_start, fy_end, exclude_invoice_id=invoice.invoice_id
            )
        aggregate_amount = prior_aggregate + taxable_base

        result["threshold_amount"] = threshold_amount
        result["prior_period_aggregate"] = prior_aggregate
        result["current_transaction_amount"] = taxable_base
        result["aggregate_amount"] = aggregate_amount

        compare_amount = aggregate_amount if threshold_type == THRESHOLD_TYPE_AGGREGATE_PERIOD else taxable_base
        below_threshold = threshold_amount is not None and threshold_type is not None and compare_amount < threshold_amount

        legal_ref = rule.legal_reference or rule.rule_code

        if below_threshold:
            qualifier = "Cumulative" if threshold_type == THRESHOLD_TYPE_AGGREGATE_PERIOD else "Transaction"
            result["determination_reason"] = (
                f"{rule.rule_name} ({legal_ref}): {qualifier.lower()} amount {compare_amount} is below the "
                f"{threshold_amount} threshold - TDS not applicable."
            )
            return

        reason_bits = [f"{rule.rule_name} ({legal_ref}) applies."]
        if threshold_amount is not None:
            qualifier = "Cumulative" if threshold_type == THRESHOLD_TYPE_AGGREGATE_PERIOD else "Transaction"
            reason_bits.append(f"{qualifier} amount {compare_amount} meets/exceeds the {threshold_amount} threshold.")

        if rate_rule.calculation_type == "FIXED":
            tds_amount = _round_amount(rate_rule.fixed_amount or Decimal("0"))
            reason_bits.append(f"Fixed deduction of {tds_amount} applies.")
            result["tds_rate"] = None
            result["tds_amount"] = tds_amount
        else:
            effective_rate = rate_rule.rate_percent
            certificate_active = (
                profile.lower_deduction_available
                and profile.certificate_rate is not None
                and profile.certificate_valid_from is not None
                and profile.certificate_valid_to is not None
                and profile.certificate_valid_from <= as_of <= profile.certificate_valid_to
            )
            if certificate_active:
                effective_rate = profile.certificate_rate
                reason_bits.append(
                    f"Lower-deduction certificate {profile.certificate_number or ''} applies: rate reduced to "
                    f"{effective_rate}%."
                )
            elif profile.pan_status != PAN_STATUS_VALID:
                if effective_rate < PAN_MISSING_RATE_FLOOR:
                    effective_rate = PAN_MISSING_RATE_FLOOR
                    reason_bits.append(
                        f"Vendor PAN is not valid/available - higher rate of {effective_rate}% applied (Section 206AA)."
                    )
                else:
                    reason_bits.append(f"Vendor PAN is not valid/available (standard rate already >= {PAN_MISSING_RATE_FLOOR}%).")

            tds_amount = _round_amount(taxable_base * effective_rate / Decimal("100"))
            result["tds_rate"] = effective_rate
            result["tds_amount"] = tds_amount

        result["tds_applicable"] = True
        result["determination_reason"] = " ".join(reason_bits)

    @staticmethod
    def _blank_result() -> dict:
        return {
            "tds_applicable": False,
            "payment_nature_id": None,
            "tds_rule_id": None,
            "tds_rate_rule_id": None,
            "taxable_base": None,
            "tds_rate": None,
            "tds_amount": None,
            "threshold_amount": None,
            "prior_period_aggregate": None,
            "current_transaction_amount": None,
            "aggregate_amount": None,
            "pan_status": None,
            "entity_type": None,
            "gstin_status": None,
            "gstin_checked_at": None,
            "determination_reason": "",
        }

    def _save(self, invoice_id: int, existing: Optional[InvoiceTds], result: dict, user_id) -> InvoiceTds:
        now = datetime.datetime.now(datetime.timezone.utc)
        if existing is None:
            row = InvoiceTds(invoice_id=invoice_id)
            self.tds_dao.create_invoice_tds(row)
        else:
            row = existing

        row.tds_applicable = result["tds_applicable"]
        row.payment_nature_id = result["payment_nature_id"]
        row.tds_rule_id = result["tds_rule_id"]
        row.tds_rate_rule_id = result["tds_rate_rule_id"]
        row.taxable_base = result["taxable_base"]
        row.tds_rate = result["tds_rate"]
        row.tds_amount = result["tds_amount"]
        row.threshold_amount = result["threshold_amount"]
        row.prior_period_aggregate = result["prior_period_aggregate"]
        row.current_transaction_amount = result["current_transaction_amount"]
        row.aggregate_amount = result["aggregate_amount"]
        row.pan_status = result["pan_status"]
        row.entity_type = result["entity_type"]
        row.gstin_status = result["gstin_status"]
        row.gstin_checked_at = result["gstin_checked_at"]
        row.determination_status = DETERMINATION_STATUS_DETERMINED
        row.determination_reason = result["determination_reason"]
        row.determined_at = now
        row.determined_by = str(user_id) if user_id is not None else None
        return row

    def _record_audit(self, invoice_id: int, action: str, user_id, values: dict) -> None:
        # Same shared ap.audit_log table every other invoice-lifecycle event uses
        # (table_name="invoice", record_id=invoice_id) - matches
        # InvoiceApprovalService._record_audit exactly, so TDS determine/verify
        # events show up in the invoice's Activity timeline (InvoiceDAO.
        # get_audit_log_for_record) alongside OCR review/send-for-approval/
        # approve/reject, instead of being invisible there.
        self.invoice_dao.create_audit_log(
            AuditLog(
                table_name="invoice",
                record_id=invoice_id,
                action=action,
                changed_by=str(user_id) if user_id is not None else None,
                new_values={k: v for k, v in values.items() if v is not None} or None,
            )
        )
