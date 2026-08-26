# Backend/API_Layer/utils/invoice_extraction_fields.py

import asyncio
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from Backend.API_Layer.interface.invoice_extraction_interface import (
    ExtractedInvoiceResponse,
    InvoiceAmounts,
    InvoiceBuyer,
    InvoiceCompliance,
    InvoiceDocument,
    InvoiceLine,
    InvoicePayment,
    InvoiceReference,
    InvoiceTax,
    InvoiceValidation,
    InvoiceVendor,
    ExtractionMetadata,
)

from Backend.API_Layer.utils.s3_utils import (
    AWS_ACCESS_KEY,
    AWS_REGION,
    AWS_SECRET_KEY,
    BUCKET_NAME,
)


# ============================================================
# AWS client
# ============================================================

textract_client = boto3.client(
    "textract",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
)


# ============================================================
# Constants
# ============================================================

GSTIN_PATTERN = re.compile(
    r"\b\d{2}[A-Z0-9]{13}\b",
    re.IGNORECASE,
)

PAN_PATTERN = re.compile(
    r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    re.IGNORECASE,
)

IFSC_PATTERN = re.compile(
    r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
    re.IGNORECASE,
)

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

PHONE_PATTERN = re.compile(
    r"(?:\+91[\s-]?)?[6-9]\d{9}"
)

HSN_SAC_PATTERN = re.compile(
    r"\b\d{4,8}\b"
)

IRN_PATTERN = re.compile(
    r"\b[a-fA-F0-9]{64}\b"
)


INDIAN_STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}


# ============================================================
# Textract field aliases
# ============================================================

SUMMARY_FIELD_ALIASES = {

    "INVOICE_RECEIPT_ID": "invoice_number",
    "INVOICE_RECEIPT_DATE": "invoice_date",

    "DUE_DATE": "due_date",

    "VENDOR_NAME": "vendor_name",
    "VENDOR_ADDRESS": "vendor_address",

    "VENDOR_PHONE": "vendor_phone",
    "VENDOR_EMAIL": "vendor_email",

    "RECEIVER_NAME": "buyer_name",
    "RECEIVER_ADDRESS": "buyer_address",

    "RECEIVER_PHONE": "buyer_phone",
    "RECEIVER_EMAIL": "buyer_email",

    "PO_NUMBER": "po_number",
    "PO_DATE": "po_date",

    "SUBTOTAL": "subtotal",

    "TAX": "total_tax",
    "TOTAL_TAX": "total_tax",

    "TOTAL": "grand_total",

    "DISCOUNT": "discount",

    "PAYMENT_TERMS": "payment_terms",

    "BANK_NAME": "bank_name",
    "ACCOUNT_NUMBER": "account_number",
    "IFSC_CODE": "ifsc_code",

    "TAX_REGISTRATION_NUMBER": "vendor_gstin",

    "PLACE_OF_SUPPLY": "place_of_supply",

    "IRN": "irn",

    "ACKNOWLEDGEMENT_NUMBER": (
        "acknowledgement_number"
    ),

    "ACKNOWLEDGEMENT_DATE": (
        "acknowledgement_date"
    ),

    "SHIPPING_HANDLING_CHARGE": (
        "shipping_charges"
    ),

    "OTHER_CHARGES": "other_charges",

    "ROUNDING": "round_off",
}


# ============================================================
# AnalyzeExpense also tags some generic fields (ADDRESS/NAME)
# with a GroupProperties.Types entry identifying which party
# block they belong to (VENDOR_SUPPLIER / RECEIVER_BILL_TO /
# RECEIVER_SHIP_TO). This is the only way to reach the buyer's
# shipping address and a party's "legal name" (there is no flat
# alias for either) - used as a supplementary source, filled in
# only where the flat aliases above didn't already set a value.
# ============================================================

GROUP_TYPE_FIELD_MAP = {

    "VENDOR_SUPPLIER": {
        "ADDRESS": "vendor_address",
        "NAME": "vendor_legal_name",
    },

    "RECEIVER_BILL_TO": {
        "ADDRESS": "buyer_address",
        "NAME": "buyer_legal_name",
    },

    "RECEIVER_SHIP_TO": {
        "ADDRESS": "buyer_shipping_address",
    },
}


# ============================================================
# Critical queries
#
# NOTE: Amazon Textract enforces a hard limit of 15 queries per
# page for synchronous analysis and 30 for asynchronous
# analysis. Fields that AnalyzeExpense already extracts
# reliably (invoice number/date, due date, PO number/date,
# vendor/buyer name, HSN/SAC, subtotal, totals) are deliberately
# excluded here so this list can stay well under that limit.
# Seller/buyer PAN are intentionally NOT queried - they are
# derived from a validated GSTIN instead (see
# derive_pan_from_gstin), which also avoids asking the caller
# for PAN and avoids wasting a query slot on a field Textract
# can rarely read explicitly.
# ============================================================

TEXTRACT_QUERIES = [

    (
        "What is the seller or supplier GSTIN?",
        "SELLER_GSTIN",
    ),

    (
        "What is the buyer or recipient GSTIN?",
        "BUYER_GSTIN",
    ),

    (
        "What is the place of supply?",
        "PLACE_OF_SUPPLY",
    ),

    (
        "What taxes, tax rates, and tax amounts are shown on this invoice?",
        "TAX_DETAILS",
    ),

    (
        "What is the total amount payable or grand total?",
        "GRAND_TOTAL",
    ),

    (
        "What are the payment terms or the payment due date? "
        "Do not return a billing period or service period.",
        "PAYMENT_TERMS",
    ),

    (
        "What billing period or service period does this "
        "invoice cover?",
        "BILLING_PERIOD",
    ),

    (
        "What are the seller bank details?",
        "BANK_DETAILS",
    ),

    (
        "What is the IFSC code?",
        "IFSC",
    ),

    (
        "What is the taxable amount or taxable value?",
        "TAXABLE_AMOUNT",
    ),

    (
        "Is reverse charge applicable?",
        "REVERSE_CHARGE",
    ),

    (
        "What is the IRN?",
        "IRN",
    ),

    (
        "What is the acknowledgement number?",
        "ACKNOWLEDGEMENT_NUMBER",
    ),
]

TEXTRACT_SYNC_QUERY_LIMIT = 15
TEXTRACT_ASYNC_QUERY_LIMIT = 30

assert len(TEXTRACT_QUERIES) <= TEXTRACT_ASYNC_QUERY_LIMIT, (
    "TEXTRACT_QUERIES exceeds the Textract per-page query limit. "
    "Split fields across additional query batches instead of growing this list."
)


# ============================================================
# Extraction method labels (per-field provenance)
# ============================================================

class ExtractionMethod:

    TEXTRACT_QUERY = "TEXTRACT_QUERY"
    TEXTRACT_SUMMARY = "TEXTRACT_SUMMARY"
    TEXTRACT_TABLE = "TEXTRACT_TABLE"
    REGEX = "REGEX"
    DERIVED = "DERIVED"
    VALIDATED = "VALIDATED"


# ============================================================
# AWS retry helper
# ============================================================

TRANSIENT_ERROR_CODES = {
    "ThrottlingException",
    "ProvisionedThroughputExceededException",
    "InternalServerError",
    "LimitExceededException",
    "ServiceUnavailableException",
}


def call_textract_with_retry(
    func,
    *args,
    max_attempts: int = 4,
    base_delay: float = 1.5,
    **kwargs,
):

    attempt = 0

    while True:

        try:

            return func(*args, **kwargs)

        except ClientError as exc:

            error_code = exc.response.get("Error", {}).get("Code")

            attempt += 1

            if (
                error_code not in TRANSIENT_ERROR_CODES
                or attempt >= max_attempts
            ):
                raise

            time.sleep(base_delay * (2 ** (attempt - 1)))


# ============================================================
# Basic helpers
# ============================================================

def clean_text(
    value: Optional[Any]
) -> Optional[str]:

    if value is None:
        return None

    value = str(value).strip()

    return value if value else None


def normalize_number(
    value: Optional[Any]
) -> Optional[float]:

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    try:

        value = str(value).strip()

        # Remove common currency symbols.
        value = re.sub(
            r"[₹$€£]",
            "",
            value,
        )

        # Remove currency names/prefixes, including trailing
        # punctuation like "Rs." that a bare \b word match misses.
        value = re.sub(
            r"(?i)\b(inr|usd|eur|gbp|rs\.?|rupees)\b\.?",
            "",
            value,
        )

        value = value.replace(
            ",",
            "",
        )

        value = value.strip()

        # Guard against a stray leading dot/colon left behind
        # after stripping a label like "Rs." or "Amount:".
        value = value.lstrip(".:").strip()

        # Accounting negative:
        # (1000.00) => -1000
        if (
            value.startswith("(")
            and value.endswith(")")
        ):
            value = "-" + value[1:-1]

        return float(
            Decimal(value)
        )

    except (
        InvalidOperation,
        ValueError,
    ):
        return None


def normalize_date(
    value: Optional[Any]
) -> Optional[date]:

    if not value:
        return None

    value = str(value).strip()

    formats = [

        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%m/%d/%Y",

        "%d/%m/%y",
        "%d-%m-%y",

        "%d-%b-%Y",
        "%d-%B-%Y",

        "%d %b %Y",
        "%d %B %Y",

        "%b %d, %Y",
        "%B %d, %Y",
    ]

    for fmt in formats:

        try:
            return datetime.strptime(
                value,
                fmt,
            ).date()

        except ValueError:
            continue

    return None


def normalize_gstin(
    value: Optional[str]
) -> Optional[str]:

    if not value:
        return None

    value = re.sub(
        r"[^A-Za-z0-9]",
        "",
        value,
    ).upper()

    return value or None


def normalize_pan(
    value: Optional[str]
) -> Optional[str]:

    if not value:
        return None

    value = re.sub(
        r"[^A-Za-z0-9]",
        "",
        value,
    ).upper()

    return value or None


