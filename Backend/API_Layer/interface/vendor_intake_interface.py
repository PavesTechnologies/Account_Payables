# Backend/API_Layer/interface/vendor_intake_interface.py
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# =====================================================
# Vendor Intake (Save)
# =====================================================


class VendorIntakeCreateRequest(BaseModel):
    department_id: int
    category_id: int
    # Separate fields by design: business_requirement is what the vendor is
    # needed for, purpose_of_onboarding is why this vendor specifically.
    business_requirement: Optional[str] = None
    purpose_of_onboarding: Optional[str] = None
    # Optional procurement handoff context, set when this intake originates
    # from a vendor onboarding request raised by a PR Officer. Purely
    # additive - the standalone Register Vendor flow omits it.
    onboarding_request_id: Optional[int] = None

    # GST branch. When gst_registered is True, gstin is required and is
    # verified via the existing GST verification service; vendor_name and
    # the registered address are then auto-filled from that response and
    # any values supplied here for those fields are ignored. When False,
    # gstin must not be supplied, and vendor_name/address are taken as given.
    gst_registered: bool
    gstin: Optional[str] = None

    vendor_name: Optional[str] = None
    country_id: int
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None

    # Preserved, optional vendor fields (same as VendorCreateRequest).
    payment_term_id: Optional[int] = None
    currency_id: Optional[int] = None
    pan_number: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None


class VendorIntakeResponse(BaseModel):
    engagement_id: int
    vendor_id: int
    vendor_created: bool
    pre_screen_status: str
    gst_status: Optional[str] = None
    message: str


class VendorEngagementDTO(BaseModel):
    engagement_id: int
    vendor_id: int
    department_id: int
    category_id: int
    business_requirement: Optional[str]
    purpose_of_onboarding: Optional[str]
    pre_screen_status: str
    pre_screen_result_reason: Optional[str]
    pre_screen_checked_at: Optional[datetime.datetime]
    nda_recommended: Optional[bool]
    nda_override: Optional[bool]
    nda_override_reason: Optional[str]
    nda_final_required: Optional[bool]
    # Derived, never stored: PENDING when an NDA is required, NOT_REQUIRED when
    # it is not, None until Pre-Screen has produced a recommendation. Actual
    # NDA document generation/storage is out of scope.
    nda_document_status: Optional[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime


# =====================================================
# Pre-Screen
# =====================================================


class PreScreenCheckResult(BaseModel):
    name: str
    passed: bool
    # PASS / NEED_INFORMATION / FAIL for this individual check. `passed` alone
    # cannot distinguish "blocked vendor" (FAIL) from "incomplete data"
    # (NEED_INFORMATION), so the frontend renders this rather than deriving it.
    status: str
    reason: Optional[str] = None


class PreScreenResultResponse(BaseModel):
    engagement_id: int
    result: str
    reason: Optional[str] = None
    checks: List[PreScreenCheckResult]
    nda_recommended: bool
    nda_document_status: str


# =====================================================
# NDA Decision
# =====================================================


class NdaDecisionRequest(BaseModel):
    # None = accept the business-rule recommendation as-is.
    # Set = override the recommendation; reason is then required.
    override_required: Optional[bool] = None
    reason: Optional[str] = None


class NdaDecisionResponse(BaseModel):
    engagement_id: int
    nda_final_required: Optional[bool]
    nda_document_status: Optional[str]
    message: str


# =====================================================
# Vendor Screening Rule (Business Rule Engine admin config)
# =====================================================


class VendorScreeningRuleRequest(BaseModel):
    name: str
    department_id: Optional[int] = None
    purchase_category_id: Optional[int] = None
    requires_nda: bool = Field(default=False)
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)
    description: Optional[str] = None


class VendorScreeningRuleDTO(BaseModel):
    id: int
    name: str
    department_id: Optional[int]
    purchase_category_id: Optional[int]
    requires_nda: bool
    is_default: bool
    is_active: bool
    description: Optional[str]


class VendorScreeningRuleResponse(BaseModel):
    id: int
    message: str
