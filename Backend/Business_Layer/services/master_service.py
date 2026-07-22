# Backend/Business_Layer/services/master_service.py

from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.master import (
    Country,
    Currency,
    TaxType,
    VendorCategory,
    PaymentTerm,
    StatusMaster,
)
from Backend.API_Layer.interface.master import (
    CountryRequest,
    CurrencyRequest,
     TaxTypeRequest,
    VendorCategoryRequest,
    PaymentTermRequest,
    StatusMasterRequest,   
)
from Backend.Business_Layer.utils.country_validator import validate_country_code


class MasterService:
    def __init__(self, db):
        self.db = db
        self.master_dao = MasterDAO(db)

    # =========================================================
    # Country
    # =========================================================

    def create_country(
        self,
        country_data: CountryRequest,
        user_id: str,
    ) -> Country:

        validated_code = validate_country_code(
            country_data.country_code
        )

        country = Country(
            country_name=country_data.country_name,
            country_code=validated_code,
            is_active=country_data.is_active,
            created_by=user_id,
            updated_by=user_id,
        )

        self.master_dao.create_country(country)

        self.db.commit()
        self.db.refresh(country)

        return country

    def get_all_countries(self):
        return self.master_dao.get_all_countries()

    def get_country_by_id(self, country_id: int) -> Country:

        country = self.master_dao.get_country_by_id(country_id)

        if country is None:
            raise ValueError("Country not found")

        return country

    def delete_country(self, country_id: int):

        country = self.master_dao.get_country_by_id(country_id)

        if country is None:
            raise ValueError("Country not found.")

        self.master_dao.delete_country(country)

        self.db.commit()

    # =========================================================
    # Currency
    # =========================================================

    def create_currency(
        self,
        currency_data: CurrencyRequest,
        user_id: str,
    ) -> Currency:

        existing_currency = self.master_dao.get_currency_by_code(
            currency_data.currency_code.upper()
        )

        if existing_currency:
            raise ValueError("Currency code already exists.")

        currency = Currency(
            currency_name=currency_data.currency_name,
            currency_code=currency_data.currency_code.upper(),
            symbol=currency_data.symbol,
            decimal_places=currency_data.decimal_places,
            is_active=currency_data.is_active,
            created_by=user_id,
            updated_by=user_id,
        )

        self.master_dao.create_currency(currency)

        self.db.commit()
        self.db.refresh(currency)

        return currency

    def get_all_currencies(self):
        return self.master_dao.get_all_currencies()

    def get_currency_by_id(self, currency_id: int) -> Currency:

        currency = self.master_dao.get_currency_by_id(currency_id)

        if currency is None:
            raise ValueError("Currency not found.")

        return currency

    def delete_currency(self, currency_id: int):

        currency = self.master_dao.get_currency_by_id(currency_id)

        if currency is None:
            raise ValueError("Currency not found.")

        self.master_dao.delete_currency(currency)

        self.db.commit()

    # =====================================================
    # Tax Type
    # =====================================================

    def create_tax_type(
        self,
        tax_data: TaxTypeRequest,
        user_id: str,
    ) -> TaxType:

        existing = self.master_dao.get_tax_type_by_code(
            tax_data.tax_code.upper()
        )

        if existing:
            raise ValueError("Tax code already exists.")

        tax = TaxType(
            tax_type_name=tax_data.tax_type_name,
            tax_code=tax_data.tax_code.upper(),
            rate=tax_data.rate,
            is_active=tax_data.is_active,
            created_by=user_id,
            updated_by=user_id,
        )

        self.master_dao.create_tax_type(tax)

        self.db.commit()
        self.db.refresh(tax)

        return tax


    def get_all_tax_types(self):
        return self.master_dao.get_all_tax_types()


    def get_tax_type_by_id(
        self,
        tax_type_id: int,
    ):

        tax = self.master_dao.get_tax_type_by_id(
            tax_type_id
        )

        if tax is None:
            raise ValueError("Tax Type not found.")

        return tax


    def delete_tax_type(
        self,
        tax_type_id: int,
    ):

        tax = self.master_dao.get_tax_type_by_id(
            tax_type_id
        )

        if tax is None:
            raise ValueError("Tax Type not found.")

        self.master_dao.delete_tax_type(tax)

        self.db.commit()

    # =====================================================
    # Vendor Category
    # =====================================================

    def create_vendor_category(
        self,
        data: VendorCategoryRequest,
        user_id: str,
    ) -> VendorCategory:

        existing = self.master_dao.get_vendor_category_by_code(
            data.category_code.upper()
        )

        if existing:
            raise ValueError(
                "Vendor Category code already exists."
            )

        category = VendorCategory(
            category_name=data.category_name,
            category_code=data.category_code.upper(),
            description=data.description,
            is_active=data.is_active,
            created_by=user_id,
            updated_by=user_id,
        )

        self.master_dao.create_vendor_category(category)

        self.db.commit()
        self.db.refresh(category)

        return category


    def get_all_vendor_categories(self):
        return self.master_dao.get_all_vendor_categories()


    def get_vendor_category_by_id(
        self,
        category_id: int,
    ):

        category = self.master_dao.get_vendor_category_by_id(
            category_id
        )

        if category is None:
            raise ValueError(
                "Vendor Category not found."
            )

        return category


    def delete_vendor_category(
        self,
        category_id: int,
    ):

        category = self.master_dao.get_vendor_category_by_id(
            category_id
        )

        if category is None:
            raise ValueError(
                "Vendor Category not found."
            )

        self.master_dao.delete_vendor_category(
            category
        )

        self.db.commit()

    # =====================================================
    # Payment Term
    # =====================================================

    def create_payment_term(
        self,
        data: PaymentTermRequest,
        user_id: str,
    ) -> PaymentTerm:

        payment_term = PaymentTerm(
            payment_term_name=data.payment_term_name,
            payment_days=data.payment_days,
            description=data.description,
            is_active=data.is_active,
            created_by=user_id,
            updated_by=user_id,
        )

        self.master_dao.create_payment_term(
            payment_term
        )

        self.db.commit()
        self.db.refresh(payment_term)

        return payment_term


    def get_all_payment_terms(self):
        return self.master_dao.get_all_payment_terms()


    def get_payment_term_by_id(
        self,
        payment_term_id: int,
    ):

        payment_term = self.master_dao.get_payment_term_by_id(
            payment_term_id
        )

        if payment_term is None:
            raise ValueError(
                "Payment Term not found."
            )

        return payment_term


    def delete_payment_term(
        self,
        payment_term_id: int,
    ):

        payment_term = self.master_dao.get_payment_term_by_id(
            payment_term_id
        )

        if payment_term is None:
            raise ValueError(
                "Payment Term not found."
            )

        self.master_dao.delete_payment_term(
            payment_term
        )

        self.db.commit()

    # =====================================================
    # Status Master
    # =====================================================

    def create_status(
        self,
        data: StatusMasterRequest,
        user_id: str,
    ) -> StatusMaster:

        existing = self.master_dao.get_status_by_code(
            data.status_code.upper()
        )

        if existing:
            raise ValueError(
                "Status code already exists."
            )

        status = StatusMaster(
            status_name=data.status_name,
            status_code=data.status_code.upper(),
            module_name=data.module_name,
            description=data.description,
            is_active=data.is_active,
            created_by=user_id,
            updated_by=user_id,
        )

        self.master_dao.create_status(status)

        self.db.commit()
        self.db.refresh(status)

        return status


    def get_all_statuses(self):
        return self.master_dao.get_all_statuses()


    def get_status_by_id(
        self,
        status_id: int,
    ):

        status = self.master_dao.get_status_by_id(
            status_id
        )

        if status is None:
            raise ValueError(
                "Status not found."
            )

        return status


    def delete_status(
        self,
        status_id: int,
    ):

        status = self.master_dao.get_status_by_id(
            status_id
        )

        if status is None:
            raise ValueError(
                "Status not found."
            )

        self.master_dao.delete_status(status)

        self.db.commit()