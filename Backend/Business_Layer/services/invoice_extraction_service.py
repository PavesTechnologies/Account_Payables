import datetime
import logging
import time
import types
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from Backend.Data_Access_Layer.dao.inbound_document_dao import (
    InboundDocumentDAO,
)
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.dao.invoice_extraction_dao import (
    InvoiceExtractionDAO,
)
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.inbound_document import (
    InboundDocument,
)
from Backend.Data_Access_Layer.models.invoice import (
    Invoice,
    InvoiceAttachment,
    InvoiceLine,
)
from Backend.Data_Access_Layer.utils.database import SessionLocal
from Backend.API_Layer.interface.invoice_extraction_interface import (
    CustomInvoiceRequest,
    FieldComparison,
    FieldComparisonStatus,
    InboundDocumentRequest,
    InvoiceAttachmentRequest,
    InvoiceLineRequest,
    InvoiceRequest,
    InvoiceType,
    ValidationResult,
    ValidationSummary,
)
from Backend.API_Layer.utils.validation_progress import (
    complete_validation_job,
    fail_validation_job,
    skip_remaining_stages,
    update_validation_stage,
)
from Backend.Business_Layer.utils import invoice_status
from Backend.Business_Layer.utils.exceptions import (
    DuplicateInvoiceError,
    FieldExtractionError,
)
from Backend.config.env_loader import get_env_var

logger = logging.getLogger(__name__)


# ============================================================
# Tax validation configuration
#
# Configurable via environment rather than hardcoded, per the
# existing project convention (see get_env_var usage elsewhere
# in this service). Defaults match the tolerance already used
# by the pre-existing amount/total checks (1.00).
# ============================================================

TAX_AMOUNT_TOLERANCE = Decimal(
    get_env_var("TAX_AMOUNT_TOLERANCE", "1.00")
)

TAX_RATE_TOLERANCE = Decimal(
    get_env_var("TAX_RATE_TOLERANCE", "0.01")
)

TAX_COUNTRY_CODE = get_env_var("TAX_COUNTRY_CODE", "IN")

# The buyer is always our own company, not something that varies per
# invoice like the vendor does - so unlike vendor.state_code (which
# only ever comes from the vendor's own GSTIN on that invoice), the
# buyer's GST state code can be configured once and used as a
# fallback whenever OCR/Textract didn't extract the buyer's own
# GSTIN (buyer GSTIN is frequently faint/absent on vendor-issued
# invoices). BUYER_STATE is kept only for readability in messages -
# BUYER_CODE (the 2-digit GST state code) is what actually drives
# the same-state/different-state comparison.
BUYER_STATE_NAME = get_env_var("BUYER_STATE", "")
BUYER_STATE_CODE = get_env_var("BUYER_CODE", "")

# Buyer GSTIN/PAN/address are optional - unlike BUYER_NAME, there is
# no fallback lookup for them (no buyer master table exists; the
# buyer is always "our own company", configured once). Left unset,
# the corresponding field simply isn't compared (NOT_COMPARED rather
# than a false MISMATCH).
BUYER_GSTIN = get_env_var("BUYER_GSTIN", "")
BUYER_PAN = get_env_var("BUYER_PAN", "")
BUYER_ADDRESS = get_env_var("BUYER_ADDRESS", "")

# ============================================================
# Vendor/Buyer field-comparison configuration
# ============================================================

# Vendor statuses that block an invoice outright, regardless of how
# well the extracted fields otherwise match the vendor master record.
VENDOR_BLOCKING_STATUSES = {"BLOCKED", "INACTIVE"}

# Extracted addresses are a single free-text OCR string; master data
# is several discrete columns (address_line1/2, city, postal_code) or
# a single configured BUYER_ADDRESS string - byte-equality is never
# realistic, so address comparison uses normalized token-overlap
# containment instead. This is the minimum fraction of the shorter
# string's significant tokens that must also appear in the longer
# string for the pair to count as a MATCH.
ADDRESS_FUZZY_MIN_OVERLAP_RATIO = float(
    get_env_var("ADDRESS_FUZZY_MIN_OVERLAP_RATIO", "0.6")
)

_ADDRESS_STOPWORDS = {
    "the", "and", "of", "at", "no", "near", "opp", "opposite", "road",
    "street", "st", "india",
}

# Any of these present on a line means the invoice carries real
# line-level tax data, so line-level validation should run. When
# none of them are present on ANY line (common for SaaS/cloud
# billing invoices, e.g. AWS, which only ever state tax once at the
# header), tax rate/amount validation falls back to a single
# invoice-level check using the header's own extracted tax.*_rate /
# amounts.*_amount instead of silently skipping every line.
LINE_TAX_PRESENCE_FIELDS = (
    "cgst_rate",
    "sgst_rate",
    "igst_rate",
    "ugst_rate",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
    "ugst_amount",
    "cess_amount",
)

# ap.tax_rule_condition/ap.tax_type currently only has GST rows for
# CGST/SGST/IGST - there is no configured rule for UGST or CESS, so
# those two are intentionally excluded here. They're still included
# in the pure-arithmetic total-tax reconciliation (validate_tax_total)
# since that doesn't need a DB rule, only the extracted figures.
LINE_TAX_COMPONENT_FIELDS = {
    "CGST": ("cgst_rate", "cgst_amount"),
    "SGST": ("sgst_rate", "sgst_amount"),
    "IGST": ("igst_rate", "igst_amount"),
}

TOTAL_TAX_COMPONENT_FIELDS = (
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
    "ugst_amount",
    "cess_amount",
)


def _to_decimal(value: Any) -> Optional[Decimal]:

    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _quantize_money(value: Decimal) -> Decimal:

    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _format_rate(rate: Decimal) -> str:
    """Decimal(9.0000) -> "9", Decimal(9.5000) -> "9.5" - trims the
    Numeric(7,4) column's trailing zeros for user-facing messages."""

    text = format(rate, "f")

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text


def _normalize_text(value: Optional[str]) -> str:
    return " ".join(str(value).strip().casefold().split())


def _address_tokens(value: str) -> set:
    return {
        token
        for token in _normalize_text(value).replace(",", " ").split()
        if len(token) > 2 and token not in _ADDRESS_STOPWORDS
    }


