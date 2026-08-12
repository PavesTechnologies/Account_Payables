# Backend/Business_Layer/utils/vendor_auto_onboarding.py
"""Automatic vendor creation from a GST-verified GSTIN during invoice processing.

Used by invoice_process_service.persist_processed_invoice when vendor
matching fails: if the extraction confidence is high enough and the
extracted GSTIN checks out against the GST verification service, a new
Vendor (+ VendorAddress + VendorTax) is created in PENDING status
instead of falling back to manual onboarding. Every failure mode here
returns None rather than raising, so the caller can fall back to the
existing manual-onboarding path unconditionally — the only exceptions
that propagate are actual DB write failures once creation has started,
which must roll back the whole invoice-persistence transaction.

Nothing here commits or rolls back — the caller (persist_processed_invoice)
owns the transaction, consistent with every other DAO/service call in
that flow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests

from Backend.API_Layer.interface.invoice_process_interface import ExtractedInvoice
from Backend.Business_Layer.services.vendor_service import VendorService
from Backend.Business_Layer.utils.extraction.normalizers import is_valid_gstin_format, pan_from_gstin
from Backend.Business_Layer.utils.gst_service import search_gstin
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.dao.system_dao import SystemDAO
from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorAddress, VendorTax

logger = logging.getLogger(__name__)

OCR_CONFIDENCE_THRESHOLD_CONFIG_KEY = "OCR_CONFIDENCE_THRESHOLD"
DEFAULT_BASE_CURRENCY_CONFIG_KEY = "DEFAULT_BASE_CURRENCY"
INDIA_COUNTRY_CODE = "IN"

VENDOR_STATUS_MODULE = "VENDOR"
VENDOR_STATUS_CODE_PENDING = "PENDING"

VENDOR_TAX_REGISTRATION_TYPE = "GSTIN"
GST_ACTIVE_STATUS = "active"
from dataclasses import dataclass
from typing import Optional


@dataclass
class GSTVerificationResult:
    verified: bool
    data: Optional[dict] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    transaction_id: Optional[str] = None


def _mask_gstin(gstin: Optional[str]) -> str:
    if not gstin or len(gstin) < 4:
        return "****"
    return f"{'*' * (len(gstin) - 4)}{gstin[-4:]}"


def get_numeric_system_config(db, key: str, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Read a system_configuration value as a Decimal.

    Returns ``default`` when the key isn't configured at all. Returns
    ``None`` (regardless of ``default``) when the key IS configured but
    its value isn't numeric — a malformed threshold must fail closed,
    never silently become 0 or the caller's default.
    """
    config = MasterDAO(db).get_system_config_by_key(key)
    if config is None:
        return default

    try:
        return Decimal(config.config_value.strip())
    except (InvalidOperation, AttributeError):
        logger.error(
            "system_configuration key '%s' has a non-numeric value '%s'; failing closed",
            key, config.config_value,
        )
        return None


def _normalize_and_validate_gstin(raw: Optional[str]) -> Optional[str]:
    if not raw or not raw.strip():
        return None
    candidate = raw.strip().upper()
    if not is_valid_gstin_format(candidate):
        return None
    return candidate


def _call_gst_search(gstin: str) -> GSTVerificationResult:
    try:
        response = search_gstin(gstin)

        return GSTVerificationResult(
            verified=True,
            data=response,
        )

    except requests.exceptions.HTTPError as exc:
        response = getattr(exc, "response", None)

        error_code = response.status_code if response is not None else None
        error_message = None
        transaction_id = None

        if response is not None:
            try:
                payload = response.json()

                error_code = payload.get("code", error_code)
                error_message = payload.get("message")
                transaction_id = payload.get("transaction_id")

            except ValueError:
                error_message = response.text

        logger.warning(
            "GST verification failed for GSTIN %s: code=%s message=%s transaction_id=%s",
            _mask_gstin(gstin),
            error_code,
            error_message,
            transaction_id,
        )

        return GSTVerificationResult(
            verified=False,
            error_code=error_code,
            error_message=error_message,
            transaction_id=transaction_id,
        )

    except requests.exceptions.RequestException as exc:
        logger.warning(
            "GST verification unavailable for GSTIN %s (%s)",
            _mask_gstin(gstin),
            type(exc).__name__,
        )

        return GSTVerificationResult(
            verified=False,
            error_message="GST verification service unavailable",
        )

    except Exception:
        logger.exception(
            "Unexpected error calling GST verification service"
        )

        return GSTVerificationResult(
            verified=False,
            error_message="Unexpected GST verification error",
        )


