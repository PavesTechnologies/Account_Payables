"""Review workbench (Step A): coding suggestions, readiness checks, bulk review & send through the
existing operations, auto TDS, and the route's permissions. In-memory fakes only."""
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import invoice_review_workbench_route as route
from Backend.Business_Layer.services import invoice_review_automation_service as svc

VALID = {"is_valid": True, "issues": []}


def _inv(i, vendor=1, kind="NON_PO", dept=None, cat=None, po_id=None, amount="1000", status="OCR_REVIEW_PENDING"):
    return SimpleNamespace(invoice_id=i, invoice_number=f"INV-{i}", vendor_id=vendor, invoice_type=kind,
                           invoice_date=datetime.date(2026, 10, 1), net_amount=Decimal(amount), department_id=dept,
                           purchase_category_id=cat, po_id=po_id, inbound_document_id=500 + i,
                           created_at=datetime.datetime(2026, 10, 1, 9, i), _status=status)


class _DAO:
    invoices, uploads, issues, tds, mappings, last, po = [], {}, {}, {}, {}, {}, {}

    def __init__(self, db):
        pass

    def invoices_in_status(self, codes, limit, invoice_ids=None):
        rows = [(i, f"Vendor {i.vendor_id}", i._status, "INR") for i in _DAO.invoices if i._status in codes]
        if invoice_ids is not None:
            rows = [r for r in rows if r[0].invoice_id in invoice_ids]
        return rows[:limit]

    def inbound_document_ids(self, ids):
        return {}

    def upload_items(self, ids):
        return {k: v for k, v in _DAO.uploads.items() if k in ids}

    def open_issue_counts(self, ids):
        return _DAO.issues

    def tds_rows(self, ids):
        return _DAO.tds

    def vendor_mappings(self, ids):
        return _DAO.mappings

    def last_coded_non_po(self, ids, exclude):
        return _DAO.last

    def po_coding(self, ids):
        return _DAO.po

    def departments(self):
        return {10: ("IT", True), 20: ("Finance", True), 30: ("Old", False)}

    def categories(self):
        return {101: ("Software", True, 10), 102: ("Hardware", True, 10), 201: ("Audit", True, 20), 301: ("Legacy", True, 30)}


class _Policy:
    def __init__(self, db):
        pass

    def match_policy(self, dept, cat, amount):
        if dept == 20:
            raise ValueError("No applicable approval policy found for this invoice.")
        return SimpleNamespace(name="IT standard")


class _Db:
    def rollback(self):
        pass


@pytest.fixture
def world(monkeypatch):
    _DAO.invoices, _DAO.uploads, _DAO.issues, _DAO.tds, _DAO.mappings, _DAO.last, _DAO.po = [], {}, {}, {}, {}, {}, {}
    calls = SimpleNamespace(reviews=[], tds=[], sent=[], tds_problem=None, send_error=None)

    def fake_review(inbound_id, review, db, user_id):
        calls.reviews.append((inbound_id, review.invoice_type, review.department_id, review.purchase_category_id, user_id))
        inv = next(i for i in _DAO.invoices if i.inbound_document_id == inbound_id)
        inv._status = "OCR_REVIEWED"
        inv.department_id, inv.purchase_category_id = review.department_id, review.purchase_category_id

    def fake_tds(db, invoice_id, user_id):
        calls.tds.append(invoice_id)
        return calls.tds_problem

    class FakeApproval:
        def __init__(self, db):
            pass

        def send_for_approval(self, invoice_id, user_id):
            if calls.send_error:
                raise ValueError(calls.send_error)
            calls.sent.append(invoice_id)

    monkeypatch.setattr(svc, "ReviewWorkbenchDAO", _DAO)
    monkeypatch.setattr(svc, "ApprovalPolicyService", _Policy)
    monkeypatch.setattr(svc.invoice_process_service, "apply_ocr_review", fake_review)
    monkeypatch.setattr(svc, "auto_determine_tds", fake_tds)
    monkeypatch.setattr(svc, "InvoiceApprovalService", FakeApproval)
    return calls


def _rows(stage="to_review"):
    return {r["invoice_id"]: r for r in svc.InvoiceReviewAutomationService(_Db()).workbench(stage)["items"]}


def _check(row, key):
    return next(c for c in row["checks"] if c["key"] == key)


# ======================================================================
# Suggestions
# ======================================================================
def test_coding_suggestion_order(world):
    _DAO.invoices = [_inv(1, vendor=1), _inv(2, vendor=2), _inv(3, vendor=3), _inv(4, vendor=4), _inv(5, vendor=5, dept=20, cat=201)]
    _DAO.mappings = {1: [(10, 102, False), (10, 101, True)],   # primary mapping wins
                     2: [(10, 102, False), (20, 201, False)],  # several, none primary -> no mapping suggestion
                     4: [(30, 301, True)]}                      # inactive department -> ignored
    _DAO.last = {2: (20, 201), 3: (10, 102), 4: (10, 101)}
    rows = _rows()
    assert (rows[1]["department_id"], rows[1]["purchase_category_id"], rows[1]["coding_source"]) == (10, 101, "VENDOR_MAPPING")
    assert (rows[2]["purchase_category_id"], rows[2]["coding_source"]) == (201, "LAST_INVOICE")
    assert (rows[3]["purchase_category_name"], rows[3]["coding_source"]) == ("Hardware", "LAST_INVOICE")
    assert (rows[4]["purchase_category_id"], rows[4]["coding_source"]) == (101, "LAST_INVOICE")
    assert rows[5]["coding_source"] == "INVOICE"


