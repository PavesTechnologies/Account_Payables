# Backend/tests/test_process_invoice_route.py
"""Route-level tests for /process-invoice and the OCR-review endpoint.

Runs a minimal FastAPI app containing only invoice_process_route's
router, with a lightweight stand-in for JWTMiddleware/DBSessionMiddleware
(the real ones need a live UMS/JWKS endpoint and a live DB — out of scope
for a route unit test). Every Business_Layer.services.invoice_process_service
function the route calls is monkeypatched, so these tests only verify the
route's own logic: validation ordering, exception-to-HTTP-status mapping,
and response shape.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import invoice_process_route
from Backend.API_Layer.interface.invoice_process_interface import (
    ConfidenceResult,
    DocumentResult,
    ExtractedInvoice,
    FinalResponse,
    ValidationResult,
    VendorMatch,
)
from Backend.Business_Layer.services.invoice_process_service import PersistenceOutcome
from Backend.Business_Layer.utils import invoice_status
from Backend.Business_Layer.utils.exceptions import DuplicateInvoiceError, OCRFailure


class _FakeAuthAndDBMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.user = {"user_id": "test-user"}
        request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
        return await call_next(request)


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(_FakeAuthAndDBMiddleware)
    app.include_router(invoice_process_route.router)
    return TestClient(app)


def _pdf_file(name="invoice.pdf", content=b"%PDF-1.4 fake"):
    return {"file": (name, content, "application/pdf")}


def _fake_final_response() -> FinalResponse:
    extracted = ExtractedInvoice(
        invoice_number="INV-1",
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 1, 31),
        subtotal=Decimal("1000.00"),
        total=Decimal("1180.00"),
        currency="INR",
    )
    return FinalResponse(
        document=DocumentResult(source_filename="invoice.pdf", page_count=1, pages=[]),
        extracted_invoice=extracted,
        validation=ValidationResult(valid=True, errors=[]),
        vendor_match=VendorMatch(matched=True, vendor_id=42, confidence=100.0),
        confidence=ConfidenceResult(
            ocr_confidence=95, extraction_confidence=95, validation_confidence=100,
            vendor_confidence=100, overall_confidence=95,
        ),
    )


def _fake_inbound_document():
    return SimpleNamespace(inbound_document_id=1, file_name="invoice.pdf", file_path="invoices/2026/01/x.pdf")


def test_process_invoice_happy_path(client, monkeypatch):
    monkeypatch.setattr(invoice_process_route, "upload_to_s3", lambda *a, **k: {
        "status": "success", "filename": "invoice.pdf", "filepath": "invoices/2026/01/x.pdf",
    })
    monkeypatch.setattr(invoice_process_route.service, "create_pending_inbound_document", lambda *a, **k: _fake_inbound_document())
    monkeypatch.setattr(invoice_process_route.service, "process_invoice", lambda *a, **k: _fake_final_response())
    monkeypatch.setattr(
        invoice_process_route.service, "persist_processed_invoice",
        lambda *a, **k: PersistenceOutcome(inbound_document_id=1, invoice_id=10, invoice_status=invoice_status.STATUS_CODE_OCR_REVIEW_PENDING),
    )

    response = client.post("/process-invoice", files=_pdf_file())

    assert response.status_code == 200
    body = response.json()
    assert body["invoice_id"] == 10
    assert body["inbound_document_id"] == 1
    assert body["invoice_status"] == invoice_status.STATUS_CODE_OCR_REVIEW_PENDING


def test_process_invoice_rejects_unsupported_extension(client):
    response = client.post("/process-invoice", files={"file": ("invoice.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_process_invoice_rejects_empty_file(client):
    response = client.post("/process-invoice", files={"file": ("invoice.pdf", b"", "application/pdf")})
    assert response.status_code == 400


def test_process_invoice_ocr_failure_maps_to_422(client, monkeypatch):
    monkeypatch.setattr(invoice_process_route, "upload_to_s3", lambda *a, **k: {
        "status": "success", "filename": "invoice.pdf", "filepath": "invoices/2026/01/x.pdf",
    })
    monkeypatch.setattr(invoice_process_route.service, "create_pending_inbound_document", lambda *a, **k: _fake_inbound_document())

    def _raise_ocr_failure(*a, **k):
        raise OCRFailure("no text could be extracted")

    monkeypatch.setattr(invoice_process_route.service, "process_invoice", _raise_ocr_failure)
    monkeypatch.setattr(invoice_process_route.service, "mark_inbound_document_failed", lambda *a, **k: None)

    response = client.post("/process-invoice", files=_pdf_file())
    assert response.status_code == 422


def test_process_invoice_duplicate_maps_to_409(client, monkeypatch):
    monkeypatch.setattr(invoice_process_route, "upload_to_s3", lambda *a, **k: {
        "status": "success", "filename": "invoice.pdf", "filepath": "invoices/2026/01/x.pdf",
    })
    monkeypatch.setattr(invoice_process_route.service, "create_pending_inbound_document", lambda *a, **k: _fake_inbound_document())
    monkeypatch.setattr(invoice_process_route.service, "process_invoice", lambda *a, **k: _fake_final_response())

    def _raise_duplicate(*a, **k):
        raise DuplicateInvoiceError("Invoice 'INV-1' already exists for vendor 42")

    monkeypatch.setattr(invoice_process_route.service, "persist_processed_invoice", _raise_duplicate)

    response = client.post("/process-invoice", files=_pdf_file())
    assert response.status_code == 409


def test_ocr_review_success(client, monkeypatch):
    fake_invoice = SimpleNamespace(invoice_id=10, status_id=8)
    monkeypatch.setattr(invoice_process_route.service, "apply_ocr_review", lambda *a, **k: fake_invoice)

    response = client.patch("/inbound-documents/1/ocr-review", json={"invoice_number": "INV-1-CORRECTED"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["invoice_id"] == 10


def test_ocr_review_missing_vendor_maps_to_422(client, monkeypatch):
    def _raise_value_error(*a, **k):
        raise ValueError("vendor_id is required: this document's vendor was not auto-matched")

    monkeypatch.setattr(invoice_process_route.service, "apply_ocr_review", _raise_value_error)

    response = client.patch("/inbound-documents/1/ocr-review", json={"invoice_number": "INV-1"})
    assert response.status_code == 422
