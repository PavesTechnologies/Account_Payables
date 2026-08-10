# Backend/tests/test_document_intelligence_regression.py
"""Regression suite for the Document Intelligence layer.

Exercises `extraction/*` and `validators.py` against varied synthetic
invoice layouts (different vendors/templates, tax regimes, party
structures) to lock in the business-field-assignment behavior fixed in
this pass. The OCR/PDF layer (PyMuPDF, RapidOCR) is unchanged and out
of scope, so these tests build `DocumentResult` directly via
`invoice_builder.build_document` rather than rendering real files —
what matters here is field *assignment* given already-recognized text
and geometry, not text recognition itself.
"""
from __future__ import annotations

import decimal

from Backend.Business_Layer.utils import validators
from Backend.Business_Layer.utils.extraction.registry import extract_invoice_fields

from invoice_builder import build_document

D = decimal.Decimal


def test_cgst_sgst_regime_full_invoice():
    """Intra-state invoice: every field present, CGST+SGST, single tax slab."""
    doc = build_document([
        "TAX INVOICE",
        "Manan Agency Pvt Ltd",
        "Vendor GSTIN 27ABCDE1234F1Z5",
        "Bill To",
        "Acme Retail Ltd",
        "Buyer GSTIN 07PQRSX5678L1Z3",
        "Invoice Number INV-2024-001",
        "Invoice Date 12/03/2024",
        "Due Date 11/04/2024",
        "PO Number PO-99881",
        "Description Qty Rate Amount",
        "Widget A 10 100.00 1000.00",
        "Subtotal 1000.00",
        "CGST 90.00",
        "SGST 90.00",
        "Payment Terms Net 30",
        "Currency INR",
        "Grand Total 1180.00",
    ])
    result = extract_invoice_fields(doc)

    assert result.invoice_number == "INV-2024-001"
    assert str(result.invoice_date) == "2024-03-12"
    assert str(result.due_date) == "2024-04-11"
    assert result.gstin == "27ABCDE1234F1Z5"
    assert result.buyer_gstin == "07PQRSX5678L1Z3"
    assert result.po_number == "PO-99881"
    assert result.subtotal == D("1000.00")
    assert result.cgst == D("90.00")
    assert result.sgst == D("90.00")
    assert result.igst is None
    assert result.total == D("1180.00")
    assert result.payment_terms == "Net 30"
    assert result.currency == "INR"

    validation = validators.validate_invoice(result)
    assert validation.valid, validation.errors


def test_igst_interstate_invoice():
    """Inter-state invoice: IGST only, no CGST/SGST."""
    doc = build_document([
        "Global Traders Pvt Ltd",
        "Vendor GSTIN 27ABCDE1234F1Z5",
        "Bill To XYZ Corp",
        "Invoice No IGST-777",
        "Invoice Date 01-05-2024",
        "Subtotal 5000.00",
        "IGST 900.00",
        "Grand Total 5900.00",
    ])
    result = extract_invoice_fields(doc)

    assert result.igst == D("900.00")
    assert result.cgst is None
    assert result.sgst is None
    assert result.total == D("5900.00")

    validation = validators.validate_invoice(result)
    assert validation.valid, validation.errors


def test_tax_rate_never_returned_as_tax_amount():
    """'CGST 9% Rs.225.00' must yield 225.00, never the 9% rate."""
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-5",
        "Invoice Date 01-01-2024",
        "Subtotal 2500.00",
        "CGST 9% Rs.225.00",
        "SGST 9% Rs.225.00",
        "Grand Total 2950.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.cgst == D("225.00")
    assert result.sgst == D("225.00")


def test_multiple_tax_slabs_aggregate():
    """Two CGST/SGST slabs (14% and 2.5%) must sum, not pick one winner."""
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-6",
        "Invoice Date 01-01-2024",
        "Description Qty Rate Amount",
        "Item A 1 20000.00 20000.00",
        "Item B 1 40600.00 40600.00",
        "Subtotal 60600.00",
        "CGST 14% 2800.00",
        "SGST 14% 2800.00",
        "CGST 2.5% 1015.00",
        "SGST 2.5% 1015.00",
        "Grand Total 68230.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.cgst == D("3815.00")
    assert result.sgst == D("3815.00")


def test_cess_included_in_total_and_validation():
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-7",
        "Invoice Date 01-01-2024",
        "Subtotal 1000.00",
        "CGST 90.00",
        "SGST 90.00",
        "Cess 21.00",
        "Grand Total 1201.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.cess == D("21.00")
    assert result.total == D("1201.00")

    validation = validators.validate_invoice(result)
    assert validation.valid, validation.errors


def test_grand_total_not_confused_with_total_gst_or_line_total():
    """'Total GST'/'Line Total' must never outrank the real grand total."""
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-8",
        "Invoice Date 01-01-2024",
        "Description Qty Rate Line Total",
        "Item A 1 500.00 500.00",
        "Subtotal 500.00",
        "CGST 45.00",
        "SGST 45.00",
        "Total GST 90.00",
        "Grand Total 590.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.total == D("590.00")