# ============================================================
# GSTIN structural validation and PAN derivation
#
# GSTIN layout: 2-digit state code + 10-character PAN +
# 1 entity code digit + 'Z' (default) + 1 checksum character.
# ============================================================

GSTIN_FORMAT_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
)


def is_valid_gstin_format(
    gstin: Optional[str],
) -> bool:

    if not gstin:
        return False

    return bool(
        GSTIN_FORMAT_PATTERN.match(gstin)
    )


def derive_pan_from_gstin(
    gstin: Optional[str],
) -> Optional[str]:

    if not gstin or len(gstin) != 15:
        return None

    candidate = gstin[2:12]

    if PAN_PATTERN.fullmatch(candidate):
        return candidate

    return None


# ============================================================
# Regex extraction
# ============================================================

def find_gstin(
    text: Optional[str]
) -> Optional[str]:

    if not text:
        return None

    match = GSTIN_PATTERN.search(
        text.upper()
    )

    return (
        match.group(0).upper()
        if match
        else None
    )


def find_pan(
    text: Optional[str]
) -> Optional[str]:

    if not text:
        return None

    match = PAN_PATTERN.search(
        text.upper()
    )

    return (
        match.group(0).upper()
        if match
        else None
    )


def find_ifsc(
    text: Optional[str]
) -> Optional[str]:

    if not text:
        return None

    match = IFSC_PATTERN.search(
        text.upper()
    )

    return (
        match.group(0).upper()
        if match
        else None
    )


def find_email(
    text: Optional[str]
) -> Optional[str]:

    if not text:
        return None

    match = EMAIL_PATTERN.search(
        text
    )

    return (
        match.group(0)
        if match
        else None
    )


def find_phone(
    text: Optional[str]
) -> Optional[str]:

    if not text:
        return None

    match = PHONE_PATTERN.search(
        text.replace(
            " ",
            "",
        )
    )

    return (
        match.group(0)
        if match
        else None
    )


# ============================================================
# Composite query-answer parsing
#
# Some queries deliberately ask a broad question (tax details,
# bank details) instead of consuming a separate query slot per
# sub-field. The answer text is a free-form phrase/line that we
# break down with tolerant regex heuristics.
# ============================================================

RATE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*%"
)

AMOUNT_TOKEN_PATTERN = re.compile(
    r"[₹$€£]?\s*-?\(?[\d,]+(?:\.\d+)?\)?"
)


def _split_tax_segments(
    text: str,
) -> List[str]:

    # Break the answer into per-tax-type chunks so a rate/amount
    # found near "CGST" isn't attributed to "SGST" etc.
    segments = re.split(
        r"[,;\n]|(?=\bCGST\b)|(?=\bSGST\b)|(?=\bIGST\b)"
        r"|(?=\bUTGST\b)|(?=\bUGST\b)|(?=\bCESS\b)",
        text,
        flags=re.IGNORECASE,
    )

    return [
        segment.strip()
        for segment in segments
        if segment.strip()
    ]


def parse_tax_details_answer(
    text: Optional[str],
) -> Dict[str, float]:

    result: Dict[str, float] = {}

    if not text:
        return result

    for segment in _split_tax_segments(text):

        segment_upper = segment.upper()

        # CGST must not steal SGST's "GST" substring match.
        if "CGST" in segment_upper:
            tax_key = "cgst"
        elif "UTGST" in segment_upper or "UGST" in segment_upper:
            tax_key = "ugst"
        elif "SGST" in segment_upper:
            tax_key = "sgst"
        elif "IGST" in segment_upper:
            tax_key = "igst"
        elif "CESS" in segment_upper:
            tax_key = "cess"
        else:
            continue

        rate_match = RATE_PATTERN.search(segment)

        if rate_match:
            result[f"{tax_key}_rate"] = normalize_number(
                rate_match.group(1)
            )

        remainder = (
            segment[rate_match.end():]
            if rate_match
            else segment
        )

        amount_candidates = AMOUNT_TOKEN_PATTERN.findall(
            remainder
        )

        amount_candidates = [
            normalize_number(candidate)
            for candidate in amount_candidates
        ]

        amount_candidates = [
            value
            for value in amount_candidates
            if value is not None
        ]

        if amount_candidates:
            result[f"{tax_key}_amount"] = amount_candidates[-1]

    return result


BANK_NAME_PATTERN = re.compile(
    r"(?:Bank\s*Name|Bank)\s*[:\-]?\s*"
    r"([A-Za-z0-9&.,\-\s]+?"
    r"(?:Bank|BANK)\b[A-Za-z\s]*)",
)

ACCOUNT_NUMBER_PATTERN = re.compile(
    r"(?:A/?c\.?\s*No\.?|Account\s*No\.?|"
    r"Account\s*Number)\s*[:\-]?\s*"
    r"([0-9][0-9\s]{6,20}[0-9])",
    re.IGNORECASE,
)

BRANCH_PATTERN = re.compile(
    r"Branch\s*[:\-]?\s*([A-Za-z0-9.,\-\s]+?)"
    r"(?:$|,|;|\n)",
    re.IGNORECASE,
)


def parse_bank_details_answer(
    text: Optional[str],
) -> Dict[str, str]:

    result: Dict[str, str] = {}

    if not text:
        return result

    name_match = BANK_NAME_PATTERN.search(text)

    if name_match:
        result["bank_name"] = clean_text(
            name_match.group(1)
        )

    account_match = ACCOUNT_NUMBER_PATTERN.search(text)

    if account_match:
        result["account_number"] = re.sub(
            r"\s+",
            "",
            account_match.group(1),
        )

    branch_match = BRANCH_PATTERN.search(text)

    if branch_match:
        result["branch"] = clean_text(
            branch_match.group(1)
        )

    if not result:

        # Fall back to a bare GSTIN-style bank text blob: at
        # least capture a raw account-number-looking sequence.
        digits_match = re.search(
            r"\b\d{9,18}\b",
            text,
        )

        if digits_match:
            result["account_number"] = digits_match.group(0)

    return result


REVERSE_CHARGE_TRUE_PATTERN = re.compile(
    r"\b(yes|applicable|y)\b", re.IGNORECASE
)

REVERSE_CHARGE_FALSE_PATTERN = re.compile(
    r"\b(no|not\s+applicable|n/?a|n)\b", re.IGNORECASE
)


def parse_reverse_charge_answer(
    text: Optional[str],
) -> Optional[bool]:

    if not text:
        return None

    if REVERSE_CHARGE_FALSE_PATTERN.search(text):
        return False

    if REVERSE_CHARGE_TRUE_PATTERN.search(text):
        return True

    return None


# ============================================================
# Parse summary fields
# ============================================================

def parse_summary_fields(
    summary_fields: List[Dict[str, Any]],
    field_details: Dict[str, Dict[str, Any]],
) -> Tuple[
    Dict[str, Any],
    Dict[str, float],
    Dict[str, str],
]:

    extracted = {}
    confidence = {}
    sources = {}

    # --------------------------------------------------------
    # Pass 1: Textract's own disambiguated top-level fields
    # (VENDOR_NAME, VENDOR_ADDRESS, RECEIVER_NAME,
    # RECEIVER_ADDRESS, INVOICE_RECEIPT_ID, PO_NUMBER, ...)
    # take priority over the generic group-tagged fields below.
    # --------------------------------------------------------

    for field in summary_fields:

        field_type = (
            field.get("Type", {})
            .get("Text")
        )

        if not field_type:
            continue

        field_type = field_type.upper()

        mapped_field = SUMMARY_FIELD_ALIASES.get(
            field_type
        )

        if not mapped_field:
            continue

        value = clean_text(
            field.get("ValueDetection", {})
            .get("Text")
        )

        if not value:
            continue

        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            mapped_field,
            value,
            field.get("ValueDetection", {}).get(
                "Confidence", 0.0
            ),
            "TEXTRACT_SUMMARY",
            ExtractionMethod.TEXTRACT_SUMMARY,
            field.get("PageNumber"),
        )

    # --------------------------------------------------------
    # Pass 2: generic ADDRESS/NAME fields tagged with a
    # GroupProperties.Types entry (VENDOR_SUPPLIER /
    # RECEIVER_BILL_TO / RECEIVER_SHIP_TO). This is the only
    # source for the buyer's shipping address and a party's
    # legal name - there is no flat alias for either - so it
    # only fills gaps pass 1 left behind.
    # --------------------------------------------------------

    for field in summary_fields:

        field_type = (
            field.get("Type", {})
            .get("Text")
        )

        if not field_type:
            continue

        field_type = field_type.upper()

        value = clean_text(
            field.get("ValueDetection", {})
            .get("Text")
        )

        if not value:
            continue

        for group in field.get("GroupProperties", []) or []:

            for group_type in group.get("Types", []) or []:

                group_map = GROUP_TYPE_FIELD_MAP.get(
                    group_type
                )

                if not group_map:
                    continue

                target = group_map.get(field_type)

                if not target:
                    continue

                _set_field(
                    extracted,
                    confidence,
                    sources,
                    field_details,
                    target,
                    value,
                    field.get("ValueDetection", {}).get(
                        "Confidence", 0.0
                    ),
                    "TEXTRACT_SUMMARY",
                    ExtractionMethod.TEXTRACT_SUMMARY,
                    field.get("PageNumber"),
                )

    return (
        extracted,
        confidence,
        sources,
    )


# ============================================================
# Parse line items
# ============================================================

