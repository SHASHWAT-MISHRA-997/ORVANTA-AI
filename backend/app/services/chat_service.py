"""
ORVANTA Cloud - Chat service
Free-first provider routing for the in-app AI assistant.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Optional
from urllib.parse import quote
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.event_evidence import build_event_evidence_bundle, classify_reference_link
from app.core.logging import get_logger
from app.ingestion.rss import DEFAULT_FEEDS, fetch_rss_events
from app.models.event import Event

logger = get_logger(__name__)


OLLAMA_FALLBACK_URLS = [
    "http://localhost:11434",
    "http://127.0.0.1:11434",
    "http://ollama:11434",
]

OLLAMA_FALLBACK_MODELS = [
    "llama3.1:8b",
    "llama3.2:3b",
    "phi3:latest",
    "mistral:latest",
]

GREETING_INPUTS = {
    "hi",
    "hello",
    "hey",
    "hii",
    "hiii",
    "good morning",
    "good afternoon",
    "good evening",
    "good night",
    "good mid night",
    "good midnight",
    "mid night",
    "midnight",
    "namaste",
}

WISH_KEYWORDS = {
    "good morning",
    "good afternoon",
    "good evening",
    "good night",
    "good mid night",
    "good midnight",
    "mid night",
    "midnight",
    "happy birthday",
    "happy new year",
    "happy diwali",
    "happy holi",
    "eid mubarak",
    "best wishes",
    "congratulations",
}

THANKS_INPUTS = {
    "thanks",
    "thank you",
    "thankyou",
    "thx",
    "ok thanks",
    "thanks a lot",
    "dhanyawad",
    "dhanyavaad",
    "shukriya",
}

WELCOME_INPUTS = {
    "welcome",
    "you are welcome",
    "you're welcome",
    "youre welcome",
    "swagat",
}

ACKNOWLEDGEMENT_INPUTS = {
    "ok",
    "okay",
    "kk",
    "k",
    "acha",
    "accha",
    "theek",
    "thik",
    "hmm",
    "hmmm",
}

FAREWELL_INPUTS = {
    "bye",
    "goodbye",
    "see you",
    "see you later",
    "take care",
}

CURRENT_INFO_HINTS = {
    "latest",
    "today",
    "current",
    "currently",
    "recent",
    "news",
    "update",
    "updates",
    "what happened",
    "what is happening",
    "situation",
    "right now",
}

EXPLAINER_HINTS = {
    "tell me about",
    "explain",
    "overview",
    "summary",
    "brief me",
    "what is",
    "who is",
    "why is",
    "how does",
}

WEB_CONTEXT_STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "brief",
    "briefing",
    "briefly",
    "current",
    "currently",
    "details",
    "explain",
    "for",
    "happened",
    "how",
    "in",
    "is",
    "latest",
    "me",
    "news",
    "of",
    "on",
    "overview",
    "recent",
    "right",
    "situation",
    "status",
    "summary",
    "tell",
    "the",
    "today",
    "update",
    "updates",
    "what",
    "why",
}

OVERCONFIDENT_TERMS = {
    "100%",
    "guaranteed",
    "definitely",
    "certainly",
    "without a doubt",
    "always true",
    "no risk",
    "completely accurate",
    "undeniably",
    "perfectly",
    "confirmed for sure",
}

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
DUCKDUCKGO_API = "https://api.duckduckgo.com/"
WIKIPEDIA_SEARCH_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
RSS_WEB_CONTEXT_FEED_NAMES = {
    "UN News - Peace and Security",
    "CISA Cyber Alerts",
}


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = (value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


def _provider_order() -> list[str]:
    configured = [item.strip().lower() for item in settings.AI_CHAT_PROVIDER_ORDER.split(",")]
    return _dedupe_strings(configured or ["groq", "openrouter", "nvidia", "ollama", "local"])


def _chat_system_prompt() -> str:
    return (
        "You are ORVANTA Assistant, the built-in assistant for this software. "
        "Decide user intent from the message and answer that intent directly. "
        "Always use respectful and polite language. "
        "Address the user respectfully, for example with 'Respected user'. "
        "Answer in natural, clear English. "
        "Be genuinely helpful for both general conversation and ORVANTA product questions. "
        "Avoid robotic, repeated, or template-style phrasing. Vary sentence structure naturally. "
        "Answer the user's exact question first. "
        "Use short paragraphs by default. Use bullets or numbered steps only when they improve clarity. "
        "Do not use canned templates, repeated response patterns, or labels like 'Quick response for:'. "
        "For simple conversational questions, respond directly and naturally. "
        "Think through the answer internally and provide only the final helpful response. "
        "For meaningful operational questions, include practical next steps and likely near-future scenarios with clear uncertainty language. "
        "When answering product or workflow questions, explicitly anchor the answer to ORVANTA modules: Dashboard, Events, Analytics, Alerts, and Manage. "
        "Briefly explain how the answer connects to this real software, not just general AI behavior. "
        "Never invent facts, sources, current events, verification status, or certainty. "
        "Never present rumors, unverified social posts, or speculative claims as facts. "
        "If evidence is weak, explicitly mark uncertainty and ask for verification. "
        "Prefer official and trusted sources over social-media narratives. "
        "If the available context is not enough, say so plainly. "
        "If confidence is low, use available web context before finalizing. If still uncertain, ask one focused follow-up question. "
        "When official stored event context is provided, prioritize that over generic world knowledge. "
        "Use linked official sources for factual claims whenever possible. "
        "Treat search links as search tools, not as verified evidence. "
        "Only mention a direct video as verified when the source list marks it verified. "
        "Important product facts: Dashboard shows stored event summaries and verification indicators. "
        "Analytics shows event-timeline trends and event-type charts from stored records. "
        "Alerts may include a source link for manual checking. "
        "Manage shows live operational controls and system actions. "
        "The current verification rule marks events as verified only when they are official-source verified. "
        "If the user asks who created you, explain that you are the ORVANTA assistant built into this software by Shashwat Mishra, "
        "and that your response quality depends on the currently connected model provider. "
        "If the user asks about Shashwat Mishra, explain his role as the creator and platform builder in a respectful and factual way, "
        "without inventing private details. "
        "If the user asks whether information is real, explain the verification workflow inside the app."
    )


def _normalize_history(message: str, history: Optional[list[dict[str, Any]]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []

    for item in history or []:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})

    latest_message = message.strip()
    if latest_message and (
        not normalized
        or normalized[-1]["role"] != "user"
        or normalized[-1]["content"] != latest_message
    ):
        normalized.append({"role": "user", "content": latest_message})

    history_limit = max(2, settings.AI_CHAT_HISTORY_LIMIT)
    return normalized[-history_limit:]


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return "\n".join(parts).strip()

    return ""


async def _call_openai_compatible_provider(
    *,
    provider_name: str,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    extra_headers: Optional[dict[str, str]] = None,
    extra_payload: Optional[dict[str, Any]] = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": settings.AI_CHAT_TEMPERATURE,
        "max_tokens": settings.AI_CHAT_MAX_TOKENS,
    }
    if extra_payload:
        payload.update(extra_payload)

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.AI_CHAT_TIMEOUT_SECONDS, connect=8.0)) as client:
        response = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = _extract_text_content(message.get("content"))
    if not content:
        raise RuntimeError(f"{provider_name} returned an empty response")

    return {
        "response": content,
        "provider": provider_name,
        "model": str(data.get("model") or model),
    }


async def _fetch_ollama_models(base_url: str) -> list[str]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
        response = await client.get(f"{base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
        data = response.json()
    return [
        str(model.get("name", "")).strip()
        for model in data.get("models", [])
        if str(model.get("name", "")).strip()
    ]


def _resolve_ollama_candidates(available_models: list[str]) -> list[str]:
    configured_models = [
        settings.OLLAMA_CHAT_MODEL,
        settings.OLLAMA_MODEL,
        *OLLAMA_FALLBACK_MODELS,
    ]
    candidates: list[str] = []

    for configured in _dedupe_strings(configured_models):
        if configured in available_models:
            candidates.append(configured)
            continue

        alias_match = next(
            (model for model in available_models if model == f"{configured}:latest" or model.startswith(f"{configured}:")),
            None,
        )
        if alias_match:
            candidates.append(alias_match)

    if not candidates:
        candidates.extend(available_models[:4])

    return _dedupe_strings(candidates)


async def _call_ollama(messages: list[dict[str, str]]) -> dict[str, str]:
    candidate_urls = _dedupe_strings([settings.OLLAMA_BASE_URL, *OLLAMA_FALLBACK_URLS])
    last_error: Optional[Exception] = None

    for base_url in candidate_urls:
        try:
            available_models = await _fetch_ollama_models(base_url)
        except Exception as exc:
            logger.warning("ollama_tags_failed", base_url=base_url, error=str(exc))
            last_error = exc
            continue

        for model in _resolve_ollama_candidates(available_models)[:2]:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(settings.OLLAMA_CHAT_ATTEMPT_TIMEOUT_SECONDS, connect=5.0)
                ) as client:
                    response = await client.post(
                        f"{base_url.rstrip('/')}/api/chat",
                        json={
                            "model": model,
                            "messages": messages,
                            "stream": False,
                            "keep_alive": "30m",
                            "options": {
                                "temperature": settings.AI_CHAT_TEMPERATURE,
                                "top_p": 0.9,
                                "num_predict": settings.AI_CHAT_MAX_TOKENS,
                            },
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                content = _extract_text_content((data.get("message") or {}).get("content"))
                if content:
                    return {
                        "response": content,
                        "provider": "ollama",
                        "model": model,
                    }
            except Exception as exc:
                logger.warning("ollama_chat_attempt_failed", base_url=base_url, model=model, error=str(exc))
                last_error = exc
                continue

    raise RuntimeError(f"Ollama chat failed across all configured endpoints: {last_error}")


def _last_user_message(history: list[dict[str, str]]) -> str:
    for item in reversed(history):
        if item["role"] == "user":
            return item["content"].strip()
    return ""


def _contains_any(text: str, tokens: set[str] | list[str]) -> bool:
    return any(token in text for token in tokens)


def _is_greeting(prompt: str) -> bool:
    return prompt.strip().lower() in GREETING_INPUTS


def _is_thanks(prompt: str) -> bool:
    return prompt.strip().lower() in THANKS_INPUTS


def _is_farewell(prompt: str) -> bool:
    return prompt.strip().lower() in FAREWELL_INPUTS


def _is_acknowledgement(prompt: str) -> bool:
    return prompt.strip().lower() in ACKNOWLEDGEMENT_INPUTS


def _is_wish(prompt: str) -> bool:
    lower = prompt.strip().lower()
    return _contains_any(lower, WISH_KEYWORDS)


def _is_welcome(prompt: str) -> bool:
    lower = prompt.strip().lower()
    return lower in WELCOME_INPUTS


def _mirrored_greeting_from_prompt(prompt: str) -> Optional[str]:
    lower = prompt.strip().lower()
    if "good morning" in lower:
        return "Good morning"
    if "good afternoon" in lower:
        return "Good afternoon"
    if "good evening" in lower:
        return "Good evening"
    if "good night" in lower:
        return "Good night"
    if "good mid night" in lower or "good midnight" in lower or "mid night" in lower or "midnight" in lower:
        return "Good mid night"
    return None


def _is_short_topic_prompt(prompt: str) -> bool:
    cleaned = prompt.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,40}", cleaned):
        return False
    if _is_greeting(cleaned) or _is_thanks(cleaned) or _is_farewell(cleaned) or _is_acknowledgement(cleaned):
        return False
    return True


def _resolve_client_now(
    client_now_iso: Optional[str],
    client_tz_offset_minutes: Optional[int] = None,
) -> datetime:
    if not client_now_iso:
        return datetime.now()

    candidate = client_now_iso.strip()
    if not candidate:
        return datetime.now()

    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            utc_naive = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            if client_tz_offset_minutes is None:
                return parsed.astimezone().replace(tzinfo=None)
            return utc_naive - timedelta(minutes=int(client_tz_offset_minutes))
        return parsed
    except Exception:
        return datetime.now()


def _current_wish_and_date(
    client_now_iso: Optional[str] = None,
    client_tz_offset_minutes: Optional[int] = None,
) -> tuple[str, str]:
    now = _resolve_client_now(client_now_iso, client_tz_offset_minutes)
    hour = now.hour
    if hour < 12:
        wish = "Good morning"
    elif hour < 17:
        wish = "Good afternoon"
    elif hour < 22:
        wish = "Good evening"
    else:
        wish = "Good night"

    return wish, now.strftime("%A, %d %B %Y")


def _build_local_intent_response(
    message: str,
    history: list[dict[str, str]],
    client_now_iso: Optional[str] = None,
    client_tz_offset_minutes: Optional[int] = None,
) -> Optional[str]:
    prompt = message.strip()
    lower = prompt.lower()
    previous = _last_user_message(history[:-1]).lower() if len(history) > 1 else ""
    sections: list[str] = []

    wants_greeting = _is_greeting(prompt)
    wants_wish = _is_wish(prompt)
    wants_thanks = _is_thanks(prompt)
    wants_welcome = _is_welcome(prompt)
    wants_farewell = _is_farewell(prompt)
    wants_ack = _is_acknowledgement(prompt)
    wants_status = _contains_any(
        lower,
        [
            "how are you",
            "how r you",
            "how are u",
            "kaise ho",
            "kese ho",
            "haal chal",
            "hal chal",
            "kya haal",
            "sab thik",
            "sab theek",
        ],
    )
    wants_identity = _contains_any(
        lower,
        [
            "kisne banaya",
            "who made you",
            "who created you",
            "who are you",
            "what are you",
            "tum kaun ho",
            "aap kaun ho",
            "tumhe kisne",
            "who built you",
            "who developed you",
        ],
    )
    wants_shashwat_about = _contains_any(
        lower,
        [
            "shashwat mishra",
            "about shashwat",
            "shashwat ke baare",
            "shashwat kai baare",
            "shashwat ke bare",
            "shashwat ke bare me",
        ],
    )
    wants_capabilities = _contains_any(
        lower,
        [
            "what can you do",
            "what do you do",
            "what work",
            "what work do you do",
            "what can u do",
            "tum kya kar sakte ho",
            "tum kya kya kar sakte ho",
            "tum kya karte ho",
            "what are your capabilities",
        ],
    )
    wants_compare = "dashboard" in lower and "analytics" in lower
    wants_about = _contains_any(
        lower,
        ["what does this software do", "what can this software do", "about this software", "what is orvanta", "what is warops", "what is this software"],
    )
    wants_verification = _contains_any(lower, ["real hai", "is this real", "genuine", "verified", "fake", "true information", "sab real"])
    wants_workflow = _contains_any(lower, ["kaise", "how do i", "how can i", "what should i do"])
    time_wish, _ = _current_wish_and_date(client_now_iso, client_tz_offset_minutes)
    mirrored_wish = _mirrored_greeting_from_prompt(prompt) or time_wish

    # Route substantive questions to the model so responses are adaptive instead of fixed templates.
    # Keep software-about intent local so product identity stays consistent.
    if any([wants_capabilities, wants_compare, wants_verification, wants_workflow]) and not wants_about:
        return None

    if wants_farewell:
        return "Goodbye. If you need anything later, I will be here to help with ORVANTA."

    if wants_ack and not any([wants_status, wants_identity, wants_capabilities, wants_compare, wants_about, wants_verification, wants_workflow]):
        return "Respected user, got it. Ask me anything about alerts, events, risks, or live operations whenever you are ready."

    if wants_wish:
        sections.append(
            f"{mirrored_wish}, respected user. Thank you for your kind wishes. "
            "I am here to help you with ORVANTA anytime."
        )

    if wants_greeting and not wants_wish and not any([wants_status, wants_identity, wants_capabilities, wants_compare, wants_about, wants_verification, wants_workflow]):
        sections.append(
            f"{mirrored_wish}, respected user. I am your ORVANTA assistant. "
            "You can ask me about alerts, analytics, risk scores, verification, manage workflows, or general product guidance."
        )
    elif (wants_status or wants_greeting) and not wants_wish:
        sections.append(
            f"{time_wish}, respected user. I am doing well and ready to help. "
            "You can ask me about alerts, dashboard data, analytics, risk scores, verification, live operations, or how to use this software."
        )

    if wants_identity:
        sections.append(
            "I am the ORVANTA assistant built into this software by Shashwat Mishra. "
            "I help you with alerts, events, analytics, risk interpretation, and live-operations guidance."
        )

    if wants_shashwat_about:
        sections.append(
            "Respected user, based on the project context available to me, Shashwat Mishra is the creator and primary builder of this ORVANTA platform. "
            "His work is focused on building a practical AI operations system for event monitoring, risk analysis, alerts, and guided workflows. "
            "I can explain his product decisions and platform workflow in detail, but I do not invent private personal information."
        )

    if wants_capabilities:
        sections.append(
            "I can help you understand and use ORVANTA.\n"
            "1. Explain dashboard, analytics, alerts, and manage sections.\n"
            "2. Summarize risk scores, trends, and event information.\n"
            "3. Show how to verify source links, confidence, and source status.\n"
            "4. Help you understand what this software does, how to use each feature, and when live public web context is needed."
        )

    if wants_compare:
        sections.append(
            "Dashboard and Analytics are different in this software.\n"
            "1. Dashboard is the quick operational overview. It shows summary cards, alerts, automation status, verification snapshot, and guidance.\n"
            "2. Analytics is the deep analysis page. It shows trend charts, risk distribution, and event-type breakdowns.\n"
            "3. Use Dashboard for fast monitoring.\n"
            "4. Use Analytics when you want detailed pattern review."
        )

    if wants_about:
        sections.append(
            "ORVANTA is the actual operations software where this assistant runs. "
            "Dashboard gives live overview, Events provides source-level verification, Analytics shows trends and risk distribution, Alerts manages action queue, and Manage provides live controls. "
            "I answer using this platform context first, then use live web references when needed."
        )

    if wants_verification:
        sections.append(
            "Not automatically. This software shows stored event data, computed risk scores, and automated analysis outputs, "
            "but important items should still be verified before you treat them as confirmed facts.\n"
            "1. Open the source link on the alert or event.\n"
            "2. Check whether the event is marked verified and whether a source URL is present.\n"
            "3. Review source status and confidence before operational decisions.\n"
            "4. Use Analytics for trend context, then compare that with the original source."
        )

    if wants_workflow:
        if any(token in previous for token in ["real", "verified", "fake", "genuine"]):
            sections.append(
                "Use this workflow inside the app:\n"
                "1. Open Alerts or Dashboard and find the item you want to verify.\n"
                "2. Click the source link and read the original report.\n"
                "3. Check the verification status and confidence indicators.\n"
                "4. If the source is weak or missing, do not treat the item as fully confirmed."
            )
        else:
            sections.append(
            "Tell me the exact task you want help with inside ORVANTA, for example alert verification, risk explanation, "
            "source verification, or analytics, and I will give you the steps."
        )

    if sections:
        return "\n\n".join(sections)

    if wants_welcome:
        return "Thank you, respected user. Dhanyawad. I appreciate it."

    if wants_thanks:
        if "dhany" in lower or "shukriya" in lower:
            return "Dhanyawad, respected user. Aapka swagat hai. If you want, I can help with alerts, analytics, verification, or manage controls."
        return "Thank you, respected user. You are welcome. If you want, I can help with alerts, analytics, verification, or manage controls."

    return None


def _smart_local_fallback(
    message: str,
    history: list[dict[str, str]],
    client_now_iso: Optional[str] = None,
    client_tz_offset_minutes: Optional[int] = None,
) -> str:
    local_response = _build_local_intent_response(message, history, client_now_iso, client_tz_offset_minutes)
    if local_response:
        return local_response

    prompt = message.strip()
    if _is_short_topic_prompt(prompt):
        return (
            f"I can help with {prompt}. "
            "Ask for a current update, quick overview, risk summary, verification view, or supply-chain impact, and I will start directly."
        )

    return (
        "The connected AI model is unavailable right now, but I can still help. "
        "Ask a complete question and, if possible, mention the event, country, alert, or page you want me to explain."
    )


def _should_try_web_context(
    message: str,
    history: list[dict[str, str]],
    client_now_iso: Optional[str] = None,
    client_tz_offset_minutes: Optional[int] = None,
) -> bool:
    prompt = message.strip()
    lower = prompt.lower()

    if _build_local_intent_response(message, history, client_now_iso, client_tz_offset_minutes):
        return False
    if not settings.AI_CHAT_ENABLE_WEB_CONTEXT:
        return False
    if not lower:
        return False

    # Skip web lookups for lightweight social messages.
    if _is_greeting(prompt) or _is_thanks(prompt) or _is_farewell(prompt) or _is_acknowledgement(prompt):
        return False

    return True


def _google_news_search_source(query: str) -> dict[str, str]:
    cleaned = query.strip() or "latest world news"
    return {
        "title": f"Search Google News: {cleaned}",
        "url": f"https://news.google.com/search?q={quote(cleaned)}",
        "source": "Google News",
        "snippet": "Search tool for cross-checking current coverage when direct context is limited.",
        "kind": "news_search",
    }


def _dedupe_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    ordered: list[dict[str, str]] = []
    for item in sources:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _flatten_duckduckgo_topics(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get("Topics"):
            flattened.extend(_flatten_duckduckgo_topics(item.get("Topics") or []))
        elif isinstance(item, dict):
            flattened.append(item)
    return flattened


def _clean_html_snippet(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _extract_focus_query(prompt: str) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'-]*", prompt)
    filtered = [word for word in words if word.lower() not in WEB_CONTEXT_STOPWORDS]
    if not filtered:
        return prompt.strip()
    return " ".join(filtered[:4]).strip()


async def _fetch_duckduckgo_sources(query: str) -> list[dict[str, str]]:
    if settings.OFFICIAL_ONLY_MODE:
        return []

    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
        "no_redirect": "1",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.AI_CHAT_WEB_LOOKUP_TIMEOUT_SECONDS, connect=5.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(DUCKDUCKGO_API, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("duckduckgo_lookup_failed", query=query, error=str(exc))
        return []

    sources: list[dict[str, str]] = []
    abstract = str(data.get("AbstractText") or "").strip()
    abstract_url = str(data.get("AbstractURL") or "").strip()
    abstract_source = str(data.get("AbstractSource") or "DuckDuckGo").strip()
    heading = str(data.get("Heading") or query).strip()

    if abstract and abstract_url:
        sources.append(
            {
                "title": heading or query,
                "url": abstract_url,
                "source": abstract_source or "DuckDuckGo",
                "snippet": abstract,
                "kind": "reference",
            }
        )

    for topic in _flatten_duckduckgo_topics(data.get("RelatedTopics") or [])[: settings.AI_CHAT_WEB_MAX_RESULTS]:
        text = str(topic.get("Text") or "").strip()
        url = str(topic.get("FirstURL") or "").strip()
        if text and url:
            sources.append(
                {
                    "title": text.split(" - ", 1)[0].strip() or query,
                    "url": url,
                    "source": "DuckDuckGo",
                    "snippet": text,
                    "kind": "reference",
                }
            )

    return _dedupe_sources(sources)[: settings.AI_CHAT_WEB_MAX_RESULTS]


async def _fetch_wikipedia_sources(query: str) -> list[dict[str, str]]:
    if settings.OFFICIAL_ONLY_MODE:
        return []

    headers = {"User-Agent": f"{settings.APP_NAME}/1.0"}
    focus_query = _extract_focus_query(query)
    direct_candidates = _dedupe_strings([focus_query, query])

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.AI_CHAT_WEB_LOOKUP_TIMEOUT_SECONDS, connect=8.0),
            follow_redirects=True,
        ) as client:
            direct_sources: list[dict[str, str]] = []
            for candidate in direct_candidates[:2]:
                summary_url = f"{WIKIPEDIA_SUMMARY_API}/{quote(candidate.replace(' ', '_'))}"
                try:
                    summary_response = await client.get(summary_url, headers=headers)
                    summary_response.raise_for_status()
                    summary_data = summary_response.json()
                    title = str(summary_data.get("title") or candidate).strip()
                    extract = str(summary_data.get("extract") or "").strip()
                    page_url = str(((summary_data.get("content_urls") or {}).get("desktop") or {}).get("page") or "")
                    if title and extract and page_url:
                        direct_sources.append(
                            {
                                "title": title,
                                "url": page_url,
                                "source": "Wikipedia",
                                "snippet": extract,
                                "kind": "reference",
                            }
                        )
                except Exception:
                    continue

            if direct_sources:
                return _dedupe_sources(direct_sources)[: settings.AI_CHAT_WEB_MAX_RESULTS]

            params = {
                "action": "query",
                "list": "search",
                "srsearch": focus_query or query,
                "format": "json",
                "utf8": "1",
                "srlimit": min(2, settings.AI_CHAT_WEB_MAX_RESULTS),
            }

            response = await client.get(WIKIPEDIA_SEARCH_API, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            results = (data.get("query") or {}).get("search") or []

            sources: list[dict[str, str]] = []
            for item in results:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue

                snippet = _clean_html_snippet(str(item.get("snippet") or ""))
                summary_url = f"{WIKIPEDIA_SUMMARY_API}/{quote(title.replace(' ', '_'))}"
                try:
                    summary_response = await client.get(summary_url, headers=headers)
                    summary_response.raise_for_status()
                    summary_data = summary_response.json()
                    extract = str(summary_data.get("extract") or "").strip()
                    page_url = str(((summary_data.get("content_urls") or {}).get("desktop") or {}).get("page") or "")
                    thumbnail = str((summary_data.get("thumbnail") or {}).get("source") or "")
                    final_snippet = extract or snippet
                    final_url = page_url or f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                    sources.append(
                        {
                            "title": title,
                            "url": final_url,
                            "source": "Wikipedia",
                            "snippet": final_snippet,
                            "published_at": "",
                            "kind": "reference",
                        }
                    )
                    if thumbnail:
                        sources[-1]["thumbnail"] = thumbnail
                except Exception:
                    sources.append(
                        {
                            "title": title,
                            "url": f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                            "source": "Wikipedia",
                            "snippet": snippet,
                            "kind": "reference",
                        }
                    )
    except Exception as exc:
        logger.warning("wikipedia_lookup_failed", query=query, error=str(exc))
        return []

    return _dedupe_sources(sources)[: settings.AI_CHAT_WEB_MAX_RESULTS]


async def _fetch_gdelt_sources(query: str) -> list[dict[str, str]]:
    if settings.OFFICIAL_ONLY_MODE:
        return []

    focus_query = _extract_focus_query(query)
    params = {
        "query": focus_query or query,
        "mode": "artlist",
        "maxrecords": str(min(3, settings.AI_CHAT_WEB_MAX_RESULTS)),
        "timespan": "7d",
        "format": "json",
        "sort": "datedesc",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.AI_CHAT_WEB_LOOKUP_TIMEOUT_SECONDS, connect=8.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(GDELT_DOC_API, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("gdelt_lookup_failed", query=query, error=str(exc))
        return []

    sources: list[dict[str, str]] = []
    for article in (data.get("articles") or [])[: min(3, settings.AI_CHAT_WEB_MAX_RESULTS)]:
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        domain = str(article.get("domain") or "GDELT").strip()
        seen_date = str(article.get("seendate") or "").strip()
        if title and url:
            sources.append(
                {
                    "title": title,
                    "url": url,
                    "source": domain or "GDELT",
                    "snippet": f"Recent article indexed by GDELT for query '{focus_query or query}'.",
                    "published_at": seen_date,
                    "kind": "news",
                }
            )

    return _dedupe_sources(sources)


async def _fetch_rss_sources(query: str) -> list[dict[str, str]]:
    focus_query = _extract_focus_query(query)
    query_terms = [term.lower() for term in focus_query.split() if len(term) > 2]
    selected_feeds = [feed for feed in DEFAULT_FEEDS if feed.get("name") in RSS_WEB_CONTEXT_FEED_NAMES]

    try:
        events = await fetch_rss_events(feeds=selected_feeds, max_per_feed=5)
    except Exception as exc:
        logger.warning("rss_lookup_failed", query=query, error=str(exc))
        return []

    sources: list[dict[str, str]] = []
    for event in events:
        title = str(event.get("title") or "").strip()
        description = _clean_html_snippet(str(event.get("description") or ""))
        url = str(event.get("source_url") or "").strip()
        feed_name = str((event.get("raw_data") or {}).get("feed") or "RSS").strip()
        event_date = event.get("event_date")
        haystack = f"{title} {description}".lower()

        if query_terms and not any(term in haystack for term in query_terms):
            continue
        if not title or not url:
            continue

        sources.append(
            {
                "title": title,
                "url": url,
                "source": feed_name,
                "snippet": description[:240] if description else f"Recent feed item related to {focus_query or query}.",
                "published_at": event_date.isoformat() if event_date else "",
                "kind": "news",
            }
        )

    return _dedupe_sources(sources)[: settings.AI_CHAT_WEB_MAX_RESULTS]


async def _fetch_google_news_rss_sources(query: str) -> list[dict[str, str]]:
    search_query = _extract_focus_query(query) or query.strip() or "latest world news"
    rss_url = (
        "https://news.google.com/rss/search"
        f"?q={quote(search_query)}&hl=en-US&gl=US&ceid=US:en"
    )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.AI_CHAT_WEB_LOOKUP_TIMEOUT_SECONDS, connect=8.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(rss_url)
            response.raise_for_status()
            xml_text = response.text
    except Exception as exc:
        logger.warning("google_news_rss_failed", query=query, error=str(exc))
        return []

    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        logger.warning("google_news_rss_parse_failed", query=query, error=str(exc))
        return []

    sources: list[dict[str, str]] = []
    items = root.findall("./channel/item")
    for item in items[: min(3, settings.AI_CHAT_WEB_MAX_RESULTS)]:
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        published_at = (item.findtext("pubDate") or "").strip()
        if not title or not url:
            continue

        sources.append(
            {
                "title": title,
                "url": url,
                "source": "Google News",
                "snippet": f"Live Google News coverage for '{search_query}'.",
                "published_at": published_at,
                "kind": "news",
            }
        )

    return _dedupe_sources(sources)


def _normalize_chat_source(source: dict[str, Any]) -> dict[str, Any]:
    url = str(source.get("url") or "").strip()
    base = classify_reference_link(
        url,
        title=str(source.get("title") or "").strip(),
        source=str(source.get("source") or "").strip(),
        raw={
            "name": source.get("source"),
            "published_at": source.get("published_at"),
            "published": source.get("published_at"),
        },
    )

    if source.get("kind"):
        base["kind"] = str(source.get("kind"))
    if "category" in source and source.get("category"):
        base["category"] = str(source.get("category"))
    if "verified" in source:
        base["verified"] = bool(source.get("verified"))
    if source.get("reason"):
        base["reason"] = str(source.get("reason"))
    if source.get("published_at"):
        base["published_at"] = str(source.get("published_at"))
    if source.get("snippet"):
        base["snippet"] = str(source.get("snippet"))

    return base


def _prepare_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = _dedupe_sources(sources)
    return [_normalize_chat_source(source) for source in deduped]


def _extract_match_terms(prompt: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'-]*", prompt.lower())
    return [word for word in words if word not in WEB_CONTEXT_STOPWORDS and len(word) > 2][:8]


def _score_event_match(event: Event, terms: list[str], prompt: str) -> int:
    if not terms:
        return 0

    title = (event.title or "").lower()
    description = (event.description or "").lower()
    location = " ".join(filter(None, [event.city or "", event.region or "", event.country or ""])).lower()
    tags = " ".join(str(tag) for tag in (event.tags or [])).lower()
    actors = " ".join(str(actor) for actor in (event.actors or [])).lower()
    prompt_lower = prompt.lower()

    score = 0
    for term in terms:
        if term in title:
            score += 5
        if term in location:
            score += 3
        if term in tags or term in actors:
            score += 2
        if term in description:
            score += 1

    if prompt_lower and prompt_lower in title:
        score += 6

    return score


def _clip_text(value: str, limit: int = 220) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _format_event_location(event: Event) -> str:
    parts = [event.city, event.region, event.country]
    return ", ".join(part for part in parts if part) or "Location not available"


def _build_official_event_context_message(message: str, events: list[Event]) -> str:
    lines = [
        f"Official stored event context relevant to the user's question: {message}",
        "Use these records first. Do not go beyond the evidence in these records. If they are insufficient, say so plainly.",
    ]

    for index, event in enumerate(events, start=1):
        evidence = build_event_evidence_bundle(event)
        official_source = evidence.get("official_source") or {}
        lines.append(
            " | ".join(
                [
                    f"[DB{index}] {event.title}",
                    f"location={_format_event_location(event)}",
                    f"type={event.event_type.value}",
                    f"severity={event.severity}/10",
                    f"confidence={float(event.confidence or 0):.2f}",
                    f"event_date={event.event_date.isoformat() if event.event_date else 'not available'}",
                    f"source={official_source.get('url') or 'not available'}",
                    f"detail_available={str(evidence.get('detail_available')).lower()}",
                    f"detail_reason={evidence.get('detail_reason')}",
                    f"summary={_clip_text(event.description or 'No description stored.', 180)}",
                ]
            )
        )

    return "\n".join(lines)


def _build_official_event_sources(events: list[Event]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for event in events:
        evidence = build_event_evidence_bundle(event)
        official_source = evidence.get("official_source")
        if official_source:
            sources.append(dict(official_source))

        sources.extend(dict(item) for item in (evidence.get("supporting_sources") or [])[:2])
        sources.extend(dict(item) for item in (evidence.get("video_links") or [])[:1])

        search_links = evidence.get("search_links") or []
        for preferred_kind in ("news_search", "video_search"):
            match = next((item for item in search_links if item.get("kind") == preferred_kind), None)
            if match:
                sources.append(dict(match))

    return _prepare_sources(sources)[: max(4, settings.AI_CHAT_WEB_MAX_RESULTS)]


async def _gather_official_event_context(
    message: str,
    organization_id: Any,
    db: Optional[AsyncSession],
) -> dict[str, Any]:
    if not organization_id or db is None:
        return {"events": [], "context_message": "", "sources": []}

    result = await db.execute(
        select(Event)
        .where(
            Event.organization_id == organization_id,
            Event.is_verified == 1,
        )
        .order_by(Event.created_at.desc())
        .limit(120)
    )
    events = result.scalars().all()
    if not events:
        return {"events": [], "context_message": "", "sources": []}

    terms = _extract_match_terms(message)
    ranked = sorted(
        (
            (event, _score_event_match(event, terms, message))
            for event in events
        ),
        key=lambda item: item[1],
        reverse=True,
    )

    matches = [event for event, score in ranked if score > 0][:3]
    if not matches:
        return {"events": [], "context_message": "", "sources": []}

    return {
        "events": matches,
        "context_message": _build_official_event_context_message(message, matches),
        "sources": _build_official_event_sources(matches),
    }


def _official_context_fallback(message: str, events: list[Event]) -> str:
    if not events:
        return ""

    lines = [
        f"I found {len(events)} official record(s) in your workspace related to \"{message}\".",
    ]

    for event in events[:2]:
        evidence = build_event_evidence_bundle(event)
        official_source = evidence.get("official_source") or {}
        event_time = event.event_date.isoformat() if event.event_date else "time not available"
        lines.append(
            f"{event.title} | {_format_event_location(event)} | {event_time} | source: {official_source.get('url') or 'not stored'}"
        )

    lines.append(
        "I can confirm only what is present in these official records. If you need more, open the linked source or the event detail view."
    )
    return "\n\n".join(lines)


async def _gather_web_sources(query: str) -> list[dict[str, str]]:
    google_search_card = _google_news_search_source(query)

    if settings.OFFICIAL_ONLY_MODE:
        google_rss = await _fetch_google_news_rss_sources(query)
        official_sources = await _fetch_rss_sources(query)
        merged = _dedupe_sources([google_search_card, *google_rss, *official_sources])
        return merged[: settings.AI_CHAT_WEB_MAX_RESULTS]

    tasks = [
        _fetch_google_news_rss_sources(query),
        _fetch_duckduckgo_sources(query),
        _fetch_wikipedia_sources(query),
    ]

    if _is_short_topic_prompt(query) or _contains_any(query.lower(), CURRENT_INFO_HINTS):
        tasks.append(_fetch_gdelt_sources(query))
        tasks.append(_fetch_rss_sources(query))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    sources: list[dict[str, str]] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        sources.extend(result)

    deduped = _dedupe_sources([google_search_card, *sources])
    if deduped:
        return deduped[: settings.AI_CHAT_WEB_MAX_RESULTS]
    return [google_search_card]


def _build_web_context_message(query: str, sources: list[dict[str, str]]) -> str:
    lines = [
        f"Public web context for the user's query: {query}",
        "Use this only when supported by the sources below. Do not invent facts beyond them. If the sources are limited, say so plainly.",
    ]
    for index, source in enumerate(sources, start=1):
        title = source.get("title") or "Untitled source"
        origin = source.get("source") or "Web"
        snippet = source.get("snippet") or ""
        url = source.get("url") or ""
        published_at = source.get("published_at") or ""
        meta = f"{origin}"
        if published_at:
            meta += f" | {published_at}"
        lines.append(f"[{index}] {title} | {meta} | {snippet} | {url}")
    return "\n".join(lines)


def _web_context_fallback(query: str, sources: list[dict[str, Any]]) -> str:
    lead = (
        f"I reached public web sources for {query}, but the connected model is unavailable right now. "
        "Here is a quick source-backed starting point."
    )
    details: list[str] = []
    for source in sources[:2]:
        title = source.get("title") or "Source"
        snippet = source.get("snippet") or "A relevant source was found."
        details.append(f"{title}: {snippet}")
    return "\n\n".join([lead, *details])


def _looks_factual_query(message: str) -> bool:
    lower = message.strip().lower()
    return _contains_any(
        lower,
        [
            "what",
            "why",
            "how",
            "when",
            "where",
            "is it",
            "are they",
            "latest",
            "update",
            "real",
            "verified",
            "news",
            "risk",
            "alert",
        ],
    )


def _soften_overclaim_language(text: str) -> str:
    softened = text
    replacements = {
        r"\bdefinitely\b": "likely",
        r"\bcertainly\b": "based on available data",
        r"\bundeniably\b": "with current evidence",
        r"\bguaranteed\b": "not guaranteed",
        r"\bperfectly\b": "reasonably",
        r"\bwithout a doubt\b": "with current confidence",
        r"\bcompletely accurate\b": "as accurate as current evidence allows",
    }
    for pattern, replacement in replacements.items():
        softened = re.sub(pattern, replacement, softened, flags=re.IGNORECASE)
    return softened


def _apply_truth_guardrail(message: str, response: str, has_evidence: bool) -> str:
    cleaned = (response or "").strip()
    if not cleaned:
        return cleaned

    softened = _soften_overclaim_language(cleaned)
    lower = softened.lower()
    overconfident = _contains_any(lower, OVERCONFIDENT_TERMS)

    if _looks_factual_query(message) and not has_evidence and overconfident:
        return (
            "I cannot fully verify this from current stored or live sources, so I will keep the answer careful and non-final.\n\n"
            f"{softened}"
        )

    return softened


def _should_attach_sources(message: str) -> bool:
    """Attach source cards only when the user explicitly asks for evidence/links."""
    lower = message.strip().lower()
    return _contains_any(
        lower,
        [
            "source",
            "sources",
            "link",
            "links",
            "evidence",
            "proof",
            "cite",
            "citation",
            "verify",
            "verification",
            "show source",
            "show sources",
            "reference",
            "references",
        ],
    )


async def generate_chat_response(
    message: str,
    history: Optional[list[dict[str, Any]]] = None,
    client_now_iso: Optional[str] = None,
    client_tz_offset_minutes: Optional[int] = None,
    organization_id: Any = None,
    db: Optional[AsyncSession] = None,
) -> dict[str, Any]:
    normalized_history = _normalize_history(message, history)
    local_response = _build_local_intent_response(
        message,
        normalized_history,
        client_now_iso,
        client_tz_offset_minutes,
    )
    if local_response:
        return {
            "response": local_response,
            "provider": "local_fallback",
            "model": "deterministic",
            "sources": [],
        }

    chat_messages = [{"role": "system", "content": _chat_system_prompt()}]
    official_context = await _gather_official_event_context(message, organization_id, db)
    official_sources = _prepare_sources(official_context.get("sources") or [])
    if official_context.get("context_message"):
        chat_messages.append({"role": "system", "content": official_context["context_message"]})

    web_sources: list[dict[str, Any]] = []

    if _should_try_web_context(message, normalized_history, client_now_iso, client_tz_offset_minutes):
        web_sources = _prepare_sources(await _gather_web_sources(message))
        if web_sources:
            chat_messages.append({"role": "system", "content": _build_web_context_message(message, web_sources)})

    combined_sources = _prepare_sources([*official_sources, *web_sources])
    has_evidence = bool(combined_sources)
    response_sources = combined_sources if _should_attach_sources(message) else []
    chat_messages.extend(normalized_history)
    provider_errors: list[str] = []

    for provider in _provider_order():
        try:
            if provider == "openrouter" and settings.OPENROUTER_API_KEY:
                result = await _call_openai_compatible_provider(
                    provider_name="openrouter",
                    base_url=settings.OPENROUTER_BASE_URL,
                    api_key=settings.OPENROUTER_API_KEY,
                    model=settings.OPENROUTER_MODEL,
                    messages=chat_messages,
                    extra_headers={
                        "HTTP-Referer": settings.FRONTEND_URL,
                        "X-OpenRouter-Title": settings.APP_NAME,
                    },
                )
                result["response"] = _apply_truth_guardrail(message, result.get("response", ""), has_evidence)
                result["sources"] = response_sources
                return result

            if provider == "groq" and settings.GROQ_API_KEY:
                result = await _call_openai_compatible_provider(
                    provider_name="groq",
                    base_url=settings.GROQ_BASE_URL,
                    api_key=settings.GROQ_API_KEY,
                    model=settings.GROQ_MODEL,
                    messages=chat_messages,
                )
                result["response"] = _apply_truth_guardrail(message, result.get("response", ""), has_evidence)
                result["sources"] = response_sources
                return result

            if provider == "nvidia" and settings.NVIDIA_API_KEY:
                result = await _call_openai_compatible_provider(
                    provider_name="nvidia",
                    base_url=settings.NVIDIA_BASE_URL,
                    api_key=settings.NVIDIA_API_KEY,
                    model=settings.NVIDIA_MODEL,
                    messages=chat_messages,
                )
                result["response"] = _apply_truth_guardrail(message, result.get("response", ""), has_evidence)
                result["sources"] = response_sources
                return result

            if provider == "ollama":
                result = await _call_ollama(chat_messages)
                result["response"] = _apply_truth_guardrail(message, result.get("response", ""), has_evidence)
                result["sources"] = response_sources
                return result

            if provider == "local":
                break
        except Exception as exc:
            logger.warning("chat_provider_failed", provider=provider, error=str(exc))
            provider_errors.append(f"{provider}: {exc}")

    if official_context.get("events"):
        if provider_errors:
            logger.warning("chat_all_remote_providers_failed", failures=provider_errors)
        return {
            "response": _apply_truth_guardrail(
                message,
                _official_context_fallback(message, official_context["events"]),
                True,
            ),
            "provider": "official_context_fallback",
            "model": "stored_official_records",
            "sources": response_sources,
        }

    if web_sources:
        if provider_errors:
            logger.warning("chat_all_remote_providers_failed", failures=provider_errors)
        return {
            "response": _apply_truth_guardrail(message, _web_context_fallback(message, web_sources), True),
            "provider": "web_fallback",
            "model": "public_sources",
            "sources": response_sources,
        }

    fallback = _smart_local_fallback(
        message,
        normalized_history,
        client_now_iso,
        client_tz_offset_minutes,
    )
    if provider_errors:
        logger.warning("chat_all_remote_providers_failed", failures=provider_errors)

    return {
        "response": _apply_truth_guardrail(message, fallback, False),
        "provider": "local_fallback",
        "model": "deterministic",
        "sources": [],
    }
