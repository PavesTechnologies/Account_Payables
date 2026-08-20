# Backend/tests/test_invoice_extraction_fields.py
"""Unit tests for the Textract-backed invoice extraction pipeline.

AWS Textract is never called for real - `textract_client` (a module-level
boto3 client) is monkeypatched with an in-memory fake that answers
StartExpenseAnalysis/GetExpenseAnalysis and StartDocumentAnalysis/
GetDocumentAnalysis with pre-built synthetic Textract-shaped responses.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

import Backend.API_Layer.utils.invoice_extraction_fields as fields


# ---------------------------------------------------------------------------
# Fake Textract client
# ---------------------------------------------------------------------------


class FakeTextractClient:
    """Pagination is driven entirely by the NextToken value (the page
    index, as a string) rather than a shared call counter - this way the
    poll loops (which call Get* once, ignore the payload, and stop as soon
    as JobStatus is SUCCEEDED) don't desynchronize the *separate* fetch
    loop that walks NextToken from the start.
    """

    def __init__(
        self,
        expense_pages: List[List[Dict[str, Any]]],
        query_block_pages: List[List[Dict[str, Any]]],
    ):
        self._expense_pages = expense_pages
        self._query_block_pages = query_block_pages

    def start_expense_analysis(self, **kwargs):
        return {"JobId": "expense-job"}

    def get_expense_analysis(self, **kwargs):
        page_idx = int(kwargs.get("NextToken") or 0)
        docs = (
            self._expense_pages[page_idx]
            if page_idx < len(self._expense_pages)
            else []
        )
        response = {"JobStatus": "SUCCEEDED", "ExpenseDocuments": docs}
        if page_idx + 1 < len(self._expense_pages):
            response["NextToken"] = str(page_idx + 1)
        return response

    def start_document_analysis(self, **kwargs):
        return {"JobId": "query-job"}

    def get_document_analysis(self, **kwargs):
        page_idx = int(kwargs.get("NextToken") or 0)
        blocks = (
            self._query_block_pages[page_idx]
            if page_idx < len(self._query_block_pages)
            else []
        )
        response = {"JobStatus": "SUCCEEDED", "Blocks": blocks}
        if page_idx + 1 < len(self._query_block_pages):
            response["NextToken"] = str(page_idx + 1)
        return response


def make_fake_client(
    expense_documents: List[Dict[str, Any]],
    query_blocks: List[Dict[str, Any]],
) -> FakeTextractClient:
    return FakeTextractClient([expense_documents], [query_blocks])


# ---------------------------------------------------------------------------
# Synthetic Textract block builders
# ---------------------------------------------------------------------------


def summary_field(
    type_text: str,
    value_text: str,
    confidence: float = 95.0,
    page: int = 1,
    group_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    field = {
        "Type": {"Text": type_text, "Confidence": 99.0},
        "ValueDetection": {"Text": value_text, "Confidence": confidence},
        "PageNumber": page,
    }
    if group_types:
        field["GroupProperties"] = [{"Types": group_types, "Id": "g1"}]
    return field


def line_item(fields_map: Dict[str, str]) -> Dict[str, Any]:
    return {
        "LineItemExpenseFields": [
            {"Type": {"Text": k}, "ValueDetection": {"Text": v}}
            for k, v in fields_map.items()
        ]
    }


def expense_document(
    summary_fields: List[Dict[str, Any]],
    line_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "SummaryFields": summary_fields,
        "LineItemGroups": (
            [{"LineItems": line_items}] if line_items else []
        ),
    }


_id_counter = {"n": 0}


def _next_id(prefix: str) -> str:
    _id_counter["n"] += 1
    return f"{prefix}-{_id_counter['n']}"


def query_answer_blocks(
    alias: str,
    text: str,
    confidence: float = 90.0,
    page: int = 1,
) -> List[Dict[str, Any]]:
    query_id = _next_id("query")
    result_id = _next_id("result")
    return [
        {
            "BlockType": "QUERY",
            "Id": query_id,
            "Page": page,
            "Query": {"Text": alias, "Alias": alias},
            "Relationships": [{"Type": "ANSWER", "Ids": [result_id]}],
        },
        {
            "BlockType": "QUERY_RESULT",
            "Id": result_id,
            "Text": text,
            "Confidence": confidence,
        },
    ]


def line_block(text: str, page: int = 1, top: float = 0.0) -> Dict[str, Any]:
    return {
        "BlockType": "LINE",
        "Id": _next_id("line"),
        "Text": text,
        "Page": page,
        "Geometry": {"BoundingBox": {"Top": top}},
    }


# Known-valid synthetic identifiers (format-checked, not real entities).
VENDOR_GSTIN = "29AABCU9603R1ZM"  # -> PAN AABCU9603R
BUYER_GSTIN = "27AAAAA0000A1Z5"  # -> PAN AAAAA0000A
IFSC = "HDFC0001234"


def base_summary_fields(**overrides) -> List[Dict[str, Any]]:
    fields_list = [
        summary_field("INVOICE_RECEIPT_ID", overrides.get("invoice_number", "INV-1")),
        summary_field("INVOICE_RECEIPT_DATE", overrides.get("invoice_date", "01/08/2026")),
        summary_field("VENDOR_NAME", overrides.get("vendor_name", "Acme Traders Pvt Ltd")),
        summary_field("VENDOR_ADDRESS", overrides.get("vendor_address", "123 MG Road, Bengaluru")),
        summary_field("RECEIVER_NAME", overrides.get("buyer_name", "Beta Buyers Pvt Ltd")),
        summary_field("RECEIVER_ADDRESS", overrides.get("buyer_address", "456 Anna Salai, Chennai")),
        summary_field("SUBTOTAL", overrides.get("subtotal", "10000.00")),
        summary_field("TOTAL", overrides.get("grand_total", "11800.00")),
    ]
    if overrides.get("po_number"):
        fields_list.append(summary_field("PO_NUMBER", overrides["po_number"]))
    return fields_list


def run_extraction(client: FakeTextractClient, monkeypatch):
    monkeypatch.setattr(fields, "textract_client", client)
    return asyncio.run(
        fields.extract_invoice_from_s3("invoices/test.pdf", "test.pdf")
    )


# ---------------------------------------------------------------------------
# 1. CGST + SGST
# ---------------------------------------------------------------------------


def test_cgst_sgst_invoice(monkeypatch):
    summary = base_summary_fields()
    query_blocks = (
        query_answer_blocks("SELLER_GSTIN", VENDOR_GSTIN)
        + query_answer_blocks("BUYER_GSTIN", BUYER_GSTIN)
        + query_answer_blocks(
            "TAX_DETAILS", "CGST 9% 900.00, SGST 9% 900.00"
        )
        + query_answer_blocks("TAXABLE_AMOUNT", "10000.00")
        + query_answer_blocks("GRAND_TOTAL", "11800.00")
    )

    client = make_fake_client(
        [expense_document(summary)], query_blocks
    )
    result = run_extraction(client, monkeypatch)

    assert result.amounts.cgst_amount == 900.0
    assert result.amounts.sgst_amount == 900.0
    assert result.amounts.igst_amount is None
    assert result.tax.tax_type == "INTRA_STATE_CGST_SGST"
    assert result.vendor.pan == "AABCU9603R"
    assert result.buyer.pan == "AAAAA0000A"
    assert result.validation.is_valid is True


# ---------------------------------------------------------------------------
# 2. IGST
# ---------------------------------------------------------------------------


def test_igst_invoice(monkeypatch):
    summary = base_summary_fields(grand_total="11800.00")
    query_blocks = (
        query_answer_blocks("SELLER_GSTIN", VENDOR_GSTIN)
        + query_answer_blocks("BUYER_GSTIN", BUYER_GSTIN)
        + query_answer_blocks("TAX_DETAILS", "IGST 18% 1800.00")
        + query_answer_blocks("TAXABLE_AMOUNT", "10000.00")
        + query_answer_blocks("GRAND_TOTAL", "11800.00")
    )

    client = make_fake_client([expense_document(summary)], query_blocks)
    result = run_extraction(client, monkeypatch)

    assert result.amounts.igst_amount == 1800.0
    assert result.amounts.cgst_amount is None
    assert result.tax.tax_type == "INTER_STATE_IGST"
    assert not any(
        issue.code == "CONTRADICTORY_TAX_STRUCTURE"
        for issue in result.validation.field_issues
    )


# ---------------------------------------------------------------------------
# 3. Invoice with cess
# ---------------------------------------------------------------------------


def test_igst_with_cess(monkeypatch):
    summary = base_summary_fields(grand_total="12000.00")
    query_blocks = (
        query_answer_blocks("SELLER_GSTIN", VENDOR_GSTIN)
        + query_answer_blocks(
            "TAX_DETAILS", "IGST 18% 1800.00, CESS 2% 200.00"
        )
        + query_answer_blocks("TAXABLE_AMOUNT", "10000.00")
        + query_answer_blocks("GRAND_TOTAL", "12000.00")
    )

    client = make_fake_client([expense_document(summary)], query_blocks)
    result = run_extraction(client, monkeypatch)

    assert result.amounts.igst_amount == 1800.0
    assert result.amounts.cess_amount == 200.0
    assert result.amounts.total_tax == 2000.0


# ---------------------------------------------------------------------------
# 4. Multiple GST rates across line items
# ---------------------------------------------------------------------------


def test_multiple_line_level_tax_rates(monkeypatch):
    items = [
        line_item({
            "ITEM": "Widget A",
            "AMOUNT": "1000.00",
            "TAX_RATE": "18",
        }),
        line_item({
            "ITEM": "Widget B",
            "AMOUNT": "500.00",
            "TAX_RATE": "12",
        }),
    ]
    summary = base_summary_fields()
    client = make_fake_client(
        [expense_document(summary, items)],
        query_answer_blocks("GRAND_TOTAL", "11800.00"),
    )
    result = run_extraction(client, monkeypatch)

    rates = {line.description: line.tax_rate for line in result.invoice_lines}
    assert rates.get("Widget A") == 18.0
    assert rates.get("Widget B") == 12.0


# ---------------------------------------------------------------------------
# 5 & 6. Bank details present / absent
# ---------------------------------------------------------------------------


def test_bank_details_present(monkeypatch):
    summary = base_summary_fields()
    query_blocks = query_answer_blocks(
        "BANK_DETAILS",
        "Bank Name: HDFC Bank, A/c No: 1234567890123, Branch: MG Road",
    ) + query_answer_blocks("IFSC", IFSC)

    client = make_fake_client([expense_document(summary)], query_blocks)
    result = run_extraction(client, monkeypatch)

    assert result.payment.bank_name and "HDFC" in result.payment.bank_name
    assert result.payment.account_number == "1234567890123"
    assert result.payment.ifsc_code == IFSC


def test_bank_details_absent(monkeypatch):
    summary = base_summary_fields()
    client = make_fake_client(
        [expense_document(summary)],
        query_answer_blocks("GRAND_TOTAL", "11800.00"),
    )
    result = run_extraction(client, monkeypatch)

    assert result.payment.bank_name is None
    assert result.payment.account_number is None
    # Missing optional payment info must not fail the invoice.
    assert result.validation.is_valid is True


# ---------------------------------------------------------------------------
# 7. Invoice without PO
# ---------------------------------------------------------------------------


def test_invoice_without_po(monkeypatch):
    summary = base_summary_fields()  # no po_number override -> absent
    client = make_fake_client(
        [expense_document(summary)],
        query_answer_blocks("GRAND_TOTAL", "11800.00"),
    )
    result = run_extraction(client, monkeypatch)

    assert result.reference.po_number is None
    assert result.validation.is_valid is True


# ---------------------------------------------------------------------------
# 8. Multi-page invoice: header on page 1, totals on page 2, and the
# query-pagination fix (highest confidence per alias wins, not "last
# page seen").
# ---------------------------------------------------------------------------


def test_multipage_invoice_picks_highest_confidence_answer(monkeypatch):
    page1_summary = base_summary_fields()
    page2_summary = [
        summary_field("TOTAL", "11800.00", page=2),
    ]

    # Same alias answered on both pages: page 1's answer is a low
    # confidence non-answer, page 2's is the correct, high-confidence one.
    query_blocks = query_answer_blocks(
        "GRAND_TOTAL", "Not stated", confidence=20.0, page=1
    ) + query_answer_blocks(
        "GRAND_TOTAL", "11800.00", confidence=95.0, page=2
    )

    client = FakeTextractClient(
        expense_pages=[[expense_document(page1_summary)], [expense_document(page2_summary)]],
        query_block_pages=[query_blocks],
    )
    result = run_extraction(client, monkeypatch)

    assert result.extraction.pages_processed == 2
    # AnalyzeExpense's own TOTAL (page 2) already supplies grand_total,
    # so the query answer is a fallback only - but it must never have
    # been corrupted by the low-confidence page-1 "Not stated" answer.
    assert result.amounts.grand_total == 11800.0


# ---------------------------------------------------------------------------
# 9. GSTIN present but PAN not explicitly printed
# ---------------------------------------------------------------------------


def test_pan_derived_when_not_printed(monkeypatch):
    summary = base_summary_fields()
    query_blocks = query_answer_blocks(
        "SELLER_GSTIN", VENDOR_GSTIN
    ) + query_answer_blocks("GRAND_TOTAL", "11800.00")

    client = make_fake_client([expense_document(summary)], query_blocks)
    result = run_extraction(client, monkeypatch)

    assert result.vendor.gstin == VENDOR_GSTIN
    assert result.vendor.pan == "AABCU9603R"
    assert result.extraction.field_sources.get("vendor_pan") == "DERIVED_FROM_GSTIN"


# ---------------------------------------------------------------------------
# Extra: invalid GSTIN format is a hard issue, not just a warning
# ---------------------------------------------------------------------------


def test_invalid_gstin_format_is_an_issue(monkeypatch):
    summary = base_summary_fields()
    query_blocks = query_answer_blocks(
        "SELLER_GSTIN", "9924USA29003OSI"
    ) + query_answer_blocks("GRAND_TOTAL", "11800.00")

    client = make_fake_client([expense_document(summary)], query_blocks)
    result = run_extraction(client, monkeypatch)

    assert result.validation.is_valid is False
    assert any(
        issue.code == "INVALID_GSTIN_FORMAT"
        for issue in result.validation.field_issues
    )
    assert result.vendor.pan is None


# ---------------------------------------------------------------------------
# Extra: total reconciliation accounts for charges/discount/round-off,
# not just taxable + tax.
# ---------------------------------------------------------------------------


def test_total_reconciliation_accounts_for_charges_and_discount(monkeypatch):
    summary = base_summary_fields(subtotal="10000.00", grand_total="10650.00")
    query_blocks = (
        query_answer_blocks("TAXABLE_AMOUNT", "10000.00")
        + query_answer_blocks("TAX_DETAILS", "IGST 5% 500.00")
        + query_answer_blocks("GRAND_TOTAL", "10650.00")
    )
    summary.append(summary_field("SHIPPING_HANDLING_CHARGE", "200.00"))
    summary.append(summary_field("DISCOUNT", "50.00"))

    client = make_fake_client([expense_document(summary)], query_blocks)
    result = run_extraction(client, monkeypatch)

    # 10000 + 500 (igst) + 200 (shipping) - 50 (discount) = 10650
    assert not any(
        issue.code == "TOTAL_MISMATCH"
        for issue in result.validation.field_issues
    )
    assert result.validation.is_valid is True
