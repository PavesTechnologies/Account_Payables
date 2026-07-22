#Backend/API_Layer/interface/master.py
from pydantic import BaseModel, Field

class CountryRequest(BaseModel):
    country_name: str
    country_code: str
    is_active: bool = Field(default=True)

class CountryResponse(BaseModel):
    country_id: int
    message: str