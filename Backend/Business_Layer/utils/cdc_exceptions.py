# Backend/Business_Layer/utils/cdc_exceptions.py
"""Custom exceptions for the EOS/UMS Kafka CDC consumer (Backend/cdc_consumer).

Raised by Backend/Business_Layer/services/cdc_sync_service.py; caught by
both the live consumer and CdcRetryService so the two never duplicate
failure-handling logic.
"""


class CdcProcessingError(Exception):
    """Base class for all CDC event processing errors."""


class UnknownCdcTopicError(CdcProcessingError):
    """Raised when an event arrives for a topic the consumer isn't wired to handle."""


class MalformedCdcEventError(CdcProcessingError):
    """Raised when a CDC message can't be parsed into a CdcEvent at all
    (not valid JSON, missing 'after' on a non-delete op, etc). Not
    worth retrying - the message itself is broken."""


class MissingDependencyError(CdcProcessingError):
    """Raised when an event can't be applied yet because a cross-topic
    dependency hasn't arrived/synced (e.g. a ums.user_role event referencing
    a user_id that ap.ums_user_cache doesn't have yet). Retried later by
    CdcRetryService once the dependency is expected to have caught up."""