def extract_vendor_data_from_gst_response(gst_response: dict) -> Optional[dict]:
    """Normalize the raw Sandbox GST API response into the fields auto-onboarding needs.

    Returns None for any structurally unusable response — missing
    ``data``/nested ``data``, an unsuccessful ``status_cd``, no GSTIN/
    status, no usable name, or an address missing address_line1/city
    (both NOT NULL on VendorAddress). Never raises.
    """
    try:
        outer = gst_response.get("data") or {}
        if str(outer.get("status_cd")) != "1":
            return None

        data = outer.get("data") or {}
        gstin = (data.get("gstin") or "").strip().upper()
        status = (data.get("sts") or "").strip()
        if not gstin or not status:
            return None

        trade_name = (data.get("tradeNam") or "").strip()
        legal_name = (data.get("lgnm") or "").strip()
        vendor_name = trade_name or legal_name
        if not vendor_name:
            return None

        addr = ((data.get("pradr") or {}).get("addr")) or {}
        address_parts = [
            (addr.get("bno") or "").strip(),
            (addr.get("bnm") or "").strip(),
            (addr.get("st") or "").strip(),
            (addr.get("flno") or "").strip(),
            (addr.get("loc") or "").strip(),
        ]
        address_line1 = ", ".join(part for part in address_parts if part)
        city = (addr.get("dst") or addr.get("locality") or "").strip()
        state = (addr.get("stcd") or "").strip() or None
        postal_code = (addr.get("pncd") or "").strip() or None

        if not address_line1 or not city:
            return None

        return {
            "gstin": gstin,
            "vendor_name": vendor_name,
            "status": status,
            "address_line1": address_line1,
            "city": city,
            "state": state,
            "postal_code": postal_code,
        }
    except (AttributeError, TypeError):
        logger.warning("Malformed GST verification response could not be parsed")
        return None


def build_vendor_address_from_gst(gst_details: dict, vendor_id: int, country_id: int) -> Optional[VendorAddress]:
    """Build a VendorAddress from a parsed GST details dict (see extract_vendor_data_from_gst_response).

    Returns None if the mandatory fields (address_line1, city) aren't
    present — callers must not create a partial address.
    """
    address_line1 = gst_details.get("address_line1")
    city = gst_details.get("city")
    if not address_line1 or not city:
        return None

    return VendorAddress(
        vendor_id=vendor_id,
        address_type="REGISTERED",
        address_line1=address_line1[:200],
        city=city[:100],
        state=(gst_details.get("state") or None),
        postal_code=(gst_details.get("postal_code") or None),
        country_id=country_id,
        is_primary=True,
    )


def _resolve_default_currency_id(db) -> Optional[int]:
    currency_code_config = MasterDAO(db).get_system_config_by_key(DEFAULT_BASE_CURRENCY_CONFIG_KEY)
    if currency_code_config is None or not currency_code_config.config_value:
        logger.error(
            "Automatic vendor onboarding: system_configuration key '%s' is not configured",
            DEFAULT_BASE_CURRENCY_CONFIG_KEY,
        )
        return None

    currency = MasterDAO(db).get_currency_by_code(currency_code_config.config_value.strip())
    if currency is None:
        logger.error(
            "Automatic vendor onboarding: base currency '%s' is not configured in the currency master",
            currency_code_config.config_value,
        )
        return None

    return currency.currency_id


