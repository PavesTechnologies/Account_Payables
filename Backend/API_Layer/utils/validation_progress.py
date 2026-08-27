# Backend/API_Layer/utils/validation_progress.py
"""Jenkins-style stage progress for the /validate-fields pipeline,
backed by Redis (via redis_cache.py) for temporary UI-facing state.

Each validation job gets its own Redis key (ap:validation:{job_id}),
so concurrent jobs never share state. Redis is purely a progress
cache: every write here is best-effort and swallows its own errors
(logged, never raised) so the actual validation pipeline never
depends on Redis being reachable - see each function's try/except.

Not the source of truth for anything permanent; keys expire after
VALIDATION_PROGRESS_TTL_SECONDS.
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


VALIDATION_PROGRESS_TTL_SECONDS = int(
    get_env_var("VALIDATION_PROGRESS_TTL_SECONDS", "3600")
)

# Order matters: this is the sequence the pipeline actually runs in,
# and it's what skip_remaining_stages() walks forward from.
STAGE_ORDER = ["extraction", "vendor", "buyer", "gst"]

STAGE_LABELS = {
    "extraction": "Extraction Validation",
    "vendor": "Vendor Validation",
    "buyer": "Buyer Validation",
    "gst": "GST Tax Validation",
}

_KEY_PREFIX = "ap:validation:"


def _job_key(job_id: str) -> str:
    return f"{_KEY_PREFIX}{job_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_job_id() -> str:
    return f"val_{uuid.uuid4().hex[:8]}"


def _empty_stage() -> Dict[str, Any]:
    return {
        "status": "WAITING",
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
        "message": None,
        "issues": [],
        "field_comparisons": [],
    }


# ============================================================
# Job lifecycle
# ============================================================

def init_validation_job(job_id: str) -> None:
    """Creates the Redis record for a newly-queued job. Always
    call this before scheduling the background task, so a GET
    on /status immediately after POST already finds something."""

    job = {
        "job_id": job_id,
        "status": "QUEUED",
        "current_stage": None,
        "started_at": _now_iso(),
        "completed_at": None,
        "is_valid": None,
        "requires_manual_review": None,
        "issues": [],
        "success": [],
        "stages": {
            stage: {**_empty_stage(), "label": STAGE_LABELS[stage]}
            for stage in STAGE_ORDER
        },
    }

    try:
        set_cache(
            _job_key(job_id),
            job,
            ttl=VALIDATION_PROGRESS_TTL_SECONDS,
        )
    except Exception:
        logger.exception(
            "Failed to initialize validation progress for job '%s'",
            job_id,
        )


def get_validation_status(job_id: str) -> Optional[Dict[str, Any]]:

    try:
        return get_cache(_job_key(job_id))
    except Exception:
        logger.exception(
            "Failed to read validation progress for job '%s'", job_id
        )
        return None


def _load_job(job_id: str) -> Optional[Dict[str, Any]]:

    job = get_cache(_job_key(job_id))

    if job is None:
        logger.warning(
            "No validation progress record found for job '%s' "
            "(expired, never initialized, or Redis unavailable).",
            job_id,
        )

    return job


def _save_job(job_id: str, job: Dict[str, Any]) -> None:
    set_cache(
        _job_key(job_id),
        job,
        ttl=VALIDATION_PROGRESS_TTL_SECONDS,
    )


# ============================================================
# Stage updates
# ============================================================

def update_validation_stage(
    job_id: str,
    stage: str,
    status: str,
    message: Optional[str] = None,
    issues: Optional[List[str]] = None,
    duration_ms: Optional[int] = None,
    field_comparisons: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """status: one of WAITING / RUNNING / SUCCESS / FAILED / SKIPPED."""

    try:
        job = _load_job(job_id)

        if job is None:
            return

        stage_data = job["stages"].setdefault(
            stage,
            {**_empty_stage(), "label": STAGE_LABELS.get(stage, stage)},
        )

        now = _now_iso()

        stage_data["status"] = status

        if message is not None:
            stage_data["message"] = message

        if issues is not None:
            stage_data["issues"] = issues

        if field_comparisons is not None:
            stage_data["field_comparisons"] = field_comparisons

        if status == "RUNNING":
            stage_data["started_at"] = now
            job["status"] = "RUNNING"
            job["current_stage"] = stage

        elif status in ("SUCCESS", "FAILED"):
            stage_data["completed_at"] = now

            if duration_ms is not None:
                stage_data["duration_ms"] = duration_ms
            elif stage_data.get("started_at"):
                try:
                    started = datetime.fromisoformat(
                        stage_data["started_at"]
                    )
                    completed = datetime.fromisoformat(now)
                    stage_data["duration_ms"] = round(
                        (completed - started).total_seconds() * 1000
                    )
                except ValueError:
                    pass

        job["stages"][stage] = stage_data

        _save_job(job_id, job)

    except Exception:
        logger.exception(
            "Failed to update validation stage '%s' for job '%s'",
            stage,
            job_id,
        )


def skip_remaining_stages(
    job_id: str,
    from_stage: str,
    message: str = "Skipped - an earlier stage failed",
) -> None:
    """Marks every stage after from_stage as SKIPPED, so the UI
    doesn't show them stuck on WAITING forever once the pipeline
    has stopped (stop-at-first-failure orchestration)."""

    try:
        index = STAGE_ORDER.index(from_stage)
    except ValueError:
        return

    for stage in STAGE_ORDER[index + 1:]:
        update_validation_stage(
            job_id,
            stage,
            "SKIPPED",
            message=message,
        )


def complete_validation_job(
    job_id: str,
    is_valid: bool,
    requires_manual_review: bool,
    issues: List[str],
    success: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Marks the whole job COMPLETED (valid) or FAILED (not valid),
    and stores the same is_valid/requires_manual_review/issues/success
    shape the synchronous ValidationResult always returned - so a
    caller reading the finished job via GET .../status gets the exact
    same fields it used to get directly from POST."""

    try:
        job = _load_job(job_id)

        if job is None:
            return

        job["status"] = "COMPLETED" if is_valid else "FAILED"
        job["current_stage"] = None
        job["completed_at"] = _now_iso()
        job["is_valid"] = is_valid
        job["requires_manual_review"] = requires_manual_review
        job["issues"] = issues
        job["success"] = success or []

        _save_job(job_id, job)

    except Exception:
        logger.exception(
            "Failed to complete validation job '%s'", job_id
        )


def fail_validation_job(job_id: str, error_message: str) -> None:
    """For genuine unexpected/system errors (e.g. DB unreachable),
    as opposed to a normal validation failure - the pipeline could
    not run to a real conclusion at all."""

    try:
        job = _load_job(job_id) or {
            "job_id": job_id,
            "stages": {},
        }

        job["status"] = "FAILED"
        job["current_stage"] = None
        job["completed_at"] = _now_iso()
        job["is_valid"] = False
        job["requires_manual_review"] = True
        job["issues"] = [error_message]
        job.setdefault("success", [])

        _save_job(job_id, job)

    except Exception:
        logger.exception(
            "Failed to mark validation job '%s' as failed", job_id
        )


def delete_validation_job(job_id: str) -> None:
    try:
        delete_cache(_job_key(job_id))
    except Exception:
        logger.exception(
            "Failed to delete validation job '%s'", job_id
        )
