"""
Source trust classification helpers.

These helpers are intentionally conservative:
- "official" means a clearly official source host or official feed.
- In official-only mode, every non-official record is treated as unverified
  and hidden from user-facing views.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from app.core.config import settings


OFFICIAL_FEEDS = {
    "cisa cyber alerts",
    "un news - peace and security",
    "reliefweb updates",
    "usgs significant earthquakes",
    "usgs m4.5+ earthquakes",
}

OFFICIAL_HOSTS = {
    "cisa.gov",
    "news.un.org",
    "un.org",
    "reliefweb.int",
    "ochaopt.org",
    "who.int",
    "cdc.gov",
    "fema.gov",
    "usgs.gov",
    "earthquake.usgs.gov",
    "state.gov",
    "whitehouse.gov",
    "europa.eu",
    "nato.int",
    "redcross.org",
    "icrc.org",
}


def _normalize_text(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().lower()


def normalize_host(url: Optional[str]) -> str:
    if not url:
        return ""

    try:
        host = urlparse(url).hostname or ""
    except Exception:
        host = ""

    host = host.strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def classify_source(source: Any, source_url: Optional[str], raw_data: Any = None) -> dict[str, str]:
    """Return a conservative trust classification for a stored event source."""
    host = normalize_host(source_url)
    raw = raw_data if isinstance(raw_data, dict) else {}
    feed_name = _normalize_text(raw.get("feed") or raw.get("source_name") or raw.get("name"))
    source_name = _normalize_text(source)
    official_only = settings.OFFICIAL_ONLY_MODE

    if host:
        if host.endswith(".gov") or host.endswith(".mil") or host in OFFICIAL_HOSTS:
            return {
                "source_domain": host,
                "source_status": "official",
                "source_status_reason": f"Official host: {host}",
            }

    if feed_name:
        if feed_name in OFFICIAL_FEEDS:
            return {
                "source_domain": host,
                "source_status": "official",
                "source_status_reason": f"Official feed: {raw.get('feed') or raw.get('source_name') or raw.get('name')}",
            }

    if official_only:
        return {
            "source_domain": host,
            "source_status": "unverified",
            "source_status_reason": "Non-official source hidden in official-only mode",
        }

    if source_name in {"manual", "agent"}:
        return {
            "source_domain": host,
            "source_status": "unverified",
            "source_status_reason": "Manually entered or automation-generated record requires review",
        }

    return {
        "source_domain": host,
        "source_status": "unverified",
        "source_status_reason": "No official host or official feed match found",
    }


def is_verified_source(source: Any, source_url: Optional[str], raw_data: Any = None, credibility_score: float = 0.0) -> bool:
    """Decide whether a record is verified enough to mark as verified in the UI."""
    classification = classify_source(source, source_url, raw_data)
    return classification["source_status"] == "official"
