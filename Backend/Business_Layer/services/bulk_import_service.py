# Backend/Business_Layer/services/bulk_import_service.py
"""Bulk import of payments / TDS challans / TDS filings from Excel + documents
(APM_AUTOMATION_PLAN.md 6.7). Orchestration only: rows are recorded by the existing services -
PaymentTrackingService.record_payment (+ upload_document) and TdsChallanService.create_challan /
create_filing - so every existing validation, history and audit still applies.

Flow
  1. create_job - read the sheet, match each row to its document (by file name; loose files or a
     ZIP), store the documents, one bulk_import_row per sheet row.
  2. validate_job (background) - read every document once (Textract, 2 at a time) and check it
     against its row(s):
       PAYMENTS     invoice resolves and is payable, amounts within the remaining balance (across
                    the whole sheet), reference format; the receipt confirms the UTR, date and
                    amount (rows sharing a UTR must add up to the receipt), the transfer did not
                    fail, the beneficiary looks like the vendor.
       TDS_CHALLANS each challan group through TdsChallanService.validate_challan, plus the
                    challan document must show the same serial / BSR / date / tax.
       TDS_FILINGS  each filing group through validate_filing, plus the acknowledgement must
                    show the same token number / date.
     Row -> READY (everything confirmed) / NEEDS_REVIEW (a mismatch a person must look at) /
     ERROR (cannot be recorded).
  3. record - READY rows (and NEEDS_REVIEW rows a person accepts) are recorded. SharePoint jobs
     (auto_record) record READY rows on their own; manual uploads wait for "Record verified rows".
"""
import asyncio
import datetime
import json
import logging
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
from starlette.concurrency import run_in_threadpool

from Backend.API_Layer.interface.payment_interface import RecordPaymentRequest
from Backend.API_Layer.utils.receipt_extraction_fields import extract_receipt_from_s3
from Backend.API_Layer.utils.s3_utils import get_object_bytes, upload_to_s3
from Backend.API_Layer.utils.tds_document_extraction import extract_challan_from_s3, extract_filing_from_s3
from Backend.Business_Layer.services.payment_receipt_extraction_service import names_look_alike
from Backend.Business_Layer.services.payment_tracking_service import _REFERENCE_PATTERNS, PaymentTrackingService
from Backend.Business_Layer.services.tds_challan_service import DEPOSITED, TdsChallanService
from Backend.Business_Layer.utils import bulk_import_workbook as wbk
from Backend.Business_Layer.utils import bulk_upload_files as bf
from Backend.Business_Layer.utils.statutory_calendar import financial_quarter
from Backend.Data_Access_Layer.models.bulk_import import (
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_NEEDS_REVIEW,
    JOB_RECORDING,
    JOB_VALIDATED,
    JOB_VALIDATING,
    KIND_PAYMENTS,
    KIND_TDS_CHALLANS,
    KIND_TDS_FILINGS,
    KINDS,
    ROW_ERROR,
    ROW_NEEDS_REVIEW,
    ROW_PENDING,
    ROW_READY,
    ROW_RECORDED,
    ROW_SKIPPED,
    SOURCE_MANUAL,
    BulkImportJob,
    BulkImportRow,
)
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.utils.database import SessionLocal

logger = logging.getLogger(__name__)

CONCURRENCY = 2
PERMISSIONS = {KIND_PAYMENTS: ["PAYMENT_PROCESS"], KIND_TDS_CHALLANS: ["TDS_TRACKING_UPDATE"], KIND_TDS_FILINGS: ["TDS_TRACKING_UPDATE"]}
_EXTRACTORS = {KIND_PAYMENTS: extract_receipt_from_s3, KIND_TDS_CHALLANS: extract_challan_from_s3, KIND_TDS_FILINGS: extract_filing_from_s3}
DOCUMENT_TYPES = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _jsonable(value):
    return json.loads(json.dumps(value, default=lambda v: str(v) if isinstance(v, (Decimal, datetime.date)) else v))


def _msg(severity: str, message: str) -> Dict[str, str]:
    return {"severity": severity, "message": message}


def _ref(value) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _d(value) -> Optional[datetime.date]:
    if not value:
        return None
    return value if isinstance(value, datetime.date) else datetime.date.fromisoformat(str(value)[:10])


def _m(value) -> Optional[Decimal]:
    return None if value in (None, "") else Decimal(str(value)).quantize(Decimal("0.01"))