def parse_line_items(
    groups: List[Dict[str, Any]]
) -> List[InvoiceLine]:

    result = []

    line_number = 1

    for group in groups:

        for item in group.get(
            "LineItems",
            [],
        ):

            values = {}

            for field in item.get(
                "LineItemExpenseFields",
                [],
            ):

                field_type = (
                    field.get("Type", {})
                    .get("Text")
                )

                value = (
                    field.get("ValueDetection", {})
                    .get("Text")
                )

                if not field_type or value is None:
                    continue

                field_type = field_type.upper()

                value = clean_text(value)

                if not value:
                    continue

                if field_type in {
                    "ITEM",
                    "DESCRIPTION",
                    "PRODUCT_DESCRIPTION",
                }:

                    values["description"] = value

                elif field_type in {
                    "PRODUCT_CODE",
                    "ITEM_CODE",
                }:

                    values["product_code"] = value

                    if (
                        not values.get("hsn_sac")
                        and HSN_SAC_PATTERN.fullmatch(
                            re.sub(
                                r"[^0-9]",
                                "",
                                value,
                            )
                        )
                    ):
                        values["hsn_sac"] = (
                            re.sub(
                                r"[^0-9]",
                                "",
                                value,
                            )
                        )

                elif field_type in {
                    "HSN",
                    "HSN_CODE",
                    "SAC",
                    "SAC_CODE",
                    "HSN_OR_SAC",
                }:

                    values["hsn_sac"] = value

                elif field_type == "QUANTITY":

                    values["quantity"] = (
                        normalize_number(value)
                    )

                elif field_type == "UNIT":

                    values["unit"] = value

                elif field_type in {
                    "UNIT_PRICE",
                    "PRICE",
                }:

                    values["unit_price"] = (
                        normalize_number(value)
                    )

                elif field_type == "DISCOUNT":

                    values["discount"] = (
                        normalize_number(value)
                    )

                elif field_type in {
                    "AMOUNT",
                    "LINE_TOTAL",
                }:

                    values["line_total"] = (
                        normalize_number(value)
                    )

                elif field_type in {
                    "TAXABLE_AMOUNT",
                    "TAXABLE_VALUE",
                }:

                    values["taxable_amount"] = (
                        normalize_number(value)
                    )

                elif field_type in {
                    "TAX",
                    "TAX_AMOUNT",
                }:

                    values["total_tax"] = (
                        normalize_number(value)
                    )

                elif field_type in {
                    "TAX_RATE",
                    "TAX_RATE_PERCENT",
                }:

                    values["tax_rate"] = (
                        normalize_number(value)
                    )

                elif field_type == "CGST":

                    values["cgst_amount"] = (
                        normalize_number(value)
                    )

                elif field_type == "SGST":

                    values["sgst_amount"] = (
                        normalize_number(value)
                    )

                elif field_type == "IGST":

                    values["igst_amount"] = (
                        normalize_number(value)
                    )

                elif field_type in {
                    "UGST",
                    "UTGST",
                }:

                    values["ugst_amount"] = (
                        normalize_number(value)
                    )

                elif field_type == "CESS":

                    values["cess_amount"] = (
                        normalize_number(value)
                    )

                elif field_type == "CGST_RATE":

                    values["cgst_rate"] = (
                        normalize_number(value)
                    )

                elif field_type == "SGST_RATE":

                    values["sgst_rate"] = (
                        normalize_number(value)
                    )

                elif field_type == "IGST_RATE":

                    values["igst_rate"] = (
                        normalize_number(value)
                    )

                elif field_type in {
                    "UGST_RATE",
                    "UTGST_RATE",
                }:

                    values["ugst_rate"] = (
                        normalize_number(value)
                    )

                elif field_type == "CESS_RATE":

                    values["cess_rate"] = (
                        normalize_number(value)
                    )

            if values:

                # Service-style line items (no quantity/rate
                # table) report the line amount under
                # unit_price/UNIT_PRICE rather than a separate
                # line total.
                if (
                    values.get("unit_price") is not None
                    and values.get("line_total") is None
                    and values.get("quantity") is None
                ):
                    values["line_total"] = values["unit_price"]

                result.append(
                    InvoiceLine(
                        line_number=line_number,
                        **values,
                    )
                )

                line_number += 1

    return result


# ============================================================
# Textract pagination
# ============================================================

def get_all_expense_documents(
    job_id: str,
) -> List[Dict[str, Any]]:

    documents = []

    next_token = None

    while True:

        params = {
            "JobId": job_id,
        }

        if next_token:
            params["NextToken"] = next_token

        response = call_textract_with_retry(
            textract_client.get_expense_analysis,
            **params,
        )

        documents.extend(
            response.get(
                "ExpenseDocuments",
                [],
            )
        )

        next_token = response.get(
            "NextToken"
        )

        if not next_token:
            break

    return documents


# ============================================================
# Textract query extraction
#
# Uses the asynchronous StartDocumentAnalysis/GetDocumentAnalysis
# pair (not the single-page-only synchronous AnalyzeDocument
# call) so multi-page invoices are queried on every page and
# results are correctly paginated via NextToken.
# ============================================================

def get_all_query_blocks(
    job_id: str,
) -> List[Dict[str, Any]]:

    blocks = []

    next_token = None

    while True:

        params = {
            "JobId": job_id,
        }

        if next_token:
            params["NextToken"] = next_token

        response = call_textract_with_retry(
            textract_client.get_document_analysis,
            **params,
        )

        blocks.extend(
            response.get(
                "Blocks",
                [],
            )
        )

        next_token = response.get(
            "NextToken"
        )

        if not next_token:
            break

    return blocks


def run_queries(
    s3_key: str,
) -> Tuple[Dict[str, Dict[str, Any]], str]:

    query_config = [
        {
            "Text": question,
            "Alias": alias,
        }
        for question, alias
        in TEXTRACT_QUERIES
    ]

    start_response = call_textract_with_retry(
        textract_client.start_document_analysis,
        DocumentLocation={
            "S3Object": {
                "Bucket": BUCKET_NAME,
                "Name": s3_key,
            }
        },
        FeatureTypes=[
            "QUERIES"
        ],
        QueriesConfig={
            "Queries": query_config
        },
    )

    job_id = start_response["JobId"]

    start_time = time.monotonic()

    status = None

    while True:

        response = call_textract_with_retry(
            textract_client.get_document_analysis,
            JobId=job_id,
            MaxResults=1,
        )

        status = response.get(
            "JobStatus"
        )

        if status in {
            "SUCCEEDED",
            "PARTIAL_SUCCESS",
            "FAILED",
        }:
            break

        if (
            time.monotonic()
            - start_time
            > 300
        ):
            raise TimeoutError(
                "Textract query analysis timed out."
            )

        time.sleep(2)

    if status == "FAILED":

        raise RuntimeError(
            "AWS Textract query analysis failed."
        )

    blocks = get_all_query_blocks(
        job_id
    )

    queries = {
        block["Id"]: block
        for block in blocks
        if block.get(
            "BlockType"
        ) == "QUERY"
    }

    answers = {
        block["Id"]: block
        for block in blocks
        if block.get(
            "BlockType"
        ) == "QUERY_RESULT"
    }

    results: Dict[str, Dict[str, Any]] = {}

    # A multi-page document gets one QUERY/QUERY_RESULT pair per
    # alias PER PAGE (Textract answers every query on every page
    # unless explicitly restricted). Keep the highest-confidence
    # answer per alias instead of letting whichever page happens
    # to be last in the block list silently win.
    for query in queries.values():

        alias = (
            query.get("Query", {})
            .get("Alias")
        )

        for relationship in query.get(
            "Relationships",
            [],
        ):

            if relationship.get(
                "Type"
            ) != "ANSWER":
                continue

            for answer_id in relationship.get(
                "Ids",
                [],
            ):

                answer = answers.get(
                    answer_id
                )

                if not answer:
                    continue

                candidate = {
                    "value": answer.get(
                        "Text"
                    ),
                    "confidence": answer.get(
                        "Confidence",
                        0.0,
                    ),
                    "page": query.get(
                        "Page",
                        1,
                    ),
                }

                existing = results.get(alias)

                if (
                    existing is None
                    or candidate["confidence"]
                    > existing["confidence"]
                ):
                    results[alias] = candidate

                break

    # Full document text, reusing the LINE blocks already
    # present in this same response - no extra Textract cost.
    # Backs the label-based regex fallback for fields with no
    # dedicated AnalyzeExpense type or query (delivery note,
    # quotation/contract references, invoice type, etc.).
    line_blocks = [
        block
        for block in blocks
        if block.get("BlockType") == "LINE"
        and block.get("Text")
    ]

    line_blocks.sort(
        key=lambda block: (
            block.get("Page", 1),
            block.get("Geometry", {})
            .get("BoundingBox", {})
            .get("Top", 0.0),
        )
    )

    full_text = "\n".join(
        block["Text"] for block in line_blocks
    )

    return results, full_text


# ============================================================
# Apply query fallback
# ============================================================

def _set_field(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    field_details: Dict[str, Dict[str, Any]],
    target: str,
    value: Any,
    field_confidence: float,
    source: str,
    method: str,
    page: Optional[int] = None,
    overwrite: bool = False,
):

    if value is None or value == "":
        return

    if not overwrite and extracted.get(target):
        return

    extracted[target] = value

    confidence[target] = field_confidence

    sources[target] = source

    field_details[target] = {
        "value": value,
        "confidence": field_confidence,
        "source": source,
        "extraction_method": method,
        "page": page,
    }


