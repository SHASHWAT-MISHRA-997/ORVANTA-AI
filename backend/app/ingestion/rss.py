"""
ORVANTA Cloud — RSS Feed Ingestion
Fetches and parses RSS/Atom feeds from conflict and geopolitical news sources.
"""

import feedparser
import httpx
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from email.utils import parsedate_to_datetime

from app.core.config import settings
from app.core.source_trust import OFFICIAL_FEEDS
from app.core.logging import get_logger

logger = get_logger(__name__)

# Curated list of conflict/geopolitical RSS feeds
DEFAULT_FEEDS = [
    {"name": "ReliefWeb Updates", "url": "https://reliefweb.int/updates/rss.xml", "credibility": 0.85, "kind": "rss"},
    {"name": "UN News - Peace and Security", "url": "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml", "credibility": 0.9, "kind": "rss"},
    {"name": "SIPRI News", "url": "https://www.sipri.org/rss.xml", "credibility": 0.9, "kind": "rss"},
    {"name": "Crisis Group", "url": "https://www.crisisgroup.org/rss.xml", "credibility": 0.88, "kind": "rss"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "credibility": 0.7, "kind": "rss"},
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "credibility": 0.8, "kind": "rss"},
    {"name": "Reuters World", "url": "https://www.reutersagency.com/feed/", "credibility": 0.85, "kind": "rss"},
    {"name": "CISA Cyber Alerts", "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml", "credibility": 1.0, "kind": "rss"},
    {
        "name": "USGS Significant Earthquakes",
        "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.geojson",
        "credibility": 1.0,
        "kind": "geojson",
    },
    {
        "name": "USGS M4.5+ Earthquakes",
        "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson",
        "credibility": 1.0,
        "kind": "geojson",
    },
]

# Keywords for relevance filtering
RELEVANCE_KEYWORDS = [
    "conflict", "war", "military", "attack", "bombing", "protest",
    "crisis", "sanctions", "terrorism", "insurgency", "ceasefire",
    "displacement", "refugees", "humanitarian", "violence", "troops",
    "coup", "uprising", "blockade", "missile", "drone", "airstrike",
    "explosion", "clash", "rebel", "militia", "peacekeeping",
    "nuclear", "chemical", "cyber attack", "embargo", "genocide",
    "cyber", "ransomware", "vulnerability", "cve", "hack", "exploit",
]


def _is_relevant(title: str, summary: str = "") -> bool:
    """Check if an article is relevant to conflict/geopolitical monitoring."""
    text = f"{title} {summary}".lower()
    return any(keyword in text for keyword in RELEVANCE_KEYWORDS)


def _classify_from_text(title: str, summary: str = "") -> str:
    """Classify event type from article text."""
    text = f"{title} {summary}".lower()
    if any(w in text for w in ["terror", "bombing", "suicide", "isis", "al-qaeda", "explosive"]):
        return "terrorism"
    elif any(w in text for w in ["war", "military", "troops", "battle", "airstrike", "missile"]):
        return "conflict"
    elif any(w in text for w in ["protest", "demonstrat", "rally", "march", "uprising"]):
        return "protest"
    elif any(w in text for w in ["earthquake", "hurricane", "flood", "tsunami", "cyclone"]):
        return "natural_disaster"
    elif any(w in text for w in ["cyber", "hack", "data breach", "ransomware"]):
        return "cyber"
    elif any(w in text for w in ["sanction", "embargo", "trade", "economic"]):
        return "economic"
    elif any(w in text for w in ["election", "coup", "political", "government", "diplomacy"]):
        return "political"
    elif any(w in text for w in ["disrupt", "supply chain", "shortage", "blockade"]):
        return "disruption"
    return "other"


