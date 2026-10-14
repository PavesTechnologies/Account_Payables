"""MSME: s.15 status and s.16 interest, s.43B(h) year-end outcome, Form-1 half years."""
import datetime
from decimal import Decimal

import pytest

from Backend.Business_Layer.services import msme_compliance_service as ms

D = Decimal
d = datetime.date


def _inv(due=D("100000"), statutory=d(2026, 3, 20), settlements=(), invoice_date=d(2026, 2, 3)):
    return ms.MsmeInvoice(1, "INV-1", invoice_date, 9, "Small Co", "TSTPN0000T", "UDYAM-XX-00-0000000", "SMALL", due,
                          statutory, "MSMED_S15_45_DAYS", "Ready for payment", list(settlements))


class _Svc(ms.MsmeComplianceService):
    def __init__(self, today, rows=()):
        super().__init__(None, today=today)
        self.rows = list(rows)

    def bank_rate(self):
        return D("6.00")  # 3 x 6% = 18% a year, 1.5% a month

    def invoices(self, invoice_from=None, invoice_to=None):
        return [r for r in self.rows if (invoice_from is None or r.invoice_date >= invoice_from)
                and (invoice_to is None or r.invoice_date <= invoice_to)]


def test_interest_compounds_monthly_at_three_times_bank_rate():
    one_year = ms.s16_interest(D("100000"), 365, D("6.00"))
    assert one_year == D("19561.82")  # (1.015)^12 - 1, not simple 18%
    assert ms.s16_interest(D("100000"), 0, D("6.00")) == 0 and ms.s16_interest(D("0"), 30, D("6")) == 0


def test_status_on_time_late_overdue_due_soon():
    svc = _Svc(d(2026, 4, 30))
    on_time = svc.invoice_status(_inv(settlements=[(d(2026, 3, 18), D("100000"))]))
    assert on_time["status"] == "Paid on time" and on_time["interest_s16"] == 0 and on_time["paid_on"] == d(2026, 3, 18)
    late = svc.invoice_status(_inv(settlements=[(d(2026, 3, 10), D("40000")), (d(2026, 4, 19), D("60000"))]))
    assert late["status"] == "Paid late" and late["days_late"] == 30 and late["late_amount"] == D("60000")
    assert late["interest_s16"] > 0
    overdue = svc.invoice_status(_inv())
    assert overdue["status"] == "Overdue" and overdue["outstanding"] == D("100000") and overdue["days_late"] == 41
    soon = _Svc(d(2026, 3, 15)).invoice_status(_inv())
    assert soon["status"] == "Due soon" and soon["interest_s16"] == 0


def test_fy_and_half_year_bounds():
    assert ms.fy_bounds(d(2026, 2, 1)) == (d(2025, 4, 1), d(2026, 3, 31))
    assert ms.fy_bounds(d(2026, 4, 1)) == (d(2026, 4, 1), d(2027, 3, 31))
    assert ms.half_year(d(2026, 9, 30)) == (d(2026, 4, 1), d(2026, 9, 30), d(2026, 10, 31))
    assert ms.half_year(d(2027, 2, 1)) == (d(2026, 10, 1), d(2027, 3, 31), d(2027, 4, 30))


@pytest.mark.parametrize("settlements, today, outcome, disallowed, at_risk", [
    ([(d(2026, 3, 25), D("100000"))], d(2026, 6, 1), None, None, None),                                   # paid in the year
    ([(d(2026, 4, 10), D("100000"))], d(2026, 6, 1), "Allowed", D("0"), D("0")),                            # after YE, in time
    ([(d(2026, 5, 20), D("100000"))], d(2026, 6, 1), "Disallowed - paid after", D("100000"), D("0")),
    ([], d(2026, 6, 1), "Disallowed - unpaid", D("100000"), D("0")),
    ([], d(2026, 4, 5), "At risk", D("0"), D("100000")),
])
def test_43bh_outcomes(settlements, today, outcome, disallowed, at_risk):
    inv = _inv(statutory=d(2026, 4, 15), settlements=settlements, invoice_date=d(2026, 3, 1))
    rows = _Svc(today, [inv]).s43bh(d(2025, 4, 1), d(2026, 3, 31))
    if outcome is None:
        assert rows == []
        return
    assert rows[0]["outcome"].startswith(outcome)
    assert rows[0]["disallowed"] == disallowed and rows[0]["at_risk"] == at_risk


def test_form1_lists_dues_beyond_the_limit_at_half_year_end():
    late = _inv(statutory=d(2026, 9, 10), invoice_date=d(2026, 7, 27))
    not_yet = _inv(statutory=d(2026, 10, 5), invoice_date=d(2026, 8, 21))
    paid = _inv(statutory=d(2026, 9, 1), settlements=[(d(2026, 9, 20), D("100000"))], invoice_date=d(2026, 7, 18))
    rows = _Svc(d(2026, 10, 14), [late, not_yet, paid]).form1(d(2026, 9, 30))
    assert len(rows) == 1 and rows[0]["due_from"] == d(2026, 9, 11) and rows[0]["days_outstanding"] == 20
    assert rows[0]["pan"] == "TSTPN0000T"


def test_form1_reminder_only_in_the_filing_window():
    inv = _inv(statutory=d(2026, 9, 10), invoice_date=d(2026, 7, 27))
    assert _Svc(d(2026, 10, 14), [inv]).attention() == {}          # 17 days before 31 Oct
    reminder = _Svc(d(2026, 10, 20), [inv]).attention()
    assert reminder["due"] == d(2026, 10, 31) and reminder["invoices"] == 1 and reminder["amount"] == D("100000")
