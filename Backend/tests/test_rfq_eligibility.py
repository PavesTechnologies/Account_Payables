# Backend/tests/test_rfq_eligibility.py
"""Tests for the backend-enforced RFQ eligibility gate.

Fake-DAO style (see test_purchase_category_department.py): no DB, no network.
The gate must fail closed - anything missing blocks the RFQ.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services.nda_service import (
    LOOKUP_EXPIRED,
    LOOKUP_INVALID,
    LOOKUP_NOT_FOUND,
    LOOKUP_VALID,
    NdaLookupResult,
)
from Backend.Business_Layer.services.rfq_eligibility_service import RFQEligibilityService


def _status(code):
    return SimpleNamespace(status_code=code)


def _pr(pr_id=1, status="APPROVED", department_id=1, purchase_category_id=10):
    return SimpleNamespace(
        id=pr_id, status=_status(status),
        department_id=department_id, purchase_category_id=purchase_category_id,
    )


def _vendor(vendor_id=100, status="ACTIVE"):
    return SimpleNamespace(vendor_id=vendor_id, vendor_name="Acme", status=_status(status))


def _engagement(pre_screen="PASS", nda_final=False, nda_recommended=False):
    return SimpleNamespace(
        pre_screen_status=pre_screen,
        nda_final_required=nda_final,
        nda_recommended=nda_recommended,
    )


def _onboarding(status_code):
    return SimpleNamespace(status=_status(status_code))


class FakeDAO:
    def __init__(self, pr=None, vendor=None, engagement=None, onboarding_requests=None):
        self._pr = pr
        self._vendor = vendor
        self._engagement = engagement
        self._onboarding_requests = onboarding_requests or []

    def get_pr_by_id(self, pr_id):
        return self._pr

    def get_vendor_by_id(self, vendor_id):
        return self._vendor

    def get_engagement(self, vendor_id, department_id, purchase_category_id):
        return self._engagement

    def get_open_requests_for_pr(self, pr_id):
        return self._onboarding_requests


def _nda(status_code):
    return SimpleNamespace(status=_status(status_code))


def _service(nda_lookup=None, signed_is_final=False, **kwargs):
    """Eligibility service with its data access faked.

    ``nda_lookup`` stands in for NdaService.check_existing_nda - the NDA
    lifecycle itself is covered by test_nda.py; here we only assert how each
    outcome affects RFQ eligibility. The default (NOT_FOUND) is the realistic
    "NDA required but never generated" case.
    """
    service = RFQEligibilityService(db=object())
    service.onboarding_dao = FakeDAO(**kwargs)

    lookup = nda_lookup or NdaLookupResult(LOOKUP_NOT_FOUND, None, "No NDA on file.")
    service.nda_service = SimpleNamespace(
        check_existing_nda=lambda vendor_id, department_id, purchase_category_id: lookup,
        nda_dao=SimpleNamespace(
            get_config_value=lambda key: "TRUE" if signed_is_final else "FALSE"
        ),
    )
    return service


def _check(result, name):
    return next(c for c in result.checks if c.check == name)


# ---------------------------------------------------------------------------
# Allowed
# ---------------------------------------------------------------------------


def test_no_nda_required_is_eligible():
    service = _service(pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=False))

    result = service.check(1, 100)

    assert result.eligible is True
    assert result.failed_checks == []
    assert result.reason is None
    assert _check(result, "NDA").status == "NOT_REQUIRED"


def test_completed_onboarding_request_is_eligible():
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(),
        onboarding_requests=[_onboarding("COMPLETED")],
    )

    assert service.check(1, 100).eligible is True


def test_cancelled_onboarding_request_does_not_block():
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(),
        onboarding_requests=[_onboarding("CANCELLED")],
    )

    assert service.check(1, 100).eligible is True


def test_pr_in_vendor_selection_is_eligible():
    service = _service(pr=_pr(status="VENDOR_SELECTION"), vendor=_vendor(), engagement=_engagement())

    assert service.check(1, 100).eligible is True


# ---------------------------------------------------------------------------
# Blocked
# ---------------------------------------------------------------------------


def test_pending_nda_blocks_with_spec_shaped_failure():
    service = _service(pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=True))

    result = service.check(1, 100)

    assert result.eligible is False
    failure = result.failed_checks[0]
    assert failure.check == "NDA"
    assert failure.status == "PENDING"
    assert failure.message == "Mandatory NDA is not completed."


def test_nda_recommendation_is_used_when_no_decision_recorded():
    service = _service(
        pr=_pr(), vendor=_vendor(),
        engagement=_engagement(nda_final=None, nda_recommended=True),
    )

    assert service.check(1, 100).eligible is False


def test_pre_screen_fail_blocks():
    service = _service(pr=_pr(), vendor=_vendor(), engagement=_engagement(pre_screen="FAIL"))

    result = service.check(1, 100)

    assert result.eligible is False
    assert _check(result, "PRE_SCREEN").status == "FAIL"


def test_pre_screen_need_information_blocks():
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(pre_screen="NEED_INFORMATION")
    )

    assert service.check(1, 100).eligible is False


def test_missing_engagement_blocks():
    service = _service(pr=_pr(), vendor=_vendor(), engagement=None)

    result = service.check(1, 100)

    assert result.eligible is False
    assert _check(result, "PRE_SCREEN").status == "NOT_FOUND"


def test_inactive_vendor_blocks():
    service = _service(pr=_pr(), vendor=_vendor(status="INACTIVE"), engagement=_engagement())

    result = service.check(1, 100)

    assert result.eligible is False
    assert _check(result, "VENDOR").status == "INACTIVE"


def test_blocked_vendor_blocks():
    service = _service(pr=_pr(), vendor=_vendor(status="BLOCKED"), engagement=_engagement())

    assert service.check(1, 100).eligible is False


def test_unapproved_pr_blocks():
    service = _service(pr=_pr(status="PENDING_APPROVAL"), vendor=_vendor(), engagement=_engagement())

    result = service.check(1, 100)

    assert result.eligible is False
    assert _check(result, "PR").status == "PENDING_APPROVAL"


def test_incomplete_onboarding_blocks():
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(),
        onboarding_requests=[_onboarding("PRE_SCREEN_PENDING")],
    )

    result = service.check(1, 100)

    assert result.eligible is False
    assert _check(result, "ONBOARDING").status == "PRE_SCREEN_PENDING"


def test_missing_pr_blocks():
    service = _service(pr=None, vendor=_vendor(), engagement=_engagement())

    result = service.check(1, 100)

    assert result.eligible is False
    assert result.failed_checks[0].check == "PR"


def test_missing_vendor_blocks():
    service = _service(pr=_pr(), vendor=None, engagement=_engagement())

    result = service.check(1, 100)

    assert result.eligible is False
    assert any(c.check == "VENDOR" and c.status == "NOT_FOUND" for c in result.failed_checks)


# ---------------------------------------------------------------------------
# NDA lifecycle -> RFQ eligibility (Stage 2)
# ---------------------------------------------------------------------------


def test_valid_existing_nda_allows_rfq():
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=True),
        nda_lookup=NdaLookupResult(LOOKUP_VALID, _nda("COMPLETED")),
    )

    result = service.check(1, 100)

    assert result.eligible is True
    assert _check(result, "NDA").status == "COMPLETED"


@pytest.mark.parametrize("status_code", ["PENDING", "SENT", "REJECTED"])
def test_incomplete_nda_states_block_rfq(status_code):
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=True),
        nda_lookup=NdaLookupResult(LOOKUP_INVALID, _nda(status_code), "The vendor's NDA is not completed."),
    )

    result = service.check(1, 100)

    assert result.eligible is False
    assert _check(result, "NDA").status == status_code


def test_expired_nda_blocks_rfq():
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=True),
        nda_lookup=NdaLookupResult(LOOKUP_EXPIRED, _nda("COMPLETED"), "The vendor's NDA has expired."),
    )

    result = service.check(1, 100)

    assert result.eligible is False
    assert "expired" in result.reason.lower()


def test_signed_nda_blocks_by_default():
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=True),
        nda_lookup=NdaLookupResult(LOOKUP_INVALID, _nda("SIGNED"), "The vendor's NDA is not completed."),
    )

    result = service.check(1, 100)

    assert result.eligible is False
    assert _check(result, "NDA").status == "SIGNED"


def test_signed_nda_allowed_when_configuration_says_signed_is_final():
    service = _service(
        pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=True),
        nda_lookup=NdaLookupResult(LOOKUP_INVALID, _nda("SIGNED"), "not completed"),
        signed_is_final=True,
    )

    result = service.check(1, 100)

    assert result.eligible is True
    assert _check(result, "NDA").status == "SIGNED"


def test_not_required_skips_the_nda_lookup_entirely():
    calls = []

    service = _service(pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=False))
    service.nda_service.check_existing_nda = lambda *a, **k: calls.append(a) or None

    result = service.check(1, 100)

    assert result.eligible is True
    assert calls == []


# ---------------------------------------------------------------------------
# Enforcement helpers
# ---------------------------------------------------------------------------


def test_require_eligible_raises_with_reason():
    service = _service(pr=_pr(), vendor=_vendor(), engagement=_engagement(nda_final=True))

    with pytest.raises(ValueError, match="Mandatory NDA is not completed"):
        service.require_eligible(1, 100)


def test_require_eligible_returns_result_when_allowed():
    service = _service(pr=_pr(), vendor=_vendor(), engagement=_engagement())

    assert service.require_eligible(1, 100).eligible is True


def test_check_many_returns_one_result_per_vendor():
    service = _service(pr=_pr(), vendor=_vendor(), engagement=_engagement())

    results = service.check_many(1, [100, 101, 102])

    assert [r.vendor_id for r in results] == [100, 101, 102]


def test_all_three_reported_checks_are_present_on_success():
    service = _service(pr=_pr(), vendor=_vendor(), engagement=_engagement())

    names = [c.check for c in service.check(1, 100).checks]

    assert names == ["PR", "VENDOR", "ONBOARDING", "PRE_SCREEN", "NDA"]


# ---------------------------------------------------------------------------
# Wiring: RFQService must actually call the gate, at BOTH enforcement points.
#
# Gating only send_rfq would leave a hole - ProcurementService.create_quotation
# admits any *invited* vendor, so invite -> quotation -> select_vendor -> PO
# would bypass Pre-Screen and a mandatory NDA entirely.
# ---------------------------------------------------------------------------


class _FakeRFQDAO:
    def __init__(self, rfq, vendor):
        self._rfq = rfq
        self._vendor = vendor
        self.created_invitations = []

    def get_rfq_by_id(self, rfq_id):
        return self._rfq

    def get_vendor_by_id(self, vendor_id):
        return self._vendor

    def is_vendor_invited(self, rfq_id, vendor_id):
        return False

    def create_rfq_vendor(self, rfq_vendor):
        self.created_invitations.append(rfq_vendor)
        return rfq_vendor

    def get_rfq_vendors(self, rfq_id):
        return [SimpleNamespace(vendor_id=100)]


def _rfq_service_with_real_gate(engagement):
    from Backend.Business_Layer.services.rfq_service import RFQService

    rfq = SimpleNamespace(id=5, pr_id=1, status=_status("DRAFT"))
    vendor = _vendor()

    service = RFQService(db=SimpleNamespace(commit=lambda: None, refresh=lambda o: None))
    service.rfq_dao = _FakeRFQDAO(rfq, vendor)
    # A successful invite writes a PR-timeline audit row via procurement_dao.
    service.procurement_dao = SimpleNamespace(create_audit_log=lambda audit_log: audit_log)
    # The REAL eligibility service, with only its data access faked - this is
    # what makes these wiring tests meaningful.
    service.eligibility_service = _service(
        pr=_pr(), vendor=vendor, engagement=engagement
    )
    return service


def test_invite_vendors_is_blocked_by_the_real_gate():
    service = _rfq_service_with_real_gate(_engagement(nda_final=True))

    with pytest.raises(ValueError, match="Mandatory NDA is not completed"):
        service.invite_vendors(5, [100], "officer-1")

    assert service.rfq_dao.created_invitations == []


def test_invite_vendors_allows_an_eligible_vendor():
    service = _rfq_service_with_real_gate(_engagement())

    service.invite_vendors(5, [100], "officer-1")

    assert len(service.rfq_dao.created_invitations) == 1


def test_send_rfq_is_blocked_by_the_real_gate():
    service = _rfq_service_with_real_gate(_engagement(pre_screen="FAIL"))

    with pytest.raises(ValueError, match="Pre-Screen has not passed"):
        service.send_rfq(5, [100], "officer-1")
