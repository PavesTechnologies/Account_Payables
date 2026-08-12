# Backend/tests/test_vendor_auto_onboarding.py
"""Unit tests for automatic vendor creation from a GST-verified GSTIN.

DAOs and VendorService are faked (no real DB), and gst_service.search_gstin
is monkeypatched so no real network call is ever made.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

import Backend.Business_Layer.utils.vendor_auto_onboarding as vao

VALID_GSTIN = "07AAJCA9880A1ZL"


def _gst_response(
    status_cd="1",
    sts="Active",
    trade_name="AMAZON WEB SERVICES INDIA PRIVATE LIMITED",
    legal_name="AMAZON WEB SERVICES INDIA PRIVATE LIMITED LGL",
    gstin=VALID_GSTIN,
    addr=None,
):
    if addr is None:
        addr = {
            "bnm": "", "loc": "NEHRU PLACE", "st": "International Trade Tower",
            "bno": "Block E", "dst": "South Delhi", "pncd": "110019",
            "stcd": "Delhi", "flno": "14th Floor,1401-1421",
        }
    return {
        "code": 200,
        "data": {
            "data": {
                "gstin": gstin,
                "sts": sts,
                "tradeNam": trade_name,
                "lgnm": legal_name,
                "pradr": {"addr": addr},
            },
            "status_cd": status_cd,
        },
    }


def _extracted(gstin=VALID_GSTIN, vendor_name="Some OCR Name"):
    from datetime import date
    from decimal import Decimal
    from Backend.API_Layer.interface.invoice_process_interface import ExtractedInvoice

    return ExtractedInvoice(
        invoice_number="INV-1", invoice_date=date(2026, 1, 1), due_date=date(2026, 1, 31),
        subtotal=Decimal("1000.00"), total=Decimal("1180.00"), currency="INR",
        gstin=gstin, vendor_name=vendor_name,
    )


class _FakeMasterDAO:
    config = {
        "OCR_CONFIDENCE_THRESHOLD": "85",
        "DEFAULT_BASE_CURRENCY": "INR",
    }

    def __init__(self, db):
        self.db = db

    def get_system_config_by_key(self, key):
        value = self.config.get(key)
        return SimpleNamespace(config_value=value) if value is not None else None

    def get_currency_by_code(self, code):
        return SimpleNamespace(currency_id=1) if code == "INR" else None


class _FakeSystemDAO:
    def __init__(self, db):
        self.db = db

    def get_country_by_code(self, code):
        return SimpleNamespace(country_id=10) if code == "IN" else None


class _FakeVendorDAO:
    instances = []

    def __init__(self, db):
        self.db = db
        self.existing_vendor = None
        self.created_vendor = None
        self.created_address = None
        self.created_tax = None
        self.audit_logs = []
        _FakeVendorDAO.instances.append(self)

    def get_vendor_by_gstin(self, gstin):
        return self.existing_vendor

    def get_status_by_module_code(self, module_name, status_code):
        assert module_name == "VENDOR"
        assert status_code == "PENDING"
        return SimpleNamespace(status_id=1)

    def create_vendor(self, vendor):
        vendor.vendor_id = 100
        self.created_vendor = vendor
        return vendor

    def create_vendor_address(self, address):
        address.vendor_address_id = 200
        self.created_address = address
        return address

    def create_vendor_tax(self, tax):
        tax.vendor_tax_id = 300
        self.created_tax = tax
        return tax

    def create_audit_log(self, audit_log):
        self.audit_logs.append(audit_log)
        return audit_log


class _FakeVendorService:
    def __init__(self, db):
        self.db = db

    def _generate_unique_vendor_code(self, vendor_name):
        return "AWSI1234"


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    _FakeVendorDAO.instances = []
    monkeypatch.setattr(vao, "MasterDAO", _FakeMasterDAO)
    monkeypatch.setattr(vao, "SystemDAO", _FakeSystemDAO)
    monkeypatch.setattr(vao, "VendorDAO", _FakeVendorDAO)
    monkeypatch.setattr(vao, "VendorService", _FakeVendorService)
    _FakeMasterDAO.config = {"OCR_CONFIDENCE_THRESHOLD": "85", "DEFAULT_BASE_CURRENCY": "INR"}
    yield


def test_high_confidence_valid_active_gstin_creates_vendor(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response())

    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=91.5, db=object(), user_id="user-1")

    assert vendor_id == 100
    dao = _FakeVendorDAO.instances[-1]
    assert dao.created_vendor.vendor_name == "AMAZON WEB SERVICES INDIA PRIVATE LIMITED"
    assert dao.created_vendor.status_id == 1
    assert dao.created_vendor.country_id == 10
    assert dao.created_vendor.currency_id == 1
    assert dao.created_vendor.pan_number == VALID_GSTIN[2:12]
    assert dao.created_address.address_line1 == "Block E, International Trade Tower, 14th Floor,1401-1421, NEHRU PLACE"
    assert dao.created_address.city == "South Delhi"
    assert dao.created_address.state == "Delhi"
    assert dao.created_address.postal_code == "110019"
    assert dao.created_address.is_primary is True
    assert dao.created_tax.registration_type == "GSTIN"
    assert dao.created_tax.registration_number == VALID_GSTIN
    assert dao.created_tax.is_verified is True
    assert len(dao.audit_logs) == 1


def test_missing_gstin_falls_back_to_manual():
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(gstin=None), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_invalid_gstin_format_falls_back_to_manual():
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(gstin="NOT-A-GSTIN"), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_low_confidence_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(
        vao, "search_gstin",
        lambda gstin: (_ for _ in ()).throw(AssertionError("should not call GST API below the confidence threshold")),
    )
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=72.0, db=object(), user_id="u")
    assert vendor_id is None
    assert _FakeVendorDAO.instances == []


def test_invalid_threshold_config_fails_closed(monkeypatch):
    _FakeMasterDAO.config["OCR_CONFIDENCE_THRESHOLD"] = "not-a-number"
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response())
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=99.0, db=object(), user_id="u")
    assert vendor_id is None


def test_missing_threshold_config_fails_closed(monkeypatch):
    del _FakeMasterDAO.config["OCR_CONFIDENCE_THRESHOLD"]
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response())
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=99.0, db=object(), user_id="u")
    assert vendor_id is None


def test_gst_api_http_error_falls_back_to_manual(monkeypatch):
    def _raise(gstin):
        response = SimpleNamespace(status_code=502)
        raise requests.exceptions.HTTPError(response=response)

    monkeypatch.setattr(vao, "search_gstin", _raise)
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_gst_api_connection_error_falls_back_to_manual(monkeypatch):
    def _raise(gstin):
        raise requests.exceptions.ConnectionError("network down")

    monkeypatch.setattr(vao, "search_gstin", _raise)
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_gst_inactive_status_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response(sts="Cancelled"))
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_missing_trade_name_uses_legal_name(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response(trade_name=""))
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id == 100
    assert _FakeVendorDAO.instances[-1].created_vendor.vendor_name == "AMAZON WEB SERVICES INDIA PRIVATE LIMITED LGL"


def test_missing_both_names_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response(trade_name="", legal_name=""))
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_missing_address_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response(addr={"loc": "", "dst": ""}))
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_malformed_response_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: {"data": {"status_cd": "0"}})
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_country_not_found_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response())
    monkeypatch.setattr(vao, "SystemDAO", lambda db: SimpleNamespace(get_country_by_code=lambda code: None))
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_currency_config_missing_falls_back_to_manual(monkeypatch):
    del _FakeMasterDAO.config["DEFAULT_BASE_CURRENCY"]
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response())
    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None


def test_existing_vendor_with_same_gstin_is_reused(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: (_ for _ in ()).throw(AssertionError("should not call GST API when vendor already exists")))

    def _vendor_dao_with_existing(db):
        dao = _FakeVendorDAO(db)
        dao.existing_vendor = SimpleNamespace(vendor_id=999)
        return dao

    monkeypatch.setattr(vao, "VendorDAO", _vendor_dao_with_existing)

    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")

    assert vendor_id == 999
    assert _FakeVendorDAO.instances[-1].created_vendor is None


def test_vendor_status_not_configured_falls_back_to_manual(monkeypatch):
    monkeypatch.setattr(vao, "search_gstin", lambda gstin: _gst_response())

    def _vendor_dao_no_status(db):
        dao = _FakeVendorDAO(db)
        dao.get_status_by_module_code = lambda module_name, status_code: None
        return dao

    monkeypatch.setattr(vao, "VendorDAO", _vendor_dao_no_status)

    vendor_id = vao.auto_create_vendor_from_extraction(_extracted(), confidence=95.0, db=object(), user_id="u")
    assert vendor_id is None
