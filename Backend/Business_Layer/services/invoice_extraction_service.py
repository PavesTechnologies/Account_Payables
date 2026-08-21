import datetime
import logging
import types
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from Backend.Data_Access_Layer.dao.invoice_extraction_dao import (
    InvoiceExtractionDAO,
)
from Backend.API_Layer.interface.invoice_extraction_interface import (
    ValidationResult,
    ValidationSummary,
    InboundDocumentRequest,
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


class InvoiceExtractionService:

    def __init__(self, db):
        self.invoice_extraction_dao = InvoiceExtractionDAO(db)

    # ============================================================
    # Main validation orchestrator
    # ============================================================

    def validate_invoice(
        self,
        extracted,
        file_path: str,
    ) -> ValidationResult:

        # Stops at the first failing check - extraction, then vendor,
        # then buyer, then tax - rather than running every check
        # regardless of earlier failures. success only ever contains
        # checks that actually ran and passed; a failing check's
        # issues are returned on their own (not merged with anything
        # from checks that never got a chance to run).

        success: List[ValidationSummary] = []

        # --------------------------------------------------------
        # 1. Extraction validation
        # --------------------------------------------------------

        extraction_result = self.validate_extraction(extracted)

        if not extraction_result["is_valid"]:

            self._create_inbound_document(
                extracted=extracted,
                file_path=file_path,
            )

            return ValidationResult(
                is_valid=False,
                requires_manual_review=True,
                issues=extraction_result["issues"],
                success=success,
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

        vendor_result = self.validate_vendor(extracted)

        if not vendor_result["is_valid"]:
            return ValidationResult(
                is_valid=False,
                requires_manual_review=True,
                issues=vendor_result["issues"],
                success=success,
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

        buyer_result = self.validate_buyer(extracted)

        if not buyer_result["is_valid"]:
            return ValidationResult(
                is_valid=False,
                requires_manual_review=True,
                issues=buyer_result["issues"],
                success=success,
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

        tax_result = self.validate_tax(
            extracted=extracted,
            vendor_details=vendor_result.get("vendor_details"),
        )

        if not tax_result["is_valid"]:
            return ValidationResult(
                is_valid=False,
                requires_manual_review=True,
                issues=tax_result["issues"],
                success=success,
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

        return ValidationResult(
            is_valid=True,
            requires_manual_review=False,
            issues=[],
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

        vendor_gstin = extracted.vendor.gstin
        vendor_name = extracted.vendor.name

        print(f"Vendor GSTIN: {vendor_gstin}")
        print(f"Vendor name: {vendor_name}")

        if not vendor_gstin and not vendor_name:
            return {
                "is_valid": False,
                "issues": [
                    "Vendor GSTIN and vendor name are missing"
                ],
                "vendor_details": None,
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
            }

        print(
            f"Vendor details: {vendor_details}"
        )

        return {
            "is_valid": True,
            "issues": [],
            "vendor_details": vendor_details,
            "summary": (
                "Vendor found in vendor master: "
                f"'{vendor_details.get('vendor_name')}' "
                f"(vendor_id={vendor_details.get('vendor_id')})."
            ),
        }

    # ============================================================
    # 3. Buyer validation
    # ============================================================

    def validate_buyer(self, extracted) -> Dict[str, Any]:

        expected_buyer = get_env_var("BUYER_NAME")
        buyer_name = extracted.buyer.name

        print(
            f"Expected buyer: {expected_buyer}"
        )

        print(
            f"Extracted buyer: {buyer_name}"
        )

        if not buyer_name:
            return {
                "is_valid": False,
                "issues": [
                    "Buyer name not found in invoice"
                ],
            }

        if buyer_name.strip().lower() != expected_buyer.strip().lower():
            return {
                "is_valid": False,
                "issues": [
                    "Buyer name does not match expected buyer"
                ],
            }

        return {
            "is_valid": True,
            "issues": [],
            "summary": (
                f"Buyer '{buyer_name}' matched the configured "
                "BUYER_NAME."
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
    # Inbound document / audit
    # ============================================================

    def _create_inbound_document(
        self,
        extracted,
        file_path: str,
    ):

        request = InboundDocumentRequest(
            source_type="UPLOAD",
            file_name=(
                extracted.document.original_filename
            ),
            file_path=file_path,
            extraction_status=(
                extracted.validation.status
            ),
            extraction_confidence=(
                extracted.extraction.confidence
            ),
            raw_extracted_data=(
                extracted.model_dump(mode="json")
            ),
        )

        return (
            self.invoice_extraction_dao
            .create_inbound_document(request)
        )