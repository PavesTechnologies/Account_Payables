# Backend/Business_Layer/services/accounting_export_service.py
"""Accounting export (P3) - post AP to the books without re-typing it.

Vouchers (double entry, every voucher balances):
  INVOICE  (Journal, invoice date) once approved:   Dr expense (category ledger)      taxable value
                                                     Dr Input CGST / SGST / IGST / Cess  (eligible GST; blocked
                                                        or not-claimable GST is added to the expense instead)
                                                     Cr vendor                          net - TDS
                                                     Cr TDS payable (section)            TDS
  PAYMENT  (Payment, payment date) once cleared:     Dr vendor (against each invoice) / Cr bank
  NOTE     (Journal, note date) once applied:        credit note  Dr vendor / Cr expense + Cr input GST
                                                     debit note   Dr vendor / Cr expense (no GST effect)
                                                     TDS released by the note: Dr TDS payable, vendor less
  CHALLAN  (Payment, deposit date):                  Dr TDS payable (section) + interest + fee / Cr bank

Formats: TALLY_XML (Tally Prime / ERP 9 "Import Data", optional ledger masters, REMOTEID per voucher so a
re-import alters instead of duplicating), ZOHO_CSV (Zoho Books manual-journal import), GENERIC_CSV.
Ledger names come from system_configuration (ACCT_LEDGER_* keys) with sensible defaults; the vendor
ledger is the vendor name. Every export is recorded so the next one defaults to "not yet exported".
"""
from __future__ import annotations

import csv
import datetime
import io
import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

from sqlalchemy import func, select

from Backend.Data_Access_Layer.models.accounting_export import (SOURCE_CHALLAN, SOURCE_INVOICE, SOURCE_NOTE,
                                                                SOURCE_PAYMENT, SOURCE_TYPES, AccountingExport,
                                                                AccountingExportItem)
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import SystemConfiguration

logger = logging.getLogger(__name__)

EXPORT_PERMISSIONS = ["ACCOUNTING_EXPORT", "PAYMENT_PROCESS", "AP_AUTOMATION_MANAGE"]
LEDGER_PERMISSIONS = ["ACCOUNTING_EXPORT", "AP_AUTOMATION_MANAGE"]
FORMATS = ("TALLY_XML", "ZOHO_CSV", "GENERIC_CSV")
BOOKED_STATUSES = ("APPROVED", "READY_FOR_PAYMENT", "PARTIALLY_PAID", "PAID")
CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_DAYS = 400

# key -> (default ledger, Tally group it is created under, label on the page)
LEDGERS: Dict[str, Tuple[str, str, str]] = {
    "BANK": ("Bank Account", "Bank Accounts", "Bank (payments and TDS deposits)"),
    "INPUT_CGST": ("Input CGST", "Duties & Taxes", "Input CGST"),
    "INPUT_SGST": ("Input SGST", "Duties & Taxes", "Input SGST / UTGST"),
    "INPUT_IGST": ("Input IGST", "Duties & Taxes", "Input IGST"),
    "INPUT_CESS": ("Input GST Cess", "Duties & Taxes", "Input GST cess"),
    "TDS_PAYABLE": ("TDS Payable - {section}", "Duties & Taxes", "TDS payable ({section} = 194J, 194C ...)"),
    "TDS_INTEREST": ("Interest on TDS", "Indirect Expenses", "Interest on late TDS deposit"),
    "TDS_FEE": ("Late Fee - TDS", "Indirect Expenses", "Late filing fee (s.234E)"),
    "EXPENSE_DEFAULT": ("General Expenses", "Indirect Expenses", "Expense when the invoice has no category"),
}
KEY_PREFIX = "ACCT_LEDGER_"
VENDOR_GROUP = "Sundry Creditors"


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS, ROUND_HALF_UP)


@dataclass
class Line:
    ledger: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    bill: Optional[str] = None       # bill-wise reference on the vendor line (Tally "New Ref" / "Agst Ref")
    bill_type: Optional[str] = None


