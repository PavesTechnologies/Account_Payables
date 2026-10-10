"""Shared TDS challan + quarterly filing (Phase 5): extraction parsing, validation rules, the
all-or-nothing confirm through the existing per-invoice deposit / filing, and route permissions.
No DB / S3 / Textract."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import tds_challan_route as route
from Backend.API_Layer.utils import tds_document_extraction as tx
from Backend.Business_Layer.services import tds_challan_service as svc

TODAY = datetime.date(2026, 10, 10)


def _q(value, confidence=95.0):
    return {"value": value, "confidence": confidence}


# ======================================================================
# Pure helpers / extraction
# ======================================================================
def test_section_and_quarter_helpers():
    assert svc.normalize_section("194C") == svc.normalize_section("94C") == svc.normalize_section(" 194 c") == "94C"
    assert svc.quarter_bounds("2026-27", 1) == (datetime.date(2026, 4, 1), datetime.date(2026, 6, 30))
    assert svc.quarter_bounds("2026-27", 4) == (datetime.date(2027, 1, 1), datetime.date(2027, 3, 31))
    with pytest.raises(ValueError):
        svc.quarter_bounds("2026", 1)


def test_parse_challan_with_cin_cross_check():
    out = tx.parse_challan_fields({
        "SERIAL": _q("00123"), "BSR": _q("0510308"), "DEPOSIT_DATE": _q("07/10/2026"), "TAN": _q("blra12345b"),
        "AY": _q("2027-28"), "MINOR_HEAD": _q("(200) TDS payable by taxpayer"), "SECTION": _q("194C"),
        "TAX": _q("Rs. 12,500"), "INTEREST": _q("0"), "TOTAL": _q("₹ 12,500.00"),
        "CIN": _q("0510308 07102026 00123"),
    }, "")
    f = out["fields"]
    assert (f["challan_serial_no"]["value"], f["bsr_code"]["value"], f["deposit_date"]["value"]) == ("00123", "0510308", "2026-10-07")
    assert f["tan"]["value"] == "BLRA12345B" and f["minor_head"]["value"] == "200" and f["section_code"]["value"] == "194C"
    assert f["tax_amount"]["value"] == "12500.00" and f["total_amount"]["value"] == "12500.00"
    assert out["cin"] == "05103080710202600123" and out["cin_mismatch"] is False


def test_parse_challan_falls_back_to_cin_and_detects_mismatch():
    out = tx.parse_challan_fields({"CIN": _q("0510308 07102026 00123")}, "")
    assert out["fields"]["bsr_code"]["value"] == "0510308" and out["fields"]["deposit_date"]["value"] == "2026-10-07"
    mismatch = tx.parse_challan_fields({"SERIAL": _q("00999"), "BSR": _q("0510308"), "DEPOSIT_DATE": _q("07/10/2026"),
                                        "CIN": _q("05103080710202600123")}, "")
    assert mismatch["cin_mismatch"] is True


def test_parse_filing_acknowledgement():
    out = tx.parse_filing_fields({"ACK": _q("Token No. 123456789012345"), "FILING_DATE": _q("28-Jul-2026"),
                                  "FORM": _q("Form 26Q"), "FY": _q("2026-27"), "QUARTER": _q("Q1"), "KIND": _q("Regular")}, "")
    f = out["fields"]
    assert f["acknowledgement_no"]["value"] == "123456789012345" and f["filing_date"]["value"] == "2026-07-28"
    assert (f["form_type"]["value"], f["financial_year"]["value"], f["quarter"]["value"]) == ("26Q", "2026-27", 1)
    assert out["is_revision"] is False


# ======================================================================
# Service with in-memory DAO
# ======================================================================
def _row(i, tds="5000", status="TDS_DEDUCTED", deducted=datetime.date(2026, 9, 15), section="194C", verified=True,
         deposited=None, residency="RESIDENT"):
    invoice = SimpleNamespace(invoice_id=i, invoice_number=f"INV-{i}", vendor_id=1)
    tds_row = SimpleNamespace(tds_amount=Decimal(tds), determination_status="VERIFIED" if verified else "DETERMINED",
                              rule_snapshot={"old_section": section}, residency_type=residency)
    tracking = SimpleNamespace(id=100 + i, tracking_status=status, deduction_date=deducted, deposit_date=deposited, challan_number=None)
    return (invoice, "Acme", None, tds_row, SimpleNamespace(name="Contract"), None, tracking)


class _DAO:
    def __init__(self, rows, allocated=None, existing_challan=None, existing_ack=None):
        self.rows, self.allocated, self.existing_challan, self.existing_ack = rows, allocated or {}, existing_challan, existing_ack
        self.added = []
        self.tracking = SimpleNamespace(get_tracking_locked=lambda i: SimpleNamespace(id=100 + i))

    def add(self, obj):
        if hasattr(obj, "challan_serial_no") and getattr(obj, "challan_id", None) is None:
            obj.challan_id = 1
        if hasattr(obj, "acknowledgement_no") and getattr(obj, "filing_id", None) is None:
            obj.filing_id = 1
        self.added.append(obj)
        return obj

    def tds_row(self, i):
        return self.rows.get(i)

    def actively_allocated(self, ids):
        return {i: c for i, c in self.allocated.items() if i in ids}

    def invoices_in_tracking_status(self, statuses, start, end):
        return [r for r in self.rows.values() if r[6].tracking_status in statuses
                and (start is None or start <= r[6].deduction_date <= end)]

    def challan_by_identity(self, *a):
        return self.existing_challan

    def filing_by_ack(self, ack):
        return self.existing_ack


class _Db:
    def __init__(self):
        self.commits = self.rollbacks = 0
        self.audit = []

    def add(self, obj):
        self.audit.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def world(monkeypatch):
    calls = SimpleNamespace(deposits=[], filings=[], stored=[], discarded=[], fail_on=None)

    class Tracking:
        def __init__(self, db):
            pass

        def record_deposit(self, invoice_id, data, user_id, commit=True):
            assert commit is False
            if calls.fail_on == invoice_id:
                raise ValueError("TDS Payment Date cannot be before the deduction date")
            calls.deposits.append((invoice_id, data.challan_number, data.bsr_code, data.deposit_date))

        def record_filing(self, invoice_id, data, user_id, commit=True):
            assert commit is False
            calls.filings.append((invoice_id, data.filing_reference))

    monkeypatch.setattr(svc, "TdsTrackingService", Tracking)
    monkeypatch.setattr(svc.TdsChallanService, "_tolerance", lambda self: Decimal("1"))
    monkeypatch.setattr(svc.TdsChallanService, "_due_days", lambda self: (7, 30))
    monkeypatch.setattr(svc.TdsChallanService, "_store", staticmethod(lambda doc, prefix: calls.stored.append(prefix) or ("c.pdf", "tds/challans/c.pdf", "application/pdf", 3) if doc else None))
    monkeypatch.setattr(svc.TdsChallanService, "_discard", staticmethod(lambda stored: calls.discarded.append(stored)))
    monkeypatch.setattr(svc.TdsChallanService, "challan_detail", lambda self, i: {"challan_id": i})
    monkeypatch.setattr(svc.TdsChallanService, "filing_detail", lambda self, i: {"filing_id": i})
    return calls


def _service(dao):
    s = svc.TdsChallanService(_Db(), today=TODAY)
    s.dao = dao
    return s


HEADER = {"challan_serial_no": "123", "bsr_code": "0510308", "deposit_date": "2026-10-07", "tax_amount": "12000",
          "total_amount": "12000", "section_code": "194C"}


def test_valid_challan_and_cin(world):
    dao = _DAO({1: _row(1, "5000"), 2: _row(2, "7000")})
    result = _service(dao).validate_challan(HEADER, [{"invoice_id": 1}, {"invoice_id": 2}], True)
    assert result["valid"], result["errors"]
    assert result["cin"] == "05103080710202600123" and result["allocated_total"] == Decimal("12000.00")
    assert result["warnings"] == []


@pytest.mark.parametrize("change,code", [
    ({"tax_amount": "13000", "total_amount": "13000"}, "SUM"),
    ({"total_amount": "12500"}, "TOTAL"),
    ({"bsr_code": "12345"}, "BSR"),
    ({"deposit_date": "2026-12-01"}, "DATE"),
    ({"section_code": "194J"}, "SECTION"),
    ({"tan": "BAD"}, "TAN"),
])
def test_challan_errors(world, change, code):
    dao = _DAO({1: _row(1, "5000"), 2: _row(2, "7000")})
    result = _service(dao).validate_challan({**HEADER, **change}, [{"invoice_id": 1}, {"invoice_id": 2}], True)
    assert not result["valid"] and code in {e["code"] for e in result["errors"]}


def test_invoice_level_errors_and_evidence(world):
    dao = _DAO({1: _row(1, verified=False), 2: _row(2, status="TDS_DEPOSITED"), 3: _row(3, deducted=datetime.date(2026, 10, 9))},
               allocated={4: 7})
    dao.rows[4] = _row(4)
    result = _service(dao).validate_challan({**HEADER, "remarks": "x"}, [{"invoice_id": i} for i in (1, 2, 3, 4)], False)
    codes = {e["code"] for e in result["errors"]}
    assert {"NOT_VERIFIED", "NOT_DEDUCTED", "BEFORE_DEDUCTION", "ALREADY_ON_CHALLAN", "EVIDENCE"} <= codes
    dup = _service(_DAO({1: _row(1, "12000")}, existing_challan=object())).validate_challan(HEADER, [{"invoice_id": 1}], True)
    assert "DUPLICATE" in {e["code"] for e in dup["errors"]}


def test_late_deposit_warns_about_interest(world):
    dao = _DAO({1: _row(1, "12000", deducted=datetime.date(2026, 8, 20))})  # due 7 Sep, deposited 7 Oct
    result = _service(dao).validate_challan(HEADER, [{"invoice_id": 1}], True)
    assert result["valid"] and "201(1A)" in next(w["message"] for w in result["warnings"] if w["code"] == "LATE")


def test_confirm_records_every_deposit_in_one_transaction(world):
    dao = _DAO({1: _row(1, "5000"), 2: _row(2, "7000")})
    service = _service(dao)
    service.create_challan(HEADER, [{"invoice_id": 1}, {"invoice_id": 2}], "u-1", ("c.pdf", b"%PDF", "application/pdf"))
    assert world.deposits == [(1, "00123", "0510308", datetime.date(2026, 10, 7)), (2, "00123", "0510308", datetime.date(2026, 10, 7))]
    assert service.db.commits == 1 and world.stored == ["tds/challans/"]
    kinds = [type(o).__name__ for o in dao.added]
    assert kinds.count("TdsChallanAllocation") == 2 and kinds.count("InvoiceTdsDocument") == 2


def test_confirm_is_all_or_nothing(world):
    world.fail_on = 2
    dao = _DAO({1: _row(1, "5000"), 2: _row(2, "7000")})
    service = _service(dao)
    with pytest.raises(ValueError):
        service.create_challan(HEADER, [{"invoice_id": 1}, {"invoice_id": 2}], "u-1", ("c.pdf", b"%PDF", "application/pdf"))
    assert service.db.commits == 0 and service.db.rollbacks == 1 and world.discarded  # uploaded file removed


def test_invalid_challan_is_never_written(world):
    dao = _DAO({1: _row(1, "5000")})
    with pytest.raises(ValueError, match="does not match the challan tax"):
        _service(dao).create_challan(HEADER, [{"invoice_id": 1}], "u-1", ("c.pdf", b"%PDF", None))
    assert dao.added == [] and world.stored == []


def test_candidates_exclude_allocated_and_filter_period_and_section(world):
    dao = _DAO({1: _row(1), 2: _row(2, section="194J"), 3: _row(3, deducted=datetime.date(2026, 8, 1)), 4: _row(4)}, allocated={4: 9})
    out = _service(dao).challan_candidates("2026-09", "94C")
    assert [i["invoice_id"] for i in out["items"]] == [1] and out["items"][0]["deposit_due_date"] == datetime.date(2026, 10, 7)
    assert out["items"][0]["overdue"] is True


# ---------------- filing
FILING = {"form_type": "26Q", "financial_year": "2026-27", "quarter": 2, "acknowledgement_no": "123456789012345",
          "filing_date": "2026-10-09"}


def _deposited(i, deducted=datetime.date(2026, 8, 10), status="TDS_DEPOSITED"):
    return _row(i, status=status, deducted=deducted, deposited=datetime.date(2026, 9, 5))


def test_filing_valid_and_confirm(world):
    dao = _DAO({1: _deposited(1), 2: _deposited(2)})
    service = _service(dao)
    assert service.validate_filing(FILING, [1, 2], True)["valid"]
    service.create_filing(FILING, [1, 2], "u-1", ("ack.pdf", b"%PDF", None))
    assert world.filings == [(1, "123456789012345"), (2, "123456789012345")] and service.db.commits == 1


def test_filing_rules(world):
    dao = _DAO({1: _deposited(1, deducted=datetime.date(2026, 6, 30)), 2: _deposited(2, status="TDS_FILED"), 3: _row(3)},
               existing_ack=object())
    result = _service(dao).validate_filing({**FILING, "filing_date": "2026-11-05"}, [1, 2, 3], False)
    codes = {e["code"] for e in result["errors"]}
    assert {"QUARTER", "NOT_DEPOSITED", "DUPLICATE", "EVIDENCE"} <= codes
    assert "LATE" in {w["code"] for w in result["warnings"]}  # Q2 statement due 31 Oct
    revision = _service(_DAO({2: _deposited(2, status="TDS_FILED")})).validate_filing({**FILING, "is_revision": True}, [2], True)
    assert revision["valid"]


def test_filing_candidates_and_form_suggestion(world):
    dao = _DAO({1: _deposited(1), 2: _deposited(2, deducted=datetime.date(2026, 5, 1))})
    out = _service(dao).filing_candidates("2026-27", 2)
    assert [i["invoice_id"] for i in out["items"]] == [1] and out["statement_due_date"] == datetime.date(2026, 10, 31)
    assert out["suggested_form"] == "26Q"


# ======================================================================
# Routes
# ======================================================================
def _client(permissions, monkeypatch):
    class Fake:
        def __init__(self, db):
            self.dao = SimpleNamespace(get_challan=lambda i: None, get_filing=lambda i: None)

        def list_challans(self, page, size):
            return {"items": [], "total": 0, "page": page, "page_size": size}

        def validate_challan(self, header, allocations, has_document):
            return {"valid": True, "allocations": allocations}

        def create_challan(self, header, allocations, user_id, document):
            if not allocations:
                raise ValueError("Select the invoices this challan pays")
            return {"challan_id": 1, "has_document": document is not None}

        def list_filings(self, page, size):
            return {"items": [], "total": 0, "page": page, "page_size": size}
    monkeypatch.setattr(route, "TdsChallanService", Fake)

    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u-1", "permissions": permissions}
            request.state.db = SimpleNamespace(rollback=lambda: None)
            return await call_next(request)
    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(route.challan_router, prefix="/tds/challans")
    app.include_router(route.filing_router, prefix="/tds/filings")
    return TestClient(app)


def test_route_permissions_and_multipart_confirm(monkeypatch):
    viewer = _client(["TDS_TRACKING_VIEW"], monkeypatch)
    assert viewer.get("/tds/challans").status_code == 200 and viewer.get("/tds/filings").status_code == 200
    assert viewer.post("/tds/challans/validate", json={"header": {}}).status_code == 403
    assert viewer.post("/tds/challans", data={"payload": "{}"}).status_code == 403
    updater = _client(["TDS_TRACKING_UPDATE"], monkeypatch)
    monkeypatch.setattr(route, "validate_upload_file", lambda f, c: None)
    res = updater.post("/tds/challans", data={"payload": '{"header": {}, "allocations": [{"invoice_id": 1}]}'},
                       files={"file": ("c.pdf", b"%PDF", "application/pdf")})
    assert res.status_code == 201 and res.json()["has_document"] is True
    assert updater.post("/tds/challans", data={"payload": '{"header": {}, "allocations": []}'}).status_code == 422
    assert updater.post("/tds/challans", data={"payload": "not json"}).status_code == 400
    assert updater.get("/tds/challans/5/document").status_code == 404


def test_challan_dao_queries_compile(monkeypatch):
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.orm import Query, Session

    from Backend.Data_Access_Layer import models  # noqa: F401
    from Backend.Data_Access_Layer.dao.tds_challan_dao import TdsChallanDAO

    compiled = []

    def capture(self):
        compiled.append(str(self.statement.compile(dialect=postgresql.dialect())))
        return []
    monkeypatch.setattr(Query, "all", capture)
    monkeypatch.setattr(Query, "first", lambda self: capture(self) or None)
    monkeypatch.setattr(Query, "count", lambda self: 0)
    dao = TdsChallanDAO(Session())
    dao.invoices_in_tracking_status(["TDS_DEDUCTED"], datetime.date(2026, 9, 1), datetime.date(2026, 9, 30))
    dao.actively_allocated([1]); dao.challan_by_identity("0510308", datetime.date(2026, 10, 7), "00123")
    dao.filing_by_ack("123"); dao.list_challans(0, 10); dao.challan_counts([1]); dao.get_challan(1)
    dao.list_filings(0, 10); dao.filing_counts([1]); dao.get_filing(1); dao.invoice_numbers([1])
    assert len(compiled) == 11 and "tds_challan_allocation" in " ".join(compiled)
