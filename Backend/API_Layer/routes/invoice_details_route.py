from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from Backend.Business_Layer.services.invoice_details_service import InvoiceDetailsService
from Backend.API_Layer.interface.invoice_details_interface import InvoiceDetailsResponse

router = APIRouter()

@router.get("/invoice/{invoice_id}", response_model=InvoiceDetailsResponse)
def get_invoice_details_by_id(invoice_id:int, http_request: Request):
    db = http_request.state.db
    try:
        invoice_details_service = InvoiceDetailsService(db)
        invoice_details = invoice_details_service.get_invoice_details_by_id(invoice_id)
        return invoice_details
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))