MAX_DOCUMENTS = 300
MAX_DOCUMENT_BYTES = 300 * 1024 * 1024


def expand_documents(documents: Sequence[Tuple[str, Optional[str], bytes]]) -> List["bf.CandidateFile"]:
    """Receipts / challans / acknowledgements uploaded with a sheet: loose files and / or ZIPs.
    Same per-file checks as invoice bulk upload (type, size, real PDF / image), a higher count
    limit (a payment sheet can carry many receipts) and the same ZIP safety (no nesting, no
    encryption, sizes read with a hard cap, folder paths dropped)."""
    import io
    import zipfile

    out: List[bf.CandidateFile] = []
    total = 0
    for name, content_type, content in documents:
        name = (name or "document").replace("\\", "/").rsplit("/", 1)[-1]
        if not bf.is_zip(name, content_type):
            out.append(bf._candidate(name, content))
            total += len(content)
            continue
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValueError(f"'{name}' is not a valid ZIP file") from exc
        with archive:
            for info in archive.infolist():
                base = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
                if info.is_dir() or not base or base.startswith(".") or "__MACOSX" in info.filename:
                    continue
                if info.flag_bits & 0x1:
                    raise ValueError("Password-protected ZIP files are not supported")
                if bf.extension(base) == ".zip":
                    raise ValueError("ZIP files inside a ZIP are not supported")
                with archive.open(info) as handle:
                    data = handle.read(bf.MAX_FILE_BYTES + 1)
                total += len(data)
                out.append(bf._candidate(base, data))
                if len(out) > MAX_DOCUMENTS:
                    break
        if len(out) > MAX_DOCUMENTS:
            break
    if len(out) > MAX_DOCUMENTS:
        raise ValueError(f"At most {MAX_DOCUMENTS} documents can be uploaded with one sheet")
    if total > MAX_DOCUMENT_BYTES:
        raise ValueError("The documents are too large to import at once - split the sheet")
    return out


def content_type_of(file_name: Optional[str]) -> Optional[str]:
    """Stored documents need their real type, or the browser downloads them instead of showing them."""
    return bf.CONTENT_TYPES.get(bf.extension(file_name or ""))


def _status_from(messages: Sequence[Dict[str, str]]) -> str:
    if any(m["severity"] == "error" for m in messages):
        return ROW_ERROR
    if any(m["severity"] == "review" for m in messages):
        return ROW_NEEDS_REVIEW
    return ROW_READY


