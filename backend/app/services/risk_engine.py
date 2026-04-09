"""
ORVANTA Cloud — Risk Engine
Core risk scoring algorithm with configurable weights and time decay.

Risk Score = (Severity × Confidence × Proximity) × Supply Chain Weight × Time Decay × Region Weight

All scores are normalized to 0-100 range.
"""

import math
from datetime import datetime, timezone
from typing import Optional, Dict, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from geopy.distance import geodesic

from app.models.event import Event
from app.models.risk_score import RiskScore
from app.models.organization import Organization
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Region Weights ──
# Higher weight = more strategically important regions
REGION_WEIGHTS = {
    "Middle East": 1.5,
    "Eastern Europe": 1.4,
    "East Africa": 1.3,
    "South Asia": 1.3,
    "Southeast Asia": 1.2,
    "Central Asia": 1.2,
    "West Africa": 1.2,
    "North Africa": 1.1,
    "East Asia": 1.1,
    "South America": 1.0,
    "Central America": 1.0,
    "Western Europe": 0.8,
    "North America": 0.7,
    "Oceania": 0.6,
}

# ── Event Severity Mapping ──
EVENT_TYPE_SEVERITY = {
    "conflict": 9,
    "terrorism": 10,
    "protest": 5,
    "disruption": 6,
    "natural_disaster": 7,
    "political": 4,
    "economic": 5,
    "cyber": 7,
    "other": 3,
}

# ── Supply chain chokepoints (lat, lon, weight) ──
SUPPLY_CHAIN_CHOKEPOINTS = [
    {"name": "Strait of Hormuz", "lat": 26.57, "lon": 56.25, "weight": 2.0},
    {"name": "Suez Canal", "lat": 30.58, "lon": 32.27, "weight": 2.0},
    {"name": "Strait of Malacca", "lat": 2.5, "lon": 101.8, "weight": 1.8},
    {"name": "Bab el-Mandeb", "lat": 12.6, "lon": 43.3, "weight": 1.7},
    {"name": "Panama Canal", "lat": 9.08, "lon": -79.68, "weight": 1.6},
    {"name": "Turkish Straits", "lat": 41.0, "lon": 29.0, "weight": 1.5},
    {"name": "Cape of Good Hope", "lat": -34.35, "lon": 18.5, "weight": 1.3},
    {"name": "Taiwan Strait", "lat": 24.0, "lon": 119.5, "weight": 1.8},
]


def compute_time_decay(event_date: datetime, half_life_days: float = 7.0) -> float:
    """
    Exponential time decay function.
    Events lose half their weight every `half_life_days` days.
    Returns value between 0.0 and 1.0.
    """
    if not event_date:
        return 0.5

    now = datetime.now(timezone.utc)
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)

    age_days = (now - event_date).total_seconds() / 86400.0
    if age_days < 0:
        age_days = 0

    decay = math.exp(-0.693 * age_days / half_life_days)  # ln(2) ≈ 0.693
    return max(0.01, min(1.0, decay))


def compute_proximity_score(
    event_lat: Optional[float],
    event_lon: Optional[float],
    ref_lat: Optional[float] = None,
    ref_lon: Optional[float] = None,
    max_distance_km: float = 5000.0,
) -> float:
    """
    Compute proximity factor based on distance to a reference point.
    When no reference point is supplied, treat the score as global monitoring and
    keep proximity neutral so global events are not incorrectly suppressed.
    Closer events get higher scores. Returns 0.0-1.0.
    """
    if event_lat is None or event_lon is None:
        return 0.5  # Default for events without location

    event_point = (event_lat, event_lon)

    # If reference point provided, use it
    if ref_lat is not None and ref_lon is not None:
        ref_point = (ref_lat, ref_lon)
        distance = geodesic(event_point, ref_point).kilometers
        return max(0.1, 1.0 - (distance / max_distance_km))

    return 1.0


def get_region_weight(country: Optional[str], region: Optional[str]) -> float:
    """Get region weight for geopolitical significance."""
    if region and region in REGION_WEIGHTS:
        return REGION_WEIGHTS[region]
    # Default weight
    return 1.0


def get_supply_chain_weight(
    event_lat: Optional[float],
    event_lon: Optional[float],
    base_weight: float = 1.0,
    threshold_km: float = 500.0,
) -> float:
    """
    Compute supply chain dependency weight.
    Events near chokepoints get multiplied weight.
    """
    if event_lat is None or event_lon is None:
        return base_weight

    event_point = (event_lat, event_lon)
    max_extra_weight = 0.0

    for cp in SUPPLY_CHAIN_CHOKEPOINTS:
        cp_point = (cp["lat"], cp["lon"])
        distance = geodesic(event_point, cp_point).kilometers
        if distance < threshold_km:
            proximity_factor = 1.0 - (distance / threshold_km)
            extra_weight = (cp["weight"] - 1.0) * proximity_factor
            max_extra_weight = max(max_extra_weight, extra_weight)

    return base_weight + max_extra_weight


