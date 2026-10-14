# Backend/API_Layer/routes/gstr2b_route.py
"""GSTR-2B reconciliation (mounted at /apm/gst/gstr2b).

View: the GST ITC view permissions. Import: GST_ITC_MANAGE or AP_AUTOMATION_MANAGE.
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.Business_Layer.services.gst_itc_service import MANAGE_PERMISSIONS, VIEW_PERMISSIONS
from Backend.Business_Layer.services.gstr2b_service import CSV_COLUMNS, Gstr2bService

router = APIRouter()
MAX_BYTES = 10 * 1024 * 1024


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    user_id = user.get("user_id") or user.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token payload missing user identifier")
    return str(user_id)


@router.get("", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def reconciliation(request: Request, period: Optional[datetime.date] = Query(None, description="Any day of the return month")):
    """The imported periods and, for the chosen one, every filed document with its match plus the
    invoices in the books the suppliers have not filed (missing in 2B)."""
    return JSONResponse(jsonable_encoder(Gstr2bService(request.state.db).reconciliation(period)))


@router.get("/template", dependencies=[Depends(permission_based_access(VIEW_PERMISSIONS))])
def template():
    """CSV layout for suppliers' documents when the portal JSON is not available."""
    return Response(",".join(CSV_COLUMNS) + "\n", media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="gstr2b_template.csv"'})


@router.post("/import", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
async def import_file(request: Request, file: UploadFile = File(...), period: Optional[datetime.date] = Form(None)):
    """Imports a GSTR-2B (portal JSON or CSV) and matches it against the books. Re-importing a period replaces it."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="The file is empty")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB")
    try:
        return JSONResponse(jsonable_encoder(Gstr2bService(request.state.db).import_file(
            file.filename or "gstr2b.json", content, _user_id(request), period)))
    except ValueError as exc:
        request.state.db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/rematch", dependencies=[Depends(permission_based_access(MANAGE_PERMISSIONS))])
def rematch(request: Request):
    """Re-checks every unmatched document against the books (e.g. after booking invoices the suppliers filed)."""
    return {"changed": Gstr2bService(request.state.db).rematch(user_id=_user_id(request))}
