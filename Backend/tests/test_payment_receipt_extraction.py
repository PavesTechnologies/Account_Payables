"""Payment receipt auto-fill (Phase 4): field parsing, warnings, the read-only route and the audit
entry mode. Textract / S3 / DB are faked."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import payment_route
from Backend.API_Layer.utils import receipt_extraction_fields as rx
from Backend.Business_Layer.services import payment_receipt_extraction_service as svc


def _q(value, confidence=95.0):
    return {"value": value, "confidence": confidence}


NEFT_RESULTS = {
    "PAYMENT_DATE": _q("08-Oct-2026"),
    "AMOUNT": _q("INR 1,18,000.00"),
    "UTR": _q("SBIN426281234567"),
    "MODE": _q("NEFT"),
    "BENEFICIARY_NAME": _q("ACME SUPPLIES PVT LTD"),
    "BENEFICIARY_ACCOUNT": _q("50200012345678"),
    "BENEFICIARY_IFSC": _q("HDFC 0001234"),
    "STATUS": _q("Transaction Successful"),
}


# ======================================================================
# Parsing
# ======================================================================
def test_parse_neft_advice():
    out = rx.parse_receipt_fields(NEFT_RESULTS, "Funds transfer advice NEFT")
    f = out["fields"]
    assert f["payment_date"]["value"] == "2026-10-08" and f["amount"]["value"] == "118000.00"
    assert f["payment_mode"]["value"] == "NEFT" and f["reference_number"]["value"] == "SBIN426281234567"
    assert out["beneficiary_account_masked"] == "XXXX5678" and out["beneficiary_ifsc"] == "HDFC0001234"
    assert out["transaction_status"] == "SUCCESS"


def test_parse_falls_back_to_page_text_for_mode_and_reference():
    out = rx.parse_receipt_fields({"AMOUNT": _q("Rs. 5,900")}, "IMPS transfer ... RRN: 628112345678 ... amount paid")
    assert out["fields"]["payment_mode"]["value"] == "IMPS"
    assert out["fields"]["reference_number"]["value"] == "628112345678"
    assert out["fields"]["amount"]["value"] == "5900.00"
    assert out["transaction_status"] is None  # "paid" in body text is not a status


def test_cheque_number_and_failed_status():
    out = rx.parse_receipt_fields({"MODE": _q("Cheque"), "CHEQUE_NUMBER": _q("004521"), "STATUS": _q("Returned unpaid")}, "")
    assert out["fields"]["reference_number"]["value"] == "004521" and out["transaction_status"] == "FAILED"
    assert rx.parse_receipt_fields({}, "This transaction was REVERSED")["transaction_status"] == "FAILED"


@pytest.mark.parametrize("text,expected", [("₹ 12,34,567.50", Decimal("1234567.50")), ("INR 0", None), ("abc", None), ("1500", Decimal("1500.00"))])
def test_parse_amount(text, expected):
    assert rx.parse_amount(text) == expected


def test_names_look_alike():
    assert svc.names_look_alike("ACME SUPPLIES PVT LTD", "Acme Supplies Private Limited")
    assert svc.names_look_alike("Skyline Realty", "[TEST] Skyline Realty LLP")
    assert not svc.names_look_alike("Zeta Traders", "Acme Supplies Pvt Ltd")


# ======================================================================
# Warnings
# ======================================================================
@pytest.fixture
def service(monkeypatch):
    state = SimpleNamespace(remaining=Decimal("118000.00"), uses=[])

    class Tracking:
        def __init__(self, db):
            pass

        def get_invoice_payments(self, invoice_id):
            return {"remaining_amount": state.remaining, "vendor_name": "Acme Supplies Pvt Ltd",
                    "invoice_date": datetime.date(2026, 10, 1)}
    monkeypatch.setattr(svc, "PaymentTrackingService", Tracking)
    s = svc.PaymentReceiptExtractionService(None, today=datetime.date(2026, 10, 10))
    monkeypatch.setattr(s, "_reference_uses", lambda ref, inv: state.uses)
    s.state = state
    return s


def _codes(result):
    return {w["code"] for w in result["warnings"]}


def test_clean_receipt_has_no_warnings(service):
    result = service.suggest(7, rx.parse_receipt_fields(NEFT_RESULTS, ""))
    assert result["warnings"] == [] and result["fields"]["amount"]["value"] == "118000.00"


def test_every_warning(service):
    results = {**NEFT_RESULTS, "PAYMENT_DATE": _q("12-Oct-2026"), "AMOUNT": _q("INR 2,00,000.00"),
               "BENEFICIARY_NAME": _q("Zeta Traders"), "STATUS": _q("Pending"), "UTR": _q("SBIN42628", 40.0)}
    service.state.uses = [(7, "INV-7"), (9, "INV-9")]
    codes = _codes(service.suggest(7, rx.parse_receipt_fields(results, "")))
    assert {"PENDING", "AMOUNT_ABOVE_REMAINING", "FUTURE_DATE", "BENEFICIARY_MISMATCH", "REFERENCE_ON_INVOICE",
            "REFERENCE_ELSEWHERE", "REFERENCE_FORMAT", "LOW_CONFIDENCE"} <= codes


def test_partial_and_before_invoice_and_missing(service):
    results = {"PAYMENT_DATE": _q("20-Sep-2026"), "AMOUNT": _q("INR 18,000")}
    result = service.suggest(7, rx.parse_receipt_fields(results, ""))
    assert {"PARTIAL", "BEFORE_INVOICE", "MISSING"} <= _codes(result)
    assert next(w for w in result["warnings"] if w["code"] == "PARTIAL")["message"].startswith("Partial payment - 100,000.00")


# ======================================================================
# Route: read-only, permission, temp S3 copy removed
# ======================================================================
def _client(permissions, monkeypatch, calls):
    async def fake_extract(key):
        calls.append(("extract", key))
        return rx.parse_receipt_fields(NEFT_RESULTS, "")

    class Tracking:
        def __init__(self, db):
            pass

        def get_invoice_payments(self, invoice_id):
            if invoice_id == 404:
                raise payment_route.PaymentNotFoundError("Invoice 404 not found")
            return {}

    class Suggest:
        def __init__(self, db):
            pass

        def suggest(self, invoice_id, extracted):
            return {"invoice_id": invoice_id, "fields": extracted["fields"], "warnings": []}

    monkeypatch.setattr(payment_route, "upload_to_s3", lambda filename, content, content_type=None, prefix="": calls.append(("upload", prefix)) or {"filepath": "payments/receipt-extraction/x.pdf"})
    monkeypatch.setattr(payment_route, "delete_from_s3", lambda key: calls.append(("delete", key)))
    monkeypatch.setattr(payment_route, "extract_receipt_from_s3", fake_extract)
    monkeypatch.setattr(payment_route, "PaymentTrackingService", Tracking)
    monkeypatch.setattr(payment_route, "PaymentReceiptExtractionService", Suggest)
    monkeypatch.setattr(payment_route, "validate_upload_file", lambda f, c: None)

    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u-1", "permissions": permissions}
            request.state.db = SimpleNamespace(rollback=lambda: None)
            return await call_next(request)
    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(payment_route.router, prefix="/payment")
    return TestClient(app)


def test_route(monkeypatch):
    calls = []
    files = {"file": ("advice.pdf", b"%PDF-1.4 receipt", "application/pdf")}
    assert _client(["PAYMENT_VIEW"], monkeypatch, calls).post("/payment/invoice/7/receipt/extract", files=files).status_code == 403
    client = _client(["PAYMENT_PROCESS"], monkeypatch, calls)
    res = client.post("/payment/invoice/7/receipt/extract", files=files)
    assert res.status_code == 200 and res.json()["fields"]["reference_number"]["value"] == "SBIN426281234567"
    assert [c[0] for c in calls] == ["upload", "extract", "delete"]
    assert client.post("/payment/invoice/404/receipt/extract", files=files).status_code == 404


def test_record_request_accepts_entry_mode():
    from Backend.API_Layer.interface.payment_interface import RecordPaymentRequest
    req = RecordPaymentRequest(payment_date="2026-10-08", amount="100", payment_mode="NEFT", reference_number="X",
                               entry_mode="RECEIPT_EXTRACTED", edited_fields=["amount"])
    assert req.entry_mode == "RECEIPT_EXTRACTED"
    with pytest.raises(Exception):
        RecordPaymentRequest(payment_date="2026-10-08", amount="100", payment_mode="NEFT", reference_number="X", entry_mode="ROBOT")
