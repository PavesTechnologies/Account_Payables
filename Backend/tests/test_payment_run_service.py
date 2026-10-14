"""Payment runs: NEFT/RTGS choice, transfer references, bank response parsing, maker-checker, guards."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import payment_run_service as prs
from Backend.Data_Access_Layer.models.payment_run import PaymentRun


def test_mode_and_reference():
    assert prs.mode_for(Decimal("199999.99")) == "NEFT"
    assert prs.mode_for(Decimal("200000")) == "RTGS"
    assert prs.run_reference(7, 15) == "PR00007V00015"


def test_bank_response_csv():
    content = ("Customer Reference,UTR,Status,Reason\n"
               "PR00007V00015,HDFCR26287123456,Success,\n"
               "PR00007V00016,,Failed,Beneficiary account closed\n"
               ",,,\n").encode()
    rows = prs.PaymentRunService(db=None).parse_response(content)
    assert rows == [{"reference": "PR00007V00015", "status": "PAID", "utr": "HDFCR26287123456", "reason": None},
                    {"reference": "PR00007V00016", "status": "FAILED", "utr": None, "reason": "Beneficiary account closed"}]
    with pytest.raises(ValueError, match="Customer Reference"):
        prs.PaymentRunService(db=None).parse_response(b"a,b\n1,2\n")


class _Db:
    def __init__(self, run):
        self.run = run

    def get(self, model, key):
        return self.run


def _run(status, created_by="5100020"):
    return PaymentRun(run_id=7, name="Week 42", value_date=datetime.date(2026, 10, 16), status=status, created_by=created_by,
                      submitted_by=created_by)


def test_maker_cannot_approve_own_run():
    svc = prs.PaymentRunService(_Db(_run("SUBMITTED")))
    with pytest.raises(ValueError, match="someone else must approve"):
        svc.approve(7, "5100020")


def test_steps_only_in_the_right_status():
    svc = prs.PaymentRunService(_Db(_run("DRAFT")))
    with pytest.raises(ValueError, match="draft"):
        svc.approve(7, "5100026")
    with pytest.raises(ValueError, match="draft"):
        svc.bank_file(7, "GENERIC_CSV", "5100020")
    with pytest.raises(ValueError, match="draft"):
        svc.confirm(7, [], "5100020")


def test_create_validates_before_anything_is_written(monkeypatch):
    svc = prs.PaymentRunService(_Db(None), today=datetime.date(2026, 10, 14))
    with pytest.raises(ValueError, match="name"):
        svc.create(" ", datetime.date(2026, 10, 16), [1], "5100020")
    with pytest.raises(ValueError, match="past"):
        svc.create("Week 42", datetime.date(2026, 10, 1), [1], "5100020")
    monkeypatch.setattr(svc, "candidates", lambda due_by=None: [
        {"invoice_id": 1, "invoice_number": "AWSIN26-1", "blocked": "Vendor bank account not verified and approved"}])
    with pytest.raises(ValueError, match="not verified and approved"):
        svc.create("Week 42", datetime.date(2026, 10, 16), [1, 2], "5100020")
