# Backend/Data_Access_Layer/dao/master_dao.py

from typing import List, Optional

from Backend.Data_Access_Layer.models.master import (
    Country,
    Currency
)


class MasterDAO:
    def __init__(self, db):
        self.db = db

    # =====================================================
    # Country
    # =====================================================

    def create_country(self, country: Country) -> Country:
        self.db.add(country)
        self.db.flush()
        return country

    def get_all_countries(self) -> List[Country]:
        return (
            self.db.query(
                Country.country_id,
                Country.country_name,
                Country.country_code,
                Country.is_active,
            ).all()
        )

    def get_country_by_id(
        self,
        country_id: int,
    ) -> Optional[Country]:

        return (
            self.db.query(Country)
            .filter(Country.country_id == country_id)
            .first()
        )

    def delete_country(
        self,
        country: Country,
    ) -> None:

        self.db.delete(country)

    # =====================================================
    # Currency
    # =====================================================

    def create_currency(
        self,
        currency: Currency,
    ) -> Currency:

        self.db.add(currency)
        self.db.flush()

        return currency

    def get_all_currencies(
        self,
    ) -> List[Currency]:

        return (
            self.db.query(Currency)
            .order_by(Currency.currency_name.asc())
            .all()
        )

    def get_currency_by_id(
        self,
        currency_id: int,
    ) -> Optional[Currency]:

        return (
            self.db.query(Currency)
            .filter(Currency.currency_id == currency_id)
            .first()
        )

    def get_currency_by_code(
        self,
        currency_code: str,
    ) -> Optional[Currency]:

        return (
            self.db.query(Currency)
            .filter(Currency.currency_code == currency_code)
            .first()
        )

    def delete_currency(
        self,
        currency: Currency,
    ) -> None:

        self.db.delete(currency)

    