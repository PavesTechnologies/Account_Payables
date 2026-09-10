# Backend/tests/test_quotation_extraction_fields.py
"""Unit tests for the quotation Textract query pipeline and field
normalization. The AWS call path (run_document_analysis_queries) is
shared with the invoice pipeline and already covered by
test_invoice_extraction_fields.py - these tests focus on the
quotation-specific query wiring and normalization/fallback rules."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

import Backend.API_Layer.utils.invoice_extraction_fields as invoice_fields
import Backend.API_Layer.utils.quotation_extraction_fields as qfields


# ---------------------------------------------------------------------------
# Fake Textract client (StartDocumentAnalysis/GetDocumentAnalysis only)
# ---------------------------------------------------------------------------


class FakeQueryClient:

    def __init__(self, blocks: List[Dict[str, Any]], job_status: str = "SUCCEEDED"):
        self._blocks = blocks
        self._job_status = job_status

    def start_document_analysis(self, **kwargs):
        return {"JobId": "quotation-query-job"}

    def get_document_analysis(self, **kwargs):
        return {"JobStatus": self._job_status, "Blocks": self._blocks}


_id_counter = {"n": 0}


def _next_id(prefix: str) -> str:
    _id_counter["n"] += 1
    return f"{prefix}-{_id_counter['n']}"


def query_answer_blocks(alias: str, text: str, confidence: float = 90.0) -> List[Dict[str, Any]]:
    query_id = _next_id("query")
    result_id = _next_id("result")
    return [
        {
            "BlockType": "QUERY",
            "Id": query_id,
            "Page": 1,
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


def line_block(text: str) -> Dict[str, Any]:
    return {
        "BlockType": "LINE",
        "Id": _next_id("line"),
        "Text": text,
        "Page": 1,
        "Geometry": {"BoundingBox": {"Top": 0.0}},
    }


# ---------------------------------------------------------------------------
# run_quotation_queries - end-to-end query wiring
# ---------------------------------------------------------------------------


def test_run_quotation_queries_extracts_all_fields(monkeypatch):
    blocks: List[Dict[str, Any]] = []
    blocks += query_answer_blocks("VENDOR_NAME", "ABC Technologies Pvt Ltd")
    blocks += query_answer_blocks("QUOTATION_NUMBER", "QT-2026-00125")
    blocks += query_answer_blocks("TOTAL_AMOUNT", "Rs. 1,25,000.00")
    blocks += query_answer_blocks("QUOTATION_DATE", "09/09/2026")
    blocks += query_answer_blocks("VALID_UNTIL", "30/09/2026")
    blocks += query_answer_blocks("DELIVERY_DAYS", "15 Days")
    blocks += query_answer_blocks("PAYMENT_TERMS", "Net 30")

    monkeypatch.setattr(invoice_fields, "textract_client", FakeQueryClient(blocks))

    query_results, _ = qfields.run_quotation_queries("quotations/test.pdf")
    extracted, confidence = qfields.parse_quotation_fields(query_results, full_text="")

    assert extracted["vendor_name"] == "ABC Technologies Pvt Ltd"
    assert extracted["quotation_number"] == "QT-2026-00125"
    assert extracted["total_amount"] == pytest.approx(125000.00)
    assert str(extracted["quotation_date"]) == "2026-09-09"
    assert str(extracted["valid_until"]) == "2026-09-30"
    assert extracted["delivery_days"] == 15
    assert extracted["payment_terms"] == "Net 30"
    assert confidence["vendor_name"] == 90.0


def test_run_quotation_queries_raises_on_failed_job(monkeypatch):
    monkeypatch.setattr(
        invoice_fields, "textract_client", FakeQueryClient([], job_status="FAILED")
    )

    with pytest.raises(RuntimeError):
        qfields.run_quotation_queries("quotations/test.pdf")


def test_run_quotation_queries_times_out(monkeypatch):
    monkeypatch.setattr(
        invoice_fields, "textract_client", FakeQueryClient([], job_status="IN_PROGRESS")
    )
    monkeypatch.setattr(invoice_fields.time, "sleep", lambda *_: None)

    call_count = {"n": 0}

    def fake_monotonic():
        call_count["n"] += 1
        # First call establishes start_time; every call after jumps
        # straight past the 300s timeout threshold.
        return 0.0 if call_count["n"] == 1 else 301.0

    monkeypatch.setattr(invoice_fields.time, "monotonic", fake_monotonic)

    with pytest.raises(TimeoutError):
        qfields.run_quotation_queries("quotations/test.pdf")


# ---------------------------------------------------------------------------
# Partial extraction / missing fields
# ---------------------------------------------------------------------------


def test_parse_quotation_fields_partial_when_answers_missing():
    query_results = {
        "VENDOR_NAME": {"value": "ABC Technologies Pvt Ltd", "confidence": 96.0},
        "QUOTATION_NUMBER": {"value": "QT-2026-00125", "confidence": 99.0},
    }

    extracted, confidence = qfields.parse_quotation_fields(query_results, full_text="")

    assert extracted["vendor_name"] == "ABC Technologies Pvt Ltd"
    assert extracted["quotation_number"] == "QT-2026-00125"
    assert "total_amount" not in extracted
    assert "quotation_date" not in extracted
    assert "delivery_days" not in extracted


def test_parse_quotation_fields_empty_when_no_answers():
    extracted, confidence = qfields.parse_quotation_fields({}, full_text=None)

    assert extracted == {}
    assert confidence == {}


# ---------------------------------------------------------------------------
# quotation_number regex fallback
# ---------------------------------------------------------------------------


def test_quotation_number_regex_fallback_from_full_text():
    full_text = "Quote No: QT/2026/0099\nVendor: Some Vendor"

    extracted, confidence = qfields.parse_quotation_fields({}, full_text=full_text)

    assert extracted["quotation_number"] == "QT/2026/0099"
    assert confidence["quotation_number"] == 75.0


def test_delivery_days_regex_fallback_from_full_text():
    full_text = "Delivery Time: 20 Days\nSome other line"

    extracted, confidence = qfields.parse_quotation_fields({}, full_text=full_text)

    assert extracted["delivery_days"] == 20


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("15 Days", 15),
        ("Within 15 days", 15),
        ("15", 15),
        (7, 7),
        (None, None),
        ("No delivery info", None),
        (True, None),
    ],
)
def test_normalize_delivery_days(raw, expected):
    assert qfields.normalize_delivery_days(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Rs. 1,25,000.00", 125000.00),
        ("$1,000.50", 1000.50),
        ("(1000.00)", -1000.00),
        ("125000", 125000.0),
        ("not a number", None),
        (None, None),
    ],
)
def test_normalize_total_amount(raw, expected):
    result = qfields.normalize_total_amount(raw)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("09/09/2026", "2026-09-09"),
        ("2026-09-09", "2026-09-09"),
        ("09-Sep-2026", "2026-09-09"),
        ("not a date", None),
        (None, None),
    ],
)
def test_normalize_quotation_date(raw, expected):
    result = qfields.normalize_quotation_date(raw)
    assert (str(result) if result else None) == expected


def test_normalize_quotation_number_preserves_hyphens_and_slashes():
    assert qfields.normalize_quotation_number(" QT-2026/00125 ") == "QT-2026/00125"


def test_normalize_payment_terms_trims_whitespace():
    assert qfields.normalize_payment_terms("  Net 30  ") == "Net 30"
