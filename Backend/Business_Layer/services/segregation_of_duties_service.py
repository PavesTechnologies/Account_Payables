# Backend/Business_Layer/services/segregation_of_duties_service.py
"""Segregation of duties (SoD) - no one person carries an invoice from entry to payment.

Three rules, each a switch in ap.system_configuration managed by the Finance Manager
(AP_AUTOMATION_MANAGE); a missing row falls back to the default below:

  SOD_PREPARER_CANNOT_APPROVE   (on)   whoever uploaded, reviewed, resubmitted or sent an invoice
                                       for approval cannot approve it
  SOD_APPROVER_CANNOT_RELEASE   (on)   whoever approved an invoice cannot mark it ready for
                                       payment or record its payment
  SOD_RELEASER_CANNOT_PAY       (off)  maker-checker: whoever marked an invoice ready for payment
                                       cannot record its payment (off by default - small finance
                                       teams often have one person doing both)

Who did what is read from audit_log, the same record auditors look at. The AP automation actor
is never a person, so its steps never block anyone. A violation raises SegregationOfDutiesError
(a ValueError, so every existing route answers 422 with the reason).
"""
import datetime
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import select

from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import SystemConfiguration

SOD_MANAGE = "AP_AUTOMATION_MANAGE"

# key -> (default, label, description)
RULES = {
    "SOD_PREPARER_CANNOT_APPROVE": (True, "Preparer cannot approve",
                                    "Whoever uploaded, reviewed or sent an invoice for approval cannot approve it."),
    "SOD_APPROVER_CANNOT_RELEASE": (True, "Approver cannot release payment",
                                    "Whoever approved an invoice cannot mark it ready for payment or record its payment."),
    "SOD_RELEASER_CANNOT_PAY": (False, "Maker-checker on payment",
                                "Whoever marked an invoice ready for payment cannot record its payment."),
}

PREPARE_ACTIONS = ("INVOICE_CREATED", "INVOICE_OCR_REVIEWED", "INVOICE_RESUBMITTED", "INVOICE_SENT_FOR_APPROVAL")
APPROVE_ACTION = "INVOICE_APPROVAL_STEP_DECISION"
RELEASE_ACTION = "INVOICE_READY_FOR_PAYMENT"
NOT_A_PERSON = {"AP_AUTOMATION", "RECURRING_SCHEDULE", "SYSTEM", "SHAREPOINT_IMPORT", "EMAIL_INTAKE", ""}


class SegregationOfDutiesError(ValueError):
    """A segregation-of-duties rule blocks this user from this step."""


