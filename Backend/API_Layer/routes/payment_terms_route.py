# Backend/API_Layer/routes/payment_terms_route.py
"""Payment-term compliance + vendor agreement endpoints (APM_AUTOMATION_PLAN.md 3.1 / 3.1a).

Three routers, mounted in main.py:
  invoice_router    -> /apm/invoice/{invoice_id}/payment-terms[...]
  terms_router      -> /apm/payment-terms/{exceptions,metadata}
  agreement_router  -> /apm/vendor-agreements/...
"""
import datetime
from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status

from Backend.API_Layer.interface.payment_terms_interface import (
    InvoicePaymentTermDTO,
    PaymentTermExceptionPageDTO,
    PaymentTermMetadataDTO,
    PaymentTermVerifyRequest,
    VendorAgreementDecisionRequest,
    VendorAgreementDTO,
    VendorAgreementExtractionDTO,
    VendorAgreementUpdateRequest,
)
from Backend.API_Layer.middleware.permission_base_access import has_permissions, permission_based_access
from Backend.API_Layer.utils.file_validation import validate_upload_file
from Backend.API_Layer.utils.s3_utils import download_from_s3, view_from_s3
from Backend.Business_Layer.services.payment_term_compliance_service import (
    EXCEPTION_STATUSES,
    REASON_TEXT,
    VALIDATION_STATUSES,
    PaymentTermComplianceService,
)
from Backend.Business_Layer.services.vendor_agreement_service import (
    S3_PREFIX,
    AgreementNotFoundError,
    VendorAgreementService,
)
from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, TextractServiceError, UnsupportedFileType
from Backend.Data_Access_Layer.models.payment_terms import AGREEMENT_STATUSES, AGREEMENT_TYPES, DUE_BASES

invoice_router = APIRouter()
terms_router = APIRouter()
agreement_router = APIRouter()

PAYMENT_TERM_VERIFY = "INVOICE_PAYMENT_TERM_VERIFY"
VENDOR_AGREEMENT_VERIFY = "VENDOR_AGREEMENT_VERIFY"
_TERM_VIEW_PERMISSIONS = ["INVOICE_VIEW", "PAYMENT_VIEW", "PAYMENT_PROCESS", PAYMENT_TERM_VERIFY]
_TERM_RECHECK_PERMISSIONS = [PAYMENT_TERM_VERIFY, "PAYMENT_PROCESS", "INVOICE_OCR_REVIEW"]
# Vendor screens are role-gated (Admin / Vendor_Intake) in the frontend; Finance reaches
# agreements through invoices, so either a role or a finance permission is enough to read.
_VENDOR_MANAGER_ROLES = ["Admin", "Vendor_Intake"]
_AGREEMENT_VIEW_PERMISSIONS = [VENDOR_AGREEMENT_VERIFY, PAYMENT_TERM_VERIFY, "PAYMENT_VIEW", "PAYMENT_PROCESS", "INVOICE_VIEW"]
_AGREEMENT_EDIT_PERMISSIONS = [VENDOR_AGREEMENT_VERIFY, PAYMENT_TERM_VERIFY, "PAYMENT_PROCESS"]


def _permission_or_role(permissions: List[str], roles: List[str]) -> Callable:
    def check(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        user_roles = user.get("roles", [])
        user_roles = [user_roles] if isinstance(user_roles, str) else (user_roles or [])
        normalized = {r.strip().lower() for r in user_roles if isinstance(r, str)}
        if has_permissions(user, permissions) or normalized & {r.lower() for r in roles}:
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You do not have permission to access this resource")
    return check


def _user_id(request: Request) -> str:
    user_id = request.state.user.get("user_id") or request.state.user.get("sub")
    if user_id is None:
        raise ValueError("Token payload missing user identifier")
    return user_id


def _fail(e: Exception, db, rollback: bool = True):
    if rollback:
        db.rollback()
    if isinstance(e, HTTPException):
        raise e
    if isinstance(e, PermissionError):
        raise HTTPException(status_code=403, detail=str(e))
    if isinstance(e, AgreementNotFoundError) or (isinstance(e, ValueError) and "not found" in str(e)):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=422, detail=str(e))
    raise HTTPException(status_code=500, detail="Payment-term request failed")