def compute_risk_score(
    event: Event,
    ref_lat: Optional[float] = None,
    ref_lon: Optional[float] = None,
    custom_supply_weight: float = 1.0,
) -> Dict:
    """
    Compute comprehensive risk score for an event.
    Returns dict with all scoring components and the final normalized score.
    """
    # ── Component 1: Severity (1-10 normalized to 0-1) ──
    base_severity = EVENT_TYPE_SEVERITY.get(event.event_type.value, 5)
    severity = max(event.severity, base_severity) / 10.0

    # ── Component 2: Confidence (already 0-1) ──
    confidence = event.confidence

    # ── Component 3: Proximity (0-1) ──
    proximity = compute_proximity_score(
        event.latitude, event.longitude, ref_lat, ref_lon
    )

    # ── Component 4: Time Decay (0-1) ──
    time_decay = compute_time_decay(event.event_date)

    # ── Component 5: Region Weight (0.5-2.0) ──
    region_wt = get_region_weight(event.country, event.region)

    # ── Component 6: Supply Chain Weight (1.0-3.0) ──
    supply_wt = get_supply_chain_weight(
        event.latitude, event.longitude, custom_supply_weight
    )

    # ── Final Score ──
    # Base score from core factors (0-1)
    base_score = severity * confidence * proximity

    # Apply weights and decay
    weighted_score = base_score * supply_wt * time_decay * region_wt

    # Normalize to 0-100
    final_score = min(100.0, weighted_score * 100.0)

    # Determine risk level
    if final_score >= 75:
        risk_level = "critical"
    elif final_score >= 50:
        risk_level = "high"
    elif final_score >= 25:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "overall_score": round(final_score, 2),
        "severity_component": round(severity, 4),
        "confidence_component": round(confidence, 4),
        "proximity_component": round(proximity, 4),
        "supply_chain_weight": round(supply_wt, 4),
        "time_decay_factor": round(time_decay, 4),
        "region_weight": round(region_wt, 4),
        "risk_level": risk_level,
        "scoring_breakdown": {
            "base_score": round(base_score, 4),
            "weighted_score": round(weighted_score, 4),
            "event_type": event.event_type.value,
            "event_severity": event.severity,
            "type_base_severity": base_severity,
        },
    }


async def compute_and_store_risk_scores(
    organization_id: UUID,
    db: AsyncSession,
    event_ids: Optional[List[UUID]] = None,
    ref_lat: Optional[float] = None,
    ref_lon: Optional[float] = None,
    supply_chain_weight: float = 1.0,
) -> List[RiskScore]:
    """Compute risk scores for events and store in database."""

    # Query events
    query = select(Event).where(
        Event.organization_id == organization_id,
        Event.is_verified == 1,
    )
    if event_ids:
        query = query.where(Event.id.in_(event_ids))
    else:
        # Default: process unscored recent events
        query = query.where(Event.is_duplicate == 0).order_by(Event.created_at.desc()).limit(100)

    result = await db.execute(query)
    events = result.scalars().all()

    scores = []
    for event in events:
        risk_score, _ = await upsert_risk_score(
            event=event,
            organization_id=organization_id,
            db=db,
            ref_lat=ref_lat,
            ref_lon=ref_lon,
            supply_chain_weight=supply_chain_weight,
        )
        scores.append(risk_score)

    if scores:
        await db.commit()
        for s in scores:
            await db.refresh(s)
        logger.info(
            "risk_scores_computed",
            count=len(scores),
            org_id=str(organization_id),
        )

    return scores


async def upsert_risk_score(
    event: Event,
    organization_id: UUID,
    db: AsyncSession,
    ref_lat: Optional[float] = None,
    ref_lon: Optional[float] = None,
    supply_chain_weight: float = 1.0,
) -> tuple[RiskScore, bool]:
    """Create or update the latest risk score row for an event."""
    score_data = compute_risk_score(event, ref_lat, ref_lon, supply_chain_weight)
    result = await db.execute(
        select(RiskScore)
        .where(
            RiskScore.organization_id == organization_id,
            RiskScore.event_id == event.id,
        )
        .order_by(RiskScore.computed_at.desc())
        .limit(1)
    )
    risk_score = result.scalar_one_or_none()
    created = False

    fields = {k: v for k, v in score_data.items() if k != "scoring_breakdown"}
    if risk_score is None:
        risk_score = RiskScore(
            event_id=event.id,
            organization_id=organization_id,
            **fields,
            scoring_breakdown=score_data["scoring_breakdown"],
        )
        db.add(risk_score)
        created = True
    else:
        for field_name, field_value in fields.items():
            setattr(risk_score, field_name, field_value)
        risk_score.scoring_breakdown = score_data["scoring_breakdown"]
        risk_score.computed_at = datetime.now(timezone.utc)

    return risk_score, created
