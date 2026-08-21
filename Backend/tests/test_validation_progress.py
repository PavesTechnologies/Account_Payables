# Backend/tests/test_validation_progress.py
"""Unit tests for the Redis-backed validation-progress tracking
(Backend/API_Layer/utils/validation_progress.py) and its wiring into
InvoiceExtractionService.validate_invoice's job_id path.

Redis is faked with an in-memory dict-backed client (no real Redis
connection needed/used). redis_cache.py's module-level name binding
for get_redis_client is what actually needs patching - it imported
the function directly (`from ... import get_redis_client`), so the
name lives in redis_cache's own namespace, not redis_client's.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest

import Backend.API_Layer.utils.redis_cache as redis_cache_module
import Backend.API_Layer.utils.validation_progress as vp
from Backend.Business_Layer.services.invoice_extraction_service import (
    InvoiceExtractionService,
)
from Backend.API_Layer.interface.invoice_extraction_interface import (
    ExtractedInvoiceResponse,
    ExtractionMetadata,
    InvoiceAmounts,
    InvoiceBuyer,
    InvoiceCompliance,
    InvoiceDocument,
    InvoiceLine,
    InvoicePayment,
    InvoiceReference,
    InvoiceTax,
    InvoiceValidation,
    InvoiceVendor,
)


# ---------------------------------------------------------------------------
# Fake Redis client
# ---------------------------------------------------------------------------


class FakeRedisClient:

    def __init__(self):
        self.store: Dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def delete(self, key):
        existed = key in self.store
        self.store.pop(key, None)
        return 1 if existed else 0

    def ping(self):
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedisClient()
    monkeypatch.setattr(
        redis_cache_module, "get_redis_client", lambda: client
    )
    return client


@pytest.fixture
def no_redis(monkeypatch):
    """Simulates Redis being completely unreachable."""
    monkeypatch.setattr(
        redis_cache_module, "get_redis_client", lambda: None
    )


# ---------------------------------------------------------------------------
# 1. Job lifecycle basics
# ---------------------------------------------------------------------------


def test_init_creates_all_stages_waiting(fake_redis):
    job_id = "val_test001"
    vp.init_validation_job(job_id)

    job = vp.get_validation_status(job_id)

    assert job["job_id"] == job_id
    assert job["status"] == "QUEUED"
    assert job["current_stage"] is None
    assert set(job["stages"].keys()) == set(vp.STAGE_ORDER)
    assert all(
        stage["status"] == "WAITING"
        for stage in job["stages"].values()
    )


def test_update_stage_running_then_success(fake_redis):
    job_id = "val_test002"
    vp.init_validation_job(job_id)

    vp.update_validation_stage(
        job_id, "vendor", "RUNNING", message="Validating vendor"
    )

    job = vp.get_validation_status(job_id)
    assert job["status"] == "RUNNING"
    assert job["current_stage"] == "vendor"
    assert job["stages"]["vendor"]["status"] == "RUNNING"
    assert job["stages"]["vendor"]["started_at"] is not None

    vp.update_validation_stage(
        job_id,
        "vendor",
        "SUCCESS",
        message="Vendor validation completed",
        issues=[],
        duration_ms=800,
    )

    job = vp.get_validation_status(job_id)
    assert job["stages"]["vendor"]["status"] == "SUCCESS"
    assert job["stages"]["vendor"]["duration_ms"] == 800
    assert job["stages"]["vendor"]["completed_at"] is not None


def test_skip_remaining_stages_marks_them_skipped_not_waiting(fake_redis):
    job_id = "val_test003"
    vp.init_validation_job(job_id)

    vp.update_validation_stage(job_id, "extraction", "SUCCESS")
    vp.update_validation_stage(job_id, "vendor", "SUCCESS")
    vp.update_validation_stage(job_id, "buyer", "FAILED", issues=["x"])

    vp.skip_remaining_stages(job_id, "buyer")

    job = vp.get_validation_status(job_id)
    assert job["stages"]["extraction"]["status"] == "SUCCESS"
    assert job["stages"]["vendor"]["status"] == "SUCCESS"
    assert job["stages"]["buyer"]["status"] == "FAILED"
    assert job["stages"]["gst"]["status"] == "SKIPPED"


def test_complete_validation_job_sets_final_shape(fake_redis):
    job_id = "val_test004"
    vp.init_validation_job(job_id)

    vp.complete_validation_job(
        job_id,
        is_valid=False,
        requires_manual_review=True,
        issues=["GST rate mismatch"],
        success=[{"validation_type": "EXTRACTION", "source": "ok"}],
    )

    job = vp.get_validation_status(job_id)
    assert job["status"] == "FAILED"
    assert job["current_stage"] is None
    assert job["is_valid"] is False
    assert job["requires_manual_review"] is True
    assert job["issues"] == ["GST rate mismatch"]
    assert job["success"] == [
        {"validation_type": "EXTRACTION", "source": "ok"}
    ]


def test_fail_validation_job_for_system_errors(fake_redis):
    job_id = "val_test005"
    vp.init_validation_job(job_id)

    vp.fail_validation_job(job_id, "Unexpected error during validation.")

    job = vp.get_validation_status(job_id)
    assert job["status"] == "FAILED"
    assert job["is_valid"] is False
    assert job["requires_manual_review"] is True
    assert job["issues"] == ["Unexpected error during validation."]


# ---------------------------------------------------------------------------
# 2. Redis unavailable - must never raise, validation must be able to
# continue regardless.
# ---------------------------------------------------------------------------


def test_all_helpers_are_safe_when_redis_is_unreachable(no_redis):
    job_id = "val_test006"

    # None of these should raise.
    vp.init_validation_job(job_id)
    vp.update_validation_stage(job_id, "vendor", "RUNNING")
    vp.skip_remaining_stages(job_id, "vendor")
    vp.complete_validation_job(job_id, True, False, [])
    vp.fail_validation_job(job_id, "boom")

    assert vp.get_validation_status(job_id) is None


# ---------------------------------------------------------------------------
# 3. Concurrency: independent jobs never share or leak state.
# ---------------------------------------------------------------------------


def test_multiple_jobs_maintain_independent_redis_state(fake_redis):
    job_a = "val_001"
    job_b = "val_002"
    job_c = "val_003"

    for job_id in (job_a, job_b, job_c):
        vp.init_validation_job(job_id)

    # Interleave updates across jobs, out of order, to simulate
    # concurrent invoices being validated at the same time.
    vp.update_validation_stage(job_a, "extraction", "RUNNING")
    vp.update_validation_stage(job_b, "extraction", "RUNNING")
    vp.update_validation_stage(job_a, "extraction", "SUCCESS", duration_ms=100)
    vp.update_validation_stage(job_c, "extraction", "RUNNING")
    vp.update_validation_stage(job_b, "extraction", "FAILED", issues=["bad"])
    vp.update_validation_stage(job_a, "vendor", "RUNNING")
    vp.skip_remaining_stages(job_b, "extraction")
    vp.update_validation_stage(job_c, "extraction", "SUCCESS", duration_ms=50)

    a = vp.get_validation_status(job_a)
    b = vp.get_validation_status(job_b)
    c = vp.get_validation_status(job_c)

    assert a["job_id"] == job_a
    assert a["stages"]["extraction"]["status"] == "SUCCESS"
    assert a["stages"]["vendor"]["status"] == "RUNNING"
    assert a["current_stage"] == "vendor"

    assert b["job_id"] == job_b
    assert b["stages"]["extraction"]["status"] == "FAILED"
    assert b["stages"]["vendor"]["status"] == "SKIPPED"
    assert b["stages"]["buyer"]["status"] == "SKIPPED"
    assert b["stages"]["gst"]["status"] == "SKIPPED"

    assert c["job_id"] == job_c
    assert c["stages"]["extraction"]["status"] == "SUCCESS"
    assert c["stages"]["vendor"]["status"] == "WAITING"

    # Each job lives at its own Redis key.
    assert set(fake_redis.store.keys()) == {
        "ap:validation:val_001",
        "ap:validation:val_002",
        "ap:validation:val_003",
    }


# ---------------------------------------------------------------------------
# 4. End to end through the real service, using job_id - proves the
# actual validate_invoice() stage wiring (not just the raw helpers).
# ---------------------------------------------------------------------------


class FakeTaxDAO:

    def __init__(self, sac_rates: Optional[Dict[str, Decimal]] = None):
        self.sac_rates = sac_rates or {"997331": Decimal("18.0000")}
        self.vendor_found = True

    def get_country_id_by_code(self, country_code):
        return 1

    def get_gst_rate_rule_for_sac(self, sac, country_id, as_of_date):
        rate = self.sac_rates.get(sac)
        if rate is None:
            return None
        return {"tax_rule_id": 1, "rule_code": f"GST_SAC_{sac}", "rate_percent": rate}

    def get_tax_component_rules(self, country_id, same_state, as_of_date):
        if same_state:
            return [
                {"tax_rule_id": 3, "rule_code": "CGST_9_SAME_STATE", "tax_code": "CGST", "rate_percent": Decimal("9.0000")},
                {"tax_rule_id": 4, "rule_code": "SGST_9_SAME_STATE", "tax_code": "SGST", "rate_percent": Decimal("9.0000")},
            ]
        return [
            {"tax_rule_id": 5, "rule_code": "IGST_18_DIFFERENT_STATE", "tax_code": "IGST", "rate_percent": Decimal("18.0000")},
        ]

    def get_vendor_details_by_gstin(self, gstin, name):
        if not self.vendor_found:
            return None
        return {"vendor_id": 1, "vendor_name": name, "status_name": "ACTIVE"}

    def create_inbound_document(self, request):
        return None


def make_service(fake_dao: FakeTaxDAO) -> InvoiceExtractionService:
    service = InvoiceExtractionService(db=None)
    service.invoice_extraction_dao = fake_dao
    return service


def make_line(**overrides) -> InvoiceLine:
    base = dict(line_number=1, hsn_sac="997331", taxable_amount=10000.0)
    base.update(overrides)
    return InvoiceLine(**base)


def make_extracted(
    lines: List[InvoiceLine],
    vendor_state_code="27",
    buyer_state_code="27",
    tax_type="INTRA_STATE_CGST_SGST",
    buyer_name="Beta Buyers",
    amounts: Optional[Dict[str, Any]] = None,
) -> ExtractedInvoiceResponse:
    amounts = amounts or {}
    return ExtractedInvoiceResponse(
        document=InvoiceDocument(invoice_number="INV-1", invoice_date="2026-08-01"),
        vendor=InvoiceVendor(
            name="Acme Traders",
            gstin=f"{vendor_state_code}AABCU9603R1ZM" if vendor_state_code else None,
            state_code=vendor_state_code,
        ),
        buyer=InvoiceBuyer(
            name=buyer_name,
            gstin=f"{buyer_state_code}AAAAA0000A1Z5" if buyer_state_code else None,
            state_code=buyer_state_code,
        ),
        reference=InvoiceReference(),
        amounts=InvoiceAmounts(**amounts),
        payment=InvoicePayment(),
        tax=InvoiceTax(tax_type=tax_type),
        compliance=InvoiceCompliance(),
        invoice_lines=lines,
        extraction=ExtractionMetadata(status="SUCCESS"),
        validation=InvoiceValidation(status="READY_FOR_VALIDATION", is_valid=True),
    )


def test_service_reports_all_stages_success_to_redis(fake_redis, monkeypatch):
    import Backend.Business_Layer.services.invoice_extraction_service as svc_module
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Beta Buyers")

    job_id = "val_success1"
    vp.init_validation_job(job_id)

    fake_dao = FakeTaxDAO()
    service = make_service(fake_dao)

    line = make_line(cgst_rate=9.0, cgst_amount=900.0, sgst_rate=9.0, sgst_amount=900.0)
    extracted = make_extracted(
        lines=[line],
        amounts={
            "taxable_amount": 10000.0,
            "cgst_amount": 900.0,
            "sgst_amount": 900.0,
            "total_tax": 1800.0,
        },
    )

    result = service.validate_invoice(extracted, file_path="s3/key.pdf", job_id=job_id)

    assert result.is_valid is True

    job = vp.get_validation_status(job_id)
    assert job["status"] == "COMPLETED"
    assert job["is_valid"] is True
    assert job["current_stage"] is None
    for stage in vp.STAGE_ORDER:
        assert job["stages"][stage]["status"] == "SUCCESS"
        assert job["stages"][stage]["duration_ms"] is not None
    assert {entry["validation_type"] for entry in job["success"]} == {
        "EXTRACTION", "VENDOR", "BUYER", "TAX"
    }


def test_service_skips_gst_in_redis_when_buyer_fails(fake_redis, monkeypatch):
    import Backend.Business_Layer.services.invoice_extraction_service as svc_module
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Someone Else")

    job_id = "val_fail1"
    vp.init_validation_job(job_id)

    fake_dao = FakeTaxDAO()
    service = make_service(fake_dao)

    line = make_line(cgst_rate=9.0, cgst_amount=900.0, sgst_rate=9.0, sgst_amount=900.0)
    extracted = make_extracted(
        lines=[line],
        buyer_name="Beta Buyers",  # won't match "Someone Else"
        amounts={"taxable_amount": 10000.0, "cgst_amount": 900.0, "sgst_amount": 900.0, "total_tax": 1800.0},
    )

    result = service.validate_invoice(extracted, file_path="s3/key.pdf", job_id=job_id)

    assert result.is_valid is False
    assert result.issues == ["Buyer name does not match expected buyer"]

    job = vp.get_validation_status(job_id)
    assert job["status"] == "FAILED"
    assert job["stages"]["extraction"]["status"] == "SUCCESS"
    assert job["stages"]["vendor"]["status"] == "SUCCESS"
    assert job["stages"]["buyer"]["status"] == "FAILED"
    assert job["stages"]["buyer"]["issues"] == [
        "Buyer name does not match expected buyer"
    ]
    assert job["stages"]["gst"]["status"] == "SKIPPED"


def test_two_concurrent_invoices_through_real_service_stay_isolated(
    fake_redis, monkeypatch
):
    """Invoice A passes fully; Invoice B fails at vendor. Both run
    through the real service with the same job_id-based Redis
    wiring - their progress records must never cross-contaminate."""

    import Backend.Business_Layer.services.invoice_extraction_service as svc_module
    monkeypatch.setattr(svc_module, "get_env_var", lambda *a, **k: "Beta Buyers")

    job_a, job_b = "val_A", "val_B"
    vp.init_validation_job(job_a)
    vp.init_validation_job(job_b)

    # Invoice A: everything matches, passes fully.
    dao_a = FakeTaxDAO()
    service_a = make_service(dao_a)
    line_a = make_line(cgst_rate=9.0, cgst_amount=900.0, sgst_rate=9.0, sgst_amount=900.0)
    extracted_a = make_extracted(
        lines=[line_a],
        amounts={"taxable_amount": 10000.0, "cgst_amount": 900.0, "sgst_amount": 900.0, "total_tax": 1800.0},
    )

    # Invoice B: vendor not found in vendor master.
    dao_b = FakeTaxDAO()
    dao_b.vendor_found = False
    service_b = make_service(dao_b)
    line_b = make_line(cgst_rate=9.0, cgst_amount=900.0, sgst_rate=9.0, sgst_amount=900.0)
    extracted_b = make_extracted(
        lines=[line_b],
        amounts={"taxable_amount": 10000.0, "cgst_amount": 900.0, "sgst_amount": 900.0, "total_tax": 1800.0},
    )

    result_a = service_a.validate_invoice(extracted_a, file_path="a.pdf", job_id=job_a)
    result_b = service_b.validate_invoice(extracted_b, file_path="b.pdf", job_id=job_b)

    assert result_a.is_valid is True
    assert result_b.is_valid is False

    a = vp.get_validation_status(job_a)
    b = vp.get_validation_status(job_b)

    assert a["status"] == "COMPLETED"
    assert all(a["stages"][s]["status"] == "SUCCESS" for s in vp.STAGE_ORDER)

    assert b["status"] == "FAILED"
    assert b["stages"]["extraction"]["status"] == "SUCCESS"
    assert b["stages"]["vendor"]["status"] == "FAILED"
    assert b["stages"]["buyer"]["status"] == "SKIPPED"
    assert b["stages"]["gst"]["status"] == "SKIPPED"

    # No cross-contamination between the two job records.
    assert a["job_id"] == job_a
    assert b["job_id"] == job_b
