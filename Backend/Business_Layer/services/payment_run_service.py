# Backend/Business_Layer/services/payment_run_service.py
"""Payment runs (P3) - pay many approved invoices in one controlled batch.

  candidates   invoices ready to pay (READY_FOR_PAYMENT / PARTIALLY_PAID, outstanding > 0) with what
               blocks each one: no approved bank account (vendor_bank_verification), already in an open
               run, or money already scheduled
  create       DRAFT run (Finance Executive - the maker)
  submit / approve / reject
               approval by someone else (the checker); approving re-checks every invoice and bank account
               and creates one SCHEDULED payment per vendor through PaymentService (amounts reserved)
  bank_file    bulk NEFT / RTGS file for the bank portal (generic CSV, or the HDFC ENET-style layout)
  mark_sent    payments SENT (file uploaded to the bank)
  confirm      per transfer: CLEARED with the bank's UTR (invoice PAID / PARTIALLY_PAID, TDS deduction
               recorded) or FAILED (invoice back to the ready list); run COMPLETED when nothing is pending

Every step is written to audit_log (table payment_run) besides the payments' own audit.
"""
from __future__ import annotations

import csv
import datetime
import io
import logging
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.payment_run import (
    ITEM_FAILED,
    ITEM_PAID,
    ITEM_PENDING,
    RUN_APPROVED,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_DRAFT,
    RUN_OPEN,
    RUN_REJECTED,
    RUN_SENT,
    RUN_SUBMITTED,
    PaymentRun,
    PaymentRunItem,
)
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorBank

logger = logging.getLogger(__name__)

PREPARE_PERMISSIONS = ["PAYMENT_PROCESS"]
APPROVE_PERMISSIONS = ["PAYMENT_RUN_APPROVE", "AP_AUTOMATION_MANAGE"]
VIEW_PERMISSIONS = ["PAYMENT_VIEW", "PAYMENT_PROCESS", "PAYMENT_RUN_APPROVE", "AP_AUTOMATION_MANAGE"]
PAYABLE = ("READY_FOR_PAYMENT", "PARTIALLY_PAID")
RTGS_MIN = Decimal("200000")
FILE_FORMATS = ("GENERIC_CSV", "HDFC_ENET")
CENTS = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS, ROUND_HALF_UP)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def mode_for(amount: Decimal) -> str:
    """RTGS from Rs 2 lakh (RBI minimum), else NEFT."""
    return "RTGS" if amount >= RTGS_MIN else "NEFT"


def run_reference(run_id: int, vendor_id: int) -> str:
    """Customer reference on each transfer - ties the bank's response back to the run and vendor."""
    return f"PR{run_id:05d}V{vendor_id:05d}"


