"""
ORVANTA Cloud — Alerts API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.db.database import get_db
from app.core.deps import get_current_org
from app.schemas.alert import AlertResponse, AlertListResponse, AlertAcknowledge
from app.services.alert_service import get_alerts, acknowledge_alert, resolve_alert, dismiss_alert
from app.models.alert import AlertPriority, AlertStatus

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    status: Optional[AlertStatus] = None,
    priority: Optional[AlertPriority] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """List alerts with optional filtering."""
    user, org, membership = org_context
    return await get_alerts(
        organization_id=org.id,
        db=db,
        status_filter=status,
        priority_filter=priority,
        limit=limit,
        offset=offset,
    )


@router.post("/{alert_id}/ack", response_model=AlertResponse)
async def ack_alert(
    alert_id: UUID,
    body: AlertAcknowledge = None,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge an alert."""
    user, org, membership = org_context
    try:
        alert = await acknowledge_alert(alert_id, org.id, user.id, db)
        return AlertResponse.model_validate(alert)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve(
    alert_id: UUID,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Resolve an alert."""
    user, org, membership = org_context
    try:
        alert = await resolve_alert(alert_id, org.id, user.id, db)
        return AlertResponse.model_validate(alert)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{alert_id}/dismiss", response_model=AlertResponse)
async def dismiss(
    alert_id: UUID,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss an alert."""
    user, org, membership = org_context
    try:
        alert = await dismiss_alert(alert_id, org.id, user.id, db)
        return AlertResponse.model_validate(alert)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/clear")
async def clear_all(
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Clear all alerts for an organization."""
    from app.services.alert_service import clear_alerts
    user, org, membership = org_context
    await clear_alerts(org.id, db)
    return {"message": "All alerts cleared successfully"}
