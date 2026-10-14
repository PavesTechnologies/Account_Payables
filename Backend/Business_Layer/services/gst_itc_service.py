# Backend/Business_Layer/services/gst_itc_service.py
"""GST input tax credit (ITC) register (P2) - recover the GST paid to vendors, and keep it.

  sync_invoice      builds / refreshes an invoice's ITC row from the invoice, the vendor's GSTIN and the
                    OCR extraction (CGST / SGST / IGST split, IRN, reverse charge). Never raises.
  set_eligibility   Finance overrides ELIGIBLE / REVIEW / BLOCKED (section 17(5)) with a reason.
  claim             marks the period's claimable credit as taken in that month's GSTR-3B.
  reverse / reclaim the 180-day rule (section 16(2), second proviso): credit on an invoice not paid
                    within 180 days of its date is reversed; re-claimed once the vendor is paid.
  register / attention   the ITC page and the Action Center.

Claimable = ELIGIBLE, not yet claimed, invoice approved or later, and - for suppliers who must
e-invoice - an IRN on the invoice (credit on an e-invoice without IRN is not admissible).
Once a GSTR-2B (what the vendor actually filed) is imported for the invoice's month or later, the
invoice must also be MATCHED there (s.16(2)(aa)); before that the register says "not checked".
Every change is written to audit_log.
"""
from __future__ import annotations

import datetime
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select

from Backend.config.env_loader import get_env_var
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceLine
from Backend.Data_Access_Layer.models.invoice_gst import (
    BLOCKED,
    ELIGIBLE,
    IRN_MISSING,
    IRN_NOT_REQUIRED,
    IRN_PRESENT,
    IRN_UNKNOWN,
    ITC_CLAIMED,
    ITC_PENDING,
    ITC_REVERSED,
    NOT_CLAIMABLE,
    REVIEW,
    InvoiceGst,
)
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.vendor import VendorAddress, VendorTax

logger = logging.getLogger(__name__)

VIEW_PERMISSIONS = ["GST_ITC_VIEW", "GST_ITC_MANAGE", "PAYMENT_VIEW", "PAYMENT_PROCESS", "AP_AUTOMATION_MANAGE"]
MANAGE_PERMISSIONS = ["GST_ITC_MANAGE", "AP_AUTOMATION_MANAGE"]

CLAIMABLE_INVOICE_STATUSES = ("APPROVED", "READY_FOR_PAYMENT", "PARTIALLY_PAID", "PAID")
DEAD_INVOICE_STATUSES = ("REJECTED",)
REVERSAL_DAYS = 180
AT_RISK_DAYS = 150
GSTR3B_DUE_DAY = 20
CENTS = Decimal("0.01")
ZERO = Decimal("0.00")

# Section 17(5) blocked credits most often seen on AP invoices: SAC/HSN prefix or wording -> reason.
BLOCKED_HINTS = [
    (("9963",), ("food", "beverage", "catering", "canteen", "restaurant", "meal"), "Food, beverages or outdoor catering (s.17(5)(b)(i))"),
    (("996601", "996602", "996412"), ("cab", "taxi", "car rental", "rent-a-cab"), "Rent-a-cab / passenger transport (s.17(5)(b)(i))"),
    (("999721", "999722"), ("club", "health club", "gym", "fitness"), "Club / health & fitness membership (s.17(5)(b)(ii))"),
    (("9954",), ("construction of", "civil work"), "Works contract for immovable property (s.17(5)(c)/(d))"),
    ((), ("gift", "personal"), "Gifts / personal consumption (s.17(5)(h))"),
]

_einvoice_cache: Dict[str, Optional[bool]] = {}


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS, ROUND_HALF_UP)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def month_start(day: datetime.date) -> datetime.date:
    return day.replace(day=1)


def month_end(day: datetime.date) -> datetime.date:
    return (day.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)


def gstr3b_due(period: datetime.date) -> datetime.date:
    """GSTR-3B for a month is due on the 20th of the next month."""
    return (month_end(period) + datetime.timedelta(days=1)).replace(day=GSTR3B_DUE_DAY)


