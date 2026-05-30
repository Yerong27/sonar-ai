from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd

from sonar.ai.gemini import GeminiExplainer
from sonar.config import settings
from sonar.db import db
from sonar.ingestion.hackernews_client import HackerNewsIngestionClient
from sonar.ingestion.news_client import NewsValidationClient
from sonar.processing.anomaly import detect_anomalies
from sonar.processing.metrics import build_metric_rows

logger = logging.getLogger(__name__)


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


class SonarCollector:
    def __init__(self) -> None:
        self.hackernews = HackerNewsIngestionClient()
        self.news = NewsValidationClient()
        self.gemini = GeminiExplainer()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._run_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def run_once(self) -> None:
        with self._run_lock:
            # Gap detection: treats monitoring reliability as a system signal
            batch_started_at = datetime.now(timezone.utc)
            batch_collected_at = batch_started_at.isoformat()
            last_collection_time = db.get_last_collection_time()
            monitor_gap_flag = False
            gap_duration_minutes: int | None = None
            if last_collection_time:
                previous_collection = datetime.fromisoformat(last_collection_time)
                gap = batch_started_at - previous_collection
                if gap.total_seconds() > settings.monitor_gap_threshold_seconds:
                    monitor_gap_flag = True
                    gap_duration_minutes = int(round(gap.total_seconds() / 60))

            # Pull fresh Hacker News snapshots first so downstream steps see one consistent batch.
            # Change 2: stamp the batch so downstream charts can distinguish post-gap observations.
            stories = self.hackernews.fetch_latest_stories(collected_at=batch_collected_at)
            for story in stories:
                story["monitor_gap_flag"] = 1 if monitor_gap_flag else 0
                story["gap_duration_minutes"] = gap_duration_minutes
            inserted = db.insert_story_snapshots(stories)
            db.set_last_collection_time(batch_collected_at)
            logger.info("Collected %s stories, inserted %s new rows", len(stories), inserted)
            db.upsert_status("gemini_status", "enabled" if self.gemini.enabled else "disabled")

            window_end = datetime.now(timezone.utc)
            metrics_history = self._load_metric_history()
            snapshot_window = self._load_new_story_window(window_end)
            metric_rows = build_metric_rows(snapshot_window, metrics_history, window_end)
            for row in metric_rows:
                db.insert_aggregated_metric(row)

            # Combine persisted history with the newest batch for anomaly scoring.
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
                anomaly_id = db.insert_anomaly(anomaly)
                persisted = anomaly.copy()
                persisted["id"] = anomaly_id
                persisted_anomalies.append(persisted)

            explanation_target_ids = _select_explanation_targets(persisted_anomalies)
            for anomaly in persisted_anomalies:
                anomaly_id = int(anomaly["id"])
                if anomaly_id not in explanation_target_ids:
                    db.update_anomaly_explanation_status(anomaly_id, "suppressed")
                    continue

                news_context = self.news.search(
                    f"Hacker News {anomaly['source_feed']} {anomaly['metric_name']}"
                )
                db.insert_news_match(
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
                db.update_anomaly_news_alignment(anomaly_id, news_aligned)

                explanation = self.gemini.explain(anomaly, news_context)
                if explanation:
                    db.insert_explanation(anomaly_id, explanation)
                else:
                    db.update_anomaly_explanation_status(anomaly_id, "failed")
                    if self.gemini.last_error:
                        db.upsert_status("gemini_status", self.gemini.last_error)

            self._run_monitoring_summary(stories)

    def reset_session_data(self) -> None:
        with self._run_lock:
            db.reset_monitoring_session()
            logger.info("Reset Sonar monitoring session data")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.exception("Collector cycle failed: %s", exc)
            self._stop_event.wait(settings.poll_interval_seconds)

    @staticmethod
    def _load_metric_history() -> pd.DataFrame:
        with db.connect() as conn:
            return pd.read_sql_query(
                """
                SELECT source_feed, story_volume, avg_score, avg_comments,
                       engagement_score, growth_rate, collected_at
                FROM aggregated_metrics
                WHERE metric_version = ?
                ORDER BY collected_at ASC
                """,
                conn,
                params=(settings.metric_semantics_version,),
            )

    @staticmethod
    def _load_new_story_window(window_end: datetime) -> pd.DataFrame:
        window_start = window_end - timedelta(minutes=30)
        with db.connect() as conn:
            return pd.read_sql_query(
                """
                WITH first_seen AS (
                    SELECT source_feed, story_id, MIN(collected_at) AS first_seen_at
                    FROM hn_story_snapshots
                    GROUP BY source_feed, story_id
                    HAVING MIN(collected_at) >= ?
                )
                SELECT s.source_feed, s.story_id, s.score, s.num_comments,
                       s.collected_at, first_seen.first_seen_at
                FROM hn_story_snapshots s
                JOIN first_seen
                  ON first_seen.source_feed = s.source_feed
                 AND first_seen.story_id = s.story_id
                WHERE s.collected_at >= ?
                ORDER BY s.collected_at ASC
                """,
                conn,
                params=(window_start.isoformat(), window_start.isoformat()),
            )

    def _run_monitoring_summary(self, stories: list[dict]) -> None:
        if not self.gemini.enabled or not stories:
            return

        latest_summary_at = db.get_latest_monitoring_summary_timestamp()
        if latest_summary_at:
            last_run = datetime.fromisoformat(latest_summary_at)
            elapsed = (datetime.now(timezone.utc) - last_run).total_seconds()
            if elapsed < settings.monitoring_interval_seconds:
                return

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
            db.insert_monitoring_summary("all_feeds", summary, len(sample))
            db.upsert_status("gemini_status", "ok")
            logger.info("Stored Gemini monitoring summary for %s stories", len(sample))
        elif self.gemini.last_error:
            db.upsert_status("gemini_status", self.gemini.last_error)
