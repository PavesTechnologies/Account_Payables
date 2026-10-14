"""Segregation of duties: preparer can't approve, approver can't release / pay, optional maker-checker."""
import pytest
from sqlalchemy.dialects import postgresql

from Backend.Business_Layer.services import segregation_of_duties_service as sod
from Backend.Data_Access_Layer.models.audit import AuditLog

pytestmark = pytest.mark.sod


class _CfgDb:
    def __init__(self):
        self.rows, self.audit, self.statements = {}, [], []

    def add(self, obj):
        (self.audit.append(obj) if isinstance(obj, AuditLog) else self.rows.__setitem__(obj.config_key, obj))

    def commit(self):
        pass


@pytest.fixture
def svc(monkeypatch):
    db = _CfgDb()

    class MasterDAO:
        def __init__(self, d):
            pass

        def get_system_config_by_key(self, key):
            return db.rows.get(key)
    monkeypatch.setattr(sod, "MasterDAO", MasterDAO)
    service = sod.SegregationOfDutiesService(db)
    people = {"preparers": {"5100007"}, "approvers": {"5100005"}, "releasers": {"5100020"}}
    monkeypatch.setattr(service, "preparers", lambda invoice_id: people["preparers"])
    monkeypatch.setattr(service, "approvers", lambda invoice_id: people["approvers"])
    monkeypatch.setattr(service, "releasers", lambda invoice_id: people["releasers"])
    return service, db


def test_defaults(svc):
    service, _ = svc
    assert service.settings() == {"SOD_PREPARER_CANNOT_APPROVE": True, "SOD_APPROVER_CANNOT_RELEASE": True,
                                  "SOD_RELEASER_CANNOT_PAY": False}


def test_preparer_cannot_approve(svc):
    service, _ = svc
    with pytest.raises(sod.SegregationOfDutiesError, match="cannot approve"):
        service.check_approve(7, "5100007")
    service.check_approve(7, "5100025")  # someone else may


def test_approver_cannot_release_or_pay(svc):
    service, _ = svc
    with pytest.raises(sod.SegregationOfDutiesError, match="mark it ready"):
        service.check_release(7, "5100005")
    with pytest.raises(sod.SegregationOfDutiesError, match="record its payment"):
        service.check_record_payment(7, "5100005")
    service.check_release(7, "5100020")
    service.check_record_payment(7, "5100020")  # maker-checker is off by default


def test_maker_checker_when_switched_on_and_audited(svc):
    service, db = svc
    rules = service.update({"SOD_RELEASER_CANNOT_PAY": True}, "5100026", "Bindu Bhargavi U")
    assert next(r for r in rules if r["key"] == "SOD_RELEASER_CANNOT_PAY")["enabled"] is True
    assert db.audit[-1].action == "SOD_RULES_CHANGED" and db.audit[-1].new_values == {"SOD_RELEASER_CANNOT_PAY": True}
    with pytest.raises(sod.SegregationOfDutiesError, match="maker-checker"):
        service.check_record_payment(7, "5100020")


def test_rules_can_be_switched_off(svc):
    service, _ = svc
    service.update({"SOD_PREPARER_CANNOT_APPROVE": False}, "5100026")
    service.check_approve(7, "5100007")
    with pytest.raises(ValueError, match="Unknown"):
        service.update({"NOPE": True}, "5100026")


def test_errors_are_value_errors_so_routes_answer_422():
    assert issubclass(sod.SegregationOfDutiesError, ValueError)


def test_actor_query_reads_the_invoice_audit_trail():
    captured = []

    class Db:
        def execute(self, stmt):
            captured.append(str(stmt.compile(dialect=postgresql.dialect())))

            class R:
                def all(self_inner):
                    return [("INVOICE_APPROVAL_STEP_DECISION", "5100005", {"decision": "APPROVED"}),
                            ("INVOICE_APPROVAL_STEP_DECISION", "5100025", {"decision": "REJECTED"}),
                            ("INVOICE_SENT_FOR_APPROVAL", "AP_AUTOMATION", {})]
            return R()
    service = sod.SegregationOfDutiesService.__new__(sod.SegregationOfDutiesService)
    service.db = Db()
    assert service.approvers(9) == {"5100005"}  # rejections and the automation actor don't count
    assert "ap.audit_log" in captured[0] and "record_id" in captured[0]
