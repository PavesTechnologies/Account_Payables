"""Receipts-only payment import: which invoice(s) each receipt pays."""
from decimal import Decimal
from types import SimpleNamespace

from Backend.Business_Layer.services import bulk_import_service as bis
from Backend.Data_Access_Layer.models.bulk_import import ROW_ERROR, ROW_PENDING

D = Decimal
INVOICES = [
    {"invoice_id": 1, "invoice_number": "WWIM/HYD/26-27/03187", "vendor_name": "WEWORK INDIA MANAGEMENT LIMITED", "remaining": D("77760.00")},
    {"invoice_id": 2, "invoice_number": "KTPL/26-27/0661", "vendor_name": "KEKA TECHNOLOGIES PRIVATE LIMITED", "remaining": D("69600.00")},
    {"invoice_id": 3, "invoice_number": "KTPL/26-27/0550", "vendor_name": "KEKA TECHNOLOGIES PRIVATE LIMITED", "remaining": D("64496.00")},
    {"invoice_id": 4, "invoice_number": "AWSIN26-1010005", "vendor_name": "AMAZON WEB SERVICES INDIA PRIVATE LIMITED", "remaining": D("105840.00")},
    {"invoice_id": 5, "invoice_number": "AWSIN26-1010004", "vendor_name": "AMAZON WEB SERVICES INDIA PRIVATE LIMITED", "remaining": D("1002600.00")},
]


class _Db:
    def __init__(self):
        self.added = []

    def add(self, obj):
        obj.row_id = 100 + len(self.added)
        self.added.append(obj)

    def flush(self):
        pass


def _run(receipts):
    """receipts: list of (text, amount, beneficiary) -> (rows evaluated next, all rows incl. new ones)"""
    svc = bis.BulkImportService(_Db())
    svc._payable_invoices = lambda: [dict(i) for i in INVOICES]
    rows, extracted = [], {}
    for n, (text, amount, beneficiary) in enumerate(receipts, start=1):
        path = f"doc{n}.pdf"
        rows.append(SimpleNamespace(row_id=n, row_number=n, data={"receipts_only": True, "receipt_file": path},
                                    document_path=path, document_name=path, extracted=None, invoice_id=None,
                                    status=ROW_PENDING, messages=None))
        extracted[path] = {"fields": {"amount": {"value": amount}}, "beneficiary_name": beneficiary, "text": text}
    job = SimpleNamespace(job_id=9, rows=rows)
    evaluated = svc._match_receipts(job, list(rows), extracted)
    return evaluated, rows + svc.db.added


def test_invoice_number_on_the_receipt_wins():
    evaluated, _ = _run([("NEFT to WeWork. Remarks: WWIM/HYD/26-27/03187 Oct rent", "77760.00", "WEWORK INDIA")])
    assert [r.invoice_id for r in evaluated] == [1]
    assert "invoice number on the receipt" in evaluated[0].messages[-1]["message"]
    assert "amount" not in evaluated[0].data  # the receipt's own amount is used (partial payments allowed)


def test_number_ignores_spacing_and_drops_shorter_overlaps():
    evaluated, _ = _run([("Ref KTPL 26-27 0661 and KTPL/26-27/0550", "134096.00", "Keka Technologies")])
    assert sorted(r.invoice_id for r in evaluated) == [2, 3]  # one transfer, two invoices: a row each
    assert {r.data["amount"] for r in evaluated} == {"69600.00", "64496.00"}


def test_beneficiary_and_amount_when_no_number():
    evaluated, _ = _run([("NEFT credit", "69600.00", "KEKA TECHNOLOGIES PVT LTD")])
    assert [r.invoice_id for r in evaluated] == [2]
    assert "beneficiary and the amount" in evaluated[0].messages[-1]["message"]


def test_one_transfer_for_all_of_a_vendors_open_invoices():
    evaluated, _ = _run([("bulk transfer", "134096.00", "Keka Technologies Private Limited")])
    assert sorted(r.invoice_id for r in evaluated) == [2, 3]


def test_amount_only_is_flagged_for_review():
    evaluated, _ = _run([("transfer", "105840.00", None)])
    assert [r.invoice_id for r in evaluated] == [4]
    assert any(m["severity"] == "review" and "amount only" in m["message"] for m in evaluated[0].messages)


def test_no_match_is_an_error_and_not_evaluated():
    evaluated, rows = _run([("transfer", "12345.00", "Someone Else Ltd")])
    assert evaluated == [] and rows[0].status == ROW_ERROR
    assert "Could not find the invoice" in rows[0].messages[-1]["message"]


def test_two_receipts_do_not_claim_the_same_invoice_by_amount():
    evaluated, rows = _run([("transfer 1", "69600.00", "Keka"), ("transfer 2", "69600.00", "Keka")])
    assert [r.invoice_id for r in evaluated] == [2]
    assert rows[1].status == ROW_ERROR
