"""
ORVANTA Cloud — Organization Management API Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, delete

from app.db.database import get_db
from app.core.deps import get_current_org
from app.models.organization import Organization
from app.models.alert import Alert
from app.models.risk_score import RiskScore
from app.models.event import Event
from app.models.watchlist import Watchlist
from app.schemas.auth import OrgResponse

router = APIRouter(prefix="/organizations", tags=["Organizations"])


async def _restore_default_thresholds(org_id, db: AsyncSession):
    await db.execute(
        update(Organization)
        .where(Organization.id == org_id)
        .values(
            risk_threshold_low="25",
            risk_threshold_medium="50",
            risk_threshold_high="75",
            risk_threshold_critical="90",
        )
    )
    await db.commit()


@router.post("/reset-thresholds", response_model=OrgResponse)
async def reset_alert_thresholds(
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Reset organization risk thresholds to standard system defaults."""
    user, org, membership = org_context

    await _restore_default_thresholds(org.id, db)
    await db.refresh(org)

    return OrgResponse.model_validate(org)


@router.post("/clear-thresholds", response_model=OrgResponse)
async def clear_alert_thresholds(
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Clear custom threshold intent by restoring standard system defaults."""
    user, org, membership = org_context

    await _restore_default_thresholds(org.id, db)
    await db.refresh(org)

    return OrgResponse.model_validate(org)


@router.post("/clear-all-data")
async def clear_all_org_data(
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Hard reset all operational data for the current organization."""
    user, org, membership = org_context

    deleted_alerts = (
        await db.execute(delete(Alert).where(Alert.organization_id == org.id))
    ).rowcount or 0
    deleted_risk_scores = (
        await db.execute(delete(RiskScore).where(RiskScore.organization_id == org.id))
    ).rowcount or 0
    deleted_events = (
        await db.execute(delete(Event).where(Event.organization_id == org.id))
    ).rowcount or 0
    deleted_watchlists = (
        await db.execute(delete(Watchlist).where(Watchlist.organization_id == org.id))
    ).rowcount or 0

    await db.commit()

    return {
        "message": "All organization data cleared successfully",
        "deleted": {
            "alerts": deleted_alerts,
            "risk_scores": deleted_risk_scores,
            "events": deleted_events,
            "watchlists": deleted_watchlists,
        },
    }