def apply_query_fallback(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    field_details: Dict[str, Dict[str, Any]],
    queries: Dict[str, Dict[str, Any]],
):

    # --------------------------------------------------------
    # Direct 1:1 query -> field mappings
    # --------------------------------------------------------

    direct_mapping = {

        "SELLER_GSTIN": "vendor_gstin",
        "BUYER_GSTIN": "buyer_gstin",

        "PLACE_OF_SUPPLY": "place_of_supply",

        "TAXABLE_AMOUNT": "taxable_amount",

        "GRAND_TOTAL": "grand_total",

        "IRN": "irn",

        "PAYMENT_TERMS": "payment_terms",

        "IFSC": "ifsc_code",

        "ACKNOWLEDGEMENT_NUMBER": "acknowledgement_number",
        "BILLING_PERIOD": "billing_period",
    }

    numeric_targets = {
        "taxable_amount",
        "grand_total",
    }

    for alias, target in direct_mapping.items():

        query = queries.get(alias)

        if not query:
            continue

        value = clean_text(
            query.get("value")
        )

        if target in numeric_targets:

            # Query answers sometimes match an "amount in
            # words" line instead of the numeric figure -
            # only accept a value that actually parses as
            # a number, otherwise skip it rather than
            # storing unparseable text in a numeric field.
            value = normalize_number(value)

            if value is None:
                continue

        if target == "ifsc_code" and value:

            candidate = re.sub(r"[^A-Za-z0-9]", "", value).upper()

            if not IFSC_PATTERN.fullmatch(candidate):
                continue

            value = candidate

        if target == "irn" and value:

            # The IRN query can latch onto an unrelated
            # nearby identifier (GSTIN, IFSC) when no real IRN
            # exists on the document - a genuine IRN is a fixed
            # 64-character hex string, so reject anything that
            # doesn't match rather than storing a false positive.
            candidate = re.sub(r"[^A-Fa-f0-9]", "", value)

            if not IRN_PATTERN.fullmatch(candidate):
                continue

            value = candidate

        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            target,
            value,
            query.get("confidence", 0.0),
            "TEXTRACT_QUERY",
            ExtractionMethod.TEXTRACT_QUERY,
            query.get("page"),
        )

    # --------------------------------------------------------
    # TAX_DETAILS: composite CGST/SGST/IGST/CESS rates+amounts
    # --------------------------------------------------------

    # Textract only reports one confidence value for the whole
    # composite answer text, not per decomposed sub-field. Rather
    # than claiming the same certainty for every regex-derived
    # sub-value, apply a discount reflecting the extra uncertainty
    # introduced by splitting a free-form phrase into fields.
    COMPOSITE_CONFIDENCE_FACTOR = 0.9

    tax_query = queries.get("TAX_DETAILS")

    if tax_query and tax_query.get("value"):

        parsed_taxes = parse_tax_details_answer(
            tax_query["value"]
        )

        tax_field_confidence = round(
            tax_query.get("confidence", 0.0)
            * COMPOSITE_CONFIDENCE_FACTOR,
            2,
        )

        for tax_field, tax_value in parsed_taxes.items():

            _set_field(
                extracted,
                confidence,
                sources,
                field_details,
                tax_field,
                tax_value,
                tax_field_confidence,
                "TEXTRACT_QUERY",
                ExtractionMethod.REGEX,
                tax_query.get("page"),
            )

        total_tax = sum(
            value
            for key, value in parsed_taxes.items()
            if key.endswith("_amount")
            and value is not None
        )

        if total_tax:

            _set_field(
                extracted,
                confidence,
                sources,
                field_details,
                "total_tax",
                total_tax,
                tax_field_confidence,
                "TEXTRACT_QUERY",
                ExtractionMethod.DERIVED,
                tax_query.get("page"),
            )

    # --------------------------------------------------------
    # BANK_DETAILS: composite bank name/account/branch
    # --------------------------------------------------------

    bank_query = queries.get("BANK_DETAILS")

    if bank_query and bank_query.get("value"):

        parsed_bank = parse_bank_details_answer(
            bank_query["value"]
        )

        bank_field_confidence = round(
            bank_query.get("confidence", 0.0)
            * COMPOSITE_CONFIDENCE_FACTOR,
            2,
        )

        for bank_field, bank_value in parsed_bank.items():

            _set_field(
                extracted,
                confidence,
                sources,
                field_details,
                bank_field,
                bank_value,
                bank_field_confidence,
                "TEXTRACT_QUERY",
                ExtractionMethod.REGEX,
                bank_query.get("page"),
            )

    # --------------------------------------------------------
    # REVERSE_CHARGE: yes/no phrase -> boolean
    # --------------------------------------------------------

    reverse_charge_query = queries.get("REVERSE_CHARGE")

    if reverse_charge_query and reverse_charge_query.get("value"):

        reverse_charge_value = parse_reverse_charge_answer(
            reverse_charge_query["value"]
        )

        if reverse_charge_value is not None:

            _set_field(
                extracted,
                confidence,
                sources,
                field_details,
                "reverse_charge",
                reverse_charge_value,
                reverse_charge_query.get("confidence", 0.0),
                "TEXTRACT_QUERY",
                ExtractionMethod.TEXTRACT_QUERY,
                reverse_charge_query.get("page"),
            )


# ============================================================
# Regex fallback from extracted addresses
# ============================================================

def apply_regex_fallback(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    field_details: Dict[str, Dict[str, Any]],
):

    # Note: vendor_pan/buyer_pan are primarily derived from a
    # validated GSTIN (see derive_pan_numbers). The address-regex
    # PAN match here only fires as a last resort when no valid
    # GSTIN was extracted at all.

    regex_targets = [
        ("vendor_gstin", "vendor_address", find_gstin, 90.0),
        ("buyer_gstin", "buyer_address", find_gstin, 90.0),
        ("vendor_pan", "vendor_address", find_pan, 90.0),
        ("buyer_pan", "buyer_address", find_pan, 90.0),
        ("vendor_email", "vendor_address", find_email, 85.0),
        ("vendor_phone", "vendor_address", find_phone, 85.0),
        ("buyer_email", "buyer_address", find_email, 85.0),
        ("buyer_phone", "buyer_address", find_phone, 85.0),
    ]

    for target, source_field, finder, field_confidence in regex_targets:

        if extracted.get(target):
            continue

        value = finder(
            extracted.get(source_field)
        )

        if not value:
            continue

        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            target,
            value,
            field_confidence,
            "REGEX_ADDRESS",
            ExtractionMethod.REGEX,
        )
GSTIN_LABEL_PATTERN = re.compile(
    r"(?:GST(?:IN)?\s*(?:Number|No\.?|Registration\s*Number)?)\s*"
    r"[:\-]?\s*([0-9]{2}[A-Z0-9]{13})",
    re.IGNORECASE,
)

# Fallback tax-line matcher used when the TAX_DETAILS query
# returns no answer at all (seen in production - see
# raw_fields.query_results gaps). Matches lines like:
#   "IGST 18%  Rs. 550.03"
#   "CGST @ 9% = Rs. 275.02"
#   "SGST 9% Rs.275.02"
TAX_LINE_PATTERN = re.compile(
    r"\b(CGST|SGST|IGST|UGST|UTGST|CESS)\b"
    r"(?:\s*@)?\s*(\d+(?:\.\d+)?)\s*%"
    r"[^0-9]{0,40}"
    r"(?:Rs\.?|INR|₹)?\s*"
    r"([\d,]+\.?\d*)",
    re.IGNORECASE | re.DOTALL,
)


def find_labeled_taxes(
    full_text: str,
) -> Dict[str, float]:

    result: Dict[str, float] = {}

    for match in TAX_LINE_PATTERN.finditer(full_text):

        raw_type = match.group(1).upper()

        tax_key = (
            "ugst"
            if raw_type in ("UGST", "UTGST")
            else raw_type.lower()
        )

        rate = normalize_number(match.group(2))
        amount = normalize_number(match.group(3))

        if rate is not None and f"{tax_key}_rate" not in result:
            result[f"{tax_key}_rate"] = rate

        if amount is not None and f"{tax_key}_amount" not in result:
            result[f"{tax_key}_amount"] = amount

    return result


def find_labeled_gstins(
    full_text: str,
) -> List[Tuple[str, int]]:

    return [
        (match.group(1).upper(), match.start())
        for match in GSTIN_LABEL_PATTERN.finditer(full_text)
        if is_valid_gstin_format(match.group(1).upper())
    ]


def classify_party_gstins(
    full_text: Optional[str],
    vendor_name: Optional[str],
    buyer_name: Optional[str],
) -> Dict[str, str]:

    # Assigns each label-anchored GSTIN found anywhere in the
    # document to vendor/buyer based on which party's name
    # appears closest to it - generalizes across layouts where
    # GSTIN sits outside the address block Textract grouped
    # (footers, repeated per-page headers, standalone lines).

    result: Dict[str, str] = {}

    if not full_text:
        return result

    matches = find_labeled_gstins(full_text)

    if not matches:
        return result

    def _find_anchor(name: Optional[str]) -> int:

        if not name:
            return -1

        # Exact match first (fast path).
        pos = full_text.find(name)

        if pos >= 0:
            return pos

        # Column-split layouts can break a multi-word name
        # across separate OCR lines - fall back to the first
        # significant word (e.g. "KEKA" instead of the full
        # "KEKA TECHNOLOGIES PRIVATE LIMITED"), which usually
        # survives even when the full string doesn't.
        first_word = name.split()[0] if name.split() else None

        return (
            full_text.find(first_word)
            if first_word and len(first_word) >= 4
            else -1
        )

    vendor_pos = _find_anchor(vendor_name)
    buyer_pos = _find_anchor(buyer_name)

    for gstin, pos in matches:

        dist_vendor = (
            abs(pos - vendor_pos)
            if vendor_pos >= 0
            else float("inf")
        )

        dist_buyer = (
            abs(pos - buyer_pos)
            if buyer_pos >= 0
            else float("inf")
        )

        if dist_vendor <= dist_buyer and "vendor_gstin" not in result:
            result["vendor_gstin"] = gstin
        elif "buyer_gstin" not in result and gstin != result.get("vendor_gstin"):
            result["buyer_gstin"] = gstin

    return result

# ============================================================
# Full-document-text regex fallback
#
# Backed by the LINE blocks already returned inside the
# Queries job's response (see run_queries) - no additional
# Textract cost. Covers fields with no dedicated AnalyzeExpense
# type and no Textract Query slot: delivery/quotation/contract
# references, invoice/document type, TDS/freight/handling
# charges, amount paid, balance due.
# ============================================================

