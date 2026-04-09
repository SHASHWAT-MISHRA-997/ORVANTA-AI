"""
ORVANTA Cloud - Live official sync helpers
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import AsyncSessionLocal
from app.ingestion.normalizer import normalize_and_deduplicate
from app.ingestion.rss import fetch_rss_events
from app.models.event import Event
from app.models.risk_score import RiskScore
from app.services.automation import process_risk_automations
from app.services.risk_engine import upsert_risk_score
from app.services.watchlist_service import evaluate_watchlists_for_events

logger = get_logger(__name__)


async def _get_latest_ingested_at(
    organization_id: UUID,
    db: AsyncSession,
) -> Optional[datetime]:
    result = await db.execute(
        select(func.max(Event.ingested_at)).where(
            Event.organization_id == organization_id,
            Event.is_verified == 1,
        )
    )
    return result.scalar_one_or_none()


async def _count_official_events(
    organization_id: UUID,
    db: AsyncSession,
) -> int:
    result = await db.execute(
        select(func.count()).where(
            Event.organization_id == organization_id,
            Event.is_verified == 1,
        )
    )
    return int(result.scalar() or 0)


async def _count_official_risk_scores(
    organization_id: UUID,
    db: AsyncSession,
) -> int:
    result = await db.execute(
        select(func.count()).where(RiskScore.organization_id == organization_id)
    )
    return int(result.scalar() or 0)


async def _store_official_events(
    organization_id: UUID,
    events_data: list[dict],
    db: AsyncSession,
) -> tuple[list[Event], int]:
    source_ids = [payload.get("source_id") for payload in events_data if payload.get("source_id")]
    existing_source_ids: set[str] = set()
    if source_ids:
        existing_result = await db.execute(
            select(Event.source_id).where(
                Event.organization_id == organization_id,
                Event.source_id.in_(source_ids),
            )
        )
        existing_source_ids = {value for value in existing_result.scalars().all() if value}

    created_events: list[Event] = []
    duplicates_skipped = 0
    for payload in events_data:
        if settings.OFFICIAL_ONLY_MODE and int(payload.get("is_verified", 0)) != 1:
            continue

        source_id = payload.get("source_id")
        if source_id and source_id in existing_source_ids:
            duplicates_skipped += 1
            continue

        event = Event(organization_id=organization_id, **payload)
        db.add(event)
        if source_id:
            existing_source_ids.add(source_id)
        created_events.append(event)

    if created_events:
        await db.commit()
        for event in created_events:
            await db.refresh(event)
    else:
        await db.rollback()

    return created_events, duplicates_skipped


async def _backfill_with_session(
    organization_id: UUID,
    db: AsyncSession,
    event_ids: Optional[list[UUID]] = None,
    limit: Optional[int] = None,
) -> dict:
    query = select(Event).where(
        Event.organization_id == organization_id,
        Event.is_verified == 1,
        Event.is_duplicate == 0,
    )
    if event_ids:
        query = query.where(Event.id.in_(event_ids))
    else:
        query = query.order_by(
            func.coalesce(Event.event_date, Event.created_at).desc()
        ).limit(limit or settings.LIVE_SYNC_BACKLOG_LIMIT)

    result = await db.execute(query)
    events = result.scalars().all()

    scored_events = 0
    updated_scores = 0
    alert_created_count = 0
    score_pairs: list[tuple[Event, object]] = []

    for event in events:
        risk_score, created = await upsert_risk_score(
            event=event,
            organization_id=organization_id,
            db=db,
        )
        if created:
            scored_events += 1
        else:
            updated_scores += 1
        score_pairs.append((event, risk_score))

    if score_pairs:
        await db.commit()

    for event, risk_score in score_pairs:
        actions = await process_risk_automations(
            risk_score=risk_score,
            event_title=event.title,
            organization_id=organization_id,
            db=db,
        )
        if actions.get("alert_created"):
            alert_created_count += 1

    return {
        "scored_events": scored_events,
        "updated_scores": updated_scores,
        "alerts_created": alert_created_count,
    }


async def backfill_official_scores_and_alerts(
    organization_id: UUID,
    db: Optional[AsyncSession] = None,
    event_ids: Optional[list[UUID]] = None,
    limit: Optional[int] = None,
) -> dict:
    if db is not None:
        return await _backfill_with_session(
            organization_id=organization_id,
            db=db,
            event_ids=event_ids,
            limit=limit,
        )

    async with AsyncSessionLocal() as session:
        return await _backfill_with_session(
            organization_id=organization_id,
            db=session,
            event_ids=event_ids,
            limit=limit,
        )


async def sync_official_live_events(
    organization_id: UUID,
    db: AsyncSession,
    force: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    latest_ingested_at = await _get_latest_ingested_at(organization_id, db)
    official_event_count = await _count_official_events(organization_id, db)
    official_risk_count = await _count_official_risk_scores(organization_id, db)
    cooldown_cutoff = now - timedelta(minutes=settings.LIVE_SYNC_COOLDOWN_MINUTES)

    should_fetch = (
        force
        or official_event_count == 0
        or latest_ingested_at is None
        or latest_ingested_at < cooldown_cutoff
    )

    fetched = 0
    normalized_count = 0
    duplicates_skipped = 0
    created_events: list[Event] = []

    if should_fetch:
        raw_events = await fetch_rss_events(max_per_feed=settings.LIVE_SYNC_MAX_PER_FEED)
        fetched = len(raw_events)
        normalized_events = normalize_and_deduplicate(raw_events)
        normalized_count = len(normalized_events)
        created_events, duplicates_skipped = await _store_official_events(
            organization_id=organization_id,
            events_data=normalized_events,
            db=db,
        )
        logger.info(
            "live_sync_fetched",
            org_id=str(organization_id),
            fetched=fetched,
            normalized=normalized_count,
            stored=len(created_events),
            duplicates_skipped=duplicates_skipped,
        )

    should_backfill = should_fetch or official_risk_count == 0

    if should_backfill:
        backfill = await backfill_official_scores_and_alerts(
            organization_id=organization_id,
            db=db,
            event_ids=[event.id for event in created_events] or None,
            limit=settings.LIVE_SYNC_BACKLOG_LIMIT,
        )
    else:
        backfill = {
            "scored_events": 0,
            "updated_scores": 0,
            "alerts_created": 0,
        }

    watchlist_result = await evaluate_watchlists_for_events(
        organization_id=organization_id,
        events=created_events,
        db=db,
    )

    latest_after = await _get_latest_ingested_at(organization_id, db)
    exact_coordinate_events = sum(
        1
        for event in created_events
        if event.latitude is not None and event.longitude is not None
    )

    if should_fetch:
        message = "Live official feeds synced and operational analytics refreshed."
        status = "synced"
    else:
        message = "Recent live data already available. Analytics and alerts were refreshed from stored verified events."
        status = "recent"

    return {
        "status": status,
        "message": message,
        "fetched": fetched,
        "normalized": normalized_count,
        "stored": len(created_events),
        "duplicates_skipped": duplicates_skipped,
        "scored_events": backfill["scored_events"],
        "updated_scores": backfill["updated_scores"],
        "alerts_created": backfill["alerts_created"] + watchlist_result["alerts_created"],
        "watchlist_alerts_created": watchlist_result["alerts_created"],
        "exact_coordinate_events": exact_coordinate_events,
        "latest_ingested_at": latest_after,
        "synced_at": datetime.now(timezone.utc),
    }
