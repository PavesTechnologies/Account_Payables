# Backend/tests/test_quotation_vendor_matcher.py
"""Unit tests for quotation vendor name matching. The pure matching
core (normalize/suffix-strip/token-overlap/find_best_match) needs no
database - only match_vendor (thin DAO wrapper) is exercised via a
fake VendorDAO substitute in test_quotation_extraction_route.py's
integration tests."""
from __future__ import annotations

import pytest

from Backend.Business_Layer.utils import quotation_vendor_matcher as matcher


# ---------------------------------------------------------------------------
# normalize_vendor_name / names_match_normalized
# ---------------------------------------------------------------------------


def test_normalize_vendor_name_casefolds_and_collapses_whitespace():
    assert (
        matcher.normalize_vendor_name("  ABC   Technologies  ")
        == "abc technologies"
    )


def test_names_match_normalized_exact_after_casefold():
    assert matcher.names_match_normalized(
        "ABC Technologies", "abc technologies"
    )


def test_names_match_normalized_via_legal_suffix_strip():
    assert matcher.names_match_normalized(
        "ABC Technologies Pvt Ltd", "ABC Technologies Private Limited"
    )


def test_names_match_normalized_false_for_different_vendors():
    assert not matcher.names_match_normalized(
        "ABC Technologies Pvt Ltd", "XYZ Traders Pvt Ltd"
    )


# ---------------------------------------------------------------------------
# name_overlap_ratio
# ---------------------------------------------------------------------------


def test_name_overlap_ratio_full_overlap():
    assert matcher.name_overlap_ratio(
        "ABC Technologies", "ABC Technologies Pvt Ltd"
    ) == pytest.approx(1.0)


def test_name_overlap_ratio_partial():
    ratio = matcher.name_overlap_ratio("ABC Technologies", "ABC Traders")
    assert 0.0 < ratio < 1.0


def test_name_overlap_ratio_empty_when_no_tokens():
    assert matcher.name_overlap_ratio("", "ABC Technologies") == 0.0


# ---------------------------------------------------------------------------
# find_best_match
# ---------------------------------------------------------------------------


def test_find_best_match_normalized_rung():
    candidates = [
        (1, "XYZ Traders"),
        (2, "ABC Technologies Private Limited"),
    ]

    match = matcher.find_best_match("ABC Technologies Pvt Ltd", candidates)

    assert match is not None
    vendor_id, vendor_name, confidence = match
    assert vendor_id == 2
    assert confidence == matcher.NORMALIZED_MATCH_CONFIDENCE


def test_find_best_match_fuzzy_rung_above_threshold():
    candidates = [(3, "ABC Technologies Solutions Private Limited")]

    match = matcher.find_best_match("ABC Technologies Solutions", candidates)

    assert match is not None
    vendor_id, vendor_name, confidence = match
    assert vendor_id == 3
    assert confidence >= matcher.FUZZY_MATCH_MIN_CONFIDENCE


def test_find_best_match_none_below_fuzzy_threshold():
    candidates = [(4, "Totally Unrelated Vendor Name")]

    match = matcher.find_best_match("ABC Technologies Pvt Ltd", candidates)

    assert match is None


def test_find_best_match_none_for_empty_candidates():
    assert matcher.find_best_match("ABC Technologies", []) is None


# ---------------------------------------------------------------------------
# match_vendor (DB-backed) - exact / normalized / unmatched
# ---------------------------------------------------------------------------


class _FakeVendor:
    def __init__(self, vendor_id: int, vendor_name: str):
        self.vendor_id = vendor_id
        self.vendor_name = vendor_name


class _FakeVendorDAO:
    def __init__(self, vendors):
        self._vendors = vendors

    def get_vendor_by_name(self, vendor_name: str):
        target = vendor_name.strip().lower()
        for vendor in self._vendors:
            if vendor.vendor_name.strip().lower() == target:
                return vendor
        return None

    def get_all_vendors(self, search=None, limit=100, **kwargs):
        if not search:
            return list(self._vendors)
        return [
            v for v in self._vendors
            if search.lower() in v.vendor_name.lower()
        ]


@pytest.fixture(autouse=True)
def _patch_vendor_dao(monkeypatch):
    """match_vendor constructs its own VendorDAO(db) - swap the class
    for a fake so these tests never touch a real database session."""

    vendors = [
        _FakeVendor(1, "ABC Technologies Pvt Ltd"),
        _FakeVendor(2, "XYZ Traders Private Limited"),
    ]

    monkeypatch.setattr(
        matcher, "VendorDAO", lambda db: _FakeVendorDAO(vendors)
    )
    yield


def test_match_vendor_exact_match():
    result = matcher.match_vendor("ABC Technologies Pvt Ltd", db=None)

    assert result.vendor_id == 1
    assert result.vendor_name == "ABC Technologies Pvt Ltd"
    assert result.confidence == matcher.EXACT_MATCH_CONFIDENCE


def test_match_vendor_normalized_match():
    result = matcher.match_vendor("abc technologies private limited", db=None)

    assert result.vendor_id == 1
    assert result.confidence == matcher.NORMALIZED_MATCH_CONFIDENCE


def test_match_vendor_unmatched_returns_name_without_id():
    result = matcher.match_vendor("Totally Unknown Vendor Co", db=None)

    assert result.vendor_id is None
    assert result.vendor_name == "Totally Unknown Vendor Co"
    assert result.confidence == 0.0


def test_match_vendor_blank_name_returns_all_none():
    result = matcher.match_vendor("   ", db=None)

    assert result.vendor_id is None
    assert result.vendor_name is None
    assert result.confidence == 0.0


def test_match_vendor_none_name_returns_all_none():
    result = matcher.match_vendor(None, db=None)

    assert result.vendor_id is None
    assert result.vendor_name is None
    assert result.confidence == 0.0
