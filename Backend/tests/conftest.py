# Backend/tests/conftest.py
"""Makes ``Backend.*`` absolute imports resolve when pytest is run from
anywhere, by putting the Account_Payables project root (the parent of
``Backend/``) on ``sys.path`` — the same root every application module
already imports relative to (e.g. ``Backend.API_Layer...``).
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "sod: exercise the real segregation-of-duties checks")


@pytest.fixture(autouse=True)
def _segregation_of_duties_off(request, monkeypatch):
    """Most tests build services on fake sessions that cannot read audit_log / system
    configuration; segregation of duties has its own tests (marked ``sod``)."""
    if request.node.get_closest_marker("sod"):
        return
    from Backend.Business_Layer.services import segregation_of_duties_service as sod
    for name in ("check_approve", "check_release", "check_record_payment"):
        monkeypatch.setattr(sod.SegregationOfDutiesService, name, lambda self, *a, **k: None)
    monkeypatch.setattr(sod.SegregationOfDutiesService, "blocked_for_approval", lambda self, *a, **k: set())