def test_po_invoice_takes_coding_from_requisition(world):
    _DAO.invoices = [_inv(1, kind="PO", po_id=9), _inv(2, kind="PO")]
    _DAO.po = {9: (10, 101, "PO-9")}
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None), 2: (VALID, 3, "MANUAL_UPLOAD", None)}
    rows = _rows()
    assert rows[1]["coding_source"] == "PO" and rows[1]["ready"] is True
    assert "not linked" in _check(rows[2], "coding")["message"] and rows[2]["ready"] is False


# ======================================================================
# Readiness
# ======================================================================
def test_only_clean_invoices_are_ready(world):
    _DAO.invoices = [_inv(i, vendor=1) for i in range(1, 6)]
    _DAO.mappings = {1: [(10, 101, True)]}
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None),
                    2: ({"is_valid": False, "issues": ["Buyer GSTIN mismatch"]}, 3, "MANUAL_UPLOAD", None),
                    4: (VALID, 4, "EMAIL", False), 5: (VALID, 3, "MANUAL_UPLOAD", None)}
    _DAO.issues = {5: 2}
    rows = _rows()
    assert rows[1]["ready"] is True
    assert rows[2]["ready"] is False and "Buyer GSTIN mismatch" in _check(rows[2], "validation")["message"]
    assert rows[3]["ready"] is False and "on its own" in _check(rows[3], "validation")["message"]  # single upload
    assert rows[4]["ready"] is True and _check(rows[4], "sender")["ok"] is False  # warning only
    assert rows[5]["ready"] is False and "2 open issue" in _check(rows[5], "issues")["message"]


def test_missing_policy_blocks(world):
    _DAO.invoices = [_inv(1, dept=20, cat=201)]
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None)}
    row = _rows()[1]
    assert row["ready"] is False and "No applicable approval policy" in _check(row, "policy")["message"]


# ======================================================================
# Bulk review & send
# ======================================================================
def test_bulk_review_and_send_uses_the_existing_operations(world):
    _DAO.invoices = [_inv(1), _inv(2), _inv(3)]
    _DAO.mappings = {1: [(10, 101, True)]}
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None), 2: (VALID, 3, "MANUAL_UPLOAD", None)}
    results = svc.InvoiceReviewAutomationService(_Db()).bulk_review(
        [{"invoice_id": 1}, {"invoice_id": 2, "department_id": 10, "purchase_category_id": 102}, {"invoice_id": 3}], "u-1", True)
    by_id = {r["invoice_id"]: r for r in results}
    assert by_id[1]["status"] == "SENT" and by_id[2]["status"] == "SENT"
    assert by_id[3]["status"] == "SKIPPED" and "on its own" in by_id[3]["message"]
    assert world.reviews == [(501, "NON_PO", 10, 101, "u-1"), (502, "NON_PO", 10, 102, "u-1")]
    assert world.tds == [1, 2] and world.sent == [1, 2]


def test_tds_problem_stops_before_send(world):
    _DAO.invoices = [_inv(1, dept=10, cat=101)]
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None)}
    world.tds_problem = "TDS needs review: no payment nature"
    result = svc.InvoiceReviewAutomationService(_Db()).bulk_review([{"invoice_id": 1}], "u-1", True)[0]
    assert result["status"] == "REVIEWED" and "payment nature" in result["message"] and world.sent == []


def test_review_only_when_user_cannot_send(world):
    _DAO.invoices = [_inv(1, dept=10, cat=101)]
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None)}
    result = svc.InvoiceReviewAutomationService(_Db()).bulk_review([{"invoice_id": 1}], "u-1", False)[0]
    assert result["status"] == "REVIEWED" and world.sent == [] and world.tds == [1]


def test_client_cannot_bypass_server_checks(world):
    _DAO.invoices = [_inv(1, dept=10, cat=101)]
    _DAO.uploads = {1: ({"is_valid": False, "issues": ["Tax total mismatch"]}, 3, "MANUAL_UPLOAD", None)}
    result = svc.InvoiceReviewAutomationService(_Db()).bulk_review([{"invoice_id": 1}], "u-1", True)[0]
    assert result["status"] == "SKIPPED" and world.reviews == []
    # chosen coding with no policy is also re-checked
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None)}
    result = svc.InvoiceReviewAutomationService(_Db()).bulk_review(
        [{"invoice_id": 1, "department_id": 20, "purchase_category_id": 201}], "u-1", True)[0]
    assert result["status"] == "SKIPPED" and "approval policy" in result["message"]


