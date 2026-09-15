# Backend/cdc_consumer/cdc_event.py
"""Normalizes a raw Kafka record from one of the ums_cdc.*/eos_cdc.* topics
into a CdcEvent, per the confirmed connector format (plain JSON key/value,
no schema registry, full Debezium envelope - see the devops CDC topic
reference: {before, after, source, op, ts_ms}, deletes followed by a
tombstone record with the same key and a null value).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from Backend.Business_Layer.utils.cdc_exceptions import MalformedCdcEventError

logger = logging.getLogger(__name__)

OP_CREATE = "c"
OP_UPDATE = "u"
OP_DELETE = "d"
OP_SNAPSHOT_READ = "r"

_VALID_OPS = {OP_CREATE, OP_UPDATE, OP_DELETE, OP_SNAPSHOT_READ}


@dataclass(frozen=True)
class CdcEvent:
    """A normalized CDC event, ready for cdc_sync_service to apply.

    `data` is the row image to process: `after` for create/update/snapshot,
    `before` for delete (Debezium sets `after` to null on delete, but a
    delete still needs the row's last known values to know what to remove).
    """

    topic: str
    operation: str  # one of OP_CREATE / OP_UPDATE / OP_DELETE / OP_SNAPSHOT_READ
    key: dict
    data: dict
    source_ts_ms: Optional[int]
    kafka_partition: int
    kafka_offset: int

    @property
    def is_delete(self) -> bool:
        return self.operation == OP_DELETE


def parse_debezium_message(
    *,
    topic: str,
    raw_key: Optional[bytes],
    raw_value: Optional[bytes],
    partition: int,
    offset: int,
) -> Optional[CdcEvent]:
    """Returns a CdcEvent, or None if this record should be skipped
    (a log-compaction tombstone: same key, null value - carries no data).

    Raises MalformedCdcEventError if the value isn't a well-formed
    Debezium envelope - not worth retrying, the message itself is broken.
    """
    if raw_value is None:
        logger.debug(
            "Skipping tombstone record on %s [partition=%s offset=%s]",
            topic, partition, offset,
        )
        return None

    try:
        envelope: Any = json.loads(raw_value)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedCdcEventError(
            f"Non-JSON value on {topic} [partition={partition} offset={offset}]: {exc}"
        ) from exc

    if not isinstance(envelope, dict):
        raise MalformedCdcEventError(
            f"Expected a JSON object envelope on {topic} [partition={partition} offset={offset}], "
            f"got {type(envelope).__name__}"
        )

    operation = envelope.get("op")
    if operation not in _VALID_OPS:
        raise MalformedCdcEventError(
            f"Unrecognized/missing Debezium 'op' ({operation!r}) on {topic} "
            f"[partition={partition} offset={offset}]"
        )

    data = envelope.get("before") if operation == OP_DELETE else envelope.get("after")
    if data is None:
        raise MalformedCdcEventError(
            f"Missing row image for op={operation!r} on {topic} [partition={partition} offset={offset}]"
        )

    key: dict = {}
    if raw_key is not None:
        try:
            parsed_key = json.loads(raw_key)
            if isinstance(parsed_key, dict):
                key = parsed_key
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "Non-JSON key on %s [partition=%s offset=%s] - continuing without it",
                topic, partition, offset,
            )

    source = envelope.get("source") or {}
    source_ts_ms = envelope.get("ts_ms") or source.get("ts_ms")

    return CdcEvent(
        topic=topic,
        operation=operation,
        key=key,
        data=data,
        source_ts_ms=source_ts_ms,
        kafka_partition=partition,
        kafka_offset=offset,
    )