def _estimate_severity(title: str, summary: str = "") -> int:
    """Estimate event severity from text (1-10)."""
    text = f"{title} {summary}".lower()
    severity = 3
    high_severity = ["killed", "dead", "massacre", "genocide", "nuclear", "war"]
    mid_severity = ["attack", "bombing", "explosion", "clash", "troops", "missile"]
    low_severity = ["protest", "sanctions", "diplomatic", "talks", "ceasefire"]
    if any(w in text for w in high_severity):
        severity = max(severity, 8)
    elif any(w in text for w in mid_severity):
        severity = max(severity, 6)
    elif any(w in text for w in low_severity):
        severity = max(severity, 4)
    return min(10, severity)


def _parse_date(entry) -> Optional[datetime]:
    """Parse date from feed entry."""
    date_str = entry.get("published") or entry.get("updated")
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_entry_coordinates(entry: Any) -> tuple[Optional[float], Optional[float]]:
    lat = _safe_float(entry.get("geo_lat") or entry.get("lat") or entry.get("latitude"))
    lon = _safe_float(
        entry.get("geo_long")
        or entry.get("geo_lon")
        or entry.get("long")
        or entry.get("lon")
        or entry.get("longitude")
    )
    if lat is not None and lon is not None:
        return lat, lon

    georss_point = entry.get("georss_point") or entry.get("point")
    if isinstance(georss_point, str):
        parts = [part.strip() for part in georss_point.replace(",", " ").split() if part.strip()]
        if len(parts) >= 2:
            parsed_lat = _safe_float(parts[0])
            parsed_lon = _safe_float(parts[1])
            if parsed_lat is not None and parsed_lon is not None:
                return parsed_lat, parsed_lon

    where = entry.get("where")
    if isinstance(where, dict):
        parsed_lat = _safe_float(where.get("lat"))
        parsed_lon = _safe_float(where.get("lon") or where.get("lng") or where.get("long"))
        if parsed_lat is not None and parsed_lon is not None:
            return parsed_lat, parsed_lon

    return None, None


