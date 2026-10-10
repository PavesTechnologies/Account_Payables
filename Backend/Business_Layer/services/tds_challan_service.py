# Backend/Business_Layer/services/tds_challan_service.py
"""Shared TDS challan and quarterly return filing (APM_AUTOMATION_PLAN.md 3.4 / D4, Phase 5).

Challan: one ITNS 281 deposit usually pays the TDS of many invoices of a month and section.
  1. candidates - invoices whose TDS is VERIFIED and DEDUCTED, not yet on a challan, optionally of
     one deduction month / section, each with its TDS amount and statutory due date;
  2. validate (preview, no writes) - identity (BSR + date + serial) unique, amounts add up, the
     allocated invoice TDS equals the challan tax within TDS_CHALLAN_TOLERANCE, every invoice is
     eligible, the deposit is not before any deduction, evidence attached (or a reason given);
     late deposits are flagged (interest u/s 201(1A));
  3. confirm - challan + allocations + the EXISTING TdsTrackingService.record_deposit for every
     invoice, all in ONE transaction; the challan PDF is linked to every invoice's TDS documents.

Filing: the same pattern for the quarterly statement acknowledgement (26Q / 27Q / 24Q / 27EQ) -
all DEPOSITED invoices of the quarter, then the existing record_filing for each.

Per-invoice TDS tracking stays the system of record, so the TDS Tracking screens, history and
reports keep working unchanged. Single-invoice deposit / filing stays available.
"""
import datetime
import re
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Backend.API_Layer.utils.tds_document_extraction import build_cin
from Backend.Business_Layer.services.tds_tracking_service import TdsTrackingService
from Backend.Business_Layer.utils.statutory_calendar import (
    configured_deposit_days,
    financial_quarter,
    tds_deposit_due_date,
    tds_statement_due_date,
)
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.dao.tds_challan_dao import TdsChallanDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.tds import InvoiceTdsDocument
from Backend.Data_Access_Layer.models.tds_challan import (
    FILING_FORMS,
    TdsChallan,
    TdsChallanAllocation,
    TdsReturnFiling,
    TdsReturnFilingInvoice,
)

ZERO = Decimal("0.00")
DEDUCTED, DEPOSITED, FILED = "TDS_DEDUCTED", "TDS_DEPOSITED", "TDS_FILED"
_FY_RE = re.compile(r"^(20[0-9]{2})-([0-9]{2})$")
_ACK_RE = re.compile(r"^[A-Za-z0-9]{8,30}$")
_TAN_RE = re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$")
MIN_REASON = 10


def _money(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0)).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"'{value}' is not a valid amount")


def section_of(row) -> Optional[str]:
    _invoice, _vendor, _status, tds, _nature, rule, _tracking = row
    snapshot = (tds.rule_snapshot or {}) if tds is not None else {}
    return snapshot.get("old_section") or (rule.old_section if rule is not None else None)


def normalize_section(code: Optional[str]) -> Optional[str]:
    """'194C', '94C', ' 194 c ' -> '94C' (the challan's nature-of-payment code)."""
    if not code:
        return None
    text = re.sub(r"\s", "", code).upper()
    return text[1:] if text.startswith("19") and len(text) >= 4 else text


def quarter_bounds(financial_year: str, quarter: int) -> Tuple[datetime.date, datetime.date]:
    match = _FY_RE.match(financial_year or "")
    if not match:
        raise ValueError("Financial year must look like 2026-27")
    start_year = int(match.group(1))
    start_month = 4 + (quarter - 1) * 3
    year = start_year if start_month <= 12 else start_year + 1
    month = start_month if start_month <= 12 else start_month - 12
    start = datetime.date(year, month, 1)
    end_month, end_year = (month + 3, year) if month + 3 <= 12 else (month + 3 - 12, year + 1)
    return start, datetime.date(end_year, end_month, 1) - datetime.timedelta(days=1)


