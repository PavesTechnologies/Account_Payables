"""Payment-term compliance engine (Business_Layer/services/payment_term_compliance_service.py).

1. decide() - the pure rule table, case by case.
2. Consistency with the synthetic test set: every created scenario in
   test-documents/synthetic_invoices_v1/scenarios.json is re-decided by the real
   engine and must give the documented status, reason and due dates.
3. The service (evaluate / verify / Ready-for-Payment gate) against a fake DAO.
"""
import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import payment_term_compliance_service as ptc
from Backend.Business_Layer.services.payment_term_compliance_service import (
    REASON_AGREEMENT_EXPIRED,
    REASON_GRN_DATE_MISSING,
    REASON_IMPLIED_FROM_PRINTED_DUE_DATE,
    REASON_INVOICE_SILENT_PO_TERMS_APPLIED,
    REASON_INVOICE_TERMS_AMBIGUOUS,
    REASON_INVOICE_TERMS_MISSING,
    REASON_INVOICE_VS_AGREEMENT,
    REASON_INVOICE_VS_PO,
    REASON_INVOICE_VS_VENDOR_MASTER,
    REASON_NO_AUTHORISED_TERMS,
    REASON_PO_NOT_MATCHED,
    REASON_PO_TERMS_MISSING,
    REASON_VENDOR_MASTER_VS_AGREEMENT,
    STATUS_COMPLIANT,
    STATUS_MISMATCH,
    STATUS_REVIEW_REQUIRED,
    STATUS_VERIFIED_OVERRIDE,
    TermInputs,
    decide,
    statutory_limit,
)
from Backend.Business_Layer.utils.payment_term_parser import BASIS_GRN_DATE, BASIS_INVOICE_DATE, parse_payment_terms

D = datetime.date
INV_DATE = D(2026, 8, 1)


def _non_po(**kw):
    return TermInputs(invoice_date=INV_DATE, is_po_invoice=False, **kw)


def _po(**kw):
    kw.setdefault("po_linked", True)
    return TermInputs(invoice_date=INV_DATE, is_po_invoice=True, **kw)


# ---------------------------------------------------------------------------
# 1. Rule table
# ---------------------------------------------------------------------------

def test_po_invoice_matching_po_terms_is_compliant():
    d = decide(_po(invoice_term_days=30, po_term_days=30))
    assert (d.validation_status, d.reason_code, d.reference_source) == (STATUS_COMPLIANT, None, "PO")
    assert d.contractual_due_date == D(2026, 8, 31) == d.effective_due_date
    assert d.due_date_verified


def test_po_invoice_terms_differ_po_terms_apply():
    d = decide(_po(invoice_term_days=30, po_term_days=45))
    assert (d.validation_status, d.reason_code) == (STATUS_MISMATCH, REASON_INVOICE_VS_PO)
    assert d.applied_term_days == 45
    assert d.effective_due_date == D(2026, 9, 15)
    assert not d.due_date_verified


def test_po_invoice_silent_uses_po_terms():
    d = decide(_po(po_term_days=60))
    assert (d.validation_status, d.reason_code, d.applied_term_days) == (
        STATUS_COMPLIANT, REASON_INVOICE_SILENT_PO_TERMS_APPLIED, 60)


def test_po_invoice_without_linked_po_needs_review():
    d = decide(_po(po_linked=False, invoice_term_days=45))
    assert (d.validation_status, d.reason_code) == (STATUS_REVIEW_REQUIRED, REASON_PO_NOT_MATCHED)
    assert d.contractual_due_date is None and d.effective_due_date is None


def test_po_without_terms_needs_review():
    d = decide(_po(invoice_term_days=30, po_term_days=None))
    assert (d.validation_status, d.reason_code, d.suggested_term_days) == (
        STATUS_REVIEW_REQUIRED, REASON_PO_TERMS_MISSING, 30)


