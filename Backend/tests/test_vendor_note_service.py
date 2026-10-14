"""Credit / debit notes: validation when recording, and payables unchanged until the table exists."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import vendor_note_service as vns


class _Db:
    """Enough of a session for record()'s checks that run before anything is written."""

    def __init__(self, vendor=True, invoice=None):
        self.vendor, self.invoice = vendor, invoice

    def get(self, model, key):
        if model.__name__ == "Vendor":
            return SimpleNamespace(vendor_id=key) if self.vendor else None
        return self.invoice

    def execute(self, stmt):
        return SimpleNamespace(first=lambda: None)


GOOD = {"note_type": "CREDIT_NOTE", "vendor_id": 15, "note_number": "CN-1", "note_date": datetime.date(2026, 10, 8),
        "reason": "Service credit for downtime", "taxable_value": "20000", "igst": "3600"}


@pytest.mark.parametrize("change, message", [
    ({"note_type": "REFUND"}, "Note type"),
    ({"note_number": " "}, "Note number"),
    ({"note_date": datetime.date.today() + datetime.timedelta(days=1)}, "future"),
    ({"reason": "x"}, "reason"),
    ({"taxable_value": "0"}, "greater than zero"),
    ({"note_type": "DEBIT_NOTE"}, "carries no GST"),
    ({"cgst": "1800", "sgst": "1800"}, "not both"),
])
def test_record_rejects_bad_notes(change, message):
    with pytest.raises(ValueError, match=message):
        vns.VendorNoteService(_Db()).record({**GOOD, **change}, "5100020")


def test_unknown_vendor_and_foreign_invoice():
    with pytest.raises(ValueError, match="Vendor not found"):
        vns.VendorNoteService(_Db(vendor=False)).record(GOOD, "5100020")
    other = SimpleNamespace(vendor_id=99, invoice_date=datetime.date(2026, 9, 1))
    with pytest.raises(ValueError, match="not from this vendor"):
        vns.VendorNoteService(_Db(invoice=other)).record({**GOOD, "reference_invoice_id": 7}, "5100020")
    earlier = SimpleNamespace(vendor_id=15, invoice_date=datetime.date(2026, 10, 20))
    with pytest.raises(ValueError, match="before the invoice"):
        vns.VendorNoteService(_Db(invoice=earlier)).record({**GOOD, "reference_invoice_id": 7}, "5100020")


def test_payables_unchanged_without_a_real_session():
    assert vns.applied_notes_totals(object(), [1, 2]) == {}
    assert vns.applied_notes_total(SimpleNamespace(), 1) == Decimal("0.00")
    assert vns.applied_notes_totals(None, []) == {}
