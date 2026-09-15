# Backend/cdc_consumer/run_consumer.py
"""Standalone entrypoint for the AP approver-directory CDC consumer.

Runs as its own process, separate from the API (`uvicorn Backend.main:app`).
Not imported by Backend/main.py: the API process does not run this
consumer. Run directly:

    python -m Backend.cdc_consumer.run_consumer

The retry scheduler runs on a background daemon thread; the Kafka poll
loop runs on the main thread. SIGINT/SIGTERM trigger a graceful stop
(finish the in-flight poll batch, close the consumer cleanly) rather than
an abrupt kill, so an in-progress commit is never interrupted.

If the consumer loop raises past run() (see consumer.py's _log_failure -
this only happens when even writing to CdcFailureLog fails, e.g. the DB
itself is unreachable), this process exits non-zero - failing loud beats
spinning forever in a state where nothing can be persisted anyway.
"""
import logging
import signal
import sys
import threading

from Backend.cdc_consumer.consumer import ApproverDirectoryCdcConsumer
from Backend.cdc_consumer.retry_scheduler import CdcRetryScheduler
from Backend.config.kafka_config import get_kafka_config
from Backend.Data_Access_Layer import models  # noqa: F401 - registers all model classes before create_all
from Backend.Data_Access_Layer.models.base import Base
from Backend.Data_Access_Layer.utils.database import engine

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> int:
    Base.metadata.create_all(bind=engine)

    config = get_kafka_config()
    stop_event = threading.Event()

    def _handle_signal(signum, _frame):
        logger.info("Received signal %s - shutting down CDC consumer", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    retry_thread = threading.Thread(
        target=CdcRetryScheduler(config).run,
        args=(stop_event,),
        name="cdc-retry-scheduler",
        daemon=True,
    )
    retry_thread.start()

    try:
        ApproverDirectoryCdcConsumer(config).run(stop_event)
    except Exception:
        logger.exception("CDC consumer loop crashed - exiting so the orchestrator restarts it")
        stop_event.set()
        return 1
    finally:
        retry_thread.join(timeout=5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
