from __future__ import annotations

import pandas as pd

from sonar.config import settings
from sonar.db import utc_now

METRICS = ["story_volume", "avg_score", "avg_comments", "engagement_score", "growth_rate"]


def detect_anomalies(metric_history: pd.DataFrame, latest_rows: list[dict]) -> list[dict]:
    if metric_history.empty or not latest_rows:
        return []

    anomalies: list[dict] = []
    latest_frame = pd.DataFrame(latest_rows)

    for source_feed in latest_frame["source_feed"].unique():
        history = metric_history[metric_history["source_feed"] == source_feed].copy()
        if len(history) < settings.anomaly_window:
            continue

        history = history.tail(settings.anomaly_window)
        current = latest_frame[latest_frame["source_feed"] == source_feed].iloc[-1]
        triggered_metrics: list[str] = []
        anomaly_candidates: list[dict] = []

        for metric_name in METRICS:
            series = pd.to_numeric(history[metric_name], errors="coerce").dropna()
            if len(series) < 2:
                continue
            mean_value = float(series.mean())
            std_value = float(series.std(ddof=0))
            metric_value = float(current[metric_name])
            z_score = 0.0 if std_value == 0 else (metric_value - mean_value) / std_value
            if z_score >= settings.anomaly_zscore_threshold:
                triggered_metrics.append(metric_name)
                anomaly_candidates.append(
                    {
                        "source_feed": source_feed,
                        "metric_name": metric_name,
                        "metric_value": round(metric_value, 4),
                        "baseline_value": round(mean_value, 4),
                        "z_score": round(z_score, 4),
                        "metric_version": settings.metric_semantics_version,
                    }
                )

        if triggered_metrics:
            joined = ",".join(triggered_metrics)
            for candidate in anomaly_candidates:
                candidate["triggered_by"] = joined
                candidate["detected_at"] = utc_now()
                candidate["news_aligned"] = 0
                candidate["explanation_status"] = "pending"
                anomalies.append(candidate)

    return anomalies
