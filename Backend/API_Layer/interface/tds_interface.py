# Backend/API_Layer/interface/tds_interface.py
import datetime
import decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TdsDetermineRequest(BaseModel):
    # Omit to let the purchase_category default mapping suggest one.
    payment_nature_code: Optional[str] = None


class TdsUpdateRequest(BaseModel):
    # AP Executive correction - always required, always re-runs the server-side
    # calculation (see TDSDeterminationService.update_inputs).
    payment_nature_code: str


class TdsVerifyRequest(BaseModel):
    remarks: Optional[str] = None


class TdsPaymentNatureDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class TdsRuleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tax_rule_id: int
    rule_code: str
    rule_name: str
    legal_reference: Optional[str] = None


class InvoiceTdsDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: int
    tds_applicable: bool
    payment_nature: Optional[TdsPaymentNatureDTO] = None
    tds_rule: Optional[TdsRuleDTO] = None
    taxable_base: Optional[decimal.Decimal] = None
    tds_rate: Optional[decimal.Decimal] = None
    tds_amount: Optional[decimal.Decimal] = None
    threshold_amount: Optional[decimal.Decimal] = None
    prior_period_aggregate: Optional[decimal.Decimal] = None
    current_transaction_amount: Optional[decimal.Decimal] = None
    aggregate_amount: Optional[decimal.Decimal] = None
    pan_status: Optional[str] = None
    entity_type: Optional[str] = None
    # GST registration compliance signal - a warning only, never an input to
    # tds_applicable/tds_rate/tds_amount above.
    gstin_status: Optional[str] = None
    gstin_checked_at: Optional[datetime.datetime] = None
    determination_status: str
    determination_reason: Optional[str] = None
    determined_at: Optional[datetime.datetime] = None
    determined_by: Optional[str] = None
    verified_at: Optional[datetime.datetime] = None
    verified_by: Optional[str] = None
    remarks: Optional[str] = None
