# Backend/API_Layer/routes/goods_receipt_route.py

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.goods_receipt_interface import (
    DeleteGoodsReceiptResponse,
    GoodsReceiptCreateRequest,
    GoodsReceiptDTO,
    GoodsReceiptResponse,
    GoodsReceiptUpdateRequest,
    UploadGoodsReceiptDocumentResponse,
)
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import download_from_s3, view_from_s3
from Backend.Business_Layer.services.goods_receipt_service import GoodsReceiptService
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

router = APIRouter()

_NOT_FOUND = "Goods receipt not found"


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


# ---------------------------------------------------------
# Create Goods Receipt
# ---------------------------------------------------------
@router.post("", response_model=GoodsReceiptResponse)
def create_goods_receipt(payload: GoodsReceiptCreateRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = GoodsReceiptService(db)
        goods_receipt = service.create_goods_receipt(payload, user_id)

        return GoodsReceiptResponse(
            grn_id=goods_receipt.grn_id,
            message="Goods receipt created successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to create goods receipt")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get All Goods Receipts
# ---------------------------------------------------------
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from Backend.API_Layer.interface.goods_receipt_interface import (
    GoodsReceiptDTO,
    GoodsReceiptLineDTO,
)
from Backend.Business_Layer.services.goods_receipt_service import GoodsReceiptService

router = APIRouter()


@router.get("", response_model=list[GoodsReceiptDTO])
def get_all_goods_receipts(
    http_request: Request,
    vendor_id: Optional[int] = None,
    po_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
):
    db = http_request.state.db

    try:
        service = GoodsReceiptService(db)
        return service.list_goods_receipts(vendor_id, po_id, skip, limit)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get Goods Receipt By ID (includes related purchase order and invoices
# via eager-loaded relationships)
# ---------------------------------------------------------
@router.get("/{grn_id}", response_model=GoodsReceiptDTO)
def get_goods_receipt_by_id(grn_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = GoodsReceiptService(db)
        return service.get_goods_receipt(grn_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Update Goods Receipt
# ---------------------------------------------------------
@router.put("/{grn_id}", response_model=GoodsReceiptDTO)
def update_goods_receipt(
    grn_id: int,
    payload: GoodsReceiptUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = GoodsReceiptService(db)
        return service.update_goods_receipt(grn_id, payload, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to update goods receipt")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Delete Goods Receipt
# ---------------------------------------------------------
@router.delete("/{grn_id}", response_model=DeleteGoodsReceiptResponse)
def delete_goods_receipt(grn_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = GoodsReceiptService(db)
        service.delete_goods_receipt(grn_id, user_id)

        return DeleteGoodsReceiptResponse(message="Goods receipt deleted successfully")

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Goods receipt cannot be deleted because it is referenced by "
            "existing invoices",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# Goods Receipt Document
# ===========================================================


@router.post("/{grn_id}/document", response_model=UploadGoodsReceiptDocumentResponse)
async def upload_goods_receipt_document(
    grn_id: int,
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

        service = GoodsReceiptService(db)
        goods_receipt = service.upload_document(
            grn_id, file.filename, content, file.content_type, user_id
        )

        return UploadGoodsReceiptDocumentResponse(
            grn_id=goods_receipt.grn_id,
            file_path=goods_receipt.file_path,
            message="Goods receipt document uploaded successfully",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/{grn_id}/document/view")
# def view_goods_receipt_document(grn_id: int, http_request: Request):
@router.get("/{grn_id}/lines", response_model=list[GoodsReceiptLineDTO])
def get_goods_receipt_lines(grn_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = GoodsReceiptService(db)
        file_path = service.get_document_path(grn_id)

        return view_from_s3(file_path)

    except ValueError as e:
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{grn_id}/document/download")
def download_goods_receipt_document(grn_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = GoodsReceiptService(db)
        file_path = service.get_document_path(grn_id)

        return download_from_s3(file_path)

    except ValueError as e:
        status_code = 404 if str(e) == _NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))
        return service.get_lines(grn_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
