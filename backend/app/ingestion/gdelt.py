"""
ORVANTA Cloud — GDELT Data Ingestion
Fetches geopolitical events from the GDELT Project API.
GDELT updates every 15 minutes with global event data.
"""

import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_GEO_API = "https://api.gdeltproject.org/api/v2/geo/geo"

# GDELT conflict-related themes
CONFLICT_THEMES = [
    "CONFLICT", "PROTEST", "TERROR", "MILITARY",
    "ARMED_CONFLICT", "REBELLION", "WAR", "VIOLENCE",
    "SANCTIONS", "COUP", "BLOCKADE", "CRISIS",
]


# Severity mapping for GDELT tone scores
def _tone_to_severity(avg_tone: float) -> int:
    """Convert GDELT average tone to severity (1-10). More negative = more severe."""
    if avg_tone <= -8:
        return 10
    elif avg_tone <= -6:
        return 8
    elif avg_tone <= -4:
        return 7
    elif avg_tone <= -2:
        return 5
    elif avg_tone <= 0:
        return 4
    elif avg_tone <= 2:
        return 3
    return 2


def _classify_event_type(title: str, themes: List[str] = None) -> str:
    """Classify event type from title and themes."""
    title_lower = title.lower()
    themes_str = " ".join(themes or []).lower()
    combined = f"{title_lower} {themes_str}"

    if any(w in combined for w in ["terror", "bombing", "attack", "explosion", "isis", "al-qaeda"]):
        return "terrorism"
    elif any(w in combined for w in ["war", "military", "armed", "conflict", "battle", "troops"]):
        return "conflict"
    elif any(w in combined for w in ["protest", "demonstrat", "rally", "march", "uprising"]):
        return "protest"
    elif any(w in combined for w in ["earthquake", "hurricane", "flood", "tsunami", "wildfire"]):
        return "natural_disaster"
    elif any(w in combined for w in ["cyber", "hack", "data breach", "ransomware"]):
        return "cyber"
    elif any(w in combined for w in ["sanction", "embargo", "trade war", "tariff"]):
        return "economic"
    elif any(w in combined for w in ["election", "coup", "political", "government"]):
        return "political"
    elif any(w in combined for w in ["disrupt", "supply chain", "shortage", "blockade"]):
        return "disruption"
    return "other"


async def fetch_gdelt_events(
    keywords: Optional[List[str]] = None,
    max_records: int = 50,
    timespan: str = "1h",
) -> List[Dict]:
    """
    Fetch events from GDELT Document API.

    Args:
        keywords: Search keywords (defaults to conflict themes)
        max_records: Maximum number of records to return
        timespan: Time window (e.g., '15min', '1h', '24h')

    Returns:
        List of normalized event dictionaries
    """
    if settings.OFFICIAL_ONLY_MODE:
        logger.info("gdelt_skipped_official_only_mode")
        return []

    if not settings.GDELT_ENABLED:
        logger.info("gdelt_disabled")
        return []

    search_terms = keywords or ["conflict", "military", "protest", "crisis"]
    query = " OR ".join(search_terms)

    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": str(max_records),
        "timespan": timespan,
        "format": "json",
        "sort": "datedesc",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(GDELT_DOC_API, params=params)
            response.raise_for_status()
            data = response.json()

        articles = data.get("articles", [])
        if not articles:
            logger.info("gdelt_no_results", query=query)
            return []

        events = []
        for article in articles:
            # Extract location data
            lat = None
            lon = None
            country = None

            if article.get("sourcecountry"):
                country = article["sourcecountry"]

            # Parse event data
            event_type = _classify_event_type(
                article.get("title", ""),
                article.get("themes", "").split(";") if article.get("themes") else [],
            )

            severity = _tone_to_severity(article.get("tone", 0))

            # Build normalized event
            event = {
                "title": article.get("title", "Untitled Event")[:512],
                "description": article.get("seendate", ""),
                "event_type": event_type,
                "source": "gdelt",
                "source_url": article.get("url") or None,
                "source_id": f"gdelt-{article.get('url', '')[:200]}",
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "severity": severity,
                "confidence": 0.6,  # GDELT is automated, moderate confidence
                "credibility_score": 0.65,
                "event_date": _parse_gdelt_date(article.get("seendate")),
                "tags": (article.get("themes", "").split(";")[:10] if article.get("themes") else []),
                "raw_data": {
                    "source": "gdelt",
                    "domain": article.get("domain"),
                    "language": article.get("language"),
                    "tone": article.get("tone"),
                    "socialimage": article.get("socialimage"),
                    "seen_at": article.get("seendate"),
                    "source_url": article.get("url") or None,
                },
            }
            events.append(event)

        logger.info("gdelt_fetched", count=len(events), query=query)
        return events

    except httpx.HTTPStatusError as e:
        logger.error("gdelt_http_error", status=e.response.status_code, detail=str(e))
        return []
    except Exception as e:
        logger.error("gdelt_error", error=str(e))
        return []


def _parse_gdelt_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse GDELT date format (YYYYMMDDHHmmss)."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip()[:14], "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, IndexError):
        return None


async def fetch_gdelt_geo_events(
    country_code: str = None,
    theme: str = "CONFLICT",
) -> List[Dict]:
    """
    Fetch geo-located events from GDELT GEO API.
    Returns events with lat/lon coordinates.
    """
    if settings.OFFICIAL_ONLY_MODE:
        logger.info("gdelt_geo_skipped_official_only_mode")
        return []

    params = {
        "query": theme,
        "format": "geojson",
        "timespan": "24h",
    }
    if country_code:
        params["query"] = f"{theme} sourcecountry:{country_code}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(GDELT_GEO_API, params=params)
            response.raise_for_status()
            geojson = response.json()

        features = geojson.get("features", [])
        events = []

        for feature in features[:50]:  # Limit
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [None, None])

            events.append({
                "title": props.get("name", "Geo Event")[:512],
                "description": props.get("html", ""),
                "event_type": _classify_event_type(props.get("name", "")),
                "source": "gdelt",
                "source_id": f"gdelt-geo-{props.get('urlsourcename', '')}-{coords[0]}-{coords[1]}",
                "latitude": coords[1] if len(coords) > 1 else None,
                "longitude": coords[0] if coords else None,
                "country": props.get("countrycode"),
                "severity": 5,
                "confidence": 0.55,
                "credibility_score": 0.6,
                "event_date": datetime.now(timezone.utc),
                "tags": [theme],
                "raw_data": {
                    "source": "gdelt_geo",
                    "properties": props,
                    "source_time_kind": "observed",
                },
            })

        logger.info("gdelt_geo_fetched", count=len(events))
        return events

    except Exception as e:
        logger.error("gdelt_geo_error", error=str(e))
        return []
