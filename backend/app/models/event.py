"""
ORVANTA Cloud — Event Model
Represents geopolitical/conflict events ingested from external sources.
"""

import uuid
from datetime import datetime, timezone
from functools import cached_property
from sqlalchemy import (
    Column, String, Float, DateTime, Text, Integer,
    ForeignKey, Enum as SqlEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.event_evidence import build_event_evidence_bundle
from app.db.database import Base
from app.core.source_trust import classify_source
import enum


class EventType(str, enum.Enum):
    CONFLICT = "conflict"
    PROTEST = "protest"
    DISRUPTION = "disruption"
    NATURAL_DISASTER = "natural_disaster"
    POLITICAL = "political"
    ECONOMIC = "economic"
    TERRORISM = "terrorism"
    CYBER = "cyber"
    OTHER = "other"


class EventSource(str, enum.Enum):
    GDELT = "gdelt"
    ACLED = "acled"
    RSS = "rss"
    MANUAL = "manual"
    AGENT = "agent"


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Core event data
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(SqlEnum(EventType), nullable=False, index=True)
    source = Column(SqlEnum(EventSource), nullable=False)
    source_url = Column(String(1024), nullable=True)
    source_id = Column(String(255), nullable=True, index=True)  # External source ID for dedup

    # Geolocation
    country = Column(String(100), nullable=True, index=True)
    region = Column(String(255), nullable=True)
    city = Column(String(255), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Scoring
    severity = Column(Integer, default=1)  # 1-10
    confidence = Column(Float, default=0.5)  # 0.0 - 1.0
    credibility_score = Column(Float, default=0.5)  # 0.0 - 1.0

    # Metadata
    raw_data = Column(JSONB, nullable=True)  # Original source data
    tags = Column(JSONB, default=list)  # List of tags
    actors = Column(JSONB, default=list)  # Involved actors/entities

    event_date = Column(DateTime(timezone=True), nullable=True)
    ingested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_verified = Column(Integer, default=0)  # 0=unverified, 1=verified, -1=rejected
    is_duplicate = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization = relationship("Organization", back_populates="events")
    risk_scores = relationship("RiskScore", back_populates="event", cascade="all, delete-orphan")

    # Indexes for common queries
    __table_args__ = (
        Index("ix_events_org_type", "organization_id", "event_type"),
        Index("ix_events_org_date", "organization_id", "event_date"),
        Index("ix_events_geo", "latitude", "longitude"),
    )

    def __repr__(self):
        return f"<Event {self.title[:50]}>"

    @property
    def source_domain(self):
        return classify_source(self.source, self.source_url, self.raw_data).get("source_domain")

    @property
    def source_status(self):
        return classify_source(self.source, self.source_url, self.raw_data).get("source_status")

    @property
    def source_status_reason(self):
        return classify_source(self.source, self.source_url, self.raw_data).get("source_status_reason")

    @cached_property
    def _evidence_bundle(self):
        return build_event_evidence_bundle(self)

    @property
    def official_source(self):
        return self._evidence_bundle.get("official_source")

    @property
    def supporting_sources(self):
        return self._evidence_bundle.get("supporting_sources", [])

    @property
    def video_links(self):
        return self._evidence_bundle.get("video_links", [])

    @property
    def search_links(self):
        return self._evidence_bundle.get("search_links", [])

    @property
    def detail_available(self):
        return bool(self._evidence_bundle.get("detail_available"))

    @property
    def detail_reason(self):
        return self._evidence_bundle.get("detail_reason")

    @property
    def detail_missing_fields(self):
        return self._evidence_bundle.get("detail_missing_fields", [])

    @property
    def has_exact_coordinates(self):
        return bool(self._evidence_bundle.get("has_exact_coordinates"))

    @property
    def location_precision(self):
        return self._evidence_bundle.get("location_precision", "unknown")
