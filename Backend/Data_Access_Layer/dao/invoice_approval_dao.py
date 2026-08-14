# Backend/Data_Access_Layer/dao/invoice_approval_dao.py
from typing import List, Optional

from Backend.Data_Access_Layer.models.approval import InvoiceApproval
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import StatusMaster

APPROVAL_STATUS_MODULE = "APPROVAL"
INVOICE_STATUS_MODULE = "INVOICE"


class InvoiceApprovalDAO:
    def __init__(self, db):
        self.db = db

    def create_approval(self, approval: InvoiceApproval) -> InvoiceApproval:
        self.db.add(approval)
        self.db.flush()
        return approval

    def get_approvals_by_invoice_id(self, invoice_id: int) -> List[InvoiceApproval]:
        return (
            self.db.query(InvoiceApproval)
            .filter(InvoiceApproval.invoice_id == invoice_id)
            .order_by(InvoiceApproval.invoice_approval_id.asc())
            .all()
        )

    def get_status_by_module_code(
        self,
        module_name: str,
        status_code: str,
    ) -> Optional[StatusMaster]:

        return (
            self.db.query(StatusMaster)
            .filter(
                StatusMaster.module_name == module_name,
                StatusMaster.status_code == status_code,
            )
            .first()
        )

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log
