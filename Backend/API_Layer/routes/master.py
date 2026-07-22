# Backend/API_Layer/routes/master.py

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.master import (
    CountryRequest,
    CountryResponse,
    CountryDTO,
    CountryListResponse,
    DeleteCountryResponse,
    CurrencyRequest,
    CurrencyResponse,
    CurrencyDTO,
    DeleteCurrencyResponse,
    TaxTypeRequest,
    TaxTypeResponse,
    TaxTypeDTO,
    DeleteTaxTypeResponse,
    VendorCategoryRequest,
    VendorCategoryResponse,
    VendorCategoryDTO,
    DeleteVendorCategoryResponse,
    PaymentTermRequest,
    PaymentTermResponse,
    PaymentTermDTO,
    DeletePaymentTermResponse,
    StatusMasterRequest,
    StatusMasterResponse,
    StatusMasterDTO,
    DeleteStatusMasterResponse,
)


from Backend.Business_Layer.services.master_service import MasterService

router = APIRouter()


# ---------------------------------------------------------
# Create Country
# ---------------------------------------------------------
@router.post("/country", response_model=CountryResponse)
def create_country(
    payload: CountryRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = (
            http_request.state.user.get("user_id")
            or http_request.state.user.get("sub")
        )

        if user_id is None:
            raise ValueError("Token payload missing user identifier")

        service = MasterService(db)

        country = service.create_country(payload, user_id)

        return CountryResponse(
            country_id=country.country_id,
            message="Country created successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Country code already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ---------------------------------------------------------
# Get All Countries
# ---------------------------------------------------------
@router.get(
    "/country",
    response_model=list[CountryDTO],
)
def get_all_countries(http_request: Request):

    db = http_request.state.db

    try:
        print("entering route")
        service = MasterService(db)

        countries = service.get_all_countries()

        return countries

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ---------------------------------------------------------
# Get Country By ID
# ---------------------------------------------------------
@router.get(
    "/country/{country_id}",
    response_model=CountryDTO,
)
def get_country_by_id(
    country_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        country = service.get_country_by_id(country_id)

        return country

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ---------------------------------------------------------
# Delete Country
# ---------------------------------------------------------
@router.delete(
    "/country/{country_id}",
    response_model=DeleteCountryResponse,
)
def delete_country(
    country_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        service.delete_country(country_id)

        return DeleteCountryResponse(
            message="Country deleted successfully"
        )

    except ValueError as e:
        db.rollback()

        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Create Currency
# ---------------------------------------------------------
@router.post("/currency", response_model=CurrencyResponse)
def create_currency(
    payload: CurrencyRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = (
            http_request.state.user.get("user_id")
            or http_request.state.user.get("sub")
        )

        if user_id is None:
            raise ValueError("Token payload missing user identifier")

        service = MasterService(db)

        currency = service.create_currency(payload, user_id)

        return CurrencyResponse(
            currency_id=currency.currency_id,
            message="Currency created successfully",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Currency code already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ---------------------------------------------------------
# Get All Currencies
# ---------------------------------------------------------
@router.get(
    "/currency",
    response_model=list[CurrencyDTO],
)
def get_all_currencies(http_request: Request):

    db = http_request.state.db

    try:
        service = MasterService(db)

        currencies = service.get_all_currencies()

        return currencies

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ---------------------------------------------------------
# Get Currency By ID
# ---------------------------------------------------------
@router.get(
    "/currency/{currency_id}",
    response_model=CurrencyDTO,
)
def get_currency_by_id(
    currency_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        currency = service.get_currency_by_id(currency_id)

        return currency

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ---------------------------------------------------------
# Delete Currency
# ---------------------------------------------------------
@router.delete(
    "/currency/{currency_id}",
    response_model=DeleteCurrencyResponse,
)
def delete_currency(
    currency_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        service.delete_currency(currency_id)

        return DeleteCurrencyResponse(
            message="Currency deleted successfully"
        )

    except ValueError as e:
        db.rollback()

        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
    # ---------------------------------------------------------
# Create Tax Type
# ---------------------------------------------------------
@router.post("/tax-type", response_model=TaxTypeResponse)
def create_tax_type(
    payload: TaxTypeRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = (
            http_request.state.user.get("user_id")
            or http_request.state.user.get("sub")
        )

        if user_id is None:
            raise ValueError("Token payload missing user identifier")

        service = MasterService(db)

        tax_type = service.create_tax_type(payload, user_id)

        return TaxTypeResponse(
            tax_type_id=tax_type.tax_type_id,
            message="Tax Type created successfully",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Tax code already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Get All Tax Types
# ---------------------------------------------------------
@router.get(
    "/tax-type",
    response_model=list[TaxTypeDTO],
)
def get_all_tax_types(http_request: Request):

    db = http_request.state.db

    try:
        service = MasterService(db)

        tax_types = service.get_all_tax_types()

        return tax_types

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Get Tax Type By ID
# ---------------------------------------------------------
@router.get(
    "/tax-type/{tax_type_id}",
    response_model=TaxTypeDTO,
)
def get_tax_type_by_id(
    tax_type_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        tax_type = service.get_tax_type_by_id(tax_type_id)

        return tax_type

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Delete Tax Type
# ---------------------------------------------------------
@router.delete(
    "/tax-type/{tax_type_id}",
    response_model=DeleteTaxTypeResponse,
)
def delete_tax_type(
    tax_type_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        service.delete_tax_type(tax_type_id)

        return DeleteTaxTypeResponse(
            message="Tax Type deleted successfully"
        )

    except ValueError as e:
        db.rollback()

        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Create Vendor Category
# ---------------------------------------------------------
@router.post("/vendor-category", response_model=VendorCategoryResponse)
def create_vendor_category(
    payload: VendorCategoryRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = (
            http_request.state.user.get("user_id")
            or http_request.state.user.get("sub")
        )

        if user_id is None:
            raise ValueError("Token payload missing user identifier")

        service = MasterService(db)

        vendor_category = service.create_vendor_category(payload, user_id)

        return VendorCategoryResponse(
            vendor_category_id=vendor_category.vendor_category_id,
            message="Vendor Category created successfully",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Vendor Category code already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Get All Vendor Categories
# ---------------------------------------------------------
@router.get(
    "/vendor-category",
    response_model=list[VendorCategoryDTO],
)
def get_all_vendor_categories(http_request: Request):

    db = http_request.state.db

    try:
        service = MasterService(db)

        vendor_categories = service.get_all_vendor_categories()

        return vendor_categories

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Get Vendor Category By ID
# ---------------------------------------------------------
@router.get(
    "/vendor-category/{vendor_category_id}",
    response_model=VendorCategoryDTO,
)
def get_vendor_category_by_id(
    vendor_category_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        vendor_category = service.get_vendor_category_by_id(vendor_category_id)

        return vendor_category

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Delete Vendor Category
# ---------------------------------------------------------
@router.delete(
    "/vendor-category/{vendor_category_id}",
    response_model=DeleteVendorCategoryResponse,
)
def delete_vendor_category(
    vendor_category_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        service.delete_vendor_category(vendor_category_id)

        return DeleteVendorCategoryResponse(
            message="Vendor Category deleted successfully"
        )

    except ValueError as e:
        db.rollback()

        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Create Payment Term
# ---------------------------------------------------------
@router.post("/payment-term", response_model=PaymentTermResponse)
def create_payment_term(
    payload: PaymentTermRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = (
            http_request.state.user.get("user_id")
            or http_request.state.user.get("sub")
        )

        if user_id is None:
            raise ValueError("Token payload missing user identifier")

        service = MasterService(db)

        payment_term = service.create_payment_term(payload, user_id)

        return PaymentTermResponse(
            payment_term_id=payment_term.payment_term_id,
            message="Payment Term created successfully",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Payment Term already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Get All Payment Terms
# ---------------------------------------------------------
@router.get(
    "/payment-term",
    response_model=list[PaymentTermDTO],
)
def get_all_payment_terms(http_request: Request):

    db = http_request.state.db

    try:
        service = MasterService(db)

        payment_terms = service.get_all_payment_terms()

        return payment_terms

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Get Payment Term By ID
# ---------------------------------------------------------
@router.get(
    "/payment-term/{payment_term_id}",
    response_model=PaymentTermDTO,
)
def get_payment_term_by_id(
    payment_term_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        payment_term = service.get_payment_term_by_id(payment_term_id)

        return payment_term

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Delete Payment Term
# ---------------------------------------------------------
@router.delete(
    "/payment-term/{payment_term_id}",
    response_model=DeletePaymentTermResponse,
)
def delete_payment_term(
    payment_term_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        service.delete_payment_term(payment_term_id)

        return DeletePaymentTermResponse(
            message="Payment Term deleted successfully"
        )

    except ValueError as e:
        db.rollback()

        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Create Status Master
# ---------------------------------------------------------
@router.post("/status-master", response_model=StatusMasterResponse)
def create_status_master(
    payload: StatusMasterRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = (
            http_request.state.user.get("user_id")
            or http_request.state.user.get("sub")
        )

        if user_id is None:
            raise ValueError("Token payload missing user identifier")

        service = MasterService(db)

        status = service.create_status(payload, user_id)

        return StatusMasterResponse(
            status_id=status.status_id,
            message="Status Master created successfully",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Status code already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Get All Status Masters
# ---------------------------------------------------------
@router.get(
    "/status-master",
    response_model=list[StatusMasterDTO],
)
def get_all_statuses(http_request: Request):

    db = http_request.state.db

    try:
        service = MasterService(db)

        statuses = service.get_all_statuses()

        return statuses

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
# ---------------------------------------------------------
# Get Status Master By ID
# ---------------------------------------------------------
@router.get(
    "/status-master/{status_id}",
    response_model=StatusMasterDTO,
)
def get_status_by_id(
    status_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        status = service.get_status_by_id(status_id)

        return status

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
    
# ---------------------------------------------------------
# Delete Status Master
# ---------------------------------------------------------
@router.delete(
    "/status-master/{status_id}",
    response_model=DeleteStatusMasterResponse,
)
def delete_status(
    status_id: int,
    http_request: Request,
):

    db = http_request.state.db

    try:
        service = MasterService(db)

        service.delete_status(status_id)

        return DeleteStatusMasterResponse(
            message="Status Master deleted successfully"
        )

    except ValueError as e:
        db.rollback()

        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )