# Backend/cdc_consumer/consumer.py
"""The live Kafka consumer for the AP approver-directory CDC pipeline.

Kafka topic -> parse -> validate -> upsert/delete -> commit offset.
On failure: log to ap.cdc_failure_log -> commit offset anyway (so a
poison/blocked message never wedges the partition) -> CdcRetryScheduler
retries it later. This mirrors the reference XMS/EMS architecture's
"failure log -> ack -> scheduled retry" behaviour, adapted to a
synchronous, manually-committed kafka-python consumer (there is no
Spring-style container/ack object here - see cdc_dao/cdc_sync_service).

Uses its own AP-specific consumer group (KafkaConfig.group_id, default
"ap-approver-cdc-consumer") - independent of XMS's consumer group on the
shared eos.employee_details topic, with its own offsets.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

from kafka import KafkaConsumer
from kafka.structs import OffsetAndMetadata, TopicPartition

from Backend.Business_Layer.services import cdc_sync_service
from Backend.Business_Layer.services.cdc_failure_log_service import CdcFailureLogService
from Backend.Business_Layer.utils.cdc_exceptions import (
    CdcProcessingError,
    MalformedCdcEventError,
    MissingDependencyError,
    UnknownCdcTopicError,
)
from Backend.cdc_consumer.cdc_event import parse_debezium_message
from Backend.config.kafka_config import KafkaConfig
from Backend.Data_Access_Layer.utils.database import SessionLocal

logger = logging.getLogger(__name__)

_FAILURE_TYPE_BY_EXCEPTION = {
    MalformedCdcEventError: "MALFORMED_EVENT",
    MissingDependencyError: "MISSING_DEPENDENCY",
    UnknownCdcTopicError: "UNKNOWN_TOPIC",
}


def _failure_type_for(exc: Exception) -> str:
    return _FAILURE_TYPE_BY_EXCEPTION.get(type(exc), "UNKNOWN")


class ApproverDirectoryCdcConsumer:
    def __init__(self, config: KafkaConfig):
        self.config = config
        self._topic_to_entity: Dict[str, str] = {
            config.eos_department_topic: cdc_sync_service.ENTITY_DEPARTMENT,
            config.eos_employee_topic: cdc_sync_service.ENTITY_EMPLOYEE,
            config.ums_user_topic: cdc_sync_service.ENTITY_USER,
            config.ums_role_topic: cdc_sync_service.ENTITY_ROLE,
            config.ums_user_role_topic: cdc_sync_service.ENTITY_USER_ROLE,
        }
        self._consumer: Optional[KafkaConsumer] = None

    def _build_consumer(self) -> KafkaConsumer:
        return KafkaConsumer(
            *self.config.topics,
            bootstrap_servers=self.config.bootstrap_servers,
            group_id=self.config.group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            key_deserializer=lambda raw: raw,
            value_deserializer=lambda raw: raw,
        )

    def run(self, stop_event: threading.Event) -> None:
        self._consumer = self._build_consumer()
        logger.info(
            "CDC consumer started: group=%s topics=%s",
            self.config.group_id, self.config.topics,
        )
        try:
            while not stop_event.is_set():
                records = self._consumer.poll(timeout_ms=int(self.config.poll_timeout_seconds * 1000))
                if not records:
                    continue

                for topic_partition, messages in records.items():
                    last_offset = None
                    for message in messages:
                        self._handle_message(message)
                        last_offset = message.offset

                    if last_offset is not None:
                        self._consumer.commit(
                            {topic_partition: OffsetAndMetadata(last_offset + 1, None, -1)}
                        )
        finally:
            self._consumer.close()
            logger.info("CDC consumer stopped")

    def _handle_message(self, message) -> None:
        entity_type = self._topic_to_entity.get(message.topic)
        db = SessionLocal()

        try:
            if entity_type is None:
                raise UnknownCdcTopicError(f"No entity mapping registered for topic {message.topic!r}")

            event = parse_debezium_message(
                topic=message.topic,
                raw_key=message.key,
                raw_value=message.value,
                partition=message.partition,
                offset=message.offset,
            )
            if event is None:
                return  # log-compaction tombstone, nothing to apply

            cdc_sync_service.process_event(db, entity_type, event)
            db.commit()

        except CdcProcessingError as exc:
            db.rollback()
            self._log_failure(db, message, entity_type, exc)

        except Exception as exc:  # noqa: BLE001 - a single bad message must never kill the consumer
            db.rollback()
            logger.exception(
                "Unexpected error processing CDC message topic=%s partition=%s offset=%s",
                message.topic, message.partition, message.offset,
            )
            self._log_failure(db, message, entity_type, exc, failure_type="UNKNOWN")

        finally:
            db.close()

    def _log_failure(self, db, message, entity_type: Optional[str], exc: Exception, failure_type: Optional[str] = None) -> None:
        raw_payload: Optional[dict] = None
        entity_key: Optional[str] = None
        operation: Optional[str] = None

        try:
            import json
            if message.value is not None:
                envelope = json.loads(message.value)
                if isinstance(envelope, dict):
                    operation = envelope.get("op")
                    data = envelope.get("before") if operation == "d" else envelope.get("after")
                    raw_payload = data if isinstance(data, dict) else envelope
                    if entity_type and isinstance(data, dict):
                        entity_key = cdc_sync_service.describe_entity_key(entity_type, data)
        except Exception:  # noqa: BLE001 - best-effort context for debugging only
            logger.debug("Could not extract payload context for failure log", exc_info=True)

        try:
            CdcFailureLogService(db).record_failure(
                kafka_topic=message.topic,
                kafka_partition=message.partition,
                kafka_offset=message.offset,
                entity_type=entity_type or "UNKNOWN",
                entity_key=entity_key,
                operation=operation,
                failure_type=failure_type or _failure_type_for(exc),
                error_message=str(exc),
                raw_payload=raw_payload,
                max_retries=self.config.max_retries,
            )
        except Exception:  # noqa: BLE001 - logging the failure must never itself crash the consumer
            logger.exception(
                "Failed to persist CdcFailureLog for topic=%s partition=%s offset=%s - event will be "
                "reprocessed on next restart since its offset will not be committed",
                message.topic, message.partition, message.offset,
            )
            raise