LABELED_TEXT_PATTERNS = {

    "delivery_note_number": re.compile(
        r"(?:Delivery\s*Note|D\.?\s*Note|Challan)\s*"
        r"(?:No\.?|Number|#)?\s*[:\-]?\s*"
        r"([A-Za-z0-9\/\-]+)",
        re.IGNORECASE,
    ),

    "quotation_number": re.compile(
        r"Quotation\s*(?:No\.?|Number|#)?\s*[:\-]?\s*"
        r"([A-Za-z0-9\/\-]+)",
        re.IGNORECASE,
    ),

    "contract_number": re.compile(
        r"(?:Contract|Agreement)\s*"
        r"(?:No\.?|Number|Ref\.?|#)?\s*[:\-]?\s*"
        r"([A-Za-z0-9\/\-]+)",
        re.IGNORECASE,
    ),

    "tds_amount": re.compile(
        r"TDS\s*(?:Amount|Deducted)?"
        r"(?:\s*@\s*[\d.]+\s*%)?\s*[:\-]?\s*"
        r"[₹$]?\s*([\d,]+\.?\d*)",
        re.IGNORECASE,
    ),

    "amount_paid": re.compile(
        r"Amount\s*Paid\s*[:\-]?\s*[₹$]?\s*"
        r"([\d,]+\.?\d*)",
        re.IGNORECASE,
    ),

    "balance_due": re.compile(
        r"Balance\s*(?:Due|Payable)\s*[:\-]?\s*"
        r"[₹$]?\s*([\d,]+\.?\d*)",
        re.IGNORECASE,
    ),

    "freight_charges": re.compile(
        r"Freight\s*(?:Charges?)?\s*[:\-]?\s*"
        r"[₹$]?\s*([\d,]+\.?\d*)",
        re.IGNORECASE,
    ),

    "handling_charges": re.compile(
        r"Handling\s*(?:Charges?)?\s*[:\-]?\s*"
        r"[₹$]?\s*([\d,]+\.?\d*)",
        re.IGNORECASE,
    ),

    "hsn_sac": re.compile(
        r"(?:HSN\s*/?\s*SAC|HSN\s*Code|SAC\s*Code|HSN|SAC)\s*"
        r"[:\-]?\s*(\d{4,8})",
        re.IGNORECASE,
    ),
}

NUMERIC_TEXT_FIELDS = {
    "tds_amount",
    "amount_paid",
    "balance_due",
    "freight_charges",
    "handling_charges",
}

DOCUMENT_TYPE_PATTERNS = [
    (re.compile(r"\bTAX\s+INVOICE\b", re.IGNORECASE), "TAX_INVOICE"),
    (re.compile(r"\bCREDIT\s+NOTE\b", re.IGNORECASE), "CREDIT_NOTE"),
    (re.compile(r"\bDEBIT\s+NOTE\b", re.IGNORECASE), "DEBIT_NOTE"),
    (
        re.compile(r"\bPROFORMA\s+INVOICE\b", re.IGNORECASE),
        "PROFORMA_INVOICE",
    ),
    (
        re.compile(r"\bBILL\s+OF\s+SUPPLY\b", re.IGNORECASE),
        "BILL_OF_SUPPLY",
    ),
    (
        re.compile(r"\bRETAIL\s+INVOICE\b", re.IGNORECASE),
        "RETAIL_INVOICE",
    ),
]


def detect_invoice_type(
    text: Optional[str],
) -> Optional[str]:

    if not text:
        return None

    for pattern, label in DOCUMENT_TYPE_PATTERNS:

        if pattern.search(text):
            return label

    return None


def apply_fulltext_fallback(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    field_details: Dict[str, Dict[str, Any]],
    full_text: Optional[str],
):

    if not full_text:
        return

    # Tax rate/amount fallback - only fires for tax types that
    # TAX_DETAILS (query) and line items didn't already supply,
    # since _set_field never overwrites an existing value.
    for tax_field, tax_value in find_labeled_taxes(full_text).items():

        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            tax_field,
            tax_value,
            75.0,
            "REGEX_FULLTEXT",
            ExtractionMethod.REGEX,
        )

    computed_total_tax = sum(
        value
        for key, value in extracted.items()
        if key.endswith("_amount")
        and key.split("_")[0] in {
            "cgst", "sgst", "igst", "ugst", "cess",
        }
        and isinstance(value, (int, float))
    )

    current_total_tax = normalize_number(
        extracted.get("total_tax")
    )

    if computed_total_tax and (
        current_total_tax is None
        or round(computed_total_tax, 2) != round(current_total_tax, 2)
    ):

        # A single TOTAL_TAX summary field can under-capture when
        # multiple tax lines exist (e.g. CGST + SGST both present
        # but the field only matched one) - the sum of individually
        # regex-matched components is more reliable in that case.
        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            "total_tax",
            computed_total_tax,
            75.0,
            "REGEX_FULLTEXT",
            ExtractionMethod.DERIVED,
            overwrite=True,
        )

    for target, pattern in LABELED_TEXT_PATTERNS.items():

        if extracted.get(target):
            continue

        match = pattern.search(full_text)

        if not match:
            continue

        value = clean_text(match.group(1))

        if not value:
            continue

        if target in NUMERIC_TEXT_FIELDS:

            value = normalize_number(value)

            if value is None:
                continue

        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            target,
            value,
            75.0,
            "REGEX_FULLTEXT",
            ExtractionMethod.REGEX,
        )

    if not extracted.get("invoice_type"):

        detected_type = detect_invoice_type(full_text)

        if detected_type:

            _set_field(
                extracted,
                confidence,
                sources,
                field_details,
                "invoice_type",
                detected_type,
                80.0,
                "REGEX_FULLTEXT",
                ExtractionMethod.REGEX,
            )


# ============================================================
# Legal name / trade name
#
# AnalyzeExpense has no concept of "trade name" - only a single
# printed name. Default legal_name to the detected name (the
# printed name usually IS the legal name on Indian invoices) and
# only populate trade_name when a "trading as" / "T/A" / "d/b/a"
# phrase is found in that SAME party's own address block, to
# avoid attributing one party's trade name to the other.
# ============================================================

TRADE_NAME_PATTERN = re.compile(
    r"(?:trading\s+as|t\/a|d\/b\/a)\s*[:\-]?\s*"
    r"([A-Za-z0-9&.,\-\s]{2,60})",
    re.IGNORECASE,
)


def find_trade_name(
    text: Optional[str],
) -> Optional[str]:

    if not text:
        return None

    match = TRADE_NAME_PATTERN.search(text)

    if not match:
        return None

    return clean_text(
        match.group(1).split("\n")[0]
    )


def derive_legal_and_trade_names(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    field_details: Dict[str, Dict[str, Any]],
):

    party_fields = (
        (
            "vendor_name",
            "vendor_legal_name",
            "vendor_trade_name",
            "vendor_address",
        ),
        (
            "buyer_name",
            "buyer_legal_name",
            "buyer_trade_name",
            "buyer_address",
        ),
    )

    for name_field, legal_field, trade_field, address_field in party_fields:

        if extracted.get(name_field) and not extracted.get(
            legal_field
        ):

            _set_field(
                extracted,
                confidence,
                sources,
                field_details,
                legal_field,
                extracted[name_field],
                confidence.get(name_field, 0.0),
                "DERIVED_FROM_NAME",
                ExtractionMethod.DERIVED,
                field_details.get(name_field, {}).get(
                    "page"
                ),
            )

        if not extracted.get(trade_field):

            trade_name = find_trade_name(
                extracted.get(address_field)
            )

            if trade_name:

                _set_field(
                    extracted,
                    confidence,
                    sources,
                    field_details,
                    trade_field,
                    trade_name,
                    75.0,
                    "REGEX_ADDRESS",
                    ExtractionMethod.REGEX,
                )


# ============================================================
# Derive GST tax type
#
# Purely a classification of which tax components are present -
# does not attempt to distinguish "exempt" from "zero-rated"
# (that requires reading legal clause text, out of scope for a
# deterministic OCR pipeline); both surface as NO_TAX_OR_EXEMPT.
# ============================================================

def derive_tax_type(
    extracted: Dict[str, Any],
    field_details: Dict[str, Dict[str, Any]],
):

    if extracted.get("tax_type"):
        return

    cgst = normalize_number(extracted.get("cgst_amount")) or 0.0
    sgst = normalize_number(extracted.get("sgst_amount")) or 0.0
    igst = normalize_number(extracted.get("igst_amount")) or 0.0
    ugst = normalize_number(extracted.get("ugst_amount")) or 0.0
    cess = normalize_number(extracted.get("cess_amount")) or 0.0
    total_tax = normalize_number(extracted.get("total_tax")) or 0.0

    if igst:
        tax_type = "INTER_STATE_IGST"

    elif cgst and ugst:
        tax_type = "UNION_TERRITORY_CGST_UGST"

    elif cgst and sgst:
        tax_type = "INTRA_STATE_CGST_SGST"

    elif ugst:
        tax_type = "UNION_TERRITORY_UGST"

    elif cess and not (cgst or sgst or igst or ugst):
        tax_type = "CESS_ONLY"

    elif total_tax:
        tax_type = "OTHER_TAX"

    elif (
        extracted.get("taxable_amount") is not None
        or extracted.get("grand_total") is not None
    ):
        tax_type = "NO_TAX_OR_EXEMPT"

    else:
        return

    extracted["tax_type"] = tax_type

    field_details["tax_type"] = {
        "value": tax_type,
        "confidence": None,
        "source": "DERIVED",
        "extraction_method": ExtractionMethod.DERIVED,
        "page": None,
    }


# ============================================================
# Derive PAN from GSTIN
# ============================================================

def derive_pan_numbers(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    field_details: Dict[str, Dict[str, Any]],
    issues: List[Dict[str, str]],
):

    for party, gstin_field, pan_field in (
        ("vendor", "vendor_gstin", "vendor_pan"),
        ("buyer", "buyer_gstin", "buyer_pan"),
    ):

        gstin = extracted.get(gstin_field)

        if not gstin:
            continue

        if not is_valid_gstin_format(gstin):

            issues.append({
                "field": gstin_field,
                "code": "INVALID_GSTIN_FORMAT",
                "message": (
                    f"{party.capitalize()} GSTIN "
                    f"'{gstin}' does not match the "
                    "expected GSTIN structure."
                ),
            })

            continue

        pan = derive_pan_from_gstin(gstin)

        if not pan:

            issues.append({
                "field": pan_field,
                "code": "PAN_DERIVATION_FAILED",
                "message": (
                    f"Could not derive a valid PAN from "
                    f"{party} GSTIN '{gstin}'."
                ),
            })

            continue

        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            pan_field,
            pan,
            confidence.get(gstin_field, 90.0),
            "DERIVED_FROM_GSTIN",
            ExtractionMethod.DERIVED,
            field_details.get(gstin_field, {}).get("page"),
            overwrite=True,
        )