def _extract_place_segments(place: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    text = (place or "").strip()
    if not text:
        return None, None, None

    location_text = text.split(" of ", 1)[-1].strip()
    segments = [segment.strip() for segment in location_text.split(",") if segment.strip()]
    if not segments:
        return text, None, None

    if len(segments) == 1:
        return segments[0], None, None

    city = segments[0]
    country = segments[-1]
    region = ", ".join(segments[1:-1]) or None
    return city, region, country


def _magnitude_to_severity(magnitude: float) -> int:
    if magnitude >= 8.0:
        return 10
    if magnitude >= 7.0:
        return 9
    if magnitude >= 6.0:
        return 8
    if magnitude >= 5.0:
        return 7
    if magnitude >= 4.0:
        return 6
    if magnitude >= 3.0:
        return 5
    return 4


async def _fetch_geojson_feed(feed_config: Dict, max_per_feed: int) -> List[Dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            feed_config["url"],
            headers={
                "User-Agent": "ORVANTA-Cloud/1.0 (+https://orvanta.local/live-sync)",
                "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.8",
            },
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()

    features = payload.get("features", [])[:max_per_feed]
    events: List[Dict] = []

    for feature in features:
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        magnitude = _safe_float(properties.get("mag")) or 0.0
        place = str(properties.get("place") or "").strip()
        city, region, country = _extract_place_segments(place)

        event_time_ms = properties.get("time")
        updated_time_ms = properties.get("updated")
        event_date = None
        updated_at = None
        if isinstance(event_time_ms, (int, float)):
            event_date = datetime.fromtimestamp(event_time_ms / 1000.0, tz=timezone.utc)
        if isinstance(updated_time_ms, (int, float)):
            updated_at = datetime.fromtimestamp(updated_time_ms / 1000.0, tz=timezone.utc)

        longitude = _safe_float(coordinates[0]) if len(coordinates) > 0 else None
        latitude = _safe_float(coordinates[1]) if len(coordinates) > 1 else None
        if latitude is None or longitude is None:
            continue

        severity = _magnitude_to_severity(magnitude)
        title = str(properties.get("title") or f"USGS Earthquake: {place or 'Unknown location'}").strip()

        events.append({
            "title": title[:512],
            "description": properties.get("title") or place or "USGS earthquake event",
            "event_type": "natural_disaster",
            "source": "rss",
            "source_url": properties.get("url") or properties.get("detail") or feed_config["url"],
            "source_id": f"usgs-{feature.get('id') or properties.get('code') or title[:120]}",
            "country": country,
            "region": region,
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "severity": severity,
            "confidence": 0.95,
            "credibility_score": feed_config.get("credibility", 1.0),
            "event_date": event_date,
            "tags": [value for value in [
                "earthquake",
                feed_config["name"],
                f"magnitude_{magnitude:.1f}" if magnitude else None,
                "tsunami" if properties.get("tsunami") else None,
            ] if value][:10],
            "raw_data": {
                "source": "rss",
                "feed": feed_config["name"],
                "feed_url": feed_config["url"],
                "published_at": event_date.isoformat() if event_date else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "entry_link": properties.get("url") or None,
                "place": place or None,
                "magnitude": magnitude,
                "felt_reports": properties.get("felt"),
                "tsunami": properties.get("tsunami"),
                "source_time_kind": "observed",
                "coordinates": coordinates[:3],
            },
        })

    logger.info("geojson_feed_parsed", feed=feed_config["name"], entries_found=len(events))
    return events


async def fetch_rss_events(
    feeds: List[Dict] = None,
    max_per_feed: int = 10,
) -> List[Dict]:
    """Fetch and parse events from RSS feeds."""
    feeds = feeds or DEFAULT_FEEDS
    if settings.OFFICIAL_ONLY_MODE:
        feeds = [
            feed for feed in feeds
            if str(feed.get("name", "")).strip().lower() in OFFICIAL_FEEDS
        ]
        if not feeds:
            logger.info("rss_official_only_no_feeds")
            return []
    all_events = []

    for feed_config in feeds:
        try:
            if str(feed_config.get("kind", "rss")).lower() == "geojson":
                all_events.extend(await _fetch_geojson_feed(feed_config, max_per_feed))
                continue

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    feed_config["url"],
                    headers={
                        "User-Agent": "ORVANTA-Cloud/1.0 (+https://orvanta.local/live-sync)",
                        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
                    },
                    follow_redirects=True,
                )
                response.raise_for_status()
                content = response.text

            parsed = feedparser.parse(content)
            entries = parsed.entries[:max_per_feed]

            for entry in entries:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()

                if not title or not _is_relevant(title, summary):
                    continue

                event_type = _classify_from_text(title, summary)
                severity = _estimate_severity(title, summary)
                latitude, longitude = _parse_entry_coordinates(entry)

                event = {
                    "title": title[:512],
                    "description": summary[:2000] if summary else None,
                    "event_type": event_type,
                    "source": "rss",
                    "source_url": entry.get("link") or None,
                    "source_id": f"rss-{feed_config['name']}-{entry.get('id', entry.get('link', '')[:100])}",
                    "country": None,
                    "latitude": latitude,
                    "longitude": longitude,
                    "severity": severity,
                    "confidence": 0.5,
                    "credibility_score": feed_config.get("credibility", 0.6),
                    "event_date": _parse_date(entry),
                    "tags": [tag.get("term", "") for tag in entry.get("tags", [])][:10],
                    "raw_data": {
                        "source": "rss",
                        "feed": feed_config["name"],
                        "feed_url": feed_config["url"],
                        "author": entry.get("author"),
                        "published_at": entry.get("published"),
                        "updated_at": entry.get("updated"),
                        "entry_link": entry.get("link") or None,
                        "georss_point": entry.get("georss_point"),
                        "geo_lat": latitude,
                        "geo_lon": longitude,
                    },
                }
                all_events.append(event)

            logger.info("rss_feed_parsed", feed=feed_config["name"], entries_found=len(entries))

        except Exception as e:
            logger.warning("rss_feed_error", feed=feed_config["name"], error=str(e))
            continue

    logger.info("rss_total_fetched", count=len(all_events))
    return all_events
