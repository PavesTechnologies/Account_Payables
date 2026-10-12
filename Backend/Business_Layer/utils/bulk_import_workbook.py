# Backend/Business_Layer/utils/bulk_import_workbook.py
"""Excel templates, parsing and result sheets for bulk import (APM_AUTOMATION_PLAN.md 6.7).

Pure (openpyxl only - no DB / S3) so every rule is unit-tested. One row per invoice:
  * PAYMENTS      - one payment of one invoice; several rows may share one UTR (one transfer that
                    paid several invoices). Receipt file name is mandatory.
  * TDS_CHALLANS  - one invoice's share of a challan; rows with the same serial + BSR + date are
                    one challan. Challan file name is mandatory.
  * TDS_FILINGS   - one invoice in a quarterly statement; rows with the same acknowledgement number
                    are one filing. Acknowledgement file name is mandatory.
"""
import datetime
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from Backend.Business_Layer.utils.report_export import INDIAN_MONEY_FORMAT

MAX_ROWS = 500
PAYMENT_MODES = ("NEFT", "RTGS", "IMPS", "UPI", "BANK_TRANSFER", "CHEQUE", "DEMAND_DRAFT")
FILING_FORMS = ("26Q", "27Q", "24Q", "27EQ")


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    kind: str = "text"            # text | date | money | int | choice | flag
    required: bool = False
    info: bool = False            # pre-filled for reference only - never read back
    choices: Tuple[str, ...] = ()
    width: int = 18


COLUMNS: Dict[str, List[Column]] = {
    "PAYMENTS": [
        Column("invoice_id", "Invoice ID", "int", info=False, width=11),
        Column("invoice_number", "Invoice Number", required=True, width=22),
        Column("vendor_name", "Vendor", info=True, width=30),
        Column("remaining_amount", "Remaining Payable", "money", info=True, width=16),
        Column("payment_mode", "Payment Mode", "choice", required=True, choices=PAYMENT_MODES, width=15),
        # Optional: left blank, they are read from the receipt (values typed here are cross-checked).
        Column("payment_date", "Payment Date", "date", width=14),
        Column("amount", "Amount Paid", "money", width=14),
        Column("reference_number", "UTR / Reference", width=22),
        Column("receipt_file", "Receipt File Name", required=True, width=28),
        Column("remarks", "Remarks", width=30),
    ],
    "TDS_CHALLANS": [
        Column("challan_serial_no", "Challan Serial No", required=True, width=14),
        Column("bsr_code", "BSR Code", required=True, width=12),
        Column("deposit_date", "Deposit Date", "date", required=True, width=14),
        Column("section_code", "Section", width=10),
        Column("tax_amount", "Challan Tax Amount", "money", required=True, width=16),
        Column("surcharge", "Surcharge", "money", width=11),
        Column("cess", "Cess", "money", width=10),
        Column("interest", "Interest", "money", width=11),
        Column("fee", "Fee", "money", width=10),
        Column("challan_file", "Challan File Name", required=True, width=26),
        Column("invoice_id", "Invoice ID", "int", width=11),
        Column("invoice_number", "Invoice Number", required=True, width=22),
        Column("vendor_name", "Vendor", info=True, width=28),
        Column("tds_amount", "Invoice TDS", "money", info=True, width=13),
        Column("allocated_tds_amount", "TDS Paid By This Challan", "money", width=18),
    ],
    "TDS_FILINGS": [
        Column("form_type", "Form", "choice", required=True, choices=FILING_FORMS, width=8),
        Column("financial_year", "Financial Year", required=True, width=13),
        Column("quarter", "Quarter", "int", required=True, width=9),
        Column("acknowledgement_no", "Token / Ack No", required=True, width=20),
        Column("filing_date", "Filing Date", "date", required=True, width=13),
        Column("is_revision", "Correction (Y/N)", "flag", width=14),
        Column("ack_file", "Acknowledgement File Name", required=True, width=28),
        Column("invoice_id", "Invoice ID", "int", width=11),
        Column("invoice_number", "Invoice Number", required=True, width=22),
        Column("vendor_name", "Vendor", info=True, width=28),
        Column("tds_amount", "Invoice TDS", "money", info=True, width=13),
    ],
}

DOCUMENT_COLUMN = {"PAYMENTS": "receipt_file", "TDS_CHALLANS": "challan_file", "TDS_FILINGS": "ack_file"}

