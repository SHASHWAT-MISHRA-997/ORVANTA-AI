"""
ORVANTA Cloud — Alert Model
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.database import Base
import enum


class AlertPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )

    title = Column(String(512), nullable=False)
    message = Column(Text, nullable=False)
    priority = Column(SqlEnum(AlertPriority), nullable=False, index=True)
    status = Column(SqlEnum(AlertStatus), default=AlertStatus.ACTIVE, index=True)

    # Alert metadata
    alert_type = Column(String(100), default="risk_threshold")
    meta_data = Column(JSONB, nullable=True)

    # Delivery tracking
    email_sent = Column(Boolean, default=False)
    webhook_sent = Column(Boolean, default=False)
    websocket_sent = Column(Boolean, default=False)

    acknowledged_by = Column(UUID(as_uuid=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    organization = relationship("Organization", back_populates="alerts")

    def __repr__(self):
        return f"<Alert {self.title[:50]} priority={self.priority}>"