def test_vendor_and_buyer_gstin_never_swapped_multiple_gstins():
    doc = build_document([
        "Seller",
        "Prime Exports Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Ship To",
        "Warehouse GSTIN 09WXYZQ4321M1Z8",
        "Bill To",
        "Northwind Retail",
        "Buyer GSTIN 07PQRSX5678L1Z3",
        "Invoice No INV-9",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.gstin == "27ABCDE1234F1Z5"
    assert result.buyer_gstin == "07PQRSX5678L1Z3"
    assert result.gstin != result.buyer_gstin


def test_multiple_dates_only_correct_roles_populate():
    """PO date / dispatch date must never leak into invoice_date or due_date."""
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-10",
        "PO Date 15-02-2024",
        "Dispatch Date 20-02-2024",
        "Invoice Date 18-02-2024",
        "Due Date 20-03-2024",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert str(result.invoice_date) == "2024-02-18"
    assert str(result.due_date) == "2024-03-20"


def test_payment_terms_only_does_not_derive_due_date():
    """A payment-terms label alone must never populate due_date."""
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-11",
        "Invoice Date 01-01-2024",
        "Payment Terms Net 45",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.payment_terms == "Net 45"
    assert result.due_date is None


def test_payment_terms_free_text_sentence():
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-12",
        "Invoice Date 01-01-2024",
        "Payment is due within 7 days from the date of invoice",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.payment_terms is not None
    assert "7" in result.payment_terms and "days" in result.payment_terms.lower()


def test_bare_terms_heading_is_not_payment_terms():
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-13",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "Grand Total 100.00",
        "Terms and Conditions apply overleaf",
    ])
    result = extract_invoice_fields(doc)
    assert result.payment_terms is None


def test_po_number_present_and_distinct_from_invoice_number():
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-14",
        "PO Number PO-55221",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.invoice_number == "INV-14"
    assert result.po_number == "PO-55221"


def test_place_of_supply_is_not_mistaken_for_po_number():
    """'POS' (Place of Supply) must never populate po_number."""
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-15",
        "Place of Supply Maharashtra",
        "POS 27-Maharashtra",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.po_number is None


