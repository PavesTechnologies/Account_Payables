"""Accounting export: vouchers balance, merge, and render to Tally XML / Zoho Books CSV / CSV."""
import csv
import datetime
import io
import xml.dom.minidom
from decimal import Decimal

import pytest

from Backend.Business_Layer.services import accounting_export_service as ax

D = Decimal
LEDGERS = {"ledgers": {k: v[0] for k, v in ax.LEDGERS.items()}, "categories": {6: "Software Subscriptions"}, "company": "Paves & Co"}


def _invoice_voucher():
    v = ax.Voucher("INVOICE", 7, "Journal", "APM/INV/7", datetime.date(2026, 9, 2), "AWSIN26-4365006",
                   "Purchase invoice AWSIN26-4365006 - AWS <India>", "AWS & Co")
    v.lines += [ax.Line("Software Subscriptions", debit=D("222390.00")), ax.Line("Input IGST", debit=D("40030.20")),
                ax.Line("Input CGST", debit=D("0.00")), ax.Line("AWS & Co", credit=D("240150.20"), bill="AWSIN26-4365006", bill_type="New Ref"),
                ax.Line("TDS Payable - 194J", credit=D("22270.00"))]
    return v.compact()


def test_voucher_balances_and_drops_zero_lines():
    v = _invoice_voucher()
    assert v.balanced() and v.amount == D("262420.20")
    assert [l.ledger for l in v.lines] == ["Software Subscriptions", "Input IGST", "AWS & Co", "TDS Payable - 194J"]


def test_compact_merges_same_ledger_and_side():
    v = ax.Voucher("PAYMENT", 1, "Payment", "APM/PAY/1", datetime.date(2026, 9, 8), "UTR1", "x", "Keka")
    v.lines += [ax.Line("Keka", debit=D("100"), bill="A"), ax.Line("Keka", debit=D("50"), bill="A"),
                ax.Line("Keka", debit=D("25"), bill="B"), ax.Line("Bank Account", credit=D("175"))]
    v.compact()
    assert [(l.bill, l.debit) for l in v.lines if l.debit] == [("A", D("150")), ("B", D("25"))]


def test_tally_xml_is_well_formed_with_signs_bills_and_masters():
    content = ax.tally_xml([_invoice_voucher()], LEDGERS, include_masters=True).decode()
    doc = xml.dom.minidom.parseString(content)
    assert doc.getElementsByTagName("SVCURRENTCOMPANY")[0].firstChild.data == "Paves & Co"
    voucher = doc.getElementsByTagName("VOUCHER")[0]
    assert voucher.getAttribute("REMOTEID") == "APM/INV/7" and voucher.getAttribute("VCHTYPE") == "Journal"
    entries = voucher.getElementsByTagName("ALLLEDGERENTRIES.LIST")
    amounts = {e.getElementsByTagName("LEDGERNAME")[0].firstChild.data: e.getElementsByTagName("AMOUNT")[0].firstChild.data for e in entries}
    assert amounts["Software Subscriptions"] == "-222390.00" and amounts["AWS & Co"] == "240150.20"
    bill = voucher.getElementsByTagName("BILLALLOCATIONS.LIST")[0]
    assert bill.getElementsByTagName("BILLTYPE")[0].firstChild.data == "New Ref"
    masters = {l.getAttribute("NAME"): l.getElementsByTagName("PARENT")[0].firstChild.data for l in doc.getElementsByTagName("LEDGER")}
    assert masters["AWS & Co"] == "Sundry Creditors" and masters["Input IGST"] == "Duties & Taxes"
    assert masters["TDS Payable - 194J"] == "Duties & Taxes" and masters["Software Subscriptions"] == "Indirect Expenses"
    assert "<India>" not in content  # escaped


def test_tally_without_masters():
    doc = xml.dom.minidom.parseString(ax.tally_xml([_invoice_voucher()], LEDGERS, include_masters=False))
    assert doc.getElementsByTagName("LEDGER") == []


def test_zoho_and_generic_csv():
    rows = list(csv.DictReader(io.StringIO(ax.zoho_csv([_invoice_voucher()]).decode("utf-8-sig"))))
    assert list(rows[0]) == ax.ZOHO_COLUMNS and len(rows) == 4
    vendor = next(r for r in rows if r["Account"] == "AWS & Co")
    assert vendor["Credit"] == "240150.20" and vendor["Contact Name"] == "AWS & Co" and vendor["Debit"] == ""
    assert sum(D(r["Debit"] or 0) for r in rows) == sum(D(r["Credit"] or 0) for r in rows)
    generic = list(csv.DictReader(io.StringIO(ax.generic_csv([_invoice_voucher()]).decode("utf-8-sig"))))
    assert generic[0]["Voucher Number"] == "APM/INV/7" and generic[0]["Source"] == "INVOICE"


def test_tds_ledger_uses_the_section():
    assert ax.AccountingExportService._tds_ledger(LEDGERS, "194I") == "TDS Payable - 194I"
    assert ax.AccountingExportService._tds_ledger(LEDGERS, None) == "TDS Payable - Other"


class _NoDb:
    def execute(self, *a, **k):
        raise AssertionError("not reached")


def test_period_validation():
    svc = ax.AccountingExportService(_NoDb())
    with pytest.raises(ValueError, match="before the start"):
        svc.vouchers(datetime.date(2026, 9, 1), datetime.date(2026, 8, 1))
    with pytest.raises(ValueError, match="at most"):
        svc.vouchers(datetime.date(2025, 1, 1), datetime.date(2026, 9, 1))
