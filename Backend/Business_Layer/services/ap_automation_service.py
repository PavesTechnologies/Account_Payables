# Backend/Business_Layer/services/ap_automation_service.py
"""Touchless PO invoices (APM_AUTOMATION_PLAN.md Step B) - "manage by exception".

For a bulk / email PO invoice waiting for review, when AP_AUTOMATION_ENABLED is on:

1. Link: the extracted PO number -> the vendor's OPEN purchase order (exact match ignoring case /
   spaces / dashes; never a guess), and each invoice line -> a PO line (only confident matches).
2. Controls - every one must pass:
     validation passed on upload · no open invoice issues · 2-way / 3-way match within the
     configured tolerances · a goods receipt when GRN is required · no line billed beyond what was
     ordered / received across all invoices of the PO · an approval policy matches.
3. Pass -> the existing operations, in the existing order, as the "AP_AUTOMATION" actor:
     apply_ocr_review -> TDS determination -> send_for_approval, then - only when the net amount is
     at or below AP_AUTO_APPROVE_MAX_AMOUNT (INR, 0 = never) - InvoiceApprovalService.auto_approve.
   Finance still verifies TDS before the invoice can be marked ready for payment.
4. Any failure -> the invoice stays in the review queue; the reasons are recorded and shown.

Every outcome is written to audit_log (action AP_AUTOMATION_RESULT), which also feeds the
touchless-rate figures. Nothing here ever raises into the caller.
"""
import datetime
import difflib
import logging
import re
from collections import Counter
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from Backend.API_Layer.interface.invoice_process_interface import InvoiceOCRReviewRequest
from Backend.API_Layer.interface.matching_interface import LineMatchStatus, MatchType, OverallMatchStatus
from Backend.Business_Layer.services import invoice_process_service
from Backend.Business_Layer.services.ap_automation_settings_service import APAutomationSettingsService, AutomationSettings
from Backend.Business_Layer.services.approval_policy_service import ApprovalPolicyService
from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService
from Backend.Business_Layer.services.invoice_review_automation_service import auto_determine_tds
from Backend.Business_Layer.services.matching_service import MatchingService
from Backend.Data_Access_Layer.dao.ap_automation_dao import RESULT_ACTION, APAutomationDAO
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.dao.review_workbench_dao import ReviewWorkbenchDAO
from Backend.Data_Access_Layer.models.audit import AuditLog

logger = logging.getLogger(__name__)

ACTOR = "AP_AUTOMATION"
BASE_CURRENCY = "INR"

AUTO_APPROVED = "AUTO_APPROVED"
AUTO_SENT = "AUTO_SENT"
REVIEWED_NOT_SENT = "REVIEWED_NOT_SENT"
EXCEPTION = "EXCEPTION"
TOUCHLESS = (AUTO_APPROVED, AUTO_SENT)

_LINE_MATCH_MIN_SIMILARITY = 0.6


# ======================================================================
# Pure helpers (unit-tested)
# ======================================================================
def _norm(text: Optional[str]) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def link_lines(invoice_lines: Sequence[Any], po_lines: Sequence[Any]) -> Dict[int, int]:
    """invoice_line_id -> po_line_id for confident pairs only. One PO line and one invoice line
    pair directly; otherwise by description similarity (one-to-one, best first)."""
    if not invoice_lines or not po_lines:
        return {}
    if len(invoice_lines) == 1 and len(po_lines) == 1:
        return {invoice_lines[0].invoice_line_id: po_lines[0].po_line_id}
    scored = []
    for inv in invoice_lines:
        for po in po_lines:
            candidates = [_norm(po.item_name), _norm(f"{po.item_name} {po.description or ''}")]
            similarity = max(difflib.SequenceMatcher(None, _norm(inv.description), c).ratio() for c in candidates)
            same_price = po.unit_price is not None and inv.unit_price is not None and Decimal(inv.unit_price) == Decimal(po.unit_price)
            scored.append((similarity + (0.1 if same_price else 0), similarity, inv.invoice_line_id, po.po_line_id))
    links: Dict[int, int] = {}
    used = set()
    for _score, similarity, inv_id, po_id in sorted(scored, reverse=True):
        if similarity < _LINE_MATCH_MIN_SIMILARITY or inv_id in links or po_id in used:
            continue
        links[inv_id] = po_id
        used.add(po_id)
    return links


