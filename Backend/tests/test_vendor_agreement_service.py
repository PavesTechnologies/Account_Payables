"""Vendor agreements (Business_Layer/services/vendor_agreement_service.py) against a fake DAO:
four-eyes verification, supersede, validation, re-check of open invoices, extraction parsing."""
import datetime
from types import SimpleNamespace

import pytest

from Backend.API_Layer.utils.agreement_extraction_fields import guess_agreement_type, parse_agreement_fields
from Backend.Business_Layer.services import vendor_agreement_service as vas
from Backend.Data_Access_Layer.models.payment_terms import VendorAgreement

D = datetime.date


class _FakeDB:
    def __init__(self):
        self.added, self.commits, self.rollbacks = [], 0, 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, obj):
        pass


class _FakeDAO:
    def __init__(self):
        self.agreements = {}
        self.next_id = 1

    def add(self, obj):
        if isinstance(obj, VendorAgreement):
            obj.agreement_id = self.next_id
            obj.documents = []
            self.agreements[self.next_id] = obj
            self.next_id += 1
        else:
            self.agreements[obj.agreement_id].documents.append(obj)
            obj.document_id = 99
        return obj

    def get_vendor(self, vendor_id):
        return SimpleNamespace(vendor_id=vendor_id, vendor_address=[]) if vendor_id == 5 else None

    def get_agreement(self, agreement_id):
        return self.agreements.get(agreement_id)

    def get_payment_term(self, term_id):
        return SimpleNamespace(payment_term_id=term_id, due_days=30) if term_id == 3 else None

    def list_active_agreements_of_type(self, vendor_id, agreement_type, exclude_id):
        return [a for a in self.agreements.values()
                if a.vendor_id == vendor_id and a.agreement_type == agreement_type
                and a.status == "ACTIVE" and a.agreement_id != exclude_id]


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr("Backend.API_Layer.utils.s3_utils.upload_to_s3",
                        lambda name, content, ctype, prefix="": {"filepath": f"{prefix}{name}"})
    rechecks = []

    class _FakeCompliance:
        def __init__(self, db):
            pass

        def recheck_open_invoices_for_vendor(self, vendor_id, user_id):
            rechecks.append(vendor_id)
            return 2

    monkeypatch.setattr(vas, "PaymentTermComplianceService", _FakeCompliance)
    svc = vas.VendorAgreementService(_FakeDB(), today=D(2026, 10, 9))
    svc.dao = _FakeDAO()
    svc.rechecks = rechecks
    return svc


def _fields(**kw):
    base = {"title": "Office Lease", "agreement_type": "LEASE", "valid_from": D(2026, 4, 1),
            "valid_to": D(2027, 3, 31), "payment_terms_text": "within fifteen (15) days of invoice"}
    base.update(kw)
    return base


def _create(service, user="intake-1", **kw):
    return service.create(5, _fields(**kw), "lease.pdf", b"%PDF-1.4", "application/pdf", user)


def test_create_derives_term_days_and_waits_for_verification(service):
    result = _create(service)
    assert result["status"] == "PENDING_VERIFICATION"
    assert result["term_days"] == 15 and result["due_basis"] == "INVOICE_DATE"
    assert result["documents"][0]["file_name"] == "lease.pdf"
    assert not result["is_effective"]
    assert service.dao.agreements[1].documents[0].file_path == "vendor-agreements/lease.pdf"
    assert any(a.action == "VENDOR_AGREEMENT_UPLOADED" for a in service.db.added)


def test_uploader_cannot_verify_own_agreement(service):
    _create(service, user="same-user")
    with pytest.raises(PermissionError, match="different user"):
        service.verify(1, "ok", "same-user")
    assert service.dao.agreements[1].status == "PENDING_VERIFICATION"


def test_verify_activates_supersedes_previous_and_rechecks_invoices(service):
    _create(service)
    service.verify(1, "checked", "fin-1")
    _create(service, title="Lease renewal", valid_from=D(2026, 10, 1))
    result = service.verify(2, "renewal checked", "fin-1")

    assert result["status"] == "ACTIVE" and result["is_effective"]
    assert result["rechecked_invoice_count"] == 2
    assert service.dao.agreements[1].status == "SUPERSEDED"
    assert service.rechecks == [5, 5]
    actions = [a.action for a in service.db.added if hasattr(a, "action")]
    assert "VENDOR_AGREEMENT_SUPERSEDED" in actions and actions.count("VENDOR_AGREEMENT_VERIFIED") == 2


def test_verify_requires_terms(service):
    _create(service, payment_terms_text="as agreed between the parties")
    with pytest.raises(ValueError, match="payment terms"):
        service.verify(1, "ok", "fin-1")


def test_reject_needs_remarks(service):
    _create(service)
    with pytest.raises(ValueError, match="Remarks are required"):
        service.reject(1, "no", "fin-1")
    assert service.reject(1, "Wrong vendor on the document", "fin-1")["status"] == "REJECTED"


def test_validation_errors(service):
    with pytest.raises(ValueError, match="valid_to cannot be before valid_from"):
        _create(service, valid_to=D(2026, 1, 1))
    with pytest.raises(ValueError, match="agreement_type"):
        _create(service, agreement_type="LOAN")
    with pytest.raises(vas.AgreementNotFoundError):
        service.create(404, _fields(), "x.pdf", b"x", "application/pdf", "u")


def test_active_agreement_cannot_be_edited(service):
    _create(service)
    service.verify(1, "ok", "fin-1")
    with pytest.raises(ValueError, match="cannot be edited"):
        service.update(1, {"term_days": 30}, "intake-1")


def test_expired_flag_is_computed(service):
    _create(service, valid_from=D(2025, 7, 1), valid_to=D(2026, 6, 30))
    result = service.get(1)
    assert result["is_expired"] and result["days_to_expiry"] < 0


def test_extraction_parsing():
    results = {
        "AGREEMENT_TITLE": {"value": "SaaS Subscription Order Form", "confidence": 95},
        "VALID_FROM": {"value": "01 July 2025", "confidence": 90},
        "VALID_TO": {"value": "30th June 2026", "confidence": 88},
        "PAYMENT_TERMS": {"value": "Subscription fees are due Net 30 from the invoice date.", "confidence": 80},
        "VENDOR_GSTIN": {"value": "GSTIN 36AAFCK5835K1Z6", "confidence": 70},
    }
    data = parse_agreement_fields(results, "")
    assert data["agreement_type"] == "SUBSCRIPTION"
    assert (data["valid_from"], data["valid_to"]) == (D(2025, 7, 1), D(2026, 6, 30))
    assert data["term_days"] == 30 and data["due_basis"] == "INVOICE_DATE"
    assert data["vendor_gstin"] == "36AAFCK5835K1Z6"


def test_extraction_falls_back_to_full_text():
    text = ("This agreement is valid from 01 April 2026 to 31 March 2027 unless terminated. "
            "The Lessee shall pay the monthly rent within fifteen (15) days of receipt of a valid invoice.")
    data = parse_agreement_fields({}, text)
    assert (data["valid_from"], data["valid_to"]) == (D(2026, 4, 1), D(2027, 3, 31))
    assert data["term_days"] == 15


def test_type_guess():
    assert guess_agreement_type("Office Lease Agreement") == "LEASE"
    assert guess_agreement_type("Master Services Agreement") == "MSA"
    assert guess_agreement_type("Purchase terms") == "OTHER"
