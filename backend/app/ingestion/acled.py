"""
ORVANTA Cloud — ACLED Data Ingestion
Fetches conflict data from the Armed Conflict Location & Event Data Project.
Falls back to simulated realistic data if API key is not configured.
"""

import httpx
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

ACLED_API_URL = "https://api.acleddata.com/acled/read"

# Realistic ACLED event types
ACLED_EVENT_TYPES = {
    "Battles": "conflict",
    "Violence against civilians": "conflict",
    "Explosions/Remote violence": "terrorism",
    "Riots": "protest",
    "Protests": "protest",
    "Strategic developments": "political",
}

# Simulated data for development (realistic conflict hotspots)
SIMULATED_EVENTS = [
    {
        "region": "Middle East",
        "country": "Syria",
        "locations": [
            {"city": "Aleppo", "lat": 36.2, "lon": 37.15},
            {"city": "Idlib", "lat": 35.93, "lon": 36.63},
            {"city": "Damascus", "lat": 33.51, "lon": 36.29},
        ],
        "event_types": ["Battles", "Explosions/Remote violence", "Violence against civilians"],
    },
    {
        "region": "East Africa",
        "country": "Sudan",
        "locations": [
            {"city": "Khartoum", "lat": 15.59, "lon": 32.53},
            {"city": "El Fasher", "lat": 13.63, "lon": 25.35},
            {"city": "Port Sudan", "lat": 19.62, "lon": 37.22},
        ],
        "event_types": ["Battles", "Violence against civilians", "Strategic developments"],
    },
    {
        "region": "Eastern Europe",
        "country": "Ukraine",
        "locations": [
            {"city": "Donetsk", "lat": 48.0, "lon": 37.8},
            {"city": "Zaporizhzhia", "lat": 47.84, "lon": 35.14},
            {"city": "Kherson", "lat": 46.63, "lon": 32.62},
        ],
        "event_types": ["Battles", "Explosions/Remote violence"],
    },
    {
        "region": "West Africa",
        "country": "Mali",
        "locations": [
            {"city": "Bamako", "lat": 12.64, "lon": -8.0},
            {"city": "Timbuktu", "lat": 16.77, "lon": -3.01},
        ],
        "event_types": ["Battles", "Violence against civilians", "Explosions/Remote violence"],
    },
    {
        "region": "South Asia",
        "country": "Myanmar",
        "locations": [
            {"city": "Mandalay", "lat": 21.97, "lon": 96.08},
            {"city": "Sagaing", "lat": 21.88, "lon": 95.97},
        ],
        "event_types": ["Battles", "Protests", "Violence against civilians"],
    },
    {
        "region": "East Africa",
        "country": "Ethiopia",
        "locations": [
            {"city": "Mekelle", "lat": 13.5, "lon": 39.47},
            {"city": "Addis Ababa", "lat": 9.02, "lon": 38.75},
        ],
        "event_types": ["Battles", "Protests", "Strategic developments"],
    },
    {
        "region": "Middle East",
        "country": "Yemen",
        "locations": [
            {"city": "Sanaa", "lat": 15.37, "lon": 44.2},
            {"city": "Aden", "lat": 12.78, "lon": 45.04},
            {"city": "Hodeidah", "lat": 14.8, "lon": 42.95},
        ],
        "event_types": ["Battles", "Explosions/Remote violence"],
    },
]


async def fetch_acled_events(
    country: Optional[str] = None,
    limit: int = 50,
    days_back: int = 7,
) -> List[Dict]:
    """
    Fetch events from ACLED API. Falls back to simulated data if no API key.
    """
    if settings.OFFICIAL_ONLY_MODE:
        logger.info("acled_skipped_official_only_mode")
        return []

    if settings.ACLED_API_KEY and settings.ACLED_EMAIL:
        return await _fetch_real_acled(country, limit, days_back)
    else:
        logger.info("acled_using_simulated_data", reason="No API key configured")
        return _generate_simulated_acled(country, limit, days_back)