def test_grn_basis_counts_from_grn_date():
    d = decide(_po(invoice_term_days=45, invoice_term_basis=BASIS_GRN_DATE, po_term_days=45,
                   po_term_basis=BASIS_GRN_DATE, grn_date=D(2026, 8, 10)))
    assert d.basis_date == D(2026, 8, 10)
    assert d.effective_due_date == D(2026, 9, 24)


def test_grn_basis_without_grn_needs_review_instead_of_using_invoice_date():
    d = decide(_po(po_term_days=45, po_term_basis=BASIS_GRN_DATE, grn_date=None))
    assert (d.validation_status, d.reason_code) == (STATUS_REVIEW_REQUIRED, REASON_GRN_DATE_MISSING)
    assert d.suggested_term_days == 45
    assert d.effective_due_date is None


def test_non_po_missing_terms_is_flagged_not_defaulted():
    d = decide(_non_po(vendor_master_term_days=30))
    assert (d.validation_status, d.reason_code) == (STATUS_REVIEW_REQUIRED, REASON_INVOICE_TERMS_MISSING)
    assert d.suggested_term_days == 30
    assert d.applied_term_days is None and d.effective_due_date is None


def test_non_po_ambiguous_terms_flagged():
    d = decide(_non_po(invoice_terms_ambiguous=True, vendor_master_term_days=30,
                       invoice_due_date_printed=D(2026, 8, 20)))
    # an ambiguous text is not rescued by a printed date - a person must look at it
    assert (d.validation_status, d.reason_code) == (STATUS_REVIEW_REQUIRED, REASON_INVOICE_TERMS_AMBIGUOUS)


def test_non_po_printed_due_date_implies_term():
    d = decide(_non_po(invoice_due_date_printed=D(2026, 8, 16), vendor_master_term_days=15))
    assert (d.validation_status, d.reason_code) == (STATUS_COMPLIANT, REASON_IMPLIED_FROM_PRINTED_DUE_DATE)
    assert d.effective_due_date == D(2026, 8, 16)


def test_non_po_agreement_wins_and_invoice_mismatch_flagged():
    d = decide(_non_po(invoice_term_days=30, agreement_id=7, agreement_term_days=15, vendor_master_term_days=15))
    assert (d.validation_status, d.reason_code, d.reference_source) == (
        STATUS_MISMATCH, REASON_INVOICE_VS_AGREEMENT, "AGREEMENT")
    assert d.applied_term_days == 15


def test_non_po_agreement_and_master_disagree_is_never_silently_resolved():
    d = decide(_non_po(invoice_term_days=45, agreement_id=7, agreement_term_days=45, vendor_master_term_days=30))
    assert (d.validation_status, d.reason_code) == (STATUS_MISMATCH, REASON_VENDOR_MASTER_VS_AGREEMENT)


def test_non_po_vs_vendor_master():
    d = decide(_non_po(invoice_term_days=0, vendor_master_term_days=15))
    assert (d.validation_status, d.reason_code, d.applied_term_days) == (
        STATUS_MISMATCH, REASON_INVOICE_VS_VENDOR_MASTER, 15)


def test_non_po_no_reference_at_all():
    d = decide(_non_po(invoice_term_days=30))
    assert (d.validation_status, d.reason_code, d.reference_source) == (
        STATUS_REVIEW_REQUIRED, REASON_NO_AUTHORISED_TERMS, "NONE")


def test_non_po_expired_agreement_needs_review():
    d = decide(_non_po(invoice_term_days=30, vendor_master_term_days=30, vendor_has_agreement_history=True))
    assert (d.validation_status, d.reason_code, d.suggested_term_days) == (
        STATUS_REVIEW_REQUIRED, REASON_AGREEMENT_EXPIRED, 30)


def test_msme_statutory_limit_caps_effective_due_date():
    d = decide(_po(invoice_term_days=60, po_term_days=60, msme_category="SMALL"))
    assert d.contractual_due_date == D(2026, 9, 30)
    assert d.statutory_due_date == D(2026, 9, 15)
    assert d.effective_due_date == D(2026, 9, 15)
    assert d.statutory_rule == "MSMED_S15_45_DAYS"


