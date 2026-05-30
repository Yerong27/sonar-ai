from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from sonar.config import settings
from sonar.db import utc_now


def build_metric_rows(
    snapshot_window: pd.DataFrame,
    previous_metrics: pd.DataFrame,
    window_end: datetime | None = None,
) -> list[dict]:
    window_end = window_end or datetime.now(timezone.utc)
    window_start = window_end - timedelta(minutes=30)

    frame = snapshot_window.copy()
    if not frame.empty:
        frame["collected_at"] = pd.to_datetime(frame["collected_at"], utc=True)
        frame["score"] = pd.to_numeric(frame["score"], errors="coerce").fillna(0)
        frame["num_comments"] = pd.to_numeric(frame["num_comments"], errors="coerce").fillna(0)

    configured_feeds = [
        feed.strip()
        for feed in settings.hn_story_endpoints
        if feed and feed.strip()
    ]
    observed_feeds = (
        [str(feed) for feed in frame["source_feed"].dropna().unique().tolist()]
        if not frame.empty
        else []
    )
    historical_feeds = (
        [str(feed) for feed in previous_metrics["source_feed"].dropna().unique().tolist()]
        if not previous_metrics.empty
        else []
    )

    feed_order: list[str] = []
    for feed in [*configured_feeds, *observed_feeds, *historical_feeds]:
        if feed not in feed_order:
            feed_order.append(feed)

    rows: list[dict] = []
    for source_feed in feed_order:
        group = frame[frame["source_feed"] == source_feed] if not frame.empty else pd.DataFrame()

        if not group.empty:
            latest_per_story = (
                group.sort_values(["story_id", "collected_at"])
                .drop_duplicates(subset=["story_id"], keep="last")
            )
            story_volume = int(latest_per_story["story_id"].nunique())
            avg_comments = float(latest_per_story["num_comments"].mean()) if story_volume else 0.0
            avg_score = float(latest_per_story["score"].mean()) if story_volume else 0.0
            engagement_score = (
                float((latest_per_story["score"] + latest_per_story["num_comments"]).mean())
                if story_volume
                else 0.0
            )
        else:
            story_volume = 0
            avg_comments = 0.0
            avg_score = 0.0
            engagement_score = 0.0

        prev_volume = 0.0
        if not previous_metrics.empty:
            previous = previous_metrics[previous_metrics["source_feed"] == source_feed]
            if not previous.empty:
                prev_volume = float(previous.iloc[-1]["story_volume"])
        growth_rate = float((story_volume - prev_volume) / prev_volume) if prev_volume else 0.0

        rows.append(
            {
                "source_feed": source_feed,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "story_volume": story_volume,
                "avg_score": round(avg_score, 2),
                "avg_comments": round(avg_comments, 2),
                "engagement_score": round(engagement_score, 2),
                "growth_rate": round(growth_rate, 4),
                "metric_version": settings.metric_semantics_version,
                "collected_at": utc_now(),
            }
        )
    return rows
