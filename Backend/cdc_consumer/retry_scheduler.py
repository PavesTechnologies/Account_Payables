# Backend/cdc_consumer/retry_scheduler.py
"""Periodically replays retryable ap.cdc_failure_log rows.

No APScheduler/Celery/cron infra exists in this project - this is a
plain daemon-thread loop (time-based wait on a stop Event so shutdown is
immediate rather than waiting out a sleep), which is all a single
"every N minutes" job needs.
"""
from __future__ import annotations

import logging
import threading

from Backend.Business_Layer.services.cdc_retry_service import CdcRetryService
from Backend.config.kafka_config import KafkaConfig
from Backend.Data_Access_Layer.utils.database import SessionLocal

logger = logging.getLogger(__name__)


class CdcRetryScheduler:
    def __init__(self, config: KafkaConfig):
        self.config = config

    def run(self, stop_event: threading.Event) -> None:
        logger.info(
            "CDC retry scheduler started: interval=%ss max_retries=%s",
            self.config.retry_interval_seconds, self.config.max_retries,
        )
        while not stop_event.is_set():
            self._run_once_safely()
            stop_event.wait(self.config.retry_interval_seconds)
        logger.info("CDC retry scheduler stopped")

    def _run_once_safely(self) -> None:
        db = SessionLocal()
        try:
            resolved = CdcRetryService(db).run_once()
            if resolved:
                logger.info("CDC retry pass resolved %s previously-failed event(s)", resolved)
        except Exception:  # noqa: BLE001 - one bad retry pass must not kill the scheduler thread
            logger.exception("CDC retry pass raised unexpectedly")
            db.rollback()
        finally:
            db.close()
