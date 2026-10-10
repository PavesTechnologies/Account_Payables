# Backend/API_Layer/utils/tds_document_extraction.py
"""TDS challan (ITNS 281 / OLTAS counterfoil) and quarterly statement acknowledgement extraction
(APM_AUTOMATION_PLAN.md 3.4, Phase 5). Same shared Textract QUERIES runner as receipts and
agreements. Suggestions only - nothing is persisted here."""
from __future__ import annotations

import asyncio
import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import BotoCoreError, ClientError

from Backend.API_Layer.utils.agreement_extraction_fields import parse_agreement_date
from Backend.API_Layer.utils.invoice_extraction_fields import clean_text, run_document_analysis_queries
from Backend.API_Layer.utils.receipt_extraction_fields import parse_amount
from Backend.Business_Layer.utils.exceptions import TextractServiceError

CHALLAN_QUERIES = [
    ("What is the challan serial number?", "SERIAL"),
    ("What is the BSR code?", "BSR"),
    ("What is the date of deposit or tender date?", "DEPOSIT_DATE"),
    ("What is the CIN or challan identification number?", "CIN"),
    ("What is the TAN?", "TAN"),
    ("What is the assessment year?", "AY"),
    ("What is the minor head code?", "MINOR_HEAD"),
    ("What is the nature of payment or section code?", "SECTION"),
    ("What is the income tax or basic tax amount?", "TAX"),
    ("What is the surcharge amount?", "SURCHARGE"),
    ("What is the education cess amount?", "CESS"),
    ("What is the interest amount?", "INTEREST"),
    ("What is the fee or penalty amount?", "FEE"),
    ("What is the total amount paid?", "TOTAL"),
]

FILING_QUERIES = [
    ("What is the token number or provisional receipt number?", "ACK"),
    ("What is the date of filing or date of acceptance?", "FILING_DATE"),
    ("What is the form number?", "FORM"),
    ("What is the financial year?", "FY"),
    ("What is the quarter?", "QUARTER"),
    ("What is the TAN?", "TAN"),
    ("Is this a regular or correction statement?", "KIND"),
]

_TAN = re.compile(r"\b([A-Z]{4}[0-9]{5}[A-Z])\b")
# CIN: BSR (7) + DDMMYYYY (8) + serial (5)
_CIN = re.compile(r"\b([0-9]{7})\s*([0-3][0-9][01][0-9]20[0-9]{2})\s*([0-9]{5})\b")
_FORM = re.compile(r"\b(26Q|27Q|24Q|27EQ)\b", re.I)
_FY = re.compile(r"\b(20[0-9]{2})\s*[-/]\s*(?:20)?([0-9]{2})\b")
_QUARTER = re.compile(r"\bQ\s*([1-4])\b|\bquarter\s*([1-4])\b", re.I)
_ACK = re.compile(r"\b([0-9]{15})\b")
_SECTION = re.compile(r"\b(?:1?9[2-6][A-Z]{0,3}|206C[A-Z]?)\b")


def _value(results: Dict[str, Dict[str, Any]], alias: str) -> Tuple[Optional[str], float]:
    hit = results.get(alias)
    if not hit:
        return None, 0.0
    return clean_text(hit.get("value")), float(hit.get("confidence") or 0.0)


def _field(value, confidence) -> Dict[str, Any]:
    return {"value": value, "confidence": confidence if value not in (None, "") else 0.0}


