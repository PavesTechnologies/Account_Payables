# Backend/Business_Layer/services/master_service.py

from Backend.Data_Access_Layer.dao.system_dao import SystemDAO
from Backend.Data_Access_Layer.models.master import (
    Country,
    Currency,
    TaxType,
    PaymentTerm,
    StatusMaster,
)
from Backend.API_Layer.interface.system_interface import (
    CountryRequest,
    CurrencyRequest,
)
from Backend.Business_Layer.utils.country_validator import validate_country_code


class SystemService:
    def __init__(self, db):
        self.db = db
        self.master_dao = SystemDAO(db)

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