"""GSTR-2B: portal JSON / CSV parsing, matching against the books, and the ITC claim gate."""
import datetime
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import gst_itc_service as gst
from Backend.Business_Layer.services import gstr2b_service as g2b
from Backend.Data_Access_Layer.models.invoice_gst import InvoiceGst

D = Decimal
SUPPLIER = "36AADCH8710J1ZH"  # the demo WeWork vendor GSTIN already used in the GST tests


def _portal_json():
    return json.dumps({"chksum": "x", "data": {
        "rtnprd": "092026", "gendt": "14-10-2026",
        "docdata": {
            "b2b": [{"ctin": SUPPLIER, "trdnm": "WeWork", "supfildt": "11-10-2026", "inv": [
                {"inum": "KTPL/26-27/0550", "dt": "01-09-2026", "val": 11800, "itcavl": "Y",
                 "items": [{"txval": 10000, "cgst": 900, "sgst": 900, "igst": 0, "cess": 0}]},
                {"inum": "KTPL/26-27/0551", "dt": "02-09-2026", "val": 1180, "itcavl": "N", "rsn": "P",
                 "items": [{"txval": 600, "cgst": 54, "sgst": 54}, {"txval": 400, "cgst": 36, "sgst": 36}]},
            ]}],
            "cdnr": [{"ctin": SUPPLIER, "trdnm": "WeWork", "nt": [
                {"ntnum": "CN-12", "typ": "C", "dt": "20-09-2026", "items": [{"txval": 1000, "igst": 180}]}]}],
        }}}).encode()


def test_parses_the_portal_json():
    period, buyer, generated, docs = g2b.parse_json(_portal_json())
    assert period == datetime.date(2026, 9, 1) and generated == datetime.date(2026, 10, 14) and buyer is None
    assert [d["doc_type"] for d in docs] == ["INV", "INV", "CN"]
    first, second, note = docs
    assert first["taxable_value"] == D("10000.00") and first["cgst"] == D("900.00") and first["itc_available"]
    assert second["taxable_value"] == D("1000.00") and second["cgst"] == D("90.00") and not second["itc_available"]
    assert note["igst"] == D("180.00") and first["supplier_filed_on"] == datetime.date(2026, 10, 11)


def test_rejects_a_file_that_is_not_gstr2b():
    with pytest.raises(ValueError, match="not a GSTR-2B"):
        g2b.parse_json(b"\x89PNG")
    with pytest.raises(ValueError, match="No b2b"):
        g2b.parse_json(b'{"data": {"rtnprd": "092026"}}')


def test_parses_the_csv_template():
    csv = (",".join(g2b.CSV_COLUMNS) + "\n"
           f"{SUPPLIER},WeWork,INV,KTPL/0550,01/09/2026,\"10,000\",0,900,900,0,Y,\n,,,,,,,,,,,\n").encode()
    docs = g2b.parse_csv(csv)
    assert len(docs) == 1 and docs[0]["taxable_value"] == D("10000.00") and docs[0]["doc_date"] == datetime.date(2026, 9, 1)
    with pytest.raises(ValueError, match="columns"):
        g2b.parse_csv(b"foo,bar\n1,2\n")


def test_document_numbers_compare_loosely():
    assert g2b.norm_doc("KTPL/26-27/0550") == g2b.norm_doc("ktpl 26-27 550")
    assert g2b.norm_doc("INV-0012") != g2b.norm_doc("INV-0120")


def _doc(number="KTPL/26-27/0550", cgst="900", sgst="900", taxable="10000"):
    return {"supplier_gstin": SUPPLIER, "doc_type": "INV", "doc_number": number, "taxable_value": D(taxable),
            "igst": D("0"), "cgst": D(cgst), "sgst": D(sgst), "cess": D("0")}


BOOKS = {(SUPPLIER, g2b.norm_doc("KTPL-26-27-550")): [(41, D("10000.00"), D("1800.00"), "PAID", "KTPL-26-27-550")]}


def test_match_outcomes():
    svc = g2b.Gstr2bService(None)
    status, invoice_id, diff, _ = svc._match(_doc(sgst="900.60"), BOOKS, D("1"))
    assert (status, invoice_id, diff) == ("MATCHED", 41, D("0.60"))
    status, invoice_id, diff, note = svc._match(_doc(cgst="1800", sgst="1800"), BOOKS, D("1"))
    assert status == "MISMATCH" and diff == D("1800") and "books" in note
    assert svc._match(_doc(number="KTPL/26-27/0999"), BOOKS, D("1"))[0] == "NOT_IN_BOOKS"
    rejected = {k: [(41, D("10000.00"), D("1800.00"), "REJECTED", "X")] for k in BOOKS}
    assert svc._match(_doc(), rejected, D("1"))[0] == "MISMATCH"


def _gst_view(svc, invoice_id, invoice_date):
    invoice = SimpleNamespace(invoice_id=invoice_id, invoice_number="X", invoice_date=invoice_date)
    row = InvoiceGst(invoice_id=invoice_id, cgst=D("9"), sgst=D("9"), igst=D("0"), cess=D("0"), itc_eligibility="ELIGIBLE",
                     itc_status="PENDING", irn_status="PRESENT")
    return svc._view(row, invoice, "APPROVED", "Vendor")


def test_itc_claim_is_gated_once_gstr2b_is_imported():
    today = datetime.date(2026, 10, 14)
    sep, oct_ = datetime.date(2026, 9, 5), datetime.date(2026, 10, 2)
    lookup = lambda: ({1: "MATCHED", 2: "MISMATCH"}, datetime.date(2026, 9, 1), datetime.date(2026, 9, 1))
    svc = gst.GstItcService(SimpleNamespace(), today=today, einvoice_lookup=lambda g: None, gstr2b_lookup=lookup)
    assert _gst_view(svc, 1, sep)["claimable"] and _gst_view(svc, 1, sep)["gstr2b"] == "MATCHED"
    assert not _gst_view(svc, 2, sep)["claimable"]
    missing = _gst_view(svc, 3, sep)
    assert missing["gstr2b"] == "MISSING" and not missing["claimable"]
    later = _gst_view(svc, 4, oct_)  # October's 2B isn't out yet - not checked, still claimable
    assert later["gstr2b"] is None and later["claimable"]
    earlier = _gst_view(svc, 5, datetime.date(2026, 8, 20))  # before the first imported 2B - history, not checked
    assert earlier["gstr2b"] is None and earlier["claimable"]


def test_no_gstr2b_means_not_checked():
    svc = gst.GstItcService(SimpleNamespace(), today=datetime.date(2026, 10, 14), einvoice_lookup=lambda g: None)
    view = _gst_view(svc, 3, datetime.date(2026, 9, 5))
    assert view["gstr2b"] is None and view["claimable"]