def describe_line(line) -> str:
    n = line.line_number
    status = line.status
    if status == LineMatchStatus.NO_PO_LINE_LINKED:
        return f"Line {n}: not matched to any PO line"
    if status == LineMatchStatus.NO_GRN_RECEIPT_FOUND:
        return f"Line {n}: nothing received for this PO line yet (no GRN)"
    parts = []
    if status in (LineMatchStatus.PRICE_VARIANCE, LineMatchStatus.QUANTITY_AND_PRICE_VARIANCE):
        po_price = Decimal(line.po_unit_price or 0)
        pct = (Decimal(line.price_variance) / po_price * 100) if po_price else None
        parts.append(f"unit price {Decimal(line.invoice_unit_price):,.2f} vs PO {po_price:,.2f}"
                     + (f" ({pct:+.1f}%)" if pct is not None else ""))
    if status in (LineMatchStatus.QUANTITY_VARIANCE, LineMatchStatus.QUANTITY_AND_PRICE_VARIANCE):
        baseline = line.received_quantity if line.received_quantity is not None else line.ordered_quantity
        label = "received" if line.received_quantity is not None else "ordered"
        parts.append(f"quantity {Decimal(line.invoiced_quantity):g} vs {label} {Decimal(baseline or 0):g}")
    return f"Line {n}: " + "; ".join(parts) if parts else f"Line {n}: {status}"


_CATEGORIES = (
    ("double billing", "Possible double billing"),
    ("unit price", "Price variance"),
    ("quantity", "Quantity variance"),
    ("goods receipt", "No goods receipt (GRN)"),
    ("nothing received", "No goods receipt (GRN)"),
    ("not matched to any po line", "Lines not matched to the PO"),
    ("could not be matched", "Lines not matched to the PO"),
    ("po number", "PO number not found"),
    ("validation", "Validation issues"),
    ("open invoice issues", "Open invoice issues"),
    ("approval policy", "No approval policy"),
)


def exception_category(reason: str) -> str:
    lowered = (reason or "").lower()
    return next((label for needle, label in _CATEGORIES if needle in lowered), (reason or "Other")[:60])


def evaluate_match(match, settings: AutomationSettings) -> List[str]:
    """Reasons the match blocks touchless processing ([] = passes)."""
    reasons: List[str] = []
    if match.overall_status == OverallMatchStatus.NO_PO:
        return ["No purchase order linked"]
    if settings.require_grn and match.match_type != MatchType.THREE_WAY:
        reasons.append("No goods receipt (GRN) recorded for this PO yet")
    if match.overall_status == OverallMatchStatus.GRN_REQUIRED_BUT_MISSING and not reasons:
        reasons.append("No goods receipt (GRN) recorded for this PO yet")
    if match.overall_status == OverallMatchStatus.INCOMPLETE:
        reasons.append(match.messages[0] if match.messages else "Invoice lines could not be matched to PO lines")
    reasons.extend(describe_line(l) for l in match.lines if l.status != LineMatchStatus.MATCHED)
    return list(dict.fromkeys(reasons))


