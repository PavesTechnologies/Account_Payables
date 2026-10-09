# Backend/API_Layer/utils/agreement_extraction_fields.py
"""Vendor agreement / contract extraction (APM_AUTOMATION_PLAN.md 3.1a).

Reuses the shared Textract QUERIES runner (invoice_extraction_fields.
run_document_analysis_queries) exactly like quotation extraction does - same
AWS client, retry/backoff and polling. Returns *suggestions only*: nothing is
persisted here, and an agreement only becomes authoritative after a second
user verifies it (VendorAgreementService.verify).
"""
from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import BotoCoreError, ClientError

from Backend.API_Layer.utils.invoice_extraction_fields import (
    clean_text,
    find_gstin,
    normalize_date,
    run_document_analysis_queries,
)
from Backend.Business_Layer.utils.exceptions import TextractServiceError
from Backend.Business_Layer.utils.payment_term_parser import parse_payment_terms

AGREEMENT_QUERIES = [
    ("What is the title of this agreement or contract?", "AGREEMENT_TITLE"),
    ("What is the agreement or contract reference number?", "AGREEMENT_REFERENCE"),
    ("What is the effective date or start date of the agreement?", "VALID_FROM"),
    ("What is the expiry date or end date of the agreement?", "VALID_TO"),
    ("What are the payment terms for invoices?", "PAYMENT_TERMS"),
    ("Within how many days must invoices be paid?", "PAYMENT_DAYS"),
    ("What is the name of the vendor, lessor or service provider?", "VENDOR_NAME"),
    ("What is the GSTIN of the vendor, lessor or service provider?", "VENDOR_GSTIN"),
    ("Does the agreement renew automatically?", "AUTO_RENEW"),
]

_TYPE_KEYWORDS = (
    ("LEASE", ("lease", "rent", "leave and license", "tenancy")),
    ("SUBSCRIPTION", ("subscription", "saas", "order form", "licence", "license")),
    ("SOW", ("statement of work", "sow")),
    ("MSA", ("master service", "master services", "msa", "service agreement", "services agreement", "consulting")),
    ("RATE_CONTRACT", ("rate contract", "annual rate", "price agreement")),
)
_ORDINAL = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
_VALIDITY_RANGE = re.compile(
    r"valid\s+from\s+(.{6,30}?)\s+(?:to|till|until|through)\s+(.{6,30}?)(?:[.,;]|\s+unless|\s+and|$)",
    re.IGNORECASE,
)
_PAYMENT_SENTENCE = re.compile(r"[^.\n]*\b(pa(y|id|yable|yment))\b[^.\n]*\bdays?\b[^.\n]*[.\n]", re.IGNORECASE)


def _value(results: Dict[str, Dict[str, Any]], alias: str) -> Tuple[Optional[str], float]:
    hit = results.get(alias)
    if not hit:
        return None, 0.0
    return clean_text(hit.get("value")), float(hit.get("confidence") or 0.0)


def parse_agreement_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = _ORDINAL.sub(r"\1", str(value)).replace(",", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return normalize_date(text) or normalize_date(text.replace(" ", "-"))


def guess_agreement_type(*texts: Optional[str]) -> str:
    blob = " ".join(t for t in texts if t).lower()
    for agreement_type, keywords in _TYPE_KEYWORDS:
        if any(k in blob for k in keywords):
            return agreement_type
    return "OTHER"


def parse_agreement_fields(results: Dict[str, Dict[str, Any]], full_text: str) -> Dict[str, Any]:
    title, title_conf = _value(results, "AGREEMENT_TITLE")
    reference, reference_conf = _value(results, "AGREEMENT_REFERENCE")
    valid_from_raw, from_conf = _value(results, "VALID_FROM")
    valid_to_raw, to_conf = _value(results, "VALID_TO")
    terms, terms_conf = _value(results, "PAYMENT_TERMS")
    days_raw, days_conf = _value(results, "PAYMENT_DAYS")
    vendor_name, vendor_conf = _value(results, "VENDOR_NAME")
    gstin_raw, gstin_conf = _value(results, "VENDOR_GSTIN")
    renew_raw, renew_conf = _value(results, "AUTO_RENEW")

    valid_from, valid_to = parse_agreement_date(valid_from_raw), parse_agreement_date(valid_to_raw)
    if (valid_from is None or valid_to is None) and full_text:
        match = _VALIDITY_RANGE.search(full_text)
        if match:
            valid_from = valid_from or parse_agreement_date(match.group(1))
            valid_to = valid_to or parse_agreement_date(match.group(2))

    if not terms and full_text:
        sentence = _PAYMENT_SENTENCE.search(full_text)
        if sentence:
            terms, terms_conf = sentence.group(0).strip()[:500], 50.0

    parsed = parse_payment_terms(terms)
    if parsed.days is None and days_raw:
        parsed_days = parse_payment_terms(days_raw if "day" in days_raw.lower() else f"{days_raw} days")
        if parsed_days.days is not None:
            parsed = parsed_days

    gstin = find_gstin(gstin_raw or "") if gstin_raw else None
    auto_renew = None
    if renew_raw:
        lowered = renew_raw.lower()
        auto_renew = lowered.startswith("yes") or "automatic" in lowered or "auto" in lowered

    confidences = [c for c in (title_conf, from_conf, to_conf, terms_conf) if c]
    return {
        "title": title,
        "reference_no": reference,
        "agreement_type": guess_agreement_type(title, full_text[:1500] if full_text else None),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "payment_terms_text": terms,
        "term_days": parsed.days,
        "due_basis": parsed.basis,
        "terms_kind": parsed.kind,
        "auto_renew": auto_renew,
        "vendor_name": vendor_name,
        "vendor_gstin": gstin,
        "confidence": {
            "title": title_conf, "reference_no": reference_conf, "valid_from": from_conf, "valid_to": to_conf,
            "payment_terms": terms_conf, "term_days": days_conf, "vendor_name": vendor_conf,
            "vendor_gstin": gstin_conf, "auto_renew": renew_conf,
        },
        "overall_confidence": round(sum(confidences) / len(confidences), 2) if confidences else 0.0,
    }


def run_agreement_queries(s3_key: str):
    return run_document_analysis_queries(s3_key, AGREEMENT_QUERIES)


async def extract_agreement_from_s3(s3_key: str) -> Dict[str, Any]:
    try:
        results, full_text = await asyncio.to_thread(run_agreement_queries, s3_key)
    except (ClientError, BotoCoreError) as exc:
        raise TextractServiceError(f"AWS Textract error: {exc}") from exc
    except (TimeoutError, RuntimeError) as exc:
        raise TextractServiceError(str(exc)) from exc
    return parse_agreement_fields(results, full_text or "")
