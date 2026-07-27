# Backend/API_Layer/interface/vendor_interface.py
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# =====================================================
# Vendor Tax (scoped to a single vendor address — e.g. a GST
# registration tied to the address in that state)
# =====================================================


class VendorTaxCreateRequest(BaseModel):
    registration_type: str
    registration_number: str


class VendorTaxUpdateRequest(BaseModel):
    registration_type: Optional[str] = None
    registration_number: Optional[str] = None


class VendorTaxResponse(BaseModel):
    vendor_tax_id: int
    message: str


class DeleteVendorTaxResponse(BaseModel):
    message: str


class VendorTaxDTO(BaseModel):
    vendor_tax_id: int
    vendor_address_id: int
    registration_type: str
    registration_number: str
    is_verified: bool


# =====================================================
# Vendor Address
# =====================================================


class VendorAddressCreateRequest(BaseModel):
    address_type: str = Field(default="REGISTERED")
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country_id: int
    is_primary: bool = Field(default=False)


class VendorAddressUpdateRequest(BaseModel):
    address_type: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country_id: Optional[int] = None
    is_primary: Optional[bool] = None


class VendorAddressResponse(BaseModel):
    vendor_address_id: int
    message: str


class DeleteVendorAddressResponse(BaseModel):
    message: str


class VendorAddressDTO(BaseModel):
    vendor_address_id: int
    vendor_id: int
    address_type: str
    address_line1: str
    address_line2: Optional[str]
    city: str
    state: Optional[str]
    postal_code: Optional[str]
    country_id: int
    is_primary: bool
    # Field name matches the VendorAddress ORM relationship attribute
    # (vendor_tax) so FastAPI can populate it directly from the model instance.
    vendor_tax: List[VendorTaxDTO] = Field(default_factory=list)


# =====================================================
# Vendor Bank
# =====================================================


class VendorBankCreateRequest(BaseModel):
    bank_name: str
    account_holder_name: str
    account_number: Optional[str] = None
    iban: Optional[str] = None
    swift_code: Optional[str] = None
    routing_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    is_primary: bool = Field(default=False)


class VendorBankUpdateRequest(BaseModel):
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    iban: Optional[str] = None
    swift_code: Optional[str] = None
    routing_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    is_primary: Optional[bool] = None


class VendorBankResponse(BaseModel):
    vendor_bank_id: int
    message: str


class DeleteVendorBankResponse(BaseModel):
    message: str


class VendorBankDTO(BaseModel):
    vendor_bank_id: int
    vendor_id: int
    bank_name: str
    account_holder_name: str
    account_number: Optional[str]
    iban: Optional[str]
    swift_code: Optional[str]
    routing_number: Optional[str]
    ifsc_code: Optional[str]
    is_primary: bool
    effective_from: datetime.date
    effective_to: Optional[datetime.date]


# =====================================================
# Vendor
# =====================================================


class VendorCreateRequest(BaseModel):
    vendor_name: str
    country_id: int
    vendor_code: Optional[str] = None
    payment_term_id: Optional[int] = None
    currency_id: Optional[int] = None
    pan_number: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    status_id: Optional[int] = None


class VendorUpdateRequest(BaseModel):
    vendor_name: Optional[str] = None
    vendor_code: Optional[str] = None
    country_id: Optional[int] = None
    payment_term_id: Optional[int] = None
    currency_id: Optional[int] = None
    pan_number: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    status_id: Optional[int] = None


class VendorStatusUpdateRequest(BaseModel):
    is_active: bool


class VendorResponse(BaseModel):
    vendor_id: int
    message: str


class VendorDTO(BaseModel):
    vendor_id: int
    vendor_name: str
    vendor_code: Optional[str]
    country_id: int
    payment_term_id: Optional[int]
    currency_id: Optional[int]
    pan_number: Optional[str]
    phone_number: Optional[str]
    email: Optional[str]
    status_id: Optional[int]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: Optional[str]
    updated_by: Optional[str]
    # Field names match the Vendor ORM relationship attributes
    # (vendor_address/vendor_bank) so FastAPI can populate them directly
    # from the model instance. Tax registrations nest under each address
    # (VendorAddressDTO.vendor_tax) since VendorTax no longer links to
    # Vendor directly.
    vendor_address: List[VendorAddressDTO] = Field(default_factory=list)
    vendor_bank: List[VendorBankDTO] = Field(default_factory=list)
