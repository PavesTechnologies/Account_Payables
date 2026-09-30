# Backend/API_Layer/routes/tds_config_route.py
"""TDS Configuration APIs (mounted at /apm/tds/config): TDS rules, payment
natures, deductors, Excel/CSV import. Finance-owned configuration - kept on
its own TDS_CONFIG_* permissions, separate from System Configuration (Admin),
enforced here server-side (403), not just hidden in the UI.

Error mapping (same as approval_policy_route.py / tds_route.py):
    TdsConfigNotFoundError -> 404, TdsConfigConflictError -> 409,
    other ValueError -> 422, IntegrityError -> 409, anything else -> 500.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.tds_config_interface import (
    TdsConditionTypeDTO,
    TdsConfigMetadataDTO,
    TdsDeleteResponse,
    TdsImportReportDTO,
    TdsMasterCreateRequest,
    TdsMasterDTO,
    TdsMasterUpdateRequest,
    TdsOptionDTO,
    TdsRuleDTO,
    TdsRuleRequest,
    TdsStatusRequest,
)
from Backend.API_Layer.middleware.permission_base_access import has_permissions, permission_based_access
from Backend.Business_Layer.services.tds_config_import_service import (
    IMPORT_COLUMNS,
    TdsConfigImportService,
    TdsImportFileError,
    TdsImportPermissionError,
)
from Backend.Business_Layer.services.tds_config_service import (
    THRESHOLD_PERIOD_LABELS,
    TdsConfigConflictError,
    TdsConfigNotFoundError,
    TdsConfigService,
)
from Backend.Business_Layer.utils.tds_rate_condition import SUPPORTED_CONDITION_VALUES

router = APIRouter()

TDS_CONFIG_VIEW = "TDS_CONFIG_VIEW"
TDS_CONFIG_CREATE = "TDS_CONFIG_CREATE"
TDS_CONFIG_EDIT = "TDS_CONFIG_EDIT"
TDS_CONFIG_DELETE = "TDS_CONFIG_DELETE"
TDS_CONFIG_IMPORT = "TDS_CONFIG_IMPORT"

# Anyone who can change TDS configuration can also read it.
_CONFIG_VIEW_PERMISSIONS = [TDS_CONFIG_VIEW, TDS_CONFIG_CREATE, TDS_CONFIG_EDIT, TDS_CONFIG_DELETE, TDS_CONFIG_IMPORT]

# The payment-nature list also backs the AP Executive's "Correct Payment
# Nature" dropdown on the invoice TDS panel, so the invoice-TDS permissions
# (see tds_route.py) may read it too - read-only, list/get only.
_PAYMENT_NATURE_READ_PERMISSIONS = _CONFIG_VIEW_PERMISSIONS + [
    "INVOICE_TDS_VIEW",
    "INVOICE_TDS_DETERMINE",
    "INVOICE_TDS_EDIT",
    "INVOICE_TDS_VERIFY",
]


def _get_user_id(http_request: Request) -> str:
    user_id = http_request.state.user.get("user_id") or http_request.state.user.get("sub")
    if user_id is None:
        raise ValueError("Token payload missing user identifier")
    return user_id


def _raise_http(e: Exception, db, rollback: bool = True):
    if rollback:
        db.rollback()
    if isinstance(e, TdsConfigNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, TdsConfigConflictError):
        raise HTTPException(status_code=409, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(e, IntegrityError):
        raise HTTPException(status_code=409, detail="The change conflicts with existing TDS configuration")
    raise HTTPException(status_code=500, detail=str(e))


def _rule_raw(payload: TdsRuleRequest) -> dict:
    return {
        "code": payload.code,
        "old_section": payload.old_section,
        "new_section": payload.new_section,
        "payment_nature": payload.payment_nature_id if payload.payment_nature_id is not None else payload.payment_nature_code,
        "deductor": payload.deductor_id if payload.deductor_id is not None else payload.deductor_code,
        "rate": payload.rate,
        "threshold_amount": payload.threshold_amount,
        "threshold_period": payload.threshold_period,
        "rate_condition": payload.rate_condition,
        "effective_from": payload.effective_from,
        "effective_to": payload.effective_to,
        "rule_name": payload.rule_name,
        "description": payload.description,
        "legal_reference": payload.legal_reference,
        "priority": payload.priority,
        "is_active": payload.is_active,
    }


# =========================================================
# Metadata
# =========================================================

@router.get(
    "/metadata",
    response_model=TdsConfigMetadataDTO,
    dependencies=[Depends(permission_based_access(_CONFIG_VIEW_PERMISSIONS))],
)
def get_metadata():
    return TdsConfigMetadataDTO(
        threshold_periods=[TdsOptionDTO(value=code, label=label) for code, label in THRESHOLD_PERIOD_LABELS.items()],
        rate_condition_types=[
            TdsConditionTypeDTO(condition_type=t, operators=["EQUALS", "NOT_EQUALS", "IN", "NOT_IN"], values=sorted(values))
            for t, values in sorted(SUPPORTED_CONDITION_VALUES.items())
        ],
        rate_condition_example="ENTITY_TYPE IN INDIVIDUAL,HUF",
        import_columns=list(IMPORT_COLUMNS),
        import_file_types=[".xlsx", ".csv"],
    )


# =========================================================
# TDS rules
# =========================================================

@router.get(
    "/rules",
    response_model=List[TdsRuleDTO],
    dependencies=[Depends(permission_based_access(_CONFIG_VIEW_PERMISSIONS))],
)
def list_rules(
    http_request: Request,
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="ACTIVE, INACTIVE or ALL (default ALL)"),
    payment_nature: Optional[str] = Query(None, description="Payment nature code"),
    effective_date: Optional[date] = Query(None, description="Only rules in effect on this date"),
    deductor_id: Optional[int] = Query(None),
):
    db = http_request.state.db
    try:
        return TdsConfigService(db).list_rules(search, status, payment_nature, effective_date, deductor_id)
    except Exception as e:
        _raise_http(e, db, rollback=False)


@router.get(
    "/rules/{rule_id}",
    response_model=TdsRuleDTO,
    dependencies=[Depends(permission_based_access(_CONFIG_VIEW_PERMISSIONS))],
)
def get_rule(rule_id: int, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).get_rule(rule_id)
    except Exception as e:
        _raise_http(e, db, rollback=False)


@router.post(
    "/rules",
    response_model=TdsRuleDTO,
    status_code=201,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_CREATE]))],
)
def create_rule(payload: TdsRuleRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).create_rule(_rule_raw(payload), _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.put(
    "/rules/{rule_id}",
    response_model=TdsRuleDTO,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_EDIT]))],
)
def update_rule(rule_id: int, payload: TdsRuleRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).update_rule(rule_id, _rule_raw(payload), _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.patch(
    "/rules/{rule_id}/status",
    response_model=TdsRuleDTO,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_EDIT]))],
)
def set_rule_status(rule_id: int, payload: TdsStatusRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).set_rule_status(rule_id, payload.is_active, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.delete(
    "/rules/{rule_id}",
    response_model=TdsDeleteResponse,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_DELETE]))],
)
def delete_rule(rule_id: int, http_request: Request):
    """Only for rules no invoice TDS determination references - otherwise 409
    (deactivate via PATCH .../status instead)."""
    db = http_request.state.db
    try:
        TdsConfigService(db).delete_rule(rule_id, _get_user_id(http_request))
        return TdsDeleteResponse(id=rule_id, message="TDS rule deleted successfully")
    except Exception as e:
        _raise_http(e, db)


# =========================================================
# Import (validate never writes; import is all-or-nothing)
# =========================================================

async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    return file.filename or "", await file.read()


@router.post(
    "/import/validate",
    response_model=TdsImportReportDTO,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_IMPORT]))],
)
async def validate_import(http_request: Request, file: UploadFile = File(...)):
    db = http_request.state.db
    filename, content = await _read_upload(file)
    try:
        report = TdsConfigImportService(db).validate(filename, content)
        db.rollback()  # read-only - make sure nothing lingers in the session
        return report
    except TdsImportFileError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        _raise_http(e, db)


@router.post(
    "/import",
    response_model=TdsImportReportDTO,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_IMPORT]))],
)
async def import_rules(http_request: Request, file: UploadFile = File(...)):
    """Re-validates the file; if any row is invalid nothing is written and the
    full report is returned as the 422 detail. TDS_CONFIG_IMPORT is enough
    unless the file would create payment natures/deductors - then
    TDS_CONFIG_CREATE is also required (403 otherwise, nothing written)."""
    db = http_request.state.db
    filename, content = await _read_upload(file)
    can_create_masters = has_permissions(getattr(http_request.state, "user", None), [TDS_CONFIG_CREATE])
    try:
        report = TdsConfigImportService(db).import_rules(
            filename, content, _get_user_id(http_request), can_create_masters=can_create_masters
        )
    except TdsImportFileError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except TdsImportPermissionError as e:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        _raise_http(e, db)
    if not report["valid"]:
        raise HTTPException(status_code=422, detail=report)
    return report


# =========================================================
# Payment natures
# =========================================================

@router.get(
    "/payment-natures",
    response_model=List[TdsMasterDTO],
    dependencies=[Depends(permission_based_access(_PAYMENT_NATURE_READ_PERMISSIONS))],
)
def list_payment_natures(
    http_request: Request,
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    db = http_request.state.db
    try:
        return TdsConfigService(db).list_payment_natures(search, is_active)
    except Exception as e:
        _raise_http(e, db, rollback=False)


@router.get(
    "/payment-natures/{nature_id}",
    response_model=TdsMasterDTO,
    dependencies=[Depends(permission_based_access(_PAYMENT_NATURE_READ_PERMISSIONS))],
)
def get_payment_nature(nature_id: int, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).get_payment_nature(nature_id)
    except Exception as e:
        _raise_http(e, db, rollback=False)


@router.post(
    "/payment-natures",
    response_model=TdsMasterDTO,
    status_code=201,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_CREATE]))],
)
def create_payment_nature(payload: TdsMasterCreateRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).create_payment_nature(payload, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.put(
    "/payment-natures/{nature_id}",
    response_model=TdsMasterDTO,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_EDIT]))],
)
def update_payment_nature(nature_id: int, payload: TdsMasterUpdateRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).update_payment_nature(nature_id, payload, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.patch(
    "/payment-natures/{nature_id}/status",
    response_model=TdsMasterDTO,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_EDIT]))],
)
def set_payment_nature_status(nature_id: int, payload: TdsStatusRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).set_payment_nature_status(nature_id, payload.is_active, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.delete(
    "/payment-natures/{nature_id}",
    response_model=TdsDeleteResponse,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_DELETE]))],
)
def delete_payment_nature(nature_id: int, http_request: Request):
    db = http_request.state.db
    try:
        TdsConfigService(db).delete_payment_nature(nature_id, _get_user_id(http_request))
        return TdsDeleteResponse(id=nature_id, message="TDS payment nature deleted successfully")
    except Exception as e:
        _raise_http(e, db)


# =========================================================
# Deductors
# =========================================================

@router.get(
    "/deductors",
    response_model=List[TdsMasterDTO],
    dependencies=[Depends(permission_based_access(_CONFIG_VIEW_PERMISSIONS))],
)
def list_deductors(
    http_request: Request,
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    db = http_request.state.db
    try:
        return TdsConfigService(db).list_deductors(search, is_active)
    except Exception as e:
        _raise_http(e, db, rollback=False)


@router.get(
    "/deductors/{deductor_id}",
    response_model=TdsMasterDTO,
    dependencies=[Depends(permission_based_access(_CONFIG_VIEW_PERMISSIONS))],
)
def get_deductor(deductor_id: int, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).get_deductor(deductor_id)
    except Exception as e:
        _raise_http(e, db, rollback=False)


@router.post(
    "/deductors",
    response_model=TdsMasterDTO,
    status_code=201,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_CREATE]))],
)
def create_deductor(payload: TdsMasterCreateRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).create_deductor(payload, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.put(
    "/deductors/{deductor_id}",
    response_model=TdsMasterDTO,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_EDIT]))],
)
def update_deductor(deductor_id: int, payload: TdsMasterUpdateRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).update_deductor(deductor_id, payload, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.patch(
    "/deductors/{deductor_id}/status",
    response_model=TdsMasterDTO,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_EDIT]))],
)
def set_deductor_status(deductor_id: int, payload: TdsStatusRequest, http_request: Request):
    db = http_request.state.db
    try:
        return TdsConfigService(db).set_deductor_status(deductor_id, payload.is_active, _get_user_id(http_request))
    except Exception as e:
        _raise_http(e, db)


@router.delete(
    "/deductors/{deductor_id}",
    response_model=TdsDeleteResponse,
    dependencies=[Depends(permission_based_access([TDS_CONFIG_DELETE]))],
)
def delete_deductor(deductor_id: int, http_request: Request):
    db = http_request.state.db
    try:
        TdsConfigService(db).delete_deductor(deductor_id, _get_user_id(http_request))
        return TdsDeleteResponse(id=deductor_id, message="TDS deductor deleted successfully")
    except Exception as e:
        _raise_http(e, db)
