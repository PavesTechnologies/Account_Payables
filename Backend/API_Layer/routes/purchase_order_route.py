# Backend/API_Layer/routes/purchase_order_route.py
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from Backend.API_Layer.interface.purchase_order_interface import (
    PurchaseOrderDTO,
    PurchaseOrderLineDTO,
)
from Backend.Business_Layer.services.purchase_order_service import PurchaseOrderService

router = APIRouter()


@router.get("", response_model=list[PurchaseOrderDTO])
def get_all_purchase_orders(
    http_request: Request,
    vendor_id: Optional[int] = None,
    status_id: Optional[int] = None,
    po_number: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    db = http_request.state.db

    try:
        service = PurchaseOrderService(db)
        return service.list_purchase_orders(vendor_id, status_id, po_number, skip, limit)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/number/{po_number}", response_model=PurchaseOrderDTO)
def get_purchase_order_by_number(po_number: str, http_request: Request):
    db = http_request.state.db

    try:
        service = PurchaseOrderService(db)
        return service.get_purchase_order_by_number(po_number)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/{po_id}/lines", response_model=list[PurchaseOrderLineDTO])
def get_purchase_order_lines(po_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = PurchaseOrderService(db)
        return service.get_lines(po_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
