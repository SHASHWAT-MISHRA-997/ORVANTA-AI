"""
ORVANTA Cloud - Watchlist Service
Saved filters that create alert matches from official stored events.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertPriority, AlertStatus
from app.models.event import Event
from app.models.watchlist import Watchlist
from app.schemas.watchlist import WatchlistCreate, WatchlistResponse
from app.services.alert_service import create_alert


def _text(value: object) -> str:
    if hasattr(value, "value"):
        value = getattr(value, "value")
    return str(value or "").strip()


def _lower(value: object) -> str:
    return _text(value).lower()


def _raw_object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _event_source_label(event: Event) -> str:
    raw = _raw_object(event.raw_data)
    for key in ("feed", "source_name", "name", "publisher", "channel"):
        label = _text(raw.get(key))
        if label:
            return label

    source_url = _text(event.source_url)
    if source_url:
        try:
            from urllib.parse import urlparse

            return (urlparse(source_url).hostname or source_url).replace("www.", "")
        except Exception:
            return source_url

    source = _text(event.source)
    labels = {
        "gdelt": "GDELT",
        "acled": "ACLED",
        "rss": "RSS",
        "manual": "Manual",
        "agent": "Automated ingest",
    }
    return labels.get(source.lower(), source.replace("_", " ").title()) or "Source"


def _event_country(event: Event) -> str:
    raw = _raw_object(event.raw_data)
    return _text(
        event.country
        or raw.get("country")
        or raw.get("country_name")
        or raw.get("sourcecountry")
        or raw.get("location_country")
    )


def _event_location_text(event: Event) -> str:
    raw = _raw_object(event.raw_data)
    parts = [
        _text(event.city or raw.get("city") or raw.get("locality") or raw.get("town")),
        _text(event.region or raw.get("region") or raw.get("admin1") or raw.get("state") or raw.get("province")),
        _event_country(event),
    ]
    return ", ".join(part for part in parts if part)


def _event_text_blob(event: Event) -> str:
    raw = _raw_object(event.raw_data)
    values = [
        _text(event.title),
        _text(event.description),
        _text(event.event_type),
        _event_source_label(event),
        _event_location_text(event),
        _text(raw.get("place")),
        _text(raw.get("location_name")),
        " ".join(_text(item) for item in (event.tags or []) if _text(item)),
        " ".join(_text(item) for item in (event.actors or []) if _text(item)),
    ]
    return " ".join(value for value in values if value).lower()


def _event_priority(event: Event) -> AlertPriority:
    severity = int(event.severity or 0)
    if severity >= 8:
        return AlertPriority.HIGH
    if severity >= 5:
        return AlertPriority.MEDIUM
    return AlertPriority.LOW


def _watchlist_summary_parts(watchlist: Watchlist) -> list[str]:
    parts: list[str] = []
    if _text(watchlist.country):
        parts.append(f"country: {_text(watchlist.country)}")
    if _text(watchlist.source):
        parts.append(f"source: {_text(watchlist.source)}")
    if _text(watchlist.event_type):
        parts.append(f"type: {_text(watchlist.event_type).replace('_', ' ')}")
    if _text(watchlist.keyword):
        parts.append(f"keyword: {_text(watchlist.keyword)}")
    return parts


def match_watchlist(event: Event, watchlist: Watchlist) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    event_country = _lower(_event_country(event))
    source_label = _lower(_event_source_label(event))
    event_type = _lower(event.event_type)
    text_blob = _event_text_blob(event)

    if _text(watchlist.country):
        country_filter = _lower(watchlist.country)
        if not event_country or event_country != country_filter:
            return False, []
        reasons.append(f"country: {_text(watchlist.country)}")

    if _text(watchlist.source):
        source_filter = _lower(watchlist.source)
        if not source_label or source_label != source_filter:
            return False, []
        reasons.append(f"source: {_text(watchlist.source)}")

    if _text(watchlist.event_type):
        type_filter = _lower(watchlist.event_type)
        if event_type != type_filter:
            return False, []
        reasons.append(f"type: {_text(watchlist.event_type).replace('_', ' ')}")

    if _text(watchlist.keyword):
        keyword_filter = _lower(watchlist.keyword)
        if keyword_filter not in text_blob:
            return False, []
        reasons.append(f"keyword: {_text(watchlist.keyword)}")

    return True, reasons


async def _existing_watchlist_alert(
    organization_id: UUID,
    watchlist_id: UUID,
    event_id: UUID,
    db: AsyncSession,
) -> Optional[Alert]:
    result = await db.execute(
        select(Alert).where(
            Alert.organization_id == organization_id,
            Alert.event_id == event_id,
            Alert.alert_type == "watchlist_match",
            Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
        )
    )
    for alert in result.scalars().all():
        meta = alert.meta_data if isinstance(alert.meta_data, dict) else {}
        if _text(meta.get("watchlist_id")) == str(watchlist_id):
            return alert
    return None


async def create_watchlist_match_alert(
    organization_id: UUID,
    watchlist: Watchlist,
    event: Event,
    matched_filters: list[str],
    db: AsyncSession,
) -> Optional[Alert]:
    existing = await _existing_watchlist_alert(
        organization_id=organization_id,
        watchlist_id=watchlist.id,
        event_id=event.id,
        db=db,
    )
    if existing:
        return None

    summary = ", ".join(matched_filters) if matched_filters else "saved filters"
    return await create_alert(
        organization_id=organization_id,
        event_id=event.id,
        title=f'Watchlist Match: {event.title[:120]}',
        message=(
            f'Watchlist "{watchlist.name}" matched this official stored record. '
            f"Matched filters: {summary}."
        ),
        priority=_event_priority(event),
        db=db,
        alert_type="watchlist_match",
        meta_data={
            "watchlist_id": str(watchlist.id),
            "watchlist_name": watchlist.name,
            "matched_filters": matched_filters,
        },
    )


async def _load_active_watchlists(
    organization_id: UUID,
    db: AsyncSession,
) -> list[Watchlist]:
    result = await db.execute(
        select(Watchlist)
        .where(
            Watchlist.organization_id == organization_id,
            Watchlist.is_active.is_(True),
        )
        .order_by(Watchlist.created_at.desc())
    )
    return list(result.scalars().all())


async def _load_official_events(
    organization_id: UUID,
    db: AsyncSession,
) -> list[Event]:
    result = await db.execute(
        select(Event)
        .where(
            Event.organization_id == organization_id,
            Event.is_verified == 1,
            Event.is_duplicate == 0,
        )
        .order_by(Event.created_at.desc())
    )
    return list(result.scalars().all())


async def evaluate_watchlists_for_events(
    organization_id: UUID,
    events: Iterable[Event],
    db: AsyncSession,
) -> dict:
    watchlists = await _load_active_watchlists(organization_id, db)
    alerts_created = 0
    match_counts: dict[str, int] = {}

    event_list = [event for event in events if int(event.is_verified or 0) == 1 and int(event.is_duplicate or 0) == 0]
    if not watchlists or not event_list:
        return {"alerts_created": 0, "match_counts": match_counts}

    now = datetime.now(timezone.utc)
    changed_watchlists: set[UUID] = set()

    for watchlist in watchlists:
        for event in event_list:
            matched, reasons = match_watchlist(event, watchlist)
            if not matched:
                continue

            match_counts[str(watchlist.id)] = match_counts.get(str(watchlist.id), 0) + 1
            watchlist.last_matched_at = now
            changed_watchlists.add(watchlist.id)

            alert = await create_watchlist_match_alert(
                organization_id=organization_id,
                watchlist=watchlist,
                event=event,
                matched_filters=reasons,
                db=db,
            )
            if alert:
                alerts_created += 1

    if changed_watchlists:
        await db.commit()

    return {"alerts_created": alerts_created, "match_counts": match_counts}


def _watchlist_response(
    watchlist: Watchlist,
    *,
    matched_event_count: int = 0,
    alerts_created: int = 0,
) -> WatchlistResponse:
    return WatchlistResponse(
        id=watchlist.id,
        organization_id=watchlist.organization_id,
        name=watchlist.name,
        keyword=watchlist.keyword,
        country=watchlist.country,
        source=watchlist.source,
        event_type=watchlist.event_type,
        is_active=watchlist.is_active,
        matched_event_count=matched_event_count,
        alerts_created=alerts_created,
        last_matched_at=watchlist.last_matched_at,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


async def list_watchlists(
    organization_id: UUID,
    db: AsyncSession,
) -> list[WatchlistResponse]:
    watchlists = await _load_active_watchlists(organization_id, db)
    events = await _load_official_events(organization_id, db)

    responses: list[WatchlistResponse] = []
    for watchlist in watchlists:
        matched_count = 0
        for event in events:
            matched, _ = match_watchlist(event, watchlist)
            if matched:
                matched_count += 1
        responses.append(_watchlist_response(watchlist, matched_event_count=matched_count))
    return responses


async def create_watchlist(
    organization_id: UUID,
    payload: WatchlistCreate,
    db: AsyncSession,
) -> WatchlistResponse:
    if not any(
        _text(value)
        for value in (payload.keyword, payload.country, payload.source, payload.event_type)
    ):
        raise ValueError("At least one saved filter is required to create a watchlist")

    watchlist = Watchlist(
        organization_id=organization_id,
        name=_text(payload.name) or "Saved Watchlist",
        keyword=_text(payload.keyword) or None,
        country=_text(payload.country) or None,
        source=_text(payload.source) or None,
        event_type=_text(payload.event_type) or None,
        is_active=bool(payload.is_active),
    )
    db.add(watchlist)
    await db.commit()
    await db.refresh(watchlist)

    events = await _load_official_events(organization_id, db)
    matched_events = [event for event in events if match_watchlist(event, watchlist)[0]]
    result = await evaluate_watchlists_for_events(
        organization_id=organization_id,
        events=matched_events,
        db=db,
    )
    if matched_events and not watchlist.last_matched_at:
        watchlist.last_matched_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(watchlist)

    return _watchlist_response(
        watchlist,
        matched_event_count=len(matched_events),
        alerts_created=result["alerts_created"],
    )


async def delete_watchlist(
    watchlist_id: UUID,
    organization_id: UUID,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.organization_id == organization_id,
        )
    )
    watchlist = result.scalar_one_or_none()
    if watchlist is None:
        raise ValueError("Watchlist not found")

    await db.delete(watchlist)
    await db.commit()