@dataclass
class Voucher:
    source_type: str
    source_id: int
    voucher_type: str                # Journal / Payment
    number: str
    date: datetime.date
    reference: str
    narration: str
    party: Optional[str]
    lines: List[Line] = field(default_factory=list)
    exported: Optional[datetime.datetime] = None

    @property
    def amount(self) -> Decimal:
        return sum((l.debit for l in self.lines), ZERO)

    def balanced(self) -> bool:
        return sum((l.debit for l in self.lines), ZERO) == sum((l.credit for l in self.lines), ZERO)

    def compact(self) -> "Voucher":
        """Same ledger + side + bill merged, zero lines dropped."""
        merged: Dict[tuple, Line] = {}
        for l in self.lines:
            if not l.debit and not l.credit:
                continue
            side = "D" if l.debit else "C"
            key = (l.ledger, side, l.bill)
            if key in merged:
                merged[key].debit += l.debit
                merged[key].credit += l.credit
            else:
                merged[key] = Line(l.ledger, l.debit, l.credit, l.bill, l.bill_type)
        self.lines = sorted(merged.values(), key=lambda l: (0 if l.debit else 1))
        return self

    def view(self) -> dict:
        return {"source_type": self.source_type, "source_id": self.source_id, "voucher_type": self.voucher_type,
                "number": self.number, "date": self.date, "reference": self.reference, "narration": self.narration,
                "party": self.party, "amount": self.amount, "exported_at": self.exported,
                "lines": [{"ledger": l.ledger, "debit": l.debit, "credit": l.credit, "bill": l.bill} for l in self.lines]}


