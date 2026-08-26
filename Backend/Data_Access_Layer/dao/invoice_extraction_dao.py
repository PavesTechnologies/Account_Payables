from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from Backend.Data_Access_Layer.models.vendor import (
    Vendor,
    VendorAddress,
    VendorTax,
)
from Backend.Data_Access_Layer.models.master import (
    Country,
    StatusMaster,
    TaxRateRule,
    TaxRule,
    TaxRuleCondition,
    TaxType,
)
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
class InvoiceExtractionDAO:

    def __init__(self, db: Session):
        self.db = db

    def get_vendor_details_by_gstin(self, gstin: str, name: str):
        stmt = (
            select(
                Vendor.vendor_id,
                Vendor.vendor_name,
                StatusMaster.status_name,
                VendorAddress.state,
                VendorAddress.vendor_address_id,
                VendorTax.vendor_tax_id,
                VendorTax.registration_number,
            )
            .join(
                VendorAddress,
                VendorAddress.vendor_id == Vendor.vendor_id,
            )
            .join(
                StatusMaster,
                Vendor.status_id == StatusMaster.status_id,
            )
            .join(
                VendorTax,
                VendorTax.vendor_address_id == VendorAddress.vendor_address_id,
            )
            .where(
                VendorTax.registration_number == gstin
            )
        )

        result = self.db.execute(stmt).mappings().first()

        if result:
            return dict(result)

        # Fallback: search vendor by name
        result2 = (
            select(
                Vendor.vendor_id,
                Vendor.vendor_name,
                StatusMaster.status_name,
            )
            .join(
                StatusMaster,
                Vendor.status_id == StatusMaster.status_id,
            )
            .where(
                Vendor.vendor_name == name
            )
        )

        result = self.db.execute(result2).mappings().first()

        if not result:
            return None

        return dict(result)
    def create_inbound_document(self, request):
        inbound_document = InboundDocument(
            source_type=request.source_type,
            file_name=request.file_name,
            file_path=request.file_path,
            extraction_status=request.extraction_status,
            raw_extracted_data=request.raw_extracted_data,
        )

        self.db.add(inbound_document)
        self.db.flush()
        self.db.commit()

        return inbound_document

    # ============================================================
    # Tax rule resolution
    #
    # ap.tax_rule rows come in two flavours (see rule_category):
    #
    # - "GST_RATE": one per SAC/HSN, conditioned on
    #   (condition_type="SAC", operator="EQUALS", condition_value=<sac>).
    #   Its tax_rate_rule gives the *combined* GST rate for that SAC
    #   (e.g. 18%).
    #
    # - "TAX_COMPONENT": one per tax component (CGST/SGST/IGST),
    #   conditioned on (condition_type="SUPPLY_LOCATION",
    #   operator="SAME_STATE"/"DIFFERENT_STATE", condition_value="TRUE").
    #   Its own tax_rule_id -> tax_type gives the component's tax_code
    #   (CGST/SGST/IGST) and its tax_rate_rule gives that component's
    #   rate.
    #
    # Both rule/rate rows carry independent effective_from/effective_to
    # windows, so both are filtered by the invoice date.
    # ============================================================

    def get_country_id_by_code(
        self,
        country_code: str,
    ) -> Optional[int]:

        stmt = select(Country.country_id).where(
            Country.country_code == country_code
        )

        return self.db.execute(stmt).scalars().first()

    def get_gst_rate_rule_for_sac(
        self,
        sac: str,
        country_id: int,
        as_of_date,
    ) -> Optional[Dict[str, Any]]:

        stmt = (
            select(
                TaxRule.tax_rule_id,
                TaxRule.rule_code,
                TaxRateRule.rate_percent,
            )
            .join(
                TaxRuleCondition,
                TaxRuleCondition.tax_rule_id == TaxRule.tax_rule_id,
            )
            .join(
                TaxRateRule,
                TaxRateRule.tax_rule_id == TaxRule.tax_rule_id,
            )
            .join(
                TaxType,
                TaxType.tax_type_id == TaxRule.tax_type_id,
            )
            .where(
                TaxType.country_id == country_id,
                TaxRule.rule_category == "GST_RATE",
                TaxRule.is_active.is_(True),
                TaxRule.effective_from <= as_of_date,
                or_(
                    TaxRule.effective_to.is_(None),
                    TaxRule.effective_to >= as_of_date,
                ),
                TaxRateRule.is_active.is_(True),
                TaxRateRule.effective_from <= as_of_date,
                or_(
                    TaxRateRule.effective_to.is_(None),
                    TaxRateRule.effective_to >= as_of_date,
                ),
                TaxRuleCondition.condition_type == "SAC",
                TaxRuleCondition.operator == "EQUALS",
                TaxRuleCondition.condition_value == sac,
            )
            .order_by(TaxRule.priority.asc())
        )

        return self.db.execute(stmt).mappings().first()

    def get_tax_component_rules(
        self,
        country_id: int,
        same_state: bool,
        as_of_date,
    ) -> List[Dict[str, Any]]:

        location_operator = (
            "SAME_STATE" if same_state else "DIFFERENT_STATE"
        )

        stmt = (
            select(
                TaxRule.tax_rule_id,
                TaxRule.rule_code,
                TaxType.tax_code,
                TaxRateRule.rate_percent,
            )
            .join(
                TaxRuleCondition,
                TaxRuleCondition.tax_rule_id == TaxRule.tax_rule_id,
            )
            .join(
                TaxRateRule,
                TaxRateRule.tax_rule_id == TaxRule.tax_rule_id,
            )
            .join(
                TaxType,
                TaxType.tax_type_id == TaxRule.tax_type_id,
            )
            .where(
                TaxType.country_id == country_id,
                TaxRule.rule_category == "TAX_COMPONENT",
                TaxRule.is_active.is_(True),
                TaxRule.effective_from <= as_of_date,
                or_(
                    TaxRule.effective_to.is_(None),
                    TaxRule.effective_to >= as_of_date,
                ),
                TaxRateRule.is_active.is_(True),
                TaxRateRule.effective_from <= as_of_date,
                or_(
                    TaxRateRule.effective_to.is_(None),
                    TaxRateRule.effective_to >= as_of_date,
                ),
                TaxRuleCondition.condition_type == "SUPPLY_LOCATION",
                TaxRuleCondition.operator == location_operator,
                TaxRuleCondition.condition_value == "TRUE",
            )
            .order_by(TaxRule.priority.asc())
        )

        return [dict(row) for row in self.db.execute(stmt).mappings().all()]