class PaymentRunService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.today = today or datetime.date.today()

    # ------------------------------------------------------------------ helpers
    def _audit(self, run_id: int, action: str, user_id, new: dict, old: Optional[dict] = None):
        self.db.add(AuditLog(table_name="payment_run", record_id=run_id, action=action, changed_by=str(user_id),
                             old_values=old, new_values=new))

    def _require(self, run_id: int, statuses: Optional[Iterable[str]] = None) -> PaymentRun:
        run = self.db.get(PaymentRun, run_id)
        if run is None:
            raise LookupError(f"Payment run {run_id} not found")
        if statuses is not None and run.status not in statuses:
            raise ValueError(f"This run is {run.status.lower()} - that step is not possible now")
        return run

    def _items(self, run_id: int) -> List[PaymentRunItem]:
        return self.db.execute(select(PaymentRunItem).where(PaymentRunItem.run_id == run_id)
                               .order_by(PaymentRunItem.vendor_id, PaymentRunItem.invoice_id)).scalars().all()

    def _primary_bank(self, vendor_id: int) -> Optional[VendorBank]:
        return self.db.execute(select(VendorBank).where(
            VendorBank.vendor_id == vendor_id, VendorBank.is_primary.is_(True), VendorBank.effective_to.is_(None))).scalars().first()

    def _bank_payable(self, bank: Optional[VendorBank]) -> bool:
        from Backend.Business_Layer.services.vendor_bank_verification_service import VendorBankVerificationService
        return bank is not None and VendorBankVerificationService(self.db).is_payable(bank.vendor_bank_id)

    def _in_open_runs(self, invoice_ids: Sequence[int], exclude_run: Optional[int] = None) -> Dict[int, int]:
        stmt = select(PaymentRunItem.invoice_id, PaymentRunItem.run_id).join(
            PaymentRun, PaymentRun.run_id == PaymentRunItem.run_id).where(
            PaymentRunItem.invoice_id.in_(list(invoice_ids)), PaymentRun.status.in_(RUN_OPEN),
            PaymentRunItem.status == ITEM_PENDING)
        if exclude_run:
            stmt = stmt.where(PaymentRun.run_id != exclude_run)
        return dict(self.db.execute(stmt).all())

    def _figures(self, invoice_ids: Optional[Sequence[int]] = None):
        from Backend.Business_Layer.services.ap_reporting_service import APReportingService
        figures = APReportingService(self.db, today=self.today).invoice_figures(PAYABLE)
        if invoice_ids is not None:
            wanted = set(invoice_ids)
            figures = [f for f in figures if f.invoice_id in wanted]
        return {f.invoice_id: f for f in figures}

    # ------------------------------------------------------------------ candidates / create
    def candidates(self, due_by: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
        figures = self._figures()
        in_runs = self._in_open_runs(list(figures))
        banks: Dict[int, Optional[VendorBank]] = {}
        out = []
        for f in figures.values():
            if f.outstanding <= 0:
                continue
            if due_by and f.due_date and f.due_date > due_by:
                continue
            if f.vendor_id not in banks:
                banks[f.vendor_id] = self._primary_bank(f.vendor_id)
            bank = banks[f.vendor_id]
            blocked = None
            if f.invoice_id in in_runs:
                blocked = f"Already in payment run #{in_runs[f.invoice_id]}"
            elif f.reserved > 0:
                blocked = "A payment is already scheduled for this invoice"
            elif bank is None:
                blocked = "No primary bank account for this vendor"
            elif not self._bank_payable(bank):
                blocked = "Vendor bank account not verified and approved"
            elif f.currency_code != "INR":
                blocked = "Only INR invoices can go in a bank payment run"
            out.append({"invoice_id": f.invoice_id, "invoice_number": f.invoice_number, "vendor_id": f.vendor_id,
                        "vendor_name": f.vendor_name, "due_date": f.due_date, "outstanding": f.outstanding,
                        "overdue_days": f.days_overdue(self.today) or 0, "status_code": f.status_code,
                        "bank": ({"vendor_bank_id": bank.vendor_bank_id, "bank_name": bank.bank_name,
                                  "account_last4": (bank.account_number or "")[-4:]} if bank else None),
                        "blocked": blocked})
        out.sort(key=lambda r: (r["blocked"] is not None, r["due_date"] or datetime.date.max))
        return out

    def create(self, name: str, value_date: datetime.date, invoice_ids: Sequence[int], user_id, notes: Optional[str] = None) -> PaymentRun:
        if not (name or "").strip():
            raise ValueError("Give the run a name, e.g. 'Week 42 vendor payments'")
        if value_date < self.today:
            raise ValueError("The value date cannot be in the past")
        if not invoice_ids:
            raise ValueError("Choose at least one invoice")
        chosen = {c["invoice_id"]: c for c in self.candidates() if c["invoice_id"] in set(invoice_ids)}
        problems = [f"{c['invoice_number']}: {c['blocked']}" for c in chosen.values() if c["blocked"]]
        missing = set(invoice_ids) - set(chosen)
        if missing:
            problems.append(f"{len(missing)} invoice(s) are not ready for payment")
        if problems:
            raise ValueError("; ".join(problems[:5]))
        run = PaymentRun(name=name.strip()[:150], value_date=value_date, status=RUN_DRAFT, created_by=str(user_id), notes=notes)
        self.db.add(run)
        self.db.flush()
        for c in chosen.values():
            self.db.add(PaymentRunItem(run_id=run.run_id, invoice_id=c["invoice_id"], vendor_id=c["vendor_id"],
                                       amount=_money(c["outstanding"]), vendor_bank_id=c["bank"]["vendor_bank_id"]))
        total = sum((_money(c["outstanding"]) for c in chosen.values()), Decimal("0"))
        self._audit(run.run_id, "PAYMENT_RUN_CREATED", user_id, {"invoices": len(chosen), "total": str(total),
                                                                  "value_date": value_date.isoformat()})
        self.db.commit()
        return run

    def remove_item(self, run_id: int, invoice_id: int, user_id) -> None:
        self._require(run_id, (RUN_DRAFT,))
        item = self.db.execute(select(PaymentRunItem).where(PaymentRunItem.run_id == run_id,
                                                            PaymentRunItem.invoice_id == invoice_id)).scalar_one_or_none()
        if item is None:
            raise LookupError("That invoice is not in this run")
        self.db.delete(item)
        self._audit(run_id, "PAYMENT_RUN_ITEM_REMOVED", user_id, {"invoice_id": invoice_id})
        self.db.commit()

    # ------------------------------------------------------------------ maker / checker
    def submit(self, run_id: int, user_id) -> PaymentRun:
        run = self._require(run_id, (RUN_DRAFT,))
        if not self._items(run_id):
            raise ValueError("The run has no invoices")
        run.status, run.submitted_by, run.submitted_at, run.updated_at = RUN_SUBMITTED, str(user_id), _now(), _now()
        self._audit(run_id, "PAYMENT_RUN_SUBMITTED", user_id, {"status": RUN_SUBMITTED})
        self.db.commit()
        return run

    def approve(self, run_id: int, user_id, remarks: Optional[str] = None) -> PaymentRun:
        from Backend.API_Layer.interface.payment_interface import PaymentAllocationRequest, PaymentCreateRequest
        from Backend.Business_Layer.services.payment_service import PaymentService
        run = self._require(run_id, (RUN_SUBMITTED,))
        if str(user_id) in {run.created_by, run.submitted_by}:
            raise ValueError("Maker-checker: you prepared this run, so someone else must approve it")
        items = self._items(run_id)
        figures = self._figures([i.invoice_id for i in items])
        clash = self._in_open_runs([i.invoice_id for i in items], exclude_run=run_id)
        problems = []
        for item in items:
            f = figures.get(item.invoice_id)
            if f is None or f.outstanding < item.amount:
                problems.append(f"invoice #{item.invoice_id} is no longer payable for {item.amount:,}")
            if item.invoice_id in clash:
                problems.append(f"invoice #{item.invoice_id} is also in run #{clash[item.invoice_id]}")
            bank = self.db.get(VendorBank, item.vendor_bank_id) if item.vendor_bank_id else None
            if not self._bank_payable(bank) or bank.effective_to is not None:
                problems.append(f"the bank account for invoice #{item.invoice_id} is no longer approved")
        if problems:
            raise ValueError("Cannot approve: " + "; ".join(problems[:5]))

        by_vendor: "OrderedDict[int, List[PaymentRunItem]]" = OrderedDict()
        for item in items:
            by_vendor.setdefault(item.vendor_id, []).append(item)
        payments = PaymentService(self.db)
        for vendor_id, group in by_vendor.items():
            total = sum((i.amount for i in group), Decimal("0"))
            payment = payments.create_payment(PaymentCreateRequest(
                vendor_id=vendor_id, scheduled_date=run.value_date, currency_id=1, payment_method=mode_for(total),
                vendor_bank_id=group[0].vendor_bank_id, reference_number=run_reference(run_id, vendor_id),
                allocations=[PaymentAllocationRequest(invoice_id=i.invoice_id, allocated_amount=i.amount) for i in group]),
                str(user_id))
            for i in group:
                i.payment_id = payment.payment_id
        run.status, run.approved_by, run.approved_at = RUN_APPROVED, str(user_id), _now()
        run.decision_remarks, run.updated_at = (remarks or "").strip()[:500] or None, _now()
        self._audit(run_id, "PAYMENT_RUN_APPROVED", user_id, {"payments": len(by_vendor), "remarks": run.decision_remarks})
        self.db.commit()
        return run

    def reject(self, run_id: int, remarks: str, user_id) -> PaymentRun:
        run = self._require(run_id, (RUN_SUBMITTED,))
        if len((remarks or "").strip()) < 5:
            raise ValueError("Give the reason (at least 5 characters)")
        run.status, run.approved_by, run.approved_at = RUN_REJECTED, str(user_id), _now()
        run.decision_remarks, run.updated_at = remarks.strip()[:500], _now()
        self._audit(run_id, "PAYMENT_RUN_REJECTED", user_id, {"remarks": run.decision_remarks})
        self.db.commit()
        return run

    def cancel(self, run_id: int, user_id) -> PaymentRun:
        run = self._require(run_id, (RUN_DRAFT, RUN_SUBMITTED))
        run.status, run.updated_at = RUN_CANCELLED, _now()
        self._audit(run_id, "PAYMENT_RUN_CANCELLED", user_id, {})
        self.db.commit()
        return run

    # ------------------------------------------------------------------ bank file
    def transfers(self, run_id: int) -> List[Dict[str, Any]]:
        """One transfer per vendor: amount, beneficiary account, mode, reference."""
        items = self._items(run_id)
        vendors = dict(self.db.execute(select(Vendor.vendor_id, Vendor.vendor_name)).all())
        numbers = dict(self.db.execute(select(Invoice.invoice_id, Invoice.invoice_number).where(
            Invoice.invoice_id.in_([i.invoice_id for i in items]))).all()) if items else {}
        groups: "OrderedDict[int, List[PaymentRunItem]]" = OrderedDict()
        for item in items:
            groups.setdefault(item.vendor_id, []).append(item)
        out = []
        for vendor_id, group in groups.items():
            bank = self.db.get(VendorBank, group[0].vendor_bank_id) if group[0].vendor_bank_id else None
            amount = sum((i.amount for i in group if i.status != ITEM_FAILED), Decimal("0"))
            statuses = {i.status for i in group}
            out.append({"vendor_id": vendor_id, "vendor_name": vendors.get(vendor_id), "amount": amount,
                        "mode": mode_for(amount), "reference": run_reference(run_id, vendor_id),
                        "payment_id": group[0].payment_id, "utr": group[0].utr,
                        "status": ITEM_PAID if statuses == {ITEM_PAID} else ITEM_FAILED if statuses == {ITEM_FAILED} else ITEM_PENDING,
                        "beneficiary_name": bank.account_holder_name if bank else None,
                        "account_number": bank.account_number if bank else None, "ifsc": bank.ifsc_code if bank else None,
                        "bank_name": bank.bank_name if bank else None,
                        "invoices": [{"invoice_id": i.invoice_id, "invoice_number": numbers.get(i.invoice_id), "amount": i.amount,
                                      "status": i.status} for i in group]})
        return out

    def bank_file(self, run_id: int, file_format: str, user_id) -> tuple:
        run = self._require(run_id, (RUN_APPROVED, RUN_SENT, RUN_COMPLETED))
        file_format = (file_format or "GENERIC_CSV").upper()
        if file_format not in FILE_FORMATS:
            raise ValueError(f"File format must be one of {', '.join(FILE_FORMATS)}")
        transfers = [t for t in self.transfers(run_id) if t["status"] == ITEM_PENDING]
        if not transfers:
            raise ValueError("Nothing left to pay in this run")
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        if file_format == "GENERIC_CSV":
            writer.writerow(["Payment Mode", "Beneficiary Name", "Beneficiary Account Number", "IFSC", "Amount",
                             "Value Date", "Customer Reference", "Remarks"])
            for t in transfers:
                writer.writerow([t["mode"], t["beneficiary_name"], t["account_number"], t["ifsc"], f"{t['amount']:.2f}",
                                 run.value_date.strftime("%d/%m/%Y"), t["reference"],
                                 ("Inv " + ", ".join(i["invoice_number"] or "" for i in t["invoices"]))[:100]])
        else:  # HDFC ENET-style bulk upload layout - confirm the exact column order with the bank before go-live
            for t in transfers:
                writer.writerow(["N" if t["mode"] == "NEFT" else "R", "", t["account_number"], f"{t['amount']:.2f}",
                                 t["beneficiary_name"], "", "", "", "", "", "", "", "", t["reference"], t["reference"],
                                 ("Inv " + ", ".join(i["invoice_number"] or "" for i in t["invoices"]))[:30],
                                 "", "", "", "", "", "", "", run.value_date.strftime("%d/%m/%Y"), "", t["ifsc"],
                                 t["bank_name"], "", ""])
        run.file_format, run.file_generated_at, run.file_generated_by = file_format, _now(), str(user_id)
        self._audit(run_id, "PAYMENT_RUN_FILE_GENERATED", user_id, {"format": file_format, "transfers": len(transfers),
                                                                     "total": str(sum((t["amount"] for t in transfers), Decimal("0")))})
        self.db.commit()
        name = f"payment-run-{run_id:05d}-{file_format.lower()}-{run.value_date:%Y%m%d}.csv"
        return name, buffer.getvalue().encode("utf-8")

    def mark_sent(self, run_id: int, user_id) -> PaymentRun:
        from Backend.Business_Layer.services.payment_service import PaymentService
        run = self._require(run_id, (RUN_APPROVED,))
        if run.file_generated_at is None:
            raise ValueError("Download the bank file first")
        for payment_id in {i.payment_id for i in self._items(run_id) if i.payment_id and i.status == ITEM_PENDING}:
            PaymentService(self.db).update_status(payment_id, "SENT", None, None, str(user_id))
        run.status, run.sent_by, run.sent_at, run.updated_at = RUN_SENT, str(user_id), _now(), _now()
        self._audit(run_id, "PAYMENT_RUN_SENT", user_id, {"status": RUN_SENT})
        self.db.commit()
        return run

    # ------------------------------------------------------------------ bank confirmation
    def confirm(self, run_id: int, results: Sequence[Dict[str, Any]], user_id) -> Dict[str, Any]:
        """results: [{reference | vendor_id, status: PAID | FAILED, utr?, payment_date?, reason?}]"""
        from Backend.Business_Layer.services.payment_service import PaymentService
        run = self._require(run_id, (RUN_SENT,))
        transfers = {t["reference"]: t for t in self.transfers(run_id)}
        by_vendor = {t["vendor_id"]: t for t in transfers.values()}
        items = self._items(run_id)
        done = {"paid": 0, "failed": 0, "skipped": []}
        for r in results:
            t = transfers.get(str(r.get("reference") or "").strip()) or by_vendor.get(r.get("vendor_id"))
            if t is None or t["status"] != ITEM_PENDING:
                done["skipped"].append(r.get("reference") or r.get("vendor_id"))
                continue
            status = str(r.get("status") or "").upper()
            group = [i for i in items if i.vendor_id == t["vendor_id"]]
            if status == "PAID":
                utr = str(r.get("utr") or "").strip()
                if not utr:
                    raise ValueError(f"{t['reference']}: the bank's UTR is required for a paid transfer")
                paid_on = r.get("payment_date") or self.today
                if isinstance(paid_on, str):
                    paid_on = datetime.date.fromisoformat(paid_on)
                PaymentService(self.db).update_status(t["payment_id"], "CLEARED", paid_on, utr, str(user_id))
                for i in group:
                    i.status, i.utr = ITEM_PAID, utr[:50]
                    self._record_tds(i.invoice_id, paid_on, user_id)
                done["paid"] += 1
            elif status == "FAILED":
                PaymentService(self.db).update_status(t["payment_id"], "FAILED", None, None, str(user_id))
                for i in group:
                    i.status, i.failure_reason = ITEM_FAILED, str(r.get("reason") or "Rejected by the bank")[:300]
                done["failed"] += 1
            else:
                raise ValueError(f"{t['reference']}: status must be PAID or FAILED")
        if all(i.status != ITEM_PENDING for i in items):
            run.status, run.completed_at = RUN_COMPLETED, _now()
        run.updated_at = _now()
        self._audit(run_id, "PAYMENT_RUN_CONFIRMED", user_id, {"paid": done["paid"], "failed": done["failed"]})
        self.db.commit()
        return done

    def parse_response(self, content: bytes) -> List[Dict[str, Any]]:
        """A bank response CSV: columns Customer Reference, UTR, Status (Success / Paid / Failed), optional Reason."""
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        out = []
        for row in reader:
            norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            reference = norm.get("customer reference") or norm.get("reference") or norm.get("customer reference number")
            raw = (norm.get("status") or "").lower()
            status = "PAID" if raw in ("paid", "success", "successful", "processed", "credited") else "FAILED" if raw else ""
            if reference and status:
                out.append({"reference": reference, "status": status, "utr": norm.get("utr") or norm.get("utr number"),
                            "reason": norm.get("reason") or norm.get("remarks")})
        if not out:
            raise ValueError("No rows found - the file needs Customer Reference, UTR and Status columns")
        return out

    def _record_tds(self, invoice_id: int, paid_on: datetime.date, user_id) -> None:
        """TDS is deducted when the vendor is paid (first payment)."""
        try:
            from types import SimpleNamespace
            from Backend.Business_Layer.services.tds_tracking_service import TdsTrackingService
            from Backend.Data_Access_Layer.models.tds import InvoiceTds, InvoiceTdsTracking
            tds = self.db.execute(select(InvoiceTds).where(InvoiceTds.invoice_id == invoice_id)).scalar_one_or_none()
            tracking = self.db.execute(select(InvoiceTdsTracking).where(InvoiceTdsTracking.invoice_id == invoice_id)).scalar_one_or_none()
            if tds is None or not tds.tds_applicable or (tracking is not None and tracking.tracking_status != "TDS_PENDING"):
                return
            TdsTrackingService(self.db).record_deduction(invoice_id, SimpleNamespace(
                deduction_date=paid_on, remarks="TDS deducted at payment (payment run)"), str(user_id))
        except Exception:
            logger.exception("TDS deduction not recorded for invoice %s after payment run", invoice_id)

    # ------------------------------------------------------------------ views
    def view(self, run: PaymentRun) -> Dict[str, Any]:
        transfers = self.transfers(run.run_id)
        return {"run_id": run.run_id, "name": run.name, "value_date": run.value_date, "status": run.status,
                "created_by": run.created_by, "created_at": run.created_at, "submitted_by": run.submitted_by,
                "approved_by": run.approved_by, "approved_at": run.approved_at, "decision_remarks": run.decision_remarks,
                "file_format": run.file_format, "file_generated_at": run.file_generated_at, "sent_at": run.sent_at,
                "completed_at": run.completed_at, "notes": run.notes,
                "total": sum((t["amount"] for t in transfers), Decimal("0")),
                "invoice_count": sum(len(t["invoices"]) for t in transfers), "transfer_count": len(transfers),
                "transfers": transfers}

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        stmt = select(PaymentRun).order_by(PaymentRun.run_id.desc())
        if status:
            stmt = stmt.where(PaymentRun.status == status.upper())
        out = []
        for run in self.db.execute(stmt).scalars():
            v = self.view(run)
            v.pop("transfers")
            out.append(v)
        return out

    def detail(self, run_id: int) -> Dict[str, Any]:
        return self.view(self._require(run_id))
