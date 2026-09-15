# Backend/Business_Layer/services/cdc_retry_service.py
"""Replays failed CDC events. Reuses the exact same cdc_sync_service
functions the live consumer calls - this file has no synchronization
logic of its own, only the loop that finds retryable failures, replays
them, and updates their status.

Run periodically by Backend/cdc_consumer/retry_scheduler.py.
"""
import logging

from Backend.Business_Layer.services import cdc_sync_service
from Backend.Business_Layer.services.cdc_failure_log_service import CdcFailureLogService
from Backend.Business_Layer.utils.cdc_exceptions import CdcProcessingError
from Backend.cdc_consumer.cdc_event import CdcEvent

logger = logging.getLogger(__name__)


class CdcRetryService:
    def __init__(self, db):
        self.db = db
        self.failure_log_service = CdcFailureLogService(db)

    def run_once(self, limit: int = 100) -> int:
        """Attempts every currently-retryable failure once. Returns the
        number of failures resolved. Each failure is its own DB
        transaction, so one still-failing event never blocks the rest."""
        failures = self.failure_log_service.dao.list_retryable_failures(limit=limit)
        resolved = 0

        for failure in failures:
            event = CdcEvent(
                topic=failure.kafka_topic,
                operation=failure.operation or "u",
                key={},
                data=failure.raw_payload or {},
                source_ts_ms=None,
                kafka_partition=failure.kafka_partition,
                kafka_offset=failure.kafka_offset,
            )

            try:
                cdc_sync_service.process_event(self.db, failure.entity_type, event)
            except CdcProcessingError as exc:
                logger.warning(
                    "CDC retry failed again: id=%s entity_type=%s key=%s error=%s",
                    failure.id, failure.entity_type, failure.entity_key, exc,
                )
                self.db.rollback()
                self.failure_log_service.mark_retry_failed(failure, str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 - must never crash the scheduler loop
                logger.exception(
                    "Unexpected error retrying CDC failure id=%s entity_type=%s",
                    failure.id, failure.entity_type,
                )
                self.db.rollback()
                self.failure_log_service.mark_retry_failed(failure, str(exc))
                continue

            self.db.commit()
            self.failure_log_service.mark_retry_succeeded(failure)
            resolved += 1

        return resolved