def split_tax(tax: Decimal, supplier_state: Optional[str], place_of_supply: Optional[str],
              extracted: Optional[dict] = None) -> Dict[str, Any]:
    """CGST / SGST / IGST for an invoice: the OCR split when it adds up to the invoice's tax,
    otherwise derived from the states (same state -> half CGST, half SGST; else IGST)."""
    tax = _money(tax)
    amounts = (extracted or {}).get("amounts") or {}
    parts = {k: _money(amounts.get(f"{k}_amount")) for k in ("cgst", "sgst", "igst", "cess")}
    parts["sgst"] += _money(amounts.get("ugst_amount"))
    if sum(parts.values()) > 0 and abs(sum(parts.values()) - tax) <= Decimal("1"):
        supply = "INTER" if parts["igst"] > 0 else "INTRA"
        return {**parts, "supply_type": supply}
    if supplier_state and place_of_supply and supplier_state != place_of_supply:
        return {"cgst": ZERO, "sgst": ZERO, "igst": tax, "cess": ZERO, "supply_type": "INTER"}
    half = (tax / 2).quantize(CENTS, ROUND_HALF_UP)
    return {"cgst": half, "sgst": tax - half, "igst": ZERO, "cess": ZERO, "supply_type": "INTRA"}


def eligibility_hint(lines: Iterable[tuple]) -> Optional[str]:
    """A section 17(5) reason when a line looks like a blocked credit (for Finance to review)."""
    for sac, description in lines:
        code = re.sub(r"\D", "", sac or "")
        text = (description or "").lower()
        for prefixes, words, reason in BLOCKED_HINTS:
            if (code and any(code.startswith(p) for p in prefixes)) or any(w in text for w in words):
                return reason
    return None


def _state_code(place: Optional[str]) -> Optional[str]:
    match = re.search(r"\b(\d{2})\b", place or "")
    return match.group(1) if match else None


