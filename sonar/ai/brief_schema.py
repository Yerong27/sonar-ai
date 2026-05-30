from __future__ import annotations

import re
from typing import Any

VALID_EVENT_TYPES = {
    "engagement_spike",
    "controversy",
    "product_launch",
    "security_incident",
    "research_breakthrough",
    "other",
}
VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}


def coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def compact_words(value: Any, max_words: int, *, fallback: str = "") -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return fallback
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."


def compact_chars(value: Any, max_chars: int, *, fallback: str = "") -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return fallback
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip(" .,;:") + "..."


def clean_headline(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text or text.lower() in {"unknown", "none", "n/a"}:
        return "Signal anomaly requires review"
    prefixes = [
        "The rapid advancement and pervasive impact of ",
        "The current landscape is dominated by ",
        "The current Hacker News landscape is ",
        "The dominant theme is ",
        "The primary focus is on ",
    ]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            if text:
                text = text[0].upper() + text[1:]
            break
    return compact_words(text, 16, fallback="Signal anomaly requires review").rstrip(".")


def split_insight_items(items: list[str], limit: int = 3) -> list[str]:
    normalized: list[str] = []
    for item in items:
        raw = " ".join(str(item or "").strip().split())
        if not raw:
            continue
        parts = [
            segment.strip(" -•\t")
            for segment in re.split(r"(?:\n+|;\s+|(?<=[.!?])\s+(?=[A-Z0-9\"']))", raw)
            if segment and segment.strip()
        ]
        normalized.extend(parts or [raw])
        if len(normalized) >= limit:
            break
    return [compact_words(item, 18) for item in normalized if item][:limit]


def normalize_brief_payload(
    payload: dict[str, Any],
    *,
    fallback_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = dict(payload)
    fallback_evidence = fallback_evidence or []

    try:
        confidence = float(normalized.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    normalized["confidence"] = max(0.0, min(1.0, confidence))

    normalized["headline_summary"] = clean_headline(normalized.get("headline_summary"))
    normalized["topic"] = compact_words(normalized.get("topic"), 4, fallback="Technology Signal")

    event_type = str(normalized.get("event_type") or "engagement_spike").strip()
    normalized["event_type"] = event_type if event_type in VALID_EVENT_TYPES else "other"

    sentiment = str(normalized.get("sentiment_label") or "neutral").strip().lower()
    normalized["sentiment_label"] = sentiment if sentiment in VALID_SENTIMENTS else "neutral"
    normalized["is_news_aligned"] = bool(normalized.get("is_news_aligned", False))
    normalized["bullet_insights"] = split_insight_items(
        coerce_list(normalized.get("bullet_insights")),
        limit=3,
    )
    normalized["summary"] = compact_words(normalized.get("summary"), 45)

    evidence = normalized.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
    if not evidence and fallback_evidence:
        evidence = [
            {
                "source": item["source"],
                "id": item["id"],
                "title": item["title"],
                "url": item.get("url"),
                "reason_used": item["reason_used"],
            }
            for item in fallback_evidence[:3]
        ]
        normalized["confidence"] = min(normalized["confidence"], 0.49)
    normalized["evidence"] = evidence[:5]
    return normalized