class AccountingExportService:
    def __init__(self, db):
        self.db = db
        self._sections: Optional[Dict[int, Optional[str]]] = None

    def _section_map(self) -> Dict[int, Optional[str]]:
        """invoice -> TDS section (194J, 194C ...) as determined on the invoice."""
        if self._sections is None:
            from Backend.Business_Layer.services.ap_reporting_service import APReportingService
            self._sections = {f.invoice_id: f.section for f in APReportingService(self.db).invoice_figures()}
        return self._sections

    # ------------------------------------------------------------------ ledgers
    def _categories(self) -> Dict[int, str]:
        from Backend.Data_Access_Layer.models.purchase import PurchaseCategory
        return dict(self.db.execute(select(PurchaseCategory.id, PurchaseCategory.name).order_by(PurchaseCategory.name)).all())

    def ledgers(self) -> Dict[str, Any]:
        rows = dict(self.db.execute(select(SystemConfiguration.config_key, SystemConfiguration.config_value).where(
            SystemConfiguration.config_key.like(f"{KEY_PREFIX}%"))).all())
        names = {k: rows.get(KEY_PREFIX + k) or default for k, (default, _g, _l) in LEDGERS.items()}
        categories = {cid: rows.get(f"{KEY_PREFIX}CAT_{cid}") or f"{name} Expenses" for cid, name in self._categories().items()}
        return {"ledgers": names, "categories": categories, "company": rows.get(KEY_PREFIX + "COMPANY") or ""}

    def describe_ledgers(self) -> Dict[str, Any]:
        current, names = self.ledgers(), self._categories()
        return {
            "company": current["company"],
            "ledgers": [{"key": k, "label": label, "group": group, "default": default, "name": current["ledgers"][k]}
                        for k, (default, group, label) in LEDGERS.items()],
            "categories": [{"category_id": cid, "category": names[cid], "name": current["categories"][cid]} for cid in names],
        }

    def update_ledgers(self, ledgers: Dict[str, str], categories: Dict[int, str], company: Optional[str], user_id) -> Dict[str, Any]:
        unknown = set(ledgers) - set(LEDGERS)
        if unknown:
            raise ValueError(f"Unknown ledger(s): {', '.join(sorted(unknown))}")
        known_categories = self._categories()
        bad = {int(c) for c in categories} - set(known_categories)
        if bad:
            raise ValueError(f"Unknown purchase category id(s): {', '.join(map(str, sorted(bad)))}")
        changes = {KEY_PREFIX + k: v for k, v in ledgers.items()}
        changes.update({f"{KEY_PREFIX}CAT_{int(c)}": v for c, v in categories.items()})
        if company is not None:
            changes[KEY_PREFIX + "COMPANY"] = company
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        for key, value in changes.items():
            value = (value or "").strip()
            if key != KEY_PREFIX + "COMPANY" and not value:
                raise ValueError("Ledger names cannot be blank")
            if len(value) > 200:
                raise ValueError("Ledger names are limited to 200 characters")
            row = self.db.get(SystemConfiguration, key)
            if row is None:
                row = SystemConfiguration(config_key=key, config_value=value, data_type="STRING",
                                          description="Accounting export ledger name")
                self.db.add(row)
            row.config_value, row.updated_by, row.updated_at = value, str(user_id)[:100], now
        self.db.add(AuditLog(table_name="system_configuration", record_id=0, action="ACCOUNTING_LEDGERS_CHANGED",
                             changed_by=str(user_id), new_values=changes))
        self.db.commit()
        return self.describe_ledgers()

    # ------------------------------------------------------------------ vouchers
    def _exported(self) -> Dict[Tuple[str, int], datetime.datetime]:
        rows = self.db.execute(select(AccountingExportItem.source_type, AccountingExportItem.source_id,
                                      func.max(AccountingExport.created_at))
                               .join(AccountingExport, AccountingExport.export_id == AccountingExportItem.export_id)
                               .group_by(AccountingExportItem.source_type, AccountingExportItem.source_id)).all()
        return {(t, i): at for t, i, at in rows}

    def vouchers(self, date_from: datetime.date, date_to: datetime.date, types: Optional[Iterable[str]] = None) -> List[Voucher]:
        if date_to < date_from:
            raise ValueError("The end date is before the start date")
        if (date_to - date_from).days > MAX_DAYS:
            raise ValueError(f"Export at most {MAX_DAYS} days at a time")
        types = set(types or SOURCE_TYPES)
        if types - set(SOURCE_TYPES):
            raise ValueError(f"Unknown voucher type(s): {', '.join(sorted(types - set(SOURCE_TYPES)))}")
        ledgers = self.ledgers()
        out: List[Voucher] = []
        if SOURCE_INVOICE in types:
            out += self._invoices(date_from, date_to, ledgers)
        if SOURCE_PAYMENT in types:
            out += self._payments(date_from, date_to, ledgers)
        if SOURCE_NOTE in types:
            out += self._notes(date_from, date_to, ledgers)
        if SOURCE_CHALLAN in types:
            out += self._challans(date_from, date_to, ledgers)
        exported = self._exported()
        for v in out:
            v.compact()
            v.exported = exported.get((v.source_type, v.source_id))
            if not v.balanced():  # never expected - the figures above always balance; logged, still listed
                logger.error("Unbalanced voucher %s", v.number)
        return sorted(out, key=lambda v: (v.date, v.number))

    @staticmethod
    def _tds_ledger(ledgers, section: Optional[str]) -> str:
        return ledgers["ledgers"]["TDS_PAYABLE"].replace("{section}", section or "Other")

    def _invoice_meta(self, ids: List[int]) -> Dict[int, tuple]:
        from Backend.Data_Access_Layer.models.invoice import Invoice
        from Backend.Data_Access_Layer.models.invoice_gst import InvoiceGst
        if not ids:
            return {}
        rows = self.db.execute(select(Invoice.invoice_id, Invoice.purchase_category_id, InvoiceGst)
                               .outerjoin(InvoiceGst, InvoiceGst.invoice_id == Invoice.invoice_id)
                               .where(Invoice.invoice_id.in_(ids))).all()
        return {i: (cat, g) for i, cat, g in rows}

    def _expense_ledger(self, ledgers, category_id) -> str:
        return ledgers["categories"].get(category_id) or ledgers["ledgers"]["EXPENSE_DEFAULT"]

    def _invoices(self, date_from, date_to, ledgers) -> List[Voucher]:
        from Backend.Business_Layer.services.ap_reporting_service import APReportingService
        figures = APReportingService(self.db).invoice_figures(BOOKED_STATUSES, invoice_from=date_from, invoice_to=date_to)
        meta = self._invoice_meta([f.invoice_id for f in figures])
        L = ledgers["ledgers"]
        out = []
        for f in figures:
            category_id, g = meta.get(f.invoice_id, (None, None))
            net, tds = _money(f.net_amount), _money(f.tds_amount)
            gst = {"INPUT_CGST": ZERO, "INPUT_SGST": ZERO, "INPUT_IGST": ZERO, "INPUT_CESS": ZERO}
            if g is not None:  # no GST row (no GSTIN / no tax): the whole amount is expense
                gst = {"INPUT_CGST": _money(g.cgst), "INPUT_SGST": _money(g.sgst), "INPUT_IGST": _money(g.igst), "INPUT_CESS": _money(g.cess)}
                if g.itc_eligibility in ("BLOCKED", "NOT_CLAIMABLE"):
                    gst = {k: ZERO for k in gst}  # no credit: the GST is part of the cost
            claimable = sum(gst.values(), ZERO)
            expense = net - claimable
            v = Voucher(SOURCE_INVOICE, f.invoice_id, "Journal", f"APM/INV/{f.invoice_id}", f.invoice_date, f.invoice_number,
                        f"Purchase invoice {f.invoice_number} - {f.vendor_name}" + (f" (TDS {f.section})" if tds else ""),
                        f.vendor_name)
            v.lines.append(Line(self._expense_ledger(ledgers, category_id), debit=expense))
            for key, amount in gst.items():
                v.lines.append(Line(L[key], debit=amount))
            v.lines.append(Line(f.vendor_name, credit=net - tds, bill=f.invoice_number, bill_type="New Ref"))
            if tds:
                v.lines.append(Line(self._tds_ledger(ledgers, f.section), credit=tds))
            out.append(v)
        return out

    def _payments(self, date_from, date_to, ledgers) -> List[Voucher]:
        from Backend.Data_Access_Layer.models.invoice import Invoice
        from Backend.Data_Access_Layer.models.master import StatusMaster
        from Backend.Data_Access_Layer.models.payment import Payment, PaymentInvoice
        from Backend.Data_Access_Layer.models.vendor import Vendor
        payments = self.db.execute(select(Payment, Vendor.vendor_name)
                                   .join(Vendor, Vendor.vendor_id == Payment.vendor_id)
                                   .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
                                   .where(StatusMaster.status_code == "CLEARED", Payment.payment_date >= date_from,
                                          Payment.payment_date <= date_to)).all()
        if not payments:
            return []
        allocations: Dict[int, List[tuple]] = {}
        for pid, number, amount in self.db.execute(
                select(PaymentInvoice.payment_id, Invoice.invoice_number, PaymentInvoice.allocated_amount)
                .join(Invoice, Invoice.invoice_id == PaymentInvoice.invoice_id)
                .where(PaymentInvoice.payment_id.in_([p.payment_id for p, _ in payments]))).all():
            allocations.setdefault(pid, []).append((number, _money(amount)))
        bank = ledgers["ledgers"]["BANK"]
        out = []
        for p, vendor in payments:
            ref = p.reference_number or f"Payment {p.payment_id}"
            v = Voucher(SOURCE_PAYMENT, p.payment_id, "Payment", f"APM/PAY/{p.payment_id}", p.payment_date, ref,
                        f"Payment to {vendor} - {ref}", vendor)
            allocated = allocations.get(p.payment_id) or [(None, _money(p.total_amount))]
            for number, amount in allocated:
                v.lines.append(Line(vendor, debit=amount, bill=number, bill_type="Agst Ref" if number else "On Account"))
            v.lines.append(Line(bank, credit=sum((a for _n, a in allocated), ZERO)))
            out.append(v)
        return out

    def _notes(self, date_from, date_to, ledgers) -> List[Voucher]:
        try:
            from Backend.Business_Layer.services.vendor_note_service import _notes_table_exists
            if not _notes_table_exists(self.db):
                return []
        except (AttributeError, TypeError):
            return []
        from Backend.Data_Access_Layer.models.invoice import Invoice
        from Backend.Data_Access_Layer.models.vendor import Vendor
        from Backend.Data_Access_Layer.models.vendor_note import CREDIT_NOTE, NOTE_APPLIED, VendorNote
        rows = self.db.execute(select(VendorNote, Vendor.vendor_name).join(Vendor, Vendor.vendor_id == VendorNote.vendor_id)
                               .where(VendorNote.status == NOTE_APPLIED, VendorNote.note_date >= date_from,
                                      VendorNote.note_date <= date_to)).all()
        ids = [n.applied_invoice_id or n.reference_invoice_id for n, _ in rows]
        meta = self._invoice_meta([i for i in ids if i])
        numbers = dict(self.db.execute(select(Invoice.invoice_id, Invoice.invoice_number).where(Invoice.invoice_id.in_([i for i in ids if i] or [0]))).all())
        L = ledgers["ledgers"]
        out = []
        for n, vendor in rows:
            target = n.applied_invoice_id or n.reference_invoice_id
            category_id, _g = meta.get(target, (None, None))
            credit = n.note_type == CREDIT_NOTE
            label = "Credit note" if credit else "Debit note"
            total, tds = _money(n.total_amount), _money(n.tds_adjusted)
            v = Voucher(SOURCE_NOTE, n.note_id, "Journal", f"APM/{'CN' if credit else 'DN'}/{n.note_id}", n.note_date,
                        n.note_number, f"{label} {n.note_number} - {vendor}: {n.reason}"[:250], vendor)
            v.lines.append(Line(vendor, debit=total - tds, bill=numbers.get(target), bill_type="Agst Ref"))
            if tds:
                v.lines.append(Line(self._tds_ledger(ledgers, self._section_of(target)), debit=tds))
            gst = {"INPUT_CGST": _money(n.cgst), "INPUT_SGST": _money(n.sgst), "INPUT_IGST": _money(n.igst)} if credit else {}
            for key, amount in gst.items():
                v.lines.append(Line(L[key], credit=amount))
            v.lines.append(Line(self._expense_ledger(ledgers, category_id), credit=total - sum(gst.values(), ZERO)))
            out.append(v)
        return out

    def _section_of(self, invoice_id: Optional[int]) -> Optional[str]:
        return self._section_map().get(invoice_id) if invoice_id else None

    def _challans(self, date_from, date_to, ledgers) -> List[Voucher]:
        from Backend.Data_Access_Layer.models.tds_challan import TdsChallan, TdsChallanAllocation
        rows = self.db.execute(select(TdsChallan).where(TdsChallan.deposit_date >= date_from, TdsChallan.deposit_date <= date_to,
                                                        TdsChallan.status != "CANCELLED")).scalars().all()
        allocations: Dict[int, List[tuple]] = {}
        if rows:
            for cid, invoice_id, amount in self.db.execute(
                    select(TdsChallanAllocation.challan_id, TdsChallanAllocation.invoice_id, TdsChallanAllocation.allocated_tds_amount)
                    .where(TdsChallanAllocation.challan_id.in_([c.challan_id for c in rows]), TdsChallanAllocation.is_active.is_(True))).all():
                allocations.setdefault(cid, []).append((invoice_id, _money(amount)))
        L = ledgers["ledgers"]
        out = []
        for c in rows:
            v = Voucher(SOURCE_CHALLAN, c.challan_id, "Payment", f"APM/TDS/{c.challan_id}", c.deposit_date, c.cin,
                        " ".join(filter(None, ["TDS deposit", c.section_code, f"challan {c.challan_serial_no} BSR {c.bsr_code}"]))
                        + (f" for {c.tax_period:%b %Y}" if c.tax_period else ""), None)
            tax = _money(c.tax_amount) + _money(c.surcharge) + _money(c.cess)
            for invoice_id, amount in allocations.get(c.challan_id, []):  # the deduction section of each invoice it covers
                v.lines.append(Line(self._tds_ledger(ledgers, self._section_of(invoice_id) or c.section_code), debit=amount))
                tax -= amount
            v.lines.append(Line(self._tds_ledger(ledgers, c.section_code), debit=max(tax, ZERO)))
            v.lines.append(Line(L["TDS_INTEREST"], debit=_money(c.interest)))
            v.lines.append(Line(L["TDS_FEE"], debit=_money(c.fee)))
            v.lines.append(Line(L["BANK"], credit=_money(c.total_amount)))
            # a challan's total includes everything above; any other component (penalty) goes to interest
            gap = _money(c.total_amount) - sum((l.debit for l in v.lines), ZERO)
            if gap:
                v.lines.append(Line(L["TDS_INTEREST"], debit=gap))
            out.append(v)
        return out

    # ------------------------------------------------------------------ preview / export
    def preview(self, date_from, date_to, types=None, include_exported: bool = False) -> Dict[str, Any]:
        vouchers = self.vouchers(date_from, date_to, types)
        pending = [v for v in vouchers if include_exported or v.exported is None]
        by_type: Dict[str, dict] = {}
        for v in pending:
            t = by_type.setdefault(v.source_type, {"count": 0, "amount": ZERO})
            t["count"] += 1
            t["amount"] += v.amount
        return {"date_from": date_from, "date_to": date_to, "total": len(vouchers), "selected": len(pending),
                "already_exported": sum(1 for v in vouchers if v.exported), "by_type": by_type,
                "unbalanced": [v.number for v in pending if not v.balanced()],
                "vouchers": [v.view() for v in pending]}

    def export(self, date_from, date_to, export_format: str, user_id, types=None, include_exported: bool = False,
               include_masters: bool = True) -> Tuple[str, bytes, str, Dict[str, Any]]:
        if export_format not in FORMATS:
            raise ValueError(f"Format must be one of {', '.join(FORMATS)}")
        vouchers = [v for v in self.vouchers(date_from, date_to, types) if include_exported or v.exported is None]
        if not vouchers:
            raise ValueError("Nothing to export for this period - everything is already exported (tick 're-export' to repeat)")
        unbalanced = [v.number for v in vouchers if not v.balanced()]
        if unbalanced:
            raise ValueError(f"Vouchers do not balance: {', '.join(unbalanced[:5])}")
        ledgers = self.ledgers()
        stamp = f"{date_from:%Y%m%d}_{date_to:%Y%m%d}"
        if export_format == "TALLY_XML":
            name, content, ctype = f"APM_Tally_{stamp}.xml", tally_xml(vouchers, ledgers, include_masters), "application/xml"
        elif export_format == "ZOHO_CSV":
            name, content, ctype = f"APM_ZohoBooks_Journals_{stamp}.csv", zoho_csv(vouchers), "text/csv"
        else:
            name, content, ctype = f"APM_Vouchers_{stamp}.csv", generic_csv(vouchers), "text/csv"
        try:
            from Backend.API_Layer.utils.s3_utils import upload_to_s3
            path = upload_to_s3(name, content, ctype, prefix="accounting-export/")["filepath"]
        except Exception:
            logger.exception("Accounting export file not stored to S3")
            path = None
        record = AccountingExport(export_format=export_format, date_from=date_from, date_to=date_to, voucher_count=len(vouchers),
                                  total_debit=sum((v.amount for v in vouchers), ZERO), created_by=str(user_id),
                                  file_name=name, file_path=path)
        self.db.add(record)
        self.db.flush()
        for v in vouchers:
            self.db.add(AccountingExportItem(export_id=record.export_id, source_type=v.source_type, source_id=v.source_id,
                                             voucher_number=v.number, voucher_date=v.date, amount=v.amount))
        self.db.add(AuditLog(table_name="accounting_export", record_id=record.export_id, action="ACCOUNTING_EXPORTED",
                             changed_by=str(user_id), new_values={"format": export_format, "from": date_from.isoformat(),
                                                                   "to": date_to.isoformat(), "vouchers": len(vouchers)}))
        self.db.commit()
        return name, content, ctype, {"export_id": record.export_id, "vouchers": len(vouchers)}

    def history(self, limit: int = 20) -> List[dict]:
        rows = self.db.execute(select(AccountingExport).order_by(AccountingExport.created_at.desc()).limit(limit)).scalars().all()
        return [{"export_id": r.export_id, "format": r.export_format, "date_from": r.date_from, "date_to": r.date_to,
                 "vouchers": r.voucher_count, "total_debit": r.total_debit, "created_at": r.created_at,
                 "created_by": r.created_by, "file_name": r.file_name, "has_file": bool(r.file_path)} for r in rows]

    def file(self, export_id: int) -> Tuple[str, bytes, str]:
        row = self.db.get(AccountingExport, export_id)
        if row is None or not row.file_path:
            raise LookupError("Export file not found")
        from Backend.API_Layer.utils.s3_utils import get_object_bytes
        content = get_object_bytes(row.file_path)
        return row.file_name, content, "application/xml" if row.file_name.endswith(".xml") else "text/csv"