async def _fetch_real_acled(
    country: Optional[str],
    limit: int,
    days_back: int,
) -> List[Dict]:
    """Fetch from real ACLED API."""
    start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params = {
        "key": settings.ACLED_API_KEY,
        "email": settings.ACLED_EMAIL,
        "event_date": f"{start_date}|",
        "event_date_where": "BETWEEN",
        "limit": str(limit),
        "fields": "event_id_cnty|event_date|event_type|sub_event_type|actor1|actor2|country|admin1|admin2|location|latitude|longitude|fatalities|notes",
    }
    if country:
        params["country"] = country

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(ACLED_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

        events = []
        for item in data.get("data", []):
            event_type = ACLED_EVENT_TYPES.get(item.get("event_type", ""), "other")
            fatalities = int(item.get("fatalities", 0))
            severity = min(10, max(1, 3 + fatalities))

            events.append({
                "title": f"{item.get('event_type', 'Event')}: {item.get('location') or 'Location not supplied'}",
                "description": item.get("notes", ""),
                "event_type": event_type,
                "source": "acled",
                "source_id": f"acled-{item.get('event_id_cnty', '')}",
                "country": item.get("country"),
                "region": item.get("admin1"),
                "city": item.get("location"),
                "latitude": float(item["latitude"]) if item.get("latitude") else None,
                "longitude": float(item["longitude"]) if item.get("longitude") else None,
                "severity": severity,
                "confidence": 0.85,  # ACLED is curated, high confidence
                "credibility_score": 0.9,
                "event_date": datetime.strptime(item["event_date"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                ) if item.get("event_date") else None,
                "tags": [item.get("event_type", ""), item.get("sub_event_type", "")],
                "actors": [a for a in [item.get("actor1"), item.get("actor2")] if a],
                "raw_data": {"source": "acled", "fatalities": fatalities, **item},
            })

        logger.info("acled_fetched", count=len(events))
        return events

    except Exception as e:
        logger.error("acled_api_error", error=str(e))
        return _generate_simulated_acled(country, limit, days_back)


def _generate_simulated_acled(
    country: Optional[str],
    limit: int,
    days_back: int,
) -> List[Dict]:
    """Generate realistic simulated ACLED data for development."""
    events = []
    now = datetime.now(timezone.utc)

    sources = SIMULATED_EVENTS
    if country:
        sources = [s for s in sources if s["country"].lower() == country.lower()]
        if not sources:
            sources = SIMULATED_EVENTS

    for _ in range(min(limit, 30)):
        source = random.choice(sources)
        location = random.choice(source["locations"])
        event_type_name = random.choice(source["event_types"])
        event_type = ACLED_EVENT_TYPES.get(event_type_name, "other")

        # Add slight randomization to coordinates
        lat = location["lat"] + random.uniform(-0.5, 0.5)
        lon = location["lon"] + random.uniform(-0.5, 0.5)

        fatalities = random.choices(
            [0, 1, 2, 5, 10, 20, 50],
            weights=[40, 20, 15, 10, 8, 5, 2],
        )[0]

        severity = min(10, max(1, 3 + fatalities // 2))
        days_ago = random.uniform(0, days_back)
        event_date = now - timedelta(days=days_ago)

        events.append({
            "title": f"{event_type_name}: {location['city']}, {source['country']}",
            "description": (
                f"Simulated {event_type_name.lower()} event in {location['city']}, "
                f"{source['country']}. {fatalities} reported fatalities."
            ),
            "event_type": event_type,
            "source": "acled",
            "source_id": f"acled-sim-{random.randint(100000, 999999)}",
            "country": source["country"],
            "region": source["region"],
            "city": location["city"],
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "severity": severity,
            "confidence": 0.7,
            "credibility_score": 0.75,
            "event_date": event_date,
            "tags": [event_type_name, source["region"]],
            "actors": [],
            "raw_data": {
                "source": "acled_simulated",
                "fatalities": fatalities,
                "region": source["region"],
            },
        })

    logger.info("acled_simulated", count=len(events))
    return events
