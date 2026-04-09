"""
ORVANTA Cloud — Alert Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from app.models.alert import AlertPriority, AlertStatus


class AlertResponse(BaseModel):
    id: UUID
    organization_id: UUID
    event_id: Optional[UUID]
    title: str
    message: str
    priority: AlertPriority
    status: AlertStatus
    alert_type: str
    meta_data: Optional[Any] = None
    email_sent: bool
    webhook_sent: bool
    websocket_sent: bool
    acknowledged_by: Optional[UUID]
    acknowledged_at: Optional[datetime]
    source_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    alerts: List[AlertResponse]
    total: int
    active_count: int


class AlertAcknowledge(BaseModel):
    note: Optional[str] = None
