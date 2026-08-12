from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from sonar.ai.brief_schema import normalize_brief_payload
from sonar.config import settings
from sonar.db import Database, db

def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _count(database: Database, table_name: str) -> int:
    with database.connect() as conn:
        row = (
            conn.execute(text(f"SELECT COUNT(*) AS count FROM {table_name}"))
            .mappings()
            .first()
        )
        return int(row["count"] if row else 0)


def _latest_timestamp(database: Database, table_name: str, column_name: str) -> str | None:
    with database.connect() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    SELECT {column_name} AS timestamp
                    FROM {table_name}
                    ORDER BY {column_name} DESC
                    LIMIT 1
                    """
                )
            )
            .mappings()
            .first()
        )
        return str(row["timestamp"]) if row else None


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text_value = str(item or "").strip()
        if text_value and text_value not in items:
            items.append(text_value)
        if len(items) >= limit:
            break
    return items


def _monitoring_sentiment(payload: dict[str, Any]) -> dict[str, float]:
    raw = payload.get("sentiment_distribution")
    if not isinstance(raw, dict):
        return {}
    distribution: dict[str, float] = {}
    for label in ("positive", "negative", "neutral", "mixed"):
        try:
            distribution[label] = max(0.0, float(raw.get(label, 0)))
        except (TypeError, ValueError):
            distribution[label] = 0.0
    return distribution if any(distribution.values()) else {}


def _keyword_engagement_weight(score: Any, num_comments: Any) -> float:
    safe_score = max(float(score or 0), 0.0)
    safe_comments = max(float(num_comments or 0), 0.0)
    score_boost = min(math.log1p(safe_score) / 6.5, 1.0)
    comment_boost = min(math.log1p(safe_comments) / 8.5, 0.85)
    return 1.0 + score_boost + comment_boost


def _model_keyword_candidates(
    monitoring_payload: dict[str, Any],
    *,
    limit: int = 16,
) -> list[dict[str, Any]]:
    """Read model-selected concepts without inventing title-frequency keywords."""
    raw_signals = monitoring_payload.get("keyword_signals")
    if not isinstance(raw_signals, list):
        raw_signals = monitoring_payload.get("top_keywords")
    if not isinstance(raw_signals, list):
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_signals:
        if isinstance(item, dict):
            concept = str(item.get("concept") or "")
            aliases = _string_list(item.get("aliases"), limit=6)
            supporting_ids = _string_list(item.get("supporting_story_ids"), limit=12)
        else:
            concept = str(item or "")
            aliases = []
            supporting_ids = []

        concept = " ".join(concept.split()).strip(" .,:;!?-_")
        normalized = concept.casefold()
        words = re.findall(r"[A-Za-z0-9+#.-]+", concept)
        if (
            not concept
            or normalized in seen
            or len(concept) > 72
            or not 1 <= len(words) <= 5
        ):
            continue

        clean_aliases: list[str] = []
        for alias in aliases:
            cleaned = " ".join(alias.split()).strip(" .,:;!?-_")
            if cleaned and cleaned.casefold() != normalized and len(cleaned) <= 72:
                clean_aliases.append(cleaned)

        seen.add(normalized)
        candidates.append(
            {
                "concept": concept,
                "aliases": clean_aliases,
                "supporting_story_ids": supporting_ids,
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def _concept_match_strength(concept: str, aliases: list[str], title: str) -> float:
    """Match a model concept to a title using phrases and model-provided aliases."""
    title_text = " ".join(str(title or "").casefold().split())
    title_tokens = set(re.findall(r"[a-z0-9+#.-]+", title_text))
    best = 0.0
    for term in [concept, *aliases]:
        normalized = " ".join(str(term).casefold().split())
        if not normalized:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", title_text):
            best = max(best, 1.0)
            continue
        tokens = set(re.findall(r"[a-z0-9+#.-]+", normalized))
        if not tokens:
            continue
        overlap = len(tokens & title_tokens) / len(tokens)
        required = 1.0 if len(tokens) <= 2 else 0.75
        if overlap >= required:
            best = max(best, 0.7 + (0.2 * overlap))
    return best


def _expanded_keyword_signals(
    monitoring_payload: dict[str, Any],
    stories: list[dict[str, Any]],
    *,
    limit: int = 10,
    min_support: int = 2,
) -> list[dict[str, Any]]:
    """Validate model concepts against the full window and keep recurring signals."""
    signals: list[dict[str, Any]] = []
    for candidate in _model_keyword_candidates(monitoring_payload):
        concept = candidate["concept"]
        aliases = candidate["aliases"]
        explicit_ids = set(candidate["supporting_story_ids"])
        matched: dict[str, tuple[dict[str, Any], float]] = {}
        for story in stories:
            story_id = str(story.get("story_id"))
            strength = _concept_match_strength(concept, aliases, str(story.get("title") or ""))
            if story_id in explicit_ids:
                strength = max(strength, 1.0)
            if strength > 0:
                matched[story_id] = (story, strength)
        if len(matched) < min_support:
            continue

        evidence = [
            {
                "story_id": story.get("story_id"),
                "source_feed": story.get("source_feed"),
                "title": story.get("title"),
                "score": int(story.get("score") or 0),
                "num_comments": int(story.get("num_comments") or 0),
                "permalink": story.get("permalink"),
                "url": story.get("url"),
                "collected_at": story.get("collected_at"),
                "relevance": round(strength, 2),
            }
            for story, strength in matched.values()
        ]
        evidence.sort(key=lambda item: (item["score"], item["num_comments"]), reverse=True)
        visibility = sum(
            _keyword_engagement_weight(story["score"], story["num_comments"])
            * float(story["relevance"])
            for story in evidence
        )
        signals.append(
            {
                "keyword": concept,
                "display_keyword": concept,
                "visibility": round(visibility, 1),
                "coverage": round(sum(item["relevance"] for item in evidence), 1),
                "story_count": len(matched),
                "stories": evidence[:8],
                "story_ids": set(matched),
            }
        )

    signals.sort(
        key=lambda signal: (
            signal["story_count"],
            signal["coverage"],
            signal["visibility"],
        ),
        reverse=True,
    )
    distinct_signals: list[dict[str, Any]] = []
    for signal in signals:
        signal_ids = signal["story_ids"]
        duplicates_existing = any(
            len(signal_ids & existing["story_ids"])
            / max(1, min(len(signal_ids), len(existing["story_ids"])))
            >= 0.8
            for existing in distinct_signals
        )
        if duplicates_existing:
            continue
        distinct_signals.append(signal)
        if len(distinct_signals) >= limit:
            break

    for signal in distinct_signals:
        signal.pop("story_ids", None)
    return distinct_signals


def create_app(
    *,
    database: Database | None = None,
) -> FastAPI:
    api = FastAPI(title="Sonar API", version="0.1.0")
    api.state.database = database or db

    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/health/live", include_in_schema=False)
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/health/ready", include_in_schema=False)
    def health_ready() -> dict[str, str]:
        database: Database = api.state.database
        try:
            with database.connect() as conn:
                conn.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return {"status": "ready"}

    @api.get("/api/runtime")
    def get_runtime() -> dict[str, Any]:
        """Expose non-sensitive runtime facts for public deployment verification."""
        database: Database = api.state.database
        try:
            with database.connect() as conn:
                conn.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc

        service = os.getenv("K_SERVICE")
        revision = os.getenv("K_REVISION")
        configuration = os.getenv("K_CONFIGURATION")
        cloud_run_verified = bool(service and revision and configuration)

        return {
            "status": "ready",
            "cloud_run_verified": cloud_run_verified,
            "platform": "Google Cloud Run" if cloud_run_verified else "Local development",
            "service": service,
            "revision": revision,
            "configuration": configuration,
            "database": {
                "engine": database.engine.dialect.name,
                "status": "connected",
            },
        }

    @api.get("/api/status")
    def get_status() -> dict[str, Any]:
        database: Database = api.state.database
        gemini_status = database.get_status("gemini_status")
        last_collection_time = database.get_last_collection_time()

        return {
            "status": "ok",
            "last_collection_time": last_collection_time,
            "latest_story_time": _latest_timestamp(database, "hn_story_snapshots", "collected_at"),
            "latest_anomaly_time": _latest_timestamp(database, "anomalies", "detected_at"),
            "latest_brief_time": _latest_timestamp(database, "explanations", "created_at"),
            "counts": {
                "stories": _count(database, "hn_story_snapshots"),
                "anomalies": _count(database, "anomalies"),
                "briefs": _count(database, "explanations"),
                "ai_runs": _count(database, "ai_runs"),
                "documents": _count(database, "documents"),
                "monitoring_summaries": _count(database, "monitoring_summaries"),
            },
            "gemini": gemini_status or {"key": "gemini_status", "value": "unknown", "updated_at": None},
        }

    @api.get("/api/stories")
    def get_stories(
        feed: str | None = None,
        limit: int = Query(default=50, ge=1, le=250),
        since: str | None = None,
    ) -> dict[str, Any]:
        database: Database = api.state.database
        where_clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if feed:
            where_clauses.append("source_feed = :feed")
            params["feed"] = feed
        if since:
            where_clauses.append("collected_at >= :since")
            params["since"] = since

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with database.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        f"""
                        SELECT id, story_id, source_feed, title, author, score, num_comments,
                               created_at, permalink, url, collected_at, monitor_gap_flag,
                               gap_duration_minutes
                        FROM hn_story_snapshots
                        {where_sql}
                        ORDER BY collected_at DESC, score DESC, num_comments DESC
                        LIMIT :limit
                        """
                    ),
                    params,
                )
                .mappings()
                .all()
            )

        return {"stories": [_row_to_dict(row) for row in rows]}

    @api.get("/api/anomalies")
    def get_anomalies(
        limit: int = Query(default=50, ge=1, le=250),
        news_aligned: bool | None = None,
    ) -> dict[str, Any]:
        database: Database = api.state.database
        where_sql = ""
        params: dict[str, Any] = {"limit": limit}
        if news_aligned is not None:
            where_sql = "WHERE news_aligned = :news_aligned"
            params["news_aligned"] = 1 if news_aligned else 0

        with database.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        f"""
                        SELECT id, source_feed, metric_name, metric_value, baseline_value,
                               z_score, triggered_by, detected_at, news_aligned,
                               explanation_status, metric_version
                        FROM anomalies
                        {where_sql}
                        ORDER BY detected_at DESC, z_score DESC
                        LIMIT :limit
                        """
                    ),
                    params,
                )
                .mappings()
                .all()
            )

        return {"anomalies": [_row_to_dict(row) for row in rows]}

    @api.get("/api/metrics/timeline")
    def get_metrics_timeline(
        limit: int = Query(default=120, ge=1, le=500),
        feed: str | None = None,
    ) -> dict[str, Any]:
        database: Database = api.state.database
        where_clauses = ["metric_version = :metric_version"]
        params: dict[str, Any] = {
            "metric_version": settings.metric_semantics_version,
            "limit": limit,
        }
        if feed:
            where_clauses.append("source_feed = :feed")
            params["feed"] = feed
        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        with database.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        f"""
                        SELECT source_feed, window_start, window_end, story_volume,
                               avg_score, avg_comments, engagement_score, growth_rate,
                               collected_at
                        FROM aggregated_metrics
                        {where_sql}
                        ORDER BY collected_at DESC
                        LIMIT :limit
                        """
                    ),
                    params,
                )
                .mappings()
                .all()
            )

        timeline = [_row_to_dict(row) for row in reversed(rows)]
        return {"timeline": timeline}

    @api.get("/api/dashboard/overview")
    def get_dashboard_overview() -> dict[str, Any]:
        database: Database = api.state.database
        status = get_status()

        with database.connect() as conn:
            top_stories = conn.execute(
                text(
                    """
                WITH latest_snapshot AS (
                    SELECT story_id, source_feed, MAX(collected_at) AS collected_at
                    FROM hn_story_snapshots
                    GROUP BY story_id, source_feed
                )
                SELECT s.story_id, s.source_feed, s.title, s.score, s.num_comments,
                       s.permalink, s.url, s.collected_at
                FROM hn_story_snapshots s
                JOIN latest_snapshot latest
                  ON latest.story_id = s.story_id
                 AND latest.source_feed = s.source_feed
                 AND latest.collected_at = s.collected_at
                ORDER BY s.score DESC, s.num_comments DESC
                LIMIT 8
                    """
                )
            ).mappings().all()
            feed_rows = conn.execute(
                text(
                    """
                WITH latest_snapshot AS (
                    SELECT story_id, source_feed, MAX(collected_at) AS collected_at
                    FROM hn_story_snapshots
                    GROUP BY story_id, source_feed
                )
                SELECT s.source_feed,
                       COUNT(*) AS story_count,
                       COALESCE(SUM(s.score), 0) AS total_score,
                       COALESCE(SUM(s.num_comments), 0) AS total_comments
                FROM hn_story_snapshots s
                JOIN latest_snapshot latest
                  ON latest.story_id = s.story_id
                 AND latest.source_feed = s.source_feed
                 AND latest.collected_at = s.collected_at
                GROUP BY s.source_feed
                ORDER BY story_count DESC
                    """
                )
            ).mappings().all()
            anomaly_rows = conn.execute(
                text(
                    """
                SELECT id, source_feed, metric_name, metric_value, baseline_value,
                       z_score, triggered_by, detected_at, news_aligned,
                       explanation_status
                FROM anomalies
                ORDER BY detected_at DESC, z_score DESC
                LIMIT 12
                    """
                )
            ).mappings().all()
            brief_row = conn.execute(
                text(
                    """
                SELECT e.id, e.anomaly_id, e.response_json, e.created_at,
                       a.source_feed, a.metric_name, a.z_score,
                       latest_run.provider, latest_run.model,
                       latest_run.status AS ai_status
                FROM explanations e
                JOIN anomalies a ON a.id = e.anomaly_id
                LEFT JOIN (
                    SELECT ar.*
                    FROM ai_runs ar
                    JOIN (
                        SELECT anomaly_id, MAX(created_at) AS created_at
                        FROM ai_runs
                        GROUP BY anomaly_id
                    ) latest
                      ON latest.anomaly_id = ar.anomaly_id
                     AND latest.created_at = ar.created_at
                ) latest_run ON latest_run.anomaly_id = e.anomaly_id
                ORDER BY e.created_at DESC
                LIMIT 1
                    """
                )
            ).mappings().first()

        latest_brief = None
        if brief_row:
            payload = normalize_brief_payload(_json_loads(brief_row["response_json"], {}))
            latest_brief = {
                "id": brief_row["id"],
                "anomaly_id": brief_row["anomaly_id"],
                "created_at": brief_row["created_at"],
                "source_feed": brief_row["source_feed"],
                "metric_name": brief_row["metric_name"],
                "z_score": brief_row["z_score"],
                "headline_summary": payload.get("headline_summary", ""),
                "topic": payload.get("topic", ""),
                "summary": payload.get("summary", ""),
                "sentiment_label": payload.get("sentiment_label", ""),
                "confidence": payload.get("confidence"),
                "bullet_insights": payload.get("bullet_insights", []),
                "evidence_count": len(payload.get("evidence") or []),
                "provider": brief_row["provider"],
                "model": brief_row["model"],
                "ai_status": brief_row["ai_status"],
            }

        return {
            "status": status,
            "top_stories": [_row_to_dict(row) for row in top_stories],
            "feed_summary": [_row_to_dict(row) for row in feed_rows],
            "latest_anomalies": [
                {
                    **_row_to_dict(row),
                    "news_aligned": bool(row["news_aligned"]),
                }
                for row in anomaly_rows
            ],
            "latest_brief": latest_brief,
        }

    @api.get("/api/ai/intelligence")
    def get_ai_intelligence() -> dict[str, Any]:
        database: Database = api.state.database
        with database.connect() as conn:
            brief_rows = conn.execute(
                text(
                    """
                SELECT e.id, e.anomaly_id, e.response_json, e.created_at,
                       a.source_feed, a.metric_name, a.z_score, a.news_aligned,
                       a.triggered_by, a.detected_at,
                       latest_run.provider, latest_run.model,
                       latest_run.status AS ai_status
                FROM explanations e
                JOIN anomalies a ON a.id = e.anomaly_id
                LEFT JOIN (
                    SELECT ar.*
                    FROM ai_runs ar
                    JOIN (
                        SELECT anomaly_id, MAX(created_at) AS created_at
                        FROM ai_runs
                        GROUP BY anomaly_id
                    ) latest
                      ON latest.anomaly_id = ar.anomaly_id
                     AND latest.created_at = ar.created_at
                ) latest_run ON latest_run.anomaly_id = e.anomaly_id
                ORDER BY e.created_at DESC
                LIMIT 12
                    """
                )
            ).mappings().all()
            story_rows = conn.execute(
                text(
                    """
                WITH current_window AS (
                    SELECT MAX(collected_at) AS collected_at
                    FROM hn_story_snapshots
                )
                SELECT s.story_id, s.source_feed, s.title, s.score, s.num_comments,
                       s.permalink, s.url, s.collected_at
                FROM hn_story_snapshots s
                JOIN current_window current
                  ON current.collected_at = s.collected_at
                ORDER BY s.score DESC, s.num_comments DESC
                LIMIT 80
                    """
                )
            ).mappings().all()
            monitoring_row = conn.execute(
                text(
                    """
                SELECT source_scope, response_json, story_count, created_at
                FROM monitoring_summaries
                ORDER BY created_at DESC
                LIMIT 1
                    """
                )
            ).mappings().first()

        briefs: list[dict[str, Any]] = []
        theme_counter: Counter[str] = Counter()
        sentiment_counter: Counter[str] = Counter()
        monitoring_payload = (
            _json_loads(monitoring_row["response_json"], {}) if monitoring_row else {}
        )
        if not isinstance(monitoring_payload, dict):
            monitoring_payload = {}
        monitoring_topics = _string_list(monitoring_payload.get("top_topics"), limit=8)
        dominant_theme = str(monitoring_payload.get("dominant_theme") or "").strip()
        if dominant_theme and dominant_theme not in monitoring_topics:
            monitoring_topics.insert(0, dominant_theme)
        monitoring_sentiment = _monitoring_sentiment(monitoring_payload)
        dominant_sentiment = (
            max(monitoring_sentiment, key=monitoring_sentiment.get)
            if monitoring_sentiment
            else ""
        )
        monitoring_summary = None
        if monitoring_row and monitoring_payload:
            monitoring_summary = {
                "id": f"monitoring-{monitoring_row['created_at']}",
                "created_at": monitoring_row["created_at"],
                "headline_summary": str(
                    monitoring_payload.get("headline_summary")
                    or dominant_theme
                    or "Current Hacker News landscape"
                ),
                "topic": dominant_theme or (monitoring_topics[0] if monitoring_topics else "Landscape monitoring"),
                "summary": str(monitoring_payload.get("summary") or ""),
                "sentiment_label": dominant_sentiment,
                "confidence": None,
                "bullet_insights": _string_list(
                    monitoring_payload.get("bullet_insights"), limit=3
                ),
                "evidence_count": int(monitoring_row["story_count"] or 0),
                "provider": "gemini",
                "model": settings.gemini_model,
                "ai_status": "complete",
                "summary_kind": "monitoring_summary",
                "source_scope": monitoring_row["source_scope"],
            }

        for index, topic in enumerate(monitoring_topics):
            theme_counter[topic] += max(1, len(monitoring_topics) - index)

        for row in brief_rows:
            payload = normalize_brief_payload(_json_loads(row["response_json"], {}))
            topic = str(payload.get("topic") or row["metric_name"] or "").strip()
            sentiment = str(payload.get("sentiment_label") or "neutral").strip().lower()
            if topic and not monitoring_topics:
                theme_counter[topic] += 3
            sentiment_counter[sentiment or "neutral"] += 1

            brief = {
                "id": row["id"],
                "anomaly_id": row["anomaly_id"],
                "created_at": row["created_at"],
                "source_feed": row["source_feed"],
                "metric_name": row["metric_name"],
                "z_score": row["z_score"],
                "news_aligned": bool(row["news_aligned"]),
                "triggered_by": row["triggered_by"],
                "detected_at": row["detected_at"],
                "headline_summary": payload.get("headline_summary", ""),
                "topic": topic,
                "summary": payload.get("summary", ""),
                "event_type": payload.get("event_type", ""),
                "sentiment_label": sentiment,
                "confidence": payload.get("confidence"),
                "bullet_insights": payload.get("bullet_insights", []),
                "evidence_count": len(payload.get("evidence") or []),
                "provider": row["provider"],
                "model": row["model"],
                "ai_status": row["ai_status"],
            }
            briefs.append(brief)

        story_pool = [_row_to_dict(row) for row in story_rows]
        notable_story_ids = _string_list(
            monitoring_payload.get("notable_story_ids"), limit=8
        )
        stories_by_id = {str(story.get("story_id")): story for story in story_pool}
        notable_stories = [
            stories_by_id[story_id]
            for story_id in notable_story_ids
            if story_id in stories_by_id
        ]
        notable_ids = {str(story.get("story_id")) for story in notable_stories}
        notable_stories.extend(
            story
            for story in story_pool
            if str(story.get("story_id")) not in notable_ids
        )
        notable_stories = notable_stories[:8]
        keyword_signals = _expanded_keyword_signals(monitoring_payload, story_pool)

        ranked_themes = [
            {"theme": theme, "rank": index + 1, "score": score}
            for index, (theme, score) in enumerate(theme_counter.most_common(8))
        ]
        heading_visibility = [
            {
                "keyword": signal["display_keyword"],
                "visibility": signal["story_count"],
                "story_count": signal["story_count"],
            }
            for signal in keyword_signals[:8]
        ]
        keyword_bubbles = [
            {
                "keyword": signal["display_keyword"],
                "raw_keyword": signal["keyword"],
                "weight": signal["story_count"],
                "rank": index + 1,
                "story_count": signal["story_count"],
                "stories": signal["stories"],
            }
            for index, signal in enumerate(keyword_signals)
        ]
        sentiment_distribution = [
            {
                "label": label,
                "count": (
                    monitoring_sentiment[label]
                    if monitoring_sentiment
                    else sentiment_counter.get(label, 0)
                ),
            }
            for label in ["positive", "negative", "neutral", "mixed"]
        ]

        return {
            "latest_brief": monitoring_summary,
            "monitoring_summary": monitoring_summary,
            "ranked_themes": ranked_themes,
            "heading_visibility": heading_visibility,
            "keyword_bubbles": keyword_bubbles,
            "sentiment_distribution": sentiment_distribution,
            "notable_stories": notable_stories,
            "event_briefs": briefs,
        }

    @api.get("/api/briefs")
    def get_briefs(limit: int = Query(default=25, ge=1, le=100)) -> dict[str, Any]:
        database: Database = api.state.database
        with database.connect() as conn:
            rows = conn.execute(
                text(
                    """
                SELECT e.id, e.anomaly_id, e.response_json, e.created_at,
                       a.source_feed, a.metric_name, a.z_score, a.news_aligned,
                       a.triggered_by, a.detected_at,
                       latest_run.id AS ai_run_id,
                       latest_run.provider,
                       latest_run.model,
                       latest_run.status AS ai_status
                FROM explanations e
                JOIN anomalies a ON a.id = e.anomaly_id
                LEFT JOIN (
                    SELECT ar.*
                    FROM ai_runs ar
                    JOIN (
                        SELECT anomaly_id, MAX(created_at) AS created_at
                        FROM ai_runs
                        GROUP BY anomaly_id
                    ) latest
                      ON latest.anomaly_id = ar.anomaly_id
                     AND latest.created_at = ar.created_at
                ) latest_run ON latest_run.anomaly_id = e.anomaly_id
                ORDER BY e.created_at DESC
                LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()

        briefs = []
        for row in rows:
            payload = _json_loads(row["response_json"], {})
            briefs.append(
                {
                    "id": row["id"],
                    "anomaly_id": row["anomaly_id"],
                    "created_at": row["created_at"],
                    "source_feed": row["source_feed"],
                    "metric_name": row["metric_name"],
                    "z_score": row["z_score"],
                    "news_aligned": bool(row["news_aligned"]),
                    "triggered_by": row["triggered_by"],
                    "detected_at": row["detected_at"],
                    "headline_summary": payload.get("headline_summary", ""),
                    "topic": payload.get("topic", ""),
                    "sentiment_label": payload.get("sentiment_label", ""),
                    "confidence": payload.get("confidence"),
                    "event_type": payload.get("event_type", ""),
                    "evidence_count": len(payload.get("evidence") or []),
                    "ai_run_id": row["ai_run_id"],
                    "provider": row["provider"],
                    "model": row["model"],
                    "ai_status": row["ai_status"],
                }
            )

        return {"briefs": briefs}

    @api.get("/api/briefs/{brief_id}")
    def get_brief(brief_id: int) -> dict[str, Any]:
        database: Database = api.state.database
        with database.connect() as conn:
            row = conn.execute(
                text(
                    """
                SELECT e.id, e.anomaly_id, e.response_json, e.created_at,
                       a.source_feed, a.metric_name, a.metric_value, a.baseline_value,
                       a.z_score, a.triggered_by, a.detected_at, a.news_aligned,
                       a.explanation_status, a.metric_version,
                       latest_run.id AS ai_run_id,
                       latest_run.provider,
                       latest_run.model,
                       latest_run.schema_name,
                       latest_run.prompt,
                       latest_run.raw_response,
                       latest_run.parsed_json,
                       latest_run.status AS ai_status,
                       latest_run.error AS ai_error,
                       latest_run.created_at AS ai_created_at
                FROM explanations e
                JOIN anomalies a ON a.id = e.anomaly_id
                LEFT JOIN (
                    SELECT ar.*
                    FROM ai_runs ar
                    JOIN (
                        SELECT anomaly_id, MAX(created_at) AS created_at
                        FROM ai_runs
                        GROUP BY anomaly_id
                    ) latest
                      ON latest.anomaly_id = ar.anomaly_id
                     AND latest.created_at = ar.created_at
                ) latest_run ON latest_run.anomaly_id = e.anomaly_id
                WHERE e.id = :brief_id
                    """
                ),
                {"brief_id": brief_id},
            ).mappings().first()
            if not row:
                raise HTTPException(status_code=404, detail="Brief not found")

            news_rows = conn.execute(
                text(
                    """
                    SELECT id, article_count, top_headlines, checked_at
                    FROM news_matches
                    WHERE anomaly_id = :anomaly_id
                    ORDER BY checked_at DESC
                    """
                ),
                {"anomaly_id": row["anomaly_id"]},
            ).mappings().all()
            evidence_rows = []
            if row["ai_run_id"]:
                evidence_rows = conn.execute(
                    text(
                        """
                        SELECT be.id, be.reason_used, be.rank,
                               d.id AS document_id, d.source, d.source_id, d.title,
                               d.url, d.content, d.metadata_json
                        FROM brief_evidence be
                        JOIN documents d ON d.id = be.document_id
                        WHERE be.ai_run_id = :ai_run_id
                        ORDER BY be.rank ASC
                        """
                    ),
                    {"ai_run_id": row["ai_run_id"]},
                ).mappings().all()

        return {
            "brief": {
                "id": row["id"],
                "anomaly_id": row["anomaly_id"],
                "created_at": row["created_at"],
                "response": _json_loads(row["response_json"], {}),
            },
            "ai_run": {
                "id": row["ai_run_id"],
                "provider": row["provider"],
                "model": row["model"],
                "schema_name": row["schema_name"],
                "prompt": row["prompt"],
                "raw_response": row["raw_response"],
                "parsed_json": _json_loads(row["parsed_json"], None),
                "status": row["ai_status"],
                "error": row["ai_error"],
                "created_at": row["ai_created_at"],
            }
            if row["ai_run_id"]
            else None,
            "anomaly": {
                "source_feed": row["source_feed"],
                "metric_name": row["metric_name"],
                "metric_value": row["metric_value"],
                "baseline_value": row["baseline_value"],
                "z_score": row["z_score"],
                "triggered_by": row["triggered_by"],
                "detected_at": row["detected_at"],
                "news_aligned": bool(row["news_aligned"]),
                "explanation_status": row["explanation_status"],
                "metric_version": row["metric_version"],
            },
            "news_matches": [
                {
                    "id": news_row["id"],
                    "article_count": news_row["article_count"],
                    "top_headlines": _json_loads(news_row["top_headlines"], []),
                    "checked_at": news_row["checked_at"],
                }
                for news_row in news_rows
            ],
            "evidence": [
                {
                    "id": evidence_row["id"],
                    "document_id": evidence_row["document_id"],
                    "source": evidence_row["source"],
                    "source_id": evidence_row["source_id"],
                    "title": evidence_row["title"],
                    "url": evidence_row["url"],
                    "content": evidence_row["content"],
                    "metadata": _json_loads(evidence_row["metadata_json"], {}),
                    "reason_used": evidence_row["reason_used"],
                    "rank": evidence_row["rank"],
                }
                for evidence_row in evidence_rows
            ],
        }

    return api


app = create_app()
