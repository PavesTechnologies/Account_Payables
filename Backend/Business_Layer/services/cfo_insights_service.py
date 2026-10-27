# Backend/Business_Layer/services/cfo_insights_service.py
"""What a CFO asks of AP beyond today's balances - read-only, nothing stored.

  dpo        Days Payable Outstanding = what we owe vendors / what they invoiced over the last 90 days x 90.
             How long, on average, the company holds cash before paying its vendors - with the same figure
             90 days ago and a target band (system configuration AP_DPO_TARGET_MIN / _MAX, default 30-45 days).
  controls   Control exceptions in the last 30 days, from the audit trail and live data: vendor bank details
             added or changed, payments made soon after a bank change, bank accounts not yet verified,
             possible duplicate invoices, invoices approved automatically, payment terms overridden by Finance,
             approval / automation rules changed, payments without a bank receipt.
  accruals   Month-end: costs the company has incurred but that are not yet approved payables -
             goods / services received against a PO but not invoiced, invoices received but not yet approved,
             and rent / subscriptions due for the month whose invoice has not arrived.
"""
from __future__ import annotations

import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
DPO_WINDOW_DAYS = 90
CONTROL_WINDOW_DAYS = 30
BANK_CHANGE_ALERT_DAYS = 7
REJECTED = ("REJECTED",)
IN_PROGRESS = ("OCR_REVIEW_PENDING", "OCR_FAILED", "OCR_REVIEWED", "PENDING_APPROVAL", "RETURNED_FOR_REVIEW")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS, ROUND_HALF_UP)


def month_end(day: datetime.date) -> datetime.date:
    return (day.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)


