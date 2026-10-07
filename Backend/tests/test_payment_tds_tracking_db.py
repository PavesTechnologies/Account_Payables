# Backend/tests/test_payment_tds_tracking_db.py
"""Payment Management (record payment, partial/full, history, receipts) and
TDS Tracking (deduction -> deposit -> filing, documents) against the REAL
configured database, isolated by the savepoint `db` fixture from
test_tds_config_service_db.py (outer transaction always rolled back). S3 is
monkeypatched - no real upload happens.
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import payment_route, tds_tracking_route
from Backend.API_Layer.utils import s3_utils
from Backend.Business_Layer.services.payment_tracking_service import PaymentNotFoundError, PaymentTrackingService
from Backend.Business_Layer.services.tds_tracking_service import TdsTrackingNotFoundError, TdsTrackingService
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.tds import InvoiceTds, TdsPaymentNature
from Backend.tests.test_tds_config_service_db import db, tag  # noqa: F401 - fixtures

USER = "test-suite"
VENDOR_ID = 15
TODAY = datetime.date.today()


def _status_id(db, code):
    return db.query(StatusMaster).filter(StatusMaster.module_name == "INVOICE", StatusMaster.status_code == code).one().status_id


def _invoice(db, tag, status="READY_FOR_PAYMENT", net="100000.00", tds_amount="10000.00",
             determination_status="VERIFIED", tds_applicable=True):
    invoice = Invoice(
        invoice_number=f"{tag}-{uuid.uuid4().hex[:6]}", vendor_id=VENDOR_ID, invoice_type="NON_PO",
        invoice_date=TODAY - datetime.timedelta(days=30), due_date=TODAY - datetime.timedelta(days=1),
        currency_id=1, gross_amount=Decimal(net), discount_amount=Decimal("0"), tax_amount=Decimal("0"),
        net_amount=Decimal(net), amount_paid=Decimal("0"), status_id=_status_id(db, status), created_by=USER,
    )
    db.add(invoice)
    db.flush()
    nature = db.query(TdsPaymentNature).order_by(TdsPaymentNature.id).first()
    db.add(InvoiceTds(
        invoice_id=invoice.invoice_id, tds_applicable=tds_applicable, payment_nature_id=nature.id,
        taxable_base=Decimal(net), tds_rate=Decimal("10.0000") if tds_applicable else None,
        tds_amount=Decimal(tds_amount) if tds_applicable else None, determination_status=determination_status,
        rule_snapshot={"rule_code": "1027", "old_section": "194J", "new_section": "393(1) Table 6(iii).D(b)"},
    ))
    db.commit()  # savepoint release only
    return invoice


def _pay(amount, reference, mode="NEFT", date=None, remarks=None):
    return SimpleNamespace(payment_date=date or TODAY, amount=Decimal(amount), payment_mode=mode,
                           reference_number=reference, remarks=remarks)


@pytest.fixture
def fake_s3(monkeypatch):
    uploads = []

    def _upload(filename, content, content_type=None, prefix="invoices/", key=None):
        uploads.append((prefix, filename, len(content)))
        return {"filepath": f"{prefix}test/{filename}"}

    monkeypatch.setattr(s3_utils, "upload_to_s3", _upload)
    return uploads


# =========================================================
# Payment Management
# =========================================================

def test_ready_for_payment_lists_server_computed_amounts(db, tag):
    invoice = _invoice(db, tag)
    page = PaymentTrackingService(db).list_ready_for_payment(search=tag)
    assert page["total"] == 1 and page["page"] == 1
    row = page["items"][0]
    assert row["invoice_id"] == invoice.invoice_id
    assert (row["invoice_amount"], row["tds_amount"], row["net_payable"], row["amount_paid"], row["remaining_amount"]) == (
        Decimal("100000.00"), Decimal("10000.00"), Decimal("90000.00"), Decimal("0.00"), Decimal("90000.00"))
    assert row["status_code"] == "READY_FOR_PAYMENT" and row["is_overdue"] is True
    assert row["vendor_name"] and row["currency_code"] == "INR"


def test_partial_then_full_payment_and_history(db, tag):
    invoice = _invoice(db, tag)
    svc = PaymentTrackingService(db)

    first = svc.record_payment(invoice.invoice_id, _pay("50000", "UTR0000000000001", remarks="first part"), USER)
    assert first["status_code"] == "PARTIALLY_PAID"
    assert (first["amount_paid"], first["remaining_amount"]) == (Decimal("50000.00"), Decimal("40000.00"))
    assert first["recorded_payment_id"] == first["payments"][0]["payment_id"]
    assert first["payments"][0]["status_code"] == "CLEARED" and first["payments"][0]["remarks"] == "first part"

    with pytest.raises(ValueError, match="exceeds the remaining payable amount 40000.00"):
        svc.record_payment(invoice.invoice_id, _pay("40000.01", "UTR0000000000002"), USER)

    # still listed as payable while partially paid
    assert svc.list_ready_for_payment(search=tag)["items"][0]["status_code"] == "PARTIALLY_PAID"

    final = svc.record_payment(invoice.invoice_id, _pay("40000", "UTR0000000000002", mode="RTGS"), USER)
    assert final["status_code"] == "PAID" and final["remaining_amount"] == Decimal("0.00")
    assert final["can_record_payment"] is False
    assert [p["amount"] for p in final["payments"]] == [Decimal("50000.00"), Decimal("40000.00")]
    assert svc.list_ready_for_payment(search=tag)["total"] == 0

    history = svc.list_payment_history(search=tag)
    assert history["total"] == 1
    row = history["items"][0]
    assert row["payment_count"] == 2 and row["last_payment_reference"] == "UTR0000000000002" and row["last_payment_mode"] == "RTGS"
    assert svc.list_payment_history(search=tag, status="PARTIALLY_PAID")["total"] == 0
    assert svc.list_payment_history(search=tag, payment_mode="NEFT")["total"] == 1


@pytest.mark.parametrize("payload, message", [
    (_pay("100", "R1", date=TODAY + datetime.timedelta(days=1)), "cannot be in the future"),
    (_pay("0", "R1"), "greater than zero"),
    (_pay("10.001", "R1"), "at most 2 decimal places"),
    (_pay("100", "R1", mode="CASH"), "Payment Mode must be one of"),
    (_pay("100", "  "), "Reference is required"),
    (_pay("100", "bad;ref", mode="BANK_TRANSFER"), "may contain only"),
    (_pay("100", "UTR123"), "UTR Number for NEFT must be exactly 16 letters or digits"),
    (_pay("100", "UTR-000000000001", mode="RTGS"), "UTR Number for RTGS must be exactly 16"),
    (_pay("100", "12345678901", mode="IMPS"), "IMPS Reference Number for IMPS must be exactly 12 digits"),
    (_pay("100", "12345678901A", mode="UPI"), "UPI Transaction ID for UPI must be exactly 12 digits"),
    (_pay("100", "1234567", mode="CHEQUE"), "Cheque Number for Cheque must be exactly 6 digits"),
    (_pay("100", "١٢٣٤٥٦", mode="DEMAND_DRAFT"), "DD Number for Demand Draft must be exactly 6 digits"),
])
def test_record_payment_validation(db, tag, payload, message):
    invoice = _invoice(db, tag)
    with pytest.raises(ValueError, match=message):
        PaymentTrackingService(db).record_payment(invoice.invoice_id, payload, USER)


@pytest.mark.parametrize("mode, reference", [
    ("NEFT", "SBIN026280012345"), ("rtgs", "hdfcr52026100712"), ("IMPS", "628012345678"), ("UPI", "628012345678"),
    ("CHEQUE", "000123"), ("DEMAND_DRAFT", "456789"), ("BANK_TRANSFER", "TXN/2026-10/0042"),
])
def test_record_payment_accepts_valid_reference_per_mode(db, tag, mode, reference):
    invoice = _invoice(db, tag)
    detail = PaymentTrackingService(db).record_payment(invoice.invoice_id, _pay("100", reference, mode=mode), USER)
    assert detail["payments"][0]["reference_number"] == reference


def test_metadata_reference_patterns_match_validation():
    modes = {m["value"]: m for m in PaymentTrackingService.metadata()["payment_modes"]}
    assert modes["NEFT"]["reference_pattern"] == modes["RTGS"]["reference_pattern"] == "^[A-Za-z0-9]{16}$"
    assert modes["DEMAND_DRAFT"]["reference_pattern"] == "^[0-9]{6}$"
    assert modes["BANK_TRANSFER"]["reference_pattern"] is None


def test_duplicate_reference_on_same_invoice_rejected(db, tag):
    invoice = _invoice(db, tag)
    svc = PaymentTrackingService(db)
    svc.record_payment(invoice.invoice_id, _pay("100", "UTRDUP0000000001"), USER)
    with pytest.raises(ValueError, match="already recorded for this invoice"):
        svc.record_payment(invoice.invoice_id, _pay("100", "utrdup0000000001"), USER)


def test_payment_blocked_for_non_payable_invoice_and_unverified_tds(db, tag):
    svc = PaymentTrackingService(db)
    approved = _invoice(db, tag, status="APPROVED")
    with pytest.raises(ValueError, match="only Ready for Payment / Partially Paid"):
        svc.record_payment(approved.invoice_id, _pay("100", "R1"), USER)
    unverified = _invoice(db, tag, determination_status="DETERMINED")
    with pytest.raises(ValueError, match="cannot be paid: TDS has not been verified"):
        svc.record_payment(unverified.invoice_id, _pay("100", "R1"), USER)
    with pytest.raises(PaymentNotFoundError):
        svc.record_payment(999999999, _pay("100", "R1"), USER)


def test_receipt_upload_and_listing(db, tag, fake_s3):
    invoice = _invoice(db, tag)
    svc = PaymentTrackingService(db)
    payment_id = svc.record_payment(invoice.invoice_id, _pay("1000", "UTRRECEIPT000001"), USER)["recorded_payment_id"]

    doc = svc.upload_document(payment_id, "receipt.pdf", b"%PDF-1.4 test", "application/pdf", "receipt", USER)
    assert doc["document_type"] == "RECEIPT" and doc["file_size"] == 13
    assert fake_s3 == [("payments/", "receipt.pdf", 13)]
    assert svc.get_document(payment_id, doc["id"]).file_path == "payments/test/receipt.pdf"

    detail = svc.get_invoice_payments(invoice.invoice_id)
    assert detail["payments"][0]["documents"][0]["file_name"] == "receipt.pdf"
    assert svc.list_payment_history(search=tag)["items"][0]["receipt_count"] == 1
    with pytest.raises(ValueError, match="document_type must be one of"):
        svc.upload_document(payment_id, "x.pdf", b"x", "application/pdf", "CHALLAN", USER)


# =========================================================
# TDS Tracking
# =========================================================

class _D(SimpleNamespace):
    def __getattr__(self, name):  # missing optional fields -> None
        return None


def test_tds_list_includes_only_applicable_and_defaults_to_pending(db, tag):
    applicable = _invoice(db, tag)
    _invoice(db, tag, tds_applicable=False)
    page = TdsTrackingService(db).list_tds_invoices(search=tag)
    assert [r["invoice_id"] for r in page["items"]] == [applicable.invoice_id]
    row = page["items"][0]
    assert row["tds_tracking_status"] == "TDS_PENDING" and row["tds_amount"] == Decimal("10000.00")
    assert row["net_payable"] == Decimal("90000.00") and row["old_section"] == "194J" and row["rule_code"] == "1027"
    assert row["allowed_actions"] == ["RECORD_DEDUCTION"]
    assert TdsTrackingService(db).list_tds_invoices(search=tag, tds_status="TDS_FILED")["total"] == 0


def test_tds_workflow_deduction_deposit_filing(db, tag):
    invoice = _invoice(db, tag)
    svc = TdsTrackingService(db)
    d1 = TODAY - datetime.timedelta(days=20)

    with pytest.raises(ValueError, match="not allowed while TDS status is TDS Pending"):
        svc.record_filing(invoice.invoice_id, _D(filing_date=TODAY, filing_reference="ACK1"), USER)

    detail = svc.record_deduction(invoice.invoice_id, _D(deduction_date=d1, remarks="deducted at payment"), USER)
    assert detail["tds_tracking_status"] == "TDS_DEDUCTED" and detail["tracking"]["deduction_date"] == d1
    assert detail["allowed_actions"] == ["RECORD_DEDUCTION", "RECORD_DEPOSIT"]

    with pytest.raises(ValueError, match="cannot be before the deduction date"):
        svc.record_deposit(invoice.invoice_id, _D(challan_number="CH1", deposit_date=d1 - datetime.timedelta(days=1)), USER)
    with pytest.raises(ValueError, match="BSR Code must be 7 digits"):
        svc.record_deposit(invoice.invoice_id, _D(challan_number="CH1", deposit_date=d1, bsr_code="12"), USER)

    detail = svc.record_deposit(invoice.invoice_id, _D(challan_number="CH00123", bsr_code="0510308", deposit_date=d1 + datetime.timedelta(days=5)), USER)
    assert detail["tds_tracking_status"] == "TDS_DEPOSITED" and detail["tracking"]["bsr_code"] == "0510308"
    with pytest.raises(ValueError, match="not allowed while TDS status is TDS Deposited"):
        svc.record_deduction(invoice.invoice_id, _D(deduction_date=d1), USER)

    # correction of the current step is allowed
    detail = svc.record_deposit(invoice.invoice_id, _D(challan_number="CH00124", deposit_date=d1 + datetime.timedelta(days=5)), USER)
    assert detail["tracking"]["challan_number"] == "CH00124"

    detail = svc.record_filing(invoice.invoice_id, _D(filing_date=TODAY, filing_reference="ACK-26Q-001"), USER)
    assert detail["tds_tracking_status"] == "TDS_FILED" and detail["allowed_actions"] == ["RECORD_FILING"]
    actions = [a["action"] for a in detail["activity"]]
    assert actions == ["INVOICE_TDS_DEDUCTION_RECORDED", "INVOICE_TDS_DEPOSIT_RECORDED",
                       "INVOICE_TDS_DEPOSIT_RECORDED", "INVOICE_TDS_FILING_RECORDED"]
    assert detail["activity"][2]["new_values"]["correction"] is True
    # TDS amount/rate untouched
    assert detail["tds_amount"] == Decimal("10000.00") and detail["tds_rate"] == Decimal("10.0000")


@pytest.mark.parametrize("payload, message", [
    (_D(deduction_date=None), "Deduction Date is required"),
    (_D(deduction_date=TODAY + datetime.timedelta(days=1)), "cannot be in the future"),
    (_D(deduction_date=TODAY - datetime.timedelta(days=400)), "cannot be before the invoice date"),
])
def test_tds_deduction_validation(db, tag, payload, message):
    invoice = _invoice(db, tag)
    with pytest.raises(ValueError, match=message):
        TdsTrackingService(db).record_deduction(invoice.invoice_id, payload, USER)


def test_tds_activity_requires_verified_determination(db, tag):
    invoice = _invoice(db, tag, determination_status="DETERMINED")
    svc = TdsTrackingService(db)
    assert svc.list_tds_invoices(search=tag)["items"][0]["allowed_actions"] == []
    with pytest.raises(ValueError, match="must be verified"):
        svc.record_deduction(invoice.invoice_id, _D(deduction_date=TODAY), USER)
    not_applicable = _invoice(db, tag, tds_applicable=False)
    with pytest.raises(TdsTrackingNotFoundError):
        svc.get_tds_detail(not_applicable.invoice_id)


def test_tds_status_is_independent_of_invoice_payment_status(db, tag):
    invoice = _invoice(db, tag)
    PaymentTrackingService(db).record_payment(invoice.invoice_id, _pay("90000", "UTRFULL000000001"), USER)
    detail = TdsTrackingService(db).get_tds_detail(invoice.invoice_id)
    assert detail["invoice_status_code"] == "PAID" and detail["payment"]["remaining_amount"] == Decimal("0.00")
    assert detail["tds_tracking_status"] == "TDS_PENDING"
    assert PaymentTrackingService(db).get_invoice_payments(invoice.invoice_id)["tds_tracking_status"] == "TDS_PENDING"


def test_tds_document_upload(db, tag, fake_s3):
    invoice = _invoice(db, tag)
    svc = TdsTrackingService(db)
    doc = svc.upload_document(invoice.invoice_id, "challan.pdf", b"%PDF", "application/pdf", "challan", USER)
    assert doc["document_type"] == "CHALLAN" and fake_s3[0][0] == "tds/"
    detail = svc.get_tds_detail(invoice.invoice_id)
    assert detail["documents"][0]["file_name"] == "challan.pdf"
    assert detail["tds_tracking_status"] == "TDS_PENDING"  # a document alone does not advance the status
    assert detail["activity"][-1]["action"] == "INVOICE_TDS_DOCUMENT_UPLOADED"
    assert svc.get_document(invoice.invoice_id, doc["id"]).file_path == "tds/test/challan.pdf"


# =========================================================
# Routes: permissions + path ordering
# =========================================================

def _client(db, router, prefix, permissions):
    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": USER, "permissions": permissions}
            request.state.db = db
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(router, prefix=prefix)
    return TestClient(app)


def test_payment_routes_permissions_and_contract(db, tag):
    invoice = _invoice(db, tag)
    viewer = _client(db, payment_route.router, "/payment", ["PAYMENT_VIEW"])
    processor = _client(db, payment_route.router, "/payment", ["PAYMENT_PROCESS"])
    outsider = _client(db, payment_route.router, "/payment", ["INVOICE_VIEW"])
    body = {"payment_date": TODAY.isoformat(), "amount": "1000", "payment_mode": "NEFT", "reference_number": "UTRAPI0000000001"}

    assert viewer.get("/payment/metadata").json()["payment_modes"][0]["value"] == "NEFT"
    listing = viewer.get("/payment/ready-for-payment", params={"search": tag})
    assert listing.status_code == 200 and listing.json()["items"][0]["net_payable"] == "90000.00"
    assert viewer.get("/payment/history", params={"search": tag}).json()["total"] == 0  # not swallowed by /{payment_id}
    assert viewer.post(f"/payment/invoice/{invoice.invoice_id}/record", json=body).status_code == 403
    assert outsider.get("/payment/ready-for-payment").status_code == 403

    recorded = processor.post(f"/payment/invoice/{invoice.invoice_id}/record", json=body)
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["status_code"] == "PARTIALLY_PAID" and recorded.json()["remaining_amount"] == "89000.00"
    bad = processor.post(f"/payment/invoice/{invoice.invoice_id}/record", json={**body, "amount": "999999"})
    assert bad.status_code == 422 and "exceeds the remaining payable amount" in bad.json()["detail"]
    assert processor.get("/payment/invoice/999999999").status_code == 404


def test_tds_tracking_routes_permissions(db, tag):
    invoice = _invoice(db, tag)
    viewer = _client(db, tds_tracking_route.router, "/tds/tracking", ["TDS_TRACKING_VIEW"])
    updater = _client(db, tds_tracking_route.router, "/tds/tracking", ["TDS_TRACKING_UPDATE"])
    outsider = _client(db, tds_tracking_route.router, "/tds/tracking", ["PAYMENT_PROCESS", "INVOICE_TDS_VERIFY"])
    body = {"deduction_date": TODAY.isoformat()}

    assert viewer.get("/tds/tracking", params={"search": tag}).json()["items"][0]["tds_tracking_status"] == "TDS_PENDING"
    assert viewer.get(f"/tds/tracking/{invoice.invoice_id}").status_code == 200
    assert viewer.post(f"/tds/tracking/{invoice.invoice_id}/deduction", json=body).status_code == 403
    assert outsider.get("/tds/tracking").status_code == 403
    response = updater.post(f"/tds/tracking/{invoice.invoice_id}/deduction", json=body)
    assert response.status_code == 200 and response.json()["tds_tracking_status"] == "TDS_DEDUCTED"
    assert updater.post(f"/tds/tracking/{invoice.invoice_id}/filing",
                        json={"filing_date": TODAY.isoformat(), "filing_reference": "A"}).status_code == 422
    assert viewer.get("/tds/tracking/metadata").json()["tracking_statuses"][0]["value"] == "TDS_PENDING"
