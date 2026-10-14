# Backend/Business_Layer/services/gstr2b_service.py
"""GSTR-2B reconciliation (P3) - claim input credit only on what each supplier actually filed.

  import_file      a GSTR-2B for one return period: the JSON downloaded from the GST portal (b2b invoices,
                   cdnr credit / debit notes) or a CSV with the same columns. Re-importing a period
                   replaces the previous import.
  match            each document against the books by supplier GSTIN + normalised document number, then
                   the tax: MATCHED (within GSTR2B_TOLERANCE, default Rs 1), MISMATCH (difference shown),
                   NOT_IN_BOOKS (filed by the supplier, not booked - chase the invoice)
  rematch          entries not yet matched are re-checked when an invoice is booked / its GST changes
                   (suppliers often file before the invoice reaches AP) and on every import
  status_by_invoice  invoice -> MATCHED / MISMATCH, used by the ITC register: once a period's GSTR-2B is
                   imported, only MATCHED invoices are claimable (s.16(2)(aa)); invoices with no entry are
                   "missing in 2B" - the supplier has not filed them yet
  reconciliation / attention   the GST page and the Action Center
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select, update

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.gstr2b import MATCHED, MISMATCH, NOT_IN_BOOKS, Gstr2bEntry, Gstr2bImport
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.invoice_gst import InvoiceGst

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
TOLERANCE_KEY = "GSTR2B_TOLERANCE"
CSV_COLUMNS = ["Supplier GSTIN", "Supplier Name", "Document Type", "Document Number", "Document Date",
               "Taxable Value", "IGST", "CGST", "SGST", "Cess", "ITC Available", "Reason"]


def _money(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0).replace(",", "")).quantize(CENTS, ROUND_HALF_UP)
    except InvalidOperation:
        return ZERO


def norm_doc(number: Optional[str]) -> str:
    """Document numbers compare without punctuation, case or leading zeros ('KTPL/26-27/0550' = 'ktpl2627550')."""
    tokens = re.findall(r"[A-Z]+|[0-9]+", (number or "").upper())
    return "".join(t.lstrip("0") or "0" if t.isdigit() else t for t in tokens)


def _date(value) -> Optional[datetime.date]:
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _period(value: str) -> Optional[datetime.date]:
    """GSTR-2B return period 'MMYYYY' -> first of the month."""
    value = re.sub(r"\D", "", str(value or ""))
    if len(value) == 6:
        return datetime.date(int(value[2:]), int(value[:2]), 1)
    return None


def parse_json(content: bytes) -> Tuple[Optional[datetime.date], Optional[str], Optional[datetime.date], List[dict]]:
    """(return period, buyer GSTIN, generated on, documents) from the GST portal's GSTR-2B JSON."""
    try:
        doc = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("This is not a GSTR-2B JSON file") from exc
    data = doc.get("data", doc) if isinstance(doc, dict) else {}
    docdata = data.get("docdata") or {}
    out = []
    for supplier in docdata.get("b2b") or []:
        for inv in supplier.get("inv") or []:
            out.append(_doc(supplier, "INV", inv.get("inum"), inv))
    for supplier in docdata.get("cdnr") or []:
        for note in supplier.get("nt") or []:
            out.append(_doc(supplier, "CN" if str(note.get("typ", "C")).upper() == "C" else "DN", note.get("ntnum"), note))
    if not out and not docdata:
        raise ValueError("No b2b / cdnr documents found - download the GSTR-2B JSON from the GST portal")
    return _period(data.get("rtnprd")), data.get("gstin"), _date(data.get("gendt")), out


