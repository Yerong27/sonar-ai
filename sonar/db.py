from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sonar.config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.database_path
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hn_story_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_id TEXT NOT NULL,
                    source_feed TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    score INTEGER NOT NULL,
                    num_comments INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    permalink TEXT NOT NULL,
                    url TEXT,
                    collected_at TEXT NOT NULL,
                    monitor_gap_flag INTEGER NOT NULL DEFAULT 0,
                    gap_duration_minutes INTEGER
                );

                CREATE TABLE IF NOT EXISTS aggregated_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_feed TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    story_volume INTEGER NOT NULL,
                    avg_score REAL NOT NULL,
                    avg_comments REAL NOT NULL,
                    engagement_score REAL NOT NULL,
                    growth_rate REAL NOT NULL,
                    metric_version INTEGER NOT NULL DEFAULT 1,
                    collected_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS anomalies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_feed TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    baseline_value REAL NOT NULL,
                    z_score REAL NOT NULL,
                    triggered_by TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    news_aligned INTEGER DEFAULT 0,
                    explanation_status TEXT DEFAULT 'pending',
                    metric_version INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS news_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    anomaly_id INTEGER NOT NULL,
                    article_count INTEGER NOT NULL,
                    top_headlines TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    FOREIGN KEY (anomaly_id) REFERENCES anomalies(id)
                );

                CREATE TABLE IF NOT EXISTS explanations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    anomaly_id INTEGER NOT NULL UNIQUE,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (anomaly_id) REFERENCES anomalies(id)
                );

                CREATE TABLE IF NOT EXISTS monitoring_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_scope TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    story_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS system_status (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            # Change 2: persist monitoring gap metadata alongside each snapshot row.
            self._ensure_column(
                conn,
                "hn_story_snapshots",
                "monitor_gap_flag",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                conn,
                "hn_story_snapshots",
                "gap_duration_minutes",
                "INTEGER",
            )
            self._ensure_column(
                conn,
                "aggregated_metrics",
                "metric_version",
                "INTEGER NOT NULL DEFAULT 1",
            )
            self._ensure_column(
                conn,
                "anomalies",
                "metric_version",
                "INTEGER NOT NULL DEFAULT 1",
            )
            conn.execute("DROP INDEX IF EXISTS idx_hn_story_snapshot_unique")
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_hn_story_snapshot_unique
                ON hn_story_snapshots (story_id, source_feed, collected_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_hn_story_snapshot_feed_time
                ON hn_story_snapshots (source_feed, collected_at)
                """
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        columns = {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )

    def insert_story_snapshots(self, stories: list[dict[str, Any]]) -> int:
        if not stories:
            return 0
        with self.connect() as conn:
            cursor = conn.executemany(
                """
                INSERT OR IGNORE INTO hn_story_snapshots (
                    story_id, source_feed, title, author, score, num_comments,
                    created_at, permalink, url, collected_at,
                    monitor_gap_flag, gap_duration_minutes
                ) VALUES (
                    :story_id, :source_feed, :title, :author, :score, :num_comments,
                    :created_at, :permalink, :url, :collected_at,
                    :monitor_gap_flag, :gap_duration_minutes
                )
                """,
                stories,
            )
            return cursor.rowcount

    def insert_aggregated_metric(self, metric_row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO aggregated_metrics (
                    source_feed, window_start, window_end, story_volume, avg_score,
                    avg_comments, engagement_score, growth_rate, metric_version, collected_at
                ) VALUES (
                    :source_feed, :window_start, :window_end, :story_volume, :avg_score,
                    :avg_comments, :engagement_score, :growth_rate, :metric_version, :collected_at
                )
                """,
                metric_row,
            )

    def insert_anomaly(self, anomaly_row: dict[str, Any]) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO anomalies (
                    source_feed, metric_name, metric_value, baseline_value, z_score,
                    triggered_by, detected_at, news_aligned, explanation_status, metric_version
                ) VALUES (
                    :source_feed, :metric_name, :metric_value, :baseline_value, :z_score,
                    :triggered_by, :detected_at, :news_aligned, :explanation_status, :metric_version
                )
                """,
                anomaly_row,
            )
            return int(cursor.lastrowid)

    def insert_news_match(self, news_row: dict[str, Any]) -> None:
        payload = news_row.copy()
        payload["top_headlines"] = json.dumps(payload["top_headlines"])
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO news_matches (
                    anomaly_id, article_count, top_headlines, checked_at
                ) VALUES (
                    :anomaly_id, :article_count, :top_headlines, :checked_at
                )
                """,
                payload,
            )

    def insert_explanation(self, anomaly_id: int, response_json: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO explanations (
                    anomaly_id, response_json, created_at
                ) VALUES (?, ?, ?)
                """,
                (anomaly_id, json.dumps(response_json), utc_now()),
            )
            conn.execute(
                "UPDATE anomalies SET explanation_status = 'complete' WHERE id = ?",
                (anomaly_id,),
            )

    def update_anomaly_explanation_status(self, anomaly_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE anomalies SET explanation_status = ? WHERE id = ?",
                (status, anomaly_id),
            )

    def update_anomaly_news_alignment(self, anomaly_id: int, news_aligned: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE anomalies SET news_aligned = ? WHERE id = ?",
                (1 if news_aligned else 0, anomaly_id),
            )

    def insert_monitoring_summary(
        self,
        source_scope: str,
        response_json: dict[str, Any],
        story_count: int,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO monitoring_summaries (
                    source_scope, response_json, story_count, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (source_scope, json.dumps(response_json), story_count, utc_now()),
            )

    def get_latest_monitoring_summary_timestamp(self) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT created_at
                FROM monitoring_summaries
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
            return str(row["created_at"]) if row else None

    def upsert_status(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO system_status (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, utc_now()),
            )

    def get_status(self, key: str) -> dict[str, str] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT key, value, updated_at
                FROM system_status
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
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
        with self.connect() as conn:
            conn.execute("DELETE FROM explanations")
            conn.execute("DELETE FROM news_matches")
            conn.execute("DELETE FROM anomalies")
            conn.execute("DELETE FROM aggregated_metrics")
            conn.execute("DELETE FROM monitoring_summaries")
            conn.execute("DELETE FROM hn_story_snapshots")
            conn.execute("DELETE FROM system_status")
            conn.execute(
                """
                DELETE FROM sqlite_sequence
                WHERE name IN (
                    'explanations',
                    'news_matches',
                    'anomalies',
                    'aggregated_metrics',
                    'monitoring_summaries',
                    'hn_story_snapshots'
                )
                """
            )


db = Database()
