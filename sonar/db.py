from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from sonar.config import settings


COLLECTOR_ADVISORY_LOCK_ID = 7_285_358_723_025_986_130


class CollectorLockUnavailable(RuntimeError):
    """Raised when another collector cycle already owns the database lock."""


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

    @contextmanager
    def collector_lock(self) -> Iterator[None]:
        """Hold one PostgreSQL session advisory lock for a complete collector cycle."""

        with self.engine.connect() as connection:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": COLLECTOR_ADVISORY_LOCK_ID},
                ).scalar_one()
            )
            if not acquired:
                raise CollectorLockUnavailable(
                    "another collector run already holds the database lock"
                )
            try:
                yield
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": COLLECTOR_ADVISORY_LOCK_ID},
                )

    def start_pipeline_run(self, run_id: str, started_at: str) -> dict[str, Any]:
        """Create a run or resume a non-successful run while preserving its logical time."""

        with self.connect() as connection:
            inserted = connection.execute(
                text(
                    """
                    INSERT INTO pipeline_runs (
                        run_id, status, started_at, collected_at, current_stage
                    ) VALUES (
                        :run_id, 'running', :started_at, :started_at, 'starting'
                    )
                    ON CONFLICT (run_id) DO NOTHING
                    RETURNING run_id
                    """
                ),
                {"run_id": run_id, "started_at": started_at},
            ).scalar_one_or_none()

            if inserted is None:
                existing = (
                    connection.execute(
                        text("SELECT * FROM pipeline_runs WHERE run_id = :run_id FOR UPDATE"),
                        {"run_id": run_id},
                    )
                    .mappings()
                    .one()
                )
                if existing["status"] != "succeeded":
                    connection.execute(
                        text(
                            """
                            UPDATE pipeline_runs
                            SET status = 'running',
                                finished_at = NULL,
                                attempt_count = attempt_count + 1,
                                current_stage = 'starting',
                                error_stage = NULL,
                                error_message = NULL
                            WHERE run_id = :run_id
                            """
                        ),
                        {"run_id": run_id},
                    )

            return dict(
                connection.execute(
                    text("SELECT * FROM pipeline_runs WHERE run_id = :run_id"),
                    {"run_id": run_id},
                )
                .mappings()
                .one()
            )

    def get_pipeline_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM pipeline_runs WHERE run_id = :run_id"),
                    {"run_id": run_id},
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def update_pipeline_stage(self, run_id: str, stage: str) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    UPDATE pipeline_runs
                    SET current_stage = :stage
                    WHERE run_id = :run_id AND status = 'running'
                    """
                ),
                {"run_id": run_id, "stage": stage},
            )

    def complete_pipeline_run(self, run_id: str, result: dict[str, Any], finished_at: str) -> None:
        values = {
            "run_id": run_id,
            "finished_at": finished_at,
            "stories_seen": int(result["stories_seen"]),
            "stories_inserted": int(result["stories_inserted"]),
            "metrics_inserted": int(result["metrics_inserted"]),
            "anomalies_detected": int(result["anomalies_detected"]),
            "briefs_generated": int(result["briefs_generated"]),
            "monitoring_summary_checked": bool(result["monitoring_summary_checked"]),
            "monitor_gap_flag": bool(result["monitor_gap_flag"]),
            "gap_duration_minutes": result["gap_duration_minutes"],
        }
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    UPDATE pipeline_runs
                    SET status = 'succeeded',
                        finished_at = :finished_at,
                        current_stage = 'complete',
                        error_stage = NULL,
                        error_message = NULL,
                        stories_seen = :stories_seen,
                        stories_inserted = :stories_inserted,
                        metrics_inserted = :metrics_inserted,
                        anomalies_detected = :anomalies_detected,
                        briefs_generated = :briefs_generated,
                        monitoring_summary_checked = :monitoring_summary_checked,
                        monitor_gap_flag = :monitor_gap_flag,
                        gap_duration_minutes = :gap_duration_minutes
                    WHERE run_id = :run_id
                    """
                ),
                values,
            )

    def fail_pipeline_run(
        self,
        run_id: str,
        *,
        stage: str,
        error_message: str,
        finished_at: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    UPDATE pipeline_runs
                    SET status = 'failed',
                        finished_at = :finished_at,
                        current_stage = 'failed',
                        error_stage = :stage,
                        error_message = :error_message
                    WHERE run_id = :run_id AND status <> 'succeeded'
                    """
                ),
                {
                    "run_id": run_id,
                    "finished_at": finished_at or utc_now(),
                    "stage": stage,
                    "error_message": error_message[:2000],
                },
            )

    def record_pipeline_lock_failure(self, run_id: str, error_message: str) -> None:
        timestamp = utc_now()
        with self.connect() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO pipeline_runs (
                        run_id, status, started_at, collected_at, finished_at,
                        current_stage, error_stage, error_message
                    ) VALUES (
                        :run_id, 'failed', :timestamp, :timestamp, :timestamp,
                        'failed', 'lock', :error_message
                    )
                    ON CONFLICT (run_id) DO NOTHING
                    """
                ),
                {
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "error_message": error_message[:2000],
                },
            )

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

    def insert_aggregated_metric(self, metric_row: dict[str, Any]) -> bool:
        with self.connect() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO aggregated_metrics (
                        source_feed, window_start, window_end, story_volume, avg_score,
                        avg_comments, engagement_score, growth_rate, metric_version, collected_at
                    ) VALUES (
                        :source_feed, :window_start, :window_end, :story_volume, :avg_score,
                        :avg_comments, :engagement_score, :growth_rate, :metric_version, :collected_at
                    )
                    ON CONFLICT (source_feed, window_start, window_end, metric_version) DO NOTHING
                    """
                ),
                metric_row,
            )
            return bool(result.rowcount)

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
                    ON CONFLICT (source_feed, metric_name, detected_at, metric_version) DO NOTHING
                    RETURNING id
                    """
                ),
                anomaly_row,
            )
            anomaly_id = result.scalar_one_or_none()
            if anomaly_id is not None:
                return int(anomaly_id)
            existing_id = connection.execute(
                text(
                    """
                    SELECT id
                    FROM anomalies
                    WHERE source_feed = :source_feed
                      AND metric_name = :metric_name
                      AND detected_at = :detected_at
                      AND metric_version = :metric_version
                    """
                ),
                anomaly_row,
            ).scalar_one()
            return int(existing_id)

    def get_anomaly_explanation_status(self, anomaly_id: int) -> str | None:
        with self.connect() as connection:
            return connection.execute(
                text("SELECT explanation_status FROM anomalies WHERE id = :anomaly_id"),
                {"anomaly_id": anomaly_id},
            ).scalar_one_or_none()

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
                    ON CONFLICT (anomaly_id) DO UPDATE SET
                        article_count = EXCLUDED.article_count,
                        top_headlines = EXCLUDED.top_headlines,
                        checked_at = EXCLUDED.checked_at
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
        *,
        created_at: str | None = None,
    ) -> bool:
        with self.connect() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO monitoring_summaries (
                        source_scope, response_json, story_count, created_at
                    ) VALUES (
                        :source_scope, :response_json, :story_count, :created_at
                    )
                    ON CONFLICT (source_scope, created_at) DO NOTHING
                    """
                ),
                {
                    "source_scope": source_scope,
                    "response_json": json.dumps(response_json),
                    "story_count": story_count,
                    "created_at": created_at or utc_now(),
                },
            )
            return bool(result.rowcount)

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
                    ON CONFLICT (ai_run_id, document_id) DO UPDATE SET
                        reason_used = EXCLUDED.reason_used,
                        rank = EXCLUDED.rank
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
                        pipeline_runs,
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
