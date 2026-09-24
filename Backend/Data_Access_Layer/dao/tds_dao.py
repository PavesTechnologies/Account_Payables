# Backend/Data_Access_Layer/dao/tds_dao.py
import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func, or_

from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import TaxRateRule, TaxRule, TaxRuleCondition
from Backend.Data_Access_Layer.models.tds import (
    InvoiceTds,
    PurchaseCategoryTdsMapping,
    TdsPaymentNature,
    VendorTdsProfile,
)

TDS_RULE_CATEGORY = "TDS_RATE"
PAYMENT_NATURE_CONDITION_TYPE = "PAYMENT_NATURE"


class TdsDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # TDS payment nature / category mapping (config, read-only here)
    # =====================================================

    def get_payment_nature_by_code(self, code: str) -> Optional[TdsPaymentNature]:
        return (
            self.db.query(TdsPaymentNature)
            .filter(TdsPaymentNature.code == code)
            .first()
        )

    def get_default_mapping_for_category(self, purchase_category_id: int) -> Optional[PurchaseCategoryTdsMapping]:
        return (
            self.db.query(PurchaseCategoryTdsMapping)
            .join(TdsPaymentNature, PurchaseCategoryTdsMapping.tds_payment_nature_id == TdsPaymentNature.id)
            .filter(
                PurchaseCategoryTdsMapping.purchase_category_id == purchase_category_id,
                PurchaseCategoryTdsMapping.is_default.is_(True),
                PurchaseCategoryTdsMapping.is_active.is_(True),
                TdsPaymentNature.is_active.is_(True),
            )
            .order_by(PurchaseCategoryTdsMapping.id.asc())
            .first()
        )

    # =====================================================
    # Vendor TDS profile
    # =====================================================

    def get_vendor_tds_profile(self, vendor_id: int) -> Optional[VendorTdsProfile]:
        return (
            self.db.query(VendorTdsProfile)
            .filter(VendorTdsProfile.vendor_id == vendor_id)
            .first()
        )

    def create_vendor_tds_profile(self, profile: VendorTdsProfile) -> VendorTdsProfile:
        self.db.add(profile)
        self.db.flush()
        return profile

    # =====================================================
    # Tax rule engine (TDS_RATE flavour - mirrors
    # InvoiceExtractionDAO.get_gst_rate_rule_for_sac's GST_RATE flavour:
    # TaxRule -> TaxRuleCondition -> TaxRateRule, effective-dated, priority-ordered)
    # =====================================================

    def get_active_tds_rule_for_payment_nature(self, payment_nature_code: str, as_of_date) -> Optional[TaxRule]:
        return (
            self.db.query(TaxRule)
            .join(TaxRuleCondition, TaxRuleCondition.tax_rule_id == TaxRule.tax_rule_id)
            .filter(
                TaxRule.rule_category == TDS_RULE_CATEGORY,
                TaxRule.is_active.is_(True),
                TaxRule.effective_from <= as_of_date,
                or_(TaxRule.effective_to.is_(None), TaxRule.effective_to >= as_of_date),
                TaxRuleCondition.condition_type == PAYMENT_NATURE_CONDITION_TYPE,
                TaxRuleCondition.operator == "EQUALS",
                TaxRuleCondition.condition_value == payment_nature_code,
            )
            .order_by(TaxRule.priority.asc())
            .first()
        )

    def get_active_tax_rate_rule_for_tax_rule(self, tax_rule_id: int, as_of_date) -> Optional[TaxRateRule]:
        return (
            self.db.query(TaxRateRule)
            .filter(
                TaxRateRule.tax_rule_id == tax_rule_id,
                TaxRateRule.is_active.is_(True),
                TaxRateRule.effective_from <= as_of_date,
                or_(TaxRateRule.effective_to.is_(None), TaxRateRule.effective_to >= as_of_date),
            )
            .order_by(TaxRateRule.effective_from.desc())
            .first()
        )

    # =====================================================
    # invoice_tds
    # =====================================================

    def get_invoice_tds_by_invoice_id(self, invoice_id: int) -> Optional[InvoiceTds]:
        return (
            self.db.query(InvoiceTds)
            .filter(InvoiceTds.invoice_id == invoice_id)
            .first()
        )

    def get_invoice_tds_by_invoice_id_locked(self, invoice_id: int) -> Optional[InvoiceTds]:
        return (
            self.db.query(InvoiceTds)
            .filter(InvoiceTds.invoice_id == invoice_id)
            .with_for_update()
            .first()
        )

    def create_invoice_tds(self, row: InvoiceTds) -> InvoiceTds:
        self.db.add(row)
        self.db.flush()
        return row

    def sum_prior_transaction_amount(
        self,
        vendor_id: int,
        payment_nature_id: int,
        fy_start: datetime.date,
        fy_end: datetime.date,
        exclude_invoice_id: int,
    ) -> Decimal:
        """Sum of current_transaction_amount across every *other* invoice_tds row for
        this vendor + payment nature within the same financial year - the cumulative
        eligible aggregate an AGGREGATE_PERIOD threshold is evaluated against (spec
        section 5 step 8/9). Counts every considered transaction of that nature
        regardless of whether TDS was ultimately deducted on it (a transaction that
        was itself below-threshold still counts toward the running total)."""
        total = (
            self.db.query(func.coalesce(func.sum(InvoiceTds.current_transaction_amount), 0))
            .join(Invoice, Invoice.invoice_id == InvoiceTds.invoice_id)
            .filter(
                Invoice.vendor_id == vendor_id,
                InvoiceTds.payment_nature_id == payment_nature_id,
                InvoiceTds.invoice_id != exclude_invoice_id,
                Invoice.invoice_date >= fy_start,
                Invoice.invoice_date <= fy_end,
            )
            .scalar()
        )
        return Decimal(total or 0)
