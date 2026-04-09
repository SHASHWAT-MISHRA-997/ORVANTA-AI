"""
ORVANTA Cloud — Event Schemas
"""

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.event import EventSource, EventType
from app.schemas.evidence import EvidenceLink


class EventCreate(BaseModel):
    title: str = Field(..., max_length=512)
    description: Optional[str] = None
    event_type: EventType
    source: EventSource = EventSource.MANUAL
    source_url: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    severity: int = Field(1, ge=1, le=10)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    event_date: Optional[datetime] = None
    tags: List[str] = []
    actors: List[str] = []


class EventResponse(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    description: Optional[str]
    event_type: EventType
    source: EventSource
    source_url: Optional[str]
    source_id: Optional[str] = None
    source_domain: Optional[str] = None
    source_status: str = "unverified"
    source_status_reason: Optional[str] = None
    country: Optional[str]
    region: Optional[str]
    city: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    severity: int
    confidence: float
    credibility_score: float
    is_verified: int
    is_duplicate: int
    tags: Any
    actors: Any
    raw_data: Optional[Any] = None
    event_date: Optional[datetime]
    ingested_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    official_source: Optional[EvidenceLink] = None
    supporting_sources: List[EvidenceLink] = Field(default_factory=list)
    video_links: List[EvidenceLink] = Field(default_factory=list)
    search_links: List[EvidenceLink] = Field(default_factory=list)
    detail_available: bool = False
    detail_reason: Optional[str] = None
    detail_missing_fields: List[str] = Field(default_factory=list)
    has_exact_coordinates: bool = False
    location_precision: str = "unknown"

    class Config:
        from_attributes = True


class EventListResponse(BaseModel):
    events: List[EventResponse]
    total: int
    page: int
    page_size: int


class EventFilter(BaseModel):
    event_type: Optional[EventType] = None
    country: Optional[str] = None
    source: Optional[EventSource] = None
    min_severity: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)
