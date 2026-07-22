#Backend/API_Layer/interface/master.py
from pydantic import BaseModel, Field
from typing import List

class CountryRequest(BaseModel):
    country_name: str
    country_code: str
    is_active: bool = Field(default=True)

class CountryResponse(BaseModel):
    country_id: int
    message: str

class CountryDTO(BaseModel):
    country_id: int
    country_name: str
    country_code: str
    is_active: bool


class CountryListResponse(BaseModel):
    countries: List[CountryDTO]


class DeleteCountryResponse(BaseModel):
    message: str

# =====================================================
# Currency
# =====================================================

class CurrencyRequest(BaseModel):
    currency_name: str
    currency_code: str
    symbol: str
    decimal_places: int = Field(default=2)
    is_active: bool = Field(default=True)


class CurrencyResponse(BaseModel):
    currency_id: int
    message: str


class CurrencyDTO(BaseModel):
    currency_id: int
    currency_name: str
    currency_code: str
    symbol: str
    decimal_places: int
    is_active: bool

  


class CurrencyListResponse(BaseModel):
    currencies: list[CurrencyDTO]


class DeleteCurrencyResponse(BaseModel):
    message: str    

