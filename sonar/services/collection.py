from __future__ import annotations

import fcntl
import logging
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from sonar.ai.evidence_briefs import EvidenceBriefGenerator
from sonar.ai.gemini import GeminiExplainer
from sonar.config import settings
from sonar.db import Database, db as default_db
from sonar.ingestion.hackernews_client import HackerNewsIngestionClient
from sonar.ingestion.news_client import NewsValidationClient
from sonar.processing.anomaly import detect_anomalies
from sonar.processing.metrics import build_metric_rows

logger = logging.getLogger(__name__)

_thread_lock = threading.Lock()


@dataclass(frozen=True)
class CollectionCycleResult:
    started_at: str
    collected_at: str
    stories_seen: int
    stories_inserted: int
    metrics_inserted: int
    anomalies_detected: int
    briefs_generated: int
    monitoring_summary_checked: bool
    monitor_gap_flag: bool
    gap_duration_minutes: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _gemini_story_payload(story: dict[str, object]) -> dict[str, object]:
    """Trim summary payload to fields Gemini actually needs for ranking and themes."""
    return {
        "story_id": story.get("story_id"),
        "source_feed": story.get("source_feed"),
        "title": story.get("title"),
        "score": int(story.get("score", 0) or 0),
        "num_comments": int(story.get("num_comments", 0) or 0),
        "created_at": story.get("created_at"),
    }