# ============================================================
# Derive GST state
# ============================================================

def derive_states(
    extracted: Dict[str, Any],
):

    vendor_gstin = normalize_gstin(
        extracted.get(
            "vendor_gstin"
        )
    )

    buyer_gstin = normalize_gstin(
        extracted.get(
            "buyer_gstin"
        )
    )

    if vendor_gstin and len(
        vendor_gstin
    ) >= 2:

        code = vendor_gstin[:2]

        extracted[
            "vendor_state_code"
        ] = code

        extracted[
            "vendor_state"
        ] = INDIAN_STATE_CODES.get(
            code
        )

    if buyer_gstin and len(
        buyer_gstin
    ) >= 2:

        code = buyer_gstin[:2]

        extracted[
            "buyer_state_code"
        ] = code

        extracted[
            "buyer_state"
        ] = INDIAN_STATE_CODES.get(
            code
        )


# ============================================================
# Normalize extracted fields
# ============================================================

def normalize_extracted_fields(
    extracted: Dict[str, Any],
    issues: Optional[List[Dict[str, str]]] = None,
):

    date_fields = {
        "invoice_date",
        "due_date",
        "po_date",
        "delivery_note_date",
        "quotation_date",
        "acknowledgement_date",
    }

    number_fields = {
        "subtotal",
        "taxable_amount",
        "discount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "total_tax",
        "tds_amount",
        "other_charges",
        "shipping_charges",
        "freight_charges",
        "handling_charges",
        "round_off",
        "grand_total",
        "amount_paid",
        "balance_due",
    }

    for field in date_fields:

        if field in extracted:

            raw_value = extracted[field]

            parsed = normalize_date(
                raw_value
            )

            if parsed:

                extracted[field] = parsed

            elif not isinstance(raw_value, date):

                # Never leave an unparseable string behind -
                # the response model expects a real date.
                del extracted[field]

                if issues is not None:

                    issues.append({
                        "field": field,
                        "code": "UNPARSEABLE_DATE",
                        "message": (
                            f"{field} value '{raw_value}' "
                            "could not be parsed as a date."
                        ),
                    })

    for field in number_fields:

        if field in extracted:

            raw_value = extracted[field]

            parsed = normalize_number(
                raw_value
            )

            if parsed is not None:

                extracted[field] = parsed

            elif not isinstance(raw_value, (int, float)):

                # Never leave unparseable text (e.g. an
                # "amount in words" line) behind - the
                # response model expects a real number.
                del extracted[field]

                if issues is not None:

                    issues.append({
                        "field": field,
                        "code": "UNPARSEABLE_NUMBER",
                        "message": (
                            f"{field} value '{raw_value}' "
                            "could not be parsed as a number."
                        ),
                    })

    if extracted.get(
        "vendor_gstin"
    ):

        extracted[
            "vendor_gstin"
        ] = normalize_gstin(
            extracted[
                "vendor_gstin"
            ]
        )

    if extracted.get(
        "buyer_gstin"
    ):

        extracted[
            "buyer_gstin"
        ] = normalize_gstin(
            extracted[
                "buyer_gstin"
            ]
        )

    if extracted.get(
        "vendor_pan"
    ):

        extracted[
            "vendor_pan"
        ] = normalize_pan(
            extracted[
                "vendor_pan"
            ]
        )

    if extracted.get(
        "buyer_pan"
    ):

        extracted[
            "buyer_pan"
        ] = normalize_pan(
            extracted[
                "buyer_pan"
            ]
        )


# ============================================================
# Validation
# ============================================================

def find_state_code_in_text(
    text: Optional[str],
) -> Optional[str]:

    if not text:
        return None

    text_lower = text.lower()

    for code, name in INDIAN_STATE_CODES.items():

        if name.lower() in text_lower:
            return code

    return None


def amounts_match(
    expected: Optional[float],
    actual: Optional[float],
) -> Tuple[bool, Optional[float]]:

    if expected is None or actual is None:
        return True, None

    difference = round(
        abs(expected - actual),
        2,
    )

    tolerance = max(
        1.0,
        0.005 * max(abs(expected), abs(actual)),
    )

    return difference <= tolerance, difference


# ERROR-severity codes: mathematically/legally contradictory or
# structurally impossible values. Everything else (missing
# optional fields, OCR uncertainty, soft equality checks) is a
# WARNING and never flips is_valid to False.
ERROR_ISSUE_CODES = {
    "INVALID_GSTIN_FORMAT",
    "TOTAL_MISMATCH",
    "TAX_COMPONENT_MISMATCH",
    "CONTRADICTORY_TAX_STRUCTURE",
    "DUE_DATE_BEFORE_INVOICE_DATE",
}


def validate_invoice(
    extracted: Dict[str, Any],
    lines: List[InvoiceLine],
    prior_field_issues: Optional[
        List[Dict[str, str]]
    ] = None,
) -> InvoiceValidation:

    issues: List[str] = []
    warnings: List[str] = []

    field_issues: List[Dict[str, str]] = []

    def add_issue(field: str, code: str, message: str):

        field_issues.append({
            "field": field,
            "code": code,
            "message": message,
        })

        issues.append(message)

    def add_warning(field: str, code: str, message: str):

        field_issues.append({
            "field": field,
            "code": code,
            "message": message,
        })

        warnings.append(message)

    # Route issues raised earlier in the pipeline (invalid GSTIN
    # format, unparseable date/number, failed PAN derivation)
    # through the same severity classification instead of just
    # appending them - otherwise they'd never affect is_valid.
    for item in prior_field_issues or []:

        code = item.get("code", "")

        if code in ERROR_ISSUE_CODES:
            add_issue(
                item.get("field"),
                code,
                item.get("message", ""),
            )
        else:
            add_warning(
                item.get("field"),
                code,
                item.get("message", ""),
            )

    # --------------------------------------------------------
    # Required fields (do not fail the whole invoice - track)
    # --------------------------------------------------------

    critical_fields = {
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date",
        "vendor_name": "Vendor name",
        "grand_total": "Grand total",
    }

    for field, label in critical_fields.items():

        if not extracted.get(field):

            add_issue(
                field,
                "MISSING_FIELD",
                f"{label} was not detected.",
            )

    optional_fields = {
        "vendor_gstin": "Vendor GSTIN",
        "buyer_gstin": "Buyer GSTIN",
    }

    for field, label in optional_fields.items():

        if not extracted.get(field):

            add_warning(
                field,
                "MISSING_FIELD",
                f"{label} could not be confidently extracted.",
            )

    if not lines:

        add_warning(
            "invoice_lines",
            "MISSING_LINE_ITEMS",
            "No invoice line items were detected.",
        )

    # --------------------------------------------------------
    # Amount reconciliation
    # --------------------------------------------------------

    taxable_amount = normalize_number(
        extracted.get("taxable_amount")
        or extracted.get("subtotal")
    )

    cgst_amount = normalize_number(extracted.get("cgst_amount")) or 0.0
    sgst_amount = normalize_number(extracted.get("sgst_amount")) or 0.0
    igst_amount = normalize_number(extracted.get("igst_amount")) or 0.0
    ugst_amount = normalize_number(extracted.get("ugst_amount")) or 0.0
    cess_amount = normalize_number(extracted.get("cess_amount")) or 0.0

    computed_tax = (
        cgst_amount
        + sgst_amount
        + igst_amount
        + ugst_amount
        + cess_amount
    ) or None

    total_tax = normalize_number(
        extracted.get("total_tax")
    ) or computed_tax

    grand_total = normalize_number(
        extracted.get("grand_total")
    )

    tax_difference = None

    if computed_tax is not None and normalize_number(
        extracted.get("total_tax")
    ) is not None:

        matched, tax_difference = amounts_match(
            computed_tax,
            normalize_number(extracted.get("total_tax")),
        )

        if not matched:

            add_issue(
                "total_tax",
                "TAX_COMPONENT_MISMATCH",
                "Sum of CGST/SGST/UGST/IGST/CESS does not "
                "match the reported total tax amount.",
            )

    # Do not assume taxable + tax == grand_total: real invoices
    # can add freight/shipping/handling/other charges and a
    # round-off, and subtract a discount, before reaching the
    # grand total.
    other_charges = normalize_number(
        extracted.get("other_charges")
    ) or 0.0
    shipping_charges = normalize_number(
        extracted.get("shipping_charges")
    ) or 0.0
    freight_charges = normalize_number(
        extracted.get("freight_charges")
    ) or 0.0
    handling_charges = normalize_number(
        extracted.get("handling_charges")
    ) or 0.0
    discount = normalize_number(
        extracted.get("discount")
    ) or 0.0
    round_off = normalize_number(
        extracted.get("round_off")
    ) or 0.0

    total_difference = None

    if (
        taxable_amount is not None
        and total_tax is not None
        and grand_total is not None
    ):

        base_total = (
            taxable_amount
            + total_tax
            + other_charges
            + shipping_charges
            + freight_charges
            + handling_charges
            + round_off
        )

        # Two candidate interpretations of "taxable_amount":
        # already net of discount (e.g. AWS-style service
        # invoices, where the discount was applied before the
        # reported taxable value), or gross before discount
        # (traditional GST invoice style). Accept whichever
        # matches instead of assuming one invoice structure.
        candidate_net_of_discount = base_total
        candidate_gross_before_discount = base_total - discount

        matched_net, diff_net = amounts_match(
            candidate_net_of_discount,
            grand_total,
        )

        matched_gross, diff_gross = amounts_match(
            candidate_gross_before_discount,
            grand_total,
        )

        if matched_net or matched_gross:

            total_difference = (
                0.0
                if matched_net
                else diff_gross
            )

        else:

            total_difference = min(
                diff_net,
                diff_gross,
            )

            add_issue(
                "grand_total",
                "TOTAL_MISMATCH",
                "Neither (taxable amount + tax + charges) nor "
                "(taxable amount - discount + tax + charges) "
                "matches the grand total (closest difference: "
                f"{total_difference}).",
            )

    # --------------------------------------------------------
    # Line item vs header taxable amount
    # --------------------------------------------------------

    if lines and taxable_amount is not None:

        line_taxable_sum = sum(
            line.taxable_amount
            for line in lines
            if line.taxable_amount is not None
        )

        if line_taxable_sum:

            matched, _ = amounts_match(
                line_taxable_sum,
                taxable_amount,
            )

            if not matched:

                add_warning(
                    "taxable_amount",
                    "LINE_TOTAL_MISMATCH",
                    "Sum of line item taxable values does "
                    "not match the header taxable amount.",
                )

    # --------------------------------------------------------
    # GST type consistency: IGST is mutually exclusive with
    # CGST/SGST/UGST (intra-state/union-territory supply vs
    # inter-state supply) - this is a legal/structural
    # contradiction, not just uncertainty, so it's an issue.
    # --------------------------------------------------------

    if igst_amount and (cgst_amount or sgst_amount or ugst_amount):

        add_issue(
            "tax",
            "CONTRADICTORY_TAX_STRUCTURE",
            "Both IGST and CGST/SGST/UGST amounts were "
            "detected; a supply is normally either "
            "intra-state/UT (CGST+SGST or CGST+UGST) or "
            "inter-state (IGST).",
        )

    if cgst_amount and sgst_amount:

        matched, _ = amounts_match(
            cgst_amount,
            sgst_amount,
        )

        if not matched:

            add_warning(
                "tax",
                "CGST_SGST_MISMATCH",
                "CGST and SGST amounts are expected to "
                "be equal but differ.",
            )

    if cgst_amount and ugst_amount:

        matched, _ = amounts_match(
            cgst_amount,
            ugst_amount,
        )

        if not matched:

            add_warning(
                "tax",
                "CGST_UGST_MISMATCH",
                "CGST and UGST amounts are expected to "
                "be equal but differ.",
            )

    # --------------------------------------------------------
    # Place of supply vs buyer GSTIN state
    # --------------------------------------------------------

    place_of_supply_code = find_state_code_in_text(
        extracted.get("place_of_supply")
    )

    buyer_state_code = extracted.get("buyer_state_code")

    if (
        place_of_supply_code
        and buyer_state_code
        and place_of_supply_code != buyer_state_code
    ):

        add_warning(
            "place_of_supply",
            "PLACE_OF_SUPPLY_STATE_MISMATCH",
            "Place of supply state does not match "
            "the buyer GSTIN state code.",
        )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    invoice_date = extracted.get("invoice_date")
    due_date = extracted.get("due_date")

    if (
        isinstance(invoice_date, date)
        and isinstance(due_date, date)
        and due_date < invoice_date
    ):

        add_issue(
            "due_date",
            "DUE_DATE_BEFORE_INVOICE_DATE",
            "Due date is earlier than the invoice date.",
        )

    is_valid = not issues

    status = (
        "REVIEW_REQUIRED"
        if issues
        else "READY_FOR_VALIDATION"
    )

    return InvoiceValidation(
        status=status,
        is_valid=is_valid,
        issues=issues,
        warnings=warnings,
        field_issues=field_issues,
        total_difference=total_difference,
        tax_difference=tax_difference,
    )


