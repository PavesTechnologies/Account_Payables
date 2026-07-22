# Backend/API_Layer/routes/master_route.py

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.master_interface import (
    DeletePaymentTermResponse,
    DeleteTaxTypeResponse,
    PaymentTermDTO,
    PaymentTermRequest,
    PaymentTermResponse,
    PaymentTermUpdateRequest,
    SystemConfigDTO,
    SystemConfigUpdateRequest,
    TaxTypeDTO,
    TaxTypeRequest,
    TaxTypeResponse,
    TaxTypeUpdateRequest,
    UpdateSystemConfigResponse,
)
from Backend.Business_Layer.services.master_service import MasterService

router = APIRouter()


def _get_user_id(http_request: Request) -> str:
    user_id = (
        http_request.state.user.get("user_id")
        or http_request.state.user.get("sub")
    )

    if user_id is None:
        raise ValueError("Token payload missing user identifier")

    return user_id


# ---------------------------------------------------------
# Create Tax Type
# ---------------------------------------------------------
@router.post("/tax-type", response_model=TaxTypeResponse)
def create_tax_type(payload: TaxTypeRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = MasterService(db)
        tax_type = service.create_tax_type(payload, user_id)

        return TaxTypeResponse(
            tax_type_id=tax_type.tax_type_id,
            message="Tax type created successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Tax type with this country, tax_code and effective_from already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get All Tax Types
# ---------------------------------------------------------
@router.get("/tax-type", response_model=list[TaxTypeDTO])
def get_all_tax_types(http_request: Request, country_id: int | None = None):
    db = http_request.state.db

    try:
        service = MasterService(db)
        return service.get_all_tax_types(country_id)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get Tax Type By ID
# ---------------------------------------------------------
@router.get("/tax-type/{tax_type_id}", response_model=TaxTypeDTO)
def get_tax_type_by_id(tax_type_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = MasterService(db)
        return service.get_tax_type_by_id(tax_type_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Update Tax Type
# ---------------------------------------------------------
@router.put("/tax-type/{tax_type_id}", response_model=TaxTypeDTO)
def update_tax_type(
    tax_type_id: int,
    payload: TaxTypeUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = MasterService(db)
        return service.update_tax_type(tax_type_id, payload, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == "Tax type not found" else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Delete Tax Type
# ---------------------------------------------------------
@router.delete("/tax-type/{tax_type_id}", response_model=DeleteTaxTypeResponse)
def delete_tax_type(tax_type_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = MasterService(db)
        service.delete_tax_type(tax_type_id)

        return DeleteTaxTypeResponse(message="Tax type deleted successfully")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))

    except PermissionError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Create Payment Term
# ---------------------------------------------------------
@router.post("/payment-term", response_model=PaymentTermResponse)
def create_payment_term(payload: PaymentTermRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = MasterService(db)
        payment_term = service.create_payment_term(payload, user_id)

        return PaymentTermResponse(
            payment_term_id=payment_term.payment_term_id,
            message="Payment term created successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Payment term with this name already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get All Payment Terms
# ---------------------------------------------------------
@router.get("/payment-term", response_model=list[PaymentTermDTO])
def get_all_payment_terms(http_request: Request):
    db = http_request.state.db

    try:
        service = MasterService(db)
        return service.get_all_payment_terms()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get Payment Term By ID
# ---------------------------------------------------------
@router.get("/payment-term/{payment_term_id}", response_model=PaymentTermDTO)
def get_payment_term_by_id(payment_term_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = MasterService(db)
        return service.get_payment_term_by_id(payment_term_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Update Payment Term
# ---------------------------------------------------------
@router.put("/payment-term/{payment_term_id}", response_model=PaymentTermDTO)
def update_payment_term(
    payment_term_id: int,
    payload: PaymentTermUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = MasterService(db)
        return service.update_payment_term(payment_term_id, payload, user_id)

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Delete Payment Term
# ---------------------------------------------------------
@router.delete("/payment-term/{payment_term_id}", response_model=DeletePaymentTermResponse)
def delete_payment_term(payment_term_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = MasterService(db)
        service.delete_payment_term(payment_term_id)

        return DeletePaymentTermResponse(message="Payment term deleted successfully")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))

    except PermissionError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get All System Configurations
# ---------------------------------------------------------
@router.get("/system-configuration", response_model=list[SystemConfigDTO])
def get_all_system_configs(http_request: Request):
    db = http_request.state.db

    try:
        service = MasterService(db)
        return service.get_all_system_configs()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get System Configuration By Key
# ---------------------------------------------------------
@router.get("/system-configuration/{config_key}", response_model=SystemConfigDTO)
def get_system_config_by_key(config_key: str, http_request: Request):
    db = http_request.state.db

    try:
        service = MasterService(db)
        return service.get_system_config_by_key(config_key)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Update System Configuration Value
# ---------------------------------------------------------
@router.put("/system-configuration/{config_key}", response_model=SystemConfigDTO)
def update_system_config(
    config_key: str,
    payload: SystemConfigUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = MasterService(db)
        return service.update_system_config(config_key, payload, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == "Configuration key not found" else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