def _select_explanation_targets(anomalies: list[dict]) -> set[int]:
    """Choose one anomaly per feed/cycle to explain, favoring strongest/highest-signal rows."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for anomaly in anomalies:
        grouped[str(anomaly["source_feed"])].append(anomaly)

    selected_ids: set[int] = set()
    for feed_rows in grouped.values():
        chosen = max(
            feed_rows,
            key=lambda row: (
                len(str(row.get("triggered_by", "")).split(",")),
                float(row.get("z_score", 0.0) or 0.0),
                float(row.get("metric_value", 0.0) or 0.0),
            ),
        )
        selected_ids.add(int(chosen["id"]))
    return selected_ids


class CollectionCycleService:
    """Runs one complete Sonar ingestion, anomaly, validation, and AI brief cycle."""

    def __init__(
        self,
        *,
        database: Database | None = None,
        hackernews: HackerNewsIngestionClient | None = None,
        news: NewsValidationClient | None = None,
        gemini: GeminiExplainer | None = None,
        brief_generator: EvidenceBriefGenerator | None = None,
        lock_path: Path | None = None,
    ) -> None:
        self.database = database or default_db
        self.hackernews = hackernews or HackerNewsIngestionClient()
        self.news = news or NewsValidationClient()
        self.gemini = gemini or GeminiExplainer()
        self.brief_generator = brief_generator or EvidenceBriefGenerator(database=self.database)
        self.lock_path = lock_path or settings.data_dir / "collection.lock"

    def run_once(self) -> CollectionCycleResult:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with _thread_lock:
            with self.lock_path.open("w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    return self._run_unlocked()
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _run_unlocked(self) -> CollectionCycleResult:
        batch_started_at = datetime.now(timezone.utc)
        batch_collected_at = batch_started_at.isoformat()
        last_collection_time = self.database.get_last_collection_time()
        monitor_gap_flag = False
        gap_duration_minutes: int | None = None
        if last_collection_time:
            previous_collection = datetime.fromisoformat(last_collection_time)
            gap = batch_started_at - previous_collection
            if gap.total_seconds() > settings.monitor_gap_threshold_seconds:
                monitor_gap_flag = True
                gap_duration_minutes = int(round(gap.total_seconds() / 60))

        stories = self.hackernews.fetch_latest_stories(collected_at=batch_collected_at)
        for story in stories:
            story["monitor_gap_flag"] = 1 if monitor_gap_flag else 0
            story["gap_duration_minutes"] = gap_duration_minutes
        inserted = self.database.insert_story_snapshots(stories)
        self.database.set_last_collection_time(batch_collected_at)
        logger.info("Collected %s stories, inserted %s new rows", len(stories), inserted)
        self.database.upsert_status("gemini_status", "enabled" if self.gemini.enabled else "disabled")

        window_end = datetime.now(timezone.utc)
        metrics_history = self._load_metric_history()
        snapshot_window = self._load_new_story_window(window_end)
        metric_rows = build_metric_rows(snapshot_window, metrics_history, window_end)
        for row in metric_rows:
            self.database.insert_aggregated_metric(row)

        if metric_rows:
            latest_metrics = pd.DataFrame(metric_rows)
            combined_history = (
                latest_metrics
                if metrics_history.empty
                else pd.concat([metrics_history, latest_metrics], ignore_index=True)
            )
        else:
            combined_history = metrics_history

        anomalies = detect_anomalies(combined_history, metric_rows)
        persisted_anomalies: list[dict] = []
        for anomaly in anomalies:
            anomaly_id = self.database.insert_anomaly(anomaly)
            persisted = anomaly.copy()
            persisted["id"] = anomaly_id
            persisted_anomalies.append(persisted)

        briefs_generated = self._generate_briefs(persisted_anomalies, stories)
        monitoring_summary_checked = self._run_monitoring_summary(stories)

        return CollectionCycleResult(
            started_at=batch_started_at.isoformat(),
            collected_at=batch_collected_at,
            stories_seen=len(stories),
            stories_inserted=inserted,
            metrics_inserted=len(metric_rows),
            anomalies_detected=len(persisted_anomalies),
            briefs_generated=briefs_generated,
            monitoring_summary_checked=monitoring_summary_checked,
            monitor_gap_flag=monitor_gap_flag,
            gap_duration_minutes=gap_duration_minutes,
        )

    def _generate_briefs(self, persisted_anomalies: list[dict], stories: list[dict]) -> int:
        briefs_generated = 0
        explanation_target_ids = _select_explanation_targets(persisted_anomalies)
        for anomaly in persisted_anomalies:
            anomaly_id = int(anomaly["id"])
            if anomaly_id not in explanation_target_ids:
                self.database.update_anomaly_explanation_status(anomaly_id, "suppressed")
                continue

            news_context = self.news.search(
                f"Hacker News {anomaly['source_feed']} {anomaly['metric_name']}"
            )
            self.database.insert_news_match(
                {
                    "anomaly_id": anomaly_id,
                    "article_count": int(news_context["article_count"]),
                    "top_headlines": news_context["top_headlines"],
                    "checked_at": anomaly["detected_at"],
                }
            )

            news_aligned = int(news_context["article_count"]) > 0
            if news_aligned:
                anomaly["news_aligned"] = 1
            self.database.update_anomaly_news_alignment(anomaly_id, news_aligned)

            explanation = self.brief_generator.generate(
                anomaly=anomaly,
                news_context=news_context,
                stories=stories,
            )
            if explanation:
                briefs_generated += 1
                self.database.upsert_status("gemini_status", "ok")
            else:
                self.database.update_anomaly_explanation_status(anomaly_id, "failed")
                if not self.brief_generator.enabled:
                    self.database.upsert_status("gemini_status", "provider_disabled")
        return briefs_generated

    def _load_metric_history(self) -> pd.DataFrame:
        with self.database.connect() as conn:
            return pd.read_sql_query(
                text(
                    """
                    SELECT source_feed, story_volume, avg_score, avg_comments,
                           engagement_score, growth_rate, collected_at
                    FROM aggregated_metrics
                    WHERE metric_version = :metric_version
                    ORDER BY collected_at ASC
                    """
                ),
                conn,
                params={"metric_version": settings.metric_semantics_version},
            )

    def _load_new_story_window(self, window_end: datetime) -> pd.DataFrame:
        window_start = window_end - timedelta(minutes=30)
        with self.database.connect() as conn:
            return pd.read_sql_query(
                text(
                    """
                    WITH first_seen AS (
                        SELECT source_feed, story_id, MIN(collected_at) AS first_seen_at
                        FROM hn_story_snapshots
                        GROUP BY source_feed, story_id
                        HAVING MIN(collected_at) >= :window_start
                    )
                    SELECT s.source_feed, s.story_id, s.score, s.num_comments,
                           s.collected_at, first_seen.first_seen_at
                    FROM hn_story_snapshots s
                    JOIN first_seen
                      ON first_seen.source_feed = s.source_feed
                     AND first_seen.story_id = s.story_id
                    WHERE s.collected_at >= :window_start
                    ORDER BY s.collected_at ASC
                    """
                ),
                conn,
                params={"window_start": window_start.isoformat()},
            )

    def _run_monitoring_summary(self, stories: list[dict]) -> bool:
        if not self.gemini.enabled or not stories:
            return False

        latest_summary_at = self.database.get_latest_monitoring_summary_timestamp()
        if latest_summary_at:
            last_run = datetime.fromisoformat(latest_summary_at)
            elapsed = (datetime.now(timezone.utc) - last_run).total_seconds()
            if elapsed < settings.monitoring_interval_seconds:
                return False

        ranked_stories = sorted(
            stories,
            key=lambda row: (int(row.get("score", 0)) + int(row.get("num_comments", 0))),
            reverse=True,
        )
        sample = [
            _gemini_story_payload(story)
            for story in ranked_stories[: settings.monitoring_story_sample_size]
        ]
        summary = self.gemini.summarize_monitoring_snapshot(sample)
        if summary:
            self.database.insert_monitoring_summary("all_feeds", summary, len(sample))
            self.database.upsert_status("gemini_status", "ok")
            logger.info("Stored Gemini monitoring summary for %s stories", len(sample))
        elif self.gemini.last_error:
            self.database.upsert_status("gemini_status", self.gemini.last_error)
        return True


def run_collection_cycle(service: CollectionCycleService | None = None) -> CollectionCycleResult:
    """Shared task entrypoint for API-triggered and scheduled collection runs."""
    return (service or CollectionCycleService()).run_once()
