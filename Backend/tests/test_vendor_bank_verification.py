"""Vendor bank verification: name match, penny-drop outcomes, second-person approval, reset on change."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import vendor_bank_verification_service as vbv
from Backend.Data_Access_Layer.models.vendor_bank_verification import VendorBankVerification


def test_name_score_ignores_case_punctuation_and_legal_suffixes():
    assert vbv.name_score("WEWORK INDIA MANAGEMENT LIMITED", "WeWork India Management Ltd.") == Decimal("100.0")
    assert vbv.name_score("Keka Technologies Pvt Ltd", "KEKA TECHNOLOGIES PRIVATE LIMITED") >= 95
    assert vbv.name_score("Acme Traders", "KEKA TECHNOLOGIES PRIVATE LIMITED") < 60
    assert vbv.name_score(None, "x") == Decimal("0")


class _Db:
    def __init__(self, bank, vendor, row=None):
        self.bank, self.vendor, self.row, self.added = bank, vendor, row, []

    def get(self, model, key):
        name = model.__name__
        return {"VendorBank": self.bank, "Vendor": self.vendor, "VendorBankVerification": self.row}[name]

    def add(self, obj):
        if isinstance(obj, VendorBankVerification):
            self.row = obj
        self.added.append(obj)

    def commit(self):
        pass

    def rollback(self):
        pass


def _world(name_at_bank="WEWORK INDIA MANAGEMENT LIMITED", exists=True, raises=False):
    bank = SimpleNamespace(vendor_bank_id=3, vendor_id=17, ifsc_code="HDFC0DEMO01", account_number="50200012340001",
                           account_holder_name="WEWORK INDIA MANAGEMENT LIMITED")
    vendor = SimpleNamespace(vendor_id=17, vendor_name="WEWORK INDIA MANAGEMENT LIMITED")
    db = _Db(bank, vendor)

    def check(ifsc, account, name):
        if raises:
            raise RuntimeError("bank API down")
        return {"exists": exists, "name_at_bank": name_at_bank, "reference": "UTR123"}
    return db, vbv.VendorBankVerificationService(db, bank_check=check)


def test_penny_drop_verified_mismatch_failed():
    db, svc = _world()
    assert svc.verify_penny_drop(17, 3, "5100020")["status"] == "VERIFIED"
    db, svc = _world(name_at_bank="SOMEONE ELSE ENTERPRISES")
    result = svc.verify_penny_drop(17, 3, "5100020")
    assert result["status"] == "NAME_MISMATCH" and "differs" in result["message"]
    db, svc = _world(exists=False)
    assert svc.verify_penny_drop(17, 3, "5100020")["status"] == "FAILED"
    db, svc = _world(raises=True)
    result = svc.verify_penny_drop(17, 3, "5100020")
    assert result["status"] == "FAILED" and "cancelled cheque" in result["message"]


def test_approval_needs_verification_and_a_second_person():
    db, svc = _world()
    with pytest.raises(ValueError, match="Verify the account first"):
        svc.approve(17, 3, None, "5100026")
    svc.reset_after_change(3, "5100031")  # Vendor Intake added the account
    svc.verify_penny_drop(17, 3, "5100020")
    with pytest.raises(ValueError, match="someone else must approve"):
        svc.approve(17, 3, None, "5100031")
    view = svc.approve(17, 3, "Matches vendor letterhead", "5100026")
    assert view["approval_status"] == "APPROVED" and view["payable"] is True
    assert svc.is_payable(3) is True


def test_any_change_resets_and_blocks_payment():
    db, svc = _world()
    svc.verify_penny_drop(17, 3, "5100020")
    svc.approve(17, 3, None, "5100026")
    svc.reset_after_change(3, "5100031")
    assert db.row.status == "UNVERIFIED" and db.row.approval_status == "PENDING" and svc.is_payable(3) is False
    assert db.added[-1].action == "VENDOR_BANK_VERIFICATION_RESET"


def test_wrong_vendor_is_not_found():
    db, svc = _world()
    with pytest.raises(LookupError):
        svc.status(99, 3)
