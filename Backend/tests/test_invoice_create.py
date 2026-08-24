# Backend/tests/test_invoice_create.py
"""Tests for InvoiceExtractionService.create_invoice and its pure
mapping helper build_custom_invoice_request.

build_custom_invoice_request is pure (no DB) and tested as such.
create_invoice does real inserts, so its tests run against the real
dev DB (same one every other integration check in this session has
used) against an already-existing real vendor (Amazon Web Services
India Private Limited, vendor_id=15, GSTIN 07AAJCA9880A1ZL), using a
uuid-suffixed invoice_number to avoid collisions, and clean up every
row they create in a finally block.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from Backend.Business_Layer.services.invoice_extraction_service import (
    InvoiceExtractionService,
    build_custom_invoice_request,
)
from Backend.Business_Layer.utils.exceptions import (
    DuplicateInvoiceError,
    FieldExtractionError,
)
from Backend.Data_Access_Layer.utils.database import SessionLocal
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
    InvoiceType,
    InvoiceValidation,
    InvoiceVendor,
)


AWS_VENDOR_GSTIN = "07AAJCA9880A1ZL"
AWS_VENDOR_NAME = "Amazon Web Services India Private Limited"


def make_extracted(
    invoice_number,
    lines=None,
    po_number=None,
) -> ExtractedInvoiceResponse:
    return ExtractedInvoiceResponse(
        document=InvoiceDocument(
            invoice_number=invoice_number,
            invoice_date=date(2026, 8, 1),
            due_date=date(2026, 8, 31),
            currency="INR",
            original_filename="test-invoice.pdf",
        ),
        vendor=InvoiceVendor(
            name=AWS_VENDOR_NAME,
            gstin=AWS_VENDOR_GSTIN,
        ),
        buyer=InvoiceBuyer(name="Paves Global Infotech pvt ltd"),
        reference=InvoiceReference(po_number=po_number),
        amounts=InvoiceAmounts(
            subtotal=1000.0,
            taxable_amount=1000.0,
            cgst_amount=90.0,
            sgst_amount=90.0,
            total_tax=180.0,
            grand_total=1180.0,
        ),
        payment=InvoicePayment(payment_terms="Net 30"),
        tax=InvoiceTax(tax_type="INTRA_STATE_CGST_SGST"),
        compliance=InvoiceCompliance(),
        invoice_lines=lines or [],
        extraction=ExtractionMetadata(status="SUCCESS", confidence=95.5),
        validation=InvoiceValidation(
            status="READY_FOR_VALIDATION", is_valid=True
        ),
    )


# ---------------------------------------------------------------------------
# build_custom_invoice_request - pure mapping, no DB
# ---------------------------------------------------------------------------


def test_build_custom_invoice_request_maps_header_fields():
    line = InvoiceLine(
        line_number=1,
        description="Cloud services",
        hsn_sac="998315",
        quantity=1.0,
        unit_price=1000.0,
        line_total=1000.0,
        cgst_amount=90.0,
        sgst_amount=90.0,
    )
    extracted = make_extracted("INV-TEST-1", lines=[line])

    custom_request = build_custom_invoice_request(
        extracted, "invoices/test.pdf"
    )

    assert custom_request.invoice.invoice_number == "INV-TEST-1"
    assert custom_request.invoice.invoice_type == InvoiceType.NON_PO
    assert custom_request.invoice.currency == "INR"
    assert custom_request.invoice.grand_amount == Decimal("1180.0")
    assert custom_request.invoice.tax_amount == Decimal("180.0")
    assert custom_request.invoice.net_amount == Decimal("1180.0")

    assert len(custom_request.invoice_lines) == 1
    line_request = custom_request.invoice_lines[0]
    assert line_request.hsn_sac == "998315"
    assert line_request.line_amount == Decimal("1000.0")
    assert line_request.tax_amount == Decimal("180.0")

    assert custom_request.inbound_document.file_path == "invoices/test.pdf"
    assert custom_request.inbound_document.extraction_status == "EXTRACTED"
    assert custom_request.inbound_document.extraction_confidence == Decimal(
        "95.5"
    )

    assert custom_request.invoice_attachment.file_path == "invoices/test.pdf"


def test_build_custom_invoice_request_po_present_sets_po_type():
    extracted = make_extracted("INV-TEST-2", po_number="PO-123")
    custom_request = build_custom_invoice_request(extracted, "x.pdf")
    assert custom_request.invoice.invoice_type == InvoiceType.PO


def test_build_custom_invoice_request_missing_invoice_number_raises():
    extracted = make_extracted("INV-TEST-3")
    extracted.document.invoice_number = None

    with pytest.raises(FieldExtractionError):
        build_custom_invoice_request(extracted, "x.pdf")


def test_build_custom_invoice_request_missing_amount_raises():
    extracted = make_extracted("INV-TEST-4")
    extracted.amounts.grand_total = None
    extracted.amounts.subtotal = None

    with pytest.raises(FieldExtractionError):
        build_custom_invoice_request(extracted, "x.pdf")


# ---------------------------------------------------------------------------
# create_invoice - real DB, cleaned up afterward
# ---------------------------------------------------------------------------


def _cleanup(invoice_id, inbound_document_id, db):
    # invoice.inbound_document_id and inbound_document.invoice_id FK
    # each other (circular) - break the cycle by nulling one side
    # before either row can be deleted. invoice_line/invoice_attachment
    # cascade-delete with invoice; inbound_document does not.
    if invoice_id is not None:
        db.execute(
            text(
                "UPDATE ap.invoice SET inbound_document_id = NULL "
                "WHERE invoice_id = :id"
            ),
            {"id": invoice_id},
        )
    if inbound_document_id is not None:
        db.execute(
            text(
                "DELETE FROM ap.inbound_document "
                "WHERE inbound_document_id = :id"
            ),
            {"id": inbound_document_id},
        )
    if invoice_id is not None:
        db.execute(
            text("DELETE FROM ap.invoice WHERE invoice_id = :id"),
            {"id": invoice_id},
        )
    db.commit()


def test_create_invoice_persists_invoice_lines_and_attachment():
    invoice_number = f"TEST-CREATE-{uuid.uuid4().hex[:8]}"

    line = InvoiceLine(
        line_number=1,
        description="Cloud services",
        hsn_sac="998315",
        quantity=1.0,
        unit_price=1000.0,
        line_total=1000.0,
        cgst_amount=90.0,
        sgst_amount=90.0,
    )
    extracted = make_extracted(invoice_number, lines=[line])

    db = SessionLocal()
    result = None

    try:
        service = InvoiceExtractionService(db)
        result = service.create_invoice(
            extracted, f"invoices/{invoice_number}.pdf"
        )

        assert result["invoice_number"] == invoice_number
        assert result["vendor_id"] == 15
        assert result["status_code"] == "OCR_REVIEW_PENDING"
        assert result["line_count"] == 1
        assert result["skipped_line_count"] == 0
        assert result["invoice_attachment_id"] is not None
        assert result["inbound_document_id"] is not None

        # Verify what actually landed in the DB, not just the
        # returned summary.
        row = db.execute(
            text(
                "SELECT status_id, gross_amount, net_amount, "
                "inbound_document_id FROM ap.invoice "
                "WHERE invoice_id = :id"
            ),
            {"id": result["invoice_id"]},
        ).first()
        assert row is not None
        assert row.status_id == 6  # OCR_REVIEW_PENDING
        assert row.gross_amount == Decimal("1180.00")

        line_rows = db.execute(
            text(
                "SELECT line_number, description, line_amount "
                "FROM ap.invoice_line WHERE invoice_id = :id"
            ),
            {"id": result["invoice_id"]},
        ).all()
        assert len(line_rows) == 1
        assert line_rows[0].description == "Cloud services"

        attachment_rows = db.execute(
            text(
                "SELECT file_path FROM ap.invoice_attachment "
                "WHERE invoice_id = :id"
            ),
            {"id": result["invoice_id"]},
        ).all()
        assert len(attachment_rows) == 1

        inbound_row = db.execute(
            text(
                "SELECT invoice_id, vendor_id, extraction_status "
                "FROM ap.inbound_document "
                "WHERE inbound_document_id = :id"
            ),
            {"id": result["inbound_document_id"]},
        ).first()
        assert inbound_row.invoice_id == result["invoice_id"]
        assert inbound_row.vendor_id == 15
        assert inbound_row.extraction_status == "EXTRACTED"

    finally:
        if result:
            _cleanup(result["invoice_id"], result["inbound_document_id"], db)
        db.close()


def test_create_invoice_duplicate_raises_and_first_row_survives():
    invoice_number = f"TEST-CREATE-DUP-{uuid.uuid4().hex[:8]}"
    extracted_1 = make_extracted(invoice_number)
    extracted_2 = make_extracted(invoice_number)

    db = SessionLocal()
    result = None

    try:
        service = InvoiceExtractionService(db)
        result = service.create_invoice(
            extracted_1, f"invoices/{invoice_number}-1.pdf"
        )

        with pytest.raises(DuplicateInvoiceError):
            service.create_invoice(
                extracted_2, f"invoices/{invoice_number}-2.pdf"
            )

        # Exactly one invoice must exist despite the second attempt.
        count = db.execute(
            text(
                "SELECT COUNT(*) FROM ap.invoice "
                "WHERE invoice_number = :n AND vendor_id = 15"
            ),
            {"n": invoice_number},
        ).scalar()
        assert count == 1

    finally:
        if result:
            _cleanup(result["invoice_id"], result["inbound_document_id"], db)
        db.close()


def test_create_invoice_unknown_vendor_raises_field_extraction_error():
    invoice_number = f"TEST-CREATE-NOVENDOR-{uuid.uuid4().hex[:8]}"
    extracted = make_extracted(invoice_number)
    extracted.vendor.gstin = "99ZZZZZ0000Z1Z9"
    extracted.vendor.name = "Totally Unknown Vendor Pvt Ltd"

    db = SessionLocal()

    try:
        service = InvoiceExtractionService(db)

        with pytest.raises(FieldExtractionError):
            service.create_invoice(
                extracted, f"invoices/{invoice_number}.pdf"
            )

    finally:
        db.close()
