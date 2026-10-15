# Backend/Business_Layer/services/work_assignment_service.py
"""Work assignment (P3) - who in the AP team works which invoice.

  assign_new        a new / just-reviewed invoice goes to its vendor's (else department's) AP Executive
                    when a rule exists; otherwise it stays unassigned for anyone to claim. Never raises.
  claim             an AP Executive takes unassigned invoices (or ones already theirs)
  reassign          the AP lead moves invoices - one, several, or everything a person holds (leave)
  team / workload   the AP Executives (role AP_EXECUTIVE) with their open work by stage
  owners            invoice -> owner, for the workbench, dashboards and the Action Center

Only invoices still with AP (review / reviewed / returned) can be claimed or moved; the owner is
kept afterwards so "who processed this" stays visible. Every change is written to audit_log.
"""
from __future__ import annotations

import datetime
import logging
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select, text

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.vendor import Vendor
from Backend.Data_Access_Layer.models.work_assignment import (
    SCOPE_DEPARTMENT,
    SCOPE_VENDOR,
    SOURCE_CLAIM,
    SOURCE_REASSIGN,
    SOURCE_RULE,
    InvoiceAssignment,
    WorkAssignmentRule,
)

logger = logging.getLogger(__name__)

TEAM_ROLE = "AP_EXECUTIVE"
LEAD_PERMISSIONS = ["AP_WORK_ASSIGN", "AP_AUTOMATION_MANAGE"]
WORK_PERMISSIONS = ["INVOICE_OCR_REVIEW", "INVOICE_SEND_FOR_APPROVAL", "INVOICE_CREATE"]
VIEW_PERMISSIONS = LEAD_PERMISSIONS + WORK_PERMISSIONS
AP_STAGE = ("OCR_REVIEW_PENDING", "OCR_FAILED", "RETURNED_FOR_REVIEW", "OCR_REVIEWED")
STAGE_LABELS = {"OCR_REVIEW_PENDING": "to_review", "OCR_FAILED": "to_review", "RETURNED_FOR_REVIEW": "returned",
                "OCR_REVIEWED": "reviewed", "PENDING_APPROVAL": "in_approval"}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _safe_rollback(db) -> None:
    try:
        db.rollback()
    except Exception:
        pass


