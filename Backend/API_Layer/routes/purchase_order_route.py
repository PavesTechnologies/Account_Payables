# Backend/API_Layer/routes/purchase_order_route.py

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.purchase_order_interface import (
    DeletePurchaseOrderResponse,
    PurchaseOrderCreateRequest,
    PurchaseOrderDTO,
    PurchaseOrderResponse,
    PurchaseOrderStatusUpdateRequest,
    PurchaseOrderUpdateRequest,
    UploadPurchaseOrderDocumentResponse,
)
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import download_from_s3, view_from_s3
from Backend.Business_Layer.services.purchase_order_service import PurchaseOrderService
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

router = APIRouter()

_NOT_FOUND = "Purchase order not found"


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


# ---------------------------------------------------------
# Create Purchase Order
# ---------------------------------------------------------
@router.post("", response_model=PurchaseOrderResponse)
def create_purchase_order(payload: PurchaseOrderCreateRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = PurchaseOrderService(db)
        purchase_order = service.create_purchase_order(payload, user_id)

        return PurchaseOrderResponse(
            po_id=purchase_order.po_id,
            message="Purchase order created successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A purchase order with this po_number already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get All Purchase Orders
# ---------------------------------------------------------
@router.get("", response_model=list[PurchaseOrderDTO])
def get_all_purchase_orders(
    http_request: Request,
    vendor_id: Optional[int] = None,
    status_id: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    db = http_request.state.db

    try:
        service = PurchaseOrderService(db)
        return service.list_purchase_orders(vendor_id, status_id, search, skip, limit)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get Purchase Order By ID (includes related goods receipts and invoices
# via eager-loaded relationships)
# ---------------------------------------------------------
@router.get("/{po_id}", response_model=PurchaseOrderDTO)
def get_purchase_order_by_id(po_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = PurchaseOrderService(db)
        return service.get_purchase_order(po_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Update Purchase Order
# ---------------------------------------------------------
@router.put("/{po_id}", response_model=PurchaseOrderDTO)
def update_purchase_order(
    po_id: int,
    payload: PurchaseOrderUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = PurchaseOrderService(db)
        return service.update_purchase_order(po_id, payload, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A purchase order with this po_number already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Update Purchase Order Status
# ---------------------------------------------------------
@router.patch("/{po_id}/status", response_model=PurchaseOrderDTO)
def update_purchase_order_status(
    po_id: int,
    payload: PurchaseOrderStatusUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = PurchaseOrderService(db)
        return service.change_status(po_id, payload.status_id, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Delete Purchase Order
# ---------------------------------------------------------
@router.delete("/{po_id}", response_model=DeletePurchaseOrderResponse)
def delete_purchase_order(po_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = PurchaseOrderService(db)
        service.delete_purchase_order(po_id, user_id)

        return DeletePurchaseOrderResponse(message="Purchase order deleted successfully")

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Purchase order cannot be deleted because it is referenced by "
            "existing goods receipts or invoices",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# Purchase Order Document
# ===========================================================


@router.post("/{po_id}/document", response_model=UploadPurchaseOrderDocumentResponse)
async def upload_purchase_order_document(
    po_id: int,
    http_request: Request,
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

        service = PurchaseOrderService(db)
        purchase_order = service.upload_document(
            po_id, file.filename, content, file.content_type, user_id
        )

        return UploadPurchaseOrderDocumentResponse(
            po_id=purchase_order.po_id,
            file_path=purchase_order.file_path,
            message="Purchase order document uploaded successfully",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{po_id}/document/view")
def view_purchase_order_document(po_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = PurchaseOrderService(db)
        file_path = service.get_document_path(po_id)

        return view_from_s3(file_path)

    except ValueError as e:
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{po_id}/document/download")
def download_purchase_order_document(po_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = PurchaseOrderService(db)
        file_path = service.get_document_path(po_id)

        return download_from_s3(file_path)

    except ValueError as e:
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
