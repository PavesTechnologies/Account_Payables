# Backend/Data_Access_Layer/dao/payment_term_dao.py
"""Data access for payment-term compliance and vendor agreements
(see models/payment_terms.py). No commits here - the calling service owns the
transaction, same as every other DAO in this package."""
import datetime
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import PaymentTerm, StatusMaster
from Backend.Data_Access_Layer.models.payment_terms import (
    AGREEMENT_STATUS_ACTIVE,
    InvoicePaymentTerm,
    VendorAgreement,
    VendorAgreementDocument,
)
from Backend.Data_Access_Layer.models.purchase_order import GoodsReceipt, PurchaseOrder
from Backend.Data_Access_Layer.models.vendor import Vendor


class PaymentTermDAO:
    def __init__(self, db):
        self.db = db

    def add(self, obj):
        self.db.add(obj)
        self.db.flush()
        return obj

    # ------------------------------------------------------------------
    # Lookups used by the compliance engine
    # ------------------------------------------------------------------
    def get_vendor(self, vendor_id: int) -> Optional[Vendor]:
        return self.db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()

    def get_payment_term(self, payment_term_id: Optional[int]) -> Optional[PaymentTerm]:
        if payment_term_id is None:
            return None
        return self.db.query(PaymentTerm).filter(PaymentTerm.payment_term_id == payment_term_id).first()

    def get_active_payment_term_by_days(self, due_days: int) -> Optional[PaymentTerm]:
        """The payment_term row for a number of days - system default first, then lowest id,
        so "Net 30 days" / "30 days credit" resolve to the same row as "Net 30"."""
        return (
            self.db.query(PaymentTerm)
            .filter(PaymentTerm.due_days == due_days, PaymentTerm.is_active.is_(True))
            .order_by(PaymentTerm.is_system_default.desc(), PaymentTerm.payment_term_id.asc())
            .first()
        )

    def get_purchase_order(self, po_id: Optional[int]) -> Optional[PurchaseOrder]:
        if po_id is None:
            return None
        return self.db.query(PurchaseOrder).filter(PurchaseOrder.po_id == po_id).first()

    def get_goods_receipt(self, grn_id: Optional[int]) -> Optional[GoodsReceipt]:
        if grn_id is None:
            return None
        return self.db.query(GoodsReceipt).filter(GoodsReceipt.grn_id == grn_id).first()

    def get_latest_goods_receipt_for_po(self, po_id: int) -> Optional[GoodsReceipt]:
        return (
            self.db.query(GoodsReceipt)
            .filter(GoodsReceipt.po_id == po_id, GoodsReceipt.receipt_date.isnot(None))
            .order_by(GoodsReceipt.receipt_date.desc(), GoodsReceipt.grn_id.desc())
            .first()
        )

    # ------------------------------------------------------------------
    # Invoice payment-term records
    # ------------------------------------------------------------------
    def get_record(self, invoice_id: int) -> Optional[InvoicePaymentTerm]:
        return self.db.query(InvoicePaymentTerm).filter(InvoicePaymentTerm.invoice_id == invoice_id).first()

    def get_records(self, invoice_ids: Sequence[int]) -> dict:
        if not invoice_ids:
            return {}
        rows = self.db.query(InvoicePaymentTerm).filter(InvoicePaymentTerm.invoice_id.in_(list(invoice_ids))).all()
        return {row.invoice_id: row for row in rows}

    def get_invoice(self, invoice_id: int) -> Optional[Invoice]:
        return self.db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()

    def list_open_invoice_ids_for_vendor(self, vendor_id: int, closed_status_codes: Sequence[str]) -> List[int]:
        rows = (
            self.db.query(Invoice.invoice_id)
            .outerjoin(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .filter(Invoice.vendor_id == vendor_id)
            .filter(or_(StatusMaster.status_code.is_(None), StatusMaster.status_code.notin_(list(closed_status_codes))))
            .all()
        )
        return [r[0] for r in rows]

    def list_invoice_ids_for_backfill(self, closed_status_codes: Sequence[str], include_closed: bool) -> List[int]:
        query = self.db.query(Invoice.invoice_id).outerjoin(StatusMaster, StatusMaster.status_id == Invoice.status_id)
        if not include_closed:
            query = query.filter(
                or_(StatusMaster.status_code.is_(None), StatusMaster.status_code.notin_(list(closed_status_codes)))
            )
        return [r[0] for r in query.order_by(Invoice.invoice_id).all()]

    def list_exceptions(
        self,
        statuses: Sequence[str],
        closed_status_codes: Sequence[str],
        vendor_id: Optional[int],
        reason_code: Optional[str],
        due_from: Optional[datetime.date],
        due_to: Optional[datetime.date],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> Tuple[List[tuple], int]:
        query = (
            self.db.query(InvoicePaymentTerm, Invoice, Vendor.vendor_name, StatusMaster.status_code)
            .join(Invoice, Invoice.invoice_id == InvoicePaymentTerm.invoice_id)
            .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
            .outerjoin(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .filter(InvoicePaymentTerm.validation_status.in_(list(statuses)))
            .filter(or_(StatusMaster.status_code.is_(None), StatusMaster.status_code.notin_(list(closed_status_codes))))
        )
        if vendor_id is not None:
            query = query.filter(Invoice.vendor_id == vendor_id)
        if reason_code:
            query = query.filter(InvoicePaymentTerm.reason_code == reason_code)
        if due_from is not None:
            query = query.filter(Invoice.due_date >= due_from)
        if due_to is not None:
            query = query.filter(Invoice.due_date <= due_to)
        if search:
            like = f"%{search.strip()}%"
            query = query.filter(or_(Invoice.invoice_number.ilike(like), Vendor.vendor_name.ilike(like)))
        total = query.count()
        rows = (
            query.order_by(Invoice.due_date.asc(), Invoice.invoice_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return rows, total

    # ------------------------------------------------------------------
    # Vendor agreements
    # ------------------------------------------------------------------
    def get_agreement(self, agreement_id: int) -> Optional[VendorAgreement]:
        return (
            self.db.query(VendorAgreement)
            .options(selectinload(VendorAgreement.documents))
            .filter(VendorAgreement.agreement_id == agreement_id)
            .first()
        )

    def list_agreements(self, vendor_id: int) -> List[VendorAgreement]:
        return (
            self.db.query(VendorAgreement)
            .options(selectinload(VendorAgreement.documents))
            .filter(VendorAgreement.vendor_id == vendor_id)
            .order_by(VendorAgreement.valid_from.desc(), VendorAgreement.agreement_id.desc())
            .all()
        )

    def has_any_active_agreement_history(self, vendor_id: int) -> bool:
        """True when the vendor has (or had) a verified agreement - used to tell "no agreement
        on file" apart from "agreement on file but not valid on this date"."""
        return (
            self.db.query(VendorAgreement.agreement_id)
            .filter(
                VendorAgreement.vendor_id == vendor_id,
                VendorAgreement.status.in_([AGREEMENT_STATUS_ACTIVE, "SUPERSEDED"]),
            )
            .first()
            is not None
        )

    def get_active_agreements_valid_on(self, vendor_id: int, on_date: datetime.date) -> List[VendorAgreement]:
        return (
            self.db.query(VendorAgreement)
            .filter(
                VendorAgreement.vendor_id == vendor_id,
                VendorAgreement.status == AGREEMENT_STATUS_ACTIVE,
                VendorAgreement.valid_from <= on_date,
                or_(VendorAgreement.valid_to.is_(None), VendorAgreement.valid_to >= on_date),
            )
            .order_by(VendorAgreement.valid_from.desc(), VendorAgreement.agreement_id.desc())
            .all()
        )

    def list_active_agreements_of_type(self, vendor_id: int, agreement_type: str, exclude_id: int) -> List[VendorAgreement]:
        return (
            self.db.query(VendorAgreement)
            .filter(
                VendorAgreement.vendor_id == vendor_id,
                VendorAgreement.agreement_type == agreement_type,
                VendorAgreement.status == AGREEMENT_STATUS_ACTIVE,
                VendorAgreement.agreement_id != exclude_id,
            )
            .all()
        )

    def list_expiring_agreements(self, today: datetime.date, within_days: int) -> List[tuple]:
        until = today + datetime.timedelta(days=within_days)
        return (
            self.db.query(VendorAgreement, Vendor.vendor_name)
            .join(Vendor, Vendor.vendor_id == VendorAgreement.vendor_id)
            .filter(
                VendorAgreement.status == AGREEMENT_STATUS_ACTIVE,
                VendorAgreement.valid_to.isnot(None),
                and_(VendorAgreement.valid_to >= today, VendorAgreement.valid_to <= until),
            )
            .order_by(VendorAgreement.valid_to.asc())
            .all()
        )

    def get_agreement_document(self, agreement_id: int, document_id: int) -> Optional[VendorAgreementDocument]:
        return (
            self.db.query(VendorAgreementDocument)
            .filter(
                VendorAgreementDocument.agreement_id == agreement_id,
                VendorAgreementDocument.document_id == document_id,
            )
            .first()
        )

    def count_status(self, status: str) -> int:
        return (
            self.db.query(func.count(InvoicePaymentTerm.invoice_id))
            .filter(InvoicePaymentTerm.validation_status == status)
            .scalar()
            or 0
        )
