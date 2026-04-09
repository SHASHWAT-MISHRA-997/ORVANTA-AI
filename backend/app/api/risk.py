"""
ORVANTA Cloud — Risk Score API Routes
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.db.database import get_db
from app.core.deps import get_current_org
from app.schemas.risk import (
    RiskScoreResponse, RiskComputeRequest, RiskScoreListResponse,
    RiskTrendPoint, RiskTrendResponse,
)
from app.services.risk_engine import compute_and_store_risk_scores
from app.models.risk_score import RiskScore
from app.models.event import Event

router = APIRouter(prefix="/risk-score", tags=["Risk Scores"])


@router.get("", response_model=RiskScoreListResponse)
async def list_risk_scores(
    risk_level: Optional[str] = None,
    min_score: Optional[float] = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """List risk scores with optional filtering."""
    user, org, membership = org_context

    query = (
        select(RiskScore)
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org.id,
            Event.organization_id == org.id,
            Event.is_verified == 1,
        )
    )
    if risk_level:
        query = query.where(RiskScore.risk_level == risk_level)
    if min_score is not None:
        query = query.where(RiskScore.overall_score >= min_score)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    critical = (await db.execute(
        select(func.count())
        .select_from(RiskScore)
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org.id,
            Event.organization_id == org.id,
            Event.is_verified == 1,
            RiskScore.risk_level == "critical",
        )
    )).scalar()
    high = (await db.execute(
        select(func.count())
        .select_from(RiskScore)
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org.id,
            Event.organization_id == org.id,
            Event.is_verified == 1,
            RiskScore.risk_level == "high",
        )
    )).scalar()

    avg = (await db.execute(
        select(func.avg(RiskScore.overall_score))
        .select_from(RiskScore)
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org.id,
            Event.organization_id == org.id,
            Event.is_verified == 1,
        )
    )).scalar() or 0

    query = query.order_by(RiskScore.computed_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    scores = result.scalars().all()

    return RiskScoreListResponse(
        scores=[RiskScoreResponse.model_validate(s) for s in scores],
        total=total,
        average_score=round(avg, 2),
        critical_count=critical,
        high_count=high,
    )


@router.post("/compute", response_model=list[RiskScoreResponse])
async def compute_risks(
    request: RiskComputeRequest,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Trigger risk score computation for events."""
    user, org, membership = org_context
    scores = await compute_and_store_risk_scores(
        organization_id=org.id,
        db=db,
        event_ids=request.event_ids,
        ref_lat=request.reference_lat,
        ref_lon=request.reference_lon,
        supply_chain_weight=request.supply_chain_weight,
    )
    return [RiskScoreResponse.model_validate(s) for s in scores]


@router.get("/trends", response_model=RiskTrendResponse)
async def get_risk_trends(
    days: int = Query(30, ge=1, le=365),
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Get risk score trends over time."""
    user, org, membership = org_context
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    from sqlalchemy import cast, Date
    timeline_expr = func.coalesce(Event.event_date, Event.created_at)
    timeline_date_expr = cast(timeline_expr, Date)
    results = await db.execute(
        select(
            timeline_date_expr.label("date"),
            func.avg(RiskScore.overall_score).label("avg_score"),
            func.count(RiskScore.id).label("event_count"),
            func.count().filter(RiskScore.risk_level == "critical").label("critical_count"),
        )
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org.id,
            Event.organization_id == org.id,
            Event.is_verified == 1,
            timeline_expr >= start_date,
        )
        .group_by(timeline_date_expr)
        .order_by(timeline_date_expr)
    )

    trend_rows = {
        str(row.date): RiskTrendPoint(
            date=str(row.date),
            average_score=round(float(row.avg_score), 2) if row.avg_score is not None else None,
            event_count=int(row.event_count or 0),
            critical_count=int(row.critical_count or 0),
        )
        for row in results
    }

    end_date = datetime.now(timezone.utc).date()
    cursor = start_date.date()
    trends: list[RiskTrendPoint] = []
    while cursor <= end_date:
        key = cursor.isoformat()
        trends.append(
            trend_rows.get(
                key,
                RiskTrendPoint(
                    date=key,
                    average_score=None,
                    event_count=0,
                    critical_count=0,
                ),
            )
        )
        cursor += timedelta(days=1)

    return RiskTrendResponse(trends=trends, period_days=days, basis="event_timeline")
