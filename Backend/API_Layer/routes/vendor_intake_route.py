# Backend/API_Layer/routes/vendor_intake_route.py
"""Vendor Intake + Pre-Screen endpoints.

ROUTE ORDER MATTERS HERE. FastAPI matches routes in declaration order, so
every literal path (``/screening-rules``, ``/vendor/{vendor_id}``) must be
declared BEFORE the single-segment dynamic route ``/{engagement_id}`` -
otherwise ``GET /apm/vendor-intake/screening-rules`` is captured by
``/{engagement_id}`` and fails trying to parse "screening-rules" as an int.
Keep new literal paths above the "Vendor Engagement (dynamic paths)" section.
"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.vendor_intake_interface import (
    NdaDecisionRequest,
    NdaDecisionResponse,
    PreScreenResultResponse,
    VendorEngagementDTO,
    VendorIntakeCreateRequest,
    VendorIntakeResponse,
    VendorScreeningRuleDTO,
    VendorScreeningRuleRequest,
    VendorScreeningRuleResponse,
)
from Backend.Business_Layer.services.vendor_intake_service import (
    VendorIntakeService,
    nda_document_status,
)
from Backend.Data_Access_Layer.models.vendor import VendorEngagement
from Backend.Data_Access_Layer.models.vendor_screening_rule import VendorScreeningRule

router = APIRouter()


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


def _to_engagement_dto(engagement: VendorEngagement) -> VendorEngagementDTO:
    # A recorded decision wins over the business-rule recommendation.
    effective_nda = (
        engagement.nda_final_required
        if engagement.nda_final_required is not None
        else engagement.nda_recommended
    )

    return VendorEngagementDTO(
        engagement_id=engagement.vendor_category_mapping_id,
        vendor_id=engagement.vendor_id,
        department_id=engagement.department_id,
        category_id=engagement.purchase_category_id,
        business_requirement=engagement.business_requirement,
        purpose_of_onboarding=engagement.purpose_of_onboarding,
        pre_screen_status=engagement.pre_screen_status,
        pre_screen_result_reason=engagement.pre_screen_result_reason,
        pre_screen_checked_at=engagement.pre_screen_checked_at,
        nda_recommended=engagement.nda_recommended,
        nda_override=engagement.nda_override,
        nda_override_reason=engagement.nda_override_reason,
        nda_final_required=engagement.nda_final_required,
        nda_document_status=nda_document_status(effective_nda),
        created_at=engagement.created_at,
        updated_at=engagement.updated_at,
    )


def _to_rule_dto(rule: VendorScreeningRule) -> VendorScreeningRuleDTO:
    return VendorScreeningRuleDTO(
        id=rule.id,
        name=rule.name,
        department_id=rule.department_id,
        purchase_category_id=rule.purchase_category_id,
        requires_nda=rule.requires_nda,
        is_default=rule.is_default,
        is_active=rule.is_active,
        description=rule.description,
    )


_NOT_FOUND_MESSAGES = {
    "Vendor engagement not found",
    "Vendor not found",
    "Screening rule not found",
}


# ---------------------------------------------------------
# Vendor Intake (Save)
# ---------------------------------------------------------
@router.post("", response_model=VendorIntakeResponse)
def create_intake(payload: VendorIntakeCreateRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorIntakeService(db)
        result = service.create_intake(payload, user_id)

        return VendorIntakeResponse(
            engagement_id=result.engagement.vendor_category_mapping_id,
            vendor_id=result.vendor.vendor_id,
            vendor_created=result.vendor_created,
            pre_screen_status=result.engagement.pre_screen_status,
            gst_status=result.gst_status,
            message="Vendor intake saved successfully",
        )

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An engagement already exists for this vendor, department and category",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# Vendor Screening Rule (Business Rule Engine admin config)
#
# Declared before /{engagement_id} - see the module docstring.
# ===========================================================


@router.post("/screening-rules", response_model=VendorScreeningRuleResponse)
def create_screening_rule(payload: VendorScreeningRuleRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorIntakeService(db)
        rule = service.create_screening_rule(payload, user_id)

        return VendorScreeningRuleResponse(id=rule.id, message="Screening rule created successfully")

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A screening rule with this name already exists")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screening-rules", response_model=list[VendorScreeningRuleDTO])
def get_all_screening_rules(http_request: Request):
    db = http_request.state.db

    try:
        service = VendorIntakeService(db)
        return [_to_rule_dto(r) for r in service.list_screening_rules()]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/screening-rules/{rule_id}", response_model=VendorScreeningRuleResponse)
def update_screening_rule(rule_id: int, payload: VendorScreeningRuleRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorIntakeService(db)
        rule = service.update_screening_rule(rule_id, payload, user_id)

        return VendorScreeningRuleResponse(id=rule.id, message="Screening rule updated successfully")

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _NOT_FOUND_MESSAGES else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A screening rule with this name already exists")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# List a Vendor's Engagements (literal /vendor prefix - also
# declared before /{engagement_id})
# ---------------------------------------------------------
@router.get("/vendor/{vendor_id}", response_model=list[VendorEngagementDTO])
def list_engagements_for_vendor(vendor_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorIntakeService(db)
        return [_to_engagement_dto(e) for e in service.list_engagements_for_vendor(vendor_id)]

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# Vendor Engagement (dynamic paths - keep last)
# ===========================================================


@router.get("/{engagement_id}", response_model=VendorEngagementDTO)
def get_engagement(engagement_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorIntakeService(db)
        return _to_engagement_dto(service.get_engagement(engagement_id))

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Pre-Screen
# ---------------------------------------------------------
@router.post("/{engagement_id}/pre-screen", response_model=PreScreenResultResponse)
def run_pre_screen(engagement_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorIntakeService(db)
        outcome = service.run_pre_screen(engagement_id, user_id)

        return PreScreenResultResponse(
            engagement_id=outcome.engagement.vendor_category_mapping_id,
            result=outcome.result,
            reason=outcome.reason,
            checks=outcome.checks,
            nda_recommended=outcome.nda_recommended,
            nda_document_status=nda_document_status(outcome.nda_recommended),
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _NOT_FOUND_MESSAGES else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# NDA Decision
# ---------------------------------------------------------
@router.patch("/{engagement_id}/nda-decision", response_model=NdaDecisionResponse)
def set_nda_decision(engagement_id: int, payload: NdaDecisionRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorIntakeService(db)
        engagement = service.set_nda_decision(
            engagement_id, payload.override_required, payload.reason, user_id
        )

        return NdaDecisionResponse(
            engagement_id=engagement.vendor_category_mapping_id,
            nda_final_required=engagement.nda_final_required,
            nda_document_status=nda_document_status(engagement.nda_final_required),
            message="NDA decision recorded successfully",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _NOT_FOUND_MESSAGES else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