INSTRUCTIONS = {
    "PAYMENTS": [
        "One row per invoice payment. Rows are pre-filled with invoices that are ready for payment - delete the ones you are not paying. Do not change Invoice ID.",
        "Fill Payment Mode and Receipt File Name (the bank receipt / advice uploaded with this sheet). A full path is fine - only the file name is used.",
        "Payment Date, Amount Paid and UTR / Reference are optional: left blank they are read from the receipt; if you fill them they are checked against it.",
        "One receipt that paid several invoices: put it on each of those rows and enter each invoice's Amount Paid - the amounts must add up to the receipt.",
        "Rows whose receipt confirms everything are recorded; anything missing or different waits for review.",
    ],
    "TDS_CHALLANS": [
        "One row per invoice paid by a challan. Rows are pre-filled with invoices whose TDS is deducted but not deposited.",
        "Rows with the same Challan Serial No, BSR Code and Deposit Date form one challan - repeat the challan columns on each of its rows.",
        "Challan Tax Amount is the challan's total tax; the invoices' 'TDS Paid By This Challan' must add up to it (blank = the invoice's full TDS).",
        "Challan File Name is mandatory: the challan counterfoil, uploaded together with this sheet.",
    ],
    "TDS_FILINGS": [
        "One row per invoice covered by a quarterly statement. Rows are pre-filled with invoices whose TDS is deposited but not filed.",
        "Rows with the same Token / Ack No form one filing. Financial Year looks like 2026-27; Quarter is 1-4.",
        "Acknowledgement File Name is mandatory: the provisional receipt, uploaded together with this sheet.",
    ],
}

_HEADER_FILL = PatternFill("solid", fgColor="0A0082")
_INFO_FILL = PatternFill("solid", fgColor="EEF0F6")
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y")


def file_name_of(value: Any) -> str:
    """A Windows path, a 'folder/file.pdf' path or a bare name -> just the file name ('advice-7.pdf')."""
    return str(value or "").strip().replace("\\", "/").rsplit("/", 1)[-1].strip()


def _header_text(column: Column) -> str:
    return column.header + (" *" if column.required else "")


def _norm_header(text: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower().replace("*", ""))


# ======================================================================
# Template
# ======================================================================
def build_template(kind: str, rows: Iterable[Dict[str, Any]] = ()) -> bytes:
    columns = COLUMNS[kind]
    wb = Workbook()
    ws = wb.active
    ws.title = {"PAYMENTS": "Payments", "TDS_CHALLANS": "Challans", "TDS_FILINGS": "Filings"}[kind]
    for idx, column in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=idx, value=_header_text(column))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(idx)].width = column.width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"

    written = 0
    for r, row in enumerate(rows, start=2):
        written += 1
        for idx, column in enumerate(columns, start=1):
            value = row.get(column.key)
            if isinstance(value, Decimal):
                value = float(value)
            cell = ws.cell(row=r, column=idx, value=value)
            if column.info or column.key == "invoice_id":
                cell.fill = _INFO_FILL
            if column.kind == "date":
                cell.number_format = "dd-mm-yyyy"
            elif column.kind == "money":
                cell.number_format = INDIAN_MONEY_FORMAT
    last = max(written + 1, 2) + 200
    for idx, column in enumerate(columns, start=1):
        letter = get_column_letter(idx)
        if column.kind == "choice":
            dv = DataValidation(type="list", formula1='"' + ",".join(column.choices) + '"', allow_blank=not column.required)
            ws.add_data_validation(dv)
            dv.add(f"{letter}2:{letter}{last}")
        if column.kind == "date":
            for r in range(2, last + 1):
                ws.cell(row=r, column=idx).number_format = "dd-mm-yyyy"

    guide = wb.create_sheet("Instructions")
    guide.column_dimensions["A"].width = 120
    for i, line in enumerate(INSTRUCTIONS[kind] + ["", "Columns marked * are required. Grey columns are for reference and are not read."], start=1):
        guide.cell(row=i, column=1, value=line).alignment = Alignment(wrap_text=True)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ======================================================================
# Parsing
# ======================================================================
class WorkbookRejected(ValueError):
    """The workbook as a whole cannot be read; nothing is stored."""


def _date(value) -> Optional[datetime.date]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{text}' is not a date (use dd-mm-yyyy)")


def _money(value) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value).replace(",", "").replace("₹", "").strip())
    except InvalidOperation:
        raise ValueError(f"'{value}' is not an amount")
    return amount.quantize(Decimal("0.01"))


