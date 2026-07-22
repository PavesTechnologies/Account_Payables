# Backend/Data_Access_Layer/dao/master_dao.py

from typing import List, Optional

from Backend.Data_Access_Layer.models.master import (
    Country,
    Currency,
    StatusMaster,
)


class SystemDAO:
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

    # =====================================================
    # Status Master
    # =====================================================

    def get_all_statuses(
        self,
        module_name: Optional[str] = None,
    ) -> List[StatusMaster]:

        query = self.db.query(StatusMaster)

        if module_name is not None:
            query = query.filter(StatusMaster.module_name == module_name)

        return query.order_by(
            StatusMaster.module_name.asc(),
            StatusMaster.display_order.asc(),
        ).all()

    def get_status_by_id(
        self,
        status_id: int,
    ) -> Optional[StatusMaster]:

        return (
            self.db.query(StatusMaster)
            .filter(StatusMaster.status_id == status_id)
            .first()
        )