def test_msme_medium_has_no_statutory_limit():
    d = decide(_po(invoice_term_days=60, po_term_days=60, msme_category="MEDIUM"))
    assert d.statutory_due_date is None
    assert d.effective_due_date == D(2026, 9, 30)


def test_msme_statutory_deadline_tracked_even_when_terms_unresolved():
    d = decide(_non_po(msme_category="MICRO"))  # no terms anywhere -> 15-day statutory default
    assert d.validation_status == STATUS_REVIEW_REQUIRED
    assert d.statutory_due_date == D(2026, 8, 16)
    assert d.statutory_rule == "MSMED_S15_15_DAYS_NO_AGREEMENT"
    assert d.effective_due_date == D(2026, 8, 16)


def test_statutory_limit_respects_configured_days():
    due, rule = statutory_limit("MICRO", 40, INV_DATE, max_days=30, default_days=10)
    assert due == D(2026, 8, 31) and rule == "MSMED_S15_30_DAYS"


# ---------------------------------------------------------------------------
# 2. Consistency with the synthetic invoice set
# ---------------------------------------------------------------------------

MANIFEST = Path(__file__).resolve().parents[2] / "test-documents" / "synthetic_invoices_v1" / "scenarios.json"


def _scenario_cases():
    if not MANIFEST.exists():
        return []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = []
    for sc in manifest["scenarios"]:
        if sc["expected"]["payment_terms"]:
            cases.append(pytest.param(manifest, sc, id=sc["id"]))
    return cases


@pytest.mark.parametrize("manifest, sc", _scenario_cases())
def test_engine_matches_documented_scenario(manifest, sc):
    expected = sc["expected"]["payment_terms"]
    vendor = manifest["vendors"][sc["vendor_key"]]
    inv_date = D.fromisoformat(sc["invoice_date"])
    parsed = parse_payment_terms(expected["invoice_terms_text"])
    printed = expected["printed_due_date"]
    is_po = sc["invoice_type"] == "PO"

    po_days = po_basis = grn = None
    po_linked = False
    if is_po:
        po = manifest["purchase_orders"][sc["po_number"]]
        po_parsed = parse_payment_terms(po["terms"])
        po_days, po_basis = po_parsed.days, po_parsed.basis
        grn = D.fromisoformat(po["grn"]) if po["grn"] else None
        po_linked = sc["po_number_printed"] == sc["po_number"]

    agreements = [a for a in manifest["agreements"] if a["vendor"] == sc["vendor_key"]]
    valid = [a for a in agreements if D.fromisoformat(a["valid_from"]) <= inv_date <= D.fromisoformat(a["valid_to"])]

    decision = decide(TermInputs(
        invoice_date=inv_date,
        is_po_invoice=is_po,
        invoice_term_days=parsed.days,
        invoice_term_basis=parsed.basis,
        invoice_terms_ambiguous=parsed.kind == "AMBIGUOUS",
        # the generator prints a due date derived from the terms; only an explicitly printed
        # date with no terms text acts as the invoice's own statement
        invoice_due_date_printed=D.fromisoformat(printed) if printed and not expected["invoice_terms_text"] else None,
        po_linked=po_linked,
        po_term_days=po_days,
        po_term_basis=po_basis or BASIS_INVOICE_DATE,
        grn_date=grn,
        agreement_id=1 if valid else None,
        agreement_term_days=valid[0]["term_days"] if valid else None,
        vendor_has_agreement_history=bool(agreements),
        vendor_master_term_days=parse_payment_terms(vendor["master_payment_term"]).days,
        msme_category=vendor.get("msme_category"),
    ))

    assert decision.validation_status == expected["validation_status"]
    assert decision.reason_code == expected["reason"]
    if expected["validation_status"] != STATUS_REVIEW_REQUIRED:
        assert decision.applied_term_days == expected["applied_term_days"]
        assert str(decision.contractual_due_date) == str(expected["contractual_due_date"])
    assert (decision.statutory_due_date.isoformat() if decision.statutory_due_date else None) == expected["statutory_due_date"]
    if expected["effective_due_date"]:
        assert decision.effective_due_date.isoformat() == expected["effective_due_date"]


