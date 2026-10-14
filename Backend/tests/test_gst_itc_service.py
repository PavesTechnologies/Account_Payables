"""GST input credit: CGST/SGST/IGST split, blocked-credit hints, GSTR-3B due date, IRN and 180-day rule."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import gst_itc_service as gst
from Backend.Data_Access_Layer.models.invoice_gst import InvoiceGst

D = Decimal


def test_split_uses_the_invoice_split_when_it_adds_up():
    extracted = {"amounts": {"cgst_amount": 21600.0, "sgst_amount": 21600.0}}
    assert gst.split_tax(D("43200"), "36", "36", extracted) == {"cgst": D("21600.00"), "sgst": D("21600.00"),
                                                                 "igst": D("0.00"), "cess": D("0.00"), "supply_type": "INTRA"}


def test_split_derived_from_states_when_ocr_is_missing_or_wrong():
    inter = gst.split_tax(D("35208"), "07", "36", {"amounts": {"igst_amount": 999.0}})  # OCR total doesn't match
    assert inter["igst"] == D("35208.00") and inter["supply_type"] == "INTER"
    intra = gst.split_tax(D("8244.01"), "36", "36", None)
    assert intra["cgst"] + intra["sgst"] == D("8244.01") and intra["supply_type"] == "INTRA"


def test_blocked_credit_hints():
    assert "Food" in gst.eligibility_hint([("996331", "Team lunch")])
    assert "cab" in gst.eligibility_hint([(None, "Airport cab - client visit")]).lower()
    assert gst.eligibility_hint([("998315", "Amazon EC2 - compute")]) is None


def test_gstr3b_due_is_the_20th_of_next_month():
    assert gst.gstr3b_due(datetime.date(2026, 9, 1)) == datetime.date(2026, 10, 20)
    assert gst.gstr3b_due(datetime.date(2026, 12, 1)) == datetime.date(2027, 1, 20)


class _Db:
    def __init__(self, row):
        self.row, self.added = row, []

    def get(self, model, key):
        return self.row

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass


def test_irn_must_be_64_hex_and_is_audited():
    row = InvoiceGst(invoice_id=7, irn_status="MISSING", itc_status="PENDING")
    db = _Db(row)
    svc = gst.GstItcService(db, einvoice_lookup=lambda g: True)
    with pytest.raises(ValueError, match="64 characters"):
        svc.set_irn(7, "not-an-irn", None, "5100020")
    irn = "a" * 64
    svc.set_irn(7, irn.upper(), "112610012345678", "5100020")
    assert row.irn == irn and row.irn_status == "PRESENT" and row.ack_no == "112610012345678"
    assert db.added[-1].action == "GST_IRN_RECORDED"


def test_eligibility_override_rules():
    row = InvoiceGst(invoice_id=7, itc_eligibility="REVIEW", itc_status="PENDING")
    svc = gst.GstItcService(_Db(row), einvoice_lookup=lambda g: None)
    svc.set_eligibility(7, "BLOCKED", "Staff lunch - s.17(5)", "5100026")
    assert row.itc_status == "NOT_CLAIMABLE" and row.eligibility_locked is True
    row.itc_status = "CLAIMED"
    with pytest.raises(ValueError, match="already claimed"):
        svc.set_eligibility(7, "ELIGIBLE", "Changed my mind", "5100026")


def _view(svc, age_days, status, itc_status="CLAIMED"):
    invoice = SimpleNamespace(invoice_id=1, invoice_number="X", invoice_date=svc.today - datetime.timedelta(days=age_days))
    row = InvoiceGst(invoice_id=1, cgst=D("9"), sgst=D("9"), igst=D("0"), cess=D("0"), itc_eligibility="ELIGIBLE",
                     itc_status=itc_status, irn_status="PRESENT")
    return svc._view(row, invoice, status, "Vendor")


def test_180_day_rule_states():
    svc = gst.GstItcService(db=None, today=datetime.date(2026, 10, 12), einvoice_lookup=lambda g: None)
    assert _view(svc, 100, "READY_FOR_PAYMENT")["risk"] is None
    assert _view(svc, 160, "READY_FOR_PAYMENT")["risk"] == "AT_RISK"
    assert _view(svc, 190, "READY_FOR_PAYMENT")["risk"] == "REVERSAL_DUE"
    assert _view(svc, 190, "PAID")["risk"] is None
    assert _view(svc, 200, "PAID", itc_status="REVERSED")["risk"] == "RECLAIM"
    claimable = _view(svc, 20, "APPROVED", itc_status="PENDING")
    assert claimable["claimable"] is True and claimable["itc"] == D("18")
    assert _view(svc, 20, "PENDING_APPROVAL", itc_status="PENDING")["claimable"] is False
