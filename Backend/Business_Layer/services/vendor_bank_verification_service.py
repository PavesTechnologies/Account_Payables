# Backend/Business_Layer/services/vendor_bank_verification_service.py
"""Vendor bank account verification and change control (P3).

  1. verify   PENNY_DROP - a live bank-account check (Sandbox) returns the name registered at the bank,
              compared with the vendor's legal name; or DOCUMENT - Finance checks a cancelled cheque /
              bank letter and uploads it. Result: VERIFIED, NAME_MISMATCH or FAILED.
  2. approve  a second person - not whoever added or last changed the account - approves a VERIFIED
              account. Only APPROVED accounts are payable through a payment run (is_payable).
  Any change to the account (create / update) resets it to UNVERIFIED + PENDING (reset_after_change).

Every step is written to audit_log (table vendor_bank).
"""
from __future__ import annotations

import datetime
import difflib
import logging
import re
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorBank
from Backend.Data_Access_Layer.models.vendor_bank_verification import (
    APPROVAL_PENDING,
    APPROVED,
    DOCUMENT,
    FAILED,
    NAME_MISMATCH,
    PENNY_DROP,
    REJECTED,
    UNVERIFIED,
    VERIFIED,
    VendorBankVerification,
)

logger = logging.getLogger(__name__)

VERIFY_PERMISSIONS = ["VENDOR_BANK_VERIFY", "AP_AUTOMATION_MANAGE", "PAYMENT_PROCESS"]
VIEW_PERMISSIONS = VERIFY_PERMISSIONS + ["VENDOR_VIEW", "VENDOR_MANAGE", "VENDOR_BANK_MANAGE", "PAYMENT_VIEW"]
NAME_MATCH_MIN = Decimal("85")
_COMPANY_WORDS = r"\b(private|pvt|limited|ltd|llp|inc|india|the|co|company|corporation|corp)\b"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def name_score(a: Optional[str], b: Optional[str]) -> Decimal:
    """0-100 similarity of two business names, ignoring case, punctuation and legal suffixes."""
    def norm(value):
        value = re.sub(r"[^a-z0-9 ]", " ", (value or "").lower())
        return " ".join(re.sub(_COMPANY_WORDS, " ", value).split())
    left, right = norm(a), norm(b)
    if not left or not right:
        return Decimal("0")
    return Decimal(str(round(difflib.SequenceMatcher(None, left, right).ratio() * 100, 2)))


def penny_drop(ifsc: str, account_number: str, name: Optional[str]) -> Dict[str, Any]:
    """Live bank-account check through the Sandbox API - {exists, name_at_bank, reference}. Raises on failure."""
    import os

    import requests
    from Backend.Business_Layer.utils.sandbox_auth import get_access_token
    base = os.getenv("SANDBOX_BASE_URL", "https://test-api.sandbox.co.in")
    headers = {"authorization": get_access_token(), "x-api-key": os.getenv("SANDBOX_API_KEY", ""), "x-api-version": "1.0.0"}
    response = requests.get(f"{base}/bank/{ifsc}/accounts/{account_number}/verify", headers=headers,
                            params={"name": name} if name else None, timeout=30)
    response.raise_for_status()
    data = (response.json() or {}).get("data") or {}
    exists = data.get("account_exists")
    return {"exists": bool(exists) if exists is not None else None,
            "name_at_bank": data.get("name_at_bank") or data.get("registered_name"),
            "reference": str(data.get("utr") or data.get("reference_id") or "") or None,
            "message": data.get("message")}