def auto_create_vendor_from_extraction(
    extracted: ExtractedInvoice,
    confidence: float,
    db,
    user_id: str,
) -> Optional[int]:
    """Attempt to auto-create (or reuse) a vendor for an unmatched invoice's GSTIN.

    Returns the vendor_id on success (newly created or a pre-existing
    vendor found for the same GSTIN), or None if automatic onboarding
    isn't possible for any reason — the caller should then fall back to
    the existing manual-onboarding path. Only DB write failures once
    creation has actually started are allowed to raise, so the caller's
    outer transaction rolls back cleanly.
    """
    print("plain GSTIN:", extracted.gstin)
    print("extracted GSTIN:", extracted.buyer_gstin)
    gstin = extracted.gstin or extracted.buyer_gstin
    gstin = _normalize_and_validate_gstin(gstin)
    print("normalized GSTIN:", gstin)
    if gstin is None:
        logger.info("Automatic vendor onboarding skipped: GSTIN missing or invalid format")
        return None

    threshold = get_numeric_system_config(db, OCR_CONFIDENCE_THRESHOLD_CONFIG_KEY)
    if threshold is None:
        logger.warning(
            "Automatic vendor onboarding skipped: '%s' is not configured or invalid; failing closed",
            OCR_CONFIDENCE_THRESHOLD_CONFIG_KEY,
        )
        return None
    if Decimal(str(confidence)) < threshold:
        logger.info(
            "Automatic vendor onboarding skipped: confidence %.2f below threshold %s",
            confidence, threshold,
        )
        return None

    vendor_dao = VendorDAO(db)
    existing_vendor = vendor_dao.get_vendor_by_gstin(gstin)
    if existing_vendor is not None:
        logger.info(
            "Vendor already exists for GSTIN %s; reusing vendor_id=%s",
            _mask_gstin(gstin), existing_vendor.vendor_id,
        )
        return existing_vendor.vendor_id

    gst_result = _call_gst_search(gstin)

    if not gst_result.verified:
        logger.warning(
            "GST verification rejected GSTIN %s: code=%s message=%s transaction_id=%s",
            _mask_gstin(gstin),
            gst_result.error_code,
            gst_result.error_message,
            gst_result.transaction_id,
        )

        return None

    gst_details = extract_vendor_data_from_gst_response(gst_result)
    if gst_details is None:
        logger.warning("Automatic vendor onboarding skipped: GST response incomplete/malformed for %s", _mask_gstin(gstin))
        return None

    if gst_details["gstin"] != gstin:
        logger.warning("Automatic vendor onboarding skipped: GST response GSTIN mismatch for %s", _mask_gstin(gstin))
        return None

    if gst_details["status"].strip().lower() != GST_ACTIVE_STATUS:
        logger.info(
            "Automatic vendor onboarding skipped: GST registration status '%s' is not Active for %s",
            gst_details["status"], _mask_gstin(gstin),
        )
        return None

    country = SystemDAO(db).get_country_by_code(INDIA_COUNTRY_CODE)
    if country is None:
        logger.error("Automatic vendor onboarding skipped: '%s' country record not found", INDIA_COUNTRY_CODE)
        return None

    currency_id = _resolve_default_currency_id(db)
    if currency_id is None:
        logger.error("Automatic vendor onboarding skipped: base currency could not be resolved")
        return None

    status = vendor_dao.get_status_by_module_code(VENDOR_STATUS_MODULE, VENDOR_STATUS_CODE_PENDING)
    if status is None:
        logger.error(
            "Automatic vendor onboarding skipped: %s/%s status not configured",
            VENDOR_STATUS_MODULE, VENDOR_STATUS_CODE_PENDING,
        )
        return None

    # extract_vendor_data_from_gst_response already guarantees address_line1/city
    # are present (it returns None otherwise), so this is a defensive re-check,
    # not the primary gate — kept because build_vendor_address_from_gst is the
    # single place address-completeness is enforced, per its own contract.
    if build_vendor_address_from_gst(gst_details, vendor_id=0, country_id=country.country_id) is None:
        logger.warning(
            "Automatic vendor onboarding skipped: GST address missing address_line1/city for %s",
            _mask_gstin(gstin),
        )
        return None

    try:
        pan_number = pan_from_gstin(gstin)
    except ValueError:
        pan_number = None

    try:
        vendor_code = VendorService(db)._generate_unique_vendor_code(gst_details["vendor_name"])
    except Exception:
        logger.exception("Vendor code generation failed during automatic onboarding; continuing without one")
        vendor_code = None

    # From here on, failures are real DB errors and must propagate so the
    # caller's transaction rolls back — no more "fall back to manual" exits.
    vendor = Vendor(
        vendor_name=gst_details["vendor_name"],
        vendor_code=vendor_code,
        country_id=country.country_id,
        payment_term_id=None,
        currency_id=currency_id,
        pan_number=pan_number,
        phone_number=None,
        email=None,
        status_id=status.status_id,
        created_by=user_id,
        updated_by=user_id,
    )
    vendor_dao.create_vendor(vendor)

    address = build_vendor_address_from_gst(gst_details, vendor_id=vendor.vendor_id, country_id=country.country_id)
    if address is None:
        raise ValueError("GST address became unavailable while creating the vendor address")
    vendor_dao.create_vendor_address(address)

    tax = VendorTax(
        vendor_address_id=address.vendor_address_id,
        registration_type=VENDOR_TAX_REGISTRATION_TYPE,
        registration_number=gstin,
        is_verified=True,
    )
    vendor_dao.create_vendor_tax(tax)

    vendor_dao.create_audit_log(
        AuditLog(
            table_name="vendor",
            record_id=vendor.vendor_id,
            action="CREATE",
            changed_by=user_id,
            new_values={
                "vendor_name": vendor.vendor_name,
                "vendor_code": vendor.vendor_code,
                "country_id": vendor.country_id,
                "status_id": vendor.status_id,
                "source": "AUTO_ONBOARDING_GSTIN",
            },
        )
    )

    logger.info("Automatic vendor created: vendor_id=%s for GSTIN %s", vendor.vendor_id, _mask_gstin(gstin))
    return vendor.vendor_id
