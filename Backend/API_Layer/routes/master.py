# Backend/API_Layer/routes/master.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.master import CountryRequest, CountryResponse
from Backend.Business_Layer.services.master_service import MasterService

router = APIRouter()

@router.post("/country", response_model=CountryResponse)
def create_country(
    payload: CountryRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = http_request.state.user.get("user_id") or http_request.state.user.get("sub")
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
        raise HTTPException(status_code=409, detail="Country code already exists")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))