"""
ORVANTA Cloud — Risk Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime


class RiskScoreResponse(BaseModel):
    id: UUID
    event_id: UUID
    organization_id: UUID
    overall_score: float
    severity_component: float
    confidence_component: float
    proximity_component: float
    supply_chain_weight: float
    time_decay_factor: float
    region_weight: float
    risk_level: str
    scoring_breakdown: Optional[Any]
    recommendations: Optional[str]
    computed_at: datetime

    class Config:
        from_attributes = True


class RiskComputeRequest(BaseModel):
    event_ids: Optional[List[UUID]] = None  # If None, compute for all recent events
    reference_lat: Optional[float] = Field(None, ge=-90, le=90)
    reference_lon: Optional[float] = Field(None, ge=-180, le=180)
    supply_chain_weight: float = Field(1.0, ge=0.1, le=5.0)


class RiskScoreListResponse(BaseModel):
    scores: List[RiskScoreResponse]
    total: int
    average_score: float
    critical_count: int
    high_count: int


class RiskTrendPoint(BaseModel):
    date: str
    average_score: Optional[float] = None
    event_count: int = 0
    critical_count: int = 0


class RiskTrendResponse(BaseModel):
    trends: List[RiskTrendPoint]
    period_days: int
    basis: str = "event_timeline"
