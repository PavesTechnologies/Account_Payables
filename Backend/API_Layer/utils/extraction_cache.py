# Backend/API_Layer/utils/extraction_cache.py
"""Server-side cache for an extracted invoice, backed by Redis (via
redis_cache.py), keyed independently from the validation job_id.

An extraction (one uploaded document) can be re-validated more than
once as the user corrects vendor/buyer fields, so its identity and
lifetime are separate from a single validation run's job_id - see
validation_progress.py for that side.

Each extraction gets its own Redis key (ap:extraction:{extraction_id}).
Redis is purely a working cache here too: every write is best-effort
and swallows its own errors (logged, never raised), and this is never
the source of truth for anything permanent - corrections are NOT
persisted to the Invoice DB until the separate POST /create-invoice
call. Keys expire after EXTRACTION_CACHE_TTL_SECONDS, refreshed on
every correction/confirmation write.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from Backend.API_Layer.utils.redis_cache import (
    delete_cache,
    get_cache,
    set_cache,
)
from Backend.config.env_loader import get_env_var

logger = logging.getLogger(__name__)


EXTRACTION_CACHE_TTL_SECONDS = int(
    get_env_var("EXTRACTION_CACHE_TTL_SECONDS", "14400")
)

_KEY_PREFIX = "ap:extraction:"

CONFIRMED_MARKER_SUFFIX = "__confirmed__"


def _cache_key(extraction_id: str) -> str:
    return f"{_KEY_PREFIX}{extraction_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_extraction_id() -> str:
    return f"ext_{uuid.uuid4().hex[:8]}"


# ============================================================
# Lifecycle
# ============================================================

def init_extraction_cache(
    extraction_id: str,
    extracted_invoice: Dict[str, Any],
    file_path: str,
) -> None:
    """Creates the Redis record for a newly-extracted invoice. Call
    this right after extraction succeeds, before returning the
    response, so the extraction_id the caller gets back always
    resolves to something."""

    record = {
        "extraction_id": extraction_id,
        "extracted_invoice": extracted_invoice,
        "file_path": file_path,
        "created_at": _now_iso(),
        "corrections": [],
    }

    try:
        set_cache(
            _cache_key(extraction_id),
            record,
            ttl=EXTRACTION_CACHE_TTL_SECONDS,
        )
    except Exception:
        logger.exception(
            "Failed to initialize extraction cache for '%s'",
            extraction_id,
        )


def get_extraction_cache(extraction_id: str) -> Optional[Dict[str, Any]]:

    try:
        return get_cache(_cache_key(extraction_id))
    except Exception:
        logger.exception(
            "Failed to read extraction cache for '%s'", extraction_id
        )
        return None


def _load(extraction_id: str) -> Optional[Dict[str, Any]]:

    record = get_cache(_cache_key(extraction_id))

    if record is None:
        logger.warning(
            "No extraction cache record found for '%s' (expired, "
            "never initialized, or Redis unavailable).",
            extraction_id,
        )

    return record


def _save(extraction_id: str, record: Dict[str, Any]) -> None:
    set_cache(
        _cache_key(extraction_id),
        record,
        ttl=EXTRACTION_CACHE_TTL_SECONDS,
    )


# ============================================================
# Corrections
# ============================================================

def apply_correction(
    extraction_id: str,
    section: str,
    field_updates: Dict[str, Any],
    corrected_by: str,
) -> Optional[Dict[str, Any]]:
    """Applies each (field -> new_value) pair onto the cached
    section (vendor/buyer), recording a before/after CorrectionEvent
    per changed field. No-op fields (new value equal to the current
    cached value) are skipped - they don't generate a correction
    event. Returns the updated cache record, or None if extraction_id
    doesn't exist/expired."""

    try:
        record = _load(extraction_id)

        if record is None:
            return None

        section_data = record["extracted_invoice"].setdefault(section, {})
        now = _now_iso()

        for field, new_value in field_updates.items():

            old_value = section_data.get(field)

            if old_value == new_value:
                continue

            section_data[field] = new_value

            record["corrections"].append({
                "field": f"{section}.{field}",
                "before": old_value,
                "after": new_value,
                "corrected_by": corrected_by,
                "corrected_at": now,
            })

        _save(extraction_id, record)

        return record

    except Exception:
        logger.exception(
            "Failed to apply correction to extraction '%s'",
            extraction_id,
        )
        return None


def record_confirmation(
    extraction_id: str,
    section: str,
    confirmed_by: str,
) -> Optional[Dict[str, Any]]:
    """Records an explicit 'user confirmed this section as-is'
    marker, using the same CorrectionEvent shape as a real field
    correction (before=None, after=True) so no new structure is
    needed. is_section_confirmed() derives the current confirmed
    state by scanning for the latest marker."""

    try:
        record = _load(extraction_id)

        if record is None:
            return None

        record["corrections"].append({
            "field": f"{section}.{CONFIRMED_MARKER_SUFFIX}",
            "before": None,
            "after": True,
            "corrected_by": confirmed_by,
            "corrected_at": _now_iso(),
        })

        _save(extraction_id, record)

        return record

    except Exception:
        logger.exception(
            "Failed to record confirmation for extraction '%s'",
            extraction_id,
        )
        return None


def is_section_confirmed(
    corrections: List[Dict[str, Any]],
    section: str,
) -> bool:
    marker = f"{section}.{CONFIRMED_MARKER_SUFFIX}"
    return any(event.get("field") == marker for event in corrections)


def delete_extraction_cache(extraction_id: str) -> None:
    try:
        delete_cache(_cache_key(extraction_id))
    except Exception:
        logger.exception(
            "Failed to delete extraction cache for '%s'", extraction_id
        )
