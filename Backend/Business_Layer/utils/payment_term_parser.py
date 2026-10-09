# Backend/Business_Layer/utils/payment_term_parser.py
"""Turns printed payment-terms text into (days, due basis).

Pure function, no DB access. Used by PaymentTermComplianceService for the
invoice-stated, PO and agreement terms alike, so all three are read the same
way. Deliberately conservative: anything that cannot be read as a single,
unambiguous number of days comes back as AMBIGUOUS / NONE so the caller flags
the invoice for review instead of guessing a default.

Recognised (case-insensitive):
  "Net 30", "Net-30", "30 days", "30 days credit", "within 15 days of invoice",
  "thirty (30) days", "Net 45 from GRN date", "45 days from delivery",
  "Immediate", "Due on receipt", "COD", "Advance"
  "2/10 Net 30", "2% 10 days, Net 30"  -> 30 (the net period wins over a
                                          discount window)
Ambiguous:
  "As agreed", "As per agreed terms", "30/60 days", "30 or 45 days", "30 days EOM", "> 365 days"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

KIND_DAYS = "DAYS"
KIND_IMMEDIATE = "IMMEDIATE"
KIND_ADVANCE = "ADVANCE"
KIND_AMBIGUOUS = "AMBIGUOUS"
KIND_NONE = "NONE"

BASIS_INVOICE_DATE = "INVOICE_DATE"
BASIS_GRN_DATE = "GRN_DATE"

MAX_TERM_DAYS = 365

_IMMEDIATE = re.compile(
    r"\bimmediate(ly)?\b|\bdue\s+(up)?on\s+receipt\b|\bon\s+receipt\b|\bupon\s+receipt\b|"
    r"\bcash\s+on\s+delivery\b|\bcod\b|\bpayable\s+on\s+demand\b",
    re.IGNORECASE,
)
_ADVANCE = re.compile(r"\b(100\s*%\s*)?advance\b|\bprepaid\b|\bpre-?payment\b", re.IGNORECASE)
_AGREED = re.compile(
    r"\bas\s+(per\s+)?(the\s+)?agreed\b|\bagreed\s+terms\b|\bas\s+per\s+(the\s+)?(agreement|contract|terms|po)\b|"
    r"\bmutually\s+agreed\b|\bas\s+discussed\b|\bto\s+be\s+agreed\b",
    re.IGNORECASE,
)
_EOM = re.compile(r"\beom\b|\bend\s+of\s+(the\s+)?month\b|\bmonth[-\s]end\b", re.IGNORECASE)
_NET = re.compile(r"\bnet\s*[-:]?\s*(\d{1,4})\b", re.IGNORECASE)
_DAYS = re.compile(r"(\d{1,4})\s*\)?\s*(?:calendar\s+|working\s+|business\s+)?days?\b", re.IGNORECASE)
_SLASHED = re.compile(r"\b\d{1,3}\s*/\s*\d{1,3}\s*days?\b", re.IGNORECASE)
# "30 or 45 days", "30-45 days", "30 to 60 days": a range is not a term.
_ALTERNATIVES = re.compile(r"\b\d{1,3}\s*(?:or|to|-|–)\s*\d{1,3}\s*days?\b", re.IGNORECASE)
_GRN_BASIS = re.compile(
    r"\bgrn\b|\bgoods\s+receipt\b|\breceipt\s+of\s+(the\s+)?(goods|material|materials)\b|\bdelivery\b|"
    r"\bdate\s+of\s+(receipt|acceptance)\s+of\s+(goods|material)",
    re.IGNORECASE,
)
_DISCOUNT_WINDOW = re.compile(r"\d+(\.\d+)?\s*%\s*(within\s+)?(\d{1,3})\s*days?", re.IGNORECASE)

_WORD_NUMBERS = {
    "seven": 7, "ten": 10, "fourteen": 14, "fifteen": 15, "twenty": 20, "twenty-one": 21, "twenty one": 21,
    "thirty": 30, "forty-five": 45, "forty five": 45, "sixty": 60, "seventy-five": 75, "ninety": 90,
}
_WORD_DAYS = re.compile(
    r"\b(" + "|".join(sorted((re.escape(w) for w in _WORD_NUMBERS), key=len, reverse=True)) + r")\s+days?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedPaymentTerms:
    days: Optional[int]
    basis: str
    kind: str
    source_text: Optional[str]

    @property
    def is_determinable(self) -> bool:
        return self.days is not None


def _basis(text: str) -> str:
    return BASIS_GRN_DATE if _GRN_BASIS.search(text) else BASIS_INVOICE_DATE


def parse_payment_terms(text: Optional[str]) -> ParsedPaymentTerms:
    if text is None or not str(text).strip():
        return ParsedPaymentTerms(None, BASIS_INVOICE_DATE, KIND_NONE, None)
    raw = str(text).strip()

    if _AGREED.search(raw) or _EOM.search(raw) or _SLASHED.search(raw) or _ALTERNATIVES.search(raw):
        return ParsedPaymentTerms(None, _basis(raw), KIND_AMBIGUOUS, raw)

    net = _NET.search(raw)
    if net:
        days = int(net.group(1))
        if days > MAX_TERM_DAYS:
            return ParsedPaymentTerms(None, _basis(raw), KIND_AMBIGUOUS, raw)
        return ParsedPaymentTerms(days, _basis(raw), KIND_DAYS, raw)

    # A discount window ("2% 10 days") is not the payment term; ignore it.
    scrubbed = _DISCOUNT_WINDOW.sub(" ", raw)
    numbers = {int(m.group(1)) for m in _DAYS.finditer(scrubbed)}
    numbers |= {_WORD_NUMBERS[m.group(1).lower()] for m in _WORD_DAYS.finditer(scrubbed)}
    if len(numbers) == 1:
        days = numbers.pop()
        if days > MAX_TERM_DAYS:
            return ParsedPaymentTerms(None, _basis(raw), KIND_AMBIGUOUS, raw)
        return ParsedPaymentTerms(days, _basis(raw), KIND_DAYS, raw)
    if len(numbers) > 1:
        return ParsedPaymentTerms(None, _basis(raw), KIND_AMBIGUOUS, raw)

    if _ADVANCE.search(raw):
        return ParsedPaymentTerms(0, BASIS_INVOICE_DATE, KIND_ADVANCE, raw)
    if _IMMEDIATE.search(raw):
        return ParsedPaymentTerms(0, BASIS_INVOICE_DATE, KIND_IMMEDIATE, raw)

    return ParsedPaymentTerms(None, _basis(raw), KIND_AMBIGUOUS, raw)
