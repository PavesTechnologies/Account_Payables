# Backend/Business_Logic_Layer/service/master_service.py
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.master import Country
from Backend.API_Layer.interface.master import CountryRequest
from Backend.Business_Layer.utils.country_validator import validate_country_code


class MasterService:
    def __init__(self, db):
        self.db = db
        self.master_dao = MasterDAO(db)

    def create_country(self, country_data: CountryRequest, user_id: str) -> Country:
        validated_code = validate_country_code(country_data.country_code)
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