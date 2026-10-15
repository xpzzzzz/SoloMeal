import logging
import signal
import time
from datetime import timezone
from pathlib import Path

from ..core.config import Settings
from ..core.database import build_engine, build_session_factory
from ..services.receipt_jobs import dispatch
from .celery_app import TASK_NAME, app

logger = logging.getLogger(__name__)


def publish(task_id, deadline):
    with app.connection_for_write() as connection:
        connection.ensure_connection(max_retries=0)
        with app.amqp.Producer(connection) as producer:
            app.send_task(TASK_NAME, args=[task_id], task_id=task_id, producer=producer,
                          expires=deadline.replace(tzinfo=timezone.utc), retry=False,
                          delivery_mode=2, argsrepr="(<task_id>,)")


def main():
    settings = Settings()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while running:
            Path("/tmp/receipt-dispatch.heartbeat").touch()
            try:
                dispatch(factory, settings, publish, limit=10)
            except Exception:
                logger.warning("Receipt dispatch unavailable category=database_or_broker")
            Path("/tmp/receipt-dispatch.heartbeat").touch()
            end = time.monotonic() + settings.receipt_dispatch_interval_seconds
            while running and time.monotonic() < end:
                time.sleep(min(.25, max(0, end - time.monotonic())))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
