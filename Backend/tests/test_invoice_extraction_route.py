# Backend/tests/test_invoice_extraction_route.py
"""Route-level tests for POST /validate-fields (job creation) and
GET /validate-fields/{job_id}/status.

Same convention as test_new_routes.py: a minimal FastAPI app with
only this router mounted. run_validation_job is monkeypatched to a
no-op so these tests never touch a real DB or background thread -
the actual pipeline/Redis wiring is covered by
test_validation_progress.py. Redis is faked the same way as there:
redis_cache.py bound the name directly, so that's the patch target.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

import Backend.API_Layer.utils.redis_cache as redis_cache_module
import Backend.API_Layer.routes.invoice_extraction_route as route_module
import Backend.API_Layer.utils.validation_progress as vp
import Backend.API_Layer.utils.extraction_cache as extraction_cache_module
from Backend.API_Layer.routes import invoice_extraction_route


class FakeRedisClient:

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)
        return 1


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedisClient()
    monkeypatch.setattr(
        redis_cache_module, "get_redis_client", lambda: client
    )
    return client


class _FakeAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.user = {"user_id": "test-user"}
        return await call_next(request)


@pytest.fixture
def client(monkeypatch):
    # Never actually run the pipeline in these route tests - just
    # prove the route creates a job and returns immediately.
    monkeypatch.setattr(
        route_module, "run_validation_job", lambda *a, **k: None
    )

    app = FastAPI()
    app.add_middleware(_FakeAuthMiddleware)
    app.include_router(invoice_extraction_route.router)
    return TestClient(app)


MINIMAL_EXTRACTED_PAYLOAD = {
    "extracted_invoice": {
        "document": {},
        "vendor": {},
        "buyer": {},
        "reference": {},
        "amounts": {},
        "payment": {},
        "tax": {},
        "compliance": {},
        "invoice_lines": [],
        "extraction": {"status": "SUCCESS"},
        "validation": {"status": "READY_FOR_VALIDATION", "is_valid": True},
    },
    "file_path": "invoices/2026/08/test.pdf",
}


def test_post_validate_fields_returns_job_id_immediately(client, fake_redis):
    response = client.post("/validate-fields", json=MINIMAL_EXTRACTED_PAYLOAD)

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "QUEUED"
    assert body["job_id"].startswith("val_")

    # The route must have initialized the Redis record synchronously,
    # before returning - a poll immediately after POST must not race.
    job = vp.get_validation_status(body["job_id"])
    assert job is not None
    assert job["status"] == "QUEUED"
    assert set(job["stages"].keys()) == set(vp.STAGE_ORDER)


def test_get_status_unknown_job_returns_404(client, fake_redis):
    response = client.get("/validate-fields/val_doesnotexist/status")
    assert response.status_code == 404


def test_get_status_returns_current_job_state(client, fake_redis):
    post_response = client.post(
        "/validate-fields", json=MINIMAL_EXTRACTED_PAYLOAD
    )
    job_id = post_response.json()["job_id"]

    # Simulate the background job having made progress.
    vp.update_validation_stage(job_id, "extraction", "SUCCESS", duration_ms=1200)
    vp.update_validation_stage(job_id, "vendor", "RUNNING")

    status_response = client.get(f"/validate-fields/{job_id}/status")
    assert status_response.status_code == 200

    body = status_response.json()
    assert body["job_id"] == job_id
    assert body["status"] == "RUNNING"
    assert body["current_stage"] == "vendor"
    assert body["stages"]["extraction"]["status"] == "SUCCESS"
    assert body["stages"]["extraction"]["duration_ms"] == 1200
    assert body["stages"]["vendor"]["status"] == "RUNNING"
    assert body["stages"]["buyer"]["status"] == "WAITING"


def test_two_posts_create_independent_jobs(client, fake_redis):
    first = client.post("/validate-fields", json=MINIMAL_EXTRACTED_PAYLOAD).json()
    second = client.post("/validate-fields", json=MINIMAL_EXTRACTED_PAYLOAD).json()

    assert first["job_id"] != second["job_id"]

    vp.update_validation_stage(first["job_id"], "extraction", "SUCCESS")

    first_status = client.get(f"/validate-fields/{first['job_id']}/status").json()
    second_status = client.get(f"/validate-fields/{second['job_id']}/status").json()

    assert first_status["stages"]["extraction"]["status"] == "SUCCESS"
    assert second_status["stages"]["extraction"]["status"] == "WAITING"


# ---------------------------------------------------------------------------
# extraction_id: /validate-fields loading from the cache, and the new
# GET/PATCH/POST correction endpoints (see extraction_cache.py).
# ---------------------------------------------------------------------------


def _seed_extraction(fake_redis):
    extraction_id = extraction_cache_module.new_extraction_id()
    extraction_cache_module.init_extraction_cache(
        extraction_id,
        MINIMAL_EXTRACTED_PAYLOAD["extracted_invoice"],
        MINIMAL_EXTRACTED_PAYLOAD["file_path"],
    )
    return extraction_id


def test_validate_fields_accepts_extraction_id(client, fake_redis):
    extraction_id = _seed_extraction(fake_redis)

    response = client.post(
        "/validate-fields", json={"extraction_id": extraction_id}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "QUEUED"

    job = vp.get_validation_status(body["job_id"])
    assert job is not None


def test_validate_fields_unknown_extraction_id_returns_404(client, fake_redis):
    response = client.post(
        "/validate-fields", json={"extraction_id": "ext_doesnotexist"}
    )
    assert response.status_code == 404


def test_validate_fields_empty_body_returns_400(client, fake_redis):
    response = client.post("/validate-fields", json={})
    assert response.status_code == 400


def test_get_extraction_returns_cached_state(client, fake_redis):
    extraction_id = _seed_extraction(fake_redis)

    response = client.get(f"/extract-fields/{extraction_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["extraction_id"] == extraction_id
    assert body["corrections"] == []
    assert body["vendor_confirmed"] is False
    assert body["buyer_confirmed"] is False


def test_get_extraction_unknown_id_returns_404(client, fake_redis):
    response = client.get("/extract-fields/ext_doesnotexist")
    assert response.status_code == 404


def test_correct_vendor_persists_and_reflects_on_get(client, fake_redis):
    extraction_id = _seed_extraction(fake_redis)

    patch_response = client.patch(
        f"/extract-fields/{extraction_id}/vendor",
        json={"gstin": "27AABCU9603R1ZQ"},
    )

    assert patch_response.status_code == 200
    patch_body = patch_response.json()
    assert patch_body["updated"]["gstin"] == "27AABCU9603R1ZQ"
    assert len(patch_body["corrections"]) == 1
    assert patch_body["corrections"][0]["field"] == "vendor.gstin"
    assert patch_body["corrections"][0]["corrected_by"] == "test-user"

    get_response = client.get(f"/extract-fields/{extraction_id}")
    assert (
        get_response.json()["extracted_invoice"]["vendor"]["gstin"]
        == "27AABCU9603R1ZQ"
    )


def test_correct_buyer_unknown_extraction_id_returns_404(client, fake_redis):
    response = client.patch(
        "/extract-fields/ext_doesnotexist/buyer",
        json={"name": "New Buyer Name"},
    )
    assert response.status_code == 404


def test_confirm_section_marks_confirmed(client, fake_redis):
    extraction_id = _seed_extraction(fake_redis)

    response = client.post(
        f"/extract-fields/{extraction_id}/confirm",
        json={"section": "vendor"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["vendor_confirmed"] is True
    assert body["buyer_confirmed"] is False


def test_confirm_section_invalid_section_returns_400(client, fake_redis):
    extraction_id = _seed_extraction(fake_redis)

    response = client.post(
        f"/extract-fields/{extraction_id}/confirm",
        json={"section": "not-a-section"},
    )
    assert response.status_code == 400


def test_validate_fields_bare_body_still_works(client, fake_redis):
    """Regression guard: the original bare
    {"extracted_invoice":..., "file_path":...} body (no extraction_id,
    no "extracted_data" wrapper) must keep working unchanged."""

    response = client.post("/validate-fields", json=MINIMAL_EXTRACTED_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "QUEUED"
