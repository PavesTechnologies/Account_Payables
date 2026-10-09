# Backend/API_Layer/routes/dashboard_route.py
"""AP Dashboard (mounted at /apm/dashboard). Any authenticated user may call
it (JWTMiddleware already rejects unauthenticated requests); WHAT comes back
is decided server-side from the caller's own JWT permissions/roles by
DashboardService - a user with no AP permissions gets empty sections, never
someone else's data. No user id is accepted from the client."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from Backend.API_Layer.middleware.permission_base_access import has_permissions
from Backend.Business_Layer.services.ap_reporting_service import FINANCE_PERMISSIONS, APReportingService
from Backend.Business_Layer.services.role_dashboard_service import RoleDashboardService

from Backend.API_Layer.interface.dashboard_interface import DashboardActivityPageDTO, DashboardSummaryDTO
from Backend.Business_Layer.services.dashboard_service import ACTIVITY_PAGE_SIZE, DashboardService

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryDTO)
def get_dashboard_summary(
    http_request: Request,
    from_date: Optional[date] = Query(None, description="Start of the period for trends / period amounts / recent activity (default: last 30 days)"),
    to_date: Optional[date] = Query(None, description="End of the period (default: today)"),
):
    user = getattr(http_request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    db = http_request.state.db
    try:
        return DashboardService(db).get_summary(user, from_date, to_date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to build the dashboard")


@router.get("/activity", response_model=DashboardActivityPageDTO)
def get_dashboard_activity(
    http_request: Request,
    search: Optional[str] = Query(None, max_length=100, description="Matches invoice number, PR number, vendor name or activity type"),
    entity_type: Optional[str] = Query(None, description="invoice / purchase_requisition / vendor"),
    from_date: Optional[date] = Query(None, description="Start of the period (default: last 30 days)"),
    to_date: Optional[date] = Query(None, description="End of the period (default: today)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(ACTIVITY_PAGE_SIZE, ge=1, le=100),
):
    user = getattr(http_request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    db = http_request.state.db
    try:
        return DashboardService(db).get_activity(user, search, entity_type, from_date, to_date, page, page_size)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to load activity")


@router.get("/finance")
def get_finance_dashboard(http_request: Request):
    """Finance Executive operational dashboard: what needs paying, what is overdue, what is
    coming up, and payment-term / TDS / receipt follow-ups. PAYMENT_VIEW or PAYMENT_PROCESS
    required; the TDS block is included only for users holding a TDS permission."""
    user = getattr(http_request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not has_permissions(user, FINANCE_PERMISSIONS):
        raise HTTPException(status_code=403, detail="You do not have permission to access this resource")
    try:
        return JSONResponse(jsonable_encoder(APReportingService(http_request.state.db).finance_dashboard(user)))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to build the finance dashboard")


@router.get("/views")
def get_dashboard_views(http_request: Request):
    """The role dashboards this user may open (Management / Finance / Approvals / My work), in
    display order - decided from the JWT permissions, so the frontend never guesses."""
    user = getattr(http_request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return RoleDashboardService.views_for(user)


@router.get("/view/{view_key}")
def get_role_dashboard(view_key: str, http_request: Request):
    """One role dashboard. Each view checks its own permissions server-side (403 otherwise)."""
    user = getattr(http_request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return JSONResponse(jsonable_encoder(RoleDashboardService(http_request.state.db).build(view_key, user)))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to build the dashboard")
