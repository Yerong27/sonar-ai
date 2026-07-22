from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from sonar.config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """PostgreSQL-backed database operations used by Sonar.

    Constructing this wrapper creates a lazy SQLAlchemy engine only. Schema DDL
    is owned exclusively by Alembic and is never executed during import/startup.
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
    ) -> None:
        if database_url is not None and engine is not None:
            raise ValueError("Pass either database_url or engine, not both")
        self.engine = engine or create_engine(
            database_url or settings.database_url,
            pool_pre_ping=True,
        )

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        """Yield one transactional connection.

        A successful context commits once; an exception rolls the transaction
        back. The connection is returned to the engine pool in both cases.
        """

        with self.engine.begin() as connection:
            yield connection

    def insert_story_snapshots(self, stories: list[dict[str, Any]]) -> int:
        if not stories:
            return 0
        with self.connect() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO hn_story_snapshots (
                        story_id, source_feed, title, author, score, num_comments,
                        created_at, permalink, url, collected_at,
                        monitor_gap_flag, gap_duration_minutes
                    ) VALUES (
                        :story_id, :source_feed, :title, :author, :score, :num_comments,
                        :created_at, :permalink, :url, :collected_at,
                        :monitor_gap_flag, :gap_duration_minutes
                    )
                    ON CONFLICT (story_id, source_feed, collected_at) DO NOTHING
                    """
                ),
                stories,
            )
            return int(result.rowcount or 0)

    def insert_aggregated_metric(self, metric_row: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO aggregated_metrics (
                        source_feed, window_start, window_end, story_volume, avg_score,
                        avg_comments, engagement_score, growth_rate, metric_version, collected_at
                    ) VALUES (
                        :source_feed, :window_start, :window_end, :story_volume, :avg_score,
                        :avg_comments, :engagement_score, :growth_rate, :metric_version, :collected_at
                    )
                    """
                ),
                metric_row,
            )

    def insert_anomaly(self, anomaly_row: dict[str, Any]) -> int:
        with self.connect() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO anomalies (
                        source_feed, metric_name, metric_value, baseline_value, z_score,
                        triggered_by, detected_at, news_aligned, explanation_status, metric_version
                    ) VALUES (
                        :source_feed, :metric_name, :metric_value, :baseline_value, :z_score,
                        :triggered_by, :detected_at, :news_aligned, :explanation_status, :metric_version
                    )
                    RETURNING id
                    """
                ),
                anomaly_row,
            )
            return int(result.scalar_one())

    def insert_news_match(self, news_row: dict[str, Any]) -> None:
        payload = news_row.copy()
        payload["top_headlines"] = json.dumps(payload["top_headlines"])
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO news_matches (
                        anomaly_id, article_count, top_headlines, checked_at
                    ) VALUES (
                        :anomaly_id, :article_count, :top_headlines, :checked_at
                    )
                    """
                ),
                payload,
            )

    def insert_explanation(self, anomaly_id: int, response_json: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO explanations (
                        anomaly_id, response_json, created_at
                    ) VALUES (
                        :anomaly_id, :response_json, :created_at
                    )
                    ON CONFLICT (anomaly_id) DO UPDATE SET
                        response_json = EXCLUDED.response_json,
                        created_at = EXCLUDED.created_at
                    """
                ),
                {
                    "anomaly_id": anomaly_id,
                    "response_json": json.dumps(response_json),
                    "created_at": utc_now(),
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE anomalies
                    SET explanation_status = 'complete'
                    WHERE id = :anomaly_id
                    """
                ),
                {"anomaly_id": anomaly_id},
            )

    def update_anomaly_explanation_status(self, anomaly_id: int, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    UPDATE anomalies
                    SET explanation_status = :status
                    WHERE id = :anomaly_id
                    """
                ),
                {"status": status, "anomaly_id": anomaly_id},
            )

    def update_anomaly_news_alignment(self, anomaly_id: int, news_aligned: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    UPDATE anomalies
                    SET news_aligned = :news_aligned
                    WHERE id = :anomaly_id
                    """
                ),
                {"news_aligned": int(news_aligned), "anomaly_id": anomaly_id},
            )

    def insert_monitoring_summary(
        self,
        source_scope: str,
        response_json: dict[str, Any],
        story_count: int,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO monitoring_summaries (
                        source_scope, response_json, story_count, created_at
                    ) VALUES (
                        :source_scope, :response_json, :story_count, :created_at
                    )
                    """
                ),
                {
                    "source_scope": source_scope,
                    "response_json": json.dumps(response_json),
                    "story_count": story_count,
                    "created_at": utc_now(),
                },
            )

    def upsert_document(
        self,
        *,
        source: str,
        source_id: str,
        title: str,
        url: str | None,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self.connect() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        source, source_id, title, url, content, metadata_json, created_at
                    ) VALUES (
                        :source, :source_id, :title, :url, :content, :metadata_json, :created_at
                    )
                    ON CONFLICT (source, source_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        url = EXCLUDED.url,
                        content = EXCLUDED.content,
                        metadata_json = EXCLUDED.metadata_json
                    RETURNING id
                    """
                ),
                {
                    "source": source,
                    "source_id": source_id,
                    "title": title,
                    "url": url,
                    "content": content,
                    "metadata_json": json.dumps(metadata or {}),
                    "created_at": utc_now(),
                },
            )
            return int(result.scalar_one())

    def insert_ai_run(
        self,
        *,
        anomaly_id: int | None,
        provider: str,
        model: str,
        schema_name: str,
        prompt: str,
        raw_response: str | None,
        parsed_json: dict[str, Any] | None,
        status: str,
        error: str | None = None,
    ) -> int:
        with self.connect() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO ai_runs (
                        anomaly_id, provider, model, schema_name, prompt, raw_response,
                        parsed_json, status, error, created_at
                    ) VALUES (
                        :anomaly_id, :provider, :model, :schema_name, :prompt, :raw_response,
                        :parsed_json, :status, :error, :created_at
                    )
                    RETURNING id
                    """
                ),
                {
                    "anomaly_id": anomaly_id,
                    "provider": provider,
                    "model": model,
                    "schema_name": schema_name,
                    "prompt": prompt,
                    "raw_response": raw_response,
                    "parsed_json": json.dumps(parsed_json) if parsed_json is not None else None,
                    "status": status,
                    "error": error,
                    "created_at": utc_now(),
                },
            )
            return int(result.scalar_one())

    def insert_brief_evidence(
        self,
        *,
        ai_run_id: int,
        document_id: int,
        reason_used: str,
        rank: int,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO brief_evidence (
                        ai_run_id, document_id, reason_used, rank, created_at
                    ) VALUES (
                        :ai_run_id, :document_id, :reason_used, :rank, :created_at
                    )
                    """
                ),
                {
                    "ai_run_id": ai_run_id,
                    "document_id": document_id,
                    "reason_used": reason_used,
                    "rank": rank,
                    "created_at": utc_now(),
                },
            )

    def get_latest_monitoring_summary_timestamp(self) -> str | None:
        with self.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT created_at
                        FROM monitoring_summaries
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    )
                )
                .mappings()
                .first()
            )
            return str(row["created_at"]) if row else None

    def upsert_status(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO system_status (key, value, updated_at)
                    VALUES (:key, :value, :updated_at)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {"key": key, "value": value, "updated_at": utc_now()},
            )

    def get_status(self, key: str) -> dict[str, str] | None:
        with self.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT key, value, updated_at
                        FROM system_status
                        WHERE key = :key
                        """
                    ),
                    {"key": key},
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            return {
                "key": str(row["key"]),
                "value": str(row["value"]),
                "updated_at": str(row["updated_at"]),
            }

    def get_last_collection_time(self) -> str | None:
        status = self.get_status("last_collection_time")
        return status["value"] if status else None

    def set_last_collection_time(self, timestamp: str) -> None:
        self.upsert_status("last_collection_time", timestamp)

    def reset_monitoring_session(self) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    TRUNCATE TABLE
                        brief_evidence,
                        explanations,
                        ai_runs,
                        document_terms,
                        documents,
                        news_matches,
                        anomalies,
                        aggregated_metrics,
                        monitoring_summaries,
                        hn_story_snapshots,
                        system_status
                    RESTART IDENTITY CASCADE
                    """
                )
            )


db = Database()