class WorkAssignmentService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------ people
    def names(self, user_ids: Iterable[str]) -> Dict[str, str]:
        """user_id -> display name from the UMS user cache (first + last name only)."""
        ids = sorted({str(u) for u in user_ids if u and str(u).isdigit()})
        if not ids:
            return {}
        rows = self.db.execute(text("""select user_id::text, raw_payload->>'first_name', raw_payload->>'last_name'
                                       from ap.ums_user_cache where user_id = any(cast(:ids as bigint[]))"""),
                               {"ids": [int(i) for i in ids]}).all()
        return {uid: " ".join(p for p in (first, last) if p) or uid for uid, first, last in rows}

    def team(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(text("""
            select distinct u.user_id::text from ap.approver_directory_role r
            join ap.approver_directory d on d.user_uuid = r.user_uuid and d.is_user_active
            join ap.ums_user_cache u on u.user_uuid = r.user_uuid
            where r.role_code = :role and r.is_active order by 1"""), {"role": TEAM_ROLE}).scalars().all()
        names = self.names(rows)
        return [{"user_id": uid, "name": names.get(uid, uid)} for uid in rows]

    def _require_member(self, user_id: str) -> None:
        if str(user_id) not in {m["user_id"] for m in self.team()}:
            raise ValueError("Assign work only to an active AP Executive")

    # ------------------------------------------------------------------ rules
    def rules(self) -> List[Dict[str, Any]]:
        rules = self.db.execute(select(WorkAssignmentRule).where(WorkAssignmentRule.is_active.is_(True))
                                .order_by(WorkAssignmentRule.scope, WorkAssignmentRule.rule_id)).scalars().all()
        names = self.names(r.assignee_user_id for r in rules)
        vendors = dict(self.db.execute(select(Vendor.vendor_id, Vendor.vendor_name)).all())
        departments = dict(self.db.execute(text("select id, name from ap.department")).all())
        return [{"rule_id": r.rule_id, "scope": r.scope, "vendor_id": r.vendor_id, "vendor_name": vendors.get(r.vendor_id),
                 "department_id": r.department_id, "department_name": departments.get(r.department_id),
                 "assignee_user_id": r.assignee_user_id, "assignee_name": names.get(r.assignee_user_id, r.assignee_user_id)}
                for r in rules]

    def set_rule(self, scope: str, target_id: int, assignee_user_id: str, user_id) -> WorkAssignmentRule:
        scope = (scope or "").upper()
        if scope not in (SCOPE_VENDOR, SCOPE_DEPARTMENT):
            raise ValueError("Scope must be VENDOR or DEPARTMENT")
        self._require_member(assignee_user_id)
        column = WorkAssignmentRule.vendor_id if scope == SCOPE_VENDOR else WorkAssignmentRule.department_id
        rule = self.db.execute(select(WorkAssignmentRule).where(
            WorkAssignmentRule.scope == scope, column == target_id, WorkAssignmentRule.is_active.is_(True))).scalar_one_or_none()
        old = rule.assignee_user_id if rule else None
        if rule is None:
            rule = WorkAssignmentRule(scope=scope, created_by=str(user_id),
                                      **({"vendor_id": target_id} if scope == SCOPE_VENDOR else {"department_id": target_id}))
            self.db.add(rule)
        rule.assignee_user_id, rule.updated_by, rule.updated_at = str(assignee_user_id), str(user_id), _now()
        self.db.flush()
        self.db.add(AuditLog(table_name="work_assignment_rule", record_id=rule.rule_id, action="WORK_ASSIGNMENT_RULE_SET",
                             changed_by=str(user_id), old_values={"assignee": old},
                             new_values={"scope": scope, "target_id": target_id, "assignee": str(assignee_user_id)}))
        self.db.commit()
        return rule

    def remove_rule(self, rule_id: int, user_id) -> None:
        rule = self.db.get(WorkAssignmentRule, rule_id)
        if rule is None:
            raise LookupError(f"Rule {rule_id} not found")
        rule.is_active, rule.updated_by, rule.updated_at = False, str(user_id), _now()
        self.db.add(AuditLog(table_name="work_assignment_rule", record_id=rule_id, action="WORK_ASSIGNMENT_RULE_REMOVED",
                             changed_by=str(user_id), new_values={"assignee": rule.assignee_user_id}))
        self.db.commit()

    # ------------------------------------------------------------------ assignment
    def _set(self, invoice_id: int, assignee: str, source: str, by, rule_id=None, note=None) -> InvoiceAssignment:
        row = self.db.get(InvoiceAssignment, invoice_id)
        old = row.assignee_user_id if row else None
        if row is None:
            row = InvoiceAssignment(invoice_id=invoice_id, assignee_user_id=str(assignee), source=source)
            self.db.add(row)
        row.assignee_user_id, row.source, row.assigned_by, row.assigned_at = str(assignee), source, str(by), _now()
        row.rule_id, row.note = rule_id, (note or None) and note[:300]
        self.db.add(AuditLog(table_name="invoice", record_id=invoice_id, action="INVOICE_ASSIGNED", changed_by=str(by),
                             old_values={"assignee": old}, new_values={"assignee": str(assignee), "source": source,
                                                                       **({"note": note} if note else {})}))
        return row

    def assign_new(self, invoice_id: int, actor="SYSTEM") -> Optional[str]:
        """Rule-based assignment of a new / reviewed invoice. Never raises."""
        try:
            if self.db.get(InvoiceAssignment, invoice_id) is not None:
                return None
            invoice = self.db.get(Invoice, invoice_id)
            if invoice is None:
                return None
            rule = None
            if invoice.vendor_id:
                rule = self.db.execute(select(WorkAssignmentRule).where(
                    WorkAssignmentRule.scope == SCOPE_VENDOR, WorkAssignmentRule.vendor_id == invoice.vendor_id,
                    WorkAssignmentRule.is_active.is_(True))).scalar_one_or_none()
            if rule is None and invoice.department_id:
                rule = self.db.execute(select(WorkAssignmentRule).where(
                    WorkAssignmentRule.scope == SCOPE_DEPARTMENT, WorkAssignmentRule.department_id == invoice.department_id,
                    WorkAssignmentRule.is_active.is_(True))).scalar_one_or_none()
            if rule is None:
                return None
            self._set(invoice_id, rule.assignee_user_id, SOURCE_RULE, actor, rule_id=rule.rule_id,
                      note=f"{rule.scope.lower()} rule")
            self.db.commit()
            return rule.assignee_user_id
        except Exception:
            _safe_rollback(self.db)
            logger.exception("Work assignment failed for invoice %s", invoice_id)
            return None

    def _ap_stage(self, invoice_ids: Sequence[int]) -> Dict[int, str]:
        rows = self.db.execute(select(Invoice.invoice_id, StatusMaster.status_code).join(
            StatusMaster, StatusMaster.status_id == Invoice.status_id).where(Invoice.invoice_id.in_(list(invoice_ids)))).all()
        return dict(rows)

    def claim(self, invoice_ids: Sequence[int], user_id) -> Dict[str, Any]:
        statuses = self._ap_stage(invoice_ids)
        owners = self.owners(invoice_ids)
        done, skipped = [], []
        for invoice_id in invoice_ids:
            owner = owners.get(invoice_id, {}).get("user_id")
            if statuses.get(invoice_id) not in AP_STAGE:
                skipped.append({"invoice_id": invoice_id, "reason": "No longer with AP"})
            elif owner and owner != str(user_id):
                skipped.append({"invoice_id": invoice_id, "reason": f"Already with {owners[invoice_id]['name']}"})
            elif owner == str(user_id):
                done.append(invoice_id)
            else:
                self._set(invoice_id, user_id, SOURCE_CLAIM, user_id)
                done.append(invoice_id)
        self.db.commit()
        return {"claimed": done, "skipped": skipped}

    def reassign(self, invoice_ids: Sequence[int], to_user: str, user_id, note: Optional[str] = None) -> Dict[str, Any]:
        self._require_member(to_user)
        statuses = self._ap_stage(invoice_ids)
        done, skipped = [], []
        for invoice_id in invoice_ids:
            if statuses.get(invoice_id) not in AP_STAGE:
                skipped.append({"invoice_id": invoice_id, "reason": "No longer with AP"})
                continue
            self._set(invoice_id, to_user, SOURCE_REASSIGN, user_id, note=note)
            done.append(invoice_id)
        self.db.commit()
        return {"reassigned": done, "skipped": skipped}

    def reassign_all(self, from_user: str, to_user: str, user_id, note: Optional[str] = None) -> Dict[str, Any]:
        """Everything a person holds that is still with AP (e.g. they are on leave)."""
        held = [i for (i,) in self.db.execute(select(InvoiceAssignment.invoice_id).where(
            InvoiceAssignment.assignee_user_id == str(from_user))).all()]
        open_ids = [i for i, s in self._ap_stage(held).items() if s in AP_STAGE] if held else []
        if not open_ids:
            return {"reassigned": [], "skipped": []}
        return self.reassign(open_ids, to_user, user_id, note or "Reassigned while away")

    # ------------------------------------------------------------------ views
    def owners(self, invoice_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
        ids = [i for i in invoice_ids if i is not None]
        if not ids:
            return {}
        rows = self.db.execute(select(InvoiceAssignment).where(InvoiceAssignment.invoice_id.in_(ids))).scalars().all()
        names = self.names(r.assignee_user_id for r in rows)
        return {r.invoice_id: {"user_id": r.assignee_user_id, "name": names.get(r.assignee_user_id, r.assignee_user_id),
                               "source": r.source, "assigned_at": r.assigned_at} for r in rows}

    def workload(self) -> Dict[str, Any]:
        team = self.team()
        rows = self.db.execute(text("""
            select i.invoice_id, s.status_code, a.assignee_user_id,
                   extract(epoch from (localtimestamp - i.created_at)) / 86400 as age_days
            from ap.invoice i join ap.status_master s on s.status_id = i.status_id
            left join ap.invoice_assignment a on a.invoice_id = i.invoice_id
            where s.status_code = any(:statuses)"""), {"statuses": list(AP_STAGE) + ["PENDING_APPROVAL"]}).all()
        # invoice.created_at is timestamp WITHOUT time zone (DB local time), so its age is taken in SQL
        # against the DB's own clock - mixing it with an aware Python "now" raised TypeError.
        per: Dict[str, Counter] = {m["user_id"]: Counter() for m in team}
        oldest: Dict[str, float] = {}
        unassigned = Counter()
        for invoice_id, status, owner, age_days in rows:
            stage = STAGE_LABELS.get(status, "other")
            age = max(float(age_days or 0), 0.0)
            if owner is None:
                if status in AP_STAGE:
                    unassigned[stage] += 1
                continue
            per.setdefault(owner, Counter())[stage] += 1
            if status in AP_STAGE:
                oldest[owner] = max(oldest.get(owner, 0), age)
        names = {m["user_id"]: m["name"] for m in team} | self.names(per)
        members = [{"user_id": uid, "name": names.get(uid, uid), "to_review": c["to_review"], "returned": c["returned"],
                    "reviewed": c["reviewed"], "in_approval": c["in_approval"],
                    "open": c["to_review"] + c["returned"] + c["reviewed"], "oldest_days": round(oldest.get(uid, 0), 1),
                    "in_team": uid in {m["user_id"] for m in team}} for uid, c in per.items()]
        members.sort(key=lambda m: (-m["open"], m["name"]))
        return {"members": members, "unassigned": {"to_review": unassigned["to_review"], "returned": unassigned["returned"],
                                                   "reviewed": unassigned["reviewed"], "total": sum(unassigned.values())},
                "rules": self.rules()}
