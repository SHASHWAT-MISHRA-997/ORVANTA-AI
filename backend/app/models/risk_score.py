"""
ORVANTA Cloud — Risk Score Model
Stores computed risk scores for events with full scoring breakdown.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.database import Base


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Computed scores
    overall_score = Column(Float, nullable=False)  # 0-100 final score
    severity_component = Column(Float, nullable=False)
    confidence_component = Column(Float, nullable=False)
    proximity_component = Column(Float, nullable=False)
    supply_chain_weight = Column(Float, default=1.0)
    time_decay_factor = Column(Float, default=1.0)
    region_weight = Column(Float, default=1.0)

    # Classification
    risk_level = Column(String(20), nullable=False)  # low, medium, high, critical

    # Breakdown for transparency
    scoring_breakdown = Column(JSONB, nullable=True)  # Full computation details
    recommendations = Column(Text, nullable=True)  # AI-generated recommendations

    computed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    event = relationship("Event", back_populates="risk_scores")

    def __repr__(self):
        return f"<RiskScore event={self.event_id} score={self.overall_score}>"
