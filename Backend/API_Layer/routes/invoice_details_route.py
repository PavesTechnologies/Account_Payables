from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from Backend.Business_Layer.services.invoice_details_service import InvoiceDetailsService
from Backend.API_Layer.interface.invoice_details_interface import InvoiceDetailsResponse
from Backend.Data_Access_Layer.dao.invoice_details_dao import InvoiceDetailsDAO
from Backend.API_Layer.utils.s3_utils import view_from_s3, download_from_s3
import logging
router = APIRouter()

logger = logging.getLogger(__name__)

@router.get(
    "/invoice/{invoice_id}",
    response_model=InvoiceDetailsResponse,
)
def get_invoice_details_by_id(
    invoice_id: int,
    http_request: Request,
):
    db = http_request.state.db

    try:
        service = InvoiceDetailsService(db)

        invoice = service.get_invoice_details_by_id(invoice_id)

        if invoice is None:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found",
            )

        return invoice

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Failed to fetch invoice details: invoice_id=%s",
            invoice_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve invoice details",
        )
@router.get("/invoice", response_model = list[InvoiceDetailsResponse])
def get_all_invoice_details(http_request: Request):
    db = http_request.state.db
    try:
        service = InvoiceDetailsService(db)
        invoices = service.get_all_invoice_details()
        return invoices
    except Exception as e:
        logger.exception("Failed to fetch all invoice details: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve all invoice details",
        )
@router.get("/invoice/view/{inbound_document_id}")
def view_invoice_from_s3(inbound_document_id: int, http_request: Request):
    db = http_request.state.db
    try:
        dao = InvoiceDetailsDAO(db)
        file_path = dao.file_name_by_inbound_document_id(inbound_document_id)
        if file_path is None:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {inbound_document_id} not found",
            )
        return view_from_s3(file_path)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception("Failed to view invoice from S3: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to view invoice from S3",
        )