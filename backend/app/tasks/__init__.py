from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "pms_extraction",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.task_routes = {
    "app.tasks.ingestion.*": {"queue": "ingestion"},
    "app.tasks.extraction.*": {"queue": "extraction"},
    "app.tasks.learning.*": {"queue": "learning"},
}

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
