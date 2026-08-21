#Backend/API_Layer/utils/redis_cache.py
import json
import logging
from typing import Any, Optional

from Backend.API_Layer.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def get_cache(key: str) -> Optional[Any]:

    redis_client = get_redis_client()

    if not redis_client:
        return None

    try:
        raw_value = redis_client.get(key)
    except Exception:
        logger.exception("Redis GET failed for key '%s'", key)
        return None

    if raw_value is None:
        return None

    try:
        return json.loads(raw_value)
    except (TypeError, ValueError):
        logger.error(
            "Malformed JSON in Redis for key '%s' - ignoring.", key
        )
        return None


def set_cache(
    key: str,
    value: Any,
    ttl: Optional[int] = None,
) -> bool:

    redis_client = get_redis_client()

    if not redis_client:
        return False

    try:
        payload = json.dumps(value, default=str)
    except (TypeError, ValueError):
        logger.exception(
            "Failed to JSON-serialize value for key '%s'", key
        )
        return False

    try:
        if ttl:
            redis_client.set(key, payload, ex=ttl)
        else:
            redis_client.set(key, payload)
        return True
    except Exception:
        logger.exception("Redis SET failed for key '%s'", key)
        return False


def delete_cache(key: str) -> bool:

    redis_client = get_redis_client()

    if not redis_client:
        return False

    try:
        redis_client.delete(key)
        return True
    except Exception:
        logger.exception("Redis DELETE failed for key '%s'", key)
        return False
