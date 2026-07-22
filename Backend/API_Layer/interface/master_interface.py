# Backend/API_Layer/interface/master_interface.py
import datetime
import decimal
from typing import Optional

from pydantic import BaseModel, Field

# =====================================================
# Tax Type
# =====================================================


class TaxTypeRequest(BaseModel):
    country_id: int
    tax_name: str
    tax_code: str
    calculation_type: str = Field(default="PERCENTAGE")
    rate_percent: Optional[decimal.Decimal] = None
    fixed_amount: Optional[decimal.Decimal] = None
    is_withholding: bool = Field(default=False)
    effective_from: datetime.date
    effective_to: Optional[datetime.date] = None
    is_active: bool = Field(default=True)


class TaxTypeUpdateRequest(BaseModel):
    tax_name: Optional[str] = None
    calculation_type: Optional[str] = None
    rate_percent: Optional[decimal.Decimal] = None
    fixed_amount: Optional[decimal.Decimal] = None
    is_withholding: Optional[bool] = None
    effective_from: Optional[datetime.date] = None
    effective_to: Optional[datetime.date] = None
    is_active: Optional[bool] = None


class TaxTypeResponse(BaseModel):
    tax_type_id: int
    message: str


class TaxTypeDTO(BaseModel):
    tax_type_id: int
    country_id: int
    tax_name: str
    tax_code: str
    calculation_type: str
    rate_percent: Optional[decimal.Decimal]
    fixed_amount: Optional[decimal.Decimal]
    is_withholding: bool
    effective_from: datetime.date
    effective_to: Optional[datetime.date]
    is_system_default: bool
    is_active: bool


class DeleteTaxTypeResponse(BaseModel):
    message: str


# =====================================================
# Payment Term
# =====================================================


class PaymentTermRequest(BaseModel):
    term_name: str
    due_days: int = Field(default=0)
    discount_percent: decimal.Decimal = Field(default=decimal.Decimal("0"))
    discount_days: int = Field(default=0)
    is_active: bool = Field(default=True)


class PaymentTermUpdateRequest(BaseModel):
    term_name: Optional[str] = None
    due_days: Optional[int] = None
    discount_percent: Optional[decimal.Decimal] = None
    discount_days: Optional[int] = None
    is_active: Optional[bool] = None


class PaymentTermResponse(BaseModel):
    payment_term_id: int
    message: str


class PaymentTermDTO(BaseModel):
    payment_term_id: int
    term_name: str
    due_days: int
    discount_percent: decimal.Decimal
    discount_days: int
    is_system_default: bool
    is_active: bool


class DeletePaymentTermResponse(BaseModel):
    message: str


# =====================================================
# System Configuration
# =====================================================


class SystemConfigUpdateRequest(BaseModel):
    config_value: str
    description: Optional[str] = None


class SystemConfigDTO(BaseModel):
    config_key: str
    config_value: str
    data_type: str
    description: Optional[str]
    updated_by: Optional[str]
    updated_at: datetime.datetime


class UpdateSystemConfigResponse(BaseModel):
    message: str
