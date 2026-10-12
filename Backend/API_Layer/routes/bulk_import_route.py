# Backend/API_Layer/routes/bulk_import_route.py
"""Bulk import of payments / TDS challans / TDS filings from Excel + documents (6.7).
Each import type needs the permission of the area it writes to: payments -> PAYMENT_PROCESS,
challans / filings -> TDS_TRACKING_UPDATE (checked per job as well as per route)."""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from Backend.API_Layer.middleware.permission_base_access import has_permissions, permission_based_access
from Backend.Business_Layer.services import bulk_import_service as importer
from Backend.Business_Layer.services.bulk_import_service import PERMISSIONS, BulkImportService
from Backend.Data_Access_Layer.models.bulk_import import KIND_PAYMENTS, KIND_TDS_CHALLANS, KIND_TDS_FILINGS, BulkImportRow

router = APIRouter()

_KIND_BY_PATH = {"payments": KIND_PAYMENTS, "tds-challans": KIND_TDS_CHALLANS, "tds-filings": KIND_TDS_FILINGS}
_ANY = sorted({p for perms in PERMISSIONS.values() for p in perms})
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_WORKBOOK_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 300 * 1024 * 1024


class RecordRequest(BaseModel):
    row_ids: Optional[List[int]] = None
    accept_review: bool = False


def _user(request: Request):
    user = request.state.user or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id), user.get("name") or user.get("email")


def _kind(path_kind: str, request: Request) -> str:
    kind = _KIND_BY_PATH.get(path_kind)
    if kind is None:
        raise HTTPException(status_code=404, detail="Unknown import type")
    _require(kind, request)
    return kind


def _require(kind: str, request: Request) -> None:
    if not has_permissions(request.state.user, PERMISSIONS[kind]):
        raise HTTPException(status_code=403, detail="You do not have permission for this import")


def _job_kind(service: BulkImportService, job_id: int, request: Request):
    try:
        job = service._job(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require(job.kind, request)
    return job


@router.get("/{path_kind}/template", dependencies=[Depends(permission_based_access(_ANY))])
def download_template(path_kind: str, request: Request):
    kind = _kind(path_kind, request)
    content = BulkImportService(request.state.db).template(kind)
    return Response(content, media_type=_XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{path_kind}-import-template.xlsx"'})


@router.post("/{path_kind}", status_code=202, dependencies=[Depends(permission_based_access(_ANY))])
async def upload(path_kind: str, request: Request, background_tasks: BackgroundTasks,
                 workbook: UploadFile = File(...), documents: List[UploadFile] = File(default=[])):
    """The filled sheet plus its documents (loose files and / or ZIPs). Returns at once; the
    documents are read in the background - poll GET /jobs/{job_id}."""
    kind = _kind(path_kind, request)
    if not (workbook.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload the sheet as .xlsx (download the template).")
    book = await workbook.read(MAX_WORKBOOK_BYTES + 1)
    if len(book) > MAX_WORKBOOK_BYTES:
        raise HTTPException(status_code=413, detail="The sheet is larger than 5 MB.")
    docs, total = [], 0
    for doc in documents:
        content = await doc.read(MAX_UPLOAD_BYTES + 1)
        total += len(content)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="The documents are larger than 300 MB - split the sheet.")
        docs.append((doc.filename or "document", doc.content_type, content))
    user_id, name = _user(request)
    service = BulkImportService(request.state.db)
    try:
        job_id = await run_in_threadpool(service.create_job, kind, (workbook.filename, book), docs, user_id, name)
    except ValueError as exc:
        request.state.db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(importer.validate_job, job_id, user_id)
    return await run_in_threadpool(service.job_detail, job_id)


@router.get("/jobs", dependencies=[Depends(permission_based_access(_ANY))])
def list_jobs(request: Request, kind: Optional[str] = Query(None), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    wanted = _KIND_BY_PATH.get(kind) if kind else None
    if kind and wanted is None:
        raise HTTPException(status_code=404, detail="Unknown import type")
    if wanted:
        _require(wanted, request)
    return BulkImportService(request.state.db).list_jobs(wanted, page, page_size)


@router.get("/jobs/{job_id}", dependencies=[Depends(permission_based_access(_ANY))])
def get_job(job_id: int, request: Request):
    service = BulkImportService(request.state.db)
    _job_kind(service, job_id, request)
    return service.job_detail(job_id)


@router.post("/jobs/{job_id}/record", dependencies=[Depends(permission_based_access(_ANY))])
def record(job_id: int, body: RecordRequest, request: Request):
    """Record the verified rows (or the chosen ones; rows needing review only with accept_review)."""
    service = BulkImportService(request.state.db)
    _job_kind(service, job_id, request)
    user_id, _ = _user(request)
    summary = service.record(job_id, user_id, body.row_ids, body.accept_review)
    return {**service.job_detail(job_id), "summary": summary}


@router.post("/rows/{row_id}/skip", dependencies=[Depends(permission_based_access(_ANY))])
def skip(row_id: int, request: Request):
    service = BulkImportService(request.state.db)
    row = request.state.db.query(BulkImportRow).filter(BulkImportRow.row_id == row_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Row not found")
    _require(row.job.kind, request)  # before anything changes
    try:
        job = service.skip(row_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return service.job_detail(job.job_id)


@router.get("/jobs/{job_id}/results", dependencies=[Depends(permission_based_access(_ANY))])
def results(job_id: int, request: Request):
    service = BulkImportService(request.state.db)
    _job_kind(service, job_id, request)
    name, content = service.results_workbook(job_id)
    return Response(content, media_type=_XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})