class VendorBankVerificationService:
    def __init__(self, db, bank_check=penny_drop):
        self.db = db
        self._bank_check = bank_check

    # ------------------------------------------------------------------ helpers
    def _bank(self, vendor_id: int, bank_id: int) -> Tuple[VendorBank, Vendor]:
        bank = self.db.get(VendorBank, bank_id)
        if bank is None or bank.vendor_id != vendor_id:
            raise LookupError("Bank account not found for this vendor")
        return bank, self.db.get(Vendor, vendor_id)

    def _row(self, bank_id: int) -> VendorBankVerification:
        row = self.db.get(VendorBankVerification, bank_id)
        if row is None:
            row = VendorBankVerification(vendor_bank_id=bank_id, status=UNVERIFIED, approval_status=APPROVAL_PENDING)
            self.db.add(row)
        return row

    def _audit(self, bank_id: int, action: str, user_id, new: dict):
        self.db.add(AuditLog(table_name="vendor_bank", record_id=bank_id, action=action, changed_by=str(user_id), new_values=new))

    @staticmethod
    def view(row: Optional[VendorBankVerification]) -> Dict[str, Any]:
        if row is None:
            return {"status": UNVERIFIED, "approval_status": APPROVAL_PENDING, "payable": False}
        return {"status": row.status, "approval_status": row.approval_status, "method": row.method,
                "name_at_bank": row.name_at_bank, "name_match_score": row.name_match_score, "reference": row.reference,
                "message": row.message, "verified_by": row.verified_by, "verified_at": row.verified_at,
                "approved_by": row.approved_by, "approved_at": row.approved_at, "approval_remarks": row.approval_remarks,
                "changed_by": row.changed_by, "has_document": bool(row.file_path),
                "payable": row.status == VERIFIED and row.approval_status == APPROVED}

    def status(self, vendor_id: int, bank_id: int) -> Dict[str, Any]:
        self._bank(vendor_id, bank_id)
        return self.view(self.db.get(VendorBankVerification, bank_id))

    def for_vendor(self, vendor_id: int) -> Dict[int, Dict[str, Any]]:
        ids = [b for (b,) in self.db.execute(select(VendorBank.vendor_bank_id).where(VendorBank.vendor_id == vendor_id))]
        rows = {r.vendor_bank_id: r for r in self.db.execute(select(VendorBankVerification).where(
            VendorBankVerification.vendor_bank_id.in_(ids))).scalars()} if ids else {}
        return {i: self.view(rows.get(i)) for i in ids}

    def is_payable(self, bank_id: Optional[int]) -> bool:
        if not bank_id:
            return False
        row = self.db.get(VendorBankVerification, bank_id)
        return row is not None and row.status == VERIFIED and row.approval_status == APPROVED

    # ------------------------------------------------------------------ change control
    def reset_after_change(self, bank_id: int, user_id) -> None:
        """Account added or edited: it must be verified and approved again before it is paid."""
        try:
            row = self._row(bank_id)
            row.status, row.approval_status, row.changed_by, row.updated_at = UNVERIFIED, APPROVAL_PENDING, str(user_id), _now()
            for field in ("method", "name_at_bank", "name_match_score", "reference", "message", "verified_by", "verified_at",
                          "approved_by", "approved_at", "approval_remarks", "file_name", "file_path", "content_type"):
                setattr(row, field, None)
            self._audit(bank_id, "VENDOR_BANK_VERIFICATION_RESET", user_id, {"reason": "Bank details added or changed"})
            self.db.commit()
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.exception("Could not reset verification for vendor bank %s", bank_id)

    # ------------------------------------------------------------------ verify
    def verify_penny_drop(self, vendor_id: int, bank_id: int, user_id) -> Dict[str, Any]:
        bank, vendor = self._bank(vendor_id, bank_id)
        if not bank.ifsc_code or not bank.account_number:
            raise ValueError("A penny-drop check needs the account number and IFSC")
        row = self._row(bank_id)
        try:
            result = self._bank_check(bank.ifsc_code, bank.account_number, bank.account_holder_name)
        except Exception as exc:
            logger.info("Penny-drop check failed for vendor bank %s: %s", bank_id, exc)
            row.status, row.method = FAILED, PENNY_DROP
            row.message = "The bank check could not be completed - verify with a cancelled cheque or bank letter instead."
        else:
            if result.get("exists") is False:
                row.status, row.message = FAILED, "The bank reports this account does not exist."
            else:
                score = name_score(result.get("name_at_bank"), vendor.vendor_name if vendor else bank.account_holder_name)
                row.status = VERIFIED if score >= NAME_MATCH_MIN else NAME_MISMATCH
                row.name_at_bank, row.name_match_score = result.get("name_at_bank"), score
                row.message = (None if row.status == VERIFIED else
                               f"Name at the bank '{result.get('name_at_bank')}' differs from the vendor's legal name - confirm with the vendor.")
            row.method, row.reference = PENNY_DROP, result.get("reference")
        row.verified_by, row.verified_at, row.updated_at = str(user_id), _now(), _now()
        row.approval_status = APPROVAL_PENDING
        self._audit(bank_id, "VENDOR_BANK_VERIFIED", user_id, {"method": PENNY_DROP, "status": row.status,
                                                                "name_match_score": str(row.name_match_score or "")})
        self.db.commit()
        return self.view(row)

    def verify_document(self, vendor_id: int, bank_id: int, document: Tuple[str, bytes, Optional[str]], remarks: str, user_id) -> Dict[str, Any]:
        self._bank(vendor_id, bank_id)
        if len((remarks or "").strip()) < 5:
            raise ValueError("Say what you checked, e.g. 'Cancelled cheque matches account and IFSC'")
        from Backend.API_Layer.utils.s3_utils import upload_to_s3
        name, content, ctype = document
        stored = upload_to_s3(name, content, ctype, prefix="vendor-bank-proof/")
        row = self._row(bank_id)
        row.status, row.method, row.message = VERIFIED, DOCUMENT, remarks.strip()
        row.file_name, row.file_path, row.content_type = name[:255], stored["filepath"], ctype
        row.verified_by, row.verified_at, row.updated_at, row.approval_status = str(user_id), _now(), _now(), APPROVAL_PENDING
        self._audit(bank_id, "VENDOR_BANK_VERIFIED", user_id, {"method": DOCUMENT, "status": VERIFIED, "remarks": row.message})
        self.db.commit()
        return self.view(row)

    # ------------------------------------------------------------------ approve
    def approve(self, vendor_id: int, bank_id: int, remarks: Optional[str], user_id) -> Dict[str, Any]:
        self._bank(vendor_id, bank_id)
        row = self.db.get(VendorBankVerification, bank_id)
        if row is None or row.status != VERIFIED:
            raise ValueError("Verify the account first (penny-drop or cancelled cheque / bank letter)")
        if row.changed_by and row.changed_by == str(user_id):
            raise ValueError("Segregation of duties: you added or changed this account, so someone else must approve it")
        row.approval_status, row.approved_by, row.approved_at = APPROVED, str(user_id), _now()
        row.approval_remarks, row.updated_at = (remarks or "").strip()[:500] or None, _now()
        self._audit(bank_id, "VENDOR_BANK_APPROVED", user_id, {"remarks": row.approval_remarks})
        self.db.commit()
        return self.view(row)

    def reject(self, vendor_id: int, bank_id: int, remarks: str, user_id) -> Dict[str, Any]:
        self._bank(vendor_id, bank_id)
        if len((remarks or "").strip()) < 5:
            raise ValueError("Give the reason (at least 5 characters)")
        row = self._row(bank_id)
        row.approval_status, row.approved_by, row.approved_at = REJECTED, str(user_id), _now()
        row.approval_remarks, row.updated_at = remarks.strip()[:500], _now()
        self._audit(bank_id, "VENDOR_BANK_REJECTED", user_id, {"remarks": row.approval_remarks})
        self.db.commit()
        return self.view(row)

    def document(self, vendor_id: int, bank_id: int) -> VendorBankVerification:
        self._bank(vendor_id, bank_id)
        row = self.db.get(VendorBankVerification, bank_id)
        if row is None or not row.file_path:
            raise LookupError("No verification document")
        return row