def _doc(supplier: dict, doc_type: str, number, item: dict) -> dict:
    lines = item.get("items") or [item]
    total = lambda key: sum((_money(line.get(key)) for line in lines), ZERO)
    return {"supplier_gstin": str(supplier.get("ctin") or "").upper(), "supplier_name": supplier.get("trdnm"),
            "supplier_filed_on": _date(supplier.get("supfildt")), "doc_type": doc_type, "doc_number": str(number or ""),
            "doc_date": _date(item.get("dt")), "taxable_value": total("txval"), "igst": total("igst"),
            "cgst": total("cgst"), "sgst": total("sgst"), "cess": total("cess"),
            "itc_available": str(item.get("itcavl", "Y")).upper() != "N", "itc_unavailable_reason": item.get("rsn") or None}


def parse_csv(content: bytes) -> List[dict]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    out = []
    for row in reader:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not r.get("supplier gstin") or not r.get("document number"):
            continue
        out.append({"supplier_gstin": r["supplier gstin"].upper(), "supplier_name": r.get("supplier name") or None,
                    "supplier_filed_on": None, "doc_type": (r.get("document type") or "INV").upper()[:3],
                    "doc_number": r["document number"], "doc_date": _date(r.get("document date")),
                    "taxable_value": _money(r.get("taxable value")), "igst": _money(r.get("igst")), "cgst": _money(r.get("cgst")),
                    "sgst": _money(r.get("sgst")), "cess": _money(r.get("cess")),
                    "itc_available": (r.get("itc available") or "Y").upper()[:1] != "N",
                    "itc_unavailable_reason": r.get("reason") or None})
    if not out:
        raise ValueError(f"No rows found - the CSV needs these columns: {', '.join(CSV_COLUMNS)}")
    return out


_table_ready = False


def _table_exists(db) -> bool:
    """ITC claims work exactly as before until the migration has run."""
    global _table_ready
    if not _table_ready:
        from sqlalchemy import text
        _table_ready = bool(db.execute(text("select to_regclass('ap.gstr2b_import')")).scalar())
    return _table_ready


def gstr2b_state(db) -> Tuple[Dict[int, str], Optional[datetime.date], Optional[datetime.date]]:
    """(invoice -> MATCHED / MISMATCH, first and latest imported return period) - ({}, None, None) when
    nothing is imported. Invoices dated before the first import are "not checked" (history before 2B use)."""
    try:
        if not _table_exists(db):
            return {}, None, None
        svc = Gstr2bService(db)
        periods = svc.imported_periods()
        return (svc.status_by_invoice(), periods[0], periods[-1]) if periods else ({}, None, None)
    except (AttributeError, TypeError):  # a test double without a real session
        return {}, None, None


