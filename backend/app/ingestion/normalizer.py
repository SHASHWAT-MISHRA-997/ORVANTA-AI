"""
ORVANTA Cloud — Data Normalizer
Normalizes and deduplicates events from multiple sources into a consistent format.
"""

import hashlib
import html
import re
from typing import List, Dict, Optional
from datetime import datetime, timezone

from app.core.source_trust import classify_source
from app.core.logging import get_logger

logger = get_logger(__name__)


def sanitize_text_value(value: Optional[object], limit: int) -> Optional[str]:
    """Strip HTML and collapse whitespace from stored text fields."""
    if value is None:
        return None

    text = str(value)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:limit]


def normalize_event(raw_event: Dict) -> Dict:
    """Normalize a raw event dictionary into the standard Event model format."""
    valid_types = {
        "conflict", "protest", "disruption", "natural_disaster",
        "political", "economic", "terrorism", "cyber", "other",
    }
    event_type = raw_event.get("event_type", "other")
    if event_type not in valid_types:
        event_type = "other"

    valid_sources = {"gdelt", "acled", "rss", "manual", "agent"}
    source = raw_event.get("source", "manual")
    if source not in valid_sources:
        source = "manual"

    lat = raw_event.get("latitude")
    lon = raw_event.get("longitude")
    if lat is not None:
        lat = max(-90.0, min(90.0, float(lat)))
    if lon is not None:
        lon = max(-180.0, min(180.0, float(lon)))

    severity = raw_event.get("severity", 3)
    severity = max(1, min(10, int(severity)))

    confidence = raw_event.get("confidence", 0.5)
    confidence = max(0.0, min(1.0, float(confidence)))

    credibility = raw_event.get("credibility_score", 0.5)
    credibility = max(0.0, min(1.0, float(credibility)))

    trust = classify_source(source, raw_event.get("source_url"), raw_event.get("raw_data"))
    is_verified = 1 if trust.get("source_status") == "official" else 0

    return {
        "title": sanitize_text_value(raw_event.get("title", "Untitled Event"), 512) or "Untitled Event",
        "description": sanitize_text_value(raw_event.get("description"), 5000),
        "event_type": event_type,
        "source": source,
        "source_url": str(raw_event.get("source_url", ""))[:1024] if raw_event.get("source_url") else None,
        "source_id": str(raw_event.get("source_id", ""))[:255] if raw_event.get("source_id") else None,
        "country": sanitize_text_value(raw_event.get("country"), 100),
        "region": sanitize_text_value(raw_event.get("region"), 255),
        "city": sanitize_text_value(raw_event.get("city"), 255),
        "latitude": lat,
        "longitude": lon,
        "severity": severity,
        "confidence": confidence,
        "credibility_score": credibility,
        "event_date": raw_event.get("event_date"),
        "tags": raw_event.get("tags", [])[:20],
        "actors": raw_event.get("actors", [])[:20],
        "raw_data": raw_event.get("raw_data"),
        "is_verified": is_verified,
    }


def compute_content_hash(event: Dict) -> str:
    """Compute a content hash for deduplication."""
    content = f"{event.get('title', '')}-{event.get('source', '')}-{event.get('country', '')}"
    return hashlib.md5(content.encode()).hexdigest()


def deduplicate_events(events: List[Dict]) -> List[Dict]:
    """Remove duplicate events based on source_id and content similarity."""
    seen_source_ids = set()
    seen_hashes = set()
    unique_events = []

    for event in events:
        source_id = event.get("source_id")
        if source_id and source_id in seen_source_ids:
            continue
        content_hash = compute_content_hash(event)
        if content_hash in seen_hashes:
            continue
        if source_id:
            seen_source_ids.add(source_id)
        seen_hashes.add(content_hash)
        unique_events.append(event)

    duplicates_removed = len(events) - len(unique_events)
    if duplicates_removed > 0:
        logger.info("events_deduplicated", removed=duplicates_removed, remaining=len(unique_events))

    return unique_events


def normalize_and_deduplicate(raw_events: List[Dict]) -> List[Dict]:
    """Full normalization pipeline: normalize → deduplicate."""
    normalized = [normalize_event(e) for e in raw_events]
    return deduplicate_events(normalized)
