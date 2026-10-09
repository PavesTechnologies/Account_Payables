"""Unit tests for Business_Layer/utils/payment_term_parser.py (pure, no DB)."""
import pytest

from Backend.Business_Layer.utils.payment_term_parser import (
    BASIS_GRN_DATE,
    BASIS_INVOICE_DATE,
    KIND_ADVANCE,
    KIND_AMBIGUOUS,
    KIND_DAYS,
    KIND_IMMEDIATE,
    KIND_NONE,
    parse_payment_terms,
)


@pytest.mark.parametrize(
    "text, days, basis",
    [
        ("Net 30", 30, BASIS_INVOICE_DATE),
        ("net-45", 45, BASIS_INVOICE_DATE),
        ("NET 15 DAYS", 15, BASIS_INVOICE_DATE),
        ("30 days", 30, BASIS_INVOICE_DATE),
        ("30 Days Credit", 30, BASIS_INVOICE_DATE),
        ("Payable within 15 days of invoice", 15, BASIS_INVOICE_DATE),
        ("within fifteen (15) days of receipt of a valid invoice", 15, BASIS_INVOICE_DATE),
        ("thirty days", 30, BASIS_INVOICE_DATE),
        ("Net 45 from GRN date", 45, BASIS_GRN_DATE),
        ("45 days from delivery", 45, BASIS_GRN_DATE),
        ("60 days from date of receipt of goods", 60, BASIS_GRN_DATE),
        ("2/10 Net 30", 30, BASIS_INVOICE_DATE),
        ("2% 10 days, Net 30", 30, BASIS_INVOICE_DATE),
        ("2% within 10 days, 30 days", 30, BASIS_INVOICE_DATE),
    ],
)
def test_definite_terms(text, days, basis):
    parsed = parse_payment_terms(text)
    assert parsed.kind == KIND_DAYS
    assert parsed.days == days
    assert parsed.basis == basis
    assert parsed.is_determinable


@pytest.mark.parametrize("text", ["Immediate", "Due on receipt", "Payment due upon receipt", "COD", "Cash on delivery"])
def test_immediate_terms_are_zero_days(text):
    parsed = parse_payment_terms(text)
    assert parsed.kind == KIND_IMMEDIATE
    assert parsed.days == 0
    assert parsed.basis == BASIS_INVOICE_DATE


def test_advance_is_zero_days():
    parsed = parse_payment_terms("100% advance")
    assert parsed.kind == KIND_ADVANCE
    assert parsed.days == 0


@pytest.mark.parametrize(
    "text",
    [
        "As agreed",
        "Payment as per agreed terms",
        "As per agreement",
        "30/60 days",
        "30 days EOM",
        "Net 30 end of month",
        "30 or 45 days",
        "400 days",
        "Please pay promptly",
    ],
)
def test_ambiguous_terms_are_never_guessed(text):
    parsed = parse_payment_terms(text)
    assert parsed.kind == KIND_AMBIGUOUS
    assert parsed.days is None
    assert not parsed.is_determinable


@pytest.mark.parametrize("text", [None, "", "   "])
def test_missing_terms(text):
    parsed = parse_payment_terms(text)
    assert parsed.kind == KIND_NONE
    assert parsed.days is None
    assert parsed.source_text is None
