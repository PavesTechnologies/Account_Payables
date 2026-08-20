from typing import Any, Dict, List, Optional

from Backend.Data_Access_Layer.dao.invoice_extraction_dao import (
    InvoiceExtractionDAO,
)
from Backend.API_Layer.interface.invoice_extraction_interface import (
    ValidationResult,
    InboundDocumentRequest,
)
from Backend.config.env_loader import get_env_var


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

        issues: List[str] = []

        # --------------------------------------------------------
        # 1. Extraction validation
        # --------------------------------------------------------

        extraction_result = self.validate_extraction(extracted)

        if not extraction_result["is_valid"]:
            issues.extend(extraction_result["issues"])

            self._create_inbound_document(
                extracted=extracted,
                file_path=file_path,
            )

            return ValidationResult(
                is_valid=False,
                requires_manual_review=True,
                issues=issues,
            )

        # --------------------------------------------------------
        # 2. Vendor validation
        # --------------------------------------------------------

        vendor_result = self.validate_vendor(extracted)

        if not vendor_result["is_valid"]:
            issues.extend(vendor_result["issues"])

        # --------------------------------------------------------
        # 3. Buyer validation
        # --------------------------------------------------------

        buyer_result = self.validate_buyer(extracted)

        if not buyer_result["is_valid"]:
            issues.extend(buyer_result["issues"])

        # --------------------------------------------------------
        # 4. Tax validation
        # --------------------------------------------------------

        tax_result = self.validate_tax(
            extracted=extracted,
            vendor_details=vendor_result.get("vendor_details"),
        )

        if not tax_result["is_valid"]:
            issues.extend(tax_result["issues"])

        # --------------------------------------------------------
        # Final validation result
        # --------------------------------------------------------

        if issues:
            return ValidationResult(
                is_valid=False,
                requires_manual_review=True,
                issues=issues,
            )

        return ValidationResult(
            is_valid=True,
            requires_manual_review=False,
            issues=[
                "Extraction, vendor, buyer and tax validation passed"
            ],
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

        return {
            "is_valid": True,
            "issues": [],
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
        }

    # ============================================================
    # 4. Tax validation
    # ============================================================

    def validate_tax(
        self,
        extracted,
        vendor_details: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:

        issues: List[str] = []

        # --------------------------------------------------------
        # Basic tax data
        # --------------------------------------------------------

        tax = extracted.tax
        amounts = extracted.amounts
        invoice_lines = extracted.invoice_lines

        print("Starting tax validation")

        # --------------------------------------------------------
        # 4.1 Validate tax type
        # --------------------------------------------------------

        tax_type_result = self._validate_tax_type(
            extracted=extracted,
            vendor_details=vendor_details,
        )

        if not tax_type_result["is_valid"]:
            issues.extend(
                tax_type_result["issues"]
            )

        # --------------------------------------------------------
        # 4.2 Validate tax rates
        # --------------------------------------------------------

        tax_rate_result = self._validate_tax_rates(
            extracted=extracted,
            vendor_details=vendor_details,
        )

        if not tax_rate_result["is_valid"]:
            issues.extend(
                tax_rate_result["issues"]
            )

        # --------------------------------------------------------
        # 4.3 Validate tax amounts
        # --------------------------------------------------------

        tax_amount_result = self._validate_tax_amounts(
            extracted=extracted,
        )

        if not tax_amount_result["is_valid"]:
            issues.extend(
                tax_amount_result["issues"]
            )

        # --------------------------------------------------------
        # 4.4 Validate invoice tax total
        # --------------------------------------------------------

        tax_total_result = self._validate_tax_total(
            extracted=extracted,
        )

        if not tax_total_result["is_valid"]:
            issues.extend(
                tax_total_result["issues"]
            )

        # --------------------------------------------------------
        # Final tax result
        # --------------------------------------------------------

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
    # 4.1 Tax type validation
    # ============================================================

    def _validate_tax_type(
        self,
        extracted,
        vendor_details: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:

        tax = extracted.tax

        if not tax.tax_type:
            return {
                "is_valid": False,
                "issues": [
                    "Tax type could not be determined"
                ],
            }

        print(
            f"Extracted tax type: {tax.tax_type}"
        )

        # --------------------------------------------------------
        # TODO:
        #
        # Get vendor state
        # Get buyer state
        # Get place of supply
        # Query tax_rule_condition
        # Determine expected tax type
        # Compare expected vs extracted
        # --------------------------------------------------------

        return {
            "is_valid": True,
            "issues": [],
        }

    # ============================================================
    # 4.2 Tax rate validation
    # ============================================================

    def _validate_tax_rates(
        self,
        extracted,
        vendor_details: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:

        issues: List[str] = []

        # --------------------------------------------------------
        # Tax validation should primarily happen per invoice line
        # because your rules are SAC/HSN based.
        # --------------------------------------------------------

        for line in extracted.invoice_lines:

            if not line.hsn_sac:
                issues.append(
                    f"Line {line.line_number}: "
                    "HSN/SAC is missing"
                )
                continue

            print(
                f"Validating tax rate for "
                f"SAC/HSN {line.hsn_sac}"
            )

            # ----------------------------------------------------
            # TODO:
            #
            # Query:
            #   tax_rule
            #   tax_rule_condition
            #   tax_rate_rule
            #
            # Based on:
            #   SAC/HSN
            #   invoice date
            #   supply location
            #   vendor tax status
            #
            # Determine expected rate.
            # ----------------------------------------------------

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
    # 4.3 Tax amount validation
    # ============================================================

    def _validate_tax_amounts(
        self,
        extracted,
    ) -> Dict[str, Any]:

        issues: List[str] = []

        for line in extracted.invoice_lines:

            taxable_amount = line.taxable_amount

            if taxable_amount is None:
                continue

            # ----------------------------------------------------
            # CGST
            # ----------------------------------------------------

            if (
                line.cgst_rate is not None
                and line.cgst_amount is not None
            ):

                expected_cgst = round(
                    taxable_amount
                    * line.cgst_rate
                    / 100,
                    2,
                )

                difference = abs(
                    expected_cgst
                    - line.cgst_amount
                )

                if difference > 1.00:
                    issues.append(
                        f"Line {line.line_number}: "
                        f"CGST amount mismatch. "
                        f"Expected {expected_cgst}, "
                        f"extracted {line.cgst_amount}"
                    )

            # ----------------------------------------------------
            # SGST
            # ----------------------------------------------------

            if (
                line.sgst_rate is not None
                and line.sgst_amount is not None
            ):

                expected_sgst = round(
                    taxable_amount
                    * line.sgst_rate
                    / 100,
                    2,
                )

                difference = abs(
                    expected_sgst
                    - line.sgst_amount
                )

                if difference > 1.00:
                    issues.append(
                        f"Line {line.line_number}: "
                        f"SGST amount mismatch. "
                        f"Expected {expected_sgst}, "
                        f"extracted {line.sgst_amount}"
                    )

            # ----------------------------------------------------
            # IGST
            # ----------------------------------------------------

            if (
                line.igst_rate is not None
                and line.igst_amount is not None
            ):

                expected_igst = round(
                    taxable_amount
                    * line.igst_rate
                    / 100,
                    2,
                )

                difference = abs(
                    expected_igst
                    - line.igst_amount
                )

                if difference > 1.00:
                    issues.append(
                        f"Line {line.line_number}: "
                        f"IGST amount mismatch. "
                        f"Expected {expected_igst}, "
                        f"extracted {line.igst_amount}"
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
    # ============================================================

    def _validate_tax_total(
        self,
        extracted,
    ) -> Dict[str, Any]:

        amounts = extracted.amounts

        cgst = amounts.cgst_amount or 0
        sgst = amounts.sgst_amount or 0
        igst = amounts.igst_amount or 0
        ugst = amounts.ugst_amount or 0
        cess = amounts.cess_amount or 0

        calculated_tax = round(
            cgst
            + sgst
            + igst
            + ugst
            + cess,
            2,
        )

        extracted_total_tax = (
            amounts.total_tax
            if amounts.total_tax is not None
            else 0
        )

        difference = abs(
            calculated_tax
            - extracted_total_tax
        )

        if difference > 1.00:
            return {
                "is_valid": False,
                "issues": [
                    "Total tax amount mismatch. "
                    f"Calculated: {calculated_tax}, "
                    f"extracted: {extracted_total_tax}"
                ],
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