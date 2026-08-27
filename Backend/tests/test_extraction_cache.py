# Backend/tests/test_extraction_cache.py
"""Unit tests for the Redis-backed extraction cache
(Backend/API_Layer/utils/extraction_cache.py).

Same FakeRedisClient convention as test_validation_progress.py -
redis_cache.py's module-level get_redis_client binding is the patch
target, no real Redis connection needed/used.
"""
from __future__ import annotations

from typing import Dict

import pytest

import Backend.API_Layer.utils.redis_cache as redis_cache_module
import Backend.API_Layer.utils.extraction_cache as ec


class FakeRedisClient:

    def __init__(self):
        self.store: Dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def delete(self, key):
        existed = key in self.store
        self.store.pop(key, None)
        return 1 if existed else 0


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedisClient()
    monkeypatch.setattr(
        redis_cache_module, "get_redis_client", lambda: client
    )
    return client


@pytest.fixture
def no_redis(monkeypatch):
    monkeypatch.setattr(
        redis_cache_module, "get_redis_client", lambda: None
    )


MINIMAL_EXTRACTED = {
    "vendor": {"name": "Acme Traders", "gstin": "27AABCU9603R1ZM"},
    "buyer": {"name": "Beta Buyers"},
}


def test_new_extraction_id_has_expected_prefix():
    assert ec.new_extraction_id().startswith("ext_")


def test_init_and_get_round_trip(fake_redis):
    extraction_id = ec.new_extraction_id()

    ec.init_extraction_cache(
        extraction_id, MINIMAL_EXTRACTED, "invoices/test.pdf"
    )

    cached = ec.get_extraction_cache(extraction_id)

    assert cached is not None
    assert cached["extraction_id"] == extraction_id
    assert cached["file_path"] == "invoices/test.pdf"
    assert cached["extracted_invoice"]["vendor"]["name"] == "Acme Traders"
    assert cached["corrections"] == []


def test_get_missing_extraction_returns_none(fake_redis):
    assert ec.get_extraction_cache("ext_doesnotexist") is None


def test_apply_correction_records_before_after_and_updates_value(fake_redis):
    extraction_id = ec.new_extraction_id()
    ec.init_extraction_cache(
        extraction_id, MINIMAL_EXTRACTED, "invoices/test.pdf"
    )

    updated = ec.apply_correction(
        extraction_id,
        "vendor",
        {"gstin": "27AABCU9603R1ZQ"},
        corrected_by="user-1",
    )

    assert updated["extracted_invoice"]["vendor"]["gstin"] == "27AABCU9603R1ZQ"
    assert len(updated["corrections"]) == 1

    event = updated["corrections"][0]
    assert event["field"] == "vendor.gstin"
    assert event["before"] == "27AABCU9603R1ZM"
    assert event["after"] == "27AABCU9603R1ZQ"
    assert event["corrected_by"] == "user-1"
    assert event["corrected_at"]

    # Persisted, not just returned - a fresh read shows the same state.
    reread = ec.get_extraction_cache(extraction_id)
    assert reread["extracted_invoice"]["vendor"]["gstin"] == "27AABCU9603R1ZQ"
    assert len(reread["corrections"]) == 1


def test_apply_correction_skips_noop_fields(fake_redis):
    extraction_id = ec.new_extraction_id()
    ec.init_extraction_cache(
        extraction_id, MINIMAL_EXTRACTED, "invoices/test.pdf"
    )

    updated = ec.apply_correction(
        extraction_id,
        "vendor",
        {"name": "Acme Traders"},  # same as current value
        corrected_by="user-1",
    )

    assert updated["corrections"] == []


def test_apply_correction_missing_extraction_returns_none(fake_redis):
    result = ec.apply_correction(
        "ext_doesnotexist", "vendor", {"name": "X"}, corrected_by="user-1"
    )
    assert result is None


def test_record_confirmation_appends_marker(fake_redis):
    extraction_id = ec.new_extraction_id()
    ec.init_extraction_cache(
        extraction_id, MINIMAL_EXTRACTED, "invoices/test.pdf"
    )

    updated = ec.record_confirmation(extraction_id, "vendor", "user-1")

    assert len(updated["corrections"]) == 1
    assert updated["corrections"][0]["field"] == "vendor.__confirmed__"
    assert updated["corrections"][0]["after"] is True


def test_is_section_confirmed(fake_redis):
    extraction_id = ec.new_extraction_id()
    ec.init_extraction_cache(
        extraction_id, MINIMAL_EXTRACTED, "invoices/test.pdf"
    )

    cached = ec.get_extraction_cache(extraction_id)
    assert ec.is_section_confirmed(cached["corrections"], "vendor") is False

    ec.record_confirmation(extraction_id, "vendor", "user-1")

    cached = ec.get_extraction_cache(extraction_id)
    assert ec.is_section_confirmed(cached["corrections"], "vendor") is True
    assert ec.is_section_confirmed(cached["corrections"], "buyer") is False


def test_no_redis_never_raises(no_redis):
    extraction_id = ec.new_extraction_id()

    # None of these should raise even though Redis is unreachable.
    ec.init_extraction_cache(
        extraction_id, MINIMAL_EXTRACTED, "invoices/test.pdf"
    )
    assert ec.get_extraction_cache(extraction_id) is None
    assert ec.apply_correction(
        extraction_id, "vendor", {"name": "X"}, corrected_by="user-1"
    ) is None
    assert ec.record_confirmation(extraction_id, "vendor", "user-1") is None
    ec.delete_extraction_cache(extraction_id)
