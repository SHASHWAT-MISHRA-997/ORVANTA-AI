"""
Event evidence helpers.

These helpers derive a conservative evidence bundle from a stored event without
requiring schema changes. The bundle is used to:
- gate the full-detail experience
- expose verified supporting links separately from search tools
- surface exact-map readiness and location precision
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

from app.core.source_trust import OFFICIAL_FEEDS, OFFICIAL_HOSTS, classify_source, normalize_host


TRUSTED_MEDIA_FEEDS = {
    "bbc world",
    "reuters world",
    "al jazeera",
    "sipri news",
    "crisis group",
}

TRUSTED_MEDIA_HOSTS = {
    "apnews.com",
    "aljazeera.com",
    "bbc.co.uk",
    "bbc.com",
    "bloomberg.com",
    "ft.com",
    "france24.com",
    "reuters.com",
    "reutersagency.com",
    "thehindu.com",
    "washingtonpost.com",
    "wsj.com",
    "nytimes.com",
}

VIDEO_HOSTS = {
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
    "vimeo.com",
}

SEARCH_HOSTS = {
    "google.com",
    "news.google.com",
    "youtube.com",
    "www.google.com",
    "www.youtube.com",
}


def _text(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _raw_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _title_case_words(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_place_segments(value: Any) -> tuple[str, str, str]:
    text = _text(value)
    if not text:
        return "", "", ""

    location_text = text.split(" of ", 1)[-1].strip()
    segments = [segment.strip() for segment in location_text.split(",") if segment.strip()]
    if not segments:
        return text, "", ""
    if len(segments) == 1:
        return segments[0], "", ""
    return segments[0], ", ".join(segments[1:-1]), segments[-1]


def _location_parts(event: Any) -> tuple[str, str, str]:
    raw = _raw_object(_attr(event, "raw_data"))
    place_city, place_region, place_country = _extract_place_segments(
        raw.get("place") or raw.get("location_name") or raw.get("address") or raw.get("location")
    )
    city = _first_text(
        _attr(event, "city"),
        raw.get("city"),
        raw.get("locality"),
        raw.get("town"),
        raw.get("location_city"),
        place_city,
    )
    region = _first_text(
        _attr(event, "region"),
        raw.get("region"),
        raw.get("admin1"),
        raw.get("state"),
        raw.get("province"),
        raw.get("location_region"),
        place_region,
    )
    country = _first_text(
        _attr(event, "country"),
        raw.get("country"),
        raw.get("country_name"),
        raw.get("sourcecountry"),
        raw.get("location_country"),
        place_country,
    )
    return city, region, country


def _coordinate_pair(event: Any) -> tuple[Optional[float], Optional[float]]:
    latitude = _safe_float(_attr(event, "latitude"))
    longitude = _safe_float(_attr(event, "longitude"))
    if latitude is not None and longitude is not None:
        return latitude, longitude

    raw = _raw_object(_attr(event, "raw_data"))
    coordinates = raw.get("coordinates")
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        raw_latitude = _safe_float(coordinates[1])
        raw_longitude = _safe_float(coordinates[0])
        if raw_latitude is not None and raw_longitude is not None:
            return raw_latitude, raw_longitude

    where = _raw_object(raw.get("where"))
    raw_latitude = _safe_float(raw.get("geo_lat") or raw.get("latitude") or raw.get("lat") or where.get("lat"))
    raw_longitude = _safe_float(
        raw.get("geo_lon")
        or raw.get("longitude")
        or raw.get("lon")
        or raw.get("lng")
        or raw.get("long")
        or where.get("lon")
        or where.get("lng")
        or where.get("long")
    )
    if raw_latitude is not None and raw_longitude is not None:
        return raw_latitude, raw_longitude

    georss_point = _text(raw.get("georss_point") or raw.get("point"))
    if georss_point:
        parts = [_safe_float(part) for part in georss_point.replace(",", " ").split()]
        numeric_parts = [part for part in parts if part is not None]
        if len(numeric_parts) >= 2:
            return numeric_parts[0], numeric_parts[1]

    return None, None


def _format_source_label(source: Any) -> str:
    value = _text(source)
    if not value:
        return "Source"
    normalized = value.lower()
    labels = {
        "gdelt": "GDELT",
        "acled": "ACLED",
        "rss": "RSS",
        "manual": "Manual",
        "agent": "Automated ingest",
    }
    return labels.get(normalized, _title_case_words(value))


def _format_location(event: Any) -> str:
    parts = list(_location_parts(event))
    parts = [
        part
        for part in parts
        if part and _lower(part) not in {"unknown", "not available", "country not available"}
    ]
    return ", ".join(parts)


def _format_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = _text(value)
    return text or None


def _looks_like_url(value: Any) -> bool:
    text = _text(value)
    return text.startswith("http://") or text.startswith("https://")


def _compose_search_query(event: Any) -> str:
    parts = [_text(_attr(event, "title")), _format_location(event)]
    query = " ".join(part for part in parts if part).strip()
    return query or _text(_attr(event, "title")) or "official event"


def _extract_source_time(event: Any) -> Optional[str]:
    raw = _raw_object(_attr(event, "raw_data"))
    for key in (
        "published_at",
        "published",
        "updated_at",
        "updated",
        "seen_at",
        "seendate",
        "source_time",
        "reported_at",
    ):
        value = _format_datetime(raw.get(key))
        if value:
            return value
    return None


def _official_context_hint(source: Any, raw: dict[str, Any]) -> bool:
    source_name = _lower(source)
    feed_name = _lower(raw.get("feed") or raw.get("source_name") or raw.get("name"))
    explicit_verified = raw.get("verified") is True or raw.get("channel_verified") is True

    if explicit_verified:
        return True
    if feed_name in OFFICIAL_FEEDS:
        return True
    if source_name and source_name in OFFICIAL_FEEDS:
        return True
    return False


def classify_reference_link(
    url: Optional[str],
    *,
    title: str = "",
    source: str = "",
    raw: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    raw = raw or {}
    clean_url = _text(url)
    host = normalize_host(clean_url)
    source_label = _text(source)
    source_name = _lower(source)
    feed_name = _lower(raw.get("feed") or raw.get("source_name") or raw.get("name") or source_label)
    official_hint = _official_context_hint(source_label, raw)

    if not clean_url:
        return {
            "title": title or source_label or "Source",
            "url": "",
            "source": source_label or "Source",
            "host": host or None,
            "kind": "reference",
            "category": "unverified",
            "verified": False,
            "reason": "Missing URL",
            "published_at": _format_datetime(raw.get("published_at") or raw.get("published")),
        }

    if host in VIDEO_HOSTS:
        if official_hint:
            return {
                "title": title or "Official video",
                "url": clean_url,
                "source": source_label or "Official channel",
                "host": host,
                "kind": "video",
                "category": "official_video",
                "verified": True,
                "reason": "Official video hint provided by the source payload",
                "published_at": _format_datetime(raw.get("published_at") or raw.get("published")),
            }
        if source_name in TRUSTED_MEDIA_FEEDS or feed_name in TRUSTED_MEDIA_FEEDS:
            return {
                "title": title or "Trusted media video",
                "url": clean_url,
                "source": source_label or "Trusted media channel",
                "host": host,
                "kind": "video",
                "category": "trusted_video",
                "verified": True,
                "reason": "Trusted media feed linked this video",
                "published_at": _format_datetime(raw.get("published_at") or raw.get("published")),
            }
        return {
            "title": title or "Video link",
            "url": clean_url,
            "source": source_label or "Video source",
            "host": host,
            "kind": "video",
            "category": "unverified_video",
            "verified": False,
            "reason": "Video host is present but no official verification hint was stored",
            "published_at": _format_datetime(raw.get("published_at") or raw.get("published")),
        }

    if host and (host.endswith(".gov") or host.endswith(".mil") or host in OFFICIAL_HOSTS):
        return {
            "title": title or "Official source",
            "url": clean_url,
            "source": source_label or host,
            "host": host,
            "kind": "official",
            "category": "official",
            "verified": True,
            "reason": f"Official host: {host}",
            "published_at": _format_datetime(raw.get("published_at") or raw.get("published")),
        }

    if feed_name and feed_name in OFFICIAL_FEEDS:
        return {
            "title": title or "Official feed item",
            "url": clean_url,
            "source": source_label or feed_name,
            "host": host or None,
            "kind": "official",
            "category": "official",
            "verified": True,
            "reason": f"Official feed: {source_label or feed_name}",
            "published_at": _format_datetime(raw.get("published_at") or raw.get("published")),
        }

    if host and (
        host in TRUSTED_MEDIA_HOSTS
        or any(host == trusted or host.endswith(f".{trusted}") for trusted in TRUSTED_MEDIA_HOSTS)
    ):
        return {
            "title": title or "Trusted media coverage",
            "url": clean_url,
            "source": source_label or host,
            "host": host,
            "kind": "coverage",
            "category": "trusted_media",
            "verified": True,
            "reason": f"Trusted media host: {host}",
            "published_at": _format_datetime(raw.get("published_at") or raw.get("published")),
        }

    if host in SEARCH_HOSTS:
        return {
            "title": title or "Search tool",
            "url": clean_url,
            "source": source_label or host,
            "host": host,
            "kind": "search",
            "category": "search",
            "verified": False,
            "reason": "Search tool link",
            "published_at": None,
        }

    return {
        "title": title or "Reference",
        "url": clean_url,
        "source": source_label or host or "Reference",
        "host": host or None,
        "kind": "reference",
        "category": "unverified",
        "verified": False,
        "reason": "No official or trusted-media match found",
        "published_at": _format_datetime(raw.get("published_at") or raw.get("published")),
    }


def _append_candidate(
    target: list[dict[str, Any]],
    url: Any,
    *,
    title: str = "",
    source: str = "",
    raw: Optional[dict[str, Any]] = None,
) -> None:
    clean_url = _text(url)
    if not _looks_like_url(clean_url):
        return
    target.append(
        {
            "url": clean_url,
            "title": title or source or "Reference",
            "source": source or "Reference",
            "raw": raw or {},
        }
    )


def _iter_nested_links(value: Any, *, origin: str = "") -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value[:20]:
            yield from _iter_nested_links(item, origin=origin)
        return

    if isinstance(value, dict):
        url = _text(value.get("url") or value.get("link") or value.get("href"))
        title = _text(value.get("title") or value.get("name") or value.get("label") or origin)
        source = _text(value.get("source") or value.get("publisher") or value.get("channel") or origin)
        if _looks_like_url(url):
            yield {
                "url": url,
                "title": title or source or "Reference",
                "source": source or "Reference",
                "raw": value,
            }
        for nested_key in ("links", "sources", "references", "coverage", "coverage_links", "videos", "media", "items"):
            nested = value.get(nested_key)
            if nested:
                yield from _iter_nested_links(nested, origin=nested_key)
        return

    if _looks_like_url(value):
        yield {
            "url": _text(value),
            "title": origin or "Reference",
            "source": origin or "Reference",
            "raw": {},
        }


def _extract_candidate_links(event: Any) -> list[dict[str, Any]]:
    raw = _raw_object(_attr(event, "raw_data"))
    candidates: list[dict[str, Any]] = []

    for key, label in (
        ("entry_link", "Entry link"),
        ("source_url", "Source link"),
        ("report_url", "Report"),
        ("official_url", "Official page"),
        ("article_url", "Article"),
        ("youtube_url", "Video"),
        ("video_url", "Video"),
        ("livestream_url", "Live stream"),
        ("feed_url", "Feed"),
    ):
        _append_candidate(
            candidates,
            raw.get(key),
            title=label,
            source=_text(raw.get("feed") or raw.get("source_name") or raw.get("name") or _attr(event, "source")),
            raw=raw,
        )

    for nested_key in ("links", "sources", "references", "coverage", "coverage_links", "videos", "media", "attachments"):
        nested = raw.get(nested_key)
        if nested:
            candidates.extend(list(_iter_nested_links(nested, origin=nested_key)))

    return candidates


def _dedupe_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for item in links:
        url = _text(item.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        ordered.append(item)
    return ordered


def _build_search_links(event: Any) -> list[dict[str, Any]]:
    query = _compose_search_query(event)
    links = [
        {
            "title": "Search Google News",
            "url": f"https://news.google.com/search?q={quote(query)}",
            "source": "Google News",
            "kind": "news_search",
            "category": "search",
            "verified": False,
            "reason": "Search tool for cross-checking coverage",
            "host": "news.google.com",
            "published_at": None,
        },
        {
            "title": "Search the web",
            "url": f"https://www.google.com/search?q={quote(query)}",
            "source": "Google Search",
            "kind": "web_search",
            "category": "search",
            "verified": False,
            "reason": "Search tool for broader corroboration",
            "host": "google.com",
            "published_at": None,
        },
    ]

    latitude, longitude = _coordinate_pair(event)
    map_query = ""
    map_title = "Search map"
    map_reason = "Map search using stored title and location"
    if latitude is not None and longitude is not None:
        map_query = f"{latitude},{longitude}"
        map_title = "Open exact coordinates"
        map_reason = "Map lookup for stored coordinates"
    elif query:
        map_query = query

    if map_query:
        links.insert(
            0,
            {
                "title": map_title,
                "url": f"https://www.google.com/maps/search/?api=1&query={quote(map_query)}",
                "source": "Google Maps",
                "kind": "map",
                "category": "search",
                "verified": False,
                "reason": map_reason,
                "host": "google.com",
                "published_at": None,
            },
        )

    return links


def _location_precision(event: Any) -> str:
    latitude, longitude = _coordinate_pair(event)
    if latitude is not None and longitude is not None:
        return "exact"
    city, region, country = _location_parts(event)
    if city or region:
        return "place"
    if country:
        return "country"
    return "unknown"


def build_event_evidence_bundle(event: Any) -> dict[str, Any]:
    raw = _raw_object(_attr(event, "raw_data"))
    title = _text(_attr(event, "title"))
    source = _attr(event, "source")
    source_url = _text(_attr(event, "source_url"))
    source_status = classify_source(source, source_url or None, raw).get("source_status")
    source_time = _extract_source_time(event)
    event_time = _format_datetime(_attr(event, "event_date"))
    created_at = _format_datetime(_attr(event, "created_at"))
    location_precision = _location_precision(event)
    has_exact_coordinates = location_precision == "exact"
    candidate_links = _dedupe_links(_extract_candidate_links(event))

    source_reference_url = source_url
    source_reference_title = f"{_format_source_label(source)} source"
    source_reference_source = _format_source_label(source)
    source_reference_raw = raw
    if not source_reference_url:
        for candidate in candidate_links:
            candidate_raw = _raw_object(candidate.get("raw"))
            classified_candidate = classify_reference_link(
                candidate.get("url"),
                title=_text(candidate.get("title")),
                source=_text(candidate.get("source") or _format_source_label(source)),
                raw=candidate_raw,
            )
            if classified_candidate["verified"] and classified_candidate["kind"] != "video":
                source_reference_url = _text(candidate.get("url"))
                source_reference_title = _text(candidate.get("title")) or source_reference_title
                source_reference_source = _text(candidate.get("source")) or source_reference_source
                source_reference_raw = candidate_raw
                break
        if not source_reference_url and candidate_links:
            source_reference_url = _text(candidate_links[0].get("url"))
            source_reference_title = _text(candidate_links[0].get("title")) or source_reference_title
            source_reference_source = _text(candidate_links[0].get("source")) or source_reference_source
            source_reference_raw = _raw_object(candidate_links[0].get("raw"))

    official_source = None
    if source_reference_url:
        official_source = classify_reference_link(
            source_reference_url,
            title=source_reference_title,
            source=source_reference_source,
            raw=source_reference_raw,
        )

    verified_supporting: list[dict[str, Any]] = []
    verified_videos: list[dict[str, Any]] = []

    for candidate in candidate_links:
        if _text(candidate.get("url")) == _text(official_source.get("url") if official_source else ""):
            continue
        classified = classify_reference_link(
            candidate.get("url"),
            title=_text(candidate.get("title")),
            source=_text(candidate.get("source") or _format_source_label(source)),
            raw=_raw_object(candidate.get("raw")),
        )
        if classified["kind"] == "video":
            if classified["verified"]:
                verified_videos.append(classified)
            continue
        if classified["verified"]:
            verified_supporting.append(classified)

    blocking_missing_fields: list[str] = []
    informative_missing_fields: list[str] = []
    if source_status != "official":
        blocking_missing_fields.append("official source verification")
    if not source_reference_url:
        blocking_missing_fields.append("source link")
    if not (has_exact_coordinates or _format_location(event)):
        informative_missing_fields.append("usable location")
    if not (title and (_text(_attr(event, "description")) or raw)):
        blocking_missing_fields.append("descriptive context")
    if not (source_time or event_time or created_at):
        blocking_missing_fields.append("time context")

    detail_available = len(blocking_missing_fields) == 0
    if detail_available:
        if informative_missing_fields:
            detail_reason = (
                "Full detail view is available, but some stored fields are still limited: "
                f"{', '.join(informative_missing_fields)}."
            )
        else:
            detail_reason = "Full detail view is available because the event has official sourcing, context, and time metadata."
    else:
        detail_reason = f"Full detail view is limited because this record is missing: {', '.join(blocking_missing_fields)}."

    return {
        "official_source": official_source,
        "supporting_sources": verified_supporting,
        "video_links": verified_videos,
        "search_links": _build_search_links(event),
        "detail_available": detail_available,
        "detail_reason": detail_reason,
        "detail_missing_fields": [*blocking_missing_fields, *informative_missing_fields],
        "has_exact_coordinates": has_exact_coordinates,
        "location_precision": location_precision,
    }
