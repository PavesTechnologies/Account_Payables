# Backend/API_Layer/routes/reports_route.py
"""AP reports (mounted at /apm/reports). Each report checks its own permissions in
APReportingService - the list endpoint only returns reports the caller may run, and
running or exporting one the caller may not run is a 403, whatever the frontend shows."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from Backend.Business_Layer.services.ap_reporting_service import APReportingService
from Backend.Business_Layer.utils.report_export import filename_for, to_pdf, to_xlsx

router = APIRouter()

_MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.get("")
def list_reports(request: Request):
    return APReportingService(request.state.db).available_reports(_user(request))


@router.get("/summary")
def report_summary(
    request: Request,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    vendor_id: Optional[int] = None,
    department_id: Optional[int] = None,
    currency: str = Query("INR", min_length=3, max_length=3),
):
    """Period overview for the Reports page (KPI tiles, invoiced vs paid by month, breakdowns).
    Declared before /{report_key} so "summary" is not taken for a report key."""
    user = _user(request)
    try:
        return JSONResponse(jsonable_encoder(APReportingService(request.state.db).report_summary(
            user, from_date, to_date, vendor_id, department_id, currency.upper())))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to build the report summary")


@router.get("/{report_key}")
def run_report(
    report_key: str,
    request: Request,
    from_date: Optional[date] = Query(None, description="Range reports: start (default: 90 days before to_date)"),
    to_date: Optional[date] = Query(None, description="Range reports: end (default: today)"),
    vendor_id: Optional[int] = None,
    department_id: Optional[int] = None,
    months: int = Query(3, ge=1, le=12, description="expected_payments: number of months ahead"),
    format: str = Query("json", pattern="^(json|xlsx|pdf)$"),
):
    user = _user(request)
    service = APReportingService(request.state.db)
    if format != "json" and not service.can_export(user, report_key):
        raise HTTPException(status_code=403, detail="You do not have permission to export this report")
    try:
        report = service.run_report(
            report_key, user, from_date, to_date, vendor_id, department_id, months
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404 if "Unknown report" in str(e) else 422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to build the report")

    if format == "json":
        return JSONResponse(jsonable_encoder(report))
    content = to_xlsx(report) if format == "xlsx" else to_pdf(report)
    return Response(
        content=content,
        media_type=_MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{filename_for(report, format)}"'},
    )
