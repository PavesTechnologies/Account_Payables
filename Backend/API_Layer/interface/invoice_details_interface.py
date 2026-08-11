from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class InvoiceDetailsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: int
    invoice_number: str
    vendor_name: str | None
    inbound_document_id: int | None
    invoice_type: str
    invoice_date: date
    due_date: date
    gross_amount: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    status_code: str | None