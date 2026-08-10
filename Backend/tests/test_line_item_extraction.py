# Backend/tests/test_line_item_extraction.py
"""Tests for the geometry-based line-item extractor.

Builds synthetic tables with fixed per-column x-positions (unlike
invoice_builder.build_document, which lays out anchor-style fields and
doesn't keep columns aligned across rows) so header inference and
row-to-column assignment can be exercised deterministically.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Sequence

from Backend.API_Layer.interface.invoice_process_interface import DocumentResult, Page, Word
from Backend.Business_Layer.utils.extraction.line_items import extract_invoice_lines

_DEFAULT_COL_X = (40.0, 100.0, 400.0, 480.0, 580.0)


def _row_words(cells: Sequence[str], y: float, col_x: Sequence[float]) -> List[Word]:
    words: List[Word] = []
    for x0, cell in zip(col_x, cells):
        if not cell:
            continue
        x = x0
        for token in cell.split(" "):
            if not token:
                continue
            width = max(len(token) * 7.0, 6.0)
            words.append(Word(text=token, x0=x, y0=y, x1=x + width, y1=y + 12.0, confidence=98.0))
            x += width + 4.0
    return words


def _build_line_item_document(
    pages_rows: List[List[Sequence[str]]], col_x: Sequence[float] = _DEFAULT_COL_X
) -> DocumentResult:
    pages = []
    for page_number, rows in enumerate(pages_rows, start=1):
        words: List[Word] = []
        y = 50.0
        for row in rows:
            words.extend(_row_words(row, y, col_x))
            y += 40.0
        pages.append(Page(page_number=page_number, width=900.0, height=y + 100.0, words=words))
    return DocumentResult(source_filename="invoice.pdf", page_count=len(pages), pages=pages)


HEADER = ["S.No", "Description", "Qty", "Rate", "Amount"]


def test_normal_item_table_with_indian_amounts_and_footer_rows():
    rows = [
        HEADER,
        ["1", "Laptop", "2", "50,000.00", "1,00,000.00"],
        ["2", "Mouse", "5", "1,000.00", "5,000.00"],
        ["", "Subtotal", "", "", "1,05,000.00"],
        ["", "Grand Total", "", "", "1,05,000.00"],
    ]
    document = _build_line_item_document([rows])

    lines = extract_invoice_lines(document)

    assert len(lines) == 2
    assert lines[0].line_number == 1
    assert lines[0].description == "Laptop"
    assert lines[0].quantity == Decimal("2")
    assert lines[0].unit_price == Decimal("50000.00")
    assert lines[0].line_amount == Decimal("100000.00")
    assert lines[0].confidence == 1.0

    assert lines[1].line_number == 2
    assert lines[1].description == "Mouse"
    assert lines[1].line_amount == Decimal("5000.00")


def test_multi_line_description_merges_into_one_item():
    rows = [
        HEADER,
        ["1", "Laptop Computer", "", "", ""],
        ["", "Intel i7 processor", "", "", ""],
        ["", "", "2", "50,000.00", "1,00,000.00"],
        ["", "Subtotal", "", "", "1,00,000.00"],
    ]
    document = _build_line_item_document([rows])

    lines = extract_invoice_lines(document)

    assert len(lines) == 1
    assert lines[0].description == "Laptop Computer Intel i7 processor"
    assert lines[0].quantity == Decimal("2")
    assert lines[0].line_amount == Decimal("100000.00")


def test_multi_page_table_continues_numbering_and_skips_repeated_header():
    page1 = [HEADER, ["1", "Laptop", "2", "50000.00", "100000.00"]]
    page2 = [HEADER, ["2", "Mouse", "5", "1000.00", "5000.00"], ["", "Grand Total", "", "", "105000.00"]]
    document = _build_line_item_document([page1, page2])

    lines = extract_invoice_lines(document)

    assert [line.line_number for line in lines] == [1, 2]
    assert lines[0].description == "Laptop"
    assert lines[1].description == "Mouse"


def test_service_invoice_without_quantity_or_unit_price_column():
    header = ["S.No", "Description", "Amount"]
    col_x = (40.0, 100.0, 400.0)
    rows = [
        header,
        ["1", "Consulting services", "50,000.00"],
        ["2", "Support services", "25,000.00"],
        ["", "Grand Total", "75,000.00"],
    ]
    document = _build_line_item_document([rows], col_x=col_x)

    lines = extract_invoice_lines(document)

    assert len(lines) == 2
    assert lines[0].description == "Consulting services"
    assert lines[0].quantity is None
    assert lines[0].unit_price is None
    assert lines[0].line_amount == Decimal("50000.00")
    # description + amount present, quantity/unit_price absent -> partial confidence
    assert 0 < lines[0].confidence < 1.0


def test_amount_only_row_within_full_table_is_kept_at_lower_confidence():
    rows = [
        HEADER,
        ["1", "Laptop", "2", "50,000.00", "1,00,000.00"],
        ["", "Freight charges", "", "", "500.00"],
        ["", "Subtotal", "", "", "1,00,500.00"],
    ]
    document = _build_line_item_document([rows])

    lines = extract_invoice_lines(document)

    assert len(lines) == 2
    assert lines[1].description == "Freight charges"
    assert lines[1].quantity is None
    assert lines[1].unit_price is None
    assert lines[1].line_amount == Decimal("500.00")
    assert lines[1].confidence < lines[0].confidence


def test_no_table_header_yields_no_lines():
    document = _build_line_item_document([[["Some", "random", "text", "", ""]]])

    lines = extract_invoice_lines(document)

    assert lines == []


def test_extraction_never_raises_on_malformed_document():
    document = DocumentResult(source_filename="empty.pdf", page_count=0, pages=[])

    lines = extract_invoice_lines(document)

    assert lines == []
