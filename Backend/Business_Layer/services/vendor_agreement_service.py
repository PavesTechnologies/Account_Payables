# Backend/Business_Layer/services/vendor_agreement_service.py
"""Vendor agreements / contracts (APM_AUTOMATION_PLAN.md 3.1a).

Lifecycle: upload (+ optional Textract suggestions) -> PENDING_VERIFICATION ->
verify (ACTIVE) or reject (REJECTED). Verification is a four-eyes control: the
verifier must be a different user from the uploader. Only an ACTIVE agreement
valid on an invoice's date is used as an authoritative payment-term source;
activating one supersedes the vendor's previous ACTIVE agreement of the same
type and re-checks that vendor's open invoices. "Expired" is computed from
valid_to, never stored. Every change writes an ap.audit_log row.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from Backend.Business_Layer.services.payment_term_compliance_service import PaymentTermComplianceService
from Backend.Business_Layer.utils.payment_term_parser import parse_payment_terms
from Backend.Data_Access_Layer.dao.payment_term_dao import PaymentTermDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.payment_terms import (
    AGREEMENT_STATUS_ACTIVE,
    AGREEMENT_STATUS_DRAFT,
    AGREEMENT_STATUS_PENDING,
    AGREEMENT_STATUS_REJECTED,
    AGREEMENT_STATUS_SUPERSEDED,
    AGREEMENT_TYPES,
    DUE_BASES,
    VendorAgreement,
    VendorAgreementDocument,
)

EDITABLE_STATUSES = frozenset({AGREEMENT_STATUS_DRAFT, AGREEMENT_STATUS_PENDING})
EXPIRY_WARNING_DAYS = 30
S3_PREFIX = "vendor-agreements/"


class AgreementNotFoundError(ValueError):
    pass


def _user(user_id) -> Optional[str]:
    return str(user_id) if user_id is not None else None


def _clean(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value[:limit] if value else None


class VendorAgreementService:
    def __init__(self, db, today: Optional[datetime.date] = None):
        self.db = db
        self.dao = PaymentTermDAO(db)
        self._today = today

    @property
    def today(self) -> datetime.date:
        return self._today or datetime.date.today()

    # ---------------------------------------------------------------
    # Read
    # ---------------------------------------------------------------
    def list_for_vendor(self, vendor_id: int) -> List[Dict[str, Any]]:
        if self.dao.get_vendor(vendor_id) is None:
            raise AgreementNotFoundError(f"Vendor {vendor_id} not found")
        return [self.to_dict(a) for a in self.dao.list_agreements(vendor_id)]

    def get(self, agreement_id: int) -> Dict[str, Any]:
        return self.to_dict(self._require(agreement_id))

    def get_document(self, agreement_id: int, document_id: int) -> VendorAgreementDocument:
        document = self.dao.get_agreement_document(agreement_id, document_id)
        if document is None:
            raise AgreementNotFoundError(f"Document {document_id} not found for agreement {agreement_id}")
        return document

    def list_expiring(self, within_days: int = EXPIRY_WARNING_DAYS) -> List[Dict[str, Any]]:
        out = []
        for agreement, vendor_name in self.dao.list_expiring_agreements(self.today, within_days):
            item = self.to_dict(agreement)
            item["vendor_name"] = vendor_name
            out.append(item)
        return out

    def to_dict(self, a: VendorAgreement) -> Dict[str, Any]:
        expired = a.valid_to is not None and a.valid_to < self.today
        days_to_expiry = (a.valid_to - self.today).days if a.valid_to else None
        return {
            "agreement_id": a.agreement_id,
            "vendor_id": a.vendor_id,
            "agreement_type": a.agreement_type,
            "reference_no": a.reference_no,
            "title": a.title,
            "valid_from": a.valid_from,
            "valid_to": a.valid_to,
            "auto_renew": a.auto_renew,
            "payment_term_id": a.payment_term_id,
            "payment_terms_text": a.payment_terms_text,
            "term_days": a.term_days,
            "due_basis": a.due_basis,
            "status": a.status,
            "is_expired": expired,
            "is_effective": a.status == AGREEMENT_STATUS_ACTIVE and a.is_valid_on(self.today),
            "days_to_expiry": days_to_expiry,
            "extraction_confidence": a.extraction_confidence,
            "remarks": a.remarks,
            "uploaded_by": a.uploaded_by,
            "uploaded_at": a.uploaded_at,
            "verified_by": a.verified_by,
            "verified_at": a.verified_at,
            "verification_remarks": a.verification_remarks,
            "documents": [
                {
                    "document_id": d.document_id,
                    "file_name": d.file_name,
                    "content_type": d.content_type,
                    "file_size": d.file_size,
                    "uploaded_by": d.uploaded_by,
                    "uploaded_at": d.uploaded_at,
                }
                for d in (a.documents or [])
            ],
        }

    # ---------------------------------------------------------------
    # Write
    # ---------------------------------------------------------------
    def create(
        self,
        vendor_id: int,
        fields: Dict[str, Any],
        filename: str,
        content: bytes,
        content_type: Optional[str],
        user_id,
    ) -> Dict[str, Any]:
        from Backend.API_Layer.utils.s3_utils import upload_to_s3

        try:
            if self.dao.get_vendor(vendor_id) is None:
                raise AgreementNotFoundError(f"Vendor {vendor_id} not found")
            values = self._validated(fields, partial=False)
            status = AGREEMENT_STATUS_DRAFT if fields.get("save_as_draft") else AGREEMENT_STATUS_PENDING
            upload = upload_to_s3(filename, content, content_type, prefix=S3_PREFIX)
            agreement = VendorAgreement(
                vendor_id=vendor_id,
                status=status,
                uploaded_by=_user(user_id),
                updated_by=_user(user_id),
                extracted_payload=fields.get("extracted_payload"),
                extraction_confidence=fields.get("extraction_confidence"),
                **values,
            )
            self.dao.add(agreement)
            self.dao.add(VendorAgreementDocument(
                agreement_id=agreement.agreement_id,
                file_name=filename,
                file_path=upload["filepath"],
                content_type=content_type,
                file_size=len(content),
                uploaded_by=_user(user_id),
            ))
            self._audit(agreement, "VENDOR_AGREEMENT_UPLOADED", user_id, None, self._snapshot(agreement))
            self.db.commit()
            self.db.refresh(agreement)
            return self.to_dict(agreement)
        except Exception:
            self.db.rollback()
            raise

    def update(self, agreement_id: int, fields: Dict[str, Any], user_id) -> Dict[str, Any]:
        try:
            agreement = self._require(agreement_id)
            if agreement.status not in EDITABLE_STATUSES:
                raise ValueError(f"An agreement in status {agreement.status} cannot be edited; upload a new version")
            before = self._snapshot(agreement)
            for key, value in self._validated(fields, partial=True, current=agreement).items():
                setattr(agreement, key, value)
            if fields.get("submit_for_verification") and agreement.status == AGREEMENT_STATUS_DRAFT:
                agreement.status = AGREEMENT_STATUS_PENDING
            agreement.updated_by = _user(user_id)
            agreement.updated_at = datetime.datetime.utcnow()
            self._audit(agreement, "VENDOR_AGREEMENT_UPDATED", user_id, before, self._snapshot(agreement))
            self.db.commit()
            self.db.refresh(agreement)
            return self.to_dict(agreement)
        except Exception:
            self.db.rollback()
            raise

    def verify(self, agreement_id: int, remarks: Optional[str], user_id) -> Dict[str, Any]:
        try:
            agreement = self._require(agreement_id)
            if agreement.status != AGREEMENT_STATUS_PENDING:
                raise ValueError(f"Only an agreement pending verification can be verified (current: {agreement.status})")
            if agreement.uploaded_by is not None and agreement.uploaded_by == _user(user_id):
                raise PermissionError("The agreement must be verified by a different user from the one who uploaded it")
            if agreement.term_days is None and agreement.payment_term_id is None:
                raise ValueError("Set the agreement payment terms (term days) before verifying it")
            before = self._snapshot(agreement)
            now = datetime.datetime.utcnow()
            for previous in self.dao.list_active_agreements_of_type(
                agreement.vendor_id, agreement.agreement_type, agreement.agreement_id
            ):
                previous.status = AGREEMENT_STATUS_SUPERSEDED
                previous.updated_by = _user(user_id)
                previous.updated_at = now
                self._audit(previous, "VENDOR_AGREEMENT_SUPERSEDED", user_id,
                            {"status": AGREEMENT_STATUS_ACTIVE}, {"status": AGREEMENT_STATUS_SUPERSEDED,
                                                                  "superseded_by": agreement.agreement_id})
            agreement.status = AGREEMENT_STATUS_ACTIVE
            agreement.verified_by = _user(user_id)
            agreement.verified_at = now
            agreement.verification_remarks = _clean(remarks, 2000)
            agreement.updated_by = _user(user_id)
            agreement.updated_at = now
            self.db.flush()
            self._audit(agreement, "VENDOR_AGREEMENT_VERIFIED", user_id, before, self._snapshot(agreement))
            rechecked = PaymentTermComplianceService(self.db).recheck_open_invoices_for_vendor(agreement.vendor_id, user_id)
            self.db.commit()
            self.db.refresh(agreement)
            result = self.to_dict(agreement)
            result["rechecked_invoice_count"] = rechecked
            return result
        except Exception:
            self.db.rollback()
            raise

    def reject(self, agreement_id: int, remarks: Optional[str], user_id) -> Dict[str, Any]:
        try:
            agreement = self._require(agreement_id)
            if agreement.status not in EDITABLE_STATUSES:
                raise ValueError(f"Only a draft or pending agreement can be rejected (current: {agreement.status})")
            remarks = _clean(remarks, 2000)
            if not remarks or len(remarks) < 5:
                raise ValueError("Remarks are required (at least 5 characters) to reject an agreement")
            before = self._snapshot(agreement)
            agreement.status = AGREEMENT_STATUS_REJECTED
            agreement.verified_by = _user(user_id)
            agreement.verified_at = datetime.datetime.utcnow()
            agreement.verification_remarks = remarks
            agreement.updated_by = _user(user_id)
            agreement.updated_at = datetime.datetime.utcnow()
            self._audit(agreement, "VENDOR_AGREEMENT_REJECTED", user_id, before, self._snapshot(agreement))
            self.db.commit()
            self.db.refresh(agreement)
            return self.to_dict(agreement)
        except Exception:
            self.db.rollback()
            raise

    def vendor_gstins(self, vendor_id: int) -> List[str]:
        vendor = self.dao.get_vendor(vendor_id)
        if vendor is None:
            return []
        out = []
        for address in vendor.vendor_address or []:
            for tax in getattr(address, "vendor_tax", None) or []:
                if tax.registration_number:
                    out.append(tax.registration_number.strip().upper())
        return out

    # ---------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------
    def _require(self, agreement_id: int) -> VendorAgreement:
        agreement = self.dao.get_agreement(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError(f"Agreement {agreement_id} not found")
        return agreement

    def _validated(self, fields: Dict[str, Any], partial: bool, current: Optional[VendorAgreement] = None) -> Dict[str, Any]:
        out: Dict[str, Any] = {}

        def provided(key):
            return key in fields and fields[key] is not None and fields[key] != ""

        if provided("title") or not partial:
            title = _clean(fields.get("title"), 200)
            if not title:
                raise ValueError("title is required")
            out["title"] = title
        if provided("agreement_type") or not partial:
            agreement_type = (fields.get("agreement_type") or "OTHER").strip().upper()
            if agreement_type not in AGREEMENT_TYPES:
                raise ValueError(f"agreement_type must be one of {', '.join(AGREEMENT_TYPES)}")
            out["agreement_type"] = agreement_type
        if "reference_no" in fields:
            out["reference_no"] = _clean(fields.get("reference_no"), 100)
        if provided("valid_from") or not partial:
            if not fields.get("valid_from"):
                raise ValueError("valid_from is required")
            out["valid_from"] = fields["valid_from"]
        if "valid_to" in fields:
            out["valid_to"] = fields.get("valid_to") or None
        valid_from = out.get("valid_from", current.valid_from if current else None)
        valid_to = out.get("valid_to", current.valid_to if current else None)
        if valid_from and valid_to and valid_to < valid_from:
            raise ValueError("valid_to cannot be before valid_from")
        if "auto_renew" in fields and fields.get("auto_renew") is not None:
            out["auto_renew"] = bool(fields["auto_renew"])
        if "payment_term_id" in fields:
            term_id = fields.get("payment_term_id")
            if term_id is not None and self.dao.get_payment_term(term_id) is None:
                raise ValueError("Payment term not found for the given payment_term_id")
            out["payment_term_id"] = term_id
        if "payment_terms_text" in fields:
            out["payment_terms_text"] = _clean(fields.get("payment_terms_text"), 500)
        if "term_days" in fields:
            days = fields.get("term_days")
            if days is not None and days != "":
                days = int(days)
                if not 0 <= days <= 365:
                    raise ValueError("term_days must be between 0 and 365")
            else:
                days = None
            out["term_days"] = days
        if "due_basis" in fields and fields.get("due_basis"):
            basis = str(fields["due_basis"]).strip().upper()
            if basis not in DUE_BASES:
                raise ValueError(f"due_basis must be one of {', '.join(DUE_BASES)}")
            out["due_basis"] = basis
        if "remarks" in fields:
            out["remarks"] = _clean(fields.get("remarks"), 2000)

        # Term days left blank: derive them from the clause text, else from the chosen term.
        effective_days = out["term_days"] if "term_days" in out else (current.term_days if current else None)
        if effective_days is None:
            text = out.get("payment_terms_text") or (current.payment_terms_text if current else None)
            parsed = parse_payment_terms(text)
            term_id = out.get("payment_term_id", current.payment_term_id if current else None)
            if parsed.days is not None:
                out["term_days"] = parsed.days
                out.setdefault("due_basis", parsed.basis)
            elif term_id is not None:
                term = self.dao.get_payment_term(term_id)
                out["term_days"] = int(term.due_days) if term else None
        return out

    @staticmethod
    def _snapshot(a: VendorAgreement) -> Dict[str, Any]:
        return {
            "status": a.status,
            "agreement_type": a.agreement_type,
            "title": a.title,
            "reference_no": a.reference_no,
            "valid_from": a.valid_from.isoformat() if a.valid_from else None,
            "valid_to": a.valid_to.isoformat() if a.valid_to else None,
            "term_days": a.term_days,
            "due_basis": a.due_basis,
            "payment_term_id": a.payment_term_id,
        }

    def _audit(self, agreement: VendorAgreement, action: str, user_id, old, new) -> None:
        self.db.add(AuditLog(
            table_name="vendor_agreement",
            record_id=agreement.agreement_id,
            action=action,
            changed_by=_user(user_id),
            old_values=old,
            new_values={**(new or {}), "vendor_id": agreement.vendor_id},
        ))
