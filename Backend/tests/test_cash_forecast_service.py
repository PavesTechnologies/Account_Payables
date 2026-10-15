"""Forecast estimates: recurring invoices not yet received, and TDS to deposit."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

from Backend.Business_Layer.services import cash_forecast_service as cf

D = Decimal
d = datetime.date


class _Result:
    def __init__(self, rows):
        self.rows = list(rows)

    def all(self):
        return self.rows

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self.rows)


class _SeqDb:
    """Answers the service's queries in the order recurring() asks them."""
    def __init__(self, *answers):
        self.answers = list(answers)

    def execute(self, *a, **k):
        return _Result(self.answers.pop(0))

    def rollback(self):
        pass


def _recurring(today, schedules, occurrences=(), agreements=(), payment_terms=(), vendor_terms=(), horizon=None):
    db = _SeqDb(schedules,                    # active schedules
                payment_terms, agreements, vendor_terms,  # _term_days
                [(s.vendor_id, "Vendor") for s in schedules],  # vendor names
                occurrences)
    return cf.CashForecastService(db, today=today).recurring(horizon)


def _schedule(**kw):
    base = dict(schedule_id=1, vendor_id=1, name="Rent", frequency="MONTHLY", expected_day=1, expected_amount=D("100000"),
                start_date=d(2026, 4, 1), end_date=None, agreement_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _occ(period, status, amount="100000"):
    return SimpleNamespace(schedule_id=1, period_start=period, expected_date=period, status=status, expected_amount=D(amount))


def test_recurring_estimates_skip_received_and_keep_late_invoices():
    rows = _recurring(d(2026, 10, 15), [_schedule(agreement_id=5)],
                      [_occ(d(2026, 9, 1), "RECEIVED"), _occ(d(2026, 10, 1), "EXPECTED")],
                      agreements=[SimpleNamespace(agreement_id=5, term_days=10, payment_term_id=None)], horizon=d(2026, 12, 31))
    assert [r["period_start"] for r in rows] == [d(2026, 10, 1), d(2026, 11, 1), d(2026, 12, 1)]
    late = rows[0]
    assert late["late"] and late["due_date"] == d(2026, 10, 15)          # overdue estimate placed on today
    assert rows[1]["due_date"] == d(2026, 11, 11)                      # expected day + payment-term days


def test_quarterly_and_ended_schedules():
    q = _recurring(d(2026, 10, 15), [_schedule(frequency="QUARTERLY", start_date=d(2026, 4, 1))], horizon=d(2027, 3, 31))
    assert [r["period_start"] for r in q] == [d(2026, 10, 1), d(2027, 1, 1)]
    ended = _recurring(d(2026, 10, 15), [_schedule(end_date=d(2026, 11, 30))], horizon=d(2027, 3, 31))
    assert [r["period_start"] for r in ended] == [d(2026, 10, 1), d(2026, 11, 1)]


def test_vendor_payment_term_used_without_an_agreement():
    rows = _recurring(d(2026, 10, 15), [_schedule()], payment_terms=[(3, 30)], vendor_terms=[(1, 3)], horizon=d(2026, 12, 31))
    assert [r["due_date"] for r in rows] == [d(2026, 10, 31), d(2026, 12, 1), d(2026, 12, 31)]  # expected day + 30 days


def test_on_day_clamps_to_month_end():
    assert cf._on_day(d(2026, 2, 1), 31) == d(2026, 2, 28)


class _TdsDb:
    def __init__(self, deducted):
        self.deducted = deducted

    def execute(self, *a, **k):
        return SimpleNamespace(all=lambda: self.deducted)


def test_tds_deposits_by_the_7th_deducted_and_projected(monkeypatch):
    import Backend.Business_Layer.utils.statutory_calendar as sc
    monkeypatch.setattr(sc, "configured_deposit_days", lambda db: (7, 30))
    svc = cf.CashForecastService(_TdsDb([(d(2026, 9, 20), D("5000")), (d(2026, 10, 3), D("2000"))]), today=d(2026, 10, 15))
    open_items = [SimpleNamespace(tds_amount=D("3000"), tracking=None, due_verified=True, due_date=d(2026, 10, 25)),
                  SimpleNamespace(tds_amount=D("900"), tracking=SimpleNamespace(tracking_status="TDS_DEDUCTED"),
                                  due_verified=True, due_date=d(2026, 10, 1))]  # already counted as deducted
    rows = {r["due_date"]: r for r in svc.tds(d(2026, 12, 31), open_items)}
    assert rows[d(2026, 10, 7)]["overdue"] and rows[d(2026, 10, 7)]["amount"] == D("5000.00")
    assert rows[d(2026, 11, 7)]["deducted"] == D("2000.00") and rows[d(2026, 11, 7)]["projected"] == D("3000.00")
    march = cf.CashForecastService(_TdsDb([(d(2027, 3, 10), D("100"))]), today=d(2027, 3, 15)).tds(d(2027, 5, 31))
    assert march[0]["due_date"] == d(2027, 4, 30)
