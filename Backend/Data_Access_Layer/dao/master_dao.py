# Backend/Data_Access_Layer/dao/master_dao.py

from typing import List, Optional

from Backend.Data_Access_Layer.models.master import (
    Country,
    PaymentTerm,
    Currency,
    SystemConfiguration,
    TaxType,
)
from Backend.Data_Access_Layer.models.purchase import Department, PurchaseCategory

class MasterDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Country (read-only lookup, for FK validation)
    # =====================================================

    def country_exists(self, country_id: int) -> bool:
        return (
            self.db.query(Country)
            .filter(Country.country_id == country_id)
            .first()
            is not None
        )
    def get_currency_by_code(self, currency_code: str) -> Optional[Currency]:
        return (
            self.db.query(Currency)
            .filter(Currency.currency_code == currency_code)
            .first()
        )

    # =====================================================
    # Tax Type
    # =====================================================

    def create_tax_type(self, tax_type: TaxType) -> TaxType:
        self.db.add(tax_type)
        self.db.flush()
        return tax_type

    def get_all_tax_types(
        self,
        country_id: Optional[int] = None,
    ) -> List[TaxType]:

        query = self.db.query(TaxType)

        if country_id is not None:
            query = query.filter(TaxType.country_id == country_id)

        return query.order_by(TaxType.tax_name.asc()).all()

    def get_tax_type_by_id(self, tax_type_id: int) -> Optional[TaxType]:
        return (
            self.db.query(TaxType)
            .filter(TaxType.tax_type_id == tax_type_id)
            .first()
        )

    def get_tax_type_by_code(
        self,
        country_id: int,
        tax_code: str,
        effective_from,
    ) -> Optional[TaxType]:

        return (
            self.db.query(TaxType)
            .filter(
                TaxType.country_id == country_id,
                TaxType.tax_code == tax_code,
                TaxType.effective_from == effective_from,
            )
            .first()
        )

    def delete_tax_type(self, tax_type: TaxType) -> None:
        self.db.delete(tax_type)

    # =====================================================
    # Payment Term
    # =====================================================

    def create_payment_term(self, payment_term: PaymentTerm) -> PaymentTerm:
        self.db.add(payment_term)
        self.db.flush()
        return payment_term

    def get_all_payment_terms(self) -> List[PaymentTerm]:
        return (
            self.db.query(PaymentTerm)
            .order_by(PaymentTerm.term_name.asc())
            .all()
        )

    def get_payment_term_by_id(
        self,
        payment_term_id: int,
    ) -> Optional[PaymentTerm]:

        return (
            self.db.query(PaymentTerm)
            .filter(PaymentTerm.payment_term_id == payment_term_id)
            .first()
        )

    def get_payment_term_by_name(self, term_name: str) -> Optional[PaymentTerm]:
        return (
            self.db.query(PaymentTerm)
            .filter(PaymentTerm.term_name == term_name)
            .first()
        )

    def delete_payment_term(self, payment_term: PaymentTerm) -> None:
        self.db.delete(payment_term)

    # =====================================================
    # System Configuration
    # =====================================================

    def get_all_system_configs(self) -> List[SystemConfiguration]:
        return (
            self.db.query(SystemConfiguration)
            .order_by(SystemConfiguration.config_key.asc())
            .all()
        )

    def get_system_config_by_key(
        self,
        config_key: str,
    ) -> Optional[SystemConfiguration]:

        return (
            self.db.query(SystemConfiguration)
            .filter(SystemConfiguration.config_key == config_key)
            .first()
        )
    def get_all_departments(self):
        return (
            self.db.query(Department)
            .order_by(Department.name.asc())
            .all()
        )
    def get_department_by_id(self, department_id: int) -> Optional[Department]:
        return (
            self.db.query(Department)
            .filter(Department.id == department_id)
            .first()
        )
    def get_department_by_code_or_name(self, code: str, name: str):
        return (
            self.db.query(Department)
            .filter((Department.code == code) | (Department.name == name))
            .first()
        )
    def create_department(self, department):
        department_obj = Department(
            code=department.code,
            name=department.name,
            is_active=department.is_active
        )
        self.db.add(department_obj)
        self.db.flush()
        return department_obj
    def delete_department(self, department: Department) -> None:
        self.db.delete(department)