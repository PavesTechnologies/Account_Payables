# Backend/Data_Access_Layer/dao/tds_config_dao.py
"""Data access for the TDS Configuration screens (rules, payment natures,
deductors). TDS rules live in the generic tax engine tables (ap.tax_rule /
tax_rule_condition / tax_rate_rule, rule_category='TDS_RATE') - this DAO only
ever reads/writes TDS_RATE rows, never GST_RATE/TAX_COMPONENT ones.

DAOs add/flush only; TdsConfigService owns commit/rollback.
"""
import datetime
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.dao.tds_dao import PAYMENT_NATURE_CONDITION_TYPE, TDS_RULE_CATEGORY
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import TaxRule, TaxRuleCondition, TaxType
from Backend.Data_Access_Layer.models.tds import (
    InvoiceTds,
    PurchaseCategoryTdsMapping,
    TdsDeductor,
    TdsPaymentNature,
)

TDS_TAX_CODE = "TDS"


class TdsConfigDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Shared
    # =====================================================

    def get_tds_tax_type(self) -> Optional[TaxType]:
        return (
            self.db.query(TaxType)
            .filter(TaxType.tax_code == TDS_TAX_CODE, TaxType.is_withholding.is_(True))
            .order_by(TaxType.tax_type_id.asc())
            .first()
        )

    def add(self, obj):
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self.db.flush()

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log

    # =====================================================
    # Payment nature
    # =====================================================

    def list_payment_natures(self, search: Optional[str] = None, is_active: Optional[bool] = None) -> List[TdsPaymentNature]:
        query = self.db.query(TdsPaymentNature)
        if is_active is not None:
            query = query.filter(TdsPaymentNature.is_active.is_(is_active))
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(or_(TdsPaymentNature.code.ilike(pattern), TdsPaymentNature.name.ilike(pattern)))
        return query.order_by(TdsPaymentNature.code.asc()).all()

    def get_payment_nature(self, nature_id: int, lock: bool = False) -> Optional[TdsPaymentNature]:
        query = self.db.query(TdsPaymentNature).filter(TdsPaymentNature.id == nature_id)
        if lock:
            query = query.with_for_update()
        return query.first()

    def get_payment_nature_by_code(self, code: str) -> Optional[TdsPaymentNature]:
        return self.db.query(TdsPaymentNature).filter(func.upper(TdsPaymentNature.code) == code.upper()).first()

    def get_payment_nature_by_name(self, name: str) -> Optional[TdsPaymentNature]:
        return self.db.query(TdsPaymentNature).filter(func.lower(TdsPaymentNature.name) == name.lower()).first()

    def count_payment_nature_references(self, nature: TdsPaymentNature) -> dict:
        return {
            "invoice_tds": self.db.query(func.count(InvoiceTds.id)).filter(InvoiceTds.payment_nature_id == nature.id).scalar() or 0,
            "purchase_category_mappings": (
                self.db.query(func.count(PurchaseCategoryTdsMapping.id))
                .filter(PurchaseCategoryTdsMapping.tds_payment_nature_id == nature.id)
                .scalar() or 0
            ),
            "tds_rules": (
                self.db.query(func.count(TaxRuleCondition.tax_rule_condition_id))
                .join(TaxRule, TaxRule.tax_rule_id == TaxRuleCondition.tax_rule_id)
                .filter(
                    TaxRule.rule_category == TDS_RULE_CATEGORY,
                    TaxRuleCondition.condition_type == PAYMENT_NATURE_CONDITION_TYPE,
                    TaxRuleCondition.condition_value == nature.code,
                )
                .scalar() or 0
            ),
        }

    # =====================================================
    # Deductor
    # =====================================================

    def list_deductors(self, search: Optional[str] = None, is_active: Optional[bool] = None) -> List[TdsDeductor]:
        query = self.db.query(TdsDeductor)
        if is_active is not None:
            query = query.filter(TdsDeductor.is_active.is_(is_active))
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(or_(TdsDeductor.code.ilike(pattern), TdsDeductor.name.ilike(pattern)))
        return query.order_by(TdsDeductor.code.asc()).all()

    def get_deductor(self, deductor_id: int, lock: bool = False) -> Optional[TdsDeductor]:
        query = self.db.query(TdsDeductor).filter(TdsDeductor.id == deductor_id)
        if lock:
            query = query.with_for_update()
        return query.first()

    def get_deductor_by_code(self, code: str) -> Optional[TdsDeductor]:
        return self.db.query(TdsDeductor).filter(func.upper(TdsDeductor.code) == code.upper()).first()

    def get_deductor_by_name(self, name: str) -> Optional[TdsDeductor]:
        return self.db.query(TdsDeductor).filter(func.lower(TdsDeductor.name) == name.lower()).first()

    def count_deductor_references(self, deductor: TdsDeductor) -> dict:
        return {
            "tds_rules": self.db.query(func.count(TaxRule.tax_rule_id)).filter(TaxRule.tds_deductor_id == deductor.id).scalar() or 0,
        }

    # =====================================================
    # TDS rules (tax_rule, rule_category='TDS_RATE')
    # =====================================================

    def _rule_query(self):
        return (
            self.db.query(TaxRule)
            .options(
                selectinload(TaxRule.conditions),
                selectinload(TaxRule.rate_rules),
                selectinload(TaxRule.tds_deductor),
            )
            .filter(TaxRule.rule_category == TDS_RULE_CATEGORY)
        )

    def list_rules(
        self,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        payment_nature_code: Optional[str] = None,
        effective_date: Optional[datetime.date] = None,
        deductor_id: Optional[int] = None,
    ) -> List[TaxRule]:
        query = self._rule_query()
        if is_active is not None:
            query = query.filter(TaxRule.is_active.is_(is_active))
        if deductor_id is not None:
            query = query.filter(TaxRule.tds_deductor_id == deductor_id)
        if effective_date is not None:
            query = query.filter(
                TaxRule.effective_from <= effective_date,
                or_(TaxRule.effective_to.is_(None), TaxRule.effective_to >= effective_date),
            )
        if payment_nature_code:
            nature_rule_ids = select(TaxRuleCondition.tax_rule_id).where(
                TaxRuleCondition.condition_type == PAYMENT_NATURE_CONDITION_TYPE,
                func.upper(TaxRuleCondition.condition_value) == payment_nature_code.strip().upper(),
            )
            query = query.filter(TaxRule.tax_rule_id.in_(nature_rule_ids))
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    TaxRule.rule_code.ilike(pattern),
                    TaxRule.rule_name.ilike(pattern),
                    TaxRule.old_section.ilike(pattern),
                    TaxRule.new_section.ilike(pattern),
                    TaxRule.legal_reference.ilike(pattern),
                )
            )
        return query.order_by(TaxRule.old_section.asc().nulls_last(), TaxRule.rule_code.asc()).all()

    def get_rule(self, tax_rule_id: int, lock: bool = False) -> Optional[TaxRule]:
        query = self._rule_query().filter(TaxRule.tax_rule_id == tax_rule_id)
        if lock:
            # FOR UPDATE can't be combined with the selectinload secondary
            # SELECTs' outer joins - lock the parent row only.
            query = query.with_for_update(of=TaxRule)
        return query.first()

    def get_rule_by_code(self, rule_code: str) -> Optional[TaxRule]:
        """Across ALL rule categories - tax_rule.rule_code is globally unique,
        so a TDS code must not collide with a GST rule's code either."""
        return (
            self.db.query(TaxRule)
            .options(selectinload(TaxRule.conditions), selectinload(TaxRule.rate_rules), selectinload(TaxRule.tds_deductor))
            .filter(func.upper(TaxRule.rule_code) == rule_code.strip().upper())
            .first()
        )

    def list_rules_for_section_and_nature(self, old_section: str, payment_nature_code: str) -> List[TaxRule]:
        """Sibling variants used for the duplicate/conflicting-variant check."""
        nature_rule_ids = select(TaxRuleCondition.tax_rule_id).where(
            TaxRuleCondition.condition_type == PAYMENT_NATURE_CONDITION_TYPE,
            TaxRuleCondition.condition_value == payment_nature_code,
        )
        return (
            self._rule_query()
            .filter(
                func.upper(TaxRule.old_section) == old_section.upper(),
                TaxRule.tax_rule_id.in_(nature_rule_ids),
            )
            .all()
        )

    def count_rule_references(self, rule: TaxRule) -> int:
        rate_ids = [rr.tax_rate_rule_id for rr in rule.rate_rules or []]
        condition = InvoiceTds.tds_rule_id == rule.tax_rule_id
        if rate_ids:
            condition = or_(condition, InvoiceTds.tds_rate_rule_id.in_(rate_ids))
        return self.db.query(func.count(InvoiceTds.id)).filter(condition).scalar() or 0

    def is_rate_rule_referenced(self, tax_rate_rule_id: int) -> bool:
        return (
            self.db.query(InvoiceTds.id)
            .filter(InvoiceTds.tds_rate_rule_id == tax_rate_rule_id)
            .first()
            is not None
        )

    def delete_condition(self, condition: TaxRuleCondition) -> None:
        self.db.delete(condition)
