# Backend/API_Layer/routes/procurement_route.py

import datetime
import decimal
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.procurement_interface import (
    ApprovePurchaseRequisitionRequest,
    DeletePurchaseRequisitionResponse,
    DeleteQuotationResponse,
    GeneratePurchaseOrderResponse,
    PurchaseRequisitionCreateRequest,
    PurchaseRequisitionDTO,
    PurchaseRequisitionLineDTO,
    PurchaseRequisitionLineRequest,
    PurchaseRequisitionResponse,
    PurchaseRequisitionUpdateRequest,
    QuotationDTO,
    QuotationResponse,
    RejectPurchaseRequisitionRequest,
    SelectVendorRequest,
)
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import download_from_s3, upload_to_s3, view_from_s3
from Backend.Business_Layer.services.procurement_service import ProcurementService
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

router = APIRouter()

_PR_NOT_FOUND = "Purchase requisition not found"
_LINE_NOT_FOUND = "Purchase requisition line not found"
_QUOTATION_NOT_FOUND = "Quotation not found"


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


def _status_code_for(message: str, not_found_message: str) -> int:
    return 404 if message == not_found_message else 422


# ---------------------------------------------------------
# Create Purchase Requisition
# ---------------------------------------------------------
@router.post("/purchase-requisitions", response_model=PurchaseRequisitionResponse)
def create_purchase_requisition(payload: PurchaseRequisitionCreateRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = ProcurementService(db)
        pr = service.create_purchase_requisition(payload, user_id)

        return PurchaseRequisitionResponse(id=pr.id, message="Purchase requisition created successfully")

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create purchase requisition")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# List Purchase Requisitions
# ---------------------------------------------------------
@router.get("/purchase-requisitions", response_model=list[PurchaseRequisitionDTO])
def get_all_purchase_requisitions(
    http_request: Request,
    department_id: Optional[int] = None,
    purchase_category_id: Optional[int] = None,
    status_id: Optional[int] = None,
    created_by: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.list_purchase_requisitions(
            department_id, purchase_category_id, status_id, created_by, search, skip, limit
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# List Purchase Requisitions Pending Approval
# (must be registered before the "/{pr_id}" route below)
# ---------------------------------------------------------
@router.get("/purchase-requisitions/pending-approval", response_model=list[PurchaseRequisitionDTO])
def get_pending_approval_purchase_requisitions(
    http_request: Request,
    department_id: Optional[int] = None,
):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.list_pending_approval(department_id)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get Purchase Requisition By ID
# ---------------------------------------------------------
@router.get("/purchase-requisitions/{pr_id}", response_model=PurchaseRequisitionDTO)
def get_purchase_requisition_by_id(pr_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.get_purchase_requisition(pr_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Update Purchase Requisition (DRAFT only)
# ---------------------------------------------------------
@router.put("/purchase-requisitions/{pr_id}", response_model=PurchaseRequisitionDTO)
def update_purchase_requisition(pr_id: int, payload: PurchaseRequisitionUpdateRequest, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.update_purchase_requisition(pr_id, payload)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not update purchase requisition")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Delete Purchase Requisition (DRAFT only)
# ---------------------------------------------------------
@router.delete("/purchase-requisitions/{pr_id}", response_model=DeletePurchaseRequisitionResponse)
def delete_purchase_requisition(pr_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        service.delete_purchase_requisition(pr_id)

        return DeletePurchaseRequisitionResponse(message="Purchase requisition deleted successfully")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Submit / Cancel Purchase Requisition
# ---------------------------------------------------------
@router.post("/purchase-requisitions/{pr_id}/submit", response_model=PurchaseRequisitionDTO)
def submit_purchase_requisition(pr_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.submit_purchase_requisition(pr_id)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purchase-requisitions/{pr_id}/cancel", response_model=PurchaseRequisitionDTO)
def cancel_purchase_requisition(pr_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.cancel_purchase_requisition(pr_id)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Approve / Reject Purchase Requisition
# ---------------------------------------------------------
@router.post("/purchase-requisitions/{pr_id}/approve", response_model=PurchaseRequisitionDTO)
def approve_purchase_requisition(
    pr_id: int,
    payload: ApprovePurchaseRequisitionRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = ProcurementService(db)
        return service.approve_purchase_requisition(pr_id, user_id, payload.comment)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purchase-requisitions/{pr_id}/reject", response_model=PurchaseRequisitionDTO)
def reject_purchase_requisition(
    pr_id: int,
    payload: RejectPurchaseRequisitionRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = ProcurementService(db)
        return service.reject_purchase_requisition(pr_id, user_id, payload.comment)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Purchase Requisition Lines (DRAFT only)
# ---------------------------------------------------------
@router.post("/purchase-requisitions/{pr_id}/lines", response_model=PurchaseRequisitionLineDTO)
def add_purchase_requisition_line(
    pr_id: int,
    payload: PurchaseRequisitionLineRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.add_line(pr_id, payload)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/purchase-requisitions/{pr_id}/lines/{line_id}", response_model=PurchaseRequisitionLineDTO)
def update_purchase_requisition_line(
    pr_id: int,
    line_id: int,
    payload: PurchaseRequisitionLineRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.update_line(pr_id, line_id, payload)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in (_PR_NOT_FOUND, _LINE_NOT_FOUND) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/purchase-requisitions/{pr_id}/lines/{line_id}", response_model=DeletePurchaseRequisitionResponse)
def delete_purchase_requisition_line(pr_id: int, line_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        service.delete_line(pr_id, line_id)

        return DeletePurchaseRequisitionResponse(message="Purchase requisition line deleted successfully")

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in (_PR_NOT_FOUND, _LINE_NOT_FOUND) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Quotation
# ---------------------------------------------------------
@router.post("/purchase-requisitions/{pr_id}/quotations", response_model=QuotationResponse)
async def create_quotation(
    pr_id: int,
    http_request: Request,
    vendor_id: int = Form(...),
    quotation_number: Optional[str] = Form(None),
    quotation_date: Optional[datetime.date] = Form(None),
    valid_until: Optional[datetime.date] = Form(None),
    total_amount: Optional[decimal.Decimal] = Form(None),
    file: UploadFile = File(...),
):
    db = http_request.state.db

    content = await file.read()

    try:
        validate_upload_file(file, content)
    except (UnsupportedFileType, InvalidUploadFile) as e:
        status_code = 415 if isinstance(e, UnsupportedFileType) else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    try:
        user_id = _get_user_id(http_request)

        upload_result = upload_to_s3(file.filename, content, file.content_type)

        service = ProcurementService(db)
        quotation = service.create_quotation(
            pr_id=pr_id,
            vendor_id=vendor_id,
            file_url=upload_result["filepath"],
            quotation_number=quotation_number,
            quotation_date=quotation_date,
            valid_until=valid_until,
            total_amount=total_amount,
            user_id=user_id,
        )

        return QuotationResponse(id=quotation.id, message="Quotation created successfully")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/purchase-requisitions/{pr_id}/quotations", response_model=list[QuotationDTO])
def get_quotations_for_pr(pr_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.list_quotations(pr_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotations/{quotation_id}", response_model=QuotationDTO)
def get_quotation_by_id(quotation_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.get_quotation(quotation_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotations/{quotation_id}/document/view")
def view_quotation_document(quotation_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        quotation = service.get_quotation(quotation_id)

        return view_from_s3(quotation.file_url)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotations/{quotation_id}/document/download")
def download_quotation_document(quotation_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        quotation = service.get_quotation(quotation_id)

        return download_from_s3(quotation.file_url)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/quotations/{quotation_id}", response_model=DeleteQuotationResponse)
def delete_quotation(quotation_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        service.delete_quotation(quotation_id)

        return DeleteQuotationResponse(message="Quotation deleted successfully")

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in (_PR_NOT_FOUND, _QUOTATION_NOT_FOUND) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Vendor Selection
# ---------------------------------------------------------
@router.post("/purchase-requisitions/{pr_id}/select-vendor", response_model=PurchaseRequisitionDTO)
def select_vendor(pr_id: int, payload: SelectVendorRequest, http_request: Request):
    db = http_request.state.db

    try:
        service = ProcurementService(db)
        return service.select_vendor(pr_id, payload.quotation_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in (_PR_NOT_FOUND, _QUOTATION_NOT_FOUND) else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Purchase Order Generation
# ---------------------------------------------------------
@router.post("/purchase-requisitions/{pr_id}/generate-po", response_model=GeneratePurchaseOrderResponse)
def generate_purchase_order(pr_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = ProcurementService(db)
        purchase_order = service.generate_purchase_order(pr_id, user_id)

        return GeneratePurchaseOrderResponse(
            po_id=purchase_order.po_id,
            pr_id=pr_id,
            message="Purchase order generated successfully",
        )

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=_status_code_for(str(e), _PR_NOT_FOUND), detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not generate purchase order")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