def _convert(column: Column, value) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if column.kind == "date":
        return _date(value)
    if column.kind == "money":
        return _money(value)
    if column.kind == "int":
        try:
            return int(Decimal(str(value).strip()))
        except InvalidOperation:
            raise ValueError(f"'{value}' is not a whole number")
    if column.kind == "flag":
        return str(value).strip().upper() in ("Y", "YES", "TRUE", "1")
    text = str(value).strip()
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))  # e.g. a numeric UTR / serial typed into Excel
    if column.kind == "choice":
        text = text.upper().replace(" ", "_")
        if text not in column.choices:
            raise ValueError(f"'{value}' must be one of {', '.join(column.choices)}")
    return text


@dataclass
class ParsedRow:
    row_number: int
    data: Dict[str, Any]
    problems: List[str]


def parse_workbook(kind: str, content: bytes) -> List[ParsedRow]:
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise WorkbookRejected("The file is not a readable .xlsx workbook.") from exc
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        raise WorkbookRejected("The first sheet is empty.")
    columns = COLUMNS[kind]
    by_header = {_norm_header(c.header): c for c in columns}
    positions: Dict[str, int] = {}
    for idx, text in enumerate(header):
        column = by_header.get(_norm_header(text))
        if column is not None and not column.info:
            positions[column.key] = idx
    missing = [c.header for c in columns if c.required and c.key not in positions]
    if missing:
        raise WorkbookRejected("Missing column(s): " + ", ".join(missing) + ". Download a fresh template.")

    out: List[ParsedRow] = []
    for number, values in enumerate(rows, start=2):
        values = list(values or [])
        cells = {key: (values[i] if i < len(values) else None) for key, i in positions.items()}
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in cells.values()):
            continue
        if len(out) >= MAX_ROWS:
            raise WorkbookRejected(f"A sheet can have at most {MAX_ROWS} rows.")
        data, problems = {}, []
        for column in columns:
            if column.key not in positions:
                continue
            try:
                data[column.key] = _convert(column, cells.get(column.key))
            except ValueError as exc:
                problems.append(f"{column.header}: {exc}")
                data[column.key] = None
                continue
            if column.required and data[column.key] in (None, ""):
                problems.append(f"{column.header} is required")
        out.append(ParsedRow(number, data, problems))
    if not out:
        raise WorkbookRejected("The sheet has no rows to import.")
    return out


def group_key(kind: str, data: Dict[str, Any]) -> Optional[str]:
    if kind == "PAYMENTS":
        ref = re.sub(r"\s", "", str(data.get("reference_number") or "")).upper()
        return f"UTR:{ref}" if ref else None
    if kind == "TDS_CHALLANS":
        if data.get("challan_serial_no") and data.get("bsr_code") and data.get("deposit_date"):
            serial = re.sub(r"\D", "", str(data["challan_serial_no"])).zfill(5)
            return f"CHALLAN:{re.sub(r'[^0-9]', '', str(data['bsr_code']))}:{data['deposit_date']}:{serial}"
        return None
    ack = re.sub(r"\s", "", str(data.get("acknowledgement_no") or "")).upper()
    return f"FILING:{ack}" if ack else None


# ======================================================================
# Results
# ======================================================================
def build_results(kind: str, rows: Iterable[Dict[str, Any]]) -> bytes:
    """Same columns as the template plus Import Status / Messages / Recorded Reference."""
    columns = [c for c in COLUMNS[kind] if not c.info]
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    headers = [c.header for c in columns] + ["Import Status", "Messages", "Recorded Reference"]
    for idx, text in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=idx, value=text)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        ws.column_dimensions[get_column_letter(idx)].width = 40 if text == "Messages" else 18
    ws.freeze_panes = "A2"
    fills = {"RECORDED": "D1FAE5", "READY": "DBEAFE", "NEEDS_REVIEW": "FEF3C7", "ERROR": "FEE2E2", "SKIPPED": "F1F5F9"}
    for r, row in enumerate(rows, start=2):
        data = row.get("data") or {}
        for idx, column in enumerate(columns, start=1):
            value = data.get(column.key)
            ws.cell(row=r, column=idx, value=float(value) if isinstance(value, Decimal) else value)
        status = row.get("status")
        ws.cell(row=r, column=len(columns) + 1, value=status).fill = PatternFill("solid", fgColor=fills.get(status, "FFFFFF"))
        ws.cell(row=r, column=len(columns) + 2, value="; ".join(m.get("message", "") for m in (row.get("messages") or [])))
        ws.cell(row=r, column=len(columns) + 3, value=row.get("result_reference"))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
