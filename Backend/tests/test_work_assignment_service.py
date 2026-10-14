"""Work assignment: claim only unowned AP work, reassign within the team, leave cover, rule precedence."""
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services import work_assignment_service as was


class _Db:
    def __init__(self):
        self.committed = 0

    def commit(self):
        self.committed += 1


@pytest.fixture
def svc(monkeypatch):
    service = was.WorkAssignmentService(_Db())
    state = SimpleNamespace(
        statuses={1: "OCR_REVIEW_PENDING", 2: "OCR_REVIEWED", 3: "PENDING_APPROVAL", 4: "RETURNED_FOR_REVIEW"},
        owners={2: {"user_id": "5100027", "name": "Kalasagar P"}, 4: {"user_id": "5100007", "name": "Venkatesh Gali"}},
        set_calls=[])
    monkeypatch.setattr(service, "_ap_stage", lambda ids: {i: state.statuses[i] for i in ids if i in state.statuses})
    monkeypatch.setattr(service, "owners", lambda ids: {i: state.owners[i] for i in ids if i in state.owners})
    monkeypatch.setattr(service, "team", lambda: [{"user_id": "5100007", "name": "Venkatesh Gali"},
                                                   {"user_id": "5100027", "name": "Kalasagar P"}])
    monkeypatch.setattr(service, "_set", lambda invoice_id, user, source, by, rule_id=None, note=None:
                        state.set_calls.append((invoice_id, str(user), source)))
    return service, state


def test_claim_takes_only_unowned_work_still_with_ap(svc):
    service, state = svc
    result = service.claim([1, 2, 3, 4], "5100007")
    assert result["claimed"] == [1, 4]  # 1 unowned, 4 already mine
    reasons = {s["invoice_id"]: s["reason"] for s in result["skipped"]}
    assert reasons == {2: "Already with Kalasagar P", 3: "No longer with AP"}
    assert state.set_calls == [(1, "5100007", "CLAIM")]


def test_reassign_within_the_team_only(svc):
    service, state = svc
    with pytest.raises(ValueError, match="active AP Executive"):
        service.reassign([1], "5100026", "5100026")
    result = service.reassign([1, 3], "5100027", "5100026", "Balancing")
    assert result["reassigned"] == [1] and result["skipped"][0]["invoice_id"] == 3
    assert state.set_calls == [(1, "5100027", "REASSIGN")]


def test_names_never_touch_more_than_first_and_last_name():
    captured = []

    class Db:
        def execute(self, stmt, params):
            captured.append(str(stmt))
            return SimpleNamespace(all=lambda: [("5100007", "Venkatesh", "Gali")])
    names = was.WorkAssignmentService(Db()).names(["5100007", None, "AP_AUTOMATION"])
    assert names == {"5100007": "Venkatesh Gali"}
    assert "first_name" in captured[0] and "password" not in captured[0] and "raw_payload->>" in captured[0]


def test_assign_new_never_raises(monkeypatch):
    class Db:
        def get(self, *a):
            raise RuntimeError("table missing")

        def rollback(self):
            pass
    assert was.WorkAssignmentService(Db()).assign_new(5) is None
