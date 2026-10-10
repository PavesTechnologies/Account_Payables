# Backend/Data_Access_Layer/dao/tds_challan_dao.py
"""Shared TDS challan / quarterly filing queries (Phase 5). Builds on TdsTrackingDAO's invoice
query (Invoice, vendor_name, StatusMaster, InvoiceTds, TdsPaymentNature, TaxRule, tracking) so the
invoice / TDS facts are read exactly as the TDS Tracking screens read them. Add / flush only."""
import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func

from Backend.Data_Access_Layer.dao.tds_tracking_dao import TdsTrackingDAO
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.tds import InvoiceTds, InvoiceTdsTracking
from Backend.Data_Access_Layer.models.tds_challan import (
    TdsChallan,
    TdsChallanAllocation,
    TdsReturnFiling,
    TdsReturnFilingInvoice,
)


class TdsChallanDAO:
    def __init__(self, db):
        self.db = db
        self.tracking = TdsTrackingDAO(db)

    def add(self, obj):
        self.db.add(obj)
        self.db.flush()
        return obj

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------
    def invoices_in_tracking_status(self, statuses: Sequence[str], deducted_from: Optional[datetime.date],
                                    deducted_to: Optional[datetime.date]) -> List[tuple]:
        query = (self.tracking._query()
                 .filter(InvoiceTds.determination_status == "VERIFIED",
                         InvoiceTdsTracking.tracking_status.in_(list(statuses))))
        if deducted_from is not None:
            query = query.filter(InvoiceTdsTracking.deduction_date >= deducted_from)
        if deducted_to is not None:
            query = query.filter(InvoiceTdsTracking.deduction_date <= deducted_to)
        return query.order_by(InvoiceTdsTracking.deduction_date.asc(), Invoice.invoice_id.asc()).all()

    def tds_row(self, invoice_id: int):
        return self.tracking.get_tds_invoice(invoice_id)

    def actively_allocated(self, invoice_ids: Sequence[int]) -> Dict[int, int]:
        """invoice_id -> challan_id for invoices already covered by a challan."""
        if not invoice_ids:
            return {}
        rows = (self.db.query(TdsChallanAllocation.invoice_id, TdsChallanAllocation.challan_id)
                .filter(TdsChallanAllocation.invoice_id.in_(list(invoice_ids)), TdsChallanAllocation.is_active.is_(True)).all())
        return {r[0]: r[1] for r in rows}

    def challan_by_identity(self, bsr: str, deposit_date: datetime.date, serial: str) -> Optional[TdsChallan]:
        return (self.db.query(TdsChallan)
                .filter(TdsChallan.bsr_code == bsr, TdsChallan.deposit_date == deposit_date,
                        TdsChallan.challan_serial_no == serial).first())

    def filing_by_ack(self, ack: str) -> Optional[TdsReturnFiling]:
        return self.db.query(TdsReturnFiling).filter(func.upper(TdsReturnFiling.acknowledgement_no) == ack.upper()).first()

    # ------------------------------------------------------------------
    # Lists / detail
    # ------------------------------------------------------------------
    def list_challans(self, offset: int, limit: int) -> Tuple[List[TdsChallan], int]:
        query = self.db.query(TdsChallan)
        return (query.order_by(TdsChallan.deposit_date.desc(), TdsChallan.challan_id.desc()).offset(offset).limit(limit).all(),
                query.count())

    def challan_counts(self, challan_ids: Sequence[int]) -> Dict[int, int]:
        if not challan_ids:
            return {}
        rows = (self.db.query(TdsChallanAllocation.challan_id, func.count())
                .filter(TdsChallanAllocation.challan_id.in_(list(challan_ids)), TdsChallanAllocation.is_active.is_(True))
                .group_by(TdsChallanAllocation.challan_id).all())
        return {r[0]: r[1] for r in rows}

    def get_challan(self, challan_id: int) -> Optional[TdsChallan]:
        return self.db.query(TdsChallan).filter(TdsChallan.challan_id == challan_id).first()

    def list_filings(self, offset: int, limit: int) -> Tuple[List[TdsReturnFiling], int]:
        query = self.db.query(TdsReturnFiling)
        return (query.order_by(TdsReturnFiling.filing_date.desc(), TdsReturnFiling.filing_id.desc()).offset(offset).limit(limit).all(),
                query.count())

    def filing_counts(self, filing_ids: Sequence[int]) -> Dict[int, int]:
        if not filing_ids:
            return {}
        rows = (self.db.query(TdsReturnFilingInvoice.filing_id, func.count())
                .filter(TdsReturnFilingInvoice.filing_id.in_(list(filing_ids)))
                .group_by(TdsReturnFilingInvoice.filing_id).all())
        return {r[0]: r[1] for r in rows}

    def get_filing(self, filing_id: int) -> Optional[TdsReturnFiling]:
        return self.db.query(TdsReturnFiling).filter(TdsReturnFiling.filing_id == filing_id).first()

    def invoice_numbers(self, invoice_ids: Sequence[int]) -> Dict[int, tuple]:
        if not invoice_ids:
            return {}
        rows = self.tracking._query().filter(Invoice.invoice_id.in_(list(invoice_ids))).all()
        return {r[0].invoice_id: r for r in rows}