def _issue(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


class TdsChallanService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.dao = TdsChallanDAO(db)
        self.today = today or datetime.date.today()

    # ------------------------------------------------------------------
    def _tolerance(self) -> Decimal:
        row = MasterDAO(self.db).get_system_config_by_key("TDS_CHALLAN_TOLERANCE")
        try:
            return Decimal(row.config_value) if row else Decimal("1")
        except InvalidOperation:
            return Decimal("1")

    def _due_days(self):
        try:
            return configured_deposit_days(self.db)
        except Exception:
            return 7, 30

    def _row_view(self, row) -> Dict[str, Any]:
        invoice, vendor_name, _status, tds, nature, _rule, tracking = row
        due_day, march_day = self._due_days()
        deducted = tracking.deduction_date if tracking else None
        return {
            "invoice_id": invoice.invoice_id,
            "invoice_number": invoice.invoice_number,
            "vendor_id": invoice.vendor_id,
            "vendor_name": vendor_name,
            "tds_amount": _money(tds.tds_amount),
            "section": section_of(row),
            "payment_nature": nature.name if nature is not None else None,
            "residency_type": getattr(tds, "residency_type", None),
            "deduction_date": deducted,
            "deposit_due_date": tds_deposit_due_date(deducted, due_day, march_day) if deducted else None,
            "deposit_date": tracking.deposit_date if tracking else None,
            "challan_number": tracking.challan_number if tracking else None,
            "tracking_status": tracking.tracking_status if tracking else None,
        }

    # ==================================================================
    # Challan
    # ==================================================================
    def challan_candidates(self, period: Optional[str] = None, section: Optional[str] = None) -> Dict[str, Any]:
        start = end = None
        if period:
            try:
                start = datetime.datetime.strptime(period, "%Y-%m").date()
            except ValueError as exc:
                raise ValueError("period must look like 2026-09") from exc
            end = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        rows = self.dao.invoices_in_tracking_status([DEDUCTED], start, end)
        allocated = self.dao.actively_allocated([r[0].invoice_id for r in rows])
        wanted = normalize_section(section)
        items = [self._row_view(r) for r in rows if r[0].invoice_id not in allocated
                 and (not wanted or normalize_section(section_of(r)) == wanted)]
        today = self.today
        for i in items:
            i["overdue"] = bool(i["deposit_due_date"] and i["deposit_due_date"] < today)
        return {"items": items, "total_tds": sum((i["tds_amount"] for i in items), ZERO),
                "sections": sorted({normalize_section(i["section"]) for i in items if i["section"]})}

    def validate_challan(self, header: Dict[str, Any], allocations: Sequence[Dict[str, Any]],
                         has_document: bool) -> Dict[str, Any]:
        errors: List[Dict[str, str]] = []
        warnings: List[Dict[str, str]] = []
        serial = re.sub(r"\D", "", str(header.get("challan_serial_no") or ""))
        bsr = re.sub(r"\D", "", str(header.get("bsr_code") or ""))
        deposit_date = header.get("deposit_date")
        if isinstance(deposit_date, str) and deposit_date:
            deposit_date = datetime.date.fromisoformat(deposit_date)
        if not serial or len(serial) > 5:
            errors.append(_issue("SERIAL", "Challan serial number must be up to 5 digits"))
        if len(bsr) != 7:
            errors.append(_issue("BSR", "BSR code must be 7 digits"))
        if not deposit_date:
            errors.append(_issue("DATE", "Date of deposit is required"))
        elif deposit_date > self.today:
            errors.append(_issue("DATE", "Date of deposit cannot be in the future"))
        tan = (header.get("tan") or "").strip().upper() or None
        if tan and not _TAN_RE.match(tan):
            errors.append(_issue("TAN", "TAN must look like ABCD12345E"))

        amounts = {}
        for key in ("tax_amount", "surcharge", "cess", "interest", "fee"):
            try:
                amounts[key] = _money(header.get(key))
            except ValueError as exc:
                errors.append(_issue("AMOUNT", str(exc)))
                amounts[key] = ZERO
            if amounts[key] < 0:
                errors.append(_issue("AMOUNT", f"{key.replace('_', ' ')} cannot be negative"))
        computed_total = sum(amounts.values(), ZERO)
        total = _money(header.get("total_amount")) if header.get("total_amount") not in (None, "") else computed_total
        if amounts["tax_amount"] <= 0:
            errors.append(_issue("AMOUNT", "Tax amount must be greater than zero"))
        if total != computed_total:
            errors.append(_issue("TOTAL", f"Total {total:,.2f} does not equal tax + surcharge + cess + interest + fee ({computed_total:,.2f})"))

        if serial and len(bsr) == 7 and deposit_date and self.dao.challan_by_identity(bsr, deposit_date, serial.zfill(5)):
            errors.append(_issue("DUPLICATE", "This challan (same BSR code, date and serial) is already recorded"))
        if not has_document and len((header.get("remarks") or "").strip()) < MIN_REASON:
            errors.append(_issue("EVIDENCE", "Attach the challan, or give a reason (at least 10 characters) in remarks"))

        # ---- allocations
        rows: List[Dict[str, Any]] = []
        ids = [int(a["invoice_id"]) for a in allocations]
        if not ids:
            errors.append(_issue("NO_INVOICES", "Select the invoices this challan pays"))
        if len(set(ids)) != len(ids):
            errors.append(_issue("DUPLICATE_INVOICE", "An invoice is selected twice"))
        allocated = self.dao.actively_allocated(ids)
        wanted = normalize_section(header.get("section_code"))
        due_day, march_day = self._due_days()
        late = []
        for a in allocations:
            invoice_id = int(a["invoice_id"])
            row = self.dao.tds_row(invoice_id)
            if row is None:
                errors.append(_issue("INVOICE", f"Invoice {invoice_id} has no applicable TDS"))
                continue
            view = self._row_view(row)
            label = view["invoice_number"]
            tds, tracking = row[3], row[6]
            amount = _money(a.get("allocated_tds_amount", view["tds_amount"]))
            if tds.determination_status != "VERIFIED":
                errors.append(_issue("NOT_VERIFIED", f"{label}: TDS is not verified by Finance"))
            if (tracking.tracking_status if tracking else None) != DEDUCTED:
                errors.append(_issue("NOT_DEDUCTED", f"{label}: TDS must be recorded as deducted (and not already deposited)"))
            if invoice_id in allocated:
                errors.append(_issue("ALREADY_ON_CHALLAN", f"{label}: already covered by challan #{allocated[invoice_id]}"))
            if amount <= 0 or amount > view["tds_amount"]:
                errors.append(_issue("ALLOCATION", f"{label}: amount must be more than 0 and at most its TDS {view['tds_amount']:,.2f}"))
            elif amount < view["tds_amount"]:
                warnings.append(_issue("PART", f"{label}: only {amount:,.2f} of {view['tds_amount']:,.2f} TDS is deposited by this challan"))
            if deposit_date and view["deduction_date"] and deposit_date < view["deduction_date"]:
                errors.append(_issue("BEFORE_DEDUCTION", f"{label}: deposit date is before the deduction date {view['deduction_date']:%d %b %Y}"))
            if wanted and normalize_section(view["section"]) and normalize_section(view["section"]) != wanted:
                errors.append(_issue("SECTION", f"{label}: section {view['section']} does not match the challan's {header.get('section_code')}"))
            if deposit_date and view["deduction_date"]:
                due = tds_deposit_due_date(view["deduction_date"], due_day, march_day)
                if deposit_date > due:
                    late.append(label)
            rows.append({**view, "allocated_tds_amount": amount})

        allocated_total = sum((r["allocated_tds_amount"] for r in rows), ZERO)
        tolerance = self._tolerance()
        if rows and abs(allocated_total - amounts["tax_amount"]) > tolerance:
            errors.append(_issue("SUM", f"Selected invoices' TDS {allocated_total:,.2f} does not match the challan tax "
                                        f"{amounts['tax_amount']:,.2f} (allowed difference {tolerance:,.2f})"))
        if late:
            message = f"Deposited after the due date for {', '.join(late[:5])}{'…' if len(late) > 5 else ''}"
            warnings.append(_issue("LATE", message + (" - interest u/s 201(1A) applies." if amounts["interest"] == 0
                                                       else f" - interest of {amounts['interest']:,.2f} included.")))
        sections = {normalize_section(r["section"]) for r in rows if r["section"]}
        if not wanted and len(sections) > 1:
            warnings.append(_issue("MIXED_SECTIONS", "The selected invoices have different sections; a challan is normally for one section"))
        tax_period = min((r["deduction_date"] for r in rows if r["deduction_date"]), default=None)
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "allocations": rows,
            "allocated_total": allocated_total,
            "computed_total": computed_total,
            "cin": build_cin(bsr, deposit_date, serial) if (serial and len(bsr) == 7 and deposit_date) else None,
            "normalized": {
                "challan_serial_no": serial.zfill(5) if serial else None, "bsr_code": bsr, "deposit_date": deposit_date,
                "tan": tan, "total_amount": total, "tax_period": tax_period.replace(day=1) if tax_period else None,
                **amounts,
            },
        }

    def create_challan(self, header: Dict[str, Any], allocations: Sequence[Dict[str, Any]], user_id: str,
                       document: Optional[Tuple[str, bytes, Optional[str]]] = None, source: str = "MANUAL") -> Dict[str, Any]:
        check = self.validate_challan(header, allocations, document is not None)
        if not check["valid"]:
            raise ValueError("; ".join(e["message"] for e in check["errors"]))
        n = check["normalized"]
        stored = self._store(document, "tds/challans/")
        try:
            challan = self.dao.add(TdsChallan(
                challan_serial_no=n["challan_serial_no"], bsr_code=n["bsr_code"], deposit_date=n["deposit_date"],
                cin=check["cin"], tax_amount=n["tax_amount"], surcharge=n["surcharge"], cess=n["cess"],
                interest=n["interest"], fee=n["fee"], total_amount=n["total_amount"], tan=n["tan"],
                assessment_year=(header.get("assessment_year") or None), minor_head=(header.get("minor_head") or None),
                section_code=(header.get("section_code") or None), tax_period=n["tax_period"],
                file_name=stored and stored[0], file_path=stored and stored[1], content_type=stored and stored[2],
                remarks=(header.get("remarks") or "").strip() or None, source=source, created_by=str(user_id),
            ))
            tracking = TdsTrackingService(self.db)
            for row in check["allocations"]:
                self.dao.add(TdsChallanAllocation(challan_id=challan.challan_id, invoice_id=row["invoice_id"],
                                                  allocated_tds_amount=row["allocated_tds_amount"]))
                # The existing per-invoice deposit - same checks, history and audit - without committing.
                tracking.record_deposit(row["invoice_id"], SimpleNamespace(
                    deposit_date=n["deposit_date"], challan_number=n["challan_serial_no"], bsr_code=n["bsr_code"],
                    remarks=f"Shared challan CIN {check['cin']}"), user_id, commit=False)
                self._link_document(row["invoice_id"], stored, "CHALLAN", user_id)
            self.db.add(AuditLog(table_name="tds_challan", record_id=challan.challan_id, action="TDS_CHALLAN_CONFIRMED",
                                 changed_by=str(user_id),
                                 new_values={"cin": check["cin"], "tax_amount": str(n["tax_amount"]),
                                             "invoices": [r["invoice_id"] for r in check["allocations"]], "source": source}))
            self.db.commit()
        except Exception:
            self.db.rollback()
            self._discard(stored)
            raise
        return self.challan_detail(challan.challan_id)

    def list_challans(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        rows, total = self.dao.list_challans((page - 1) * page_size, page_size)
        counts = self.dao.challan_counts([c.challan_id for c in rows])
        return {"items": [{**self._challan_view(c), "invoice_count": counts.get(c.challan_id, 0)} for c in rows],
                "total": total, "page": page, "page_size": page_size}

    def challan_detail(self, challan_id: int) -> Dict[str, Any]:
        challan = self.dao.get_challan(challan_id)
        if challan is None:
            raise LookupError("Challan not found")
        active = [a for a in challan.allocations if a.is_active]
        rows = self.dao.invoice_numbers([a.invoice_id for a in active])
        return {**self._challan_view(challan), "invoice_count": len(active), "allocations": [
            {**self._row_view(rows[a.invoice_id]), "allocated_tds_amount": _money(a.allocated_tds_amount)}
            for a in active if a.invoice_id in rows]}

    @staticmethod
    def _challan_view(c: TdsChallan) -> Dict[str, Any]:
        return {
            "challan_id": c.challan_id, "cin": c.cin, "challan_serial_no": c.challan_serial_no, "bsr_code": c.bsr_code,
            "deposit_date": c.deposit_date, "tan": c.tan, "assessment_year": c.assessment_year, "minor_head": c.minor_head,
            "section_code": c.section_code, "tax_period": c.tax_period, "tax_amount": c.tax_amount, "surcharge": c.surcharge,
            "cess": c.cess, "interest": c.interest, "fee": c.fee, "total_amount": c.total_amount, "status": c.status,
            "has_document": bool(c.file_path), "file_name": c.file_name, "remarks": c.remarks, "source": c.source,
            "created_by": c.created_by, "created_at": c.created_at,
        }

    # ==================================================================
    # Quarterly filing
    # ==================================================================
    def filing_candidates(self, financial_year: str, quarter: int, revision: bool = False) -> Dict[str, Any]:
        start, end = quarter_bounds(financial_year, quarter)
        statuses = [DEPOSITED, FILED] if revision else [DEPOSITED]
        items = [self._row_view(r) for r in self.dao.invoices_in_tracking_status(statuses, start, end)]
        due = tds_statement_due_date(start)
        suggested = "27Q" if any((i["residency_type"] or "").upper().startswith("NON") for i in items) and \
            all((i["residency_type"] or "").upper().startswith("NON") for i in items) else "26Q"
        return {"items": items, "period_start": start, "period_end": end, "statement_due_date": due,
                "total_tds": sum((i["tds_amount"] for i in items), ZERO), "suggested_form": suggested}

    def validate_filing(self, header: Dict[str, Any], invoice_ids: Sequence[int], has_document: bool) -> Dict[str, Any]:
        errors: List[Dict[str, str]] = []
        warnings: List[Dict[str, str]] = []
        form = (header.get("form_type") or "").strip().upper()
        if form not in FILING_FORMS:
            errors.append(_issue("FORM", f"Form must be one of {', '.join(FILING_FORMS)}"))
        fy = (header.get("financial_year") or "").strip()
        try:
            quarter = int(header.get("quarter"))
            start, end = quarter_bounds(fy, quarter)
        except (TypeError, ValueError) as exc:
            errors.append(_issue("PERIOD", str(exc) if "Financial year" in str(exc) else "Quarter must be 1-4 and the financial year like 2026-27"))
            quarter, start, end = None, None, None
        ack = re.sub(r"\s", "", header.get("acknowledgement_no") or "")
        if not _ACK_RE.match(ack):
            errors.append(_issue("ACK", "Acknowledgement / token number must be 8-30 letters or digits"))
        elif self.dao.filing_by_ack(ack):
            errors.append(_issue("DUPLICATE", "This acknowledgement number is already recorded"))
        filing_date = header.get("filing_date")
        if isinstance(filing_date, str) and filing_date:
            filing_date = datetime.date.fromisoformat(filing_date)
        if not filing_date:
            errors.append(_issue("DATE", "Filing date is required"))
        elif filing_date > self.today:
            errors.append(_issue("DATE", "Filing date cannot be in the future"))
        elif end and filing_date <= end:
            warnings.append(_issue("EARLY", "Filed before the quarter ended - check the quarter"))
        revision = bool(header.get("is_revision"))
        if not has_document and len((header.get("remarks") or "").strip()) < MIN_REASON:
            errors.append(_issue("EVIDENCE", "Attach the acknowledgement, or give a reason (at least 10 characters) in remarks"))
        tan = (header.get("tan") or "").strip().upper() or None
        if tan and not _TAN_RE.match(tan):
            errors.append(_issue("TAN", "TAN must look like ABCD12345E"))

        ids = [int(i) for i in invoice_ids]
        if not ids:
            errors.append(_issue("NO_INVOICES", "Select the invoices this statement covers"))
        rows = []
        for invoice_id in ids:
            row = self.dao.tds_row(invoice_id)
            if row is None:
                errors.append(_issue("INVOICE", f"Invoice {invoice_id} has no applicable TDS"))
                continue
            view = self._row_view(row)
            status = view["tracking_status"]
            allowed = (DEPOSITED, FILED) if revision else (DEPOSITED,)
            if status not in allowed:
                errors.append(_issue("NOT_DEPOSITED", f"{view['invoice_number']}: TDS must be deposited first"
                                     if status != FILED else f"{view['invoice_number']}: already filed - mark this as a correction statement"))
            if start and view["deduction_date"] and not (start <= view["deduction_date"] <= end):
                errors.append(_issue("QUARTER", f"{view['invoice_number']}: deducted on {view['deduction_date']:%d %b %Y}, outside Q{quarter}"))
            if filing_date and view["deposit_date"] and filing_date < view["deposit_date"]:
                errors.append(_issue("BEFORE_DEPOSIT", f"{view['invoice_number']}: filing date is before its deposit date"))
            rows.append(view)
        due = tds_statement_due_date(start) if start else None
        if due and filing_date and filing_date > due and not revision:
            warnings.append(_issue("LATE", f"Filed after the due date {due:%d %b %Y} - late fee u/s 234E may apply"))
        return {"valid": not errors, "errors": errors, "warnings": warnings, "invoices": rows,
                "statement_due_date": due,
                "normalized": {"form_type": form, "financial_year": fy, "quarter": quarter, "acknowledgement_no": ack,
                               "filing_date": filing_date, "is_revision": revision, "tan": tan}}

    def create_filing(self, header: Dict[str, Any], invoice_ids: Sequence[int], user_id: str,
                      document: Optional[Tuple[str, bytes, Optional[str]]] = None, source: str = "MANUAL") -> Dict[str, Any]:
        check = self.validate_filing(header, invoice_ids, document is not None)
        if not check["valid"]:
            raise ValueError("; ".join(e["message"] for e in check["errors"]))
        n = check["normalized"]
        stored = self._store(document, "tds/filings/")
        try:
            filing = self.dao.add(TdsReturnFiling(
                form_type=n["form_type"], financial_year=n["financial_year"], quarter=n["quarter"],
                acknowledgement_no=n["acknowledgement_no"], filing_date=n["filing_date"], tan=n["tan"],
                is_revision=n["is_revision"], file_name=stored and stored[0], file_path=stored and stored[1],
                content_type=stored and stored[2], remarks=(header.get("remarks") or "").strip() or None,
                source=source, created_by=str(user_id),
            ))
            tracking = TdsTrackingService(self.db)
            for row in check["invoices"]:
                self.dao.add(TdsReturnFilingInvoice(filing_id=filing.filing_id, invoice_id=row["invoice_id"]))
                tracking.record_filing(row["invoice_id"], SimpleNamespace(
                    filing_date=n["filing_date"], filing_reference=n["acknowledgement_no"],
                    remarks=f"{n['form_type']} {n['financial_year']} Q{n['quarter']}" + (" (correction)" if n["is_revision"] else "")),
                    user_id, commit=False)
                self._link_document(row["invoice_id"], stored, "FILING_ACKNOWLEDGEMENT", user_id)
            self.db.add(AuditLog(table_name="tds_return_filing", record_id=filing.filing_id, action="TDS_RETURN_FILED",
                                 changed_by=str(user_id),
                                 new_values={"form": n["form_type"], "period": f"{n['financial_year']} Q{n['quarter']}",
                                             "acknowledgement_no": n["acknowledgement_no"],
                                             "invoices": [r["invoice_id"] for r in check["invoices"]], "source": source}))
            self.db.commit()
        except Exception:
            self.db.rollback()
            self._discard(stored)
            raise
        return self.filing_detail(filing.filing_id)

    def list_filings(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        rows, total = self.dao.list_filings((page - 1) * page_size, page_size)
        counts = self.dao.filing_counts([f.filing_id for f in rows])
        return {"items": [{**self._filing_view(f), "invoice_count": counts.get(f.filing_id, 0)} for f in rows],
                "total": total, "page": page, "page_size": page_size}

    def filing_detail(self, filing_id: int) -> Dict[str, Any]:
        filing = self.dao.get_filing(filing_id)
        if filing is None:
            raise LookupError("Filing not found")
        rows = self.dao.invoice_numbers([i.invoice_id for i in filing.invoices])
        return {**self._filing_view(filing), "invoice_count": len(filing.invoices),
                "invoices": [self._row_view(rows[i.invoice_id]) for i in filing.invoices if i.invoice_id in rows]}

    @staticmethod
    def _filing_view(f: TdsReturnFiling) -> Dict[str, Any]:
        return {
            "filing_id": f.filing_id, "form_type": f.form_type, "financial_year": f.financial_year, "quarter": f.quarter,
            "acknowledgement_no": f.acknowledgement_no, "filing_date": f.filing_date, "tan": f.tan,
            "is_revision": f.is_revision, "status": f.status, "has_document": bool(f.file_path), "file_name": f.file_name,
            "remarks": f.remarks, "source": f.source, "created_by": f.created_by, "created_at": f.created_at,
        }

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    @staticmethod
    def _store(document, prefix):
        if not document:
            return None
        from Backend.API_Layer.utils.s3_utils import upload_to_s3
        name, content, content_type = document
        stored = upload_to_s3(filename=name, content=content, content_type=content_type, prefix=prefix)
        return name, stored["filepath"], content_type, len(content)

    @staticmethod
    def _discard(stored):
        if not stored:
            return
        try:
            from Backend.API_Layer.utils.s3_utils import delete_from_s3
            delete_from_s3(stored[1])
        except Exception:
            pass

    def _link_document(self, invoice_id: int, stored, document_type: str, user_id: str) -> None:
        """Show the shared challan / acknowledgement on every covered invoice's TDS documents
        (same S3 object - not copied)."""
        if not stored:
            return
        tracking = self.dao.tracking.get_tracking_locked(invoice_id)
        if tracking is None:
            return
        self.dao.add(InvoiceTdsDocument(invoice_tds_tracking_id=tracking.id, document_type=document_type,
                                        file_name=stored[0], file_path=stored[1], content_type=stored[2],
                                        file_size=stored[3], uploaded_by=str(user_id)))