# ============================================================
# Overall confidence
#
# A plain mean over every extracted field (including incidental
# ones like branch/swift_code) is easily skewed by how many
# minor fields happened to be found. Weight the fields that
# actually matter for AP processing more heavily instead.
# ============================================================

CRITICAL_CONFIDENCE_FIELDS = {
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "vendor_gstin",
    "buyer_gstin",
    "grand_total",
    "taxable_amount",
}

CRITICAL_CONFIDENCE_WEIGHT = 3.0


def compute_overall_confidence(
    confidence: Dict[str, float],
) -> Optional[float]:

    if not confidence:
        return None

    weighted_sum = 0.0
    weight_total = 0.0

    for field, value in confidence.items():

        weight = (
            CRITICAL_CONFIDENCE_WEIGHT
            if field in CRITICAL_CONFIDENCE_FIELDS
            else 1.0
        )

        weighted_sum += value * weight
        weight_total += weight

    return (
        weighted_sum / weight_total
        if weight_total
        else None
    )


# ============================================================
# Build canonical response
# ============================================================

def build_response(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    lines: List[InvoiceLine],
    job_id: str,
    pages: int,
    filename: Optional[str] = None,
    raw_fields: Optional[Dict[str, Any]] = None,
    field_details: Optional[Dict[str, Dict[str, Any]]] = None,
    field_issues: Optional[List[Dict[str, str]]] = None,
) -> ExtractedInvoiceResponse:

    average_confidence = compute_overall_confidence(
        confidence
    )

    return ExtractedInvoiceResponse(

        document=InvoiceDocument(
            invoice_number=extracted.get(
                "invoice_number"
            ),
            invoice_date=extracted.get(
                "invoice_date"
            ),
            due_date=extracted.get(
                "due_date"
            ),
            invoice_type=extracted.get(
                "invoice_type"
            ),
            currency=extracted.get(
                "currency",
                "INR",
            ),
            original_filename=filename,
        ),

        vendor=InvoiceVendor(
            name=extracted.get(
                "vendor_name"
            ),
            legal_name=extracted.get(
                "vendor_legal_name"
            ),
            trade_name=extracted.get(
                "vendor_trade_name"
            ),
            gstin=extracted.get(
                "vendor_gstin"
            ),
            pan=extracted.get(
                "vendor_pan"
            ),
            address=extracted.get(
                "vendor_address"
            ),
            state=extracted.get(
                "vendor_state"
            ),
            state_code=extracted.get(
                "vendor_state_code"
            ),
            country=extracted.get(
                "vendor_country"
            ),
            email=extracted.get(
                "vendor_email"
            ),
            phone=extracted.get(
                "vendor_phone"
            ),
            website=extracted.get(
                "vendor_website"
            ),
        ),

        buyer=InvoiceBuyer(
            name=extracted.get(
                "buyer_name"
            ),
            legal_name=extracted.get(
                "buyer_legal_name"
            ),
            trade_name=extracted.get(
                "buyer_trade_name"
            ),
            gstin=extracted.get(
                "buyer_gstin"
            ),
            pan=extracted.get(
                "buyer_pan"
            ),
            address=extracted.get(
                "buyer_address"
            ),
            shipping_address=extracted.get(
                "buyer_shipping_address"
            ),
            state=extracted.get(
                "buyer_state"
            ),
            state_code=extracted.get(
                "buyer_state_code"
            ),
            country=extracted.get(
                "buyer_country"
            ),
            email=extracted.get(
                "buyer_email"
            ),
            phone=extracted.get(
                "buyer_phone"
            ),
        ),

        reference=InvoiceReference(
            po_number=extracted.get(
                "po_number"
            ),
            po_date=extracted.get(
                "po_date"
            ),
            delivery_note_number=extracted.get(
                "delivery_note_number"
            ),
            delivery_note_date=extracted.get(
                "delivery_note_date"
            ),
            quotation_number=extracted.get(
                "quotation_number"
            ),
            quotation_date=extracted.get(
                "quotation_date"
            ),
            reference_number=extracted.get(
                "reference_number"
            ),
            contract_number=extracted.get(
                "contract_number"
            ),
            order_number=extracted.get(
                "order_number"
            ),
        ),

        amounts=InvoiceAmounts(
            subtotal=extracted.get(
                "subtotal"
            ),
            taxable_amount=extracted.get(
                "taxable_amount"
            ),
            discount=extracted.get(
                "discount"
            ),
            cgst_amount=extracted.get(
                "cgst_amount"
            ),
            sgst_amount=extracted.get(
                "sgst_amount"
            ),
            igst_amount=extracted.get(
                "igst_amount"
            ),
            ugst_amount=extracted.get(
                "ugst_amount"
            ),
            cess_amount=extracted.get(
                "cess_amount"
            ),
            total_tax=extracted.get(
                "total_tax"
            ),
            tds_amount=extracted.get(
                "tds_amount"
            ),
            other_charges=extracted.get(
                "other_charges"
            ),
            shipping_charges=extracted.get(
                "shipping_charges"
            ),
            freight_charges=extracted.get(
                "freight_charges"
            ),
            handling_charges=extracted.get(
                "handling_charges"
            ),
            round_off=extracted.get(
                "round_off"
            ),
            grand_total=extracted.get(
                "grand_total"
            ),
            amount_paid=extracted.get(
                "amount_paid"
            ),
            balance_due=extracted.get(
                "balance_due"
            ),
        ),

        payment=InvoicePayment(
            payment_terms=extracted.get(
                "payment_terms"
            ),
            bank_name=extracted.get(
                "bank_name"
            ),
            account_name=extracted.get(
                "account_name"
            ),
            account_number=extracted.get(
                "account_number"
            ),
            ifsc_code=extracted.get(
                "ifsc_code"
            ),
            branch=extracted.get(
                "branch"
            ),
            swift_code=extracted.get(
                "swift_code"
            ),
            upi_id=extracted.get(
                "upi_id"
            ),
        ),

        tax=InvoiceTax(
            place_of_supply=extracted.get(
                "place_of_supply"
            ),
            reverse_charge=extracted.get(
                "reverse_charge"
            ),
            tax_type=extracted.get(
                "tax_type"
            ),
            hsn_sac=extracted.get(
                "hsn_sac"
            ),
            cgst_rate=extracted.get(
                "cgst_rate"
            ),
            sgst_rate=extracted.get(
                "sgst_rate"
            ),
            igst_rate=extracted.get(
                "igst_rate"
            ),
            ugst_rate=extracted.get(
                "ugst_rate"
            ),
            cess_rate=extracted.get(
                "cess_rate"
            ),
        ),

        compliance=InvoiceCompliance(
            irn=extracted.get(
                "irn"
            ),
            acknowledgement_number=extracted.get(
                "acknowledgement_number"
            ),
            acknowledgement_date=extracted.get(
                "acknowledgement_date"
            ),
            einvoice_status=extracted.get(
                "einvoice_status"
            ),
            qr_code_data=extracted.get(
                "qr_code_data"
            ),
            reverse_charge=extracted.get(
                "reverse_charge"
            ),
            export_invoice=extracted.get(
                "export_invoice"
            ),
        ),

        invoice_lines=lines,

        extraction=ExtractionMetadata(
            status="SUCCESS",
            provider="AWS_TEXTRACT",
            job_id=job_id,
            confidence=average_confidence,
            field_confidence=confidence,
            field_sources=sources,
            field_details=field_details or {},
            pages_processed=pages,
        ),

        validation=validate_invoice(
            extracted,
            lines,
            field_issues,
        ),

        raw_fields=raw_fields or {},
    )