def _parse_date(value: Optional[str], name: str) -> Optional[datetime.date]:
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(value[:10])
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be a date (YYYY-MM-DD)")


def _parse_int(value: Optional[str], name: str) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be a whole number")


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    try:
        validate_upload_file(file, content)
    except (UnsupportedFileType, InvalidUploadFile) as e:
        raise HTTPException(status_code=415 if isinstance(e, UnsupportedFileType) else 400, detail=str(e))
    return content


# ===========================================================================
# Invoice payment terms  (/apm/invoice/...)
# ===========================================================================

@invoice_router.get(
    "/{invoice_id}/payment-terms",
    response_model=InvoicePaymentTermDTO,
    dependencies=[Depends(permission_based_access(_TERM_VIEW_PERMISSIONS))],
)
def get_invoice_payment_terms(invoice_id: int, request: Request):
    db = request.state.db
    try:
        return PaymentTermComplianceService(db).get_summary(invoice_id)
    except Exception as e:
        _fail(e, db, rollback=False)


@invoice_router.post(
    "/{invoice_id}/payment-terms/recheck",
    response_model=InvoicePaymentTermDTO,
    dependencies=[Depends(permission_based_access(_TERM_RECHECK_PERMISSIONS))],
)
def recheck_invoice_payment_terms(invoice_id: int, request: Request):
    """Re-runs the compliance check against the current PO / agreement / vendor-master terms.
    A previous Finance verification is kept unless one of its source terms has changed."""
    db = request.state.db
    try:
        service = PaymentTermComplianceService(db)
        service.evaluate_invoice_id(invoice_id, _user_id(request))
        db.commit()
        return service.get_summary(invoice_id)
    except Exception as e:
        _fail(e, db)


@invoice_router.post(
    "/{invoice_id}/payment-terms/verify",
    response_model=InvoicePaymentTermDTO,
    dependencies=[Depends(permission_based_access([PAYMENT_TERM_VERIFY]))],
)
def verify_invoice_payment_terms(invoice_id: int, payload: PaymentTermVerifyRequest, request: Request):
    """Finance resolves a MISMATCH / REVIEW_REQUIRED by confirming the term days and due basis to
    apply (remarks mandatory, fully audited). Required before Mark Ready for Payment."""
    db = request.state.db
    try:
        service = PaymentTermComplianceService(db)
        service.verify(invoice_id, payload.applied_term_days, payload.due_basis, payload.remarks, _user_id(request))
        db.commit()
        return service.get_summary(invoice_id)
    except Exception as e:
        _fail(e, db)


# ===========================================================================
# Exceptions list + metadata  (/apm/payment-terms/...)
# ===========================================================================

@terms_router.get(
    "/metadata",
    response_model=PaymentTermMetadataDTO,
    dependencies=[Depends(permission_based_access(_TERM_VIEW_PERMISSIONS))],
)
def get_payment_term_metadata():
    return PaymentTermMetadataDTO(
        validation_statuses=list(VALIDATION_STATUSES),
        exception_statuses=list(EXCEPTION_STATUSES),
        reference_sources=["PO", "AGREEMENT", "VENDOR_MASTER", "MANUAL", "NONE"],
        due_bases=list(DUE_BASES),
        reasons=dict(REASON_TEXT),
        agreement_types=list(AGREEMENT_TYPES),
        agreement_statuses=list(AGREEMENT_STATUSES),
        msme_categories=["MICRO", "SMALL", "MEDIUM"],
    )