class CfoInsightsService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.today = today or datetime.date.today()

    # ------------------------------------------------------------------ DPO
    def _target(self):
        from Backend.Business_Layer.utils.vendor_auto_onboarding import get_numeric_system_config
        low = get_numeric_system_config(self.db, "AP_DPO_TARGET_MIN", Decimal("30"))
        high = get_numeric_system_config(self.db, "AP_DPO_TARGET_MAX", Decimal("45"))
        return int(low if low is not None else 30), int(high if high is not None else 45)

    def _ledger(self):
        """(invoice rows: id, invoice date, payable to vendor) and (cleared payments: invoice id, date, amount)."""
        from Backend.Business_Layer.services.ap_reporting_service import APReportingService
        from Backend.Data_Access_Layer.models.master import StatusMaster
        from Backend.Data_Access_Layer.models.payment import Payment, PaymentInvoice
        figures = [f for f in APReportingService(self.db, today=self.today).invoice_figures()
                   if f.status_code not in REJECTED and f.invoice_date]
        payments = self.db.execute(
            select(PaymentInvoice.invoice_id, Payment.payment_date, PaymentInvoice.allocated_amount)
            .join(Payment, Payment.payment_id == PaymentInvoice.payment_id)
            .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
            .where(StatusMaster.status_code == "CLEARED", Payment.payment_date.is_not(None))).all()
        return figures, payments

    @staticmethod
    def _dpo_at(day: datetime.date, figures, payments) -> Optional[float]:
        start = day - datetime.timedelta(days=DPO_WINDOW_DAYS)
        booked = {f.invoice_id: f.net_payable for f in figures if f.invoice_date <= day}
        paid = sum((_money(a) for i, d, a in payments if i in booked and d <= day), ZERO)
        owed = sum(booked.values(), ZERO) - paid
        purchases = sum((f.net_payable for f in figures if start < f.invoice_date <= day), ZERO)
        if purchases <= 0:
            return None
        return round(float(max(owed, ZERO) / purchases * DPO_WINDOW_DAYS), 1)

    def dpo(self) -> Dict[str, Any]:
        figures, payments = self._ledger()
        now = self._dpo_at(self.today, figures, payments)
        before = self._dpo_at(self.today - datetime.timedelta(days=DPO_WINDOW_DAYS), figures, payments)
        low, high = self._target()
        band = None if now is None else "low" if now < low else "high" if now > high else "within"
        return {"value": now, "previous": before, "target_min": low, "target_max": high, "band": band,
                "change": None if now is None or before is None else round(now - before, 1)}

    # ------------------------------------------------------------------ controls
    def _audit_count(self, table: str, actions, since: datetime.datetime, distinct_record: bool = True) -> int:
        from Backend.Data_Access_Layer.models.audit import AuditLog
        column = func.count(func.distinct(AuditLog.record_id)) if distinct_record else func.count()
        return int(self.db.execute(select(column).where(AuditLog.table_name == table, AuditLog.action.in_(list(actions)),
                                                        AuditLog.changed_at >= since)).scalar() or 0)

    def _bank_changes(self, since: datetime.datetime):
        from Backend.Data_Access_Layer.models.audit import AuditLog
        from Backend.Data_Access_Layer.models.vendor import VendorBank
        rows = self.db.execute(select(VendorBank.vendor_id, AuditLog.changed_at)
                               .join(VendorBank, VendorBank.vendor_bank_id == AuditLog.record_id)
                               .where(AuditLog.table_name == "vendor_bank", AuditLog.action.in_(("CREATE", "UPDATE")),
                                      AuditLog.changed_at >= since - datetime.timedelta(days=BANK_CHANGE_ALERT_DAYS))).all()
        return rows

    def _paid_after_bank_change(self, since: datetime.datetime) -> int:
        from Backend.Data_Access_Layer.models.master import StatusMaster
        from Backend.Data_Access_Layer.models.payment import Payment
        changes = self._bank_changes(since)
        if not changes:
            return 0
        payments = self.db.execute(select(Payment.payment_id, Payment.vendor_id, Payment.payment_date)
                                   .join(StatusMaster, StatusMaster.status_id == Payment.status_id)
                                   .where(StatusMaster.status_code == "CLEARED", Payment.payment_date >= since.date())).all()
        flagged = set()
        for pid, vendor_id, paid_on in payments:
            for v, changed_at in changes:
                changed_on = changed_at.date() if hasattr(changed_at, "date") else changed_at
                if v == vendor_id and changed_on <= paid_on <= changed_on + datetime.timedelta(days=BANK_CHANGE_ALERT_DAYS):
                    flagged.add(pid)
        return len(flagged)

    def _unverified_banks(self) -> int:
        from Backend.Business_Layer.services.vendor_bank_verification_service import VendorBankVerificationService
        from Backend.Data_Access_Layer.models.vendor import VendorBank
        ids = [b for (b,) in self.db.execute(select(VendorBank.vendor_bank_id).where(
            (VendorBank.effective_to.is_(None)) | (VendorBank.effective_to >= self.today)))]
        svc = VendorBankVerificationService(self.db)
        return sum(1 for b in ids if not svc.is_payable(b))

    def _possible_duplicates(self) -> int:
        from Backend.Business_Layer.services.invoice_review_automation_service import possible_duplicates
        from Backend.Data_Access_Layer.models.invoice import Invoice
        from Backend.Data_Access_Layer.models.master import StatusMaster
        rows = self.db.execute(select(Invoice, StatusMaster.status_code)
                               .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)).all()
        live = [i for i, status in rows if status not in REJECTED]
        open_ = [i for i, status in rows if status not in REJECTED + ("PAID",)]
        others = [(i.invoice_id, i.vendor_id, i.invoice_number, i.net_amount, i.invoice_date) for i in live]
        return len(possible_duplicates(open_, others))

    def controls(self, receipts_missing: Optional[int] = None) -> List[Dict[str, Any]]:
        since = datetime.datetime.combine(self.today - datetime.timedelta(days=CONTROL_WINDOW_DAYS), datetime.time())
        safe = lambda fn, *a: self._safe(fn, *a)
        items = [
            {"key": "paid_after_bank_change", "severity": "high",
             "label": f"Payments made within {BANK_CHANGE_ALERT_DAYS} days of a vendor bank change",
             "count": safe(self._paid_after_bank_change, since),
             "why": "The most common payment fraud is a fake 'we changed our bank account' request. Confirm each with the vendor by phone.",
             "link": "/accounts-payable/payments/history"},
            {"key": "bank_changes", "severity": "medium", "label": "Vendor bank accounts added or changed",
             "count": safe(self._audit_count, "vendor_bank", ("CREATE", "UPDATE"), since),
             "why": "Every change must be verified and approved by a second person before it is paid.",
             "link": "/accounts-payable/vendors"},
            {"key": "unverified_banks", "severity": "medium", "label": "Vendor bank accounts not yet verified",
             "count": safe(self._unverified_banks),
             "why": "Pay only into accounts that were verified (penny drop or document) and approved.",
             "link": "/accounts-payable/vendors"},
            {"key": "duplicates", "severity": "medium", "label": "Open invoices that look like duplicates",
             "count": safe(self._possible_duplicates),
             "why": "Same vendor with the same invoice number, or the same amount within 7 days - check before paying twice.",
             "link": "/accounts-payable/invoices/review-workbench"},
            {"key": "terms_overridden", "severity": "low", "label": "Payment terms overridden by Finance",
             "count": safe(self._audit_count, "invoice", ("INVOICE_PAYMENT_TERMS_VERIFIED",), since),
             "why": "The invoice terms differed from the contract / PO and Finance accepted them with a remark.",
             "link": "/accounts-payable/reports?report=payment_term_exceptions"},
            {"key": "auto_approved", "severity": "info", "label": "Invoices approved automatically (no person)",
             "count": safe(self._audit_count, "invoice", ("INVOICE_AUTO_APPROVED",), since),
             "why": "PO invoices matched to the PO and goods receipt under the auto-approval limit - by design, but worth a sample check.",
             "link": "/accounts-payable/automation"},
            {"key": "rules_changed", "severity": "low", "label": "Approval / automation rules changed",
             "count": safe(self._audit_count, "system_configuration", ("AP_AUTOMATION_SETTINGS_CHANGED", "SOD_RULES_CHANGED"), since, False),
             "why": "Changes to who approves what, auto-approval limits or duty separation.",
             "link": "/accounts-payable/automation"},
        ]
        if receipts_missing is not None:
            items.append({"key": "receipts", "severity": "low", "label": "Payments without a bank receipt (90 days)",
                          "count": receipts_missing, "why": "Every payment should have its bank receipt attached as proof.",
                          "link": "/accounts-payable/payments/history"})
        return items

    def _safe(self, fn, *args) -> Optional[int]:
        try:
            return fn(*args)
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    # ------------------------------------------------------------------ month-end accruals
    def received_not_invoiced(self, as_of: datetime.date) -> List[Dict[str, Any]]:
        """PO lines with more received (goods receipts up to the date) than invoiced, at the PO price incl. tax."""
        from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceLine
        from Backend.Data_Access_Layer.models.master import StatusMaster
        from Backend.Data_Access_Layer.models.purchase_order import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
        from Backend.Data_Access_Layer.models.vendor import Vendor
        received = dict(self.db.execute(
            select(GoodsReceiptLine.po_line_id, func.sum(GoodsReceiptLine.received_quantity))
            .join(GoodsReceipt, GoodsReceipt.grn_id == GoodsReceiptLine.grn_id)
            .where(GoodsReceiptLine.po_line_id.is_not(None),
                   func.coalesce(GoodsReceipt.receipt_date, func.date(GoodsReceipt.created_at)) <= as_of)
            .group_by(GoodsReceiptLine.po_line_id)).all())
        if not received:
            return []
        invoiced = dict(self.db.execute(
            select(InvoiceLine.po_line_id, func.sum(InvoiceLine.quantity))
            .join(Invoice, Invoice.invoice_id == InvoiceLine.invoice_id)
            .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .where(InvoiceLine.po_line_id.in_(list(received)), StatusMaster.status_code.not_in(REJECTED),
                   Invoice.invoice_date <= as_of)
            .group_by(InvoiceLine.po_line_id)).all())
        lines = self.db.execute(select(PurchaseOrderLine, PurchaseOrder.po_number, Vendor.vendor_name)
                                .join(PurchaseOrder, PurchaseOrder.po_id == PurchaseOrderLine.po_id)
                                .join(Vendor, Vendor.vendor_id == PurchaseOrder.vendor_id, isouter=True)
                                .where(PurchaseOrderLine.po_line_id.in_(list(received)))).all()
        out = []
        for line, po_number, vendor_name in lines:
            pending = Decimal(str(received.get(line.po_line_id) or 0)) - Decimal(str(invoiced.get(line.po_line_id) or 0))
            if pending <= 0:
                continue
            value = _money(pending * _money(line.unit_price) * (1 + Decimal(str(line.tax_rate or 0)) / 100))
            out.append({"kind": "RECEIVED_NOT_INVOICED", "reference": po_number, "vendor_name": vendor_name,
                        "description": f"{line.item_name} - {pending.normalize():f} received, not invoiced", "amount": value})
        return out

    def accruals(self, as_of: Optional[datetime.date] = None) -> Dict[str, Any]:
        from Backend.Business_Layer.services.ap_reporting_service import APReportingService
        from Backend.Business_Layer.services.cash_forecast_service import CashForecastService
        as_of = as_of or month_end(self.today)
        groups: List[Dict[str, Any]] = []
        grni = self._safe_list(self.received_not_invoiced, as_of)
        groups.append({"key": "received_not_invoiced", "label": "Goods / services received, not yet invoiced",
                       "why": "Delivered against a PO (goods receipt recorded) but the vendor's invoice has not arrived.",
                       "items": grni})
        figures = APReportingService(self.db, today=self.today).invoice_figures(IN_PROGRESS)
        pending = [{"kind": "NOT_APPROVED", "reference": f.invoice_number, "vendor_name": f.vendor_name,
                    "description": f"Invoice dated {f.invoice_date:%d %b %Y} - {f.status_name or f.status_code}", "amount": _money(f.net_amount),
                    "invoice_id": f.invoice_id}
                   for f in figures if f.invoice_date and f.invoice_date <= as_of]
        groups.append({"key": "not_approved", "label": "Invoices received, not yet approved",
                       "why": "Already received from the vendor but still in review or approval - the cost belongs to this month.",
                       "items": pending})
        month_start = as_of.replace(day=1)
        recurring = [r for r in self._safe_list(CashForecastService(self.db, today=self.today).recurring, as_of)
                     if r["period_start"] <= month_start]
        groups.append({"key": "recurring_missing", "label": "Rent / subscriptions for the month not yet invoiced",
                       "why": "A recurring schedule expects an invoice for the month that has not arrived - estimated at the usual amount.",
                       "items": [{"kind": "RECURRING", "reference": r["name"], "vendor_name": r["vendor_name"],
                                  "description": f"{r['period_start']:%b %Y} - estimated", "amount": r["amount"]} for r in recurring]})
        for g in groups:
            g["count"], g["amount"] = len(g["items"]), sum((i["amount"] for i in g["items"]), ZERO)
        return {"as_of": as_of, "groups": groups, "total": sum((g["amount"] for g in groups), ZERO)}

    def _safe_list(self, fn, *args) -> list:
        try:
            return fn(*args)
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return []
