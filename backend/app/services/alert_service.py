"""
ORVANTA Cloud — Alert Service
Alert creation, management, and delivery via WebSocket/email/webhook.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.alert import Alert, AlertPriority, AlertStatus
from app.models.event import Event
from app.models.organization import Organization
from app.schemas.alert import AlertResponse, AlertListResponse
from app.core.logging import get_logger

logger = get_logger(__name__)


def _score_to_priority(score: float) -> AlertPriority:
    """Convert risk score to alert priority."""
    if score >= 75:
        return AlertPriority.CRITICAL
    elif score >= 50:
        return AlertPriority.HIGH
    elif score >= 25:
        return AlertPriority.MEDIUM
    return AlertPriority.LOW


async def create_alert(
    organization_id: UUID,
    title: str,
    message: str,
    priority: AlertPriority,
    db: AsyncSession,
    event_id: Optional[UUID] = None,
    alert_type: str = "risk_threshold",
    meta_data: Optional[dict] = None,
) -> Alert:
    """Create a new alert."""
    alert = Alert(
        organization_id=organization_id,
        event_id=event_id,
        title=title,
        message=message,
        priority=priority,
        alert_type=alert_type,
        meta_data=meta_data,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    logger.info(
        "alert_created",
        alert_id=str(alert.id),
        priority=priority.value,
        org_id=str(organization_id),
    )
    return alert


async def create_risk_alert(
    organization_id: UUID,
    event_title: str,
    risk_score: float,
    risk_level: str,
    event_id: UUID,
    db: AsyncSession,
    recommendations: Optional[str] = None,
) -> Optional[Alert]:
    """Create an alert from a risk score if it exceeds threshold."""
    priority = _score_to_priority(risk_score)

    # Only create alerts for medium+ priority
    if priority == AlertPriority.LOW:
        return None

    existing_result = await db.execute(
        select(Alert).where(
            and_(
                Alert.organization_id == organization_id,
                Alert.event_id == event_id,
                Alert.alert_type == "risk_threshold",
                Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
            )
        )
        .order_by(Alert.created_at.desc())
        .limit(1)
    )
    existing_alert = existing_result.scalar_one_or_none()
    if existing_alert:
        return None

    message = (
        f"Risk score of {risk_score:.1f} ({risk_level}) detected for event: {event_title}. "
    )
    if recommendations:
        message += f"Recommended actions: {recommendations}"

    return await create_alert(
        organization_id=organization_id,
        title=f"⚠️ {risk_level.upper()} Risk: {event_title[:100]}",
        message=message,
        priority=priority,
        db=db,
        event_id=event_id,
        alert_type="risk_threshold",
        meta_data={"risk_score": risk_score, "risk_level": risk_level},
    )


async def get_alerts(
    organization_id: UUID,
    db: AsyncSession,
    status_filter: Optional[AlertStatus] = None,
    priority_filter: Optional[AlertPriority] = None,
    limit: int = 50,
    offset: int = 0,
) -> AlertListResponse:
    """Get alerts for an organization."""
    query = (
        select(Alert)
        .join(Event, Alert.event_id == Event.id)
        .where(
            Alert.organization_id == organization_id,
            Event.organization_id == organization_id,
            Event.is_verified == 1,
        )
    )

    if status_filter:
        query = query.where(Alert.status == status_filter)
    if priority_filter:
        query = query.where(Alert.priority == priority_filter)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Count active
    active_query = select(func.count()).select_from(
        select(Alert.id)
        .join(Event, Alert.event_id == Event.id)
        .where(
            Alert.organization_id == organization_id,
            Event.organization_id == organization_id,
            Event.is_verified == 1,
            Alert.status == AlertStatus.ACTIVE,
        )
        .subquery()
    )
    active_count = (await db.execute(active_query)).scalar()

    # Fetch paginated with Event join
    query = (
        select(Alert, Event.source_url)
        .join(Event, Alert.event_id == Event.id)
        .where(
            Alert.organization_id == organization_id,
            Event.organization_id == organization_id,
            Event.is_verified == 1,
        )
    )

    if status_filter:
        query = query.where(Alert.status == status_filter)
    if priority_filter:
        query = query.where(Alert.priority == priority_filter)

    query = query.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    alert_responses = []
    for alert, source_url in rows:
        resp = AlertResponse.model_validate(alert)
        resp.source_url = source_url
        alert_responses.append(resp)

    return AlertListResponse(
        alerts=alert_responses,
        total=total,
        active_count=active_count,
    )


async def acknowledge_alert(
    alert_id: UUID,
    organization_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Alert:
    """Acknowledge an alert."""
    result = await db.execute(
        select(Alert).where(
            and_(Alert.id == alert_id, Alert.organization_id == organization_id)
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise ValueError("Alert not found")

    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = user_id
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(alert)

    logger.info("alert_acknowledged", alert_id=str(alert_id), user_id=str(user_id))
    return alert


async def resolve_alert(
    alert_id: UUID,
    organization_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Alert:
    """Resolve an alert."""
    result = await db.execute(
        select(Alert).where(
            and_(Alert.id == alert_id, Alert.organization_id == organization_id)
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise ValueError("Alert not found")

    alert.status = AlertStatus.RESOLVED
    await db.commit()
    await db.refresh(alert)

    logger.info("alert_resolved", alert_id=str(alert_id), user_id=str(user_id))
    return alert


async def dismiss_alert(
    alert_id: UUID,
    organization_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Alert:
    """Dismiss an alert."""
    result = await db.execute(
        select(Alert).where(
            and_(Alert.id == alert_id, Alert.organization_id == organization_id)
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise ValueError("Alert not found")

    alert.status = AlertStatus.DISMISSED
    await db.commit()
    await db.refresh(alert)

    logger.info("alert_dismissed", alert_id=str(alert_id), user_id=str(user_id))
    return alert


async def clear_alerts(
    organization_id: UUID,
    db: AsyncSession,
) -> None:
    """Clear all alerts for an organization."""
    from sqlalchemy import delete
    await db.execute(
        delete(Alert).where(Alert.organization_id == organization_id)
    )
    await db.commit()
    logger.info("alerts_cleared", org_id=str(organization_id))
