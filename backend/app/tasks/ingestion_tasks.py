"""
ORVANTA Cloud — Ingestion Celery Tasks
Periodic tasks for data ingestion from external sources.
"""

import asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.gdelt import fetch_gdelt_events
from app.ingestion.acled import fetch_acled_events
from app.ingestion.rss import fetch_rss_events
from app.ingestion.normalizer import normalize_and_deduplicate
from app.models.event import Event
from app.models.organization import Organization
from app.db.database import AsyncSessionLocal
from app.services.live_sync import sync_official_live_events

logger = get_logger(__name__)

# Sync engine for Celery tasks (Celery doesn't play well with async)
sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
SyncSession = sessionmaker(bind=sync_engine)


def _run_async(coro):
    """Helper to run async code in sync Celery tasks."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _store_events(events_data: list, source: str):
    """Store normalized events for all organizations."""
    session = SyncSession()
    try:
        orgs = session.execute(
            select(Organization).where(Organization.is_active == True)
        ).scalars().all()

        total_created = 0
        touched_org_ids: list[str] = []
        for org in orgs:
            created_for_org = 0
            for data in events_data:
                if settings.OFFICIAL_ONLY_MODE and int(data.get("is_verified", 0)) != 1:
                    continue

                if data.get("source_id"):
                    existing = session.execute(
                        select(Event).where(
                            Event.source_id == data["source_id"],
                            Event.organization_id == org.id,
                        )
                    ).scalar_one_or_none()
                    if existing:
                        continue

                event = Event(organization_id=org.id, **data)
                session.add(event)
                total_created += 1
                created_for_org += 1

            if created_for_org > 0:
                touched_org_ids.append(str(org.id))

        session.commit()

        if touched_org_ids:
            from uuid import UUID
            from app.services.live_sync import backfill_official_scores_and_alerts

            for org_id in touched_org_ids:
                try:
                    _run_async(
                        backfill_official_scores_and_alerts(
                            organization_id=UUID(org_id),
                            limit=settings.LIVE_SYNC_BACKLOG_LIMIT,
                        )
                    )
                except Exception as exc:
                    logger.warning("ingestion_backfill_failed", org_id=org_id, error=str(exc))

        logger.info(f"{source}_events_stored", count=total_created)
        return total_created
    except Exception as e:
        session.rollback()
        logger.error(f"{source}_store_error", error=str(e))
        return 0
    finally:
        session.close()


async def _live_sync_org(org_id):
    async with AsyncSessionLocal() as db:
        return await sync_official_live_events(
            organization_id=org_id,
            db=db,
            force=False,
        )


@celery_app.task(bind=True, name="app.tasks.ingestion_tasks.ingest_gdelt")
def ingest_gdelt(self):
    """Periodic task: Fetch and store GDELT events."""
    logger.info("ingestion_started", source="gdelt")
    try:
        if settings.OFFICIAL_ONLY_MODE:
            logger.info("ingestion_skipped_official_only", source="gdelt")
            return {"source": "gdelt", "fetched": 0, "stored": 0}
        raw_events = _run_async(fetch_gdelt_events())
        if not raw_events:
            return {"source": "gdelt", "fetched": 0, "stored": 0}
        normalized = normalize_and_deduplicate(raw_events)
        stored = _store_events(normalized, "gdelt")
        return {"source": "gdelt", "fetched": len(raw_events), "stored": stored}
    except Exception as e:
        logger.error("gdelt_ingestion_failed", error=str(e))
        raise self.retry(exc=e, countdown=60, max_retries=3)


@celery_app.task(bind=True, name="app.tasks.ingestion_tasks.ingest_acled")
def ingest_acled(self):
    """Periodic task: Fetch and store ACLED events."""
    logger.info("ingestion_started", source="acled")
    try:
        if settings.OFFICIAL_ONLY_MODE:
            logger.info("ingestion_skipped_official_only", source="acled")
            return {"source": "acled", "fetched": 0, "stored": 0}
        raw_events = _run_async(fetch_acled_events())
        if not raw_events:
            return {"source": "acled", "fetched": 0, "stored": 0}
        normalized = normalize_and_deduplicate(raw_events)
        stored = _store_events(normalized, "acled")
        return {"source": "acled", "fetched": len(raw_events), "stored": stored}
    except Exception as e:
        logger.error("acled_ingestion_failed", error=str(e))
        raise self.retry(exc=e, countdown=60, max_retries=3)


@celery_app.task(bind=True, name="app.tasks.ingestion_tasks.ingest_rss")
def ingest_rss(self):
    """Periodic task: Fetch and store RSS feed events."""
    logger.info("ingestion_started", source="rss")
    try:
        raw_events = _run_async(fetch_rss_events())
        if not raw_events:
            return {"source": "rss", "fetched": 0, "stored": 0}
        normalized = normalize_and_deduplicate(raw_events)
        stored = _store_events(normalized, "rss")
        return {"source": "rss", "fetched": len(raw_events), "stored": stored}
    except Exception as e:
        logger.error("rss_ingestion_failed", error=str(e))
        raise self.retry(exc=e, countdown=60, max_retries=3)


@celery_app.task(name="app.tasks.ingestion_tasks.ingest_all")
def ingest_all():
    """Manual trigger: Run all ingestion pipelines."""
    results = {}
    for task_fn, name in [
        (ingest_gdelt, "gdelt"),
        (ingest_acled, "acled"),
        (ingest_rss, "rss"),
    ]:
        try:
            results[name] = task_fn()
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


@celery_app.task(bind=True, name="app.tasks.ingestion_tasks.live_sync_all_orgs")
def live_sync_all_orgs(self):
    """Periodic task: keep official live feeds synced for all active organizations."""
    logger.info("live_sync_all_orgs_started")
    session = SyncSession()
    try:
        org_ids = session.execute(
            select(Organization.id).where(Organization.is_active == True)
        ).scalars().all()

        synced = 0
        failed = 0
        total_stored = 0
        total_alerts = 0

        for org_id in org_ids:
            try:
                result = _run_async(_live_sync_org(org_id))
                synced += 1
                total_stored += int(result.get("stored", 0) or 0)
                total_alerts += int(result.get("alerts_created", 0) or 0)
            except Exception as exc:
                failed += 1
                logger.error("live_sync_org_failed", org_id=str(org_id), error=str(exc))

        summary = {
            "organizations_total": len(org_ids),
            "organizations_synced": synced,
            "organizations_failed": failed,
            "stored_events": total_stored,
            "alerts_created": total_alerts,
        }
        logger.info("live_sync_all_orgs_completed", **summary)
        return summary
    except Exception as e:
        logger.error("live_sync_all_orgs_failed", error=str(e))
        raise self.retry(exc=e, countdown=60, max_retries=2)
    finally:
        session.close()
