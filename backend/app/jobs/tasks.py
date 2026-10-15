import logging
from functools import lru_cache
from uuid import UUID

from ..core.config import Settings
from ..core.database import build_engine, build_session_factory
from ..services.receipt_jobs import execute
from ..services.receipt_recognition import ReceiptRecognizer
from .celery_app import TASK_NAME, app

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def runtime():
    # Created in the prefork child, not shared through fork with open connections.
    settings = Settings()
    return build_session_factory(build_engine(settings.database_url)), settings, ReceiptRecognizer(settings)


@app.task(name=TASK_NAME, ignore_result=True)
def parse_receipt(task_id):
    try:
        task_id = str(UUID(task_id))
    except (ValueError, TypeError, AttributeError):
        return
    try:
        factory, settings, parser = runtime()
        execute(factory, settings, parser, task_id)
    except Exception:
        # Keep raw provider/SQL exceptions out of Celery tracebacks and result stores.
        # MySQL still owns unfinished work; the outbox revisits it until its deadline.
        logger.warning("Receipt worker interrupted task_id=%s category=worker_internal", task_id)
