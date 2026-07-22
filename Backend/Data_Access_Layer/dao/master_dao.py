# Backend/Data_Access_Layer/dao/master_dao.py
from Backend.Data_Access_Layer.models.master import Country


# master_dao.py
class MasterDAO:
    def __init__(self, db):
        self.db = db

    def create_country(self, country: Country) -> Country:
        self.db.add(country)
        self.db.flush()  # assigns country_id without committing
        return country