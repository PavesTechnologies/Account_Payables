from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from Backend.Business_Layer.services.invoice_details_service import InvoiceDetailsService
from Backend.API_Layer.interface.invoice_details_interface import InvoiceDetailsResponse, InvoiceHistoryEventDTO
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Data_Access_Layer.dao.invoice_details_dao import InvoiceDetailsDAO
from Backend.API_Layer.utils.s3_utils import view_from_s3, download_from_s3
import logging
router = APIRouter()

# Any permission that already implies invoice visibility — INVOICE_VIEW now exists as the real
# unifying "can view this invoice" permission, but is kept alongside the others (rather than
# replacing them) since a pure Approver/Finance user's group grants INVOICE_VIEW too, while a
# user who somehow only holds one of the narrower permissions below should still see history.
_HISTORY_VIEW_PERMISSIONS = [
    "INVOICE_VIEW",
    "INVOICE_APPROVAL_VIEW",
    "INVOICE_SEND_FOR_APPROVAL",
    "INVOICE_APPROVE",
    "INVOICE_REJECT",
    "PAYMENT_VIEW",
]

_VIEW_PERMISSIONS = ["INVOICE_VIEW"]

logger = logging.getLogger(__name__)

@router.get(
    "/invoice/{invoice_id}",
    response_model=InvoiceDetailsResponse,
    dependencies=[Depends(permission_based_access(_VIEW_PERMISSIONS))],
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
@router.get(
    "/invoice",
    response_model = list[InvoiceDetailsResponse],
    dependencies=[Depends(permission_based_access(_VIEW_PERMISSIONS))],
)
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
@router.get(
    "/invoice/{invoice_id}/history",
    response_model=List[InvoiceHistoryEventDTO],
    dependencies=[Depends(permission_based_access(_HISTORY_VIEW_PERMISSIONS))],
)
def get_invoice_history(invoice_id: int, http_request: Request):
    db = http_request.state.db
    try:
        return InvoiceDetailsService(db).get_invoice_history(invoice_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Failed to fetch invoice history: invoice_id=%s", invoice_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve invoice history")


@router.get(
    "/invoice/view/{inbound_document_id}",
    dependencies=[Depends(permission_based_access(_VIEW_PERMISSIONS))],
)
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