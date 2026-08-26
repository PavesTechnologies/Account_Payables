# Backend/API_Layer/utils/redis_client.py
import redis
import time
import logging
from ...config.env_loader import get_env_var

logger = logging.getLogger(__name__)

REDIS_URL = get_env_var("REDIS_URL")

_redis_client = None
_last_failure_time = None
RETRY_AFTER_SECONDS = 30  # try reconnecting every 30s after failure


def get_redis_client():
    global _redis_client, _last_failure_time

    # If failed recently, don't retry yet (avoid hammering)
    if _last_failure_time:
        if time.time() - _last_failure_time < RETRY_AFTER_SECONDS:
            return None
        else:
            # Retry window passed — reset and try again
            logger.info("🔄 Retrying Redis connection...")
            _redis_client = None
            _last_failure_time = None

    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
                health_check_interval=30,  # 👈 auto-detects dropped connections
            )
            _redis_client.ping()
            logger.info("✅ Redis connected successfully")
        except Exception as e:
            logger.warning(f"⚠️ Redis unavailable: {e}")
            _last_failure_time = time.time()
            _redis_client = None
            return None

    return _redis_client


def close_redis_client():
    global _redis_client
    if _redis_client:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None