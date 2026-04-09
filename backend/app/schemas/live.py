"""
ORVANTA Cloud - Live sync schemas
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LiveSyncRequest(BaseModel):
    force: bool = False


class LiveSyncResponse(BaseModel):
    status: str
    message: str
    fetched: int
    normalized: int
    stored: int
    duplicates_skipped: int
    scored_events: int
    updated_scores: int
    alerts_created: int
    watchlist_alerts_created: int = 0
    exact_coordinate_events: int
    latest_ingested_at: Optional[datetime] = None
    synced_at: datetime
