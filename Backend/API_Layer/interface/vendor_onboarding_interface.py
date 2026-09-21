# Backend/API_Layer/interface/vendor_onboarding_interface.py
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# =====================================================
# Vendor Availability (PR Officer)
# =====================================================


class AvailableVendorDTO(BaseModel):
    vendor_id: int
    vendor_name: str
    vendor_code: Optional[str]
    email: Optional[str]


class VendorAvailabilityResponse(BaseModel):
    pr_id: int
    department_id: int
    purchase_category_id: int
    available: bool
    vendors: List[AvailableVendorDTO] = Field(default_factory=list)


# =====================================================
# Vendor Onboarding Request
# =====================================================


class VendorOnboardingRequestCreate(BaseModel):
    pr_id: int
    # department_id / purchase_category_id are intentionally NOT accepted here:
    # they are taken from the purchase requisition so the onboarding context can
    # never drift from the PR it belongs to.
    business_requirement: Optional[str] = None
    purpose_of_onboarding: Optional[str] = None
    requested_vendor_name: Optional[str] = None
    requested_vendor_email: Optional[str] = None
    assigned_to: Optional[str] = None


class VendorOnboardingAssignRequest(BaseModel):
    assigned_to: str


class VendorOnboardingStatusUpdateRequest(BaseModel):
    status_code: str
    reason: Optional[str] = None


class VendorOnboardingStartRequest(BaseModel):
    """Vendor identity for the existing Vendor Intake flow. Department,
    category, business requirement and purpose are supplied by the onboarding
    request itself, not by this payload."""

    gst_registered: bool
    gstin: Optional[str] = None
    vendor_name: Optional[str] = None
    country_id: int
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    payment_term_id: Optional[int] = None
    currency_id: Optional[int] = None
    pan_number: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None


class VendorOnboardingRequestDTO(BaseModel):
    id: int
    pr_id: int
    department_id: int
    purchase_category_id: int
    status_id: int
    status_code: Optional[str]
    business_requirement: Optional[str]
    purpose_of_onboarding: Optional[str]
    requested_vendor_name: Optional[str]
    requested_vendor_email: Optional[str]
    vendor_id: Optional[int]
    engagement_id: Optional[int]
    assigned_to: Optional[str]
    closed_at: Optional[datetime.datetime]
    created_by: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class VendorOnboardingResponse(BaseModel):
    id: int
    status_code: Optional[str]
    message: str


class VendorOnboardingStartResponse(BaseModel):
    id: int
    status_code: Optional[str]
    vendor_id: Optional[int]
    engagement_id: Optional[int]
    vendor_created: bool
    gst_status: Optional[str] = None
    message: str


class VendorOnboardingPreScreenResponse(BaseModel):
    id: int
    status_code: Optional[str]
    engagement_id: Optional[int]
    result: str
    reason: Optional[str] = None
    nda_recommended: bool
    message: str


# =====================================================
# RFQ Eligibility
# =====================================================


class EligibilityCheckDTO(BaseModel):
    check: str
    status: str
    passed: bool
    message: Optional[str] = None


class RFQEligibilityResponse(BaseModel):
    pr_id: int
    vendor_id: int
    eligible: bool
    reason: Optional[str] = None
    checks: List[EligibilityCheckDTO] = Field(default_factory=list)
    failed_checks: List[EligibilityCheckDTO] = Field(default_factory=list)


class RFQEligibilityCheckRequest(BaseModel):
    pr_id: int
    vendor_ids: List[int]


class RFQEligibilityBatchResponse(BaseModel):
    pr_id: int
    results: List[RFQEligibilityResponse] = Field(default_factory=list)
