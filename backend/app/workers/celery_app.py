from celery import Celery
from celery.signals import worker_init, worker_process_init

from app.core.config import get_settings
from app.workers.logging import configure_worker_file_logging

settings = get_settings()

celery_app = Celery(
    "ai_sales_teammate",
    broker=settings.celery_redis_url,
    backend=settings.celery_redis_url,
    include=["app.workers.approvals"],
)

celery_app.conf.update(
    accept_content=["json"],
    enable_utc=True,
    result_serializer="json",
    task_serializer="json",
    task_track_started=True,
    timezone="UTC",
    worker_prefetch_multiplier=1,
)


@worker_init.connect
def _configure_worker_main_logging(**kwargs) -> None:
    configure_worker_file_logging()


@worker_process_init.connect
def _configure_worker_pool_logging(**kwargs) -> None:
    configure_worker_file_logging()
