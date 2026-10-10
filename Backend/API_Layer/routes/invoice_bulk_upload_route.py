# Backend/API_Layer/routes/invoice_bulk_upload_route.py
"""Bulk invoice upload (APM_AUTOMATION_PLAN.md Phase 3). Every endpoint requires the
INVOICE_BULK_UPLOAD permission. Invoices are created by the same operations as the single
upload (see invoice_bulk_upload_service.py) and land in the OCR review queue."""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from Backend.API_Layer.interface.invoice_bulk_upload_interface import (
    BatchDetail,
    BatchList,
    BatchSummary,
    BulkUploadLimits,
)
from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services import invoice_bulk_upload_service as worker
from Backend.Business_Layer.services.invoice_bulk_upload_service import InvoiceBulkUploadService
from Backend.Business_Layer.utils import bulk_upload_files as files_util
from Backend.Business_Layer.utils.bulk_upload_files import BulkUploadRejected, expand_upload

router = APIRouter()

INVOICE_BULK_UPLOAD = "INVOICE_BULK_UPLOAD"
_PERMISSIONS = [INVOICE_BULK_UPLOAD]


def _user(request: Request):
    user = request.state.user or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    name = user.get("name") or user.get("full_name") or user.get("email")
    return str(user_id), (str(name)[:200] if name else None)


@router.get("/limits", response_model=BulkUploadLimits, dependencies=[Depends(permission_based_access(_PERMISSIONS))])
def get_limits():
    return BulkUploadLimits(
        max_files=files_util.MAX_FILES_PER_BATCH,
        max_file_mb=files_util.MAX_FILE_BYTES // (1024 * 1024),
        max_zip_mb=files_util.MAX_ZIP_BYTES // (1024 * 1024),
        accepted_extensions=sorted(files_util.CONTENT_TYPES) + [".zip"],
    )


@router.post("", response_model=BatchDetail, status_code=202,
             dependencies=[Depends(permission_based_access(_PERMISSIONS))])
async def upload_batch(request: Request, background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """Several invoice files, or one ZIP. Returns at once; files are processed in the background -
    poll GET /batches/{batch_id} for progress."""
    user_id, user_name = _user(request)
    parts = []
    for upload in files:
        # Read at most one byte past the largest allowed part so an oversized upload is rejected
        # without holding the whole thing in memory.
        limit = files_util.MAX_ZIP_BYTES if files_util.is_zip(upload.filename or "", upload.content_type) \
            else files_util.MAX_FILE_BYTES
        parts.append((upload.filename or "", upload.content_type, await upload.read(limit + 1)))
    try:
        candidates, source_name = expand_upload(parts)
    except BulkUploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = InvoiceBulkUploadService(request.state.db)
    batch_id = await run_in_threadpool(service.create_batch, candidates, source_name, user_id, user_name)
    background_tasks.add_task(worker.process_batch, batch_id, user_id)
    return await run_in_threadpool(service.batch_detail, batch_id)


@router.get("/batches", response_model=BatchList, dependencies=[Depends(permission_based_access(_PERMISSIONS))])
def list_batches(
    request: Request,
    mine: bool = Query(True, description="Only batches I uploaded"),
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None, pattern="^(MANUAL_UPLOAD|EMAIL)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    user_id, _ = _user(request)
    rows, total = InvoiceBulkUploadService(request.state.db).list_batches(user_id if mine else None, status, page, page_size, source_type)
    return BatchList(items=[BatchSummary(**r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/batches/{batch_id}", response_model=BatchDetail,
            dependencies=[Depends(permission_based_access(_PERMISSIONS))])
def get_batch(batch_id: int, request: Request):
    try:
        return InvoiceBulkUploadService(request.state.db).batch_detail(batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/batches/{batch_id}/retry", response_model=BatchDetail,
             dependencies=[Depends(permission_based_access(_PERMISSIONS))])
def retry_batch(batch_id: int, request: Request, background_tasks: BackgroundTasks):
    """Retries every file that failed for a fixable reason (vendor not found, extraction / create
    error) and resumes files left behind by a restart."""
    user_id, _ = _user(request)
    service = InvoiceBulkUploadService(request.state.db)
    try:
        ids = service.retry_batch(batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(worker.process_batch, batch_id, user_id, ids)
    return service.batch_detail(batch_id)


@router.post("/items/{item_id}/retry", response_model=BatchDetail,
             dependencies=[Depends(permission_based_access(_PERMISSIONS))])
def retry_item(item_id: int, request: Request, background_tasks: BackgroundTasks):
    user_id, _ = _user(request)
    service = InvoiceBulkUploadService(request.state.db)
    try:
        item = service.retry_item(item_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(worker.process_batch, item.batch_id, user_id, [item.item_id])
    return service.batch_detail(item.batch_id)


@router.post("/items/{item_id}/skip", response_model=BatchDetail,
             dependencies=[Depends(permission_based_access(_PERMISSIONS))])
def skip_item(item_id: int, request: Request):
    service = InvoiceBulkUploadService(request.state.db)
    try:
        item = service.skip_item(item_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return service.batch_detail(item.batch_id)
