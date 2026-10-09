"""Backend permission gates on vendor / vendor-intake / PO / GRN routes
(Backend/API_Layer/utils/vendor_permissions.py). Services are monkeypatched - only the
authorization layer is under test: who gets 403 and who reaches the handler."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import goods_receipt_route, purchase_order_route, vendor_intake_route, vendor_route
from Backend.API_Layer.utils import vendor_permissions as vp


def _client(permissions):
    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u-1", "permissions": permissions}
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)
    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(vendor_route.router, prefix="/vendor")
    app.include_router(vendor_intake_route.router, prefix="/vendor-intake")
    app.include_router(purchase_order_route.router, prefix="/purchase-order")
    app.include_router(goods_receipt_route.router, prefix="/goods-receipt")
    return TestClient(app, raise_server_exceptions=False)


def _passed(response):
    """Got past the permission gate (the handler itself may then 404/422/500 against fakes)."""
    return response.status_code != 403


BANK = {"bank_name": "X", "account_number": "1", "ifsc_code": "HDFC0000001", "account_holder_name": "A"}


@pytest.mark.parametrize("call", [
    lambda c: c.get("/vendor"), lambda c: c.get("/vendor/1"), lambda c: c.get("/vendor/1/purchase-orders"),
    lambda c: c.put("/vendor/1", json={}), lambda c: c.post("/vendor/1/banks", json=BANK),
    lambda c: c.get("/vendor-intake/1"), lambda c: c.post("/vendor-intake/1/pre-screen"),
    lambda c: c.get("/purchase-order"), lambda c: c.post("/goods-receipt", json={}),
])
def test_no_permission_is_403_everywhere(call):
    assert call(_client([])).status_code == 403


def test_vendor_view_reads_but_cannot_write():
    client = _client([vp.VENDOR_VIEW])
    assert _passed(client.get("/vendor/1/ndas"))
    assert client.put("/vendor/1", json={"vendor_name": "X"}).status_code == 403
    assert client.patch("/vendor/1/status", json={"is_active": False}).status_code == 403


def test_bank_changes_need_the_dedicated_permission():
    assert _client([vp.VENDOR_MANAGE]).post("/vendor/1/banks", json=BANK).status_code == 403
    assert _client([vp.VENDOR_MANAGE]).delete("/vendor/1/banks/2").status_code == 403
    assert _passed(_client([vp.VENDOR_BANK_MANAGE]).delete("/vendor/1/banks/2"))


def test_other_modules_keep_their_vendor_reads():
    # invoice OCR review / payments vendor picker
    assert _passed(_client(["INVOICE_VIEW"]).get("/vendor"))
    assert _client(["INVOICE_VIEW"]).get("/vendor/1/documents").status_code == 403
    # mark-as-paid reads the vendor's banks from the detail
    assert _passed(_client(["PAYMENT_PROCESS"]).get("/vendor/1"))
    # procurement PO tab / detail
    assert _passed(_client(["PO_VIEW"]).get("/purchase-order"))
    assert _passed(_client(["PO_VIEW"]).get("/purchase-order/1"))
    assert _client(["PO_VIEW"]).delete("/purchase-order/1").status_code == 403
    # onboarding-request flow runs intake steps
    assert _passed(_client(["ONBOARDING_PROCESS"]).post("/vendor-intake/1/pre-screen"))


def test_vendor_manage_covers_intake_po_and_grn_records():
    client = _client([vp.VENDOR_MANAGE])
    assert _passed(client.put("/vendor-intake/1", json={}))
    assert _passed(client.post("/purchase-order", json={}))
    assert _passed(client.delete("/goods-receipt/1"))
