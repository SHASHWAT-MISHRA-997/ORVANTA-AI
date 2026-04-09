"""
ORVANTA Cloud — Celery App Configuration
"""

from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "warops",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.ingestion_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Periodic task schedule
beat_schedule = {}

if settings.AUTO_INGEST_ENABLED:
    beat_schedule.update(
        {
            "ingest-gdelt-15min": {
                "task": "app.tasks.ingestion_tasks.ingest_gdelt",
                "schedule": 900.0,
            },
            "ingest-acled-hourly": {
                "task": "app.tasks.ingestion_tasks.ingest_acled",
                "schedule": 3600.0,
            },
            "ingest-rss-30min": {
                "task": "app.tasks.ingestion_tasks.ingest_rss",
                "schedule": 1800.0,
            },
        }
    )

if settings.LIVE_SYNC_AUTO_ENABLED:
    beat_schedule["live-sync-all-orgs"] = {
        "task": "app.tasks.ingestion_tasks.live_sync_all_orgs",
        "schedule": float(settings.LIVE_SYNC_AUTO_INTERVAL_SECONDS),
    }

celery_app.conf.beat_schedule = beat_schedule