# ---------------------------------------------------------------------- renderers
def _tally_amount(line: Line) -> str:
    # Tally: debits are negative with ISDEEMEDPOSITIVE=Yes, credits positive with No
    return f"-{line.debit:.2f}" if line.debit else f"{line.credit:.2f}"


def _ledger_masters(vouchers: List[Voucher], ledgers) -> List[Tuple[str, str]]:
    groups = {name: group for key, (_d, group, _l) in LEDGERS.items() for name in [ledgers["ledgers"][key]] if "{section}" not in name}
    for name in ledgers["categories"].values():
        groups.setdefault(name, "Indirect Expenses")
    parties = {v.party for v in vouchers if v.party}
    out: Dict[str, str] = {}
    for v in vouchers:
        for l in v.lines:
            if l.ledger in parties:
                out[l.ledger] = VENDOR_GROUP
            elif l.ledger.startswith(ledgers["ledgers"]["TDS_PAYABLE"].split("{section}")[0]) and "{section}" in ledgers["ledgers"]["TDS_PAYABLE"]:
                out[l.ledger] = "Duties & Taxes"
            else:
                out[l.ledger] = groups.get(l.ledger, "Indirect Expenses")
    return sorted(out.items())


def tally_xml(vouchers: List[Voucher], ledgers, include_masters: bool = True) -> bytes:
    company = ledgers.get("company") or ""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<ENVELOPE>",
             "<HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>", "<BODY>"]

    def section(report: str, messages: List[str]):
        parts.append("<IMPORTDATA><REQUESTDESC>")
        parts.append(f"<REPORTNAME>{report}</REPORTNAME>")
        if company:
            parts.append(f"<STATICVARIABLES><SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY></STATICVARIABLES>")
        parts.append("</REQUESTDESC><REQUESTDATA>")
        parts.extend(messages)
        parts.append("</REQUESTDATA></IMPORTDATA>")

    if include_masters:
        masters = [f'<TALLYMESSAGE xmlns:UDF="TallyUDF"><LEDGER NAME={quoteattr(name)} ACTION="Create">'
                   f"<NAME.LIST><NAME>{escape(name)}</NAME></NAME.LIST><PARENT>{escape(group)}</PARENT>"
                   + ("<ISBILLWISEON>Yes</ISBILLWISEON>" if group == VENDOR_GROUP else "")
                   + "</LEDGER></TALLYMESSAGE>" for name, group in _ledger_masters(vouchers, ledgers)]
        section("All Masters", masters)
    messages = []
    for v in vouchers:
        x = [f'<TALLYMESSAGE xmlns:UDF="TallyUDF"><VOUCHER REMOTEID={quoteattr(v.number)} VCHTYPE={quoteattr(v.voucher_type)} ACTION="Create">',
             f"<DATE>{v.date:%Y%m%d}</DATE><EFFECTIVEDATE>{v.date:%Y%m%d}</EFFECTIVEDATE>",
             f"<VOUCHERTYPENAME>{v.voucher_type}</VOUCHERTYPENAME><VOUCHERNUMBER>{escape(v.number)}</VOUCHERNUMBER>",
             f"<REFERENCE>{escape(v.reference or '')}</REFERENCE><NARRATION>{escape(v.narration)}</NARRATION>"]
        if v.party:
            x.append(f"<PARTYLEDGERNAME>{escape(v.party)}</PARTYLEDGERNAME>")
        for l in v.lines:
            x.append(f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{escape(l.ledger)}</LEDGERNAME>"
                     f"<ISDEEMEDPOSITIVE>{'Yes' if l.debit else 'No'}</ISDEEMEDPOSITIVE>"
                     f"<ISPARTYLEDGER>{'Yes' if l.ledger == v.party else 'No'}</ISPARTYLEDGER><AMOUNT>{_tally_amount(l)}</AMOUNT>")
            if l.bill and l.ledger == v.party:
                x.append(f"<BILLALLOCATIONS.LIST><NAME>{escape(l.bill)}</NAME><BILLTYPE>{escape(l.bill_type or 'Agst Ref')}</BILLTYPE>"
                         f"<AMOUNT>{_tally_amount(l)}</AMOUNT></BILLALLOCATIONS.LIST>")
            x.append("</ALLLEDGERENTRIES.LIST>")
        x.append("</VOUCHER></TALLYMESSAGE>")
        messages.append("".join(x))
    section("Vouchers", messages)
    parts.append("</BODY></ENVELOPE>")
    return "\n".join(parts).encode("utf-8")


