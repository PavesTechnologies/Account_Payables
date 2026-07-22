# Backend/Business_Layer/services/master_service.py

from Backend.Business_Layer.utils.system_config_validator import validate_config_value
from Backend.Business_Layer.utils.tax_type_validator import (
    validate_calculation_type,
    validate_effective_range,
)
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.master import (
    PaymentTerm,
    SystemConfiguration,
    TaxType,
)


class MasterService:
    def __init__(self, db):
        self.db = db
        self.master_dao = MasterDAO(db)

    # =========================================================
    # Tax Type
    # =========================================================

    def create_tax_type(self, tax_type_data, user_id: str) -> TaxType:

        if not self.master_dao.country_exists(tax_type_data.country_id):
            raise ValueError("Country not found for the given country_id")

        calculation_type = validate_calculation_type(
            tax_type_data.calculation_type,
            tax_type_data.rate_percent,
            tax_type_data.fixed_amount,
        )
        validate_effective_range(
            tax_type_data.effective_from,
            tax_type_data.effective_to,
        )

        existing = self.master_dao.get_tax_type_by_code(
            tax_type_data.country_id,
            tax_type_data.tax_code,
            tax_type_data.effective_from,
        )
        if existing:
            raise ValueError(
                "A tax type with this country, tax_code and effective_from already exists."
            )

        tax_type = TaxType(
            country_id=tax_type_data.country_id,
            tax_name=tax_type_data.tax_name,
            tax_code=tax_type_data.tax_code,
            calculation_type=calculation_type,
            rate_percent=tax_type_data.rate_percent,
            fixed_amount=tax_type_data.fixed_amount,
            is_withholding=tax_type_data.is_withholding,
            effective_from=tax_type_data.effective_from,
            effective_to=tax_type_data.effective_to,
            is_active=tax_type_data.is_active,
            is_system_default=False,
            created_by=user_id,
            updated_by=user_id,
        )

        self.master_dao.create_tax_type(tax_type)

        self.db.commit()
        self.db.refresh(tax_type)

        return tax_type

    def get_all_tax_types(self, country_id: int = None):
        return self.master_dao.get_all_tax_types(country_id)

    def get_tax_type_by_id(self, tax_type_id: int) -> TaxType:

        tax_type = self.master_dao.get_tax_type_by_id(tax_type_id)

        if tax_type is None:
            raise ValueError("Tax type not found")

        return tax_type

    def update_tax_type(self, tax_type_id: int, update_data, user_id: str) -> TaxType:

        tax_type = self.master_dao.get_tax_type_by_id(tax_type_id)

        if tax_type is None:
            raise ValueError("Tax type not found")

        new_calculation_type = (
            update_data.calculation_type
            if update_data.calculation_type is not None
            else tax_type.calculation_type
        )
        new_rate_percent = (
            update_data.rate_percent
            if update_data.rate_percent is not None
            else tax_type.rate_percent
        )
        new_fixed_amount = (
            update_data.fixed_amount
            if update_data.fixed_amount is not None
            else tax_type.fixed_amount
        )

        calculation_type = validate_calculation_type(
            new_calculation_type,
            new_rate_percent,
            new_fixed_amount,
        )

        new_effective_from = (
            update_data.effective_from
            if update_data.effective_from is not None
            else tax_type.effective_from
        )
        new_effective_to = (
            update_data.effective_to
            if update_data.effective_to is not None
            else tax_type.effective_to
        )
        validate_effective_range(new_effective_from, new_effective_to)

        if update_data.tax_name is not None:
            tax_type.tax_name = update_data.tax_name
        tax_type.calculation_type = calculation_type
        tax_type.rate_percent = new_rate_percent
        tax_type.fixed_amount = new_fixed_amount
        if update_data.is_withholding is not None:
            tax_type.is_withholding = update_data.is_withholding
        tax_type.effective_from = new_effective_from
        tax_type.effective_to = new_effective_to
        if update_data.is_active is not None:
            tax_type.is_active = update_data.is_active
        tax_type.updated_by = user_id

        self.db.commit()
        self.db.refresh(tax_type)

        return tax_type

    def delete_tax_type(self, tax_type_id: int):

        tax_type = self.master_dao.get_tax_type_by_id(tax_type_id)

        if tax_type is None:
            raise ValueError("Tax type not found.")

        if tax_type.is_system_default:
            raise PermissionError(
                "System-default tax types cannot be deleted. Deactivate it instead."
            )

        self.master_dao.delete_tax_type(tax_type)

        self.db.commit()

    # =========================================================
    # Payment Term
    # =========================================================

    def create_payment_term(self, payment_term_data, user_id: str) -> PaymentTerm:

        existing = self.master_dao.get_payment_term_by_name(
            payment_term_data.term_name
        )
        if existing:
            raise ValueError("A payment term with this name already exists.")

        payment_term = PaymentTerm(
            term_name=payment_term_data.term_name,
            due_days=payment_term_data.due_days,
            discount_percent=payment_term_data.discount_percent,
            discount_days=payment_term_data.discount_days,
            is_active=payment_term_data.is_active,
            is_system_default=False,
            created_by=user_id,
            updated_by=user_id,
        )

        self.master_dao.create_payment_term(payment_term)

        self.db.commit()
        self.db.refresh(payment_term)

        return payment_term

    def get_all_payment_terms(self):
        return self.master_dao.get_all_payment_terms()

    def get_payment_term_by_id(self, payment_term_id: int) -> PaymentTerm:

        payment_term = self.master_dao.get_payment_term_by_id(payment_term_id)

        if payment_term is None:
            raise ValueError("Payment term not found")

        return payment_term

    def update_payment_term(
        self,
        payment_term_id: int,
        update_data,
        user_id: str,
    ) -> PaymentTerm:

        payment_term = self.master_dao.get_payment_term_by_id(payment_term_id)

        if payment_term is None:
            raise ValueError("Payment term not found")

        if update_data.term_name is not None:
            payment_term.term_name = update_data.term_name
        if update_data.due_days is not None:
            payment_term.due_days = update_data.due_days
        if update_data.discount_percent is not None:
            payment_term.discount_percent = update_data.discount_percent
        if update_data.discount_days is not None:
            payment_term.discount_days = update_data.discount_days
        if update_data.is_active is not None:
            payment_term.is_active = update_data.is_active
        payment_term.updated_by = user_id

        self.db.commit()
        self.db.refresh(payment_term)

        return payment_term

    def delete_payment_term(self, payment_term_id: int):

        payment_term = self.master_dao.get_payment_term_by_id(payment_term_id)

        if payment_term is None:
            raise ValueError("Payment term not found.")

        if payment_term.is_system_default:
            raise PermissionError(
                "System-default payment terms cannot be deleted. Deactivate it instead."
            )

        self.master_dao.delete_payment_term(payment_term)

        self.db.commit()

    # =========================================================
    # System Configuration
    # =========================================================

    def get_all_system_configs(self):
        return self.master_dao.get_all_system_configs()

    def get_system_config_by_key(self, config_key: str) -> SystemConfiguration:

        config = self.master_dao.get_system_config_by_key(config_key)

        if config is None:
            raise ValueError("Configuration key not found")

        return config

    def update_system_config(
        self,
        config_key: str,
        update_data,
        user_id: str,
    ) -> SystemConfiguration:

        config = self.master_dao.get_system_config_by_key(config_key)

        if config is None:
            raise ValueError("Configuration key not found")

        validate_config_value(update_data.config_value, config.data_type)

        config.config_value = update_data.config_value
        if update_data.description is not None:
            config.description = update_data.description
        config.updated_by = user_id

        self.db.commit()
        self.db.refresh(config)

        return config
