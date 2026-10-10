# Backend/Business_Layer/services/invoice_bulk_upload_service.py
"""Bulk invoice upload (APM_AUTOMATION_PLAN.md Phase 3) - orchestration only.

The single-upload flow stays the source of truth. For every file the worker calls exactly the
operations the Invoice Upload page drives, in the same order:

    upload_to_s3  ->  extract_invoice_from_s3  ->  InvoiceExtractionService.validate_invoice
                  ->  InvoiceExtractionService.create_invoice

and, like the page's "Save for Manual Review", create_invoice runs whatever the validation outcome,
so every readable invoice lands at OCR_REVIEW_PENDING in the existing review queue. Review,
approval, payment terms, TDS and payment behaviour are therefore unchanged.

This module adds only:
  * batch / item tracking (invoice_upload_batch[_item]),
  * a concurrency limit (BULK_UPLOAD_CONCURRENCY files at a time per backend process, so AWS
    Textract is not throttled),
  * retry safety - an item is claimed atomically before it is processed; the Textract result is
    kept so a retry does not re-extract; a retry after a crash finds the invoice the earlier
    attempt already created (by its S3 path) instead of creating a duplicate; the same file
    uploaded twice is caught by its SHA-256 before it reaches Textract.
"""
import asyncio
import datetime
import logging
import re
import weakref
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from Backend.API_Layer.interface.invoice_extraction_interface import ExtractedInvoiceResponse
from Backend.API_Layer.utils.invoice_extraction_fields import extract_invoice_from_s3
from Backend.API_Layer.utils.s3_utils import upload_to_s3
from Backend.Business_Layer.services.invoice_extraction_service import InvoiceExtractionService
from Backend.Business_Layer.utils.bulk_upload_files import CandidateFile
from Backend.Business_Layer.utils.exceptions import (
    DuplicateInvoiceError,
    FieldExtractionError,
    VendorNotMatchedError,
)
from Backend.config.env_loader import get_env_var
from Backend.Data_Access_Layer.dao.invoice_upload_batch_dao import InvoiceUploadBatchDAO
from Backend.Data_Access_Layer.models.invoice_upload_batch import (
    ITEM_CREATED,
    ITEM_DUPLICATE,
    ITEM_FAILED,
    ITEM_NEEDS_ATTENTION,
    ITEM_PENDING,
    ITEM_PROCESSING,
    ITEM_QUEUED,
    ITEM_SKIPPED,
    ITEM_VENDOR_NOT_FOUND,
    SOURCE_MANUAL_UPLOAD,
    InvoiceUploadBatch,
    InvoiceUploadBatchItem,
)
from Backend.Data_Access_Layer.utils.database import SessionLocal

logger = logging.getLogger(__name__)

# 2 by default: Textract is the bottleneck and the DB pool is small (3 + 2 overflow, shared with requests).
CONCURRENCY = max(1, int(get_env_var("BULK_UPLOAD_CONCURRENCY", "2")))
# A PROCESSING item untouched this long belongs to a worker that died (restart / crash).
STALE_AFTER = datetime.timedelta(minutes=max(5, int(get_env_var("BULK_UPLOAD_STALE_MINUTES", "15"))))
S3_PREFIX = "invoices/bulk/"

# error_code values
INVALID_FILE = "INVALID_FILE"
DUPLICATE_FILE = "DUPLICATE_FILE"
DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
UPLOAD_FAILED = "UPLOAD_FAILED"
EXTRACTION_FAILED = "EXTRACTION_FAILED"
VENDOR_NOT_FOUND = "VENDOR_NOT_FOUND"
CREATE_FAILED = "CREATE_FAILED"
UNEXPECTED = "UNEXPECTED"

# Failures that a retry can fix. INVALID_FILE / UPLOAD_FAILED have no stored file - upload it again.
RETRYABLE_CODES = (EXTRACTION_FAILED, VENDOR_NOT_FOUND, CREATE_FAILED, UNEXPECTED)

_INVOICE_ID_IN_MESSAGE = re.compile(r"invoice_id=(\d+)")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _error_text(exc: Exception, fallback: str) -> str:
    if isinstance(exc, HTTPException) and isinstance(exc.detail, str):
        return exc.detail
    text = str(exc).strip()
    return text[:1000] if text else fallback