class GstItcService:
    def __init__(self, db, today: Optional[datetime.date] = None, einvoice_lookup=None, gstr2b_lookup=None):
        self.db = db
        self.today = today or datetime.date.today()
        self._lookup = einvoice_lookup or self._einvoice_from_gst_portal
        self._gstr2b_lookup = gstr2b_lookup
        self._gstr2b_cache = None
        self.buyer_state = str(get_env_var("BUYER_CODE", "36") or "36").zfill(2)[:2]

    # ------------------------------------------------------------------ inputs
    def _status_code(self, invoice: Invoice) -> Optional[str]:
        status = self.db.get(StatusMaster, invoice.status_id) if invoice.status_id else None
        return status.status_code if status else None

    def _supplier_gstin(self, vendor_id: int) -> Optional[str]:
        row = self.db.execute(select(VendorTax.registration_number).join(
            VendorAddress, VendorAddress.vendor_address_id == VendorTax.vendor_address_id).where(
            VendorAddress.vendor_id == vendor_id, VendorTax.registration_type == "GST").order_by(
            VendorAddress.is_primary.desc())).first()
        if row is None or not row[0]:
            return None
        return row[0].strip().upper() or None

    def _extraction(self, invoice: Invoice) -> dict:
        if not invoice.inbound_document_id:
            return {}
        doc = self.db.get(InboundDocument, invoice.inbound_document_id)
        return doc.raw_extracted_data if doc is not None and isinstance(doc.raw_extracted_data, dict) else {}

    @staticmethod
    def _einvoice_from_gst_portal(gstin: str) -> Optional[bool]:
        """Whether the supplier is e-invoice enabled, from the GST portal (Sandbox) - None if unknown."""
        from Backend.Business_Layer.utils.gst_service import search_gstin
        result = search_gstin(gstin)
        data = (result or {}).get("data") or {}
        data = data.get("data", data)
        status = str(data.get("einvoiceStatus") or "").strip().lower()
        return True if status == "yes" else False if status == "no" else None

    def einvoice_applicable(self, gstin: Optional[str]) -> Optional[bool]:
        if not gstin:
            return None
        if gstin in _einvoice_cache:
            return _einvoice_cache[gstin]
        known = self.db.execute(select(InvoiceGst.einvoice_applicable).where(
            InvoiceGst.supplier_gstin == gstin, InvoiceGst.einvoice_applicable.is_not(None),
            InvoiceGst.updated_at >= _now() - datetime.timedelta(days=30)).limit(1)).scalar()
        if known is None:
            try:
                known = self._lookup(gstin)
            except Exception:
                logger.info("e-invoice status lookup failed for %s", gstin)
                known = None
        _einvoice_cache[gstin] = known
        return known

    # ------------------------------------------------------------------ build the row
    def sync_invoice(self, invoice_id: int) -> Optional[InvoiceGst]:
        try:
            row = self._sync(invoice_id)
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.exception("GST ITC sync failed for invoice %s", invoice_id)
            return None
        if row is not None:
            self._rematch_gstr2b(invoice_id)
        return row

    def _rematch_gstr2b(self, invoice_id: int) -> None:
        """A supplier's filing imported before the invoice was booked (or corrected) now matches it."""
        try:
            from Backend.Business_Layer.services.gstr2b_service import Gstr2bService, _table_exists
            if _table_exists(self.db):
                Gstr2bService(self.db).rematch(invoice_id)
                self._gstr2b_cache = None
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.exception("GSTR-2B re-match failed for invoice %s", invoice_id)

    def _sync(self, invoice_id: int) -> Optional[InvoiceGst]:
        invoice = self.db.get(Invoice, invoice_id)
        if invoice is None:
            return None
        row = self.db.get(InvoiceGst, invoice_id) or InvoiceGst(invoice_id=invoice_id)
        extracted = self._extraction(invoice)
        compliance = extracted.get("compliance") or {}
        irn = (compliance.get("irn") or "").strip() or None
        if row.itc_status in (ITC_CLAIMED, ITC_REVERSED):  # amounts are frozen once in a return
            if irn and not row.irn:
                row.irn, row.irn_status = irn[:64], IRN_PRESENT
                row.updated_at = _now()
                self.db.commit()
            return row
        gstin = self._supplier_gstin(invoice.vendor_id) if invoice.vendor_id else None
        supplier_state = gstin[:2] if gstin else None
        place = _state_code((extracted.get("tax") or {}).get("place_of_supply")) or self.buyer_state
        tax = _money(invoice.tax_amount)
        parts = split_tax(tax, supplier_state, place, extracted)
        row.supplier_gstin, row.place_of_supply, row.supply_type = gstin, place, parts["supply_type"]
        row.cgst, row.sgst, row.igst, row.cess = parts["cgst"], parts["sgst"], parts["igst"], parts["cess"]
        row.taxable_value = _money(invoice.net_amount) - tax
        row.reverse_charge = bool(compliance.get("reverse_charge") or (extracted.get("tax") or {}).get("reverse_charge"))
        row.reversal_due_date = invoice.invoice_date + datetime.timedelta(days=REVERSAL_DAYS) if invoice.invoice_date else None

        applicable = self.einvoice_applicable(gstin)
        row.einvoice_applicable = applicable
        row.irn = irn[:64] if irn else row.irn
        row.ack_no = (str(compliance.get("acknowledgement_number") or "").strip() or row.ack_no or None)
        row.irn_status = (IRN_PRESENT if row.irn else IRN_MISSING if applicable else
                          IRN_NOT_REQUIRED if applicable is False else IRN_UNKNOWN)

        status = self._status_code(invoice)
        if not row.eligibility_locked:
            if not gstin:
                row.itc_eligibility, row.eligibility_reason = NOT_CLAIMABLE, "Supplier has no GSTIN on the vendor master"
            elif tax <= 0:
                row.itc_eligibility, row.eligibility_reason = NOT_CLAIMABLE, "No GST charged on this invoice"
            else:
                lines = [(None, l.description) for l in self.db.execute(
                    select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id)).scalars()]
                hint = eligibility_hint(lines)
                row.itc_eligibility, row.eligibility_reason = (REVIEW, hint) if hint else (ELIGIBLE, None)
        row.itc_status = NOT_CLAIMABLE if (status in DEAD_INVOICE_STATUSES or row.itc_eligibility in (BLOCKED, NOT_CLAIMABLE)) else ITC_PENDING
        row.updated_at = _now()
        self.db.add(row)
        self.db.commit()
        return row

    def sync_all(self) -> int:
        ids = [i for (i,) in self.db.execute(select(Invoice.invoice_id).order_by(Invoice.invoice_id))]
        return sum(1 for i in ids if self.sync_invoice(i) is not None)

    # ------------------------------------------------------------------ Finance actions
    def _audit(self, invoice_id: int, action: str, user_id, new: dict, old: Optional[dict] = None):
        self.db.add(AuditLog(table_name="invoice", record_id=invoice_id, action=action, changed_by=str(user_id),
                             old_values=old, new_values=new))

    def set_eligibility(self, invoice_id: int, eligibility: str, reason: str, user_id) -> InvoiceGst:
        if eligibility not in (ELIGIBLE, REVIEW, BLOCKED):
            raise ValueError("Eligibility must be ELIGIBLE, REVIEW or BLOCKED")
        if len((reason or "").strip()) < 5:
            raise ValueError("Give a reason (at least 5 characters)")
        row = self.db.get(InvoiceGst, invoice_id) or self._sync(invoice_id)
        if row is None:
            raise LookupError(f"Invoice {invoice_id} not found")
        if row.itc_status in (ITC_CLAIMED, ITC_REVERSED):
            raise ValueError("Credit already claimed in a return - correct it through the next return instead")
        old = {"itc_eligibility": row.itc_eligibility, "reason": row.eligibility_reason}
        row.itc_eligibility, row.eligibility_reason, row.eligibility_locked = eligibility, reason.strip(), True
        row.eligibility_set_by = str(user_id)
        row.itc_status = NOT_CLAIMABLE if eligibility == BLOCKED else ITC_PENDING
        row.updated_at = _now()
        self._audit(invoice_id, "GST_ITC_ELIGIBILITY_SET", user_id, {"itc_eligibility": eligibility, "reason": row.eligibility_reason}, old)
        self.db.commit()
        return row

    def set_irn(self, invoice_id: int, irn: str, ack_no: Optional[str], user_id) -> InvoiceGst:
        """Record the e-invoice IRN (64 hex characters, from the invoice's QR code) when OCR missed it."""
        irn = (irn or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", irn):
            raise ValueError("An IRN is 64 characters (0-9, a-f) - copy it from the e-invoice or its QR code")
        row = self.db.get(InvoiceGst, invoice_id) or self._sync(invoice_id)
        if row is None:
            raise LookupError(f"Invoice {invoice_id} not found")
        old = {"irn": row.irn}
        row.irn, row.irn_status = irn, IRN_PRESENT
        if ack_no:
            row.ack_no = ack_no.strip()[:30]
        row.updated_at = _now()
        self._audit(invoice_id, "GST_IRN_RECORDED", user_id, {"irn": irn, "ack_no": row.ack_no}, old)
        self.db.commit()
        return row

    def _gstr2b(self):
        if self._gstr2b_cache is None:
            if self._gstr2b_lookup is not None:
                self._gstr2b_cache = self._gstr2b_lookup()
            else:
                from Backend.Business_Layer.services.gstr2b_service import gstr2b_state
                self._gstr2b_cache = gstr2b_state(self.db)
        return self._gstr2b_cache

    def gstr2b_status(self, invoice) -> Optional[str]:
        """MATCHED / MISMATCH / MISSING once a GSTR-2B covering the invoice's month is imported, else None."""
        statuses, first, latest = self._gstr2b()
        if latest is None or not invoice.invoice_date or not first <= month_start(invoice.invoice_date) <= latest:
            return None
        return statuses.get(invoice.invoice_id, "MISSING")

    def _rows_with_invoices(self, *conditions):
        stmt = (select(InvoiceGst, Invoice, StatusMaster.status_code)
                .join(Invoice, Invoice.invoice_id == InvoiceGst.invoice_id)
                .join(StatusMaster, StatusMaster.status_id == Invoice.status_id, isouter=True))
        for c in conditions:
            stmt = stmt.where(c)
        return self.db.execute(stmt.order_by(Invoice.invoice_date, Invoice.invoice_id)).all()

    def claimable(self, period: datetime.date) -> List[tuple]:
        return [(g, i, s) for g, i, s in self._rows_with_invoices(
            InvoiceGst.itc_status == ITC_PENDING, InvoiceGst.itc_eligibility == ELIGIBLE,
            Invoice.invoice_date <= month_end(period))
            if s in CLAIMABLE_INVOICE_STATUSES and g.irn_status != IRN_MISSING and self.gstr2b_status(i) in (None, "MATCHED")]

    def pending_credit_notes(self, period: datetime.date) -> list:
        """Vendor credit notes up to the period whose GST has not yet reduced a claim (s.34)."""
        from Backend.Business_Layer.services.vendor_note_service import _notes_table_exists
        from Backend.Data_Access_Layer.models.vendor_note import CREDIT_NOTE, NOTE_CANCELLED, VendorNote
        try:
            if not _notes_table_exists(self.db):
                return []
        except (AttributeError, TypeError):
            return []
        notes = self.db.execute(select(VendorNote).where(
            VendorNote.note_type == CREDIT_NOTE, VendorNote.status != NOTE_CANCELLED, VendorNote.itc_period.is_(None),
            VendorNote.note_date <= month_end(period))).scalars().all()
        return [n for n in notes if (n.cgst + n.sgst + n.igst) > 0]

    def claim(self, period: datetime.date, user_id) -> Dict[str, Any]:
        period = month_start(period)
        if period > month_start(self.today):
            raise ValueError("A return period cannot be in the future")
        rows = self.claimable(period)
        notes = self.pending_credit_notes(period)
        if not rows and not notes:
            raise ValueError("Nothing to claim for this period")
        now = _now()
        total = ZERO
        for g, invoice, _s in rows:
            g.itc_status, g.claim_period, g.claimed_at, g.claimed_by, g.updated_at = ITC_CLAIMED, period, now, str(user_id), now
            amount = g.cgst + g.sgst + g.igst + g.cess
            total += amount
            self._audit(invoice.invoice_id, "GST_ITC_CLAIMED", user_id,
                        {"return": "GSTR-3B", "period": period.isoformat(), "itc": str(amount)})
        note_gst = ZERO
        for note in notes:  # a credit note's GST comes off the credit claimed in the same return
            gst = note.cgst + note.sgst + note.igst
            note.itc_period, note.updated_at = period, now
            note_gst += gst
            self.db.add(AuditLog(table_name="vendor_note", record_id=note.note_id, action="GST_ITC_REDUCED_BY_CREDIT_NOTE",
                                 changed_by=str(user_id), new_values={"period": period.isoformat(), "gst": str(gst)}))
        self.db.commit()
        return {"period": period, "invoices": len(rows), "itc": total - note_gst, "gross_itc": total,
                "credit_notes": len(notes), "credit_note_gst": note_gst}

    def reverse(self, invoice_ids: List[int], period: datetime.date, user_id) -> int:
        period, now, done = month_start(period), _now(), 0
        for g, invoice, status in self._rows_with_invoices(InvoiceGst.invoice_id.in_(invoice_ids)):
            if g.itc_status != ITC_CLAIMED:
                raise ValueError(f"Invoice {invoice.invoice_number}: only claimed credit can be reversed")
            if status == "PAID":
                raise ValueError(f"Invoice {invoice.invoice_number} is paid - no reversal needed")
            g.itc_status, g.reversal_period, g.reversed_at, g.reversed_by, g.updated_at = ITC_REVERSED, period, now, str(user_id), now
            self._audit(invoice.invoice_id, "GST_ITC_REVERSED", user_id, {"period": period.isoformat(),
                        "reason": f"Not paid within {REVERSAL_DAYS} days of the invoice date"})
            done += 1
        self.db.commit()
        return done

    def reclaim(self, invoice_ids: List[int], period: datetime.date, user_id) -> int:
        period, now, done = month_start(period), _now(), 0
        for g, invoice, status in self._rows_with_invoices(InvoiceGst.invoice_id.in_(invoice_ids)):
            if g.itc_status != ITC_REVERSED or status != "PAID":
                raise ValueError(f"Invoice {invoice.invoice_number}: only reversed credit of a paid invoice can be re-claimed")
            g.itc_status, g.reclaim_period, g.reclaimed_at, g.updated_at = ITC_CLAIMED, period, now, now
            self._audit(invoice.invoice_id, "GST_ITC_RECLAIMED", user_id, {"period": period.isoformat()})
            done += 1
        self.db.commit()
        return done

    # ------------------------------------------------------------------ views
    def _view(self, g: InvoiceGst, invoice: Invoice, status: Optional[str], vendor_name: Optional[str]) -> dict:
        unpaid = status != "PAID"
        age = (self.today - invoice.invoice_date).days if invoice.invoice_date else None
        risk = None
        if unpaid and g.itc_status in (ITC_PENDING, ITC_CLAIMED) and age is not None and g.itc_eligibility == ELIGIBLE:
            risk = "REVERSAL_DUE" if age > REVERSAL_DAYS and g.itc_status == ITC_CLAIMED else "AT_RISK" if age >= AT_RISK_DAYS else None
        if g.itc_status == ITC_REVERSED and not unpaid:
            risk = "RECLAIM"
        twob = self.gstr2b_status(invoice) if g.itc_eligibility == ELIGIBLE else None
        return {
            "invoice_id": invoice.invoice_id, "invoice_number": invoice.invoice_number, "invoice_date": invoice.invoice_date,
            "vendor_name": vendor_name, "supplier_gstin": g.supplier_gstin, "supply_type": g.supply_type,
            "invoice_status": status, "taxable_value": g.taxable_value, "cgst": g.cgst, "sgst": g.sgst, "igst": g.igst,
            "cess": g.cess, "itc": g.cgst + g.sgst + g.igst + g.cess, "itc_eligibility": g.itc_eligibility,
            "eligibility_reason": g.eligibility_reason, "itc_status": g.itc_status, "claim_period": g.claim_period,
            "irn_status": g.irn_status, "irn": g.irn, "reverse_charge": g.reverse_charge,
            "reversal_due_date": g.reversal_due_date, "days_since_invoice": age, "risk": risk, "gstr2b": twob,
            "claimable": (g.itc_status == ITC_PENDING and g.itc_eligibility == ELIGIBLE and status in CLAIMABLE_INVOICE_STATUSES
                          and g.irn_status != IRN_MISSING and twob in (None, "MATCHED")),
        }

    def _all_views(self) -> List[dict]:
        from Backend.Data_Access_Layer.models.vendor import Vendor
        names = dict(self.db.execute(select(Vendor.vendor_id, Vendor.vendor_name)).all())
        return [self._view(g, i, s, names.get(i.vendor_id)) for g, i, s in self._rows_with_invoices()]

    def register(self, month: Optional[datetime.date] = None) -> Dict[str, Any]:
        month = month_start(month or self.today)
        views = self._all_views()
        in_month = [v for v in views if v["invoice_date"] and month_start(v["invoice_date"]) == month]
        sum_itc = lambda rows: sum((v["itc"] for v in rows), ZERO)
        last_closed = month_start(month_start(self.today) - datetime.timedelta(days=1))
        open_claim = [v for v in views if v["claimable"] and v["invoice_date"] <= month_end(last_closed)]
        note_gst = sum((n.cgst + n.sgst + n.igst for n in self.pending_credit_notes(last_closed)), ZERO)
        periods = []
        cursor = month_start(self.today)
        for _ in range(6):
            claimed = [v for v in views if v["claim_period"] == cursor]
            periods.append({"period": cursor, "label": cursor.strftime("%b %Y"), "claimed": sum_itc(claimed),
                            "invoices": len(claimed), "due_date": gstr3b_due(cursor)})
            cursor = month_start(cursor - datetime.timedelta(days=1))
        return {
            "as_of": self.today, "month": month,
            "summary": {
                "itc_in_month": sum_itc([v for v in in_month if v["itc_eligibility"] == ELIGIBLE]),
                "claimable_now": sum_itc(open_claim) - note_gst, "claimable_count": len(open_claim),
                "credit_note_gst": note_gst,
                "claim_period": last_closed, "claim_due": gstr3b_due(last_closed),
                "irn_missing": sum(1 for v in views if v["irn_status"] == IRN_MISSING and v["itc_status"] == ITC_PENDING),
                "review": sum(1 for v in views if v["itc_eligibility"] == REVIEW),
                "blocked_itc": sum_itc([v for v in views if v["itc_eligibility"] == BLOCKED]),
                "at_risk": sum(1 for v in views if v["risk"] == "AT_RISK"),
                "reversal_due": sum(1 for v in views if v["risk"] == "REVERSAL_DUE"),
                "reclaim": sum(1 for v in views if v["risk"] == "RECLAIM"),
                "gstr2b": "CHECKED" if self._gstr2b()[2] else "NOT_CHECKED",
                "gstr2b_period": self._gstr2b()[2],
                "gstr2b_held": sum(1 for v in views if v["itc_status"] == ITC_PENDING and v["gstr2b"] in ("MISMATCH", "MISSING")
                                   and v["invoice_status"] in CLAIMABLE_INVOICE_STATUSES),
            },
            "invoices": in_month,
            "attention": [v for v in views if v["risk"] or v["irn_status"] == IRN_MISSING or v["itc_eligibility"] == REVIEW][:50],
            "periods": periods,
        }

    def attention(self) -> Dict[str, Any]:
        data = self.register()
        s = data["summary"]
        return {"summary": s, "claim_due": s["claim_due"], "claim_period": s["claim_period"]}
