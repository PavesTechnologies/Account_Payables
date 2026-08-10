from pydantic import BaseModel
from datetime import date
from decimal import Decimal
class InvoiceDetailsResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    vendor_id: int
    inbound_document_id: int
    invoice_type: str
    invoice_date: date
    due_date: date
    gross_amount: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    status_id: str