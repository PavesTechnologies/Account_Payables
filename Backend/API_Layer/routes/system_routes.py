# Backend/API_Layer/routes/master.py

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.system_interface import (
    CountryRequest,
    CountryResponse,
    CountryDTO,
    CountryListResponse,
    DeleteCountryResponse,
    CurrencyRequest,
    CurrencyResponse,
    CurrencyDTO,
    DeleteCurrencyResponse
)


from Backend.Business_Layer.services.system_service import MasterService

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