class Gstr2bService:
    def __init__(self, db):
        self.db = db

    def _tolerance(self) -> Decimal:
        from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
        row = MasterDAO(self.db).get_system_config_by_key(TOLERANCE_KEY)
        return _money(row.config_value) if row is not None and row.config_value else Decimal("1.00")

    # ------------------------------------------------------------------ import + match
    def import_file(self, file_name: str, content: bytes, user_id, period: Optional[datetime.date] = None) -> Dict[str, Any]:
        is_json = file_name.lower().endswith(".json") or content.lstrip()[:1] in (b"{", b"[")
        if is_json:
            file_period, buyer, generated, docs = parse_json(content)
        else:
            file_period, buyer, generated, docs = None, None, None, parse_csv(content)
        period = (period.replace(day=1) if period else None) or file_period
        if period is None:
            raise ValueError("Choose the return period (the CSV does not carry it)")
        if period > datetime.date.today().replace(day=1):
            raise ValueError("A GSTR-2B return period cannot be in the future")
        try:
            from Backend.API_Layer.utils.s3_utils import upload_to_s3
            stored = upload_to_s3(file_name, content, "application/json" if is_json else "text/csv", prefix="gstr2b/")
            path = stored["filepath"]
        except Exception:
            logger.exception("GSTR-2B file not stored to S3")
            path = None
        self.db.execute(update(Gstr2bImport).where(Gstr2bImport.return_period == period).values(is_current=False))
        imp = Gstr2bImport(return_period=period, file_name=file_name[:255], file_path=path, source_format="JSON" if is_json else "CSV",
                           buyer_gstin=buyer, generated_on=generated, uploaded_by=str(user_id), is_current=True)
        self.db.add(imp)
        self.db.flush()
        counts = {MATCHED: 0, MISMATCH: 0, NOT_IN_BOOKS: 0}
        books = self._books()
        tolerance = self._tolerance()
        for d in docs:
            status, invoice_id, diff, note = self._match(d, books, tolerance)
            counts[status] += 1
            self.db.add(Gstr2bEntry(import_id=imp.import_id, match_status=status, matched_invoice_id=invoice_id,
                                    tax_difference=diff, note=note, **{k: d[k] for k in (
                                        "supplier_gstin", "supplier_name", "supplier_filed_on", "doc_type", "doc_date",
                                        "taxable_value", "igst", "cgst", "sgst", "cess", "itc_available",
                                        "itc_unavailable_reason")}, doc_number=d["doc_number"][:60]))
        self.db.flush()
        self._rematch(books, tolerance, exclude_import=imp.import_id)
        self.db.add(AuditLog(table_name="gstr2b_import", record_id=imp.import_id, action="GSTR2B_IMPORTED",
                             changed_by=str(user_id), new_values={"period": period.isoformat(), "documents": len(docs),
                                                                   **{k.lower(): v for k, v in counts.items()}}))
        self.db.commit()
        return {"import_id": imp.import_id, "period": period, "documents": len(docs), "counts": counts}

    def rematch(self, invoice_id: Optional[int] = None, user_id="SYSTEM") -> int:
        """Re-checks unmatched entries (only the invoice's supplier when given). Commits; returns entries changed."""
        gstin = None
        if invoice_id is not None:
            gstin = self.db.execute(select(InvoiceGst.supplier_gstin).where(InvoiceGst.invoice_id == invoice_id)).scalar()
            if not gstin:
                return 0
        changed = self._rematch(self._books(), self._tolerance(), gstin=gstin, invoice_id=invoice_id)
        if changed:
            self.db.add(AuditLog(table_name="gstr2b_entry", record_id=invoice_id or 0, action="GSTR2B_REMATCHED",
                                 changed_by=str(user_id), new_values={"entries": changed}))
        self.db.commit()
        return changed

    def _rematch(self, books, tolerance: Decimal, gstin: Optional[str] = None, invoice_id: Optional[int] = None,
                 exclude_import: Optional[int] = None) -> int:
        stmt = (select(Gstr2bEntry).join(Gstr2bImport, Gstr2bImport.import_id == Gstr2bEntry.import_id)
                .where(Gstr2bImport.is_current.is_(True), Gstr2bEntry.doc_type == "INV"))
        if exclude_import is not None:
            stmt = stmt.where(Gstr2bEntry.import_id != exclude_import)
        if gstin:
            stmt = stmt.where(Gstr2bEntry.supplier_gstin == gstin.upper())
        changed = 0
        for e in self.db.execute(stmt).scalars().all():
            if e.match_status == MATCHED and e.matched_invoice_id != invoice_id:
                continue
            doc = {k: getattr(e, k) for k in ("supplier_gstin", "doc_type", "doc_number", "taxable_value", "igst", "cgst", "sgst", "cess")}
            status, matched, diff, note = self._match(doc, books, tolerance)
            if (status, matched, diff) != (e.match_status, e.matched_invoice_id, e.tax_difference):
                e.match_status, e.matched_invoice_id, e.tax_difference, e.note = status, matched, diff, note
                changed += 1
        return changed

    def _books(self) -> Dict[Tuple[str, str], List[tuple]]:
        """(supplier GSTIN, normalised number) -> [(invoice_id, taxable, tax, status, invoice number)]"""
        from Backend.Data_Access_Layer.models.master import StatusMaster
        rows = self.db.execute(select(Invoice.invoice_id, Invoice.invoice_number, InvoiceGst.supplier_gstin, InvoiceGst.taxable_value,
                                      InvoiceGst.cgst, InvoiceGst.sgst, InvoiceGst.igst, InvoiceGst.cess, StatusMaster.status_code)
                               .join(InvoiceGst, InvoiceGst.invoice_id == Invoice.invoice_id)
                               .join(StatusMaster, StatusMaster.status_id == Invoice.status_id, isouter=True)).all()
        out: Dict[Tuple[str, str], List[tuple]] = {}
        for r in rows:
            if r.supplier_gstin:
                tax = _money(r.cgst) + _money(r.sgst) + _money(r.igst) + _money(r.cess)
                out.setdefault((r.supplier_gstin.upper(), norm_doc(r.invoice_number)), []).append(
                    (r.invoice_id, _money(r.taxable_value), tax, r.status_code, r.invoice_number))
        return out

    def _match(self, d: dict, books, tolerance: Decimal):
        if d["doc_type"] != "INV":
            return self._match_note(d)
        found = books.get((d["supplier_gstin"], norm_doc(d["doc_number"])))
        if not found:
            return NOT_IN_BOOKS, None, None, "Filed by the supplier but not in the books - get the invoice and book it"
        invoice_id, taxable, tax, status, number = found[0]
        filed_tax = d["igst"] + d["cgst"] + d["sgst"] + d["cess"]
        diff = filed_tax - tax
        if status == "REJECTED":
            return MISMATCH, invoice_id, diff, "Rejected in the books - ask the supplier to cancel it or issue a credit note"
        if abs(diff) <= tolerance and abs(d["taxable_value"] - taxable) <= max(tolerance, Decimal("1")):
            return MATCHED, invoice_id, diff, None
        return MISMATCH, invoice_id, diff, (f"Supplier filed tax {filed_tax:,} vs {tax:,} in the books "
                                            f"(taxable {d['taxable_value']:,} vs {taxable:,})")

    def _match_note(self, d: dict):
        try:
            from Backend.Data_Access_Layer.models.vendor_note import CREDIT_NOTE, VendorNote
            from Backend.Data_Access_Layer.models.vendor import Vendor
        except Exception:
            return NOT_IN_BOOKS, None, None, None
        notes = self.db.execute(select(VendorNote).where(VendorNote.note_type == CREDIT_NOTE)).scalars().all()
        for note in notes:
            if norm_doc(note.note_number) == norm_doc(d["doc_number"]):
                return MATCHED, note.reference_invoice_id, None, f"Credit note {note.note_number}"
        return NOT_IN_BOOKS, None, None, "Credit / debit note filed by the supplier but not recorded - record it"

    # ------------------------------------------------------------------ used by the ITC register
    def status_by_invoice(self) -> Dict[int, str]:
        rows = self.db.execute(select(Gstr2bEntry.matched_invoice_id, Gstr2bEntry.match_status).join(
            Gstr2bImport, Gstr2bImport.import_id == Gstr2bEntry.import_id).where(
            Gstr2bImport.is_current.is_(True), Gstr2bEntry.matched_invoice_id.is_not(None), Gstr2bEntry.doc_type == "INV")).all()
        out: Dict[int, str] = {}
        for invoice_id, status in rows:
            if out.get(invoice_id) != MATCHED:  # a later re-filing that matches wins
                out[invoice_id] = status
        return out

    def imported_periods(self) -> List[datetime.date]:
        return sorted(p for (p,) in self.db.execute(select(Gstr2bImport.return_period).where(Gstr2bImport.is_current.is_(True))).all())

    # ------------------------------------------------------------------ views
    def reconciliation(self, period: Optional[datetime.date] = None) -> Dict[str, Any]:
        imports = self.db.execute(select(Gstr2bImport).where(Gstr2bImport.is_current.is_(True))
                                  .order_by(Gstr2bImport.return_period.desc())).scalars().all()
        if not imports:
            return {"imports": [], "period": None, "entries": [], "missing_in_2b": [], "counts": {}}
        chosen = next((i for i in imports if period and i.return_period == period.replace(day=1)), imports[0])
        entries = self.db.execute(select(Gstr2bEntry).where(Gstr2bEntry.import_id == chosen.import_id)
                                  .order_by(Gstr2bEntry.match_status, Gstr2bEntry.supplier_gstin)).scalars().all()
        numbers = dict(self.db.execute(select(Invoice.invoice_id, Invoice.invoice_number)).all())
        itc = dict(self.db.execute(select(InvoiceGst.invoice_id, InvoiceGst.itc_status)).all())
        counts = {MATCHED: 0, MISMATCH: 0, NOT_IN_BOOKS: 0}
        for e in entries:
            counts[e.match_status] += 1
        missing = self.missing_in_2b(chosen.return_period)
        counts["MISSING_IN_2B"] = len(missing)
        return {
            "imports": [{"import_id": i.import_id, "period": i.return_period, "file_name": i.file_name, "uploaded_at": i.uploaded_at}
                        for i in imports],
            "period": chosen.return_period, "import_id": chosen.import_id, "file_name": chosen.file_name,
            "generated_on": chosen.generated_on, "counts": counts,
            "entries": [{"entry_id": e.entry_id, "supplier_gstin": e.supplier_gstin, "supplier_name": e.supplier_name,
                         "doc_type": e.doc_type, "doc_number": e.doc_number, "doc_date": e.doc_date,
                         "taxable_value": e.taxable_value, "tax": e.igst + e.cgst + e.sgst + e.cess, "match_status": e.match_status,
                         "matched_invoice_id": e.matched_invoice_id, "matched_invoice_number": numbers.get(e.matched_invoice_id),
                         "itc_status": itc.get(e.matched_invoice_id),
                         "tax_difference": e.tax_difference, "note": e.note, "itc_available": e.itc_available,
                         "itc_unavailable_reason": e.itc_unavailable_reason} for e in entries],
            "missing_in_2b": missing,
        }

    def missing_in_2b(self, period: datetime.date) -> List[dict]:
        """Invoices dated from the first imported period up to this one, with GST credit to take but no
        matching GSTR-2B entry in any import (a supplier filing late shows up in a later month's 2B)."""
        from Backend.Data_Access_Layer.models.vendor import Vendor
        end = (period.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        periods = self.imported_periods()
        start = periods[0] if periods else period
        matched = set(self.status_by_invoice())
        rows = self.db.execute(select(Invoice.invoice_id, Invoice.invoice_number, Invoice.invoice_date, Vendor.vendor_name,
                                      InvoiceGst.supplier_gstin, InvoiceGst.cgst, InvoiceGst.sgst, InvoiceGst.igst, InvoiceGst.cess,
                                      InvoiceGst.itc_status)
                               .join(InvoiceGst, InvoiceGst.invoice_id == Invoice.invoice_id)
                               .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
                               .where(Invoice.invoice_date >= start, Invoice.invoice_date <= end,
                                      InvoiceGst.itc_eligibility == "ELIGIBLE",
                                      InvoiceGst.itc_status.in_(("PENDING", "CLAIMED")))).all()
        return [{"invoice_id": r.invoice_id, "invoice_number": r.invoice_number, "invoice_date": r.invoice_date,
                 "vendor_name": r.vendor_name, "supplier_gstin": r.supplier_gstin, "itc_status": r.itc_status,
                 "itc": _money(r.cgst) + _money(r.sgst) + _money(r.igst) + _money(r.cess)}
                for r in rows if r.invoice_id not in matched]

    def attention(self) -> Dict[str, int]:
        data = self.reconciliation()
        c = data.get("counts") or {}
        return {"period": data.get("period"), "mismatch": c.get(MISMATCH, 0), "not_in_books": c.get(NOT_IN_BOOKS, 0),
                "missing_in_2b": c.get("MISSING_IN_2B", 0)}
