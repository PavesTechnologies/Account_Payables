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

# =====================================================
# Tax Type
# =====================================================

class TaxTypeRequest(BaseModel):
    tax_type_name: str
    tax_code: str
    rate: float
    is_active: bool = Field(default=True)


class TaxTypeResponse(BaseModel):
    tax_type_id: int
    message: str


class TaxTypeDTO(BaseModel):
    tax_type_id: int
    tax_type_name: str
    tax_code: str
    rate: float
    is_active: bool



class DeleteTaxTypeResponse(BaseModel):
    message: str

# =====================================================
# Vendor Category
# =====================================================

class VendorCategoryRequest(BaseModel):
    category_name: str
    category_code: str
    description: str | None = None
    is_active: bool = Field(default=True)


class VendorCategoryResponse(BaseModel):
    vendor_category_id: int
    message: str


class VendorCategoryDTO(BaseModel):
    vendor_category_id: int
    category_name: str
    category_code: str
    description: str | None = None
    is_active: bool



class DeleteVendorCategoryResponse(BaseModel):
    message: str

# =====================================================
# Payment Term
# =====================================================

class PaymentTermRequest(BaseModel):
    payment_term_name: str
    payment_days: int
    description: str | None = None
    is_active: bool = Field(default=True)


class PaymentTermResponse(BaseModel):
    payment_term_id: int
    message: str


class PaymentTermDTO(BaseModel):
    payment_term_id: int
    payment_term_name: str
    payment_days: int
    description: str | None = None
    is_active: bool



class DeletePaymentTermResponse(BaseModel):
    message: str

# =====================================================
# Status Master
# =====================================================

class StatusMasterRequest(BaseModel):
    status_name: str
    status_code: str
    module_name: str
    description: str | None = None
    is_active: bool = Field(default=True)


class StatusMasterResponse(BaseModel):
    status_id: int
    message: str


class StatusMasterDTO(BaseModel):
    status_id: int
    status_name: str
    status_code: str
    module_name: str
    description: str | None = None
    is_active: bool

class DeleteStatusMasterResponse(BaseModel):
    message: str