def test_manifest_present_so_consistency_tests_actually_ran():
    assert MANIFEST.exists(), "regenerate with Backend/scripts/generate_test_invoices.py"
    assert len(_scenario_cases()) >= 45


# ---------------------------------------------------------------------------
# 3. Service against a fake DAO
# ---------------------------------------------------------------------------

class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


class _FakeDAO:
    def __init__(self, invoice, vendor, po=None, agreements=(), terms=None, grn=None):
        self.invoice, self.vendor, self.po, self.grn = invoice, vendor, po, grn
        self.agreements = list(agreements)
        self.terms = terms or {}
        self.record = None

    def add(self, obj):
        self.record = obj
        return obj

    def get_record(self, invoice_id):
        return self.record

    def get_invoice(self, invoice_id):
        return self.invoice

    def get_vendor(self, vendor_id):
        return self.vendor

    def get_payment_term(self, term_id):
        return self.terms.get(term_id)

    def get_purchase_order(self, po_id):
        return self.po if po_id is not None else None

    def get_goods_receipt(self, grn_id):
        return self.grn

    def get_latest_goods_receipt_for_po(self, po_id):
        return self.grn

    def get_active_agreements_valid_on(self, vendor_id, on_date):
        return [a for a in self.agreements if a.valid_from <= on_date <= (a.valid_to or on_date)]

    def has_any_active_agreement_history(self, vendor_id):
        return bool(self.agreements)

    def list_open_invoice_ids_for_vendor(self, vendor_id, closed):
        return [self.invoice.invoice_id]


def _invoice(**kw):
    base = dict(invoice_id=1, vendor_id=5, invoice_type="NON_PO", invoice_date=INV_DATE, due_date=INV_DATE,
                payment_term_id=None, po_id=None, grn_id=None, updated_by=None,
                status=SimpleNamespace(status_code="APPROVED"), inbound_document=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _vendor(term_id=None, msme=None):
    return SimpleNamespace(vendor_id=5, payment_term_id=term_id, msme_registered=bool(msme), msme_category=msme)


TERMS = {3: SimpleNamespace(payment_term_id=3, due_days=30, term_name="Net 30"),
         5: SimpleNamespace(payment_term_id=5, due_days=60, term_name="Net 60")}


@pytest.fixture
def make_service(monkeypatch):
    monkeypatch.setattr(ptc, "get_numeric_system_config", lambda db, key, default=None: default)

    def factory(invoice, vendor, **kw):
        service = ptc.PaymentTermComplianceService(_FakeDB(), today=D(2026, 10, 9))
        service.dao = _FakeDAO(invoice, vendor, terms=TERMS, **kw)
        return service
    return factory


def test_evaluate_sets_due_date_from_terms_not_invoice_date(make_service):
    invoice = _invoice()
    service = make_service(invoice, _vendor(term_id=3))
    record = service.evaluate_invoice(invoice, "ap-1", stated_terms_text="30 days credit", stated_due_date=None)
    assert record.validation_status == STATUS_COMPLIANT
    assert invoice.due_date == D(2026, 8, 31)
    audit = [a for a in service.db.added if getattr(a, "action", None) == "INVOICE_PAYMENT_TERMS_CHECKED"]
    assert len(audit) == 1 and audit[0].new_values["validation_status"] == STATUS_COMPLIANT


def test_unresolved_terms_keep_stated_terms_due_date_and_block_payment(make_service):
    invoice = _invoice()
    service = make_service(invoice, _vendor(term_id=None))
    record = service.evaluate_invoice(invoice, "ap-1", stated_terms_text="Net 45", stated_due_date=None)
    assert (record.validation_status, record.reason_code) == (STATUS_REVIEW_REQUIRED, REASON_NO_AUTHORISED_TERMS)
    assert invoice.due_date == D(2026, 9, 15)  # invoice-stated terms, never the bare invoice date
    assert record.due_date_verified is False
    with pytest.raises(ValueError, match="Payment terms must be verified"):
        service.require_resolved_for_payment(invoice)


def test_verify_resolves_and_unblocks(make_service):
    invoice = _invoice()
    service = make_service(invoice, _vendor(term_id=3))
    service.evaluate_invoice(invoice, "ap-1", stated_terms_text="Net 60", stated_due_date=None)
    assert service.dao.record.validation_status == STATUS_MISMATCH

    with pytest.raises(ValueError, match="Remarks are required"):
        service.verify(1, 30, "INVOICE_DATE", "ok", "fin-1")

    record = service.verify(1, 30, "INVOICE_DATE", "Confirmed Net 30 with vendor by email", "fin-1")
    assert record.validation_status == STATUS_VERIFIED_OVERRIDE
    assert record.reference_source == "VENDOR_MASTER"
    assert record.verified_by == "fin-1"
    assert invoice.due_date == D(2026, 8, 31)
    assert service.require_resolved_for_payment(invoice) is record
    audit = [a for a in service.db.added if getattr(a, "action", None) == "INVOICE_PAYMENT_TERMS_VERIFIED"]
    assert audit and audit[-1].old_values["validation_status"] == STATUS_MISMATCH


def test_override_survives_recheck_but_not_a_change_of_source_terms(make_service):
    invoice = _invoice()
    vendor = _vendor(term_id=3)
    service = make_service(invoice, vendor)
    service.evaluate_invoice(invoice, "ap-1", stated_terms_text="Net 60", stated_due_date=None)
    service.verify(1, 30, "INVOICE_DATE", "Confirmed Net 30 with vendor", "fin-1")

    service.evaluate_invoice(invoice, "sys")
    assert service.dao.record.validation_status == STATUS_VERIFIED_OVERRIDE

    vendor.payment_term_id = 5  # vendor master changed to Net 60 -> override no longer applies
    record = service.evaluate_invoice(invoice, "sys")
    assert record.validation_status == STATUS_COMPLIANT
    assert record.verified_by is None
    assert "no longer applies" in record.reason_detail


def test_verify_refused_on_closed_invoice(make_service):
    invoice = _invoice(status=SimpleNamespace(status_code="PAID"))
    service = make_service(invoice, _vendor(term_id=3))
    with pytest.raises(ValueError, match="cannot be changed while the invoice is PAID"):
        service.verify(1, 30, "INVOICE_DATE", "late correction", "fin-1")


def test_verify_with_grn_basis_needs_a_grn(make_service):
    invoice = _invoice(invoice_type="PO", po_id=9)
    po = SimpleNamespace(po_id=9, payment_terms="Net 45", payment_term_id=None)
    service = make_service(invoice, _vendor(), po=po)
    with pytest.raises(ValueError, match="goods-receipt date"):
        service.verify(1, 45, "GRN_DATE", "Use GRN basis per PO", "fin-1")


def test_raw_extraction_used_when_nothing_stated(make_service):
    raw = {"document": {"due_date": "2026-08-16"}, "payment": {"payment_terms": None}}
    invoice = _invoice(inbound_document=SimpleNamespace(raw_extracted_data=raw))
    service = make_service(invoice, _vendor(term_id=None))
    service.dao.terms = {2: SimpleNamespace(payment_term_id=2, due_days=15, term_name="Net 15")}
    service.dao.vendor.payment_term_id = 2
    record = service.evaluate_invoice(invoice, "ap-1")
    assert (record.validation_status, record.reason_code) == (STATUS_COMPLIANT, REASON_IMPLIED_FROM_PRINTED_DUE_DATE)
    assert record.invoice_due_date_printed == D(2026, 8, 16)