def _addresses_match(extracted_value: str, master_value: str) -> bool:

    extracted_tokens = _address_tokens(extracted_value)
    master_tokens = _address_tokens(master_value)

    if not extracted_tokens or not master_tokens:
        return False

    shorter, longer = sorted(
        [extracted_tokens, master_tokens], key=len
    )

    overlap = len(shorter & longer) / len(shorter)

    return overlap >= ADDRESS_FUZZY_MIN_OVERLAP_RATIO


def _compare_field(
    field_name: str,
    extracted_value: Optional[str],
    master_value: Optional[str],
    *,
    fuzzy: bool = False,
) -> FieldComparison:
    """Compares one extracted vendor/buyer field against its master/
    expected counterpart. GSTIN/PAN/state_code compare as exact
    (case/whitespace-insensitive); names compare as exact after
    normalization; address compares via fuzzy token-overlap
    (fuzzy=True)."""

    has_extracted = extracted_value not in (None, "")
    has_master = master_value not in (None, "")

    if not has_extracted and not has_master:
        status = FieldComparisonStatus.NOT_COMPARED
    elif not has_extracted:
        status = FieldComparisonStatus.MISSING_EXTRACTED
    elif not has_master:
        status = FieldComparisonStatus.MISSING_MASTER
    elif fuzzy:
        status = (
            FieldComparisonStatus.MATCH
            if _addresses_match(extracted_value, master_value)
            else FieldComparisonStatus.MISMATCH
        )
    elif _normalize_text(extracted_value) == _normalize_text(master_value):
        status = FieldComparisonStatus.MATCH
    else:
        status = FieldComparisonStatus.MISMATCH

    return FieldComparison(
        field=field_name,
        extracted_value=extracted_value,
        master_value=master_value,
        status=status,
    )


