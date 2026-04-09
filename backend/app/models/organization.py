"""
ORVANTA Cloud — Organization & Membership Models
"""

import uuid
import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SqlEnum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base
import enum


class OrgRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    api_key = Column(String(64), unique=True, default=lambda: secrets.token_hex(32), index=True)
    is_active = Column(Boolean, default=True)

    # Risk engine config
    risk_threshold_low = Column(String(10), default="25")
    risk_threshold_medium = Column(String(10), default="50")
    risk_threshold_high = Column(String(10), default="75")
    risk_threshold_critical = Column(String(10), default="90")

    # Webhook config
    webhook_url = Column(String(512), nullable=True)
    webhook_enabled = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    members = relationship("OrgMember", back_populates="organization", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="organization", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Organization {self.name}>"


class OrgMember(Base):
    __tablename__ = "org_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(SqlEnum(OrgRole), default=OrgRole.USER, nullable=False)
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="members")

    def __repr__(self):
        return f"<OrgMember user={self.user_id} org={self.organization_id} role={self.role}>"