class SegregationOfDutiesService:
    def __init__(self, db):
        self.db = db
        self.dao = MasterDAO(db)

    # ------------------------------------------------------------------ settings
    def settings(self) -> Dict[str, bool]:
        out = {}
        for key, (default, *_rest) in RULES.items():
            row = self.dao.get_system_config_by_key(key)
            out[key] = default if row is None or row.config_value is None else row.config_value.strip().lower() == "true"
        return out

    def describe(self) -> List[dict]:
        values = self.settings()
        return [{"key": key, "label": label, "description": description, "enabled": values[key], "default": default}
                for key, (default, label, description) in RULES.items()]

    def update(self, changes: Dict[str, bool], user_id: str, user_name: Optional[str] = None) -> List[dict]:
        unknown = set(changes) - set(RULES)
        if unknown:
            raise ValueError(f"Unknown segregation-of-duties rule(s): {', '.join(sorted(unknown))}")
        before = self.settings()
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        old, new = {}, {}
        for key, enabled in changes.items():
            if enabled is None or bool(enabled) == before[key]:
                continue
            row = self.dao.get_system_config_by_key(key)
            if row is None:
                row = SystemConfiguration(config_key=key, config_value="", data_type="BOOLEAN", description=RULES[key][2])
                self.db.add(row)
            row.config_value = "true" if enabled else "false"
            row.updated_by = (user_name or user_id)[:100]
            row.updated_at = now
            old[key], new[key] = before[key], bool(enabled)
        if new:
            self.db.add(AuditLog(table_name="system_configuration", record_id=0, action="SOD_RULES_CHANGED",
                                 changed_by=str(user_id), old_values=old, new_values=new))
        self.db.commit()
        return self.describe()

    # ------------------------------------------------------------------ who did what
    def _actors(self, invoice_id: int, actions: Iterable[str], approved_only: bool = False) -> Set[str]:
        rows = self.db.execute(select(AuditLog.action, AuditLog.changed_by, AuditLog.new_values).where(
            AuditLog.table_name == "invoice", AuditLog.record_id == invoice_id, AuditLog.action.in_(list(actions)))).all()
        out = set()
        for action, changed_by, values in rows:
            if approved_only and action == APPROVE_ACTION and (values or {}).get("decision") != "APPROVED":
                continue
            who = str(changed_by or "")
            if who.upper() not in NOT_A_PERSON:
                out.add(who)
        return out

    def preparers(self, invoice_id: int) -> Set[str]:
        actors = self._actors(invoice_id, PREPARE_ACTIONS)
        created_by = self.db.execute(select(Invoice.created_by).where(Invoice.invoice_id == invoice_id)).scalar()
        if created_by and str(created_by).upper() not in NOT_A_PERSON:
            actors.add(str(created_by))
        return actors

    def approvers(self, invoice_id: int) -> Set[str]:
        return self._actors(invoice_id, [APPROVE_ACTION], approved_only=True)

    def releasers(self, invoice_id: int) -> Set[str]:
        return self._actors(invoice_id, [RELEASE_ACTION])

    # ------------------------------------------------------------------ checks
    def check_approve(self, invoice_id: int, user_id) -> None:
        if self.settings()["SOD_PREPARER_CANNOT_APPROVE"] and str(user_id) in self.preparers(invoice_id):
            raise SegregationOfDutiesError(
                "Segregation of duties: you uploaded, reviewed or sent this invoice for approval, so you cannot "
                "approve it. Another approver on this step must decide.")

    def check_release(self, invoice_id: int, user_id) -> None:
        if self.settings()["SOD_APPROVER_CANNOT_RELEASE"] and str(user_id) in self.approvers(invoice_id):
            raise SegregationOfDutiesError(
                "Segregation of duties: you approved this invoice, so another Finance user must mark it ready for payment.")

    def check_record_payment(self, invoice_id: int, user_id) -> None:
        rules = self.settings()
        if rules["SOD_APPROVER_CANNOT_RELEASE"] and str(user_id) in self.approvers(invoice_id):
            raise SegregationOfDutiesError(
                "Segregation of duties: you approved this invoice, so another Finance user must record its payment.")
        if rules["SOD_RELEASER_CANNOT_PAY"] and str(user_id) in self.releasers(invoice_id):
            raise SegregationOfDutiesError(
                "Segregation of duties (maker-checker): you marked this invoice ready for payment, so another "
                "Finance user must record the payment.")

    def blocked_for_approval(self, invoice_ids: Iterable[int], user_id) -> Set[int]:
        """Invoices in this user's queue that the preparer rule stops them from approving."""
        ids = list(invoice_ids)
        if not ids or not self.settings()["SOD_PREPARER_CANNOT_APPROVE"]:
            return set()
        who = str(user_id)
        blocked = {i for (i,) in self.db.execute(select(Invoice.invoice_id).where(
            Invoice.invoice_id.in_(ids), Invoice.created_by == who)).all()}
        blocked |= {r for (r,) in self.db.execute(select(AuditLog.record_id).where(
            AuditLog.table_name == "invoice", AuditLog.record_id.in_(ids), AuditLog.action.in_(PREPARE_ACTIONS),
            AuditLog.changed_by == who)).all()}
        return blocked
