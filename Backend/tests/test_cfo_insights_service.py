"""CFO insights: DPO against a target, and the month-end date."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

from Backend.Business_Layer.services import cfo_insights_service as cfo

D = Decimal
d = datetime.date


def _fig(invoice_id, invoice_date, payable):
    return SimpleNamespace(invoice_id=invoice_id, invoice_date=invoice_date, net_payable=D(payable))


def test_dpo_is_what_we_owe_over_90_days_of_purchases():
    today = d(2026, 10, 26)
    figures = [_fig(1, d(2026, 9, 1), "90000"), _fig(2, d(2026, 10, 10), "90000"), _fig(3, d(2026, 5, 1), "50000")]
    payments = [(1, d(2026, 9, 20), D("90000")), (3, d(2026, 5, 20), D("50000"))]
    # owed today = 90,000 (invoice 2); purchases in the last 90 days = 180,000 -> 90,000 / 180,000 x 90 = 45 days
    assert cfo.CfoInsightsService._dpo_at(today, figures, payments) == 45.0
    # nothing invoiced in the window -> no DPO rather than a divide-by-zero
    assert cfo.CfoInsightsService._dpo_at(d(2026, 1, 1), figures, payments) is None


def test_dpo_band_against_the_target(monkeypatch):
    svc = cfo.CfoInsightsService(None, today=d(2026, 10, 26))
    monkeypatch.setattr(svc, "_target", lambda: (30, 45))
    monkeypatch.setattr(svc, "_ledger", lambda: ([_fig(1, d(2026, 10, 1), "100")], []))
    out = svc.dpo()  # everything still owed: 100 / 100 x 90 = 90 days, above the band
    assert out["value"] == 90.0 and out["band"] == "high" and out["target_max"] == 45


def test_month_end():
    assert cfo.month_end(d(2026, 2, 10)) == d(2026, 2, 28)
    assert cfo.month_end(d(2026, 12, 31)) == d(2026, 12, 31)
