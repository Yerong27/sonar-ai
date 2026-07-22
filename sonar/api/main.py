from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from sonar.ai.brief_schema import normalize_brief_payload
from sonar.config import settings
from sonar.db import Database, db
from sonar.ingestion.collector import SonarCollector

CollectorFactory = Callable[[], SonarCollector]
STOP_WORDS = {
    "about", "after", "again", "against", "also", "and", "are", "because", "before",
    "being", "between", "could", "for", "from", "has", "have", "into", "its",
    "more", "not", "over", "that", "the", "their", "there", "these", "they",
    "this", "through", "under", "using", "was", "were", "with", "would", "you",
    "your", "what", "when", "where", "which", "while", "will", "news",
    "hacker", "story", "stories", "feed", "newstories", "topstories",
    "anomaly", "anomalies", "automatically", "average", "baseline", "brief", "briefs",
    "comments", "detected", "engagement", "generated", "increase", "internal",
    "label", "metric", "metrics", "monitoring", "score", "signal", "signals",
    "spike", "volume",
}


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


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{1,}", text.lower())
    return [word.strip(".-") for word in words if word not in STOP_WORDS and len(word) > 2]


def _display_keyword(keyword: str) -> str:
    keyword = keyword.strip()
    return keyword.upper() if len(keyword) <= 3 else keyword.title()


def _keyword_tokens(keyword: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(keyword or "").lower())
    short_whitelist = {"ai", "llm", "ml", "ui", "ux", "hn", "gpu", "api"}
    return [token for token in tokens if len(token) > 2 or token in short_whitelist]


def _keyword_match_score(keyword: str, title: str) -> tuple[int, bool]:
    keyword_lower = str(keyword or "").strip().lower()
    title_lower = str(title or "").lower()
    if not keyword_lower or not title_lower:
        return 0, False

    tokens = _keyword_tokens(keyword_lower)
    if not tokens:
        return 0, False

    phrase_match = keyword_lower in title_lower
    matched_tokens = [
        token
        for token in tokens
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", title_lower)
    ]
    token_matches = len(set(matched_tokens))
    if phrase_match:
        return max(4, 3 + token_matches), True
    if token_matches == 0:
        return 0, False

    min_related_matches = 1 if len(tokens) == 1 else max(1, math.ceil(len(tokens) / 2))
    score = token_matches + (1 if token_matches == len(tokens) and len(tokens) > 1 else 0)
    return score, token_matches >= min_related_matches


def _keyword_engagement_weight(score: Any, num_comments: Any) -> float:
    safe_score = max(float(score or 0), 0.0)
    safe_comments = max(float(num_comments or 0), 0.0)
    score_boost = min(math.log1p(safe_score) / 6.5, 1.0)
    comment_boost = min(math.log1p(safe_comments) / 8.5, 0.85)
    return 1.0 + score_boost + comment_boost


def _build_keyword_signals(keywords: list[str], stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for keyword in keywords:
        matched: list[dict[str, Any]] = []
        total_visibility = 0.0
        for story in stories:
            match_score, is_related = _keyword_match_score(keyword, str(story.get("title") or ""))
            if not is_related:
                continue
            visibility_boost = _keyword_engagement_weight(story.get("score"), story.get("num_comments"))
            total_visibility += match_score * visibility_boost
            matched.append(
                {
                    "story_id": story.get("story_id"),
                    "source_feed": story.get("source_feed"),
                    "title": story.get("title"),
                    "score": int(story.get("score") or 0),
                    "num_comments": int(story.get("num_comments") or 0),
                    "permalink": story.get("permalink"),
                    "url": story.get("url"),
                    "collected_at": story.get("collected_at"),
                }
            )

        matched.sort(key=lambda item: (item["score"], item["num_comments"]), reverse=True)
        signals.append(
            {
                "keyword": keyword,
                "display_keyword": _display_keyword(keyword),
                "visibility": round(total_visibility, 1),
                "story_count": len(matched),
                "stories": matched[:8],
            }
        )
    return signals


def create_app(
    *,
    database: Database | None = None,
    collector_factory: CollectorFactory | None = None,
) -> FastAPI:
    api = FastAPI(title="Sonar API", version="0.1.0")
    api.state.database = database or db
    api.state.collector_factory = collector_factory or SonarCollector

    api.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
                LIMIT 80
                    """
                )
            ).mappings().all()

        briefs: list[dict[str, Any]] = []
        theme_counter: Counter[str] = Counter()
        sentiment_counter: Counter[str] = Counter()
        keyword_counter: Counter[str] = Counter()
        latest_brief = None

        for row in brief_rows:
            payload = normalize_brief_payload(_json_loads(row["response_json"], {}))
            topic = str(payload.get("topic") or row["metric_name"] or "").strip()
            sentiment = str(payload.get("sentiment_label") or "neutral").strip().lower()
            if topic:
                theme_counter[topic] += 3
                keyword_counter.update(_keywords(topic))
            sentiment_counter[sentiment or "neutral"] += 1
            for insight in payload.get("bullet_insights") or []:
                keyword_counter.update(_keywords(str(insight)))
            for evidence in payload.get("evidence") or []:
                title = str(evidence.get("title") or "")
                keyword_counter.update(_keywords(title))

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
            if latest_brief is None:
                latest_brief = brief

        story_pool = [_row_to_dict(row) for row in story_rows]
        notable_stories = story_pool[:8]
        for story in story_pool[:18]:
            score = int(story.get("score") or 0)
            comments = int(story.get("num_comments") or 0)
            for keyword in _keywords(str(story.get("title") or "")):
                keyword_counter[keyword] += max(1, min(8, (score + comments) // 250 + 1))

        raw_keywords = [keyword for keyword, _count in keyword_counter.most_common(24)]
        keyword_signals = [
            signal for signal in _build_keyword_signals(raw_keywords, story_pool) if signal["story_count"] > 0
        ][:14]

        ranked_themes = [
            {"theme": theme, "rank": index + 1, "score": score}
            for index, (theme, score) in enumerate(theme_counter.most_common(8))
        ]
        heading_visibility = [
            {
                "keyword": signal["display_keyword"],
                "visibility": max(1, int(signal["visibility"])),
                "story_count": signal["story_count"],
            }
            for signal in keyword_signals[:8]
        ]
        keyword_bubbles = [
            {
                "keyword": signal["display_keyword"],
                "raw_keyword": signal["keyword"],
                "weight": max(1, int(signal["visibility"])),
                "rank": index + 1,
                "story_count": signal["story_count"],
                "stories": signal["stories"],
            }
            for index, signal in enumerate(keyword_signals)
        ]
        sentiment_distribution = [
            {"label": label, "count": sentiment_counter.get(label, 0)}
            for label in ["positive", "negative", "neutral", "mixed"]
        ]

        return {
            "latest_brief": latest_brief,
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

    @api.post("/api/run-once")
    def run_once() -> dict[str, Any]:
        collector = api.state.collector_factory()
        try:
            result = collector.run_once()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        payload = result.to_dict() if hasattr(result, "to_dict") else None
        return {"status": "completed", "cycle": payload}

    return api


app = create_app()
