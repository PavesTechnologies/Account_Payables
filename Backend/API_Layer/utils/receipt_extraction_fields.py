# Backend/API_Layer/utils/receipt_extraction_fields.py
"""Payment receipt / bank advice extraction (APM_AUTOMATION_PLAN.md 3.3, Phase 4).

Reuses the shared Textract QUERIES runner (run_document_analysis_queries) exactly like agreement
and quotation extraction. Returns *suggestions only* - nothing is persisted; the user reviews the
pre-filled Record Payment form and submits it through the existing endpoint.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import BotoCoreError, ClientError

from Backend.API_Layer.utils.agreement_extraction_fields import parse_agreement_date
from Backend.API_Layer.utils.invoice_extraction_fields import clean_text, run_document_analysis_queries
from Backend.Business_Layer.utils.exceptions import TextractServiceError

RECEIPT_QUERIES = [
    ("What is the transaction date or payment date?", "PAYMENT_DATE"),
    ("What is the amount paid or transferred?", "AMOUNT"),
    ("What is the UTR number?", "UTR"),
    ("What is the transaction reference number or transaction ID?", "REFERENCE"),
    ("What is the payment mode such as NEFT, RTGS, IMPS, UPI or cheque?", "MODE"),
    ("What is the cheque number?", "CHEQUE_NUMBER"),
    ("Who is the beneficiary or payee name?", "BENEFICIARY_NAME"),
    ("What is the beneficiary account number?", "BENEFICIARY_ACCOUNT"),
    ("What is the beneficiary IFSC code?", "BENEFICIARY_IFSC"),
    ("What is the status of the transaction?", "STATUS"),
]

MODES = ("NEFT", "RTGS", "IMPS", "UPI", "CHEQUE", "DEMAND_DRAFT", "BANK_TRANSFER")
_MODE_PATTERNS = (
    ("RTGS", re.compile(r"\bRTGS\b", re.I)),
    ("NEFT", re.compile(r"\bNEFT\b", re.I)),
    ("IMPS", re.compile(r"\bIMPS\b", re.I)),
    ("UPI", re.compile(r"\bUPI\b|@\w+\b.*\bVPA\b|\bVPA\b", re.I)),
    ("DEMAND_DRAFT", re.compile(r"\bdemand\s+draft\b|\bDD\s*(?:no|number)\b", re.I)),
    ("CHEQUE", re.compile(r"\bcheque\b|\bchq\b", re.I)),
)
_FAILED = re.compile(r"\b(failed|failure|rejected|reversed|returned|unsuccessful|declined)\b", re.I)
_PENDING = re.compile(r"\b(pending|in\s+process|processing|initiated|scheduled|awaiting)\b", re.I)
_SUCCESS = re.compile(r"\b(success(ful)?|completed|processed|credited|paid|executed)\b", re.I)
_AMOUNT = re.compile(r"(?:₹|INR|Rs\.?)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)
_UTR_IN_TEXT = re.compile(r"\b(?:UTR|U\.T\.R\.?)\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([A-Z0-9]{12,22})\b", re.I)
_RRN_IN_TEXT = re.compile(r"\b(?:RRN|UPI\s*Ref(?:erence)?\s*(?:No\.?)?|Transaction\s*ID)\s*[:\-]?\s*([0-9]{12})\b", re.I)


def _value(results: Dict[str, Dict[str, Any]], alias: str) -> Tuple[Optional[str], float]:
    hit = results.get(alias)
    if not hit:
        return None, 0.0
    return clean_text(hit.get("value")), float(hit.get("confidence") or 0.0)


def parse_amount(text: Optional[str]) -> Optional[Decimal]:
    if not text:
        return None
    match = _AMOUNT.search(text) or re.search(r"([0-9][0-9,]*(?:\.\d{1,2})?)", text)
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    return value.quantize(Decimal("0.01")) if value > 0 else None


def detect_mode(*texts: Optional[str]) -> Optional[str]:
    blob = " ".join(t for t in texts if t)
    for mode, pattern in _MODE_PATTERNS:
        if pattern.search(blob):
            return mode
    return None


def detect_status(*texts: Optional[str]) -> Optional[str]:
    blob = " ".join(t for t in texts if t)
    if _FAILED.search(blob):
        return "FAILED"
    if _PENDING.search(blob):
        return "PENDING"
    if _SUCCESS.search(blob):
        return "SUCCESS"
    return None


def _clean_reference(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return cleaned or None


def mask_account(value: Optional[str]) -> Optional[str]:
    digits = re.sub(r"\D", "", value or "")
    return f"XXXX{digits[-4:]}" if len(digits) >= 4 else None


def parse_receipt_fields(results: Dict[str, Dict[str, Any]], full_text: str) -> Dict[str, Any]:
    """{field: {"value": ..., "confidence": 0-100}} for the Record Payment form, plus context."""
    out: Dict[str, Dict[str, Any]] = {}

    raw_date, date_conf = _value(results, "PAYMENT_DATE")
    parsed_date: Optional[date] = parse_agreement_date(raw_date)
    out["payment_date"] = {"value": parsed_date.isoformat() if parsed_date else None, "confidence": date_conf if parsed_date else 0.0}

    raw_amount, amount_conf = _value(results, "AMOUNT")
    amount = parse_amount(raw_amount)
    out["amount"] = {"value": str(amount) if amount is not None else None, "confidence": amount_conf if amount else 0.0}

    raw_mode, mode_conf = _value(results, "MODE")
    mode = detect_mode(raw_mode) or detect_mode(full_text)
    out["payment_mode"] = {"value": mode, "confidence": mode_conf if detect_mode(raw_mode) else (60.0 if mode else 0.0)}

    reference, ref_conf = None, 0.0
    if mode in ("CHEQUE", "DEMAND_DRAFT"):
        value, conf = _value(results, "CHEQUE_NUMBER")
        reference, ref_conf = _clean_reference(value), conf
    if not reference:
        for alias in ("UTR", "REFERENCE"):
            value, conf = _value(results, alias)
            if _clean_reference(value):
                reference, ref_conf = _clean_reference(value), conf
                break
    if not reference:
        match = _UTR_IN_TEXT.search(full_text or "") or _RRN_IN_TEXT.search(full_text or "")
        if match:
            reference, ref_conf = match.group(1).upper(), 55.0
    out["reference_number"] = {"value": reference, "confidence": ref_conf if reference else 0.0}

    beneficiary, ben_conf = _value(results, "BENEFICIARY_NAME")
    account, _ = _value(results, "BENEFICIARY_ACCOUNT")
    ifsc, _ = _value(results, "BENEFICIARY_IFSC")
    status_text, _ = _value(results, "STATUS")
    return {
        "fields": out,
        "beneficiary_name": beneficiary,
        "beneficiary_name_confidence": ben_conf,
        "beneficiary_account_masked": mask_account(account),
        "beneficiary_ifsc": (re.sub(r"\s", "", ifsc).upper() if ifsc else None),
        # The STATUS answer decides; whole-page wording only counts for an explicit failure, since
        # "paid", "initiated", "scheduled" appear in ordinary receipt text.
        "transaction_status": detect_status(status_text) if status_text else ("FAILED" if _FAILED.search(full_text or "") else None),
    }


async def extract_receipt_from_s3(s3_key: str) -> Dict[str, Any]:
    try:
        results, full_text = await asyncio.to_thread(run_document_analysis_queries, s3_key, RECEIPT_QUERIES)
    except (BotoCoreError, ClientError) as exc:
        raise TextractServiceError(f"Receipt extraction failed: {exc}") from exc
    return parse_receipt_fields(results, full_text)
