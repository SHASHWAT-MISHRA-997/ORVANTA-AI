"""
ORVANTA Cloud — Event Service
CRUD operations for geopolitical events.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from app.models.event import Event, EventType, EventSource
from app.schemas.event import EventCreate, EventResponse, EventListResponse, EventFilter
from app.core.config import settings
from app.core.source_trust import is_verified_source
from app.core.logging import get_logger
from app.ingestion.normalizer import sanitize_text_value

logger = get_logger(__name__)


async def create_event(
    data: EventCreate,
    organization_id: UUID,
    db: AsyncSession,
) -> Event:
    """Create a new event."""
    is_verified = 1 if is_verified_source(data.source, data.source_url, None) else 0
    if settings.OFFICIAL_ONLY_MODE and is_verified != 1:
        raise ValueError("Only official-source records can be created in official-only mode")
    event = Event(
        organization_id=organization_id,
        title=sanitize_text_value(data.title, 512) or "Untitled Event",
        description=sanitize_text_value(data.description, 5000),
        event_type=data.event_type,
        source=data.source,
        source_url=data.source_url or None,
        country=sanitize_text_value(data.country, 100),
        region=sanitize_text_value(data.region, 255),
        city=sanitize_text_value(data.city, 255),
        latitude=data.latitude,
        longitude=data.longitude,
        severity=data.severity,
        confidence=data.confidence,
        event_date=data.event_date or datetime.now(timezone.utc),
        tags=data.tags,
        actors=data.actors,
        is_verified=is_verified,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    logger.info("event_created", event_id=str(event.id), type=data.event_type)
    return event


async def get_events(
    organization_id: UUID,
    filters: EventFilter,
    db: AsyncSession,
) -> EventListResponse:
    """Get events with filtering and pagination."""
    query = select(Event).where(
        Event.organization_id == organization_id,
        Event.is_verified == 1,
    )

    # Apply filters
    if filters.event_type:
        query = query.where(Event.event_type == filters.event_type)
    if filters.country:
        query = query.where(Event.country == filters.country)
    if filters.source:
        query = query.where(Event.source == filters.source)
    if filters.min_severity:
        query = query.where(Event.severity >= filters.min_severity)
    if filters.start_date:
        query = query.where(Event.event_date >= filters.start_date)
    if filters.end_date:
        query = query.where(Event.event_date <= filters.end_date)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (filters.page - 1) * filters.page_size
    query = query.order_by(Event.created_at.desc()).offset(offset).limit(filters.page_size)

    result = await db.execute(query)
    events = result.scalars().all()

    return EventListResponse(
        events=[EventResponse.model_validate(e) for e in events],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


async def get_event_by_id(
    event_id: UUID,
    organization_id: UUID,
    db: AsyncSession,
) -> Optional[Event]:
    """Get a single event by ID."""
    result = await db.execute(
        select(Event).where(
            and_(
                Event.id == event_id,
                Event.organization_id == organization_id,
                Event.is_verified == 1,
            )
        )
    )
    return result.scalar_one_or_none()


async def bulk_create_events(
    events_data: List[dict],
    organization_id: UUID,
    db: AsyncSession,
) -> int:
    """Bulk insert events from ingestion pipelines. Returns count of created events."""
    created = 0
    for data in events_data:
        payload = dict(data)
        payload["title"] = sanitize_text_value(payload.get("title"), 512) or "Untitled Event"
        payload["description"] = sanitize_text_value(payload.get("description"), 5000)
        payload["country"] = sanitize_text_value(payload.get("country"), 100)
        payload["region"] = sanitize_text_value(payload.get("region"), 255)
        payload["city"] = sanitize_text_value(payload.get("city"), 255)
        if "is_verified" not in payload:
            payload["is_verified"] = 1 if is_verified_source(
                payload.get("source"),
                payload.get("source_url"),
                payload.get("raw_data"),
            ) else 0

        if settings.OFFICIAL_ONLY_MODE and payload.get("is_verified") != 1:
            continue

        # Check for duplicates by source_id
        if payload.get("source_id"):
            existing = await db.execute(
                select(Event).where(
                    and_(
                        Event.source_id == payload["source_id"],
                        Event.organization_id == organization_id,
                    )
                )
            )
            if existing.scalar_one_or_none():
                continue

        event = Event(organization_id=organization_id, **payload)
        db.add(event)
        created += 1

    if created > 0:
        await db.commit()
        logger.info("bulk_events_created", count=created, org_id=str(organization_id))

    return created
