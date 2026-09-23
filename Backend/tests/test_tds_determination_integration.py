# Backend/tests/test_tds_determination_integration.py
"""Real-DB persistence proof for TDSDeterminationService, following the same
pattern as test_invoice_create.py: runs against the real configured DATABASE_URL
using the already-existing AWS vendor (vendor_id=15, valid PAN), a uuid-suffixed
invoice_number to avoid collisions, and cleans up every row it creates in a
finally block. invoice_tds cascade-deletes with its invoice (ON DELETE CASCADE),
so deleting the invoice row is enough cleanup.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from Backend.Business_Layer.services import tds_determination_service
from Backend.Business_Layer.services.tds_determination_service import (
    DETERMINATION_STATUS_DETERMINED,
    DETERMINATION_STATUS_VERIFIED,
)
from Backend.Business_Layer.services.tds_determination_service import TDSDeterminationService
from Backend.Business_Layer.utils.vendor_auto_onboarding import GSTVerificationResult
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.utils.database import SessionLocal

AWS_VENDOR_ID = 15


def _make_invoice(db, gross_amount: Decimal) -> Invoice:
    invoice = Invoice(
        invoice_number=f"TDS-TEST-{uuid.uuid4().hex[:12]}",
        vendor_id=AWS_VENDOR_ID,
        invoice_type="NON_PO",
        invoice_date=date(2026, 6, 15),
        due_date=date(2026, 7, 15),
        currency_id=1,
        gross_amount=gross_amount,
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        net_amount=gross_amount,
        created_by="test-suite",
    )
    db.add(invoice)
    db.flush()
    db.commit()
    return invoice


def _cleanup(invoice_id, db):
    if invoice_id is not None:
        # invoice_tds has ON DELETE CASCADE on invoice_id - deleting the invoice
        # is enough to remove both rows.
        db.execute(text("DELETE FROM ap.invoice WHERE invoice_id = :id"), {"id": invoice_id})
        db.commit()


def test_determine_persists_and_verify_locks_against_real_db(monkeypatch):
    # AWS (vendor_id=15) has a real GST registration on file in this DB
    # (07AAJCA9880A1ZL) - mock the Sandbox call so this test never makes a
    # real external API call (same convention as every other test in this
    # repo that touches GST verification - see test_vendor_auto_onboarding.py).
    monkeypatch.setattr(
        tds_determination_service, "call_gst_search",
        lambda gstin: GSTVerificationResult(
            verified=True,
            data={"code": 200, "data": {"status_cd": "1", "data": {"gstin": gstin, "sts": "Active"}}},
        ),
    )

    db = SessionLocal()
    invoice_id = None

    try:
        invoice = _make_invoice(db, gross_amount=Decimal("200000.00"))
        invoice_id = invoice.invoice_id

        service = TDSDeterminationService(db)
        determined = service.determine(invoice_id, user_id="test-suite", payment_nature_code="PROFESSIONAL_SERVICE")

        assert determined.invoice_id == invoice_id
        assert determined.determination_status == DETERMINATION_STATUS_DETERMINED
        assert determined.tds_applicable is True
        assert determined.taxable_base == Decimal("200000.00")
        assert determined.tds_rate == Decimal("10.0000")
        assert determined.tds_amount == Decimal("20000.00")
        assert determined.aggregate_amount == determined.prior_period_aggregate + determined.taxable_base
        assert determined.gstin_status == "Active"
        assert determined.gstin_checked_at is not None

        # Persisted, not just returned in-memory - a fresh read sees the same row.
        reloaded = service.get(invoice_id)
        assert reloaded.id == determined.id
        assert reloaded.tds_amount == Decimal("20000.00")

        # Re-determination before verification updates the same row (spec: re-
        # determination works before approval).
        redetermined = service.determine(invoice_id, user_id="test-suite", payment_nature_code="PROFESSIONAL_SERVICE")
        assert redetermined.id == determined.id

        verified = service.verify(invoice_id, user_id="finance-test", remarks="Confirmed by integration test")
        assert verified.determination_status == DETERMINATION_STATUS_VERIFIED
        assert verified.verified_by == "finance-test"

        # A historical/verified determination is locked - the stored snapshot
        # does not silently change (spec: historical invoice retains its
        # stored determination).
        try:
            service.determine(invoice_id, user_id="test-suite")
            assert False, "expected ValueError: already verified"
        except ValueError as e:
            assert "already been verified" in str(e)

    finally:
        _cleanup(invoice_id, db)
        db.close()