def test_issued_to_and_billing_shipping_heading_rejected_as_vendor_name():
    doc = build_document([
        "Issued To",
        "Northwind Retail Ltd",
        "Billing & Shipping Address",
        "221B Baker Street",
        "Vendor",
        "Real Vendor Enterprises",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-16",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.vendor_name is not None
    assert "issued" not in result.vendor_name.lower()
    assert "billing" not in result.vendor_name.lower()
    assert "northwind" not in result.vendor_name.lower()


def test_customer_marker_treated_as_buyer_context_for_gstin():
    doc = build_document([
        "Seller",
        "Prime Exports Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Customer",
        "Northwind Retail",
        "GSTIN 07PQRSX5678L1Z3",
        "Invoice No INV-17",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.gstin == "27ABCDE1234F1Z5"
    assert result.buyer_gstin == "07PQRSX5678L1Z3"


def test_total_reconciles_against_subtotal_and_taxes_when_alternates_exist():
    """A weak, arithmetically-wrong 'Total' candidate must lose to the
    real Grand Total when the latter reconciles with subtotal+taxes."""
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-18",
        "Invoice Date 01-01-2024",
        "Subtotal 10000.00",
        "CGST 600.00",
        "SGST 600.00",
        "Total 999.00",
        "Grand Total",
        "11200.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.total == D("11200.00")
    assert "ARITHMETIC_RECONCILED" in result.field_metadata["total"].method


def test_discount_and_round_off_extraction_still_correct_though_unreconciled():
    """Known limitation: discount/round-off aren't tracked fields (schema
    is frozen), so validate_totals may flag a mismatch here — but the
    real Grand Total value itself must still be extracted correctly."""
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-19",
        "Invoice Date 01-01-2024",
        "Subtotal 1000.00",
        "CGST 90.00",
        "SGST 90.00",
        "Discount 50.00",
        "Freight 25.00",
        "Round Off 0.00",
        "Grand Total 1155.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.total == D("1155.00")
    assert result.subtotal == D("1000.00")
    assert result.cgst == D("90.00")
    # Documented limitation: discount/freight participate in the real
    # total but are not modeled fields, so this legitimately reports a
    # validation mismatch rather than a silently-wrong "reconciled" value.
    validation = validators.validate_invoice(result)
    assert not validation.valid
    assert any("does not match" in e for e in validation.errors)


def test_currency_defaults_to_inr_for_gst_invoice_without_explicit_symbol():
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-20",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "Grand Total 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.currency == "INR"


def test_currency_explicit_code_overrides_default():
    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-21",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "Currency USD",
        "Grand Total USD 100.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.currency == "USD"


def test_invoice_51109301_net_vat_gross_table_mapping():
    doc = build_document([
        "Seller TechVision Distributors Pvt Ltd Client Raj Electronics Pvt Ltd",
        "GSTIN 27AABCT1234F1Z5",
        "Invoice No 51109301",
        "Invoice Date 03/07/2023",
        "VAT % Net Worth VAT Gross Worth",
        "10% 1,676,976.00 167,697.60 1,844,673.60",
        "Currency INR",
    ])
    result = extract_invoice_fields(doc)

    assert result.invoice_number == "51109301"
    assert str(result.invoice_date) == "2023-07-03"
    assert result.vendor_name == "TechVision Distributors Pvt Ltd"
    assert result.gstin == "27AABCT1234F1Z5"
    assert result.buyer_gstin is None
    assert result.subtotal == D("1676976.00")
    assert result.tax_type == "VAT"
    assert result.tax_rate == D("10")
    assert result.tax_amount == D("167697.60")
    assert result.total == D("1844673.60")
    assert result.currency == "INR"

    validation = validators.validate_invoice(result)
    assert validation.valid, validation.errors


def test_invoice_51109305_net_vat_gross_table_mapping():
    doc = build_document([
        "Seller TechVision Distributors Pvt Ltd",
        "GSTIN 27AABCT1234F1Z5",
        "Client Raj Electronics Pvt Ltd",
        "Invoice No 51109305",
        "Invoice Date 09/03/2024",
        "VAT % Net Worth VAT Gross Worth",
        "10% 2,023,625.00 202,362.50 2,225,987.50",
        "Currency INR",
    ])
    result = extract_invoice_fields(doc)

    assert result.invoice_number == "51109305"
    assert str(result.invoice_date) == "2024-03-09"
    assert result.vendor_name == "TechVision Distributors Pvt Ltd"
    assert result.gstin == "27AABCT1234F1Z5"
    assert result.buyer_gstin is None
    assert result.subtotal == D("2023625.00")
    assert result.tax_type == "VAT"
    assert result.tax_rate == D("10")
    assert result.tax_amount == D("202362.50")
    assert result.total == D("2225987.50")
    assert result.currency == "INR"

    validation = validators.validate_invoice(result)
    assert validation.valid, validation.errors


def test_invoice_2_seller_name_stops_before_ocr_merged_client_name():
    doc = build_document([
        "Seller",
        "TechVision Distributors Pvt Ltd Raj Electronics Pvt Ltd",
        "GSTIN 27AABCT1234F1Z5",
        "Invoice No 51109301",
        "Invoice Date 03/07/2023",
        "VAT % Net Worth VAT Gross Worth",
        "10% 1,676,976.00 167,697.60 1,844,673.60",
        "Currency INR",
    ])
    result = extract_invoice_fields(doc)

    assert result.vendor_name == "TechVision Distributors Pvt Ltd"
    assert "Raj Electronics" not in result.vendor_name
    assert result.gstin == "27AABCT1234F1Z5"
    assert result.subtotal == D("1676976.00")
    assert result.tax_type == "VAT"
    assert result.tax_rate == D("10")
    assert result.tax_amount == D("167697.60")
    assert result.total == D("1844673.60")


def test_invoice_3_seller_name_stops_before_ocr_merged_client_without_suffix():
    doc = build_document([
        "Seller",
        "TechVision Distributors Pvt Ltd Hyderabad IT Traders",
        "GSTIN 27AABCT1234F1Z5",
        "Invoice No 51109305",
        "Invoice Date 09/03/2024",
        "VAT % Net Worth VAT Gross Worth",
        "10% 2,023,625.00 202,362.50 2,225,987.50",
        "Currency INR",
    ])
    result = extract_invoice_fields(doc)

    assert result.vendor_name == "TechVision Distributors Pvt Ltd"
    assert "Hyderabad IT Traders" not in result.vendor_name
    assert result.gstin == "27AABCT1234F1Z5"
    assert result.subtotal == D("2023625.00")
    assert result.tax_type == "VAT"
    assert result.tax_rate == D("10")
    assert result.tax_amount == D("202362.50")
    assert result.total == D("2225987.50")


def test_optional_fields_absent_do_not_tank_confidence():
    """No PO number / due date / cess / buyer GSTIN on this invoice —
    correctly absent, so extraction confidence should stay high."""
    from Backend.Business_Layer.utils import confidence as confidence_util

    doc = build_document([
        "Vendor Pvt Ltd",
        "GSTIN 27ABCDE1234F1Z5",
        "Invoice No INV-22",
        "Invoice Date 01-01-2024",
        "Subtotal 100.00",
        "CGST 9.00",
        "SGST 9.00",
        "Grand Total 118.00",
    ])
    result = extract_invoice_fields(doc)
    assert result.po_number is None and result.due_date is None and result.buyer_gstin is None

    extraction_confidence = confidence_util._extraction_confidence(result)
    assert extraction_confidence > 60.0, extraction_confidence
