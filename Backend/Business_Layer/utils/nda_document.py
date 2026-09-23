# Backend/Business_Layer/utils/nda_document.py
"""NDA document rendering: approved template text -> PDF bytes.

PyMuPDF (``fitz``) is already a project dependency (used read-only for invoice
OCR in pdf_utils.py); this is the first write-mode use. It is imported INSIDE
``build_nda_pdf`` rather than at module scope on purpose: PyMuPDF is a heavy
native dependency that is not installed in every environment, and a top-level
import would make this module - and every test that touches the NDA service -
uncollectable. The same lazy-import approach the codebase already uses in
Business_Layer/utils/notifications.py.

Only the placeholders listed in SUPPORTED_PLACEHOLDERS are substituted. The
template body is otherwise reproduced verbatim - no legal clause is ever
generated, reworded or inferred here.

``build_nda_pdf`` already takes finished text rather than template data, so
the same renderer produces both the initial generated NDA and the final
document built from the user's persisted edits - there is deliberately no
second document-generation path.
"""
from __future__ import annotations

import datetime
import re
from typing import Dict, Optional

SUPPORTED_PLACEHOLDERS = (
    "VENDOR_NAME",
    "VENDOR_CODE",
    "PR_NUMBER",
    "DEPARTMENT",
    "PURCHASE_CATEGORY",
    "BUSINESS_REQUIREMENT",
    "COMPANY_NAME",
    "EFFECTIVE_DATE",
)

_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Z_]+)\s*\}\}")

# Upper bound on the editable NDA wording accepted from the client. Generous
# enough for any realistic agreement (~40 A4 pages of text) while keeping a
# single row - and the PDF rendered from it - bounded.
MAX_NDA_CONTENT_CHARS = 200_000

# Control characters that must never reach Postgres (NUL is rejected outright
# by TEXT) or the PDF renderer. Tab, newline and carriage return are kept -
# they are legitimate layout in an agreement body.
_DISALLOWED_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Page geometry (A4 at 72dpi) and typography for the generated document.
_PAGE_WIDTH = 595
_PAGE_HEIGHT = 842
_MARGIN = 56
_TITLE_FONT_SIZE = 15
_BODY_FONT_SIZE = 10.5
_LINE_HEIGHT = 15


def render_template_body(body: str, context: Dict[str, Optional[str]]) -> str:
    """Substitute supported placeholders in an approved template body.

    An unknown placeholder is left exactly as written rather than silently
    blanked, so a template typo is visible in review instead of producing a
    document with a missing term. A supported placeholder with no value
    becomes an empty string.
    """
    if not body:
        raise ValueError("NDA template body is empty")

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in SUPPORTED_PLACEHOLDERS:
            return match.group(0)
        value = context.get(name)
        return "" if value is None else str(value)

    return _PLACEHOLDER_PATTERN.sub(_replace, body)


def normalize_nda_content(content) -> str:
    """Validate and clean editable NDA wording supplied by the client.

    The NDA is rendered as plain text into a PDF - there is no markup layer
    and no template re-evaluation of user input, so nothing here is
    interpreted as code. What this guards against is unusable input reaching
    storage or the renderer: a non-string payload, a blank document, one large
    enough to be abusive, and control characters that Postgres TEXT (NUL) or
    the PDF renderer cannot represent.

    Returns the cleaned content. Raises ValueError with a caller-safe message.
    """
    if not isinstance(content, str):
        raise ValueError("NDA content must be text")

    # Normalize line endings first so a CRLF document is not counted or
    # rendered differently from the same document with LF endings.
    cleaned = content.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _DISALLOWED_CONTROL_CHARS.sub("", cleaned)

    if not cleaned.strip():
        raise ValueError("NDA content cannot be empty")

    if len(cleaned) > MAX_NDA_CONTENT_CHARS:
        raise ValueError(
            "NDA content exceeds the maximum allowed length of "
            f"{MAX_NDA_CONTENT_CHARS} characters"
        )

    return cleaned


def build_nda_document_title(vendor_name: Optional[str]) -> str:
    """Title line printed on the generated PDF. Shared by initial generation
    and the final send-time document so both produce an identical heading."""

    return f"Non-Disclosure Agreement - {vendor_name or 'Vendor'}"


def build_nda_context(
    vendor_name: Optional[str],
    vendor_code: Optional[str],
    pr_number: Optional[str],
    department_name: Optional[str],
    purchase_category_name: Optional[str],
    business_requirement: Optional[str],
    company_name: Optional[str],
    effective_date: Optional[datetime.date] = None,
) -> Dict[str, Optional[str]]:

    effective = effective_date or datetime.date.today()
    return {
        "VENDOR_NAME": vendor_name,
        "VENDOR_CODE": vendor_code,
        "PR_NUMBER": pr_number,
        "DEPARTMENT": department_name,
        "PURCHASE_CATEGORY": purchase_category_name,
        "BUSINESS_REQUIREMENT": business_requirement,
        "COMPANY_NAME": company_name,
        "EFFECTIVE_DATE": effective.isoformat(),
    }


def build_nda_pdf(title: str, body: str) -> bytes:
    """Render the already-substituted NDA text to PDF bytes via PyMuPDF.

    Returns bytes ready for S3 upload / email attachment - nothing is written
    to disk and the bytes are never persisted to Postgres.
    """
    import fitz  # lazy: heavy native dep, see module docstring

    document = fitz.open()
    page = document.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)

    cursor_y = _MARGIN
    page.insert_text(
        (_MARGIN, cursor_y), title, fontname="helvetica-bold", fontsize=_TITLE_FONT_SIZE
    )
    cursor_y += _LINE_HEIGHT * 2

    for line in _wrap_body(body):
        if cursor_y > _PAGE_HEIGHT - _MARGIN:
            page = document.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
            cursor_y = _MARGIN
        if line:
            page.insert_text(
                (_MARGIN, cursor_y), line, fontname="helvetica", fontsize=_BODY_FONT_SIZE
            )
        cursor_y += _LINE_HEIGHT

    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def _wrap_body(body: str, max_chars: int = 95):
    """Naive width-based wrapping. Blank lines in the template are preserved
    as blank lines so paragraph breaks in the approved wording survive."""

    for raw_line in (body or "").splitlines():
        stripped = raw_line.rstrip()
        if not stripped:
            yield ""
            continue

        words = stripped.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars and current:
                yield current
                current = word
            else:
                current = candidate
        if current:
            yield current


def build_nda_object_key(
    pr_number: Optional[str],
    vendor_code: Optional[str],
    version: Optional[str],
    signed: bool = False,
    year: Optional[int] = None,
) -> str:
    """ap/nda/{generated|signed}/{year}/{pr_number}/{vendor_code}/NDA-{pr}-{vendor}-v{version}.pdf"""

    safe_pr = _safe_segment(pr_number or "NO-PR")
    safe_vendor = _safe_segment(vendor_code or "NO-VENDOR")
    safe_version = _safe_segment(version or "1")
    folder = "signed" if signed else "generated"
    effective_year = year or datetime.date.today().year

    return (
        f"ap/nda/{folder}/{effective_year}/{safe_pr}/{safe_vendor}/"
        f"NDA-{safe_pr}-{safe_vendor}-v{safe_version}.pdf"
    )


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-.")
    return cleaned or "NA"