ZOHO_COLUMNS = ["Journal Date", "Journal Number", "Reference Number", "Notes", "Journal Type", "Currency Code",
                "Account", "Description", "Contact Name", "Debit", "Credit"]


def zoho_csv(vouchers: List[Voucher]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(ZOHO_COLUMNS)
    for v in vouchers:
        for l in v.lines:
            w.writerow([v.date.isoformat(), v.number, v.reference, v.narration, "both", "INR", l.ledger,
                        f"Against {l.bill}" if l.bill else "", v.party if l.ledger == v.party else "",
                        f"{l.debit:.2f}" if l.debit else "", f"{l.credit:.2f}" if l.credit else ""])
    return buf.getvalue().encode("utf-8-sig")


GENERIC_COLUMNS = ["Voucher Number", "Voucher Type", "Date", "Source", "Source ID", "Reference", "Narration", "Party",
                   "Ledger", "Debit", "Credit", "Bill Reference"]


def generic_csv(vouchers: List[Voucher]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(GENERIC_COLUMNS)
    for v in vouchers:
        for l in v.lines:
            w.writerow([v.number, v.voucher_type, v.date.isoformat(), v.source_type, v.source_id, v.reference, v.narration,
                        v.party or "", l.ledger, f"{l.debit:.2f}" if l.debit else "", f"{l.credit:.2f}" if l.credit else "",
                        l.bill or ""])
    return buf.getvalue().encode("utf-8-sig")
