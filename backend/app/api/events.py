"""
ORVANTA Cloud — Events API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.db.database import get_db
from app.core.deps import get_current_org, require_admin
from app.schemas.event import EventCreate, EventResponse, EventListResponse, EventFilter
from app.schemas.live import LiveSyncRequest, LiveSyncResponse
from app.services.event_service import create_event, get_events, get_event_by_id
from app.services.live_sync import sync_official_live_events
from app.models.event import EventType, EventSource

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=EventListResponse)
async def list_events(
    event_type: Optional[EventType] = None,
    country: Optional[str] = None,
    source: Optional[EventSource] = None,
    min_severity: Optional[int] = Query(None, ge=1, le=10),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """List events with optional filtering."""
    user, org, membership = org_context
    filters = EventFilter(
        event_type=event_type,
        country=country,
        source=source,
        min_severity=min_severity,
        page=page,
        page_size=page_size,
    )
    return await get_events(org.id, filters, db)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Get a single event by ID."""
    user, org, membership = org_context
    event = await get_event_by_id(event_id, org.id, db)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventResponse.model_validate(event)


@router.post("", response_model=EventResponse, status_code=201)
async def create_new_event(
    data: EventCreate,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Create a new event manually."""
    user, org, membership = org_context
    try:
        event = await create_event(data, org.id, db)
        return EventResponse.model_validate(event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/live-sync", response_model=LiveSyncResponse)
async def trigger_live_sync(
    request: LiveSyncRequest,
    org_context: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fetch live official events, then refresh derived scores and alerts."""
    user, org, membership = org_context
    result = await sync_official_live_events(
        organization_id=org.id,
        db=db,
        force=request.force,
    )
    return LiveSyncResponse(**result)