# ======================================================================
# Request side: build the batch
# ======================================================================
class InvoiceBulkUploadService:
    def __init__(self, db):
        self.db = db
        self.dao = InvoiceUploadBatchDAO(db)

    def create_batch(self, candidates: List[CandidateFile], source_name: str, user_id: str,
                     user_name: Optional[str] = None, source_type: str = SOURCE_MANUAL_UPLOAD,
                     source_reference: Optional[str] = None, email: Optional[Dict[str, Any]] = None) -> int:
        """Records the batch, uploads every acceptable file to S3 and leaves it QUEUED for the
        worker. Rejected / duplicate files are recorded too (never sent to Textract) so the uploader
        sees why each file was not processed. Returns batch_id."""
        batch = self.dao.add_batch(InvoiceUploadBatch(
            source_type=source_type, source_name=source_name, source_reference=source_reference,
            total_files=len(candidates), uploaded_by=user_id, uploaded_by_name=user_name,
            **(email or {}),
        ))
        seen: Dict[str, InvoiceUploadBatchItem] = {}
        to_upload = []
        for seq, candidate in enumerate(candidates, start=1):
            item = InvoiceUploadBatchItem(
                batch_id=batch.batch_id, sequence_no=seq, file_name=candidate.file_name,
                content_type=candidate.content_type, file_size=candidate.size, file_sha256=candidate.sha256,
                status=ITEM_QUEUED, attempt_count=0,
            )
            if candidate.problem:
                item.status, item.error_code, item.error_message = ITEM_FAILED, INVALID_FILE, candidate.problem
            elif candidate.sha256 in seen:
                first = seen[candidate.sha256]
                item.status, item.error_code, item.duplicate_of_item_id = ITEM_DUPLICATE, DUPLICATE_FILE, first.item_id
                item.error_message = f"Same file as #{first.sequence_no} ({first.file_name}) in this batch."
            else:
                earlier = self.dao.created_item_with_sha(candidate.sha256)
                if earlier is not None:
                    item.status, item.error_code, item.duplicate_of_item_id = ITEM_DUPLICATE, DUPLICATE_FILE, earlier.item_id
                    item.invoice_id = earlier.invoice_id
                    item.error_message = (f"This exact file was already uploaded in batch #{earlier.batch_id} "
                                          f"and created as an invoice.")
            if item.status != ITEM_QUEUED:
                item.completed_at = _now()
            self.dao.add_item(item)
            if item.status == ITEM_QUEUED:
                seen[candidate.sha256] = item
                to_upload.append((item, candidate))
        self.db.commit()

        # Same S3 helper as /extract-fields; a separate prefix only keeps bulk files grouped.
        for item, candidate in to_upload:
            try:
                stored = upload_to_s3(filename=candidate.file_name, content=candidate.content,
                                      content_type=candidate.content_type,
                                      prefix=f"{S3_PREFIX}{batch.batch_id}/")
                item.file_path = stored["filepath"]
            except Exception as exc:
                logger.exception("Bulk upload %s: S3 upload failed for item %s", batch.batch_id, item.item_id)
                item.status, item.error_code = ITEM_FAILED, UPLOAD_FAILED
                item.error_message = "The file could not be stored (" + _error_text(exc, "storage error") + "). Upload it again."
                item.completed_at = _now()
            item.updated_at = _now()
            self.db.commit()

        self.dao.refresh_batch_status(batch.batch_id)
        self.db.commit()
        return batch.batch_id

    # ------------------------------------------------------------------
    # Retry / skip
    # ------------------------------------------------------------------
    def _retryable(self, item: InvoiceUploadBatchItem) -> bool:
        if item.status in ITEM_NEEDS_ATTENTION:
            return item.error_code in RETRYABLE_CODES and bool(item.file_path)
        return item.status == ITEM_PROCESSING and self._stalled(item)

    @staticmethod
    def _stalled(item: InvoiceUploadBatchItem) -> bool:
        started = item.started_at
        if started is None:
            return False
        if started.tzinfo is None:
            started = started.replace(tzinfo=datetime.timezone.utc)
        return started < _now() - STALE_AFTER

    def retry_item(self, item_id: int) -> InvoiceUploadBatchItem:
        item = self.dao.get_item(item_id)
        if item is None:
            raise LookupError("Upload item not found")
        if not self._retryable(item):
            raise ValueError(self._why_not_retryable(item))
        if not self.dao.requeue_item(item_id, ITEM_NEEDS_ATTENTION, _now() - STALE_AFTER):
            raise ValueError("This file changed state meanwhile - refresh and try again.")
        self.dao.refresh_batch_status(item.batch_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def retry_batch(self, batch_id: int) -> List[int]:
        """Requeues every retryable item (and stalled ones). Items still QUEUED - e.g. left behind
        by a restart before the worker picked them up - are returned too, so the worker resumes
        them. Returns the item ids to process."""
        if self.dao.get_batch(batch_id) is None:
            raise LookupError("Upload batch not found")
        ids = []
        for item in self.dao.items_for_batch(batch_id):
            if item.status == ITEM_QUEUED:
                ids.append(item.item_id)
            elif self._retryable(item) and self.dao.requeue_item(item.item_id, ITEM_NEEDS_ATTENTION,
                                                                _now() - STALE_AFTER):
                ids.append(item.item_id)
        if not ids:
            raise ValueError("Nothing to retry in this batch.")
        self.dao.refresh_batch_status(batch_id)
        self.db.commit()
        return ids

    def skip_item(self, item_id: int) -> InvoiceUploadBatchItem:
        item = self.dao.get_item(item_id)
        if item is None:
            raise LookupError("Upload item not found")
        if item.status not in ITEM_NEEDS_ATTENTION:
            raise ValueError("Only files that need attention (vendor not found / failed) can be skipped.")
        if not self.dao.set_item_status(item_id, ITEM_NEEDS_ATTENTION, ITEM_SKIPPED):
            raise ValueError("This file changed state meanwhile - refresh and try again.")
        self.dao.refresh_batch_status(item.batch_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    @staticmethod
    def _why_not_retryable(item: InvoiceUploadBatchItem) -> str:
        if item.status == ITEM_CREATED:
            return "This file was already created as an invoice."
        if item.status in ITEM_PENDING:
            return "This file is still being processed."
        if item.status == ITEM_DUPLICATE:
            return "Duplicates are not retried - open the existing invoice instead."
        if item.status == ITEM_SKIPPED:
            return "This file was skipped."
        return "This file cannot be retried - upload it again in a new batch."

    # ------------------------------------------------------------------
    # Read side
    # ------------------------------------------------------------------
    def list_batches(self, uploaded_by: Optional[str], status: Optional[str], page: int, page_size: int,
                     source_type: Optional[str] = None):
        rows, total = self.dao.list_batches(uploaded_by, status, (page - 1) * page_size, page_size, source_type)
        counts = self.dao.status_counts([b.batch_id for b in rows])
        return [self._batch_summary(b, counts.get(b.batch_id, {})) for b in rows], total

    def batch_detail(self, batch_id: int) -> Dict[str, Any]:
        batch = self.dao.get_batch(batch_id)
        if batch is None:
            raise LookupError("Upload batch not found")
        items = self.dao.items_for_batch(batch_id)
        counts: Dict[str, int] = {}
        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1
        numbers = self.dao.invoice_numbers([i.invoice_id for i in items if i.invoice_id])
        automation = self._automation_results([i.invoice_id for i in items if i.invoice_id and i.status == ITEM_CREATED])
        return {
            **self._batch_summary(batch, counts),
            "items": [{**self._item_view(i, numbers), "automation": automation.get(i.invoice_id)} for i in items],
        }

    def _automation_results(self, invoice_ids) -> Dict[int, Dict[str, Any]]:
        if not invoice_ids:
            return {}
        try:
            from Backend.Data_Access_Layer.dao.ap_automation_dao import APAutomationDAO
            return {k: {"outcome": v.get("outcome"), "reasons": v.get("reasons") or []}
                    for k, v in APAutomationDAO(self.db).latest_results(invoice_ids).items()}
        except Exception:
            logger.exception("Could not load automation results")
            return {}

    @staticmethod
    def _batch_summary(batch: InvoiceUploadBatch, counts: Dict[str, int]) -> Dict[str, Any]:
        return {
            "batch_id": batch.batch_id,
            "source_type": batch.source_type,
            "source_name": batch.source_name,
            "status": batch.status,
            "total_files": batch.total_files,
            "uploaded_by": batch.uploaded_by,
            "uploaded_by_name": batch.uploaded_by_name,
            "created_at": batch.created_at,
            "started_at": batch.started_at,
            "completed_at": batch.completed_at,
            "email_from": batch.email_from,
            "email_subject": batch.email_subject,
            "email_received_at": batch.email_received_at,
            "sender_known": batch.sender_known,
            "counts": {
                "queued": counts.get(ITEM_QUEUED, 0) + counts.get(ITEM_PROCESSING, 0),
                "created": counts.get(ITEM_CREATED, 0),
                "vendor_not_found": counts.get(ITEM_VENDOR_NOT_FOUND, 0),
                "duplicate": counts.get(ITEM_DUPLICATE, 0),
                "failed": counts.get(ITEM_FAILED, 0),
                "skipped": counts.get(ITEM_SKIPPED, 0),
            },
        }

    def _item_view(self, item: InvoiceUploadBatchItem, numbers) -> Dict[str, Any]:
        validation = item.validation_result or {}
        number, vendor_id = numbers.get(item.invoice_id, (None, None)) if item.invoice_id else (None, None)
        extracted = item.extracted_data or {}
        return {
            "item_id": item.item_id,
            "sequence_no": item.sequence_no,
            "file_name": item.file_name,
            "file_size": item.file_size,
            "status": item.status,
            "stalled": item.status == ITEM_PROCESSING and self._stalled(item),
            "attempt_count": item.attempt_count,
            "error_code": item.error_code,
            "error_message": item.error_message,
            "can_retry": self._retryable(item),
            "can_skip": item.status in ITEM_NEEDS_ATTENTION,
            "invoice_id": item.invoice_id,
            "invoice_number": number or (extracted.get("reference") or {}).get("invoice_number"),
            "vendor_id": vendor_id,
            "vendor_name": (extracted.get("vendor") or {}).get("name"),
            "vendor_gstin": (extracted.get("vendor") or {}).get("gstin"),
            "is_valid": validation.get("is_valid"),
            "validation_issues": (validation.get("issues") or [])[:5],
            "started_at": item.started_at,
            "completed_at": item.completed_at,
        }


# ======================================================================
# Worker side: one file at a time through the single-upload operations
# ======================================================================
_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _semaphore() -> asyncio.Semaphore:
    # One limiter per event loop: the API runs one loop per process; the email runner starts a new
    # loop per run, and a semaphore must never be shared across loops.
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = _semaphores[loop] = asyncio.Semaphore(CONCURRENCY)
    return sem


def _with_session(fn, *args):
    db = SessionLocal()
    try:
        return fn(db, *args)
    finally:
        db.close()


def _claim(db, item_id: int) -> Optional[Dict[str, Any]]:
    dao = InvoiceUploadBatchDAO(db)
    if not dao.claim_item(item_id):
        db.rollback()
        return None
    item = dao.get_item(item_id)
    dao.mark_batch_started(item.batch_id)
    db.commit()
    return {
        "batch_id": item.batch_id,
        "file_name": item.file_name,
        "file_path": item.file_path,
        "extracted_data": item.extracted_data,
        # Retry after a crash: create_invoice may already have committed for this S3 object.
        "existing_invoice_id": dao.invoice_for_file_path(item.file_path) if item.file_path else None,
    }


def _finish(db, item_id: int, status: str, error_code: Optional[str] = None, error_message: Optional[str] = None,
            invoice_id: Optional[int] = None, validation: Optional[dict] = None) -> None:
    dao = InvoiceUploadBatchDAO(db)
    item = dao.get_item(item_id)
    if item is None:
        return
    item.status, item.error_code, item.error_message = status, error_code, error_message
    if invoice_id is not None:
        item.invoice_id = invoice_id
    if validation is not None:
        item.validation_result = validation
    item.completed_at = item.updated_at = _now()
    db.commit()


def _save_extraction(db, item_id: int, extracted: dict) -> None:
    item = InvoiceUploadBatchDAO(db).get_item(item_id)
    if item is not None:
        item.extracted_data = extracted
        item.updated_at = _now()
        db.commit()


def _validate_and_create(db, item_id: int, extracted: ExtractedInvoiceResponse, file_path: str, actor: str) -> None:
    service = InvoiceExtractionService(db)
    # 1. validate-fields - same call, no job_id (the progress-polling side effect is UI-only).
    try:
        validation = service.validate_invoice(extracted, file_path).model_dump(mode="json")
    except Exception:
        logger.exception("Bulk upload item %s: validation raised", item_id)
        db.rollback()
        validation = {"is_valid": False, "requires_manual_review": True,
                      "issues": ["Automatic validation could not run - review this invoice manually."]}
    # 2. create-invoice - runs whatever the validation outcome, exactly like "Save for Manual Review".
    try:
        result = service.create_invoice(extracted, file_path, created_by=actor)
    except VendorNotMatchedError as exc:
        db.rollback()
        _finish(db, item_id, ITEM_VENDOR_NOT_FOUND, VENDOR_NOT_FOUND,
                f"{exc} Onboard the vendor (or correct its GSTIN) and retry.", validation=validation)
        return
    except DuplicateInvoiceError as exc:
        db.rollback()
        mine = InvoiceUploadBatchDAO(db).invoice_for_file_path(file_path)
        if mine is not None:  # our own earlier attempt created it
            _finish(db, item_id, ITEM_CREATED, invoice_id=mine, validation=validation)
            return
        match = _INVOICE_ID_IN_MESSAGE.search(str(exc))
        _finish(db, item_id, ITEM_DUPLICATE, DUPLICATE_INVOICE, str(exc),
                invoice_id=int(match.group(1)) if match else None, validation=validation)
        return
    except FieldExtractionError as exc:
        db.rollback()
        _finish(db, item_id, ITEM_FAILED, CREATE_FAILED, _error_text(exc, "The invoice could not be created."),
                validation=validation)
        return
    except Exception:
        logger.exception("Bulk upload item %s: create_invoice raised", item_id)
        db.rollback()
        _finish(db, item_id, ITEM_FAILED, UNEXPECTED, "Unexpected error while creating the invoice.",
                validation=validation)
        return
    _finish(db, item_id, ITEM_CREATED, invoice_id=result["invoice_id"], validation=validation)
    # Step B: touchless PO invoices (no-op while AP_AUTOMATION_ENABLED is off; never raises).
    po_number = getattr(getattr(extracted, "reference", None), "po_number", None)
    _run_automation(db, result["invoice_id"], po_number)


def _run_automation(db, invoice_id: int, po_number: Optional[str]) -> None:
    from Backend.Business_Layer.services.ap_automation_service import run_after_create  # avoid import cycle
    run_after_create(db, invoice_id, po_number)


async def process_item(item_id: int, actor: str) -> None:
    claimed = await run_in_threadpool(_with_session, _claim, item_id)
    if claimed is None:
        return  # another worker has it, or it was skipped / requeued meanwhile
    if claimed["existing_invoice_id"]:
        await run_in_threadpool(_with_session, _finish, item_id, ITEM_CREATED, None, None, claimed["existing_invoice_id"])
        return

    file_path = claimed["file_path"]
    try:
        if claimed["extracted_data"]:
            extracted = ExtractedInvoiceResponse.model_validate(claimed["extracted_data"])
        else:
            # 1. extract-fields - same Textract call the upload page uses.
            extracted = await extract_invoice_from_s3(s3_key=file_path, filename=claimed["file_name"])
            await run_in_threadpool(_with_session, _save_extraction, item_id, extracted.model_dump(mode="json"))
    except Exception as exc:
        logger.warning("Bulk upload item %s: extraction failed: %s", item_id, exc)
        await run_in_threadpool(_with_session, _finish, item_id, ITEM_FAILED, EXTRACTION_FAILED,
                                "The invoice could not be read (" + _error_text(exc, "extraction error") + ").")
        return

    await run_in_threadpool(_with_session, _validate_and_create, item_id, extracted, file_path, actor)


async def _guarded(item_id: int, actor: str) -> None:
    async with _semaphore():
        try:
            await process_item(item_id, actor)
        except Exception:
            # Never leave the item PROCESSING because of a bug here - it becomes retryable.
            logger.exception("Bulk upload item %s: worker crashed", item_id)
            try:
                await run_in_threadpool(_with_session, _finish, item_id, ITEM_FAILED, UNEXPECTED,
                                        "Unexpected error while processing this file.")
            except Exception:
                logger.exception("Bulk upload item %s: could not record the failure", item_id)


def _refresh(db, batch_id: int) -> None:
    InvoiceUploadBatchDAO(db).refresh_batch_status(batch_id)
    db.commit()


async def process_batch(batch_id: int, actor: str, item_ids: Optional[List[int]] = None) -> None:
    """Background task: runs the batch's QUEUED items (or ``item_ids``), CONCURRENCY at a time."""
    if item_ids is None:
        item_ids = await run_in_threadpool(_with_session, lambda db: InvoiceUploadBatchDAO(db).queued_item_ids(batch_id))
    await asyncio.gather(*(_guarded(i, actor) for i in item_ids))
    try:
        await run_in_threadpool(_with_session, _refresh, batch_id)
    except Exception:
        logger.exception("Bulk upload batch %s: could not refresh status", batch_id)
