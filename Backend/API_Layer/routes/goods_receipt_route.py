# Backend/API_Layer/routes/goods_receipt_route.py
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


@router.get("/{grn_id}/lines", response_model=list[GoodsReceiptLineDTO])
def get_goods_receipt_lines(grn_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = GoodsReceiptService(db)
        return service.get_lines(grn_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