@terms_router.get(
    "/exceptions",
    response_model=PaymentTermExceptionPageDTO,
    dependencies=[Depends(permission_based_access(_TERM_VIEW_PERMISSIONS))],
)
def list_payment_term_exceptions(
    request: Request,
    status_filter: Optional[List[str]] = Query(None, alias="status"),
    vendor_id: Optional[int] = None,
    reason_code: Optional[str] = None,
    due_from: Optional[datetime.date] = None,
    due_to: Optional[datetime.date] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    db = request.state.db
    try:
        return PaymentTermComplianceService(db).list_exceptions(
            status_filter, vendor_id, reason_code, due_from, due_to, search, page, page_size
        )
    except Exception as e:
        _fail(e, db, rollback=False)


# ===========================================================================
# Vendor agreements  (/apm/vendor-agreements/...)
# ===========================================================================

_view_agreements = Depends(_permission_or_role(_AGREEMENT_VIEW_PERMISSIONS, _VENDOR_MANAGER_ROLES))
_edit_agreements = Depends(_permission_or_role(_AGREEMENT_EDIT_PERMISSIONS, _VENDOR_MANAGER_ROLES))


@agreement_router.get("/expiring", response_model=List[VendorAgreementDTO], dependencies=[_view_agreements])
def list_expiring_agreements(request: Request, within_days: int = Query(30, ge=1, le=365)):
    db = request.state.db
    try:
        return VendorAgreementService(db).list_expiring(within_days)
    except Exception as e:
        _fail(e, db, rollback=False)


@agreement_router.get("/vendor/{vendor_id}", response_model=List[VendorAgreementDTO], dependencies=[_view_agreements])
def list_vendor_agreements(vendor_id: int, request: Request):
    db = request.state.db
    try:
        return VendorAgreementService(db).list_for_vendor(vendor_id)
    except Exception as e:
        _fail(e, db, rollback=False)


@agreement_router.post(
    "/vendor/{vendor_id}/extract", response_model=VendorAgreementExtractionDTO, dependencies=[_edit_agreements]
)
async def extract_vendor_agreement(vendor_id: int, request: Request, file: UploadFile = File(...)):
    """Document -> suggested agreement fields for the upload form. Read-only: nothing is
    persisted; the user reviews/edits the values and then calls the create endpoint."""
    from Backend.API_Layer.utils.agreement_extraction_fields import extract_agreement_from_s3
    from Backend.API_Layer.utils.s3_utils import upload_to_s3

    db = request.state.db
    content = await _read_upload(file)
    service = VendorAgreementService(db)
    try:
        if service.dao.get_vendor(vendor_id) is None:
            raise AgreementNotFoundError(f"Vendor {vendor_id} not found")
        staged = upload_to_s3(file.filename, content, file.content_type, prefix=f"{S3_PREFIX}staged/")
        data = await extract_agreement_from_s3(staged["filepath"])
    except TextractServiceError as e:
        raise HTTPException(status_code=502, detail=f"Agreement extraction failed: {e}")
    except Exception as e:
        _fail(e, db, rollback=False)

    warnings = []
    if data.get("term_days") is None:
        warnings.append("Payment terms could not be read as a number of days - enter them manually.")
    if data.get("valid_from") is None:
        warnings.append("The agreement start date could not be read - enter it manually.")
    if data.get("valid_to") and data["valid_to"] < datetime.date.today():
        warnings.append("The agreement end date is in the past - this agreement has already expired.")
    gstins = service.vendor_gstins(vendor_id)
    if data.get("vendor_gstin") and gstins and data["vendor_gstin"] not in gstins:
        warnings.append(
            f"The GSTIN in the document ({data['vendor_gstin']}) does not match this vendor's registered GSTIN."
        )
    return VendorAgreementExtractionDTO(**data, warnings=warnings)


@agreement_router.post(
    "/vendor/{vendor_id}", response_model=VendorAgreementDTO, status_code=201, dependencies=[_edit_agreements]
)
async def create_vendor_agreement(
    vendor_id: int,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    valid_from: str = Form(...),
    agreement_type: str = Form("OTHER"),
    reference_no: Optional[str] = Form(None),
    valid_to: Optional[str] = Form(None),
    auto_renew: bool = Form(False),
    payment_term_id: Optional[str] = Form(None),
    payment_terms_text: Optional[str] = Form(None),
    term_days: Optional[str] = Form(None),
    due_basis: Optional[str] = Form(None),
    remarks: Optional[str] = Form(None),
    save_as_draft: bool = Form(False),
    extraction_confidence: Optional[str] = Form(None),
):
    db = request.state.db
    content = await _read_upload(file)
    fields = {
        "title": title,
        "agreement_type": agreement_type,
        "reference_no": reference_no,
        "valid_from": _parse_date(valid_from, "valid_from"),
        "valid_to": _parse_date(valid_to, "valid_to"),
        "auto_renew": auto_renew,
        "payment_term_id": _parse_int(payment_term_id, "payment_term_id"),
        "payment_terms_text": payment_terms_text,
        "term_days": _parse_int(term_days, "term_days"),
        "due_basis": due_basis,
        "remarks": remarks,
        "save_as_draft": save_as_draft,
        "extraction_confidence": float(extraction_confidence) if extraction_confidence not in (None, "") else None,
    }
    try:
        return VendorAgreementService(db).create(
            vendor_id, fields, file.filename, content, file.content_type, _user_id(request)
        )
    except Exception as e:
        _fail(e, db)


@agreement_router.get("/{agreement_id}", response_model=VendorAgreementDTO, dependencies=[_view_agreements])
def get_vendor_agreement(agreement_id: int, request: Request):
    db = request.state.db
    try:
        return VendorAgreementService(db).get(agreement_id)
    except Exception as e:
        _fail(e, db, rollback=False)


@agreement_router.patch("/{agreement_id}", response_model=VendorAgreementDTO, dependencies=[_edit_agreements])
def update_vendor_agreement(agreement_id: int, payload: VendorAgreementUpdateRequest, request: Request):
    db = request.state.db
    try:
        return VendorAgreementService(db).update(
            agreement_id, payload.model_dump(exclude_unset=True), _user_id(request)
        )
    except Exception as e:
        _fail(e, db)


@agreement_router.post(
    "/{agreement_id}/verify",
    response_model=VendorAgreementDTO,
    dependencies=[Depends(permission_based_access([VENDOR_AGREEMENT_VERIFY]))],
)
def verify_vendor_agreement(agreement_id: int, payload: VendorAgreementDecisionRequest, request: Request):
    """Four-eyes: the verifier must differ from the uploader. Activation supersedes the vendor's
    previous ACTIVE agreement of the same type and re-checks the vendor's open invoices."""
    db = request.state.db
    try:
        return VendorAgreementService(db).verify(agreement_id, payload.remarks, _user_id(request))
    except Exception as e:
        _fail(e, db)


@agreement_router.post(
    "/{agreement_id}/reject",
    response_model=VendorAgreementDTO,
    dependencies=[Depends(permission_based_access([VENDOR_AGREEMENT_VERIFY]))],
)
def reject_vendor_agreement(agreement_id: int, payload: VendorAgreementDecisionRequest, request: Request):
    db = request.state.db
    try:
        return VendorAgreementService(db).reject(agreement_id, payload.remarks, _user_id(request))
    except Exception as e:
        _fail(e, db)


@agreement_router.get("/{agreement_id}/documents/{document_id}/view", dependencies=[_view_agreements])
def view_vendor_agreement_document(agreement_id: int, document_id: int, request: Request):
    db = request.state.db
    try:
        document = VendorAgreementService(db).get_document(agreement_id, document_id)
    except Exception as e:
        _fail(e, db, rollback=False)
    return view_from_s3(document.file_path)


@agreement_router.get("/{agreement_id}/documents/{document_id}/download", dependencies=[_view_agreements])
def download_vendor_agreement_document(agreement_id: int, document_id: int, request: Request):
    db = request.state.db
    try:
        document = VendorAgreementService(db).get_document(agreement_id, document_id)
    except Exception as e:
        _fail(e, db, rollback=False)
    return download_from_s3(document.file_path)