def _digits(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


def parse_cin(text: Optional[str]) -> Optional[Dict[str, Any]]:
    match = _CIN.search(re.sub(r"[^0-9 ]", " ", text or ""))
    if not match:
        return None
    bsr, ddmmyyyy, serial = match.groups()
    try:
        deposited = date(int(ddmmyyyy[4:]), int(ddmmyyyy[2:4]), int(ddmmyyyy[:2]))
    except ValueError:
        return None
    return {"bsr_code": bsr, "deposit_date": deposited, "challan_serial_no": serial}


def build_cin(bsr: str, deposit_date: date, serial: str) -> str:
    return f"{bsr}{deposit_date:%d%m%Y}{str(serial).zfill(5)}"


def parse_challan_fields(results: Dict[str, Dict[str, Any]], full_text: str) -> Dict[str, Any]:
    out: Dict[str, Dict[str, Any]] = {}
    cin_text, cin_conf = _value(results, "CIN")
    cin = parse_cin(cin_text) or parse_cin(full_text)

    serial, serial_conf = _value(results, "SERIAL")
    serial = _digits(serial)[-5:] or (cin["challan_serial_no"] if cin else None)
    out["challan_serial_no"] = _field(serial.zfill(5) if serial else None, serial_conf or (cin_conf if cin else 0.0))

    bsr, bsr_conf = _value(results, "BSR")
    bsr = _digits(bsr) if len(_digits(bsr)) == 7 else (cin["bsr_code"] if cin else None)
    out["bsr_code"] = _field(bsr, bsr_conf or (cin_conf if cin else 0.0))

    raw_date, date_conf = _value(results, "DEPOSIT_DATE")
    deposited = parse_agreement_date(raw_date) or (cin["deposit_date"] if cin else None)
    out["deposit_date"] = _field(deposited.isoformat() if deposited else None, date_conf or (cin_conf if cin else 0.0))

    tan, tan_conf = _value(results, "TAN")
    tan_match = _TAN.search((tan or "").upper()) or _TAN.search((full_text or "").upper())
    out["tan"] = _field(tan_match.group(1) if tan_match else None, tan_conf if tan_match else 0.0)

    ay, ay_conf = _value(results, "AY")
    ay_match = _FY.search(ay or "")
    out["assessment_year"] = _field(f"{ay_match.group(1)}-{ay_match.group(2)}" if ay_match else None, ay_conf)

    minor, minor_conf = _value(results, "MINOR_HEAD")
    minor = next((code for code in ("200", "400") if code in (minor or "")), None)
    out["minor_head"] = _field(minor, minor_conf)

    section, section_conf = _value(results, "SECTION")
    section_match = _SECTION.search((section or "").upper().replace(" ", ""))
    out["section_code"] = _field(section_match.group(0) if section_match else None, section_conf)

    for key, alias in (("tax_amount", "TAX"), ("surcharge", "SURCHARGE"), ("cess", "CESS"),
                       ("interest", "INTEREST"), ("fee", "FEE"), ("total_amount", "TOTAL")):
        raw, conf = _value(results, alias)
        amount = parse_amount(raw)
        out[key] = _field(str(amount) if amount is not None else None, conf)

    cin_value = build_cin(bsr, deposited, serial) if (bsr and deposited and serial) else None
    cin_mismatch = bool(cin and cin_value and build_cin(cin["bsr_code"], cin["deposit_date"], cin["challan_serial_no"]) != cin_value)
    return {"fields": out, "cin": cin_value, "cin_mismatch": cin_mismatch}


def parse_filing_fields(results: Dict[str, Dict[str, Any]], full_text: str) -> Dict[str, Any]:
    out: Dict[str, Dict[str, Any]] = {}
    ack, ack_conf = _value(results, "ACK")
    ack_match = _ACK.search(_digits(ack) and ack or "") or _ACK.search(full_text or "")
    out["acknowledgement_no"] = _field(ack_match.group(1) if ack_match else (_digits(ack) or None), ack_conf)

    raw_date, date_conf = _value(results, "FILING_DATE")
    filed = parse_agreement_date(raw_date)
    out["filing_date"] = _field(filed.isoformat() if filed else None, date_conf)

    form, form_conf = _value(results, "FORM")
    form_match = _FORM.search(form or "") or _FORM.search(full_text or "")
    out["form_type"] = _field(form_match.group(1).upper() if form_match else None, form_conf if form_match else 0.0)

    fy, fy_conf = _value(results, "FY")
    fy_match = _FY.search(fy or "")
    out["financial_year"] = _field(f"{fy_match.group(1)}-{fy_match.group(2)}" if fy_match else None, fy_conf)

    quarter, q_conf = _value(results, "QUARTER")
    q_match = _QUARTER.search(quarter or "") or _QUARTER.search(full_text or "")
    q_value = int(next(g for g in q_match.groups() if g)) if q_match else None
    out["quarter"] = _field(q_value, q_conf if q_match else 0.0)

    tan, tan_conf = _value(results, "TAN")
    tan_match = _TAN.search((tan or "").upper()) or _TAN.search((full_text or "").upper())
    out["tan"] = _field(tan_match.group(1) if tan_match else None, tan_conf if tan_match else 0.0)

    kind, _ = _value(results, "KIND")
    return {"fields": out, "is_revision": bool(kind and re.search(r"correct|revis", kind, re.I))}


async def _run(s3_key: str, queries):
    try:
        return await asyncio.to_thread(run_document_analysis_queries, s3_key, queries)
    except (BotoCoreError, ClientError) as exc:
        raise TextractServiceError(f"Document extraction failed: {exc}") from exc


async def extract_challan_from_s3(s3_key: str) -> Dict[str, Any]:
    results, text = await _run(s3_key, CHALLAN_QUERIES)
    return parse_challan_fields(results, text)


async def extract_filing_from_s3(s3_key: str) -> Dict[str, Any]:
    results, text = await _run(s3_key, FILING_QUERIES)
    return parse_filing_fields(results, text)