# ======================================================================
# Service
# ======================================================================
class APAutomationService:
    def __init__(self, db, settings: Optional[AutomationSettings] = None):
        self.db = db
        self.dao = APAutomationDAO(db)
        self.settings = settings or APAutomationSettingsService(db).get()

    def _match(self, invoice_id: int):
        s = self.settings
        return MatchingService(self.db).match_invoice(
            invoice_id, price_tolerance_pct=s.price_tolerance_pct,
            price_tolerance_amount=s.price_tolerance_amount, quantity_tolerance=s.quantity_tolerance)

    def _record(self, invoice_id: int, outcome: str, reasons: List[str], **details) -> Dict[str, Any]:
        values = {"outcome": outcome, "reasons": reasons[:8], **{k: v for k, v in details.items() if v is not None}}
        try:
            self.db.add(AuditLog(table_name="invoice", record_id=invoice_id, action=RESULT_ACTION,
                                 changed_by=ACTOR, new_values=values))
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Could not record automation result for invoice %s", invoice_id)
        return {"invoice_id": invoice_id, **values}

    # ------------------------------------------------------------------
    def run(self, invoice_id: int, extracted_po_number: Optional[str] = None, force: bool = False) -> Optional[Dict[str, Any]]:
        """One invoice. None when automation is off (unless force) or the invoice is not a PO
        invoice waiting for review. Never raises."""
        if not (self.settings.enabled or force):
            return None
        try:
            return self._run(invoice_id, extracted_po_number)
        except Exception as exc:
            self.db.rollback()
            logger.exception("AP automation failed for invoice %s", invoice_id)
            return self._record(invoice_id, EXCEPTION, [f"Automation error: {exc}"])

    def _run(self, invoice_id: int, extracted_po_number: Optional[str]) -> Optional[Dict[str, Any]]:
        invoice_dao = InvoiceDAO(self.db)
        invoice = invoice_dao.get_invoice_by_id(invoice_id)
        if invoice is None or invoice.invoice_type != "PO":
            return None
        status = invoice_dao.get_status_details(invoice.status_id) if invoice.status_id else None
        if (status.status_code if status else None) != "OCR_REVIEW_PENDING":
            return None
        item = self.dao.upload_item_for_invoice(invoice_id)
        if extracted_po_number is None and item is not None:
            extracted_po_number = ((item.extracted_data or {}).get("reference") or {}).get("po_number")

        # 1. link PO and lines
        po_number = None
        if invoice.po_id is None:
            po = self.dao.find_open_po(invoice.vendor_id, extracted_po_number) if extracted_po_number else None
            if po is None:
                reason = (f"PO number '{extracted_po_number}' does not match an open purchase order of this vendor"
                          if extracted_po_number else "No PO number was read from the invoice")
                return self._record(invoice_id, EXCEPTION, [reason], po_number=extracted_po_number)
            invoice.po_id = po.po_id
            po_number = po.po_number
        else:
            po = None
        po_lines = list((po or invoice.po).purchase_order_line) if (po or invoice.po) else []
        po_number = po_number or (invoice.po.po_number if invoice.po else None)
        lines = self.dao.lines(invoice_id)
        unlinked = [l for l in lines if l.po_line_id is None]
        taken = {l.po_line_id for l in lines if l.po_line_id is not None}
        for inv_line_id, po_line_id in link_lines(unlinked, [p for p in po_lines if p.po_line_id not in taken]).items():
            next(l for l in unlinked if l.invoice_line_id == inv_line_id).po_line_id = po_line_id
        self.db.commit()

        # 2. controls
        reasons: List[str] = []
        validation = (item.validation_result or {}) if item is not None else None
        if validation is None:
            reasons.append("No automatic validation on record")
        elif not validation.get("is_valid"):
            reasons.append("Validation issues: " + ((validation.get("issues") or ["see invoice"])[0]))
        if invoice_dao.get_open_invoice_issues(invoice_id):
            reasons.append("Open invoice issues to resolve")
        match = self._match(invoice_id)
        reasons.extend(evaluate_match(match, self.settings))
        reasons.extend(self._overbilling(invoice_id, match))
        coding = ReviewWorkbenchDAO(self.db).po_coding([invoice.po_id]).get(invoice.po_id, (None, None, None))
        if coding[0] and coding[1]:
            try:
                ApprovalPolicyService(self.db).match_policy(coding[0], coding[1], Decimal(invoice.net_amount or 0))
            except ValueError as exc:
                reasons.append(str(exc))
        else:
            reasons.append("The PO's requisition has no department / category")
        details = {"po_number": po_number, "match_type": getattr(match.match_type, "value", str(match.match_type))}
        if reasons:
            return self._record(invoice_id, EXCEPTION, reasons, **details)

        # 3. the existing operations, in the existing order
        inbound_id = invoice.inbound_document_id or ReviewWorkbenchDAO(self.db).inbound_document_ids([invoice_id]).get(invoice_id)
        if not inbound_id:
            return self._record(invoice_id, EXCEPTION, ["No source document linked to this invoice"], **details)
        invoice_process_service.apply_ocr_review(
            inbound_id, InvoiceOCRReviewRequest(invoice_type="PO", po_id=invoice.po_id), self.db, ACTOR)
        tds_problem = auto_determine_tds(self.db, invoice_id, ACTOR)
        if tds_problem:
            return self._record(invoice_id, REVIEWED_NOT_SENT, [tds_problem], **details)
        approvals = InvoiceApprovalService(self.db)
        try:
            approvals.send_for_approval(invoice_id, ACTOR)
        except Exception as exc:
            self.db.rollback()
            return self._record(invoice_id, REVIEWED_NOT_SENT, [str(exc)], **details)

        limit = self.settings.auto_approve_max_amount
        invoice = InvoiceDAO(self.db).get_invoice_by_id(invoice_id)
        currency = getattr(getattr(invoice, "currency", None), "currency_code", BASE_CURRENCY) or BASE_CURRENCY
        amount = Decimal(invoice.net_amount or 0)
        if limit and limit > 0 and currency == BASE_CURRENCY and amount <= limit:
            reason = f"{details['match_type'].replace('_', '-').lower()} match within tolerance, {amount:,.2f} ≤ {limit:,.2f}"
            try:
                approvals.auto_approve(invoice_id, ACTOR, reason)
                return self._record(invoice_id, AUTO_APPROVED, [], **details, amount=str(amount))
            except Exception as exc:
                self.db.rollback()
                logger.exception("Auto-approval failed for invoice %s", invoice_id)
                return self._record(invoice_id, AUTO_SENT, [f"Sent for approval (auto-approval failed: {exc})"], **details)
        note = [] if not limit else [f"Above the auto-approval limit of {limit:,.2f}" if currency == BASE_CURRENCY
                                     else f"Not in {BASE_CURRENCY} - not auto-approved"]
        return self._record(invoice_id, AUTO_SENT, note, **details, amount=str(amount))

    def _overbilling(self, invoice_id: int, match) -> List[str]:
        linked = [l for l in match.lines if l.po_line_id]
        billed = self.dao.invoiced_quantity_elsewhere([l.po_line_id for l in linked], invoice_id)
        reasons = []
        for line in linked:
            baseline = line.received_quantity if line.received_quantity is not None else line.ordered_quantity
            if baseline is None:
                continue
            total = Decimal(billed.get(line.po_line_id, 0) or 0) + Decimal(line.invoiced_quantity or 0)
            if total > Decimal(baseline) + self.settings.quantity_tolerance:
                reasons.append(f"Line {line.line_number}: {total:g} billed in total vs {Decimal(baseline):g} "
                               f"{'received' if line.received_quantity is not None else 'ordered'} (possible double billing)")
        return reasons

    # ------------------------------------------------------------------
    def sweep(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Re-check waiting PO invoices (e.g. after a goods receipt was recorded)."""
        if not self.settings.enabled:
            return []
        out = []
        for invoice_id in self.dao.pending_po_invoices(limit):
            result = self.run(invoice_id)
            if result is not None:
                out.append(result)
        return out

    def stats(self, days: int = 30) -> Dict[str, Any]:
        since = datetime.datetime.now() - datetime.timedelta(days=days)
        latest: Dict[int, dict] = {}
        for invoice_id, values in self.dao.results_since(since):
            latest.setdefault(invoice_id, values or {})
        outcomes = Counter(v.get("outcome") for v in latest.values())
        reasons = Counter()
        for v in latest.values():
            if v.get("outcome") != EXCEPTION:
                continue
            for r in (v.get("reasons") or [])[:1]:
                reasons[exception_category(r)] += 1
        total = len(latest)
        touchless = outcomes[AUTO_SENT] + outcomes[AUTO_APPROVED]
        return {
            "days": days,
            "processed": total,
            "auto_approved": outcomes[AUTO_APPROVED],
            "auto_sent": outcomes[AUTO_SENT],
            "reviewed_not_sent": outcomes[REVIEWED_NOT_SENT],
            "exceptions": outcomes[EXCEPTION],
            "touchless_rate": round(100 * touchless / total, 1) if total else None,
            "top_exceptions": [{"reason": r, "count": c} for r, c in reasons.most_common(5)],
        }


def run_after_create(db, invoice_id: int, extracted_po_number: Optional[str]) -> None:
    """Bulk / email worker hook, right after create_invoice. Never raises."""
    try:
        APAutomationService(db).run(invoice_id, extracted_po_number)
    except Exception:
        logger.exception("AP automation hook failed for invoice %s", invoice_id)
