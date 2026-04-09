"""
Official-only visibility helpers.

These helpers keep the stored dataset aligned with the UI policy by marking
only official records as verified and hiding everything else from user-facing
queries.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import get_logger
from app.core.source_trust import classify_source
from app.models.event import Event

logger = get_logger(__name__)


async def reclassify_events_official_only(db: AsyncSession) -> int:
    """Mark only official records as verified; hide all others."""
    result = await db.execute(select(Event))
    events = result.scalars().all()

    updated = 0
    for event in events:
        trust = classify_source(event.source, event.source_url, event.raw_data)
        should_verify = trust.get("source_status") == "official"
        next_flag = 1 if should_verify else 0

        if event.is_verified != next_flag:
            event.is_verified = next_flag
            updated += 1

    if updated:
        await db.commit()
        logger.info("official_only_reclassified", updated=updated, scanned=len(events))
    return updated