def test_send_failure_keeps_invoice_reviewed(world):
    _DAO.invoices = [_inv(1, dept=10, cat=101)]
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None)}
    world.send_error = "No approver resolved for level 1"
    result = svc.InvoiceReviewAutomationService(_Db()).bulk_review([{"invoice_id": 1}], "u-1", True)[0]
    assert result["status"] == "REVIEWED" and "No approver" in result["message"]


def test_bulk_send_reviewed_invoices(world):
    _DAO.invoices = [_inv(1, dept=10, cat=101, status="OCR_REVIEWED"), _inv(2, status="OCR_REVIEW_PENDING")]
    results = svc.InvoiceReviewAutomationService(_Db()).bulk_send([1, 2], "u-2")
    assert results[0]["status"] == "SENT" and results[1]["status"] == "FAILED" and world.sent == [1]


def test_limits():
    service = svc.InvoiceReviewAutomationService(_Db())
    with pytest.raises(ValueError, match="At most 25"):
        service.bulk_review([{"invoice_id": i} for i in range(26)], "u", True)
    with pytest.raises(ValueError, match="at least one"):
        service.bulk_send([], "u")


# ======================================================================
# Auto TDS never overwrites a finished determination
# ======================================================================
def test_auto_tds_skips_when_already_determined(monkeypatch):
    done = SimpleNamespace(determination_status="DETERMINED", payment_nature_id=1, tds_rule_id=None, tds_rate_rule_id=None)

    class FakeTds:
        def __init__(self, db):
            self.tds_dao = SimpleNamespace(get_invoice_tds_by_invoice_id=lambda i: done)

        def determine(self, *a, **k):
            raise AssertionError("must not re-determine")
    monkeypatch.setattr(svc, "TDSDeterminationService", FakeTds)
    assert svc.auto_determine_tds(None, 1, "u") is None


def test_auto_tds_reports_problem(monkeypatch):
    class FakeTds:
        def __init__(self, db):
            self.tds_dao = SimpleNamespace(get_invoice_tds_by_invoice_id=lambda i: None)

        def determine(self, invoice_id, user_id):
            return SimpleNamespace(determination_status="DETERMINED", payment_nature_id=None, tds_rule_id=None, tds_rate_rule_id=None)
    monkeypatch.setattr(svc, "TDSDeterminationService", FakeTds)
    assert "no payment nature" in svc.auto_determine_tds(None, 1, "u")


# ======================================================================
# Route
# ======================================================================
def _client(permissions):
    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u-1", "permissions": permissions}
            request.state.db = _Db()
            return await call_next(request)
    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(route.router, prefix="/invoice-review")
    return TestClient(app)


def test_route_permissions_and_send_needs_its_own_permission(world):
    _DAO.invoices = [_inv(1, dept=10, cat=101)]
    _DAO.uploads = {1: (VALID, 3, "MANUAL_UPLOAD", None)}
    assert _client(["INVOICE_VIEW"]).get("/invoice-review/workbench").status_code == 403
    reviewer = _client(["INVOICE_OCR_REVIEW"])
    body = reviewer.get("/invoice-review/workbench").json()
    assert body["counts"] == {"total": 1, "ready": 1} and body["can_review"] and not body["can_send"]
    res = reviewer.post("/invoice-review/bulk-review", json={"items": [{"invoice_id": 1}], "send_for_approval": True}).json()
    assert res["results"][0]["status"] == "REVIEWED" and world.sent == []  # no send permission -> review only
    assert reviewer.post("/invoice-review/bulk-send", json={"invoice_ids": [1]}).status_code == 403
    sender = _client(["INVOICE_SEND_FOR_APPROVAL"])
    assert sender.post("/invoice-review/bulk-send", json={"invoice_ids": [1]}).json()["summary"]["SENT"] == 1


def test_dao_queries_compile_against_the_real_models(monkeypatch):
    """Every ReviewWorkbenchDAO query is built and compiled for PostgreSQL (no database needed),
    so a wrong column / join is caught here rather than in the dev DB."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.orm import Query, Session

    from Backend.Data_Access_Layer import models  # noqa: F401 - mappers
    from Backend.Data_Access_Layer.dao.review_workbench_dao import ReviewWorkbenchDAO

    compiled = []

    def fake_all(self):
        compiled.append(str(self.statement.compile(dialect=postgresql.dialect())))
        return []
    monkeypatch.setattr(Query, "all", fake_all)
    dao = ReviewWorkbenchDAO(Session())
    dao.invoices_in_status(["OCR_REVIEW_PENDING"], 10, invoice_ids=[1])
    dao.inbound_document_ids([1]); dao.upload_items([1]); dao.open_issue_counts([1]); dao.tds_rows([1])
    dao.vendor_mappings([1]); dao.last_coded_non_po([1], [2]); dao.po_coding([1]); dao.departments(); dao.categories()
    assert len(compiled) == 10
    assert "vendor_category_mapping" in " ".join(compiled) and "purchase_requisition" in " ".join(compiled)
