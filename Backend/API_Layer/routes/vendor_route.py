# Backend/API_Layer/routes/vendor_route.py

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from Backend.API_Layer.interface.vendor_interface import (
    DeleteVendorAddressResponse,
    DeleteVendorBankResponse,
    DeleteVendorTaxResponse,
    VendorAddressCreateRequest,
    VendorAddressDTO,
    VendorAddressResponse,
    VendorAddressUpdateRequest,
    VendorBankCreateRequest,
    VendorBankDTO,
    VendorBankResponse,
    VendorBankUpdateRequest,
    VendorCreateRequest,
    VendorDTO,
    VendorResponse,
    VendorStatusUpdateRequest,
    VendorTaxCreateRequest,
    VendorTaxDTO,
    VendorTaxResponse,
    VendorTaxUpdateRequest,
    VendorUpdateRequest,
)
from Backend.Business_Layer.services.vendor_service import VendorService

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
# Create Vendor
# ---------------------------------------------------------
@router.post("", response_model=VendorResponse)
def create_vendor(payload: VendorCreateRequest, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        vendor = service.create_vendor(payload, user_id)

        return VendorResponse(
            vendor_id=vendor.vendor_id,
            message="Vendor created successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A vendor with this name or vendor_code already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get All Vendors
# ---------------------------------------------------------
@router.get("", response_model=list[VendorDTO])
def get_all_vendors(
    http_request: Request,
    status_id: Optional[int] = None,
    country_id: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    db = http_request.state.db

    try:
        service = VendorService(db)
        return service.list_vendors(status_id, country_id, search, skip, limit)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Get Vendor By ID (complete vendor profile — includes addresses,
# banks, and taxes via eager-loaded relationships)
# ---------------------------------------------------------
@router.get("/{vendor_id}", response_model=VendorDTO)
def get_vendor_by_id(vendor_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorService(db)
        return service.get_vendor(vendor_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Update Vendor
# ---------------------------------------------------------
@router.put("/{vendor_id}", response_model=VendorDTO)
def update_vendor(
    vendor_id: int,
    payload: VendorUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        return service.update_vendor(vendor_id, payload, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == "Vendor not found" else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A vendor with this name or vendor_code already exists",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Activate / Deactivate Vendor (soft status)
# ---------------------------------------------------------
@router.patch("/{vendor_id}/status", response_model=VendorDTO)
def update_vendor_status(
    vendor_id: int,
    payload: VendorStatusUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        return service.change_status(vendor_id, payload.is_active, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) == "Vendor not found" else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# Vendor Address
# ===========================================================

_ADDRESS_NOT_FOUND = {"Vendor not found", "Address not found"}


@router.post("/{vendor_id}/addresses", response_model=VendorAddressResponse)
def create_vendor_address(
    vendor_id: int,
    payload: VendorAddressCreateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        address = service.create_address(vendor_id, payload, user_id)

        return VendorAddressResponse(
            vendor_address_id=address.vendor_address_id,
            message="Vendor address created successfully",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _ADDRESS_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vendor_id}/addresses", response_model=list[VendorAddressDTO])
def get_vendor_addresses(vendor_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorService(db)
        return service.list_addresses(vendor_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vendor_id}/addresses/{address_id}", response_model=VendorAddressDTO)
def get_vendor_address(vendor_id: int, address_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorService(db)
        return service.get_address(vendor_id, address_id)

    except ValueError as e:
        status_code = 404 if str(e) in _ADDRESS_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{vendor_id}/addresses/{address_id}", response_model=VendorAddressDTO)
def update_vendor_address(
    vendor_id: int,
    address_id: int,
    payload: VendorAddressUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        return service.update_address(vendor_id, address_id, payload, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _ADDRESS_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{vendor_id}/addresses/{address_id}", response_model=DeleteVendorAddressResponse)
def delete_vendor_address(vendor_id: int, address_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        service.delete_address(vendor_id, address_id, user_id)

        return DeleteVendorAddressResponse(message="Vendor address deleted successfully")

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _ADDRESS_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# Vendor Bank
# ===========================================================

_BANK_NOT_FOUND = {"Vendor not found", "Bank not found"}


@router.post("/{vendor_id}/banks", response_model=VendorBankResponse)
def create_vendor_bank(
    vendor_id: int,
    payload: VendorBankCreateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        bank = service.create_bank(vendor_id, payload, user_id)

        return VendorBankResponse(
            vendor_bank_id=bank.vendor_bank_id,
            message="Vendor bank account created successfully",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _BANK_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vendor_id}/banks", response_model=list[VendorBankDTO])
def get_vendor_banks(vendor_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorService(db)
        return service.list_banks(vendor_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vendor_id}/banks/{bank_id}", response_model=VendorBankDTO)
def get_vendor_bank(vendor_id: int, bank_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorService(db)
        return service.get_bank(vendor_id, bank_id)

    except ValueError as e:
        status_code = 404 if str(e) in _BANK_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{vendor_id}/banks/{bank_id}", response_model=VendorBankDTO)
def update_vendor_bank(
    vendor_id: int,
    bank_id: int,
    payload: VendorBankUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        return service.update_bank(vendor_id, bank_id, payload, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _BANK_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{vendor_id}/banks/{bank_id}", response_model=DeleteVendorBankResponse)
def delete_vendor_bank(vendor_id: int, bank_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        service.delete_bank(vendor_id, bank_id, user_id)

        return DeleteVendorBankResponse(message="Vendor bank account deleted successfully")

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _BANK_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# Vendor Tax (scoped to a vendor address, not the vendor directly)
# ===========================================================

_TAX_NOT_FOUND = {"Address not found", "Tax not found"}


@router.post("/addresses/{vendor_address_id}/taxes", response_model=VendorTaxResponse)
def create_vendor_tax(
    vendor_address_id: int,
    payload: VendorTaxCreateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        tax = service.create_tax(vendor_address_id, payload, user_id)

        return VendorTaxResponse(
            vendor_tax_id=tax.vendor_tax_id,
            message="Vendor tax registration created successfully",
        )

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _TAX_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A tax registration of this type already exists for the address",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses/{vendor_address_id}/taxes", response_model=list[VendorTaxDTO])
def get_vendor_taxes(vendor_address_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorService(db)
        return service.list_taxes(vendor_address_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses/{vendor_address_id}/taxes/{tax_id}", response_model=VendorTaxDTO)
def get_vendor_tax(vendor_address_id: int, tax_id: int, http_request: Request):
    db = http_request.state.db

    try:
        service = VendorService(db)
        return service.get_tax(vendor_address_id, tax_id)

    except ValueError as e:
        status_code = 404 if str(e) in _TAX_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/addresses/{vendor_address_id}/taxes/{tax_id}", response_model=VendorTaxDTO)
def update_vendor_tax(
    vendor_address_id: int,
    tax_id: int,
    payload: VendorTaxUpdateRequest,
    http_request: Request,
):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        return service.update_tax(vendor_address_id, tax_id, payload, user_id)

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _TAX_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A tax registration of this type already exists for the address",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/addresses/{vendor_address_id}/taxes/{tax_id}", response_model=DeleteVendorTaxResponse)
def delete_vendor_tax(vendor_address_id: int, tax_id: int, http_request: Request):
    db = http_request.state.db

    try:
        user_id = _get_user_id(http_request)

        service = VendorService(db)
        service.delete_tax(vendor_address_id, tax_id, user_id)

        return DeleteVendorTaxResponse(message="Vendor tax registration deleted successfully")

    except ValueError as e:
        db.rollback()
        status_code = 404 if str(e) in _TAX_NOT_FOUND else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
