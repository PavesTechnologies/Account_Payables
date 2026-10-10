# Backend/Business_Layer/services/invoice_review_automation_service.py
"""Review workbench (APM_AUTOMATION_PLAN.md Step A): less typing between upload and approval, with
the same rules as reviewing one invoice at a time.

* Coding suggestions for NON_PO invoices: the vendor's primary onboarding mapping
  (vendor_category_mapping) first, then the vendor's last coded NON_PO invoice. PO invoices take
  department / category from the PO's requisition, exactly as apply_ocr_review does.
* Readiness checks per invoice - shown in the UI and re-checked on the server before any bulk
  action (the client's view is never trusted).
* Bulk "review & send": per invoice, the existing operations in the existing order -
  invoice_process_service.apply_ocr_review -> TDSDeterminationService.determine (only when not
  determined yet) -> InvoiceApprovalService.send_for_approval. One invoice failing never affects
  the others; each result says exactly what happened.

Only CLEAN invoices can be bulk-reviewed: a passing validation result on record (bulk / email
uploads keep it) and no open invoice issue. Saving a review resolves the invoice's open issues, so
an invoice with issues must be looked at on its own.
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from Backend.API_Layer.interface.invoice_process_interface import InvoiceOCRReviewRequest
from Backend.Business_Layer.services import invoice_process_service
from Backend.Business_Layer.services.approval_policy_service import ApprovalPolicyService
from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService
from Backend.Business_Layer.services.tds_determination_service import (
    TDSDeterminationService,
    tds_determination_problem,
)
from Backend.Business_Layer.utils import invoice_status
from Backend.Data_Access_Layer.dao.review_workbench_dao import ReviewWorkbenchDAO

logger = logging.getLogger(__name__)

MAX_BULK = 25
STAGE_TO_REVIEW = "to_review"
STAGE_REVIEWED = "reviewed"
_STAGE_STATUSES = {
    STAGE_TO_REVIEW: (invoice_status.STATUS_CODE_OCR_REVIEW_PENDING,),
    STAGE_REVIEWED: (invoice_status.STATUS_CODE_OCR_REVIEWED,),
}

SOURCE_INVOICE = "INVOICE"
SOURCE_PO = "PO"
SOURCE_VENDOR_MAPPING = "VENDOR_MAPPING"
SOURCE_LAST_INVOICE = "LAST_INVOICE"


def _check(key: str, ok: bool, message: str, blocking: bool = True) -> Dict[str, Any]:
    return {"key": key, "ok": ok, "blocking": blocking, "message": message}


def auto_determine_tds(db, invoice_id: int, user_id: str) -> Optional[str]:
    """Runs TDS determination after review when it has not been done yet (a DETERMINED / VERIFIED
    result - possibly corrected by a person - is never overwritten). Returns the reason TDS is
    still not ready, or None when it is. Never raises."""
    service = TDSDeterminationService(db)
    try:
        existing = service.tds_dao.get_invoice_tds_by_invoice_id(invoice_id)
    except Exception:
        existing = None
    if tds_determination_problem(existing) is None:
        return None
    try:
        row = service.determine(invoice_id, user_id)
    except Exception as exc:  # determine() rolls back itself
        logger.info("Automatic TDS determination for invoice %s did not complete: %s", invoice_id, exc)
        return f"TDS needs review: {exc}"
    problem = tds_determination_problem(row)
    return f"TDS needs review: {problem}" if problem else None


class InvoiceReviewAutomationService:
    def __init__(self, db):
        self.db = db
        self.dao = ReviewWorkbenchDAO(db)

    # ------------------------------------------------------------------
    # Workbench rows
    # ------------------------------------------------------------------
    def workbench(self, stage: str, limit: int = 200) -> Dict[str, Any]:
        if stage not in _STAGE_STATUSES:
            raise ValueError("stage must be 'to_review' or 'reviewed'")
        rows = self.dao.invoices_in_status(_STAGE_STATUSES[stage], limit)
        items = self._rows(rows, stage)
        return {
            "stage": stage,
            "items": items,
            "counts": {"total": len(items), "ready": sum(1 for i in items if i["ready"])},
            "max_bulk": MAX_BULK,
        }

    def _rows(self, rows, stage: str) -> List[Dict[str, Any]]:
        invoices = [r[0] for r in rows]
        ids = [i.invoice_id for i in invoices]
        vendor_ids = list({i.vendor_id for i in invoices})
        inbound = self.dao.inbound_document_ids(ids)
        uploads = self.dao.upload_items(ids)
        issues = self.dao.open_issue_counts(ids)
        tds = self.dao.tds_rows(ids)
        mappings = self.dao.vendor_mappings(vendor_ids)
        last = self.dao.last_coded_non_po(vendor_ids, ids)
        po = self.dao.po_coding([i.po_id for i in invoices if i.po_id])
        departments = self.dao.departments()
        categories = self.dao.categories()
        policy = ApprovalPolicyService(self.db)

        out = []
        for invoice, vendor_name, status_code, currency_code in rows:
            coding = self._coding(invoice, mappings, last, po, departments, categories)
            upload = uploads.get(invoice.invoice_id)
            validation = (upload[0] or {}) if upload else None
            checks = []
            if stage == STAGE_TO_REVIEW:
                if validation is None:
                    checks.append(_check("validation", False, "No automatic validation on record - review this invoice on its own"))
                elif not validation.get("is_valid"):
                    first = (validation.get("issues") or ["Validation found issues"])[0]
                    checks.append(_check("validation", False, f"Validation issues: {first}"))
                else:
                    checks.append(_check("validation", True, "Validation passed on upload"))
                open_issues = issues.get(invoice.invoice_id, 0)
                checks.append(_check("issues", open_issues == 0,
                                     "No open issues" if open_issues == 0 else f"{open_issues} open issue(s) to resolve"))
            if invoice.invoice_type == "PO" and not invoice.po_id:
                checks.append(_check("coding", False, "PO number not linked to a purchase order - review on its own"))
            elif coding["department_id"] and coding["purchase_category_id"]:
                checks.append(_check("coding", True, f"{coding['department_name']} / {coding['purchase_category_name']}"))
            else:
                checks.append(_check("coding", False, "Choose department and purchase category"))
            if coding["department_id"] and coding["purchase_category_id"]:
                try:
                    matched = policy.match_policy(coding["department_id"], coding["purchase_category_id"],
                                                  Decimal(invoice.net_amount or 0))
                    checks.append(_check("policy", True, f"Approval policy: {matched.name}"))
                except ValueError as exc:
                    checks.append(_check("policy", False, str(exc)))
            if stage == STAGE_REVIEWED:
                problem = tds_determination_problem(tds.get(invoice.invoice_id))
                checks.append(_check("tds", problem is None, "TDS determined" if problem is None else problem))
            else:
                checks.append(_check("tds", True, "TDS is determined automatically after review", blocking=False))
            if upload and upload[2] == "EMAIL" and upload[3] is False:
                checks.append(_check("sender", False, "Emailed by a sender who is not a known vendor contact", blocking=False))

            out.append({
                "invoice_id": invoice.invoice_id,
                "inbound_document_id": invoice.inbound_document_id or inbound.get(invoice.invoice_id),
                "invoice_number": invoice.invoice_number,
                "vendor_id": invoice.vendor_id,
                "vendor_name": vendor_name,
                "invoice_type": invoice.invoice_type,
                "invoice_date": invoice.invoice_date,
                "net_amount": invoice.net_amount,
                "currency_code": currency_code or "INR",
                "status_code": status_code,
                "created_at": invoice.created_at,
                "source": (upload[2] if upload else "UPLOAD"),
                "batch_id": upload[1] if upload else None,
                **coding,
                "checks": checks,
                "ready": all(c["ok"] for c in checks if c["blocking"]),
            })
        return out

    @staticmethod
    def _valid_pair(dept, cat, departments, categories) -> bool:
        d, c = departments.get(dept), categories.get(cat)
        return bool(d and c and d[1] and c[1] and c[2] == dept)

    def _coding(self, invoice, mappings, last, po, departments, categories) -> Dict[str, Any]:
        dept = cat = None
        source = None
        if invoice.invoice_type == "PO" and invoice.po_id:
            dept, cat, _ = po.get(invoice.po_id, (None, None, None))
            source = SOURCE_PO if dept and cat else None
        elif invoice.department_id and invoice.purchase_category_id:
            dept, cat, source = invoice.department_id, invoice.purchase_category_id, SOURCE_INVOICE
        elif invoice.invoice_type != "PO":
            candidates = mappings.get(invoice.vendor_id, [])
            primary = [m for m in candidates if m[2]] or (candidates if len(candidates) == 1 else [])
            for m in primary:
                if self._valid_pair(m[0], m[1], departments, categories):
                    dept, cat, source = m[0], m[1], SOURCE_VENDOR_MAPPING
                    break
            if source is None and invoice.vendor_id in last:
                d, c = last[invoice.vendor_id]
                if self._valid_pair(d, c, departments, categories):
                    dept, cat, source = d, c, SOURCE_LAST_INVOICE
        return {
            "department_id": dept,
            "department_name": departments.get(dept, (None,))[0] if dept else None,
            "purchase_category_id": cat,
            "purchase_category_name": categories.get(cat, (None,))[0] if cat else None,
            "coding_source": source,
        }

    # ------------------------------------------------------------------
    # Bulk actions
    # ------------------------------------------------------------------
    def _row_for(self, invoice_id: int, stage: str) -> Optional[Dict[str, Any]]:
        rows = self.dao.invoices_in_status(_STAGE_STATUSES[stage], 1, invoice_ids=[invoice_id])
        return self._rows(rows, stage)[0] if rows else None

    def bulk_review(self, items: Sequence[Dict[str, Any]], user_id: str, send: bool) -> List[Dict[str, Any]]:
        if not items:
            raise ValueError("Select at least one invoice.")
        if len(items) > MAX_BULK:
            raise ValueError(f"At most {MAX_BULK} invoices can be processed at once.")
        results = []
        for item in items:
            results.append(self._review_one(item, user_id, send))
        return results

    def _review_one(self, item: Dict[str, Any], user_id: str, send: bool) -> Dict[str, Any]:
        invoice_id = int(item["invoice_id"])
        result = {"invoice_id": invoice_id, "status": "FAILED", "message": None}
        try:
            row = self._row_for(invoice_id, STAGE_TO_REVIEW)
            if row is None:
                result["message"] = "Not waiting for review any more (refresh the list)."
                return result
            result["invoice_number"] = row["invoice_number"]
            dept = item.get("department_id") or row["department_id"]
            cat = item.get("purchase_category_id") or row["purchase_category_id"]
            # Re-check on the server with the chosen coding; anything blocking stops this invoice.
            if row["invoice_type"] != "PO" and (dept, cat) != (row["department_id"], row["purchase_category_id"]):
                row = {**row, "department_id": dept, "purchase_category_id": cat}
                row["checks"] = [c for c in row["checks"] if c["key"] not in ("coding", "policy")]
                if dept and cat:
                    try:
                        ApprovalPolicyService(self.db).match_policy(int(dept), int(cat), Decimal(row["net_amount"] or 0))
                    except ValueError as exc:
                        row["checks"].append(_check("policy", False, str(exc)))
                else:
                    row["checks"].append(_check("coding", False, "Choose department and purchase category"))
            blocking = [c["message"] for c in row["checks"] if c["blocking"] and not c["ok"]]
            if blocking:
                result.update(status="SKIPPED", message=blocking[0])
                return result
            if not row["inbound_document_id"]:
                result.update(status="SKIPPED", message="No source document is linked - review this invoice on its own.")
                return result

            review = InvoiceOCRReviewRequest(invoice_type=row["invoice_type"])
            if row["invoice_type"] != "PO":
                review.department_id, review.purchase_category_id = int(dept), int(cat)
            invoice_process_service.apply_ocr_review(row["inbound_document_id"], review, self.db, user_id)
        except Exception as exc:
            self.db.rollback()
            logger.info("Bulk review of invoice %s failed: %s", invoice_id, exc)
            result["message"] = str(exc) or "The review could not be saved."
            return result

        tds_problem = auto_determine_tds(self.db, invoice_id, user_id)
        if not send:
            result.update(status="REVIEWED", message=tds_problem or "Reviewed - ready to send for approval.")
            return result
        if tds_problem:
            result.update(status="REVIEWED", message=tds_problem)
            return result
        return self._send_one(invoice_id, user_id, result)

    def _send_one(self, invoice_id: int, user_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        try:
            InvoiceApprovalService(self.db).send_for_approval(invoice_id, user_id)
            result.update(status="SENT", message="Sent for approval.")
        except Exception as exc:
            self.db.rollback()
            # The review itself was saved - the invoice stays in Reviewed with the reason.
            result.update(status="REVIEWED", message=str(exc) or "Could not send for approval.")
        return result

    def bulk_send(self, invoice_ids: Sequence[int], user_id: str) -> List[Dict[str, Any]]:
        if not invoice_ids:
            raise ValueError("Select at least one invoice.")
        if len(invoice_ids) > MAX_BULK:
            raise ValueError(f"At most {MAX_BULK} invoices can be sent at once.")
        results = []
        for invoice_id in invoice_ids:
            result = {"invoice_id": int(invoice_id), "status": "FAILED", "message": None}
            row = self._row_for(int(invoice_id), STAGE_REVIEWED)
            if row is None:
                result["message"] = "Not in Reviewed status any more (refresh the list)."
                results.append(result)
                continue
            result["invoice_number"] = row["invoice_number"]
            # TDS first: an invoice reviewed before automatic TDS existed gets it now.
            problem = auto_determine_tds(self.db, int(invoice_id), user_id)
            if problem:
                result.update(status="SKIPPED", message=problem)
                results.append(result)
                continue
            try:
                InvoiceApprovalService(self.db).send_for_approval(int(invoice_id), user_id)
                result.update(status="SENT", message="Sent for approval.")
            except Exception as exc:
                self.db.rollback()
                result.update(status="SKIPPED", message=str(exc) or "Could not send for approval.")
            results.append(result)
        return results
