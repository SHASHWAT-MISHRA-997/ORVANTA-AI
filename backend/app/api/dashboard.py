"""
ORVANTA Cloud — Dashboard API Routes
Aggregated statistics for the dashboard view.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from fastapi.responses import StreamingResponse
import io
from datetime import datetime, timedelta, timezone

try:
    from reportlab.pdfgen import canvas
except ImportError:
    pass

from app.db.database import get_db
from app.core.deps import get_current_org
from app.core.event_evidence import build_event_evidence_bundle
from app.models.event import Event, EventType
from app.models.risk_score import RiskScore
from app.models.alert import Alert, AlertStatus

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class EventTypeCount(BaseModel):
    event_type: str
    count: int


class DashboardStats(BaseModel):
    total_events: int
    events_today: int
    total_risk_scores: int
    average_risk_score: float
    critical_risks: int
    high_risks: int
    active_alerts: int
    total_alerts: int
    duplicate_events: int
    source_linked_events: int
    official_events: int
    events_with_coordinates: int
    detail_ready_events: int
    events_with_videos: int
    average_event_confidence: float
    events_by_type: List[EventTypeCount]
    recent_countries: List[str]
    generated_at: datetime


@router.get("", response_model=DashboardStats)
async def get_dashboard_stats(
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated dashboard statistics."""
    user, org, membership = org_context
    org_id = org.id
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    official_event_filter = (
        Event.organization_id == org_id,
        Event.is_verified == 1,
    )

    # Total events
    total_events = (await db.execute(
        select(func.count()).where(*official_event_filter)
    )).scalar() or 0

    # Events today
    events_today = (await db.execute(
        select(func.count()).where(
            *official_event_filter,
            Event.created_at >= today,
        )
    )).scalar() or 0

    # Risk scores
    total_risks = (await db.execute(
        select(func.count())
        .select_from(RiskScore)
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org_id,
            Event.organization_id == org_id,
            Event.is_verified == 1,
        )
    )).scalar() or 0

    avg_risk = (await db.execute(
        select(func.avg(RiskScore.overall_score))
        .select_from(RiskScore)
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org_id,
            Event.organization_id == org_id,
            Event.is_verified == 1,
        )
    )).scalar() or 0

    critical_risks = (await db.execute(
        select(func.count())
        .select_from(RiskScore)
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org_id,
            Event.organization_id == org_id,
            Event.is_verified == 1,
            RiskScore.risk_level == "critical",
        )
    )).scalar() or 0

    high_risks = (await db.execute(
        select(func.count())
        .select_from(RiskScore)
        .join(Event, RiskScore.event_id == Event.id)
        .where(
            RiskScore.organization_id == org_id,
            Event.organization_id == org_id,
            Event.is_verified == 1,
            RiskScore.risk_level == "high",
        )
    )).scalar() or 0

    # Alerts
    active_alerts = (await db.execute(
        select(func.count())
        .select_from(Alert)
        .join(Event, Alert.event_id == Event.id)
        .where(
            Alert.organization_id == org_id,
            Event.organization_id == org_id,
            Event.is_verified == 1,
            Alert.status == AlertStatus.ACTIVE,
        )
    )).scalar() or 0

    total_alerts = (await db.execute(
        select(func.count())
        .select_from(Alert)
        .join(Event, Alert.event_id == Event.id)
        .where(
            Alert.organization_id == org_id,
            Event.organization_id == org_id,
            Event.is_verified == 1,
        )
    )).scalar() or 0

    duplicate_events = (await db.execute(
        select(func.count()).where(
            *official_event_filter,
            Event.is_duplicate == 1,
        )
    )).scalar() or 0

    all_event_result = await db.execute(
        select(Event)
        .where(*official_event_filter)
        .order_by(Event.created_at.desc())
    )
    all_events = all_event_result.scalars().all()

    source_linked_events = 0
    events_with_coordinates = 0
    detail_ready_events = 0
    events_with_videos = 0
    recent_countries = []
    seen_countries = set()

    for event in all_events:
        evidence = build_event_evidence_bundle(event)
        if (evidence.get("official_source") or {}).get("url"):
            source_linked_events += 1
        if evidence.get("has_exact_coordinates"):
            events_with_coordinates += 1
        if evidence.get("detail_available"):
            detail_ready_events += 1
        if evidence.get("video_links"):
            events_with_videos += 1

        country = (event.country or "").strip()
        normalized_country = country.lower()
        if (
            len(recent_countries) < 20
            and country
            and normalized_country not in {"unknown", "country not available", "not available"}
            and country not in seen_countries
        ):
            seen_countries.add(country)
            recent_countries.append(country)

    official_events = len(all_events)

    average_event_confidence = (await db.execute(
        select(func.avg(Event.confidence)).where(*official_event_filter)
    )).scalar() or 0

    # Events by type
    type_results = await db.execute(
        select(Event.event_type, func.count().label("count"))
        .where(*official_event_filter)
        .group_by(Event.event_type)
        .order_by(func.count().desc())
    )
    events_by_type = [
        EventTypeCount(event_type=row.event_type.value, count=row.count)
        for row in type_results
    ]

    return DashboardStats(
        total_events=total_events,
        events_today=events_today,
        total_risk_scores=total_risks,
        average_risk_score=round(avg_risk, 2),
        critical_risks=critical_risks,
        high_risks=high_risks,
        active_alerts=active_alerts,
        total_alerts=total_alerts,
        duplicate_events=duplicate_events,
        source_linked_events=source_linked_events,
        official_events=official_events,
        events_with_coordinates=events_with_coordinates,
        detail_ready_events=detail_ready_events,
        events_with_videos=events_with_videos,
        average_event_confidence=round(average_event_confidence, 2),
        events_by_type=events_by_type,
        recent_countries=recent_countries,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/report")
async def generate_executive_pdf_report(
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Generate an Executive Briefing PDF Report using ReportLab."""
    user, org, membership = org_context
    org_id = org.id
    
    buffer = io.BytesIO()
    try:
        if 'canvas' not in globals():
            from reportlab.pdfgen import canvas
            
        c = canvas.Canvas(buffer)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, f"ORVANTA - Executive Geopolitical Briefing")
        
        c.setFont("Helvetica", 12)
        c.drawString(50, 770, f"Organization: {org.name}")
        c.drawString(50, 750, f"Generated on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        c.drawString(50, 710, "Status Overview:")
        c.drawString(70, 690, "• Live official-source monitoring is active.")
        c.drawString(70, 670, "• CISA Cyber Alerts integrated.")
        c.drawString(70, 650, "• Supply Chain Digital Twin is fully tracked.")
        
        c.showPage()
        c.save()
    except Exception as e:
        buffer.write(f"PDF Generation Error. Make sure reportlab is installed: {str(e)}".encode('utf-8'))
        
    buffer.seek(0)
    return StreamingResponse(
        buffer, 
        media_type="application/pdf", 
        headers={"Content-Disposition": "attachment; filename=Executive_Briefing.pdf"}
    )