class BulkImportService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.today = today or datetime.date.today()

    # ==================================================================
    # Templates (pre-filled with the invoices that can be imported now)
    # ==================================================================
    def template(self, kind: str) -> bytes:
        return wbk.build_template(kind, self._template_rows(kind))

    def _template_rows(self, kind: str) -> List[Dict[str, Any]]:
        if kind == KIND_PAYMENTS:
            tracking, rows, page = PaymentTrackingService(self.db), [], 1
            while True:
                data = tracking.list_ready_for_payment(page=page, page_size=100)
                for s in data["items"]:
                    if Decimal(str(s.get("remaining_amount") or 0)) > 0:
                        # Amount left blank: it is read from the receipt (receipt-first).
                        rows.append({"invoice_id": s["invoice_id"], "invoice_number": s["invoice_number"],
                                     "vendor_name": s.get("vendor_name"), "remaining_amount": s.get("remaining_amount")})
                if page * 100 >= data["total"] or len(rows) >= wbk.MAX_ROWS:
                    return rows[: wbk.MAX_ROWS]
                page += 1
        challans = TdsChallanService(self.db, today=self.today)
        if kind == KIND_TDS_CHALLANS:
            return [{"invoice_id": i["invoice_id"], "invoice_number": i["invoice_number"], "vendor_name": i["vendor_name"],
                     "tds_amount": i["tds_amount"], "section_code": i["section"]}
                    for i in challans.challan_candidates()["items"]][: wbk.MAX_ROWS]
        out = []
        for row in challans.dao.invoices_in_tracking_status([DEPOSITED], None, None)[: wbk.MAX_ROWS]:
            view = challans._row_view(row)
            fy, quarter = financial_quarter(view["deduction_date"]) if view["deduction_date"] else (None, None)
            out.append({"invoice_id": view["invoice_id"], "invoice_number": view["invoice_number"],
                        "vendor_name": view["vendor_name"], "tds_amount": view["tds_amount"],
                        "financial_year": fy, "quarter": quarter,
                        "form_type": "27Q" if (view["residency_type"] or "").upper().startswith("NON") else "26Q"})
        return out

    # ==================================================================
    # 1. Create
    # ==================================================================
    def create_job(self, kind: str, workbook: Tuple[str, bytes], documents: Sequence[Tuple[str, Optional[str], bytes]],
                   user_id: str, user_name: Optional[str] = None, source: str = SOURCE_MANUAL,
                   source_reference: Optional[str] = None, auto_record: bool = False) -> int:
        if kind not in KINDS:
            raise ValueError("Unknown import type")
        parsed = wbk.parse_workbook(kind, workbook[1])  # WorkbookRejected is a ValueError
        files = {}
        for candidate in expand_documents(documents):
            files.setdefault(candidate.file_name.lower(), candidate)
        doc_column = wbk.DOCUMENT_COLUMN[kind]

        job = BulkImportJob(kind=kind, source=source, status=JOB_VALIDATING, file_name=workbook[0][:255],
                            source_reference=source_reference, auto_record=auto_record,
                            created_by=user_id, created_by_name=(user_name or None) and user_name[:200])
        self.db.add(job)
        self.db.flush()
        job.file_path = upload_to_s3(filename=workbook[0], content=workbook[1],
                                     content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                     prefix=f"bulk-import/{job.job_id}/")["filepath"]
        stored: Dict[str, str] = {}
        for parsed_row in parsed:
            data = parsed_row.data
            messages = [_msg("error", p) for p in parsed_row.problems]
            name = wbk.file_name_of(data.get(doc_column))  # a full path is fine - only the file name is used
            path = None
            if name:
                candidate = files.get(name.lower())
                if candidate is None:
                    messages.append(_msg("error", f"Document '{name}' was not uploaded with the sheet"))
                elif candidate.problem:
                    messages.append(_msg("error", f"Document '{name}': {candidate.problem}"))
                else:
                    if candidate.file_name.lower() not in stored:
                        stored[candidate.file_name.lower()] = upload_to_s3(
                            filename=candidate.file_name, content=candidate.content, content_type=candidate.content_type,
                            prefix=f"bulk-import/{job.job_id}/docs/")["filepath"]
                    path = stored[candidate.file_name.lower()]
            self.db.add(BulkImportRow(
                job_id=job.job_id, row_number=parsed_row.row_number, data=_jsonable(data),
                group_key=wbk.group_key(kind, data), invoice_id=data.get("invoice_id"),
                document_name=name[:255] or None, document_path=path,
                status=ROW_ERROR if messages else ROW_PENDING, messages=messages or None,
            ))
        self.db.commit()
        return job.job_id

    # ==================================================================
    # 2. Validate
    # ==================================================================
    def _invoice_by_number(self, number: str) -> List[int]:
        return [r[0] for r in self.db.query(Invoice.invoice_id)
                .filter(func.upper(Invoice.invoice_number) == number.strip().upper()).limit(2).all()]

    def evaluate(self, job: BulkImportJob, rows: List[BulkImportRow], extracted: Dict[str, Dict[str, Any]]) -> None:
        """Sets status / messages / extracted on every PENDING row. Caller commits."""
        pending = [r for r in rows if r.status == ROW_PENDING]
        for row in pending:
            row.extracted = _jsonable(extracted.get(row.document_path)) if row.document_path in extracted else None
        if job.kind == KIND_PAYMENTS:
            self._evaluate_payments(pending, extracted)
        else:
            groups: Dict[str, List[BulkImportRow]] = {}
            for row in pending:
                if not row.group_key:
                    row.status, row.messages = ROW_ERROR, (row.messages or []) + [_msg("error", "Missing challan / acknowledgement identity")]
                    continue
                groups.setdefault(row.group_key, []).append(row)
            for group in groups.values():
                (self._evaluate_challan if job.kind == KIND_TDS_CHALLANS else self._evaluate_filing)(group, extracted)

    # ---------------- payments
    _FROM_RECEIPT = (("payment_date", "payment date"), ("payment_mode", "payment mode"), ("reference_number", "UTR"))

    def _fill_from_receipts(self, rows: List[BulkImportRow], extracted, per_row) -> None:
        """Receipt-first: blank Payment Date / Mode / UTR (and Amount, when the receipt pays only
        this row) are taken from the receipt. Values typed in the sheet are kept and checked later."""
        by_document: Dict[str, List[BulkImportRow]] = {}
        for row in rows:
            by_document.setdefault(row.document_path or f"none:{row.row_id}", []).append(row)
        for path, group in by_document.items():
            fields = ((extracted.get(path) or {}).get("fields") or {}) if not path.startswith("none:") else {}
            for row in group:
                data, filled = dict(row.data), []
                for key, label in self._FROM_RECEIPT:
                    value = (fields.get(key) or {}).get("value")
                    if data.get(key) in (None, "") and value:
                        data[key] = value
                        filled.append(label)
                if data.get("amount") in (None, ""):
                    receipt_amount = (fields.get("amount") or {}).get("value")
                    if len(group) > 1:
                        per_row[row.row_id].append(_msg("error", "This receipt pays several invoices - enter each invoice's Amount Paid in the sheet"))
                    elif receipt_amount:
                        data["amount"] = str(receipt_amount)
                        filled.append("amount")
                missing = [label for key, label in (("payment_date", "Payment Date"), ("amount", "Amount Paid"),
                                                    ("payment_mode", "Payment Mode"), ("reference_number", "UTR / Reference"))
                           if data.get(key) in (None, "")]
                if missing and not (len(group) > 1 and missing == ["Amount Paid"]):
                    per_row[row.row_id].append(_msg("error", f"{', '.join(missing)} not in the sheet or on the receipt - fill {'it' if len(missing) == 1 else 'them'} in the sheet"))
                if filled:
                    per_row[row.row_id].append(_msg("info", "Taken from the receipt: " + ", ".join(filled)))
                    data["filled_from_receipt"] = filled
                row.data = data
                row.group_key = wbk.group_key("PAYMENTS", data) or row.group_key

    def _evaluate_payments(self, rows: List[BulkImportRow], extracted) -> None:
        tracking = PaymentTrackingService(self.db)
        summaries: Dict[int, dict] = {}
        planned: Dict[int, Decimal] = {}
        per_row: Dict[int, List[Dict[str, str]]] = {r.row_id: [] for r in rows}
        self._fill_from_receipts(rows, extracted, per_row)
        for row in rows:
            data, msgs = row.data, per_row[row.row_id]
            invoice_id = data.get("invoice_id")
            if not invoice_id:
                ids = self._invoice_by_number(data.get("invoice_number") or "")
                if len(ids) != 1:
                    msgs.append(_msg("error", "Invoice not found - keep the Invoice ID column from the template"
                                      if not ids else "Invoice number matches several invoices - fill Invoice ID"))
                    continue
                invoice_id = ids[0]
            try:
                summary = summaries.get(invoice_id) or tracking.get_invoice_payments(invoice_id)
            except Exception:
                msgs.append(_msg("error", f"Invoice ID {invoice_id} not found"))
                continue
            summaries[invoice_id] = summary
            row.invoice_id = invoice_id
            if data.get("invoice_number") and _ref(data["invoice_number"]) != _ref(summary["invoice_number"]):
                msgs.append(_msg("error", f"Invoice ID {invoice_id} is {summary['invoice_number']}, not {data['invoice_number']}"))
            if not summary.get("can_record_payment"):
                msgs.append(_msg("error", f"{summary['invoice_number']} is not ready for payment ({summary.get('status_name') or summary.get('status_code')})"))
            amount = _m(data.get("amount"))
            if amount is not None:
                planned[invoice_id] = planned.get(invoice_id, Decimal("0")) + amount
                if amount <= 0:
                    msgs.append(_msg("error", "Amount Paid must be greater than zero"))
                elif planned[invoice_id] > Decimal(str(summary["remaining_amount"])):
                    msgs.append(_msg("error", f"Amount(s) for {summary['invoice_number']} exceed the remaining payable {Decimal(str(summary['remaining_amount'])):,.2f}"))
            paid_on = _d(data.get("payment_date"))
            if paid_on and paid_on > self.today:
                msgs.append(_msg("error", "Payment Date is in the future"))
            mode, reference = data.get("payment_mode"), _ref(data.get("reference_number"))
            if mode in _REFERENCE_PATTERNS and reference and not _REFERENCE_PATTERNS[mode].fullmatch(reference):
                msgs.append(_msg("error", f"UTR / Reference {reference} is not a valid {mode} reference"))

        # receipt checks, per UTR group (one transfer can pay several invoices)
        groups: Dict[Tuple[str, str], List[BulkImportRow]] = {}
        for row in rows:
            groups.setdefault((row.group_key or f"ROW:{row.row_id}", row.document_path or ""), []).append(row)
        for (_key, path), group in groups.items():
            receipt = extracted.get(path) if path else None
            first = group[0].data
            notes: List[Dict[str, str]] = []
            if receipt is None:
                notes.append(_msg("review", "The receipt could not be read - check it against the row"))
            else:
                fields = receipt.get("fields") or {}
                status = receipt.get("transaction_status")
                if status == "FAILED":
                    notes.append(_msg("error", "The receipt says the transaction failed or was reversed"))
                elif status == "PENDING":
                    notes.append(_msg("review", "The receipt shows the transfer as pending"))
                r_ref = _ref((fields.get("reference_number") or {}).get("value"))
                if not r_ref:
                    notes.append(_msg("review", "No UTR / reference found on the receipt"))
                elif r_ref != _ref(first.get("reference_number")):
                    notes.append(_msg("review", f"Receipt UTR {r_ref} differs from the sheet's {_ref(first.get('reference_number'))}"))
                r_date = _d((fields.get("payment_date") or {}).get("value"))
                if not r_date:
                    notes.append(_msg("review", "No payment date found on the receipt"))
                elif any(_d(r.data.get("payment_date")) != r_date for r in group):
                    notes.append(_msg("review", f"Receipt date {r_date:%d-%m-%Y} differs from the sheet"))
                r_amount = _m((fields.get("amount") or {}).get("value"))
                sheet_total = sum((_m(r.data.get("amount")) or Decimal("0") for r in group), Decimal("0"))
                if r_amount is None:
                    notes.append(_msg("review", "No amount found on the receipt"))
                elif r_amount != sheet_total:
                    what = "the rows with this UTR add up to" if len(group) > 1 else "the sheet says"
                    notes.append(_msg("review", f"Receipt amount {r_amount:,.2f} but {what} {sheet_total:,.2f}"))
                vendors = {summaries[r.invoice_id]["vendor_name"] for r in group if r.invoice_id in summaries}
                if len(vendors) > 1:
                    notes.append(_msg("review", "The same UTR is used for invoices of different vendors"))
                beneficiary = receipt.get("beneficiary_name")
                if beneficiary and vendors and not any(names_look_alike(beneficiary, v) for v in vendors):
                    notes.append(_msg("review", f"Beneficiary '{beneficiary}' does not look like the vendor"))
            for row in group:
                messages = (row.messages or []) + per_row[row.row_id] + notes
                row.status, row.messages = _status_from(messages), messages or None

    # ---------------- challans / filings
    def _apply_group(self, group, errors: List[str], reviews: List[str], warnings: List[str]) -> None:
        notes = [_msg("error", e) for e in errors] + [_msg("review", r) for r in reviews] + [_msg("info", w) for w in warnings]
        for row in group:
            messages = (row.messages or []) + notes
            row.status, row.messages = _status_from(messages), messages or None

    def _challan_inputs(self, group) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        first = group[0].data
        header = {k: first.get(k) for k in ("challan_serial_no", "bsr_code", "deposit_date", "section_code", "tax_amount",
                                              "surcharge", "cess", "interest", "fee")}
        header["remarks"] = f"Bulk import row(s) {', '.join(str(r.row_number) for r in group)}"
        allocations = []
        for row in group:
            ids = [row.data["invoice_id"]] if row.data.get("invoice_id") else self._invoice_by_number(row.data.get("invoice_number") or "")
            if len(ids) == 1:
                row.invoice_id = ids[0]
                allocation = {"invoice_id": ids[0]}
                if row.data.get("allocated_tds_amount") not in (None, ""):
                    allocation["allocated_tds_amount"] = row.data["allocated_tds_amount"]
                allocations.append(allocation)
        return header, allocations

    def _evaluate_challan(self, group, extracted) -> None:
        header, allocations = self._challan_inputs(group)
        errors = [f"Row {r.row_number}: invoice not found" for r in group if not r.invoice_id]
        differing = [k for k in ("bsr_code", "deposit_date", "tax_amount") if len({str(r.data.get(k)) for r in group}) > 1]
        errors += [f"Rows of this challan disagree on {k.replace('_', ' ')}" for k in differing]
        check = TdsChallanService(self.db, today=self.today).validate_challan(header, allocations, has_document=bool(group[0].document_path))
        errors += [e["message"] for e in check["errors"]]
        reviews = []
        doc = extracted.get(group[0].document_path) if group[0].document_path else None
        if doc is None:
            reviews.append("The challan could not be read - check it against the sheet")
        else:
            fields = doc.get("fields") or {}
            compare = {"challan_serial_no": check["normalized"]["challan_serial_no"], "bsr_code": check["normalized"]["bsr_code"],
                       "deposit_date": str(check["normalized"]["deposit_date"] or ""), "tax_amount": str(check["normalized"]["tax_amount"])}
            for key, expected in compare.items():
                found = (fields.get(key) or {}).get("value")
                if found is None:
                    reviews.append(f"{key.replace('_', ' ').capitalize()} not found on the challan")
                elif str(found) != str(expected):
                    reviews.append(f"Challan shows {key.replace('_', ' ')} {found}, the sheet {expected}")
        self._apply_group(group, errors, reviews, [w["message"] for w in check["warnings"]])

    def _filing_inputs(self, group) -> Tuple[Dict[str, Any], List[int]]:
        first = group[0].data
        header = {k: first.get(k) for k in ("form_type", "financial_year", "quarter", "acknowledgement_no", "filing_date", "is_revision")}
        header["remarks"] = f"Bulk import row(s) {', '.join(str(r.row_number) for r in group)}"
        ids = []
        for row in group:
            found = [row.data["invoice_id"]] if row.data.get("invoice_id") else self._invoice_by_number(row.data.get("invoice_number") or "")
            if len(found) == 1:
                row.invoice_id = found[0]
                ids.append(found[0])
        return header, ids

    def _evaluate_filing(self, group, extracted) -> None:
        header, ids = self._filing_inputs(group)
        errors = [f"Row {r.row_number}: invoice not found" for r in group if not r.invoice_id]
        differing = [k for k in ("form_type", "financial_year", "quarter", "filing_date") if len({str(r.data.get(k)) for r in group}) > 1]
        errors += [f"Rows of this filing disagree on {k.replace('_', ' ')}" for k in differing]
        check = TdsChallanService(self.db, today=self.today).validate_filing(header, ids, has_document=bool(group[0].document_path))
        errors += [e["message"] for e in check["errors"]]
        reviews = []
        doc = extracted.get(group[0].document_path) if group[0].document_path else None
        if doc is None:
            reviews.append("The acknowledgement could not be read - check it against the sheet")
        else:
            fields = doc.get("fields") or {}
            for key, expected in (("acknowledgement_no", check["normalized"]["acknowledgement_no"]),
                                  ("filing_date", str(check["normalized"]["filing_date"] or ""))):
                found = (fields.get(key) or {}).get("value")
                if found is None:
                    reviews.append(f"{key.replace('_', ' ').capitalize()} not found on the acknowledgement")
                elif _ref(found) != _ref(expected):
                    reviews.append(f"Acknowledgement shows {key.replace('_', ' ')} {found}, the sheet {expected}")
        self._apply_group(group, errors, reviews, [w["message"] for w in check["warnings"]])

    # ==================================================================
    # 3. Record
    # ==================================================================
    def record(self, job_id: int, user_id: str, row_ids: Optional[Sequence[int]] = None, accept_review: bool = False) -> Dict[str, int]:
        """Records READY rows (or the given rows; NEEDS_REVIEW ones only with accept_review). A
        challan / filing is recorded only when every row of its group is selected."""
        job = self._job(job_id)
        rows = list(job.rows)
        allowed = {ROW_READY} | ({ROW_NEEDS_REVIEW} if accept_review else set())
        chosen = [r for r in rows if r.status in allowed and (row_ids is None or r.row_id in row_ids)]
        job.status = JOB_RECORDING
        self.db.commit()
        done = failed = 0
        if job.kind == KIND_PAYMENTS:
            for row in chosen:
                ok = self._record_payment(row, user_id, accepted=row.status == ROW_NEEDS_REVIEW)
                done, failed = done + ok, failed + (not ok)
        else:
            groups: Dict[str, List[BulkImportRow]] = {}
            for row in rows:
                if row.group_key:
                    groups.setdefault(row.group_key, []).append(row)
            for key, group in groups.items():
                if not all(r in chosen for r in group):
                    continue
                ok = self._record_group(job.kind, group, user_id)
                done, failed = done + (len(group) if ok else 0), failed + (0 if ok else len(group))
        self._finish(job)
        return {"recorded": done, "failed": failed}

    def _record_payment(self, row: BulkImportRow, user_id: str, accepted: bool) -> bool:
        data = row.data
        try:
            detail = PaymentTrackingService(self.db).record_payment(row.invoice_id, RecordPaymentRequest(
                payment_date=data["payment_date"], amount=data["amount"], payment_mode=data["payment_mode"],
                reference_number=data["reference_number"],
                remarks=((data.get("remarks") or "") + f" [bulk import #{row.job_id} row {row.row_number}"
                         + (", reviewed and accepted" if accepted else "") + "]").strip()[:1000],
                entry_mode="BULK_IMPORT"), user_id)
            payment_id = detail["recorded_payment_id"]
            try:
                PaymentTrackingService(self.db).upload_document(
                    payment_id, row.document_name, get_object_bytes(row.document_path),
                    content_type_of(row.document_name), "RECEIPT", user_id)
            except Exception:
                logger.exception("Bulk import row %s: receipt could not be attached", row.row_id)
                row.messages = (row.messages or []) + [_msg("info", "Recorded, but the receipt could not be attached - upload it on the payment")]
            row.status, row.result_reference = ROW_RECORDED, f"PAYMENT-{payment_id}"
            row.recorded_by, row.recorded_at = user_id, _now()
            self.db.commit()
            return True
        except Exception as exc:
            self.db.rollback()
            row = self.db.merge(row)
            row.status = ROW_ERROR
            row.messages = (row.messages or []) + [_msg("error", f"Not recorded: {exc}")]
            self.db.commit()
            return False

    def _record_group(self, kind: str, group: List[BulkImportRow], user_id: str) -> bool:
        first = group[0]
        try:
            document = ((first.document_name, get_object_bytes(first.document_path), content_type_of(first.document_name))
                        if first.document_path else None)
            service = TdsChallanService(self.db, today=self.today)
            if kind == KIND_TDS_CHALLANS:
                header, allocations = self._challan_inputs(group)
                result = service.create_challan(header, allocations, user_id, document, source="BULK_IMPORT")
                reference = f"CHALLAN-{result['challan_id']}"
            else:
                header, ids = self._filing_inputs(group)
                result = service.create_filing(header, ids, user_id, document, source="BULK_IMPORT")
                reference = f"FILING-{result['filing_id']}"
            for row in group:
                row.status, row.result_reference, row.recorded_by, row.recorded_at = ROW_RECORDED, reference, user_id, _now()
            self.db.commit()
            return True
        except Exception as exc:
            self.db.rollback()
            for row in group:
                row = self.db.merge(row)
                row.status = ROW_ERROR
                row.messages = (row.messages or []) + [_msg("error", f"Not recorded: {exc}")]
            self.db.commit()
            return False

    def skip(self, row_id: int) -> BulkImportJob:
        row = self.db.query(BulkImportRow).filter(BulkImportRow.row_id == row_id).first()
        if row is None:
            raise LookupError("Row not found")
        if row.status in (ROW_RECORDED, ROW_PENDING):
            raise ValueError("Recorded or still-checking rows cannot be skipped")
        targets = [r for r in row.job.rows if row.group_key and r.group_key == row.group_key and r.status != ROW_RECORDED] \
            if row.job.kind != KIND_PAYMENTS else [row]
        for r in targets:
            r.status = ROW_SKIPPED
        self._finish(row.job)
        return row.job

    def _finish(self, job: BulkImportJob) -> None:
        statuses = {r.status for r in job.rows}
        if statuses <= {ROW_RECORDED, ROW_SKIPPED}:
            job.status, job.completed_at = JOB_COMPLETED, job.completed_at or _now()
        elif ROW_PENDING in statuses:
            job.status = JOB_VALIDATING
        elif ROW_READY in statuses:
            job.status = JOB_VALIDATED
        else:
            job.status = JOB_NEEDS_REVIEW
        job.updated_at = _now()
        self.db.commit()

    # ==================================================================
    # Read side
    # ==================================================================
    def _job(self, job_id: int) -> BulkImportJob:
        job = self.db.query(BulkImportJob).filter(BulkImportJob.job_id == job_id).first()
        if job is None:
            raise LookupError("Import not found")
        return job

    @staticmethod
    def _counts(rows) -> Dict[str, int]:
        out = {s: 0 for s in (ROW_PENDING, ROW_READY, ROW_NEEDS_REVIEW, ROW_ERROR, ROW_RECORDED, ROW_SKIPPED)}
        for r in rows:
            out[r.status] = out.get(r.status, 0) + 1
        return {k.lower(): v for k, v in out.items()}

    def _job_view(self, job: BulkImportJob, rows=None) -> Dict[str, Any]:
        rows = job.rows if rows is None else rows
        return {"job_id": job.job_id, "kind": job.kind, "source": job.source, "status": job.status, "file_name": job.file_name,
                "auto_record": job.auto_record, "created_by_name": job.created_by_name, "created_at": job.created_at,
                "completed_at": job.completed_at, "error_message": job.error_message, "total_rows": len(rows),
                "counts": self._counts(rows)}

    def list_jobs(self, kind: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
        query = self.db.query(BulkImportJob)
        if kind:
            query = query.filter(BulkImportJob.kind == kind)
        total = query.count()
        jobs = query.order_by(BulkImportJob.created_at.desc(), BulkImportJob.job_id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": [self._job_view(j) for j in jobs], "total": total, "page": page, "page_size": page_size}

    def job_detail(self, job_id: int) -> Dict[str, Any]:
        job = self._job(job_id)
        return {**self._job_view(job), "rows": [{
            "row_id": r.row_id, "row_number": r.row_number, "status": r.status, "data": r.data, "group_key": r.group_key,
            "invoice_id": r.invoice_id, "document_name": r.document_name, "has_document": bool(r.document_path),
            "extracted_fields": {k: (v or {}).get("value") for k, v in ((r.extracted or {}).get("fields") or {}).items()},
            "messages": r.messages or [], "result_reference": r.result_reference, "recorded_at": r.recorded_at,
        } for r in job.rows]}

    def results_workbook(self, job_id: int) -> Tuple[str, bytes]:
        job = self._job(job_id)
        content = wbk.build_results(job.kind, [{"data": r.data, "status": r.status, "messages": r.messages,
                                                "result_reference": r.result_reference} for r in job.rows])
        base = job.file_name.rsplit(".", 1)[0]
        return f"{base} - results.xlsx", content


# ======================================================================
# Background worker
# ======================================================================
async def _extract_all(kind: str, paths: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    out: Dict[str, Dict[str, Any]] = {}

    async def one(path):
        async with semaphore:
            try:
                out[path] = await _EXTRACTORS[kind](path)
            except Exception:
                logger.warning("Bulk import: could not read %s", path, exc_info=True)

    await asyncio.gather(*(one(p) for p in paths))
    return out


def _load(db, job_id):
    job = db.query(BulkImportJob).filter(BulkImportJob.job_id == job_id).first()
    return job, (sorted({r.document_path for r in job.rows if r.status == ROW_PENDING and r.document_path}) if job else [])


def _evaluate_and_maybe_record(db, job_id: int, extracted, actor: Optional[str]) -> None:
    service = BulkImportService(db)
    job = service._job(job_id)
    service.evaluate(job, list(job.rows), extracted)
    db.commit()
    service._finish(job)
    if job.auto_record and any(r.status == ROW_READY for r in job.rows):
        service.record(job_id, actor or job.created_by or "BULK_IMPORT")


async def validate_job(job_id: int, actor: Optional[str] = None) -> None:
    """Background task: read the documents, check every row, and (auto_record jobs) record READY rows."""
    db = SessionLocal()
    try:
        job, paths = await run_in_threadpool(_load, db, job_id)
        if job is None:
            return
        kind = job.kind
        extracted = await _extract_all(kind, paths)
        await run_in_threadpool(_evaluate_and_maybe_record, db, job_id, extracted, actor)
    except Exception as exc:
        logger.exception("Bulk import %s failed", job_id)
        try:
            db.rollback()
            job = db.query(BulkImportJob).filter(BulkImportJob.job_id == job_id).first()
            if job is not None:
                job.status, job.error_message = JOB_FAILED, str(exc)[:1000]
                db.commit()
        except Exception:
            logger.exception("Bulk import %s: could not record the failure", job_id)
    finally:
        db.close()
