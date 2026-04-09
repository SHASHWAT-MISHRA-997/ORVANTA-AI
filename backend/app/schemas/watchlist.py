"""
ORVANTA Cloud - Watchlist Schemas
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    name: str = Field(..., max_length=255)
    keyword: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=100)
    source: Optional[str] = Field(None, max_length=255)
    event_type: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class WatchlistResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    keyword: Optional[str] = None
    country: Optional[str] = None
    source: Optional[str] = None
    event_type: Optional[str] = None
    is_active: bool
    matched_event_count: int = 0
    alerts_created: int = 0
    last_matched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