class InvoiceExtractionService:

    def __init__(self, db):
        self.db = db
        self.invoice_extraction_dao = InvoiceExtractionDAO(db)

    # ============================================================
    # Main validation orchestrator
    # ============================================================

    def validate_invoice(
        self,
        extracted,
        file_path: str,
        job_id: Optional[str] = None,
    ) -> ValidationResult:

        # Stops at the first failing check - extraction, then vendor,
        # then buyer, then tax - rather than running every check
        # regardless of earlier failures. success only ever contains
        # checks that actually ran and passed; a failing check's
        # issues are returned on their own (not merged with anything
        # from checks that never got a chance to run).
        #
        # When job_id is given, each stage's RUNNING/SUCCESS/FAILED
        # transition (plus timing) is mirrored into Redis for the
        # frontend's progress polling (see validation_progress.py).
        # This is purely a UI-progress side effect: every Redis call
        # is best-effort and never raises, so passing job_id=None
        # (the default, used by direct/synchronous callers and
        # existing tests) reproduces the exact prior behavior.

        success: List[ValidationSummary] = []

        # --------------------------------------------------------
        # 1. Extraction validation
        # --------------------------------------------------------

        extraction_result = self._execute_stage(
            job_id,
            "extraction",
            "Validating extraction...",
            lambda: self.validate_extraction(extracted),
        )

        if not extraction_result["is_valid"]:

            if job_id:
                skip_remaining_stages(job_id, "extraction")

            # No InboundDocument/Invoice persistence here anymore -
            # validate-fields is a pure validation check now. Every
            # outcome (pass, fail, or needs review) is persisted by
            # the separate POST /create-invoice call the frontend
            # makes once it has this result, regardless of whether
            # validation passed or requires manual review.

            return self._finalize(
                job_id,
                False,
                True,
                extraction_result["issues"],
                success,
            )

        success.append(
            ValidationSummary(
                validation_type="EXTRACTION",
                source=extraction_result["summary"],
            )
        )

        # --------------------------------------------------------
        # 2. Vendor validation
        # --------------------------------------------------------

        vendor_result = self._execute_stage(
            job_id,
            "vendor",
            "Validating vendor...",
            lambda: self.validate_vendor(extracted),
        )

        if not vendor_result["is_valid"]:

            if job_id:
                skip_remaining_stages(job_id, "vendor")

            return self._finalize(
                job_id,
                False,
                True,
                vendor_result["issues"],
                success,
            )

        success.append(
            ValidationSummary(
                validation_type="VENDOR",
                source=vendor_result["summary"],
            )
        )

        # --------------------------------------------------------
        # 3. Buyer validation
        # --------------------------------------------------------

        buyer_result = self._execute_stage(
            job_id,
            "buyer",
            "Validating buyer...",
            lambda: self.validate_buyer(extracted),
        )

        if not buyer_result["is_valid"]:

            if job_id:
                skip_remaining_stages(job_id, "buyer")

            return self._finalize(
                job_id,
                False,
                True,
                buyer_result["issues"],
                success,
            )

        success.append(
            ValidationSummary(
                validation_type="BUYER",
                source=buyer_result["summary"],
            )
        )

        # --------------------------------------------------------
        # 4. Tax validation
        # --------------------------------------------------------

        tax_result = self._execute_stage(
            job_id,
            "gst",
            "Validating GST tax...",
            lambda: self.validate_tax(
                extracted=extracted,
                vendor_details=vendor_result.get("vendor_details"),
            ),
        )

        if not tax_result["is_valid"]:
            return self._finalize(
                job_id,
                False,
                True,
                tax_result["issues"],
                success,
            )

        success.append(
            ValidationSummary(
                validation_type="TAX",
                source=tax_result["summary"],
            )
        )

        # --------------------------------------------------------
        # Final validation result - every check ran and passed.
        # --------------------------------------------------------

        return self._finalize(job_id, True, False, [], success)

    def _execute_stage(
        self,
        job_id: Optional[str],
        stage: str,
        running_message: str,
        check_fn,
    ) -> Dict[str, Any]:

        if job_id:
            update_validation_stage(
                job_id,
                stage,
                "RUNNING",
                message=running_message,
            )

        start_time = time.perf_counter()

        result = check_fn()

        duration_ms = round((time.perf_counter() - start_time) * 1000)

        field_comparisons = [
            comparison.model_dump(mode="json")
            for comparison in result.get("field_comparisons", [])
        ]

        if job_id:
            if result["is_valid"]:
                update_validation_stage(
                    job_id,
                    stage,
                    "SUCCESS",
                    message=result.get("summary"),
                    issues=result.get("issues") or [],
                    duration_ms=duration_ms,
                    field_comparisons=field_comparisons,
                )
            else:
                update_validation_stage(
                    job_id,
                    stage,
                    "FAILED",
                    message=None,
                    issues=result["issues"],
                    duration_ms=duration_ms,
                    field_comparisons=field_comparisons,
                )

        return result

    def _finalize(
        self,
        job_id: Optional[str],
        is_valid: bool,
        requires_manual_review: bool,
        issues: List[str],
        success: List[ValidationSummary],
    ) -> ValidationResult:

        if job_id:
            complete_validation_job(
                job_id,
                is_valid,
                requires_manual_review,
                issues,
                success=[entry.model_dump() for entry in success],
            )

        return ValidationResult(
            is_valid=is_valid,
            requires_manual_review=requires_manual_review,
            issues=issues,
            success=success,
        )

    # ============================================================
    # 1. Extraction validation
    # ============================================================

    def validate_extraction(self, extracted) -> Dict[str, Any]:

        validation = extracted.validation

        print(
            "Extraction validation status:",
            validation.status,
        )

        print(
            "Extraction is valid:",
            validation.is_valid,
        )

        if not validation.is_valid:
            return {
                "is_valid": False,
                "issues": validation.issues or [
                    "Invoice extraction validation failed"
                ],
            }

        confidence = extracted.extraction.confidence
        confidence_text = (
            f"{confidence:.1f}%"
            if confidence is not None
            else "unknown"
        )

        return {
            "is_valid": True,
            "issues": [],
            "summary": (
                f"Extraction status '{validation.status}' is valid "
                f"(confidence {confidence_text})."
            ),
        }

    # ============================================================
    # 2. Vendor validation
    # ============================================================

    def validate_vendor(self, extracted) -> Dict[str, Any]:

        vendor = extracted.vendor
        vendor_gstin = vendor.gstin
        vendor_name = vendor.name

        if not vendor_gstin and not vendor_name:
            return {
                "is_valid": False,
                "issues": [
                    "Vendor GSTIN and vendor name are missing"
                ],
                "vendor_details": None,
                "field_comparisons": [],
            }

        vendor_details = (
            self.invoice_extraction_dao
            .get_vendor_details_by_gstin(
                vendor_gstin,
                vendor_name,
            )
        )

        if vendor_details is None:
            return {
                "is_valid": False,
                "issues": [
                    "Vendor details not found"
                ],
                "vendor_details": None,
                "field_comparisons": [],
            }

        master_address = " ".join(
            part
            for part in (
                vendor_details.get("address_line1"),
                vendor_details.get("address_line2"),
                vendor_details.get("city"),
                vendor_details.get("postal_code"),
            )
            if part
        ) or None

        # Legal Name/Trade Name have no dedicated columns on the
        # vendor master (only a single vendor_name) - both extracted
        # variants are compared against that one master field so a
        # mismatch on either is still surfaced, not silently dropped.
        field_comparisons = [
            _compare_field("name", vendor.name, vendor_details.get("vendor_name")),
            _compare_field("legal_name", vendor.legal_name, vendor_details.get("vendor_name")),
            _compare_field("trade_name", vendor.trade_name, vendor_details.get("vendor_name")),
            _compare_field("gstin", vendor.gstin, vendor_details.get("registration_number")),
            _compare_field("pan", vendor.pan, vendor_details.get("pan_number")),
            _compare_field("address", vendor.address, master_address, fuzzy=True),
            _compare_field("state", vendor.state, vendor_details.get("state")),
        ]

        # GSTIN/PAN mismatches and a blocked/inactive vendor status
        # are hard-blocking. Name/legal_name/trade_name/address/state
        # mismatches are surfaced (field_comparisons + issues) but do
        # not by themselves fail the stage - the master record only
        # has one name field to compare three extracted variants
        # against, and OCR'd addresses are approximate by nature.
        blocking_fields = {"gstin", "pan"}
        blocking_mismatches = [
            comparison
            for comparison in field_comparisons
            if comparison.status == FieldComparisonStatus.MISMATCH
            and comparison.field in blocking_fields
        ]

        status_name = (vendor_details.get("status_name") or "").upper()
        status_blocked = status_name in VENDOR_BLOCKING_STATUSES

        issues = [
            f"Vendor {comparison.field} mismatch: extracted "
            f"'{comparison.extracted_value}' vs vendor master "
            f"'{comparison.master_value}'"
            for comparison in field_comparisons
            if comparison.status == FieldComparisonStatus.MISMATCH
        ]

        if status_blocked:
            issues.append(
                f"Vendor status is '{status_name}' - invoice cannot proceed."
            )

        is_valid = not blocking_mismatches and not status_blocked

        return {
            "is_valid": is_valid,
            "issues": issues,
            "vendor_details": vendor_details,
            "field_comparisons": field_comparisons,
            "summary": (
                "Vendor found in vendor master: "
                f"'{vendor_details.get('vendor_name')}' "
                f"(vendor_id={vendor_details.get('vendor_id')}, "
                f"status={status_name or 'UNKNOWN'})."
            ) if is_valid else None,
        }

    # ============================================================
    # 3. Buyer validation
    # ============================================================

    def validate_buyer(self, extracted) -> Dict[str, Any]:

        buyer = extracted.buyer
        expected_buyer = get_env_var("BUYER_NAME")

        if not buyer.name:
            return {
                "is_valid": False,
                "issues": [
                    "Buyer name not found in invoice"
                ],
                "field_comparisons": [],
            }

        # Buyer has no master DB table (it's always "our own company")
        # - the expected profile is env-configured. Only name is
        # required/hard-blocking, matching prior behavior exactly;
        # GSTIN/PAN/address/state are compared when configured but
        # never block the stage, since an unconfigured expected value
        # isn't a real mismatch.
        field_comparisons = [
            _compare_field("name", buyer.name, expected_buyer),
            _compare_field("gstin", buyer.gstin, BUYER_GSTIN or None),
            _compare_field("pan", buyer.pan, BUYER_PAN or None),
            _compare_field("address", buyer.address, BUYER_ADDRESS or None, fuzzy=True),
            _compare_field("state", buyer.state, BUYER_STATE_NAME or None),
        ]

        name_comparison = field_comparisons[0]
        name_mismatch = name_comparison.status == FieldComparisonStatus.MISMATCH

        issues = [
            f"Buyer {comparison.field} mismatch: extracted "
            f"'{comparison.extracted_value}' vs expected "
            f"'{comparison.master_value}'"
            for comparison in field_comparisons
            if comparison.status == FieldComparisonStatus.MISMATCH
        ]

        if name_mismatch:
            return {
                "is_valid": False,
                "issues": issues,
                "field_comparisons": field_comparisons,
            }

        return {
            "is_valid": True,
            "issues": issues,
            "field_comparisons": field_comparisons,
            "summary": (
                f"Buyer '{buyer.name}' matched the configured BUYER_NAME."
            ),
        }

    # ============================================================
    # 4. Tax validation
    #
    # DB-driven: expected rates/types come from ap.tax_rule +
    # ap.tax_rule_condition + ap.tax_rate_rule (via the DAO), never
    # hardcoded. Resolution happens once per invoice line (see
    # _build_tax_context) and is then reused by all four
    # sub-validators below so each SAC only needs one DB round trip.
    # ============================================================

    def validate_tax(
        self,
        extracted,
        vendor_details: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:

        issues: List[str] = []

        logger.info("Starting tax validation")

        tax_context = self._build_tax_context(extracted)

        tax_type_result = self.validate_tax_type(
            extracted=extracted,
            tax_context=tax_context,
        )
        if not tax_type_result["is_valid"]:
            issues.extend(tax_type_result["issues"])

        tax_rate_result = self.validate_tax_rates(
            tax_context=tax_context,
        )
        if not tax_rate_result["is_valid"]:
            issues.extend(tax_rate_result["issues"])

        tax_amount_result = self.validate_tax_amounts(
            tax_context=tax_context,
        )
        if not tax_amount_result["is_valid"]:
            issues.extend(tax_amount_result["issues"])

        tax_total_result = self.validate_tax_total(
            extracted=extracted,
            tax_context=tax_context,
        )
        if not tax_total_result["is_valid"]:
            issues.extend(tax_total_result["issues"])

        if issues:
            return {
                "is_valid": False,
                "issues": issues,
            }

        return {
            "is_valid": True,
            "issues": [],
            "summary": self._build_tax_summary(extracted, tax_context),
        }

    def _build_tax_summary(
        self,
        extracted,
        tax_context: Dict[str, Any],
    ) -> str:

        actual_tax_type = extracted.tax.tax_type

        expected_components = tax_context["expected_components"]

        rate_text = (
            ", ".join(
                f"{tax_code} {_format_rate(rate)}%"
                for tax_code, rate in expected_components.items()
                if rate is not None
            )
            if expected_components
            else "no GST components expected"
        )

        level_text = (
            "line-level"
            if tax_context["has_line_tax_data"]
            else "header-level"
        )

        return (
            f"Tax type ({actual_tax_type}) and rate ({rate_text}) "
            f"matched the DB-calculated expected values, checked at "
            f"{level_text}."
        )

    # ============================================================
    # Tax context resolution
    #
    # Resolves, once per invoice:
    #   - same_state: whether vendor/buyer are in the same GST
    #     state, from their GSTIN-derived state codes (preferred
    #     over OCR state names, which the extraction pipeline
    #     already normalizes into vendor/buyer.state_code). Buyer
    #     falls back to the configured BUYER_CODE env var since the
    #     buyer is always our own company - unlike the vendor, it
    #     isn't something that varies per invoice.
    #   - expected_tax_type + the CGST/SGST/IGST component rates
    #     that apply for that supply location (ap.tax_rule,
    #     rule_category="TAX_COMPONENT"). This does NOT depend on
    #     SAC/HSN at all - it only depends on supply location - so
    #     tax type/rate/amount validation can run even when no
    #     SAC/HSN can be resolved anywhere.
    #   - per line (or once at header level - see below): the SAC's
    #     configured combined GST rate (rule_category="GST_RATE"),
    #     used only for an internal consistency check against the
    #     component rate sum. This IS SAC-dependent, but is a
    #     secondary sanity check, not a precondition for the core
    #     type/rate/amount validation.
    #
    # HSN/SAC + actual-value resolution follows this cascade:
    #   1. line.hsn_sac / the line's own rate+amount fields
    #   2. extracted.tax.hsn_sac (header-level classification)
    #   3. the invoice's own header-level tax.*_rate /
    #      amounts.*_amount, used directly as the "actual" values
    #      to validate against the DB-calculated expected ones
    #   4. only if supply location itself can't be resolved (no
    #      vendor/buyer state code at all, even after the buyer env
    #      fallback) is there truly nothing to validate against -
    #      that's the only case that blocks with a context issue.
    #
    # A per-invoice line missing its own HSN/SAC no longer blocks
    # validation by itself: the location-based component rates are
    # SAC-independent, so type/rate/amount checks still run using
    # whatever actual values (line or header) are available. HSN/SAC
    # is only used for the secondary SAC-rate-bracket sanity check.
    #
    # vendor_details is accepted for forward compatibility (e.g. a
    # future vendor tax-status condition_type) but unused today -
    # ap.vendor_tax.registration_type only has "GST" values and no
    # tax_rule_condition currently branches on vendor tax status.
    # ============================================================

    def _build_tax_context(self, extracted) -> Dict[str, Any]:

        invoice_date = (
            extracted.document.invoice_date
            or datetime.date.today()
        )

        country_id = (
            self.invoice_extraction_dao
            .get_country_id_by_code(TAX_COUNTRY_CODE)
        )

        if country_id is None:
            return {
                "expected_tax_type": None,
                "expected_components": {},
                "context_issues": [
                    "Tax country configuration "
                    f"('{TAX_COUNTRY_CODE}') not found - "
                    "cannot resolve tax rules."
                ],
                "has_line_tax_data": False,
                "lines": [],
            }

        vendor_state_code = extracted.vendor.state_code

        buyer_state_code = (
            extracted.buyer.state_code
            or BUYER_STATE_CODE
            or None
        )

        same_state: Optional[bool] = None
        if vendor_state_code and buyer_state_code:
            same_state = vendor_state_code == buyer_state_code

        context_issues: List[str] = []
        expected_tax_type: Optional[str] = None
        expected_components: Dict[str, Decimal] = {}

        if same_state is None:
            # This is the only case where classification is truly
            # unavailable - there is no supply location to derive
            # anything from, from any source.
            context_issues.append(
                "Cannot determine supply location for tax "
                "validation: vendor and/or buyer GSTIN state code "
                "is missing (buyer fallback: "
                f"BUYER_CODE='{BUYER_STATE_CODE or None}')."
            )
        else:
            component_rules = (
                self.invoice_extraction_dao
                .get_tax_component_rules(
                    country_id=country_id,
                    same_state=same_state,
                    as_of_date=invoice_date,
                )
            )

            expected_components = {
                row["tax_code"]: _to_decimal(row["rate_percent"])
                for row in component_rules
            }

            if not component_rules:
                context_issues.append(
                    "No configured tax component rule found for "
                    f"{'same-state' if same_state else 'different-state'} "
                    "supply - tax configuration requires review."
                )
            else:
                expected_tax_type = (
                    "INTRA_STATE_CGST_SGST"
                    if same_state
                    else "INTER_STATE_IGST"
                )

        header_hsn_sac = extracted.tax.hsn_sac

        has_line_tax_data = any(
            getattr(line, field, None) is not None
            for line in extracted.invoice_lines
            for field in LINE_TAX_PRESENCE_FIELDS
        )

        if has_line_tax_data:
            source_lines = [
                (line.line_number, line, line.hsn_sac)
                for line in extracted.invoice_lines
            ]
        else:
            # Tier 3: no line carries any tax rate/amount at all
            # (common for SaaS/cloud billing invoices that only
            # state tax once, at the header) - fall back to a
            # single invoice-level check using the header's own
            # extracted tax type/rates/amounts as the actual values.
            header_line = types.SimpleNamespace(
                cgst_rate=extracted.tax.cgst_rate,
                sgst_rate=extracted.tax.sgst_rate,
                igst_rate=extracted.tax.igst_rate,
                ugst_rate=extracted.tax.ugst_rate,
                cgst_amount=extracted.amounts.cgst_amount,
                sgst_amount=extracted.amounts.sgst_amount,
                igst_amount=extracted.amounts.igst_amount,
                ugst_amount=extracted.amounts.ugst_amount,
                cess_amount=extracted.amounts.cess_amount,
                taxable_amount=(
                    extracted.amounts.taxable_amount
                    if extracted.amounts.taxable_amount is not None
                    else extracted.amounts.subtotal
                ),
            )
            source_lines = [("HEADER", header_line, header_hsn_sac)]

        lines: List[Dict[str, Any]] = []

        for line_number, line, hsn_sac in source_lines:

            # Cascade tier 1 -> 2: this line's own HSN/SAC, else the
            # invoice-level (header) HSN/SAC.
            resolved_hsn_sac = hsn_sac or header_hsn_sac

            line_context: Dict[str, Any] = {
                "line": line,
                "line_number": line_number,
                "hsn_sac": resolved_hsn_sac,
                "taxable_amount": _to_decimal(
                    getattr(line, "taxable_amount", None)
                ),
                "expected_total_rate": None,
                "gst_rule_code": None,
                "issues": [],
            }

            if resolved_hsn_sac:

                gst_rate_rule = (
                    self.invoice_extraction_dao
                    .get_gst_rate_rule_for_sac(
                        sac=resolved_hsn_sac,
                        country_id=country_id,
                        as_of_date=invoice_date,
                    )
                )

                if gst_rate_rule and expected_components:

                    expected_total_rate = _to_decimal(
                        gst_rate_rule["rate_percent"]
                    )
                    line_context["expected_total_rate"] = (
                        expected_total_rate
                    )
                    line_context["gst_rule_code"] = (
                        gst_rate_rule["rule_code"]
                    )

                    component_rate_sum = sum(
                        (
                            rate
                            for rate in expected_components.values()
                            if rate is not None
                        ),
                        Decimal("0"),
                    )

                    if (
                        expected_total_rate is not None
                        and component_rate_sum != expected_total_rate
                    ):
                        line_context["issues"].append(
                            f"Line {line_number}: configured GST "
                            f"rate for SAC '{resolved_hsn_sac}' "
                            f"({expected_total_rate}%) does not "
                            "match the configured tax component "
                            f"rates ({component_rate_sum}%) - tax "
                            "configuration requires review."
                        )

            # Tier 4 note: NOT resolving a SAC/HSN here does not by
            # itself block validation - expected_components (the
            # location-based rates) is still used below to validate
            # this line's/header's own rate and amount fields. The
            # only true "unavailable -> review" case is context_issues
            # above (no supply location at all).

            lines.append(line_context)

        return {
            "expected_tax_type": expected_tax_type,
            "expected_components": expected_components,
            "context_issues": context_issues,
            "has_line_tax_data": has_line_tax_data,
            "lines": lines,
        }

    # ============================================================
    # 4.1 Tax type validation
    # ============================================================

    def validate_tax_type(
        self,
        extracted,
        tax_context: Dict[str, Any],
    ) -> Dict[str, Any]:

        issues: List[str] = list(tax_context["context_issues"])

        actual_tax_type = extracted.tax.tax_type
        expected_tax_type = tax_context["expected_tax_type"]

        if not actual_tax_type:
            issues.append("Tax type could not be determined")

        elif (
            expected_tax_type
            and actual_tax_type != expected_tax_type
        ):
            issues.append(
                "Tax type mismatch. Expected "
                f"{expected_tax_type}, extracted {actual_tax_type}."
            )

        if issues:
            return {
                "is_valid": False,
                "issues": issues,
            }

        return {
            "is_valid": True,
            "issues": [],
        }

    # ============================================================
    # 4.2 Tax rate validation (per invoice line)
    # ============================================================

    def validate_tax_rates(
        self,
        tax_context: Dict[str, Any],
    ) -> Dict[str, Any]:

        issues: List[str] = []

        for line_context in tax_context["lines"]:

            # Missing HSN/SAC or an unresolved tax rule - already
            # captured in _build_tax_context; surface it here since
            # rate comparison is meaningless without it.
            issues.extend(line_context["issues"])

            expected_components = tax_context["expected_components"]

            if not expected_components:
                continue

            line = line_context["line"]

            for tax_code, expected_rate in expected_components.items():

                fields = LINE_TAX_COMPONENT_FIELDS.get(tax_code)

                if not fields or expected_rate is None:
                    continue

                rate_field, _ = fields

                actual_rate = _to_decimal(
                    getattr(line, rate_field, None)
                )

                if actual_rate is None:
                    continue

                if abs(actual_rate - expected_rate) > TAX_RATE_TOLERANCE:
                    issues.append(
                        f"Line {line_context['line_number']}: "
                        f"{tax_code} rate mismatch. Expected "
                        f"{expected_rate}%, extracted {actual_rate}%."
                    )

        if issues:
            return {
                "is_valid": False,
                "issues": issues,
            }

        return {
            "is_valid": True,
            "issues": [],
        }

    # ============================================================
    # 4.3 Tax amount validation (per invoice line)
    # ============================================================

    def validate_tax_amounts(
        self,
        tax_context: Dict[str, Any],
    ) -> Dict[str, Any]:

        issues: List[str] = []

        expected_components = tax_context["expected_components"]

        if not expected_components:
            return {
                "is_valid": True,
                "issues": [],
            }

        for line_context in tax_context["lines"]:

            taxable_amount = line_context["taxable_amount"]

            if taxable_amount is None:
                continue

            line = line_context["line"]

            for tax_code, expected_rate in expected_components.items():

                fields = LINE_TAX_COMPONENT_FIELDS.get(tax_code)

                if not fields or expected_rate is None:
                    continue

                _, amount_field = fields

                actual_amount = _to_decimal(
                    getattr(line, amount_field, None)
                )

                if actual_amount is None:
                    continue

                expected_amount = _quantize_money(
                    taxable_amount * expected_rate / Decimal("100")
                )

                if (
                    abs(actual_amount - expected_amount)
                    > TAX_AMOUNT_TOLERANCE
                ):
                    issues.append(
                        f"Line {line_context['line_number']}: "
                        f"{tax_code} amount mismatch. Expected "
                        f"{expected_amount}, extracted {actual_amount}."
                    )

        if issues:
            return {
                "is_valid": False,
                "issues": issues,
            }

        return {
            "is_valid": True,
            "issues": [],
        }

    # ============================================================
    # 4.4 Total tax validation
    #
    # Two independent reconciliations, both pure arithmetic on the
    # already-extracted figures (no DB rule needed for either):
    #   1. header component amounts (CGST+SGST+IGST+UGST+CESS) vs
    #      header total_tax.
    #   2. sum of line-level tax amounts vs header total_tax, when
    #      the extracted invoice actually carries line-level tax
    #      data (older/simpler extractions may not).
    # ============================================================

    def validate_tax_total(
        self,
        extracted,
        tax_context: Dict[str, Any],
    ) -> Dict[str, Any]:

        issues: List[str] = []

        amounts = extracted.amounts

        header_component_sum = sum(
            (
                _to_decimal(getattr(amounts, field)) or Decimal("0")
                for field in TOTAL_TAX_COMPONENT_FIELDS
            ),
            Decimal("0"),
        )

        extracted_total_tax = (
            _to_decimal(amounts.total_tax) or Decimal("0")
        )

        if (
            abs(header_component_sum - extracted_total_tax)
            > TAX_AMOUNT_TOLERANCE
        ):
            issues.append(
                "Total tax amount mismatch. Expected "
                f"{header_component_sum}, extracted "
                f"{extracted_total_tax}."
            )

        # Only reconcile sum-of-lines vs header total_tax when the
        # invoice actually carries line-level tax data - in
        # header-only mode (see _build_tax_context) tax_context has
        # a single synthetic line built FROM the header amounts, so
        # comparing it back against the header would be circular.
        if tax_context["has_line_tax_data"]:

            line_component_sum = Decimal("0")

            for line_context in tax_context["lines"]:

                line = line_context["line"]

                for field in TOTAL_TAX_COMPONENT_FIELDS:

                    value = _to_decimal(getattr(line, field, None))

                    if value is not None:
                        line_component_sum += value

            if (
                abs(line_component_sum - extracted_total_tax)
                > TAX_AMOUNT_TOLERANCE
            ):
                issues.append(
                    "Tax total mismatch. Sum of line-level tax "
                    f"amounts ({line_component_sum}) does not "
                    "match the invoice total tax "
                    f"({extracted_total_tax})."
                )

        if issues:
            return {
                "is_valid": False,
                "issues": issues,
            }

        return {
            "is_valid": True,
            "issues": [],
        }

    # ============================================================
    # Create invoice
    #
    # Persists an Invoice + InvoiceLine(s) + InvoiceAttachment +
    # InboundDocument from the same ExtractedInvoiceResult shape
    # /validate-fields takes - this is deliberately a separate call
    # (not a side effect of validation) so a document is persisted
    # exactly once, on demand, at whatever point the frontend's
    # upload -> extraction -> validation -> create-invoice flow
    # calls it - regardless of whether validation passed or flagged
    # issues. Always lands at OCR_REVIEW_PENDING; a human moves it
    # to PENDING_APPROVAL from Invoice Management afterward (that
    # transition is out of scope here - see apply_ocr_review in
    # invoice_process_service.py for the equivalent on the other
    # ingestion pipeline).
    # ============================================================

    def create_invoice(
        self,
        extracted,
        file_path: str,
        created_by: str,
    ) -> Dict[str, Any]:

        custom_request = build_custom_invoice_request(
            extracted, file_path
        )

        invoice_dao = InvoiceDAO(self.db)
        inbound_document_dao = InboundDocumentDAO(self.db)
        master_dao = MasterDAO(self.db)

        vendor_details = (
            self.invoice_extraction_dao
            .get_vendor_details_by_gstin(
                extracted.vendor.gstin,
                extracted.vendor.name,
            )
        )

        if vendor_details is None or not vendor_details.get(
            "vendor_id"
        ):
            raise FieldExtractionError(
                "Vendor could not be matched for GSTIN "
                f"'{extracted.vendor.gstin}' / name "
                f"'{extracted.vendor.name}' - invoice cannot be "
                "created without a known vendor."
            )

        vendor_id = vendor_details["vendor_id"]

        existing = invoice_dao.get_invoice_by_vendor_and_number(
            vendor_id, custom_request.invoice.invoice_number
        )

        if existing is not None:
            raise DuplicateInvoiceError(
                f"Invoice '{custom_request.invoice.invoice_number}' "
                f"already exists for vendor {vendor_id} "
                f"(invoice_id={existing.invoice_id})."
            )

        review_status = invoice_dao.get_status_by_code(
            invoice_status.STATUS_CODE_OCR_REVIEW_PENDING
        )

        if review_status is None:
            raise FieldExtractionError(
                "Status "
                f"'{invoice_status.STATUS_CODE_OCR_REVIEW_PENDING}' "
                "is not configured in status_master."
            )

        currency_id, currency_issue = self._resolve_currency_id(
            custom_request.invoice.currency, master_dao
        )

        payment_term_id = None

        if custom_request.invoice.payment_terms:
            term = master_dao.get_payment_term_by_name(
                custom_request.invoice.payment_terms.strip()
            )
            payment_term_id = (
                term.payment_term_id if term else None
            )

        try:
            inbound_document = InboundDocument(
                source_type=custom_request.inbound_document.source_type,
                file_name=custom_request.inbound_document.file_name,
                file_path=custom_request.inbound_document.file_path,
                extraction_status=(
                    custom_request.inbound_document.extraction_status
                ),
                extraction_confidence=(
                    custom_request.inbound_document
                    .extraction_confidence
                ),
                raw_extracted_data=(
                    custom_request.inbound_document.raw_extracted_data
                ),
                vendor_id=vendor_id,
            )
            inbound_document_dao.create_inbound_document(
                inbound_document
            )

            invoice = Invoice(
                invoice_number=custom_request.invoice.invoice_number,
                vendor_id=vendor_id,
                invoice_type=custom_request.invoice.invoice_type.value,
                invoice_date=custom_request.invoice.invoice_date,
                due_date=(
                    custom_request.invoice.due_date
                    or custom_request.invoice.invoice_date
                ),
                currency_id=currency_id,
                gross_amount=custom_request.invoice.grand_amount,
                discount_amount=(
                    custom_request.invoice.discount_amount
                ),
                tax_amount=custom_request.invoice.tax_amount,
                net_amount=custom_request.invoice.net_amount,
                amount_paid=custom_request.invoice.amount_paid,
                inbound_document_id=(
                    inbound_document.inbound_document_id
                ),
                payment_term_id=payment_term_id,
                status_id=review_status.status_id,
                created_by=created_by,
                updated_by=created_by,
            )
            invoice_dao.create_invoice(invoice)

            line_models, skipped_line_count = (
                self._build_invoice_line_models(
                    custom_request.invoice_lines
                )
            )

            for line_model in line_models:
                line_model.invoice_id = invoice.invoice_id

            if line_models:
                invoice_dao.create_invoice_lines(line_models)

            attachment = None

            if custom_request.invoice_attachment:
                attachment = InvoiceAttachment(
                    invoice_id=invoice.invoice_id,
                    file_name=(
                        custom_request.invoice_attachment.file_name
                    ),
                    file_path=(
                        custom_request.invoice_attachment.file_path
                    ),
                )
                invoice_dao.create_invoice_attachment(attachment)

            inbound_document.invoice_id = invoice.invoice_id

            self.db.commit()
            self.db.refresh(invoice)

            return {
                "invoice_id": invoice.invoice_id,
                "invoice_number": invoice.invoice_number,
                "vendor_id": vendor_id,
                "inbound_document_id": (
                    inbound_document.inbound_document_id
                ),
                "invoice_attachment_id": (
                    attachment.invoice_attachment_id
                    if attachment
                    else None
                ),
                "status_code": (
                    invoice_status.STATUS_CODE_OCR_REVIEW_PENDING
                ),
                "line_count": len(line_models),
                "skipped_line_count": skipped_line_count,
                "warnings": (
                    [currency_issue] if currency_issue else []
                ),
            }

        except Exception:
            self.db.rollback()
            raise

    def _resolve_currency_id(
        self,
        currency_code: Optional[str],
        master_dao: "MasterDAO",
    ) -> "tuple[int, Optional[str]]":
        """Maps a currency code to currency_id, falling back to
        DEFAULT_CURRENCY_CODE (currency_id is NOT NULL on invoice).
        Mirrors invoice_process_service._resolve_currency_id, kept
        as its own copy rather than a cross-import since the two
        ingestion pipelines are otherwise independent."""

        if currency_code:
            currency = master_dao.get_currency_by_code(currency_code)
            if currency is not None:
                return currency.currency_id, None

        fallback = master_dao.get_currency_by_code(
            invoice_status.DEFAULT_CURRENCY_CODE
        )

        if fallback is None:
            raise FieldExtractionError(
                "Default currency "
                f"'{invoice_status.DEFAULT_CURRENCY_CODE}' is not "
                "configured in the currency master."
            )

        reason = (
            f"Currency '{currency_code}' could not be mapped to a "
            "known currency; defaulted to "
            f"{invoice_status.DEFAULT_CURRENCY_CODE}."
            if currency_code
            else
            "No currency was extracted; defaulted to "
            f"{invoice_status.DEFAULT_CURRENCY_CODE}."
        )

        return fallback.currency_id, reason

    def _build_invoice_line_models(
        self,
        line_requests: List["InvoiceLineRequest"],
    ) -> "tuple[List[InvoiceLine], int]":
        """ap.invoice_line has no hsn_sac/unit/taxable_amount columns
        (confirmed against the live schema) - those fields stay on
        InvoiceLineRequest for the caller's own reference/audit but
        cannot be persisted without a schema change, so they're
        intentionally dropped here rather than silently truncated
        into an unrelated column."""

        models: List[InvoiceLine] = []
        skipped = 0

        for line in line_requests:

            has_data = (
                line.description
                or line.line_amount is not None
                or line.unit_price is not None
            )

            if not has_data:
                skipped += 1
                continue

            quantity = (
                line.quantity
                if line.quantity is not None
                else Decimal("1")
            )
            unit_price = (
                line.unit_price
                if line.unit_price is not None
                else Decimal("0")
            )
            line_amount = (
                line.line_amount
                if line.line_amount is not None
                else (quantity * unit_price)
            )

            models.append(
                InvoiceLine(
                    line_number=line.line_number,
                    description=line.description or "",
                    quantity=quantity,
                    unit_price=unit_price,
                    line_amount=line_amount,
                    tax_amount=line.tax_amount,
                    tax_type_id=line.tax_type_id,
                )
            )

        return models, skipped


# ============================================================
# ExtractedInvoiceResponse -> CustomInvoiceRequest mapping
#
# Pure/no DB access - reuses the same InvoiceRequest/
# InvoiceLineRequest/InboundDocumentRequest/InvoiceAttachmentRequest
# contracts a manual "add invoice" caller would use directly, so
# InvoiceExtractionService.create_invoice's persistence logic below
# doesn't care whether the data came from Textract or a manual form.
# ============================================================

def build_custom_invoice_request(
    extracted,
    file_path: str,
) -> CustomInvoiceRequest:

    document = extracted.document
    amounts = extracted.amounts

    grand_amount = (
        amounts.grand_total
        if amounts.grand_total is not None
        else amounts.subtotal
    )

    if grand_amount is None:
        raise FieldExtractionError(
            "No usable amount (grand_total/subtotal) could be "
            "extracted; invoice cannot be created."
        )

    tax_amount = amounts.total_tax

    if tax_amount is None:
        tax_amount = sum(
            (
                value
                for value in (
                    amounts.cgst_amount,
                    amounts.sgst_amount,
                    amounts.igst_amount,
                    amounts.ugst_amount,
                    amounts.cess_amount,
                )
                if value is not None
            ),
            0.0,
        )

    net_amount = grand_amount

    if not document.invoice_number:
        raise FieldExtractionError(
            "invoice_number could not be extracted; invoice cannot "
            "be created."
        )

    if not document.invoice_date:
        raise FieldExtractionError(
            "invoice_date could not be extracted; invoice cannot "
            "be created."
        )

    invoice_request = InvoiceRequest(
        invoice_number=document.invoice_number,
        invoice_type=(
            InvoiceType.PO
            if extracted.reference.po_number
            else InvoiceType.NON_PO
        ),
        invoice_date=document.invoice_date,
        due_date=document.due_date,
        payment_terms=extracted.payment.payment_terms,
        currency=document.currency,
        grand_amount=Decimal(str(grand_amount)),
        discount_amount=(
            Decimal(str(amounts.discount))
            if amounts.discount is not None
            else Decimal("0")
        ),
        tax_amount=Decimal(str(tax_amount)),
        net_amount=Decimal(str(net_amount)),
        amount_paid=(
            Decimal(str(amounts.amount_paid))
            if amounts.amount_paid is not None
            else Decimal("0")
        ),
    )

    line_requests = [
        InvoiceLineRequest(
            line_number=line.line_number,
            description=line.description,
            hsn_sac=line.hsn_sac,
            quantity=(
                Decimal(str(line.quantity))
                if line.quantity is not None
                else None
            ),
            unit=line.unit,
            unit_price=(
                Decimal(str(line.unit_price))
                if line.unit_price is not None
                else None
            ),
            line_amount=(
                Decimal(str(line.line_total))
                if line.line_total is not None
                else None
            ),
            taxable_amount=(
                Decimal(str(line.taxable_amount))
                if line.taxable_amount is not None
                else None
            ),
            tax_amount=Decimal(
                str(
                    line.total_tax
                    if line.total_tax is not None
                    else sum(
                        (
                            value
                            for value in (
                                line.cgst_amount,
                                line.sgst_amount,
                                line.igst_amount,
                                line.ugst_amount,
                                line.cess_amount,
                            )
                            if value is not None
                        ),
                        0.0,
                    )
                )
            ),
        )
        for line in extracted.invoice_lines
    ]

    original_filename = (
        document.original_filename
        or file_path.rsplit("/", 1)[-1]
    )

    inbound_document_request = InboundDocumentRequest(
        source_type="UPLOAD",
        file_name=original_filename,
        file_path=file_path,
        extraction_status="EXTRACTED",
        extraction_confidence=(
            Decimal(str(round(extracted.extraction.confidence, 2)))
            if extracted.extraction.confidence is not None
            else None
        ),
        raw_extracted_data=extracted.model_dump(mode="json"),
    )

    invoice_attachment_request = InvoiceAttachmentRequest(
        file_name=original_filename,
        file_path=file_path,
    )

    return CustomInvoiceRequest(
        invoice=invoice_request,
        invoice_lines=line_requests,
        inbound_document=inbound_document_request,
        invoice_attachment=invoice_attachment_request,
    )


# ============================================================
# Background job entry point
#
# Runs as a FastAPI BackgroundTask (see invoice_extraction_route.py)
# - i.e. in a worker thread, AFTER the POST /validate-fields response
# has already been sent. It cannot reuse the request-scoped DB
# session (DBSessionMiddleware tears that down once the response is
# on its way out), so it opens and closes its own session here.
#
# Any unexpected/system error (DB unreachable, etc.) - as opposed to
# a normal validation failure - marks the job FAILED via
# fail_validation_job so the frontend's poll loop doesn't hang
# forever waiting for a job that silently died.
# ============================================================

def run_validation_job(
    job_id: str,
    extracted,
    file_path: str,
) -> None:

    db = SessionLocal()

    try:
        service = InvoiceExtractionService(db)
        service.validate_invoice(
            extracted,
            file_path,
            job_id=job_id,
        )

    except Exception:
        logger.exception(
            "Unexpected error while running validation job '%s'",
            job_id,
        )
        fail_validation_job(
            job_id,
            "Unexpected error during validation. Please retry.",
        )

    finally:
        try:
            db.close()
        except Exception:
            logger.exception(
                "Failed to close DB session for validation job '%s'",
                job_id,
            )