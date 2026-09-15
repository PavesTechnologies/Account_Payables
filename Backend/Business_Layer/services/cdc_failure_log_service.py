# Backend/Business_Layer/services/cdc_failure_log_service.py
"""Records/updates CdcFailureLog rows. Used by the live consumer when
processing fails, and by CdcRetryService when a retry attempt finishes.

One row per (kafka_topic, kafka_partition, kafka_offset) - if the same
failed message is encountered again (e.g. redelivered before its offset
was committed), the existing row's retry bookkeeping is reused instead of
creating a duplicate.
"""
from typing import Optional

from Backend.Data_Access_Layer.dao.cdc_dao import CdcDAO
from Backend.Data_Access_Layer.models.cdc import CdcFailureLog


class CdcFailureLogService:
    def __init__(self, db):
        self.db = db
        self.dao = CdcDAO(db)

    def record_failure(
        self,
        *,
        kafka_topic: str,
        kafka_partition: int,
        kafka_offset: int,
        entity_type: str,
        entity_key: Optional[str],
        operation: Optional[str],
        failure_type: str,
        error_message: str,
        raw_payload: Optional[dict],
        max_retries: int,
    ) -> CdcFailureLog:
        existing = self.dao.find_failure_by_kafka_position(kafka_topic, kafka_partition, kafka_offset)
        if existing is not None:
            self.db.commit()
            return existing

        failure = self.dao.create_failure(
            kafka_topic=kafka_topic,
            kafka_partition=kafka_partition,
            kafka_offset=kafka_offset,
            entity_type=entity_type,
            entity_key=entity_key,
            operation=operation,
            failure_type=failure_type,
            error_message=error_message,
            raw_payload=raw_payload,
            max_retries=max_retries,
        )
        self.db.commit()
        return failure

    def mark_retry_succeeded(self, failure: CdcFailureLog) -> None:
        self.dao.update_failure_after_retry(failure, succeeded=True)
        self.db.commit()

    def mark_retry_failed(self, failure: CdcFailureLog, error_message: str) -> None:
        self.dao.update_failure_after_retry(failure, succeeded=False, error_message=error_message)
        self.db.commit()
