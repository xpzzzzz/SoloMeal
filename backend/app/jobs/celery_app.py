from celery import Celery
from kombu import Exchange, Queue

from ..core.config import Settings

TASK_NAME = "solomeal.receipts.parse"
QUEUE = "solomeal.receipts"


def build_celery(settings):
    application = Celery("solomeal", broker=settings.receipt_broker_url.get_secret_value(),
                         include=["app.jobs.tasks"])
    application.conf.update(
        task_queues=(Queue(QUEUE, Exchange(QUEUE, type="direct", durable=True),
                           routing_key=QUEUE, durable=True, queue_arguments={"x-queue-type": "quorum"}),),
        task_default_queue=QUEUE, task_default_exchange=QUEUE, task_default_routing_key=QUEUE,
        task_create_missing_queues=False, task_default_delivery_mode=2,
        broker_transport_options={"confirm_publish": True, "read_timeout": 5, "write_timeout": 5},
        broker_connection_timeout=3, broker_heartbeat=10,
        broker_connection_retry_on_startup=True, broker_connection_max_retries=None,
        task_serializer="json", accept_content=["json"], result_serializer="json",
        result_backend=None, task_ignore_result=True, task_store_errors_even_if_ignored=False,
        task_acks_late=True, task_reject_on_worker_lost=True,
        worker_cancel_long_running_tasks_on_connection_loss=True,
        worker_prefetch_multiplier=1, worker_concurrency=settings.receipt_worker_concurrency,
        worker_enable_remote_control=False, worker_max_tasks_per_child=100,
        task_time_limit=settings.receipt_worker_hard_limit_seconds,
        task_soft_time_limit=max(1, settings.receipt_worker_hard_limit_seconds - 10),
        task_publish_retry=False, timezone="UTC", enable_utc=True,
    )
    return application


app = build_celery(Settings())
