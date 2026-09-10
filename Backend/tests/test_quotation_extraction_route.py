# Backend/tests/test_quotation_extraction_route.py
"""Integration tests for POST /quotations/extract.

Follows the project's existing route-test convention (see
test_procurement_authorization.py / test_invoice_extraction_route.py):
a minimal FastAPI app with only procurement_route mounted, a fake
auth+db middleware, and the AWS-touching pieces (S3 upload, Textract
extraction, vendor DB lookup) monkeypatched so these tests exercise
the real route -> service -> normalization/message wiring without any
real network/DB dependency.
"""
from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

import Backend.Business_Layer.services.quotation_extraction_service as service_module
from Backend.API_Layer.routes import procurement_route
from Backend.Business_Layer.utils.exceptions import (
    QuotationExtractionFailure,
    TextractServiceError,
)
from Backend.Business_Layer.utils.quotation_vendor_matcher import VendorMatchResult


PROCUREMENT_OFFICER_PERMISSIONS = ["QUOTATION_CREATE"]


def _make_middleware(user):
    class _FakeAuthAndDBMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if user is not None:
                request.state.user = user
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    return _FakeAuthAndDBMiddleware


def _make_client(user):
    app = FastAPI()
    app.add_middleware(_make_middleware(user))
    app.include_router(procurement_route.router)
    return TestClient(app)


def _user(permissions):
    return {"user_id": "test-user", "permissions": permissions}


FULL_EXTRACTED_FIELDS = {
    "vendor_name": "ABC Technologies Pvt Ltd",
    "quotation_number": "QT-2026-00125",
    "total_amount": 125000.00,
    "quotation_date": "2026-09-09",
    "valid_until": "2026-09-30",
    "delivery_days": 15,
    "payment_terms": "Net 30",
}


def _upload_file(name="quotation.pdf", content=b"%PDF-1.4 fake", content_type="application/pdf"):
    return {"file": (name, io.BytesIO(content), content_type)}


@pytest.fixture(autouse=True)
def _patch_s3_upload(monkeypatch):
    monkeypatch.setattr(
        procurement_route,
        "upload_to_s3",
        lambda filename, content, content_type: {"filepath": "quotations/2026/09/test.pdf"},
    )


def _patch_extraction(monkeypatch, extracted, confidence=None):
    async def fake_extract_quotation_from_s3(s3_key):
        return dict(extracted), dict(confidence or {})

    monkeypatch.setattr(
        service_module, "extract_quotation_from_s3", fake_extract_quotation_from_s3
    )


def _patch_extraction_raises(monkeypatch, exc):
    async def fake_extract_quotation_from_s3(s3_key):
        raise exc

    monkeypatch.setattr(
        service_module, "extract_quotation_from_s3", fake_extract_quotation_from_s3
    )


def _patch_vendor_match(monkeypatch, result: VendorMatchResult):
    monkeypatch.setattr(service_module, "match_vendor", lambda name, db: result)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_extract_quotation_full_success(monkeypatch):
    _patch_extraction(monkeypatch, FULL_EXTRACTED_FIELDS)
    _patch_vendor_match(
        monkeypatch,
        VendorMatchResult(vendor_id=12, vendor_name="ABC Technologies Pvt Ltd", confidence=100.0),
    )

    client = _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(),
    )

    assert response.status_code == 200
    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Quotation details extracted successfully"
    assert body["data"]["vendor_id"] == 12
    assert body["data"]["vendor_name"] == "ABC Technologies Pvt Ltd"
    assert body["data"]["quotation_number"] == "QT-2026-00125"
    assert float(body["data"]["total_amount"]) == 125000.0
    assert body["data"]["quotation_date"] == "2026-09-09"
    assert body["data"]["valid_until"] == "2026-09-30"
    assert body["data"]["delivery_days"] == 15
    assert body["data"]["payment_terms"] == "Net 30"


# ---------------------------------------------------------------------------
# Partial extraction
# ---------------------------------------------------------------------------


def test_extract_quotation_partial_extraction(monkeypatch):
    partial_fields = dict(FULL_EXTRACTED_FIELDS)
    partial_fields["quotation_date"] = None
    partial_fields["valid_until"] = None
    partial_fields["payment_terms"] = None

    _patch_extraction(monkeypatch, partial_fields)
    _patch_vendor_match(
        monkeypatch,
        VendorMatchResult(vendor_id=None, vendor_name="ABC Technologies Pvt Ltd", confidence=0.0),
    )

    client = _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(),
    )

    assert response.status_code == 200
    body = response.json()

    assert body["message"] == "Quotation partially extracted"
    assert body["data"]["vendor_id"] is None
    assert body["data"]["quotation_date"] is None
    assert body["data"]["payment_terms"] is None
    assert body["data"]["quotation_number"] == "QT-2026-00125"


# ---------------------------------------------------------------------------
# Vendor matched / unmatched
# ---------------------------------------------------------------------------


def test_extract_quotation_vendor_unmatched_still_returns_name(monkeypatch):
    _patch_extraction(monkeypatch, FULL_EXTRACTED_FIELDS)
    _patch_vendor_match(
        monkeypatch,
        VendorMatchResult(
            vendor_id=None,
            vendor_name="ABC Technologies Private Limited",
            confidence=0.0,
        ),
    )

    client = _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(),
    )

    assert response.status_code == 200
    body = response.json()

    assert body["data"]["vendor_id"] is None
    assert body["data"]["vendor_name"] == "ABC Technologies Private Limited"


# ---------------------------------------------------------------------------
# Invalid document
# ---------------------------------------------------------------------------


def test_extract_quotation_invalid_file_type_returns_400():
    client = _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(
            name="quotation.txt", content=b"not a real document", content_type="text/plain"
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid quotation document"


def test_extract_quotation_empty_file_returns_400():
    client = _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(content=b""),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid quotation document"


# ---------------------------------------------------------------------------
# Extraction failure (nothing found) -> 422
# ---------------------------------------------------------------------------


def test_extract_quotation_no_fields_found_returns_422(monkeypatch):
    _patch_extraction(monkeypatch, {})

    client = _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(),
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Unable to extract quotation details from the document"
    )


# ---------------------------------------------------------------------------
# Textract/AWS failure -> 502
# ---------------------------------------------------------------------------


def test_extract_quotation_textract_failure_returns_502(monkeypatch):
    _patch_extraction_raises(monkeypatch, TextractServiceError("AWS Textract error: boom"))

    client = _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(),
    )

    assert response.status_code == 502
    assert (
        response.json()["detail"]
        == "Quotation document extraction service is temporarily unavailable"
    )


# ---------------------------------------------------------------------------
# Unexpected error -> 500
# ---------------------------------------------------------------------------


def test_extract_quotation_unexpected_error_returns_500(monkeypatch):
    _patch_extraction_raises(monkeypatch, RuntimeError("boom - unrelated bug"))

    client = _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(),
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to process quotation document"


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_extract_quotation_requires_authentication():
    client = _make_client(None)
    response = client.post(
        "/quotations/extract",
        files=_upload_file(),
    )

    assert response.status_code == 401


def test_extract_quotation_requires_quotation_create_permission():
    client = _make_client(_user(["PR_VIEW"]))
    response = client.post(
        "/quotations/extract",
        files=_upload_file(),
    )

    assert response.status_code == 403
