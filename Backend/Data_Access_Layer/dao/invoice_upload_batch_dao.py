# Backend/Data_Access_Layer/dao/invoice_upload_batch_dao.py
"""Data access for bulk invoice upload batches (models/invoice_upload_batch.py).

Retry safety lives here: an item is only ever processed after claim_item() atomically moves it
QUEUED -> PROCESSING (a conditional UPDATE), so two workers - a double-clicked retry, or two
backend processes - can never run the same file twice.
"""
import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, update

from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.vendor import Vendor
from Backend.Data_Access_Layer.models.invoice_upload_batch import (
    BATCH_COMPLETED,
    BATCH_NEEDS_ATTENTION,
    BATCH_PROCESSING,
    BATCH_QUEUED,
    ITEM_CREATED,
    ITEM_NEEDS_ATTENTION,
    ITEM_PENDING,
    ITEM_PROCESSING,
    ITEM_QUEUED,
    InvoiceUploadBatch,
    InvoiceUploadBatchItem,
)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class InvoiceUploadBatchDAO:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # Batches
    # ------------------------------------------------------------------
    def add_batch(self, batch: InvoiceUploadBatch) -> InvoiceUploadBatch:
        self.db.add(batch)
        self.db.flush()
        return batch

    def add_item(self, item: InvoiceUploadBatchItem) -> InvoiceUploadBatchItem:
        self.db.add(item)
        self.db.flush()
        return item

    def get_batch(self, batch_id: int) -> Optional[InvoiceUploadBatch]:
        return self.db.query(InvoiceUploadBatch).filter(InvoiceUploadBatch.batch_id == batch_id).first()

    def list_batches(self, uploaded_by: Optional[str], status: Optional[str], offset: int, limit: int,
                     source_type: Optional[str] = None) -> Tuple[List[InvoiceUploadBatch], int]:
        query = self.db.query(InvoiceUploadBatch)
        if source_type:
            query = query.filter(InvoiceUploadBatch.source_type == source_type)
        if uploaded_by:
            query = query.filter(InvoiceUploadBatch.uploaded_by == uploaded_by)
        if status:
            query = query.filter(InvoiceUploadBatch.status == status)
        total = query.count()
        rows = (query.order_by(InvoiceUploadBatch.created_at.desc(), InvoiceUploadBatch.batch_id.desc())
                .offset(offset).limit(limit).all())
        return rows, total

    def status_counts(self, batch_ids: Sequence[int]) -> Dict[int, Dict[str, int]]:
        if not batch_ids:
            return {}
        rows = (self.db.query(InvoiceUploadBatchItem.batch_id, InvoiceUploadBatchItem.status, func.count())
                .filter(InvoiceUploadBatchItem.batch_id.in_(list(batch_ids)))
                .group_by(InvoiceUploadBatchItem.batch_id, InvoiceUploadBatchItem.status).all())
        out: Dict[int, Dict[str, int]] = {}
        for batch_id, status, count in rows:
            out.setdefault(batch_id, {})[status] = count
        return out

    def refresh_batch_status(self, batch_id: int) -> Optional[InvoiceUploadBatch]:
        """Derives the batch status from its items. Caller commits."""
        batch = self.get_batch(batch_id)
        if batch is None:
            return None
        counts = self.status_counts([batch_id]).get(batch_id, {})
        pending = sum(counts.get(s, 0) for s in ITEM_PENDING)
        attention = sum(counts.get(s, 0) for s in ITEM_NEEDS_ATTENTION)
        now = _now()
        if pending:
            started = counts.get(ITEM_PROCESSING, 0) or batch.started_at is not None
            batch.status = BATCH_PROCESSING if started else BATCH_QUEUED
            batch.completed_at = None
        else:
            batch.status = BATCH_NEEDS_ATTENTION if attention else BATCH_COMPLETED
            batch.completed_at = batch.completed_at or now
        batch.updated_at = now
        return batch

    def mark_batch_started(self, batch_id: int) -> None:
        self.db.execute(
            update(InvoiceUploadBatch)
            .where(InvoiceUploadBatch.batch_id == batch_id, InvoiceUploadBatch.started_at.is_(None))
            .values(started_at=_now(), status=BATCH_PROCESSING, updated_at=_now())
        )

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def get_item(self, item_id: int) -> Optional[InvoiceUploadBatchItem]:
        return self.db.query(InvoiceUploadBatchItem).filter(InvoiceUploadBatchItem.item_id == item_id).first()

    def items_for_batch(self, batch_id: int) -> List[InvoiceUploadBatchItem]:
        return (self.db.query(InvoiceUploadBatchItem)
                .filter(InvoiceUploadBatchItem.batch_id == batch_id)
                .order_by(InvoiceUploadBatchItem.sequence_no).all())

    def queued_item_ids(self, batch_id: int) -> List[int]:
        return [r[0] for r in (self.db.query(InvoiceUploadBatchItem.item_id)
                               .filter(InvoiceUploadBatchItem.batch_id == batch_id,
                                       InvoiceUploadBatchItem.status == ITEM_QUEUED)
                               .order_by(InvoiceUploadBatchItem.sequence_no).all())]

    def claim_item(self, item_id: int) -> bool:
        """QUEUED -> PROCESSING, atomically. False when another worker already took it (or it was
        skipped / retried meanwhile). Caller commits."""
        result = self.db.execute(
            update(InvoiceUploadBatchItem)
            .where(InvoiceUploadBatchItem.item_id == item_id, InvoiceUploadBatchItem.status == ITEM_QUEUED)
            .values(status=ITEM_PROCESSING, attempt_count=InvoiceUploadBatchItem.attempt_count + 1,
                    started_at=_now(), completed_at=None, error_code=None, error_message=None, updated_at=_now())
        )
        return result.rowcount == 1

    def requeue_item(self, item_id: int, from_statuses: Sequence[str], stale_before: Optional[datetime.datetime]) -> bool:
        """Back to QUEUED, only from one of ``from_statuses`` - or from PROCESSING when it started
        before ``stale_before`` (the worker died: server restart / crash). Caller commits."""
        condition = InvoiceUploadBatchItem.status.in_(list(from_statuses))
        if stale_before is not None:
            condition = condition | ((InvoiceUploadBatchItem.status == ITEM_PROCESSING)
                                     & (InvoiceUploadBatchItem.started_at < stale_before))
        result = self.db.execute(
            update(InvoiceUploadBatchItem)
            .where(InvoiceUploadBatchItem.item_id == item_id, condition)
            .values(status=ITEM_QUEUED, updated_at=_now())
        )
        return result.rowcount == 1

    def set_item_status(self, item_id: int, from_statuses: Sequence[str], status: str) -> bool:
        result = self.db.execute(
            update(InvoiceUploadBatchItem)
            .where(InvoiceUploadBatchItem.item_id == item_id, InvoiceUploadBatchItem.status.in_(list(from_statuses)))
            .values(status=status, completed_at=_now(), updated_at=_now())
        )
        return result.rowcount == 1

    def created_item_with_sha(self, sha256: str) -> Optional[InvoiceUploadBatchItem]:
        """An earlier upload of the very same file that already became an invoice."""
        return (self.db.query(InvoiceUploadBatchItem)
                .filter(InvoiceUploadBatchItem.file_sha256 == sha256, InvoiceUploadBatchItem.status == ITEM_CREATED)
                .order_by(InvoiceUploadBatchItem.item_id).first())

    def invoice_for_file_path(self, file_path: str) -> Optional[int]:
        """The invoice create_invoice made from this S3 object, if any. Lets a retry recover when the
        worker died after create_invoice committed but before the item was marked CREATED."""
        row = (self.db.query(InboundDocument.invoice_id)
               .filter(InboundDocument.file_path == file_path, InboundDocument.invoice_id.isnot(None))
               .first())
        return row[0] if row else None

    def invoice_numbers(self, invoice_ids: Sequence[int]) -> Dict[int, Tuple[str, Optional[int]]]:
        if not invoice_ids:
            return {}
        rows = (self.db.query(Invoice.invoice_id, Invoice.invoice_number, Invoice.vendor_id)
                .filter(Invoice.invoice_id.in_(list(invoice_ids))).all())
        return {r[0]: (r[1], r[2]) for r in rows}

    # ------------------------------------------------------------------
    # Email intake
    # ------------------------------------------------------------------
    def batch_for_source(self, source_type: str, source_reference: str) -> Optional[InvoiceUploadBatch]:
        return (self.db.query(InvoiceUploadBatch)
                .filter(InvoiceUploadBatch.source_type == source_type,
                        InvoiceUploadBatch.source_reference == source_reference).first())

    def vendor_emails(self) -> List[str]:
        return [r[0] for r in self.db.query(Vendor.email).filter(Vendor.email.isnot(None)).all() if r[0]]
