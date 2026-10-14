"""Recurring schedules: billing periods, amount variance, schedule choice, period state, fast-track rules."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import recurring_service as rs
from Backend.Data_Access_Layer.models.recurring_schedule import RecurringOccurrence

D = Decimal


def _schedule(**kw):
    base = dict(frequency="MONTHLY", start_date=datetime.date(2026, 4, 1), match_keyword=None, end_date=None)
    return SimpleNamespace(**{**base, **kw})


def test_period_of_monthly_and_quarterly():
    monthly = _schedule()
    assert rs.period_of(monthly, datetime.date(2026, 10, 12)) == datetime.date(2026, 10, 1)
    quarterly = _schedule(frequency="QUARTERLY")
    assert rs.period_of(quarterly, datetime.date(2026, 6, 30)) == datetime.date(2026, 4, 1)
    assert rs.period_of(quarterly, datetime.date(2026, 7, 1)) == datetime.date(2026, 7, 1)
    yearly = _schedule(frequency="YEARLY", start_date=datetime.date(2026, 7, 15))
    assert rs.period_of(yearly, datetime.date(2027, 3, 1)) == datetime.date(2026, 7, 1)


def test_variance_within_over_under():
    assert rs.variance(D("283200"), D("283200"), D("2")) == (D("0.00"), "WITHIN")
    assert rs.variance(D("100000"), D("101500"), D("2")) == (D("1.50"), "WITHIN")
    assert rs.variance(D("283200"), D("318600"), D("2")) == (D("12.50"), "OVER")
    assert rs.variance(D("45000"), D("40000"), D("10"))[1] == "UNDER"


def test_keyword_picks_the_account_and_never_guesses():
    prod, dev = _schedule(match_keyword="a/c 4417"), _schedule(match_keyword="a/c 2290")
    plain = _schedule()
    assert rs.pick_schedules([prod, dev], "Amazon EC2 - Production a/c 4417") == [prod]
    assert rs.pick_schedules([prod, dev], "Amazon Redshift - Data a/c 8830") == []  # unscheduled account
    assert rs.pick_schedules([prod, plain], "something else") == [plain]
    assert rs.pick_schedules([plain], "") == [plain]


def test_occurrence_state():
    svc = rs.RecurringService(db=None, today=datetime.date(2026, 10, 12))
    occ = lambda d, status="EXPECTED": RecurringOccurrence(expected_date=d, status=status)
    assert svc.state(occ(datetime.date(2026, 10, 20)), 5) == "UPCOMING"
    assert svc.state(occ(datetime.date(2026, 10, 10)), 5) == "DUE"
    assert svc.state(occ(datetime.date(2026, 10, 1)), 5) == "MISSING"
    assert svc.state(occ(datetime.date(2026, 10, 1), "RECEIVED"), 5) == "RECEIVED"


def test_schedule_validation():
    svc = rs.RecurringService(db=None)
    good = {"name": "Rent", "expected_amount": D("1000"), "start_date": datetime.date(2026, 4, 1)}
    svc._validate(good)
    for bad, msg in [({"name": ""}, "Name"), ({"expected_amount": D("0")}, "greater than zero"),
                     ({"expected_day": 31}, "between 1 and 28"), ({"frequency": "WEEKLY"}, "Frequency"),
                     ({"end_date": datetime.date(2026, 1, 1)}, "End date")]:
        with pytest.raises(ValueError, match=msg):
            svc._validate({**good, **bad})


class _FastTrackDb:
    def __init__(self, invoice, agreement=None):
        self.invoice, self.agreement = invoice, agreement

    def get(self, model, key):
        return self.agreement if model.__name__ == "VendorAgreement" else self.invoice

    def rollback(self):
        pass


@pytest.mark.parametrize("fast_track, variance, agreement_status, expected", [
    (True, "WITHIN", "ACTIVE", True),
    (False, "WITHIN", "ACTIVE", False),   # schedule not marked fast-track
    (True, "OVER", "ACTIVE", False),      # amount outside tolerance
    (True, "WITHIN", "EXPIRED", False),   # agreement not active
])
def test_fast_track_rules(monkeypatch, fast_track, variance, agreement_status, expected):
    invoice = SimpleNamespace(invoice_id=5, invoice_date=datetime.date(2026, 10, 1))
    agreement = SimpleNamespace(status=agreement_status, valid_from=datetime.date(2026, 4, 1), valid_to=None)
    schedule = SimpleNamespace(fast_track=fast_track, agreement_id=3, name="WeWork desks", tolerance_pct=D("2"))
    occ = SimpleNamespace(schedule=schedule, variance_status=variance, variance_pct=D("0.00"),
                          period_start=datetime.date(2026, 10, 1))
    svc = rs.RecurringService(_FastTrackDb(invoice, agreement))
    monkeypatch.setattr(svc, "occurrence_for_invoice", lambda i: occ)
    approved = []

    class Approvals:
        def __init__(self, db):
            pass

        def auto_approve(self, invoice_id, actor, reason, label):
            approved.append((invoice_id, actor, label))
    import Backend.Business_Layer.services.invoice_approval_service as ias
    monkeypatch.setattr(ias, "InvoiceApprovalService", Approvals)
    result = svc.fast_track(5)
    assert bool(result) is expected
    assert approved == ([(5, "RECURRING_SCHEDULE", "recurring schedule")] if expected else [])