# ============================================================
# AnalyzeExpense: start, poll, fetch every page
# ============================================================

async def run_expense_analysis(
    s3_key: str,
) -> Tuple[List[Dict[str, Any]], str]:

    start_response = await asyncio.to_thread(
        call_textract_with_retry,
        textract_client.start_expense_analysis,
        DocumentLocation={
            "S3Object": {
                "Bucket": BUCKET_NAME,
                "Name": s3_key,
            }
        },
    )

    job_id = start_response["JobId"]

    start_time = time.monotonic()

    status = None

    while True:

        response = await asyncio.to_thread(
            call_textract_with_retry,
            textract_client.get_expense_analysis,
            JobId=job_id,
        )

        status = response.get(
            "JobStatus"
        )

        if status in {
            "SUCCEEDED",
            "PARTIAL_SUCCESS",
            "FAILED",
        }:

            break

        if (
            time.monotonic()
            - start_time
            > 300
        ):

            raise TimeoutError(
                "Textract processing timed out."
            )

        await asyncio.sleep(2)

    if status == "FAILED":

        raise RuntimeError(
            "AWS Textract invoice analysis failed."
        )

    documents = await asyncio.to_thread(
        get_all_expense_documents,
        job_id,
    )

    if not documents:

        raise RuntimeError(
            "No invoice information was "
            "returned by Textract."
        )

    return documents, job_id

def reconcile_gstins(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    field_details: Dict[str, Dict[str, Any]],
    full_text: Optional[str],
):

    # A Textract query can answer confidently but attribute the
    # GSTIN to the wrong party (seen in production: BUYER_GSTIN
    # query returned the seller's GSTIN verbatim). Detect the two
    # tell-tale signatures and correct using the full-text
    # anchored classification, which is immune to this failure
    # mode since it locates GSTINs relative to party name
    # position rather than trusting a single query's own framing.

    anchored = classify_party_gstins(
        full_text,
        extracted.get("vendor_name"),
        extracted.get("buyer_name"),
    )

    vendor_gstin = extracted.get("vendor_gstin")
    buyer_gstin = extracted.get("buyer_gstin")

    def _overwrite_gstin(target: str, value: str):
        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            target,
            value,
            85.0,
            "REGEX_FULLTEXT_ANCHORED",
            ExtractionMethod.REGEX,
            overwrite=True,
        )

    # Signature 1: vendor and buyer ended up with the identical
    # GSTIN - a real invoice never has both parties share one
    # registration, so this is almost certainly a cross-party
    # mix-up in a query answer.
    if (
        vendor_gstin
        and buyer_gstin
        and vendor_gstin == buyer_gstin
    ):

        if (
            anchored.get("buyer_gstin")
            and anchored["buyer_gstin"] != vendor_gstin
        ):
            _overwrite_gstin("buyer_gstin", anchored["buyer_gstin"])

        elif "buyer_gstin" not in anchored:
            # No valid anchored candidate for buyer either -
            # don't guess further, but at least don't keep a
            # value we know is wrong.
            del extracted["buyer_gstin"]

        if (
            anchored.get("vendor_gstin")
            and anchored["vendor_gstin"] != buyer_gstin
        ):
            _overwrite_gstin("vendor_gstin", anchored["vendor_gstin"])

        return

    # Signature 2: a party's GSTIN fails structural validation
    # but a differently-sourced, structurally valid candidate
    # exists for that same party - prefer the valid one.
    for target in ("vendor_gstin", "buyer_gstin"):

        current = extracted.get(target)

        if (
            current
            and not is_valid_gstin_format(normalize_gstin(current))
            and anchored.get(target)
            and is_valid_gstin_format(anchored[target])
        ):
            _overwrite_gstin(target, anchored[target])

    # Gap-fill: any party still missing a GSTIN entirely.
    for target, value in anchored.items():
        if not extracted.get(target):
            _overwrite_gstin(target, value)

def reconcile_taxable_amount(
    extracted: Dict[str, Any],
    confidence: Dict[str, float],
    sources: Dict[str, str],
    field_details: Dict[str, Dict[str, Any]],
):

    # A column-layout invoice can cause Textract's TAXABLE_AMOUNT
    # query to misread text from an adjacent column into the
    # figure (e.g. a stray leading digit). subtotal, sourced from
    # AnalyzeExpense's own SUMMARY field rather than a free-form
    # query answer, is less prone to this failure mode. Prefer
    # whichever of the two actually reconciles against the
    # printed grand total.

    taxable_amount = normalize_number(extracted.get("taxable_amount"))
    subtotal = normalize_number(extracted.get("subtotal"))
    grand_total = normalize_number(extracted.get("grand_total"))
    total_tax = normalize_number(extracted.get("total_tax")) or 0.0

    if (
        taxable_amount is None
        or subtotal is None
        or grand_total is None
        or taxable_amount == subtotal
    ):
        return

    taxable_matches, _ = amounts_match(
        taxable_amount + total_tax, grand_total
    )

    subtotal_matches, _ = amounts_match(
        subtotal + total_tax, grand_total
    )

    if subtotal_matches and not taxable_matches:

        _set_field(
            extracted,
            confidence,
            sources,
            field_details,
            "taxable_amount",
            subtotal,
            confidence.get("subtotal", 75.0),
            "RECONCILED_FROM_SUBTOTAL",
            ExtractionMethod.DERIVED,
            overwrite=True,
        )

# ============================================================
# Main service
# ============================================================

async def extract_invoice_from_s3(
    s3_key: str,
    filename: Optional[str] = None,
) -> ExtractedInvoiceResponse:

    try:

        # ====================================================
        # 1. AnalyzeExpense and Queries are independent
        # Textract jobs on the same document - run them
        # concurrently instead of back-to-back to roughly
        # halve end-to-end latency.
        # ====================================================

        (
            (documents, job_id),
            (query_results, full_text),
        ) = await asyncio.gather(
            run_expense_analysis(s3_key),
            asyncio.to_thread(
                run_queries,
                s3_key,
            ),
        )

        summary_fields = []
        line_item_groups = []

        for document in documents:

            summary_fields.extend(
                document.get(
                    "SummaryFields",
                    [],
                )
            )

            line_item_groups.extend(
                document.get(
                    "LineItemGroups",
                    [],
                )
            )

        field_details: Dict[str, Dict[str, Any]] = {}

        # ====================================================
        # 2. Summary fields
        # ====================================================

        (
            extracted,
            confidence,
            sources,
        ) = parse_summary_fields(
            summary_fields,
            field_details,
        )

        # ====================================================
        # 3. Line items
        # ====================================================

        lines = parse_line_items(
            line_item_groups
        )

        # ====================================================
        # 4. Apply critical field queries (already fetched
        # concurrently above)
        # ====================================================

        apply_query_fallback(
            extracted,
            confidence,
            sources,
            field_details,
            query_results,
        )

        # ====================================================
        # 5. Regex fallback (address text, then full page text)
        # ====================================================

        apply_regex_fallback(
            extracted,
            confidence,
            sources,
            field_details,
        )

        apply_fulltext_fallback(
            extracted,
            confidence,
            sources,
            field_details,
            full_text,
        )
        reconcile_gstins(
            extracted,
            confidence,
            sources,
            field_details,
            full_text,
        )

        reconcile_taxable_amount(
            extracted,
            confidence,
            sources,
            field_details,
        )

        # ====================================================
        # 6. Normalize
        # ====================================================

        field_issues: List[Dict[str, str]] = []

        normalize_extracted_fields(
            extracted,
            field_issues,
        )

        # ====================================================
        # 7. Derive seller/buyer PAN from GSTIN
        # ====================================================

        derive_pan_numbers(
            extracted,
            confidence,
            sources,
            field_details,
            field_issues,
        )

        # ====================================================
        # 8. Derive states, legal/trade names, GST tax type
        # ====================================================

        derive_states(
            extracted
        )

        derive_legal_and_trade_names(
            extracted,
            confidence,
            sources,
            field_details,
        )

        derive_tax_type(
            extracted,
            field_details,
        )

        # ====================================================
        # 9. Build response
        #
        # raw_fields intentionally excludes the raw
        # AnalyzeExpense SummaryFields blocks - each one
        # carries full bounding-box/polygon geometry per
        # field/page, which bloats the response by tens of
        # KB without adding anything a caller needs (every
        # meaningful value/confidence/source is already
        # surfaced above). Only the small Queries answers are
        # kept for traceability.
        # ====================================================

        raw_fields = {
            "query_results": query_results,
        }

        return build_response(
            extracted=extracted,
            confidence=confidence,
            sources=sources,
            lines=lines,
            job_id=job_id,
            pages=len(documents),
            filename=filename,
            raw_fields=raw_fields,
            field_details=field_details,
            field_issues=field_issues,
        )

    except (
        ClientError,
        BotoCoreError,
    ) as exc:

        raise RuntimeError(
            f"AWS Textract error: {str(exc)}"
        ) from exc

    except Exception as exc:

        raise RuntimeError(
            f"Invoice extraction failed: {str(exc)}"
        ) from exc