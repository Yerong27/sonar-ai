from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import os
import re

from dash import Dash, Input, Output, State, dash_table, dcc, html, no_update
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from sonar.config import settings
from sonar.db import db
from sonar.ingestion.collector import SonarCollector
from sonar.utils.logging import configure_logging

configure_logging()

collector = SonarCollector()

FEED_COLORS = {
    "topstories": "#fb923c",
    "newstories": "#38bdf8",
    "beststories": "#c084fc",
}
PLOT_TEMPLATE = "plotly_dark"
TOP_FEED_ENTRY_BUCKET_MINUTES = 30

_assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")
app = Dash(__name__, external_stylesheets=[dbc.themes.DARKLY], assets_folder=_assets_dir)
app.title = "Sonar"
app.config.suppress_callback_exceptions = True


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_frame(query: str, params: tuple | None = None) -> pd.DataFrame:
    with db.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


# ---------------------------------------------------------------------------
# Figure styling
# ---------------------------------------------------------------------------

def _apply_figure_style(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        template=PLOT_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.01)",
        margin=dict(l=24, r=24, t=64, b=24),
        legend_title_text="",
        hovermode="x unified",
        font=dict(color="#d6e1ef", family="Inter, sans-serif"),
        hoverlabel=dict(
            bgcolor="rgba(25, 39, 64, 0.94)",
            bordercolor="rgba(122, 158, 206, 0.18)",
            font=dict(color="#ebf2f9", family="Inter, sans-serif"),
        ),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(148, 163, 184, 0.06)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(148, 163, 184, 0.06)", zeroline=False)

    # Auto-uppercase + center all figure titles
    if fig.layout.title and fig.layout.title.text and not fig.layout.title.text.startswith("<b>"):
        fig.update_layout(
            title=dict(
                text=f"<b>{fig.layout.title.text.upper()}</b>",
                x=0.5,
                xanchor="center",
                font=dict(size=13, color="#46c4f5", family="Inter, sans-serif"),
            )
        )
    return fig


# ---------------------------------------------------------------------------
# Reusable components
# ---------------------------------------------------------------------------

def _metric_card(title: str, value: str, subtitle: str, tone: str = "default") -> dbc.Card:
    children = [
        html.Div(title, className="metric-label"),
        html.Div(value, className=f"metric-value metric-{tone}"),
    ]
    children.append(
        html.Div(
            subtitle or "\u00a0",
            className="metric-subtitle" if subtitle else "metric-subtitle metric-subtitle-placeholder",
        )
    )
    return dbc.Card(
        dbc.CardBody(children),
        className="metric-card",
    )


def _build_story_explorer_snapshot() -> tuple[list[dict], list[dict]]:
    stories = _load_frame(
        """
        SELECT story_id, source_feed, title, score, num_comments, permalink, collected_at
        FROM hn_story_snapshots
        ORDER BY collected_at DESC, score DESC, num_comments DESC
        LIMIT 30
        """
    )
    flag_ids, anomaly_feeds = _load_story_explorer_flag_context()
    rows = _prepare_story_explorer_rows(
        stories,
        flag_ids=flag_ids,
        anomaly_feeds=anomaly_feeds,
        time_field="collected_at",
    )
    return rows, _story_explorer_columns()


def _story_explorer_columns() -> list[dict]:
    return [
        {"name": "Flags", "id": "flag"},
        {"name": "Feed", "id": "source_feed"},
        {"name": "Title", "id": "title"},
        {"name": "Pts", "id": "score"},
        {"name": "💬 Comments", "id": "num_comments"},
        {"name": "Time", "id": "collected_at"},
        {"name": "Link", "id": "permalink", "presentation": "markdown"},
    ]


def _load_story_explorer_flag_context() -> tuple[set[str], set[str]]:
    monitoring = _load_frame(
        """
        SELECT response_json
        FROM monitoring_summaries
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    anomalies = _load_frame(
        f"""
        SELECT source_feed
        FROM anomalies
        WHERE metric_version = {settings.metric_semantics_version}
        ORDER BY detected_at DESC
        LIMIT 20
        """
    )
    flag_ids: set[str] = set()
    if not monitoring.empty:
        mon_p = _safe_json_loads(monitoring.iloc[0]["response_json"])
        flag_ids.update(_coerce_list(mon_p.get("notable_story_ids")))
    anomaly_feeds: set[str] = set(anomalies["source_feed"].unique()) if not anomalies.empty else set()
    return flag_ids, anomaly_feeds


def _prepare_story_explorer_rows(
    stories: pd.DataFrame,
    *,
    flag_ids: set[str],
    anomaly_feeds: set[str],
    time_field: str,
) -> list[dict]:
    if stories.empty:
        return []

    frame = stories.copy()
    frame["permalink"] = frame["permalink"].apply(lambda link: f"[Open]({link})" if link else "")
    frame["_raw_time"] = frame[time_field].astype(str)
    frame["_engagement"] = pd.to_numeric(frame.get("score"), errors="coerce").fillna(0) + pd.to_numeric(
        frame.get("num_comments"), errors="coerce"
    ).fillna(0)
    frame["collected_at"] = frame[time_field].apply(_format_table_timestamp)

    def _flag_row(row):
        sid = str(row.get("story_id", ""))
        if sid in flag_ids:
            return "★"
        if row.get("source_feed", "") in anomaly_feeds:
            return "⚠"
        return ""

    frame["flag"] = frame.apply(_flag_row, axis=1)
    return frame[
        [
            "story_id",
            "flag",
            "source_feed",
            "title",
            "score",
            "num_comments",
            "collected_at",
            "permalink",
            "_raw_time",
            "_engagement",
        ]
    ].to_dict("records")


def _load_ranked_story_window(window_key: str, rank_key: str, feed_scope: str, limit: int = 200) -> list[dict]:
    if window_key == "current":
        rows, _ = _build_story_explorer_snapshot()
        return rows

    cutoff = datetime.now(timezone.utc) - (
        timedelta(hours=24) if window_key == "24h" else timedelta(days=7)
    )
    order_sql_map = {
        "score": "score DESC, num_comments DESC, created_at DESC",
        "comments": "num_comments DESC, score DESC, created_at DESC",
        "engagement": "engagement_score DESC, score DESC, num_comments DESC, created_at DESC",
        "newest": "created_at DESC, score DESC, num_comments DESC",
    }
    order_sql = order_sql_map.get(rank_key, order_sql_map["score"])
    feed_filter_sql = ""
    params: list[object] = [cutoff.isoformat()]
    if feed_scope and feed_scope != "all":
        feed_filter_sql = " AND source_feed = ?"
        params.append(feed_scope)
    params.append(limit)
    stories = _load_frame(
        f"""
        WITH latest_snapshot_per_story AS (
            SELECT story_id,
                   source_feed,
                   title,
                   score,
                   num_comments,
                   permalink,
                   collected_at,
                   created_at,
                   (score + num_comments) AS engagement_score,
                   ROW_NUMBER() OVER (
                       PARTITION BY story_id
                       ORDER BY collected_at DESC,
                                CASE source_feed
                                    WHEN 'topstories' THEN 0
                                    WHEN 'newstories' THEN 1
                                    ELSE 2
                                END,
                                score DESC,
                                num_comments DESC
                   ) AS row_num
            FROM hn_story_snapshots
        )
        SELECT story_id,
               source_feed,
               title,
               score,
               num_comments,
               permalink,
               collected_at,
               created_at,
               engagement_score
        FROM latest_snapshot_per_story
        WHERE row_num = 1
          AND created_at >= ?
          {feed_filter_sql}
        ORDER BY {order_sql}
        LIMIT ?
        """,
        params=tuple(params),
    )
    flag_ids, anomaly_feeds = _load_story_explorer_flag_context()
    return _prepare_story_explorer_rows(
        stories,
        flag_ids=flag_ids,
        anomaly_feeds=anomaly_feeds,
        time_field="created_at",
    )


def _story_window_copy(window_key: str, rank_key: str, feed_scope: str) -> tuple[str, str]:
    window_labels = {
        "current": "Current",
        "24h": "Last 24h",
        "7d": "Last 7d",
    }
    rank_labels = {
        "score": "Highest Score",
        "comments": "Most Comments",
        "engagement": "Highest Engagement",
        "newest": "Newest",
    }
    feed_labels = {
        "all": "All Feeds",
        "topstories": "Top Stories",
        "newstories": "New Stories",
    }
    summary = (
        f"{window_labels.get(window_key, 'Current')} · "
        f"Ranked by {rank_labels.get(rank_key, 'Highest Score')} · "
        f"{feed_labels.get(feed_scope or 'all', 'All Feeds')}"
    )
    if window_key == "current":
        return (
            summary,
            "Latest observed story states in the selected view.",
        )
    window_label = "last 24 hours" if window_key == "24h" else "last 7 days"
    return (
        summary,
        f"Latest known story states for stories created in the {window_label}. Top 200 shown.",
    )


def _sort_story_explorer_frame(frame: pd.DataFrame, rank_key: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    sort_key = rank_key or "score"
    working = frame.copy()
    working["score"] = pd.to_numeric(working["score"], errors="coerce").fillna(0)
    working["num_comments"] = pd.to_numeric(working["num_comments"], errors="coerce").fillna(0)
    working["_engagement"] = pd.to_numeric(working.get("_engagement"), errors="coerce").fillna(
        working["score"] + working["num_comments"]
    )
    working["_raw_time"] = pd.to_datetime(working.get("_raw_time"), utc=True, errors="coerce")

    if sort_key == "comments":
        return working.sort_values(["num_comments", "score", "_raw_time"], ascending=[False, False, False])
    if sort_key == "engagement":
        return working.sort_values(["_engagement", "score", "num_comments", "_raw_time"], ascending=[False, False, False, False])
    if sort_key == "newest":
        return working.sort_values(["_raw_time", "score", "num_comments"], ascending=[False, False, False])
    return working.sort_values(["score", "num_comments", "_raw_time"], ascending=[False, False, False])


def _truncate(text: str, length: int = 60) -> str:
    """Return a truncated string with ellipsis for display; full text used as hover."""
    text = str(text)
    if len(text) <= length:
        return text
    return f"{text[:length - 1].rstrip()}…"


# Change 1 & 9: Format timestamps in the frontend display layer only.
def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_command_timestamp(value: object) -> str:
    parsed = _parse_timestamp(value)
    if not parsed:
        return str(value)
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year} · {parsed.strftime('%H:%M')} UTC"


def _format_table_timestamp(value: object) -> str:
    parsed = _parse_timestamp(value)
    if not parsed:
        return str(value)
    now_utc = datetime.now(timezone.utc)
    if parsed.date() == now_utc.date():
        return f"Today {parsed.strftime('%H:%M')}"
    return f"{parsed.strftime('%b')} {parsed.day} · {parsed.strftime('%H:%M')}"


def _format_window_label(start_value: object, end_value: object) -> str:
    start = _parse_timestamp(start_value)
    end = _parse_timestamp(end_value)
    if not start or not end:
        return "Current monitoring window"
    if start.date() == end.date():
        return f"{start.strftime('%b')} {start.day} · {start.strftime('%H:%M')}–{end.strftime('%H:%M')} UTC"
    return f"{start.strftime('%b')} {start.day} {start.strftime('%H:%M')} → {end.strftime('%b')} {end.day} {end.strftime('%H:%M')} UTC"


def _apply_arrival_recovery_guard(metrics: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, datetime, datetime]]]:
    if metrics.empty:
        return metrics.copy(), []

    frame = metrics.copy()
    frame["collected_at"] = pd.to_datetime(frame["collected_at"], utc=True)
    frame["window_start"] = pd.to_datetime(frame["window_start"], utc=True)
    frame["window_end"] = pd.to_datetime(frame["window_end"], utc=True)
    frame["arrival_trusted"] = True
    frame["arrival_recovery_anchor"] = pd.NaT

    gap_threshold = timedelta(seconds=settings.monitor_gap_threshold_seconds)
    recovery_periods: list[tuple[str, datetime, datetime]] = []
    adjusted_groups: list[pd.DataFrame] = []

    for source_feed, group in frame.sort_values("collected_at").groupby("source_feed", sort=False):
        ordered = group.copy()
        collected = ordered["collected_at"]
        previous = collected.shift(1)
        gap_seconds = (collected - previous).dt.total_seconds()
        recovery_points = collected.where(previous.isna() | (gap_seconds > gap_threshold.total_seconds()))
        ordered["arrival_recovery_anchor"] = recovery_points.ffill()
        ordered["arrival_trusted"] = ordered["window_start"] > ordered["arrival_recovery_anchor"]

        for anchor in recovery_points.dropna().tolist():
            recovery_periods.append(
                (
                    str(source_feed),
                    anchor.to_pydatetime(),
                    (anchor + timedelta(minutes=30)).to_pydatetime(),
                )
            )

        adjusted_groups.append(ordered)

    adjusted = pd.concat(adjusted_groups, ignore_index=True) if adjusted_groups else frame
    return adjusted.sort_values("collected_at"), recovery_periods


def _merge_time_spans(periods: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not periods:
        return []

    ordered = sorted(periods, key=lambda item: item[0])
    merged: list[list[datetime]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1][1] = max(last_end, end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _extract_monitor_gap_spans(snapshot_frame: pd.DataFrame) -> list[tuple[datetime, datetime, int]]:
    if snapshot_frame.empty:
        return []

    flagged = snapshot_frame.copy()
    flagged["monitor_gap_flag"] = pd.to_numeric(
        flagged["monitor_gap_flag"], errors="coerce"
    ).fillna(0)
    flagged = flagged[flagged["monitor_gap_flag"] > 0].copy()
    if flagged.empty:
        return []

    flagged["collected_at"] = pd.to_datetime(flagged["collected_at"], utc=True)
    flagged["gap_duration_minutes"] = pd.to_numeric(
        flagged["gap_duration_minutes"], errors="coerce"
    ).fillna(0).astype(int)
    flagged = (
        flagged.groupby("collected_at", as_index=False)["gap_duration_minutes"]
        .max()
        .sort_values("collected_at")
    )

    spans: list[tuple[datetime, datetime, int]] = []
    for row in flagged.itertuples():
        gap_end = row.collected_at.to_pydatetime()
        gap_minutes = int(row.gap_duration_minutes or 0)
        gap_start = gap_end - timedelta(minutes=gap_minutes)
        spans.append((gap_start, gap_end, gap_minutes))
    return spans


def _add_gap_annotations(
    fig: go.Figure,
    gap_spans: list[tuple[datetime, datetime, int]],
) -> go.Figure:
    for gap_start, gap_end, gap_minutes in gap_spans:
        fig.add_vrect(
            x0=gap_start,
            x1=gap_end,
            fillcolor="rgba(255, 200, 0, 0.08)",
            line_width=0,
            layer="below",
        )
        fig.add_annotation(
            x=gap_start + ((gap_end - gap_start) / 2),
            y=0.98,
            xref="x",
            yref="paper",
            text=f"Monitor gap · {gap_minutes}m",
            showarrow=False,
            font=dict(size=10, color="#facc15", family="Inter, sans-serif"),
            bgcolor="rgba(35, 47, 74, 0.78)",
            bordercolor="rgba(250, 204, 21, 0.16)",
            borderwidth=1,
            borderpad=4,
        )
    return fig


def _bucket_story_creation_activity(snapshot_frame: pd.DataFrame) -> pd.DataFrame:
    if snapshot_frame.empty:
        return pd.DataFrame(
            columns=["bucket_start", "bucket_end", "story_count", "post_gap", "gap_minutes"]
        )

    frame = snapshot_frame[snapshot_frame["source_feed"] == "newstories"].copy()
    if frame.empty:
        return pd.DataFrame(
            columns=["bucket_start", "bucket_end", "story_count", "post_gap", "gap_minutes"]
        )

    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
    frame["collected_at"] = pd.to_datetime(frame["collected_at"], utc=True)
    frame["monitor_gap_flag"] = pd.to_numeric(frame["monitor_gap_flag"], errors="coerce").fillna(0)
    frame["gap_duration_minutes"] = pd.to_numeric(
        frame["gap_duration_minutes"], errors="coerce"
    ).fillna(0)
    first_seen = frame.sort_values(["story_id", "collected_at"]).drop_duplicates(
        subset=["story_id"],
        keep="first",
    )
    first_seen["bucket_start"] = first_seen["created_at"].dt.floor("30min")
    bucketed = (
        first_seen.groupby("bucket_start", as_index=False)
        .agg(
            story_count=("story_id", "nunique"),
            post_gap=("monitor_gap_flag", "max"),
            gap_minutes=("gap_duration_minutes", "max"),
        )
        .sort_values("bucket_start")
    )
    bucketed["bucket_end"] = bucketed["bucket_start"] + pd.Timedelta(minutes=30)
    return bucketed


def _bucket_top_feed_new_entries(snapshot_frame: pd.DataFrame) -> pd.DataFrame:
    if snapshot_frame.empty:
        return pd.DataFrame(
            columns=[
                "bucket_start",
                "bucket_end",
                "story_count",
                "current_size",
                "previous_size",
                "post_gap",
                "gap_minutes",
                "previous_bucket_start",
            ]
        )

    frame = snapshot_frame[snapshot_frame["source_feed"] == "topstories"].copy()
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "bucket_start",
                "bucket_end",
                "story_count",
                "current_size",
                "previous_size",
                "post_gap",
                "gap_minutes",
                "previous_bucket_start",
            ]
        )

    frame["collected_at"] = pd.to_datetime(frame["collected_at"], utc=True)
    frame["monitor_gap_flag"] = pd.to_numeric(frame["monitor_gap_flag"], errors="coerce").fillna(0)
    frame["gap_duration_minutes"] = pd.to_numeric(
        frame["gap_duration_minutes"], errors="coerce"
    ).fillna(0)
    frame["story_id"] = frame["story_id"].astype(str)

    observation_rows: list[dict[str, object]] = []
    previous_story_ids: set[str] | None = None
    previous_bucket_start: pd.Timestamp | None = None

    for observed_at, group in frame.groupby("collected_at", sort=True):
        current_story_ids = set(group["story_id"].dropna().astype(str).unique().tolist())
        current_size = len(current_story_ids)
        previous_size = len(previous_story_ids) if previous_story_ids is not None else 0
        if previous_story_ids is None:
            new_entry_count = 0
        else:
            new_entry_count = len(current_story_ids - previous_story_ids)

        observation_rows.append(
            {
                "observed_at": observed_at,
                "story_count": new_entry_count,
                "current_size": current_size,
                "previous_size": previous_size,
                "post_gap": int(group["monitor_gap_flag"].max() or 0),
                "gap_minutes": int(group["gap_duration_minutes"].max() or 0),
                "previous_bucket_start": previous_bucket_start,
            }
        )
        previous_story_ids = current_story_ids
        previous_bucket_start = observed_at

    observed = pd.DataFrame(observation_rows)
    if observed.empty:
        return pd.DataFrame(
            columns=[
                "bucket_start",
                "bucket_end",
                "story_count",
                "current_size",
                "previous_size",
                "post_gap",
                "gap_minutes",
                "previous_bucket_start",
                "observed_windows",
            ]
        )

    bucket_freq = f"{TOP_FEED_ENTRY_BUCKET_MINUTES}min"
    observed["bucket_start"] = observed["observed_at"].dt.floor(bucket_freq)
    bucketed = (
        observed.groupby("bucket_start", as_index=False)
        .agg(
            story_count=("story_count", "sum"),
            current_size=("current_size", "last"),
            previous_size=("previous_size", "first"),
            post_gap=("post_gap", "max"),
            gap_minutes=("gap_minutes", "max"),
            previous_bucket_start=("previous_bucket_start", "first"),
            observed_windows=("observed_at", "nunique"),
        )
        .sort_values("bucket_start")
    )
    bucketed["bucket_end"] = bucketed["bucket_start"] + pd.Timedelta(minutes=TOP_FEED_ENTRY_BUCKET_MINUTES)
    return bucketed


def _build_gap_hover_labels(
    bucket_frame: pd.DataFrame,
    count_label: str = "Story count",
) -> list[str]:
    labels: list[str] = []
    for row in bucket_frame.itertuples():
        bucket_label = _format_window_label(row.bucket_start, row.bucket_end)
        suffix = ""
        if int(row.post_gap or 0):
            suffix = f"<br>\u26a0 After monitor gap ({int(row.gap_minutes or 0)}m)"
        labels.append(
            f"Time bucket: {bucket_label}<br>"
            f"{count_label}: {int(row.story_count)}"
            f"{suffix}"
        )
    return labels


def _build_story_creation_figure(
    snapshot_frame: pd.DataFrame,
    gap_spans: list[tuple[datetime, datetime, int]],
) -> go.Figure:
    bucketed = _bucket_story_creation_activity(snapshot_frame)
    fig = go.Figure()
    if bucketed.empty:
        fig.update_layout(title="New Stories Created Over Time")
        return _apply_figure_style(fig)

    hover_labels = _build_gap_hover_labels(bucketed, count_label="Stories created")
    fig.add_trace(
        go.Scatter(
            x=bucketed["bucket_start"],
            y=bucketed["story_count"],
            mode="lines+markers",
            name="New Stories Created",
            line=dict(color=FEED_COLORS["newstories"], width=3, shape="spline", smoothing=1.1),
            marker=dict(size=8, color=FEED_COLORS["newstories"]),
            customdata=list(
                zip(
                    bucketed["bucket_start"].map(lambda value: pd.Timestamp(value).isoformat()),
                    bucketed["bucket_end"].map(lambda value: pd.Timestamp(value).isoformat()),
                    ["newstories"] * len(bucketed),
                    bucketed["story_count"].astype(int),
                    ["created"] * len(bucketed),
                )
            ),
            hovertemplate="%{text}<extra></extra>",
            text=hover_labels,
        )
    )
    fig.update_layout(
        title="New Stories Created Over Time",
        height=450,
        showlegend=False,
    )
    x_points = list(bucketed["bucket_start"].tolist()) + [start for start, _, _ in gap_spans] + [end for _, end, _ in gap_spans]
    if x_points:
        fig.update_xaxes(range=[min(x_points), max(x_points)])
    fig.update_xaxes(title="Time")
    fig.update_yaxes(title="Stories")
    fig = _apply_figure_style(fig)
    return _add_gap_annotations(fig, gap_spans)


def _build_top_feed_new_entries_figure(
    snapshot_frame: pd.DataFrame,
    gap_spans: list[tuple[datetime, datetime, int]],
) -> go.Figure:
    bucketed = _bucket_top_feed_new_entries(snapshot_frame)
    fig = go.Figure()
    if bucketed.empty:
        fig.update_layout(title="Top Feed New Entries Over Time")
        return _apply_figure_style(fig)

    hover_labels: list[str] = []
    for row in bucketed.itertuples():
        bucket_label = _format_window_label(row.bucket_start, row.bucket_end)
        prev_size = int(row.previous_size or 0)
        current_size = int(row.current_size or 0)
        observed_windows = int(row.observed_windows or 0)
        suffix = ""
        if int(row.post_gap or 0):
            suffix = f"<br>\u26a0 After monitor gap ({int(row.gap_minutes or 0)}m)"
        hover_labels.append(
            f"Observed bucket: {bucket_label}<br>"
            f"Newly observed top feed stories: {int(row.story_count)}<br>"
            f"Observation windows in bucket: {observed_windows}<br>"
            f"Ending feed snapshot: {current_size} stories<br>"
            f"Starting comparison snapshot: {prev_size} stories"
            f"{suffix}"
        )
    fig.add_trace(
        go.Scatter(
            x=bucketed["bucket_start"],
            y=bucketed["story_count"],
            mode="lines+markers",
            name="Top Feed New Entries",
            # This is a discrete per-window turnover signal, so avoid spline smoothing.
            line=dict(color=FEED_COLORS["topstories"], width=3, shape="linear"),
            marker=dict(size=8, color=FEED_COLORS["topstories"]),
            customdata=list(
                zip(
                    bucketed["bucket_start"].map(lambda value: pd.Timestamp(value).isoformat()),
                    bucketed["bucket_end"].map(lambda value: pd.Timestamp(value).isoformat()),
                    ["topstories"] * len(bucketed),
                    bucketed["story_count"].astype(int),
                    ["new_entries"] * len(bucketed),
                    bucketed["current_size"].astype(int),
                    bucketed["previous_size"].astype(int),
                    bucketed["observed_windows"].astype(int),
                )
            ),
            hovertemplate="%{text}<extra></extra>",
            text=hover_labels,
        )
    )
    fig.update_layout(
        title="Top Feed New Entries Over Time",
        height=450,
        showlegend=False,
    )
    x_points = list(bucketed["bucket_start"].tolist()) + [start for start, _, _ in gap_spans] + [end for _, end, _ in gap_spans]
    if x_points:
        fig.update_xaxes(range=[min(x_points), max(x_points)])
    fig.update_xaxes(title="Observed 30-Minute Window")
    fig.update_yaxes(title="Newly Observed Stories", dtick=1)
    fig = _apply_figure_style(fig)
    return _add_gap_annotations(fig, gap_spans)


def _build_case_brief_summary(norm: dict) -> str:
    bullet_insights = norm.get("bullet_insights") or []
    if bullet_insights:
        return _truncate(str(bullet_insights[0]), 180)
    raw_summary = str(norm.get("raw_summary") or "").strip()
    if raw_summary:
        return _truncate(raw_summary, 180)
    return "Signal remains under review."


def _compact_phrase(text: str, limit: int = 110) -> str:
    text = " ".join(str(text or "").strip().split())
    if not text:
        return ""
    replacements = {
        "Hacker News": "HN",
        "Artificial Intelligence": "AI",
        "Large Language Models": "LLMs",
        "Machine Learning": "ML",
        "Key discussion areas include ": "",
        "Most visible terms: ": "Visible terms: ",
        "The current ": "",
        "The dominant theme is ": "",
        "The primary focus is on ": "",
        "Overall sentiment reads as ": "Sentiment reads ",
        "Sentiment skews ": "Sentiment reads ",
        "sampled stories": "stories",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.strip(" .;,:")
    return _truncate(text, limit) if len(text) > limit else text


def _clean_phrase(text: str) -> str:
    text = " ".join(str(text or "").strip().split())
    if not text:
        return ""
    replacements = {
        "Hacker News": "HN",
        "Artificial Intelligence": "AI",
        "Large Language Models": "LLMs",
        "Machine Learning": "ML",
        "Key discussion areas include ": "",
        "Most visible terms: ": "Visible terms: ",
        "The current ": "",
        "The dominant theme is ": "",
        "The primary focus is on ": "",
        "Overall sentiment reads as ": "Sentiment reads ",
        "Sentiment skews ": "Sentiment reads ",
        "sampled stories": "stories",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.strip(" .;,:")


def _compact_topic_label(text: str, limit: int = 32) -> str:
    compact = _compact_phrase(text, limit)
    compact = compact.replace(" & ", " and ")
    return compact.strip(" .;,:")


def _build_brief_headline(norm: dict) -> str:
    topics = [_compact_topic_label(topic, 28) for topic in norm.get("top_topics", []) if topic]
    topics = [topic for topic in topics if topic]
    if len(topics) >= 2:
        return f"{topics[0]} and {topics[1]} lead HN"
    if topics:
        return f"{topics[0]} leads HN"

    keywords = [_compact_topic_label(keyword, 18) for keyword in norm.get("top_keywords", []) if keyword]
    keywords = [keyword for keyword in keywords if keyword]
    if len(keywords) >= 2:
        return f"{keywords[0]} and {keywords[1]} drive HN"
    if keywords:
        return f"{keywords[0]} drives HN"

    return _clean_headline(str(norm.get("headline_summary") or ""))


def _build_case_brief_lines(norm: dict, triggered_labels: list[str]) -> list[tuple[str, str]]:
    insights = [_clean_phrase(item) for item in (norm.get("bullet_insights") or []) if item]
    changed = insights[0] if insights else _build_case_brief_summary(norm)
    likely_driver = (
        insights[1]
        if len(insights) > 1
        else (
            f"Primary trigger: {', '.join(triggered_labels[:2])}."
            if triggered_labels
            else "Primary trigger: concentrated activity acceleration."
        )
    )
    why_matters = (
        insights[2]
        if len(insights) > 2
        else "Worth watching if the pattern persists or spreads across feeds."
    )
    return [
        ("What changed", changed),
        ("Why likely", likely_driver),
        ("Why it matters", why_matters),
    ]


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_sentiment_figure(sentiment_distribution: dict[str, float]) -> go.Figure:
    sentiment_frame = pd.DataFrame(
        {
            "label": list(sentiment_distribution.keys()),
            "value": list(sentiment_distribution.values()),
        }
    )
    fig = px.bar(
        sentiment_frame,
        x="label",
        y="value",
        color="label",
        title="Sentiment Distribution",
        color_discrete_map={
            "positive": "#34d399",
            "neutral": "#94a3b8",
            "mixed": "#fbbf24",
            "negative": "#f87171",
        },
    )
    fig.update_layout(
        template=PLOT_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.01)",
        margin=dict(l=10, r=10, t=48, b=10),
        showlegend=False,
        font=dict(color="#d6e1ef", family="Inter, sans-serif"),
        hoverlabel=dict(
            bgcolor="rgba(25, 39, 64, 0.94)",
            bordercolor="rgba(122, 158, 206, 0.18)",
            font=dict(color="#ebf2f9", family="Inter, sans-serif"),
        ),
    )
    if fig.layout.title and fig.layout.title.text:
        fig.update_layout(
            title=dict(
                text=f"<b>{fig.layout.title.text.upper()}</b>",
                x=0.5,
                xanchor="center",
                font=dict(size=13, color="#46c4f5", family="Inter, sans-serif"),
            )
        )
    fig.update_xaxes(title=None, showgrid=False)
    fig.update_yaxes(title=None, showgrid=True, gridcolor="rgba(148, 163, 184, 0.06)", zeroline=False)
    return fig


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
    is_related = token_matches >= min_related_matches
    score = token_matches + (1 if token_matches == len(tokens) and len(tokens) > 1 else 0)
    return score, is_related


def _keyword_engagement_weight(score: object, num_comments: object) -> float:
    safe_score = max(float(score or 0), 0.0)
    safe_comments = max(float(num_comments or 0), 0.0)
    score_boost = min(math.log1p(safe_score) / 6.5, 1.0)
    comment_boost = min(math.log1p(safe_comments) / 8.5, 0.85)
    return 1.0 + score_boost + comment_boost


def _build_keyword_signals(keywords: list[str], story_link_map: dict[str, dict]) -> list[dict]:
    signals: list[dict] = []
    for keyword in keywords:
        matched: list[dict] = []
        total_visibility = 0.0
        for story_id, meta in story_link_map.items():
            match_score, is_related = _keyword_match_score(keyword, meta.get("title", ""))
            if not is_related:
                continue
            visibility_boost = _keyword_engagement_weight(meta.get("score"), meta.get("num_comments"))
            total_visibility += match_score * visibility_boost
            matched.append(
                {
                    "story_id": str(story_id),
                    "title": meta["title"],
                    "score": meta["score"],
                    "num_comments": meta["num_comments"],
                    "permalink": meta["permalink"],
                }
            )

        matched.sort(key=lambda s: (s["score"], s["num_comments"]), reverse=True)
        signals.append(
            {
                "keyword": keyword,
                "visibility": round(total_visibility, 1),
                "story_count": len(matched),
                "stories": matched[:8],
            }
        )
    return signals


def _build_keyword_figure(keywords: list[str], story_link_map: dict | None = None, height: int = 320) -> go.Figure:
    if not keywords:
        fig = px.bar(title="Heading Visibility")
        fig.update_layout(height=height)
        return _apply_figure_style(fig)

    keywords = keywords[::-1]
    if story_link_map:
        keyword_signals = _build_keyword_signals(keywords, story_link_map)
        keyword_signals = [signal for signal in keyword_signals if signal["story_count"] > 0]
        if not keyword_signals:
            fig = px.bar(title="Heading Visibility")
            fig.update_layout(height=height)
            return _apply_figure_style(fig)
        keywords = [signal["keyword"] for signal in keyword_signals]
        scores = [max(1, int(signal["visibility"])) for signal in keyword_signals]
        story_counts = [int(signal["story_count"]) for signal in keyword_signals]
    else:
        scores = list(range(len(keywords), 0, -1))
        story_counts = [0 for _ in keywords]

    keyword_frame = pd.DataFrame(
        {
            "keyword": [f"{kw}&nbsp;&nbsp;&nbsp;" for kw in keywords],
            "visibility": scores,
            "story_count": story_counts,
        }
    )

    fig = px.bar(
        keyword_frame,
        x="visibility",
        y="keyword",
        orientation="h",
        title="Heading Visibility",
        color="visibility",
        color_continuous_scale=["#1e3a8a", "#38bdf8", "#7dd3fc"],
        labels={"visibility": "Visibility", "keyword": ""},
    )
    fig.update_traces(
        customdata=keyword_frame[["story_count"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Visibility: %{x:.1f}<br>"
            "Related stories: %{customdata[0]}"
            "<extra></extra>"
        ),
    )
    fig.update_layout(
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=48, b=10),
        height=height
    )
    fig.update_yaxes(tickfont=dict(size=14.5))
    return _apply_figure_style(fig)


def _build_keyword_cloud_figure(
    keywords: list[str],
    scores: list[int],
    story_counts: list[int],
    height: int = 400,
    selected_keyword: str | None = None,
) -> go.Figure:
    """Build a interactive bubble-scatter keyword cloud."""
    n = len(keywords)
    if n == 0:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, autorange=True),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, autorange=True),
            margin=dict(l=0, r=0, t=0, b=0),
            height=height,
            annotations=[
                dict(
                    text="Awaiting keyword data",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(size=13, color="#7284a1", family="Inter, sans-serif"),
                )
            ],
        )
        return fig

    # For sizing/colors, floor scores at 1 so AI-abstracted terms without direct matches still appear
    ranked_terms = sorted(
        zip(keywords, scores, story_counts),
        key=lambda item: max(1, item[1]),
        reverse=True,
    )
    keywords = [item[0] for item in ranked_terms]
    scores = [item[1] for item in ranked_terms]
    story_counts = [item[2] for item in ranked_terms]
    sizing_scores = [max(1, s) for s in scores]
    max_score = max(sizing_scores) if sizing_scores else 1
    norm = [s / max_score for s in sizing_scores]

    # Use a stable, productized slot template for the most prominent keywords.
    # This keeps the cloud deterministic across refreshes while avoiding the
    # awkward crowding and rightward drift of a raw spiral-only layout.
    primary_slots = [
        (0.00, 0.00),
        (-0.28, 0.10),
        (0.25, 0.14),
        (-0.18, -0.24),
        (0.22, -0.24),
        (-0.39, -0.04),
        (0.37, -0.02),
        (0.00, 0.34),
        (0.04, -0.40),
        (-0.30, 0.30),
        (0.28, 0.30),
        (-0.30, -0.34),
        (0.30, -0.34),
    ]
    xs, ys = [], []
    slot_count = min(n, len(primary_slots))
    spread_scale = 1.0 + max(0, min(n - 8, 6)) * 0.035
    for i in range(slot_count):
        slot_x, slot_y = primary_slots[i]
        xs.append(slot_x * spread_scale)
        ys.append(slot_y * spread_scale)

    # Fallback for additional keywords: keep deterministic outer slots without
    # letting the layout turn into a sparse prototype-like ring.
    if n > slot_count:
        extra = n - slot_count
        for i in range(extra):
            angle = -0.55 + i * 2.399963
            radius_progress = math.sqrt((i + 1) / (extra + 1))
            r = 0.46 + radius_progress * 0.18
            xs.append(r * math.cos(angle) * 0.95)
            ys.append((r * math.sin(angle) * 1.04) - 0.05)

    # Keep the dominant bubble effectively unchanged while giving
    # small/medium bubbles a slightly fuller baseline presence.
    marker_sizes = [int(68 + ns * 100) for ns in norm]
    font_sizes = [int(12 + ns * 12) for ns in norm]
    colors = [
        f"rgba({int(20 + ns * 36)}, {int(50 + ns * 139)}, {int(130 + ns * 118)}, {0.45 + ns * 0.35})"
        for ns in norm
    ]

    # Keep only light edge padding so the cloud reads larger and more intentional.
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_span = x_max - x_min
    y_span = y_max - y_min
    x_pad = x_span * 0.08 if x_span > 0 else max(abs(x_min), 1.0) * 0.08
    y_pad = y_span * 0.08 if y_span > 0 else max(abs(y_min), 1.0) * 0.08

    selected_available = bool(selected_keyword) and selected_keyword in set(keywords)

    def _add_cloud_trace(indexes: list[int], *, highlighted: bool) -> None:
        if not indexes:
            return
        fig.add_trace(
            go.Scatter(
                x=[xs[i] for i in indexes],
                y=[ys[i] for i in indexes],
                mode="markers+text",
                text=[keywords[i] for i in indexes],
                textposition="middle center",
                marker=dict(
                    size=[
                        marker_sizes[i] + (24 if highlighted else 0)
                        for i in indexes
                    ],
                    color=[colors[i] for i in indexes],
                    opacity=1.0 if highlighted else (0.24 if selected_available else 0.9),
                    line=dict(
                        width=3 if highlighted else 1.2,
                        color="#bae6fd" if highlighted else "rgba(96, 165, 250, 0.2)",
                    ),
                ),
                textfont=dict(
                    size=[font_sizes[i] + (2 if highlighted else 0) for i in indexes],
                    color="#f8fafc" if highlighted else ("rgba(226, 232, 240, 0.58)" if selected_available else "#e2e8f0"),
                    family="Inter, sans-serif",
                ),
                customdata=[(scores[i], story_counts[i]) for i in indexes],
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Visibility: %{customdata[0]}<br>"
                    "Related stories: %{customdata[1]}"
                    "<extra></extra>"
                ),
            )
        )

    fig = go.Figure()
    if selected_available:
        _add_cloud_trace([i for i, keyword in enumerate(keywords) if keyword != selected_keyword], highlighted=False)
        _add_cloud_trace([i for i, keyword in enumerate(keywords) if keyword == selected_keyword], highlighted=True)
    else:
        _add_cloud_trace(list(range(n)), highlighted=False)

    fig.add_trace(
        go.Scatter(
            x=[x_min - x_pad, x_max + x_pad],
            y=[y_min - y_pad, y_max + y_pad],
            mode="markers",
            marker=dict(size=0, opacity=0),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, autorange=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, autorange=True),
        hoverlabel=dict(
            bgcolor="rgba(23, 36, 59, 0.94)",
            bordercolor="rgba(122, 158, 206, 0.2)",
            font=dict(color="#f8fafc", family="Inter, sans-serif"),
        ),
        dragmode=False,
        showlegend=False,
        height=height,
    )
    return fig


# ---------------------------------------------------------------------------
# Gemini output normalisation
# ---------------------------------------------------------------------------

def _safe_json_loads(raw_json: str) -> dict:
    try:
        payload = json.loads(raw_json)
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _coerce_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _split_brief_insight_items(items: list[str], limit: int = 5) -> list[str]:
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
        if len(parts) <= 1:
            normalized.append(raw)
        else:
            normalized.extend(parts)
        if len(normalized) >= limit:
            break
    cleaned = [_clean_phrase(item) for item in normalized if _clean_phrase(item)]
    return cleaned[:limit]


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool_label(value: object) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return "Yes" if value else "No"
    return "Unknown"


def _build_bullet_insights(payload: dict, story_count: int) -> list[str]:
    bullet_insights = _coerce_list(payload.get("bullet_insights"))
    if bullet_insights:
        return _split_brief_insight_items(bullet_insights, limit=5)

    derived: list[str] = []
    top_topics = _coerce_list(payload.get("top_topics"))
    top_keywords = _coerce_list(payload.get("top_keywords") or payload.get("keywords"))
    sentiment_label = str(payload.get("sentiment_label") or "unknown").title()

    if top_topics:
        derived.append(f"Themes: {', '.join(_compact_topic_label(topic, 24) for topic in top_topics[:3])}.")
    if top_keywords:
        derived.append(f"Visible terms: {', '.join(_compact_topic_label(keyword, 16) for keyword in top_keywords[:5])}.")
    if story_count and story_count > 0:
        derived.append(f"Sentiment reads {sentiment_label.lower()} across {story_count} stories.")
    else:
        derived.append(f"Sentiment reads {sentiment_label.lower()}.")
    return [_clean_phrase(item) for item in derived[:5]]


def _normalize_gemini_output(
    payload: dict,
    story_count: int,
    fallback_triggered_by: list[str] | None = None,
    fallback_news_aligned: object | None = None,
) -> dict:
    top_keywords = _coerce_list(payload.get("top_keywords") or payload.get("keywords"))
    top_topics = _coerce_list(payload.get("top_topics"))
    triggered_by = _coerce_list(payload.get("triggered_by")) or (fallback_triggered_by or [])
    confidence = _coerce_float(payload.get("confidence"))
    short_topics = [_clean_phrase(t) for t in top_topics[:6]]

    headline = str(
        payload.get("headline_summary")
        or payload.get("dominant_theme")
        or payload.get("topic")
        or ""
    ).strip()
    if not headline or headline.lower() in ("unknown", "none"):
        headline = "Landscape assessment pending — insufficient signal for summary."

    dominant = str(
        payload.get("dominant_theme")
        or payload.get("dominant_topic")
        or payload.get("topic")
        or ""
    ).strip()

    return {
        "headline_summary": headline,
        "bullet_insights": _build_bullet_insights(payload, story_count),
        "dominant_topic": dominant if dominant.lower() not in ("", "unknown", "none") else "",
        "sentiment_label": str(payload.get("sentiment_label") or "").title() if str(payload.get("sentiment_label", "")).lower() not in ("", "unknown") else "",
        "confidence": (
            f"{confidence:.0%}"
            if confidence is not None and confidence <= 1
            else (f"{confidence:.1f}" if confidence is not None else "")
        ),
        "is_news_aligned": _coerce_bool_label(payload.get("is_news_aligned", fallback_news_aligned)),
        "triggered_by": triggered_by or ["monitoring_interval"],
        "top_keywords": top_keywords[:10],
        "top_topics": short_topics,
        "notable_stories": _coerce_list(payload.get("notable_story_ids"))[:5],
        "raw_summary": str(payload.get("summary") or ""),
    }


def _graceful(label: str, value: str) -> html.Span | None:
    """Return a badge Span only when the value is meaningful."""
    if str(value).strip() in ("Unknown", "N/A", "None", "", "unknown", "Anomaly", "0", "0%"):
        return None
    return html.Span(f"{label}: {value}", className="insight-badge")


# Feed / metric name → user-friendly event brief title
_FEED_LABELS = {
    "topstories": "Top Stories",
    "newstories": "New Stories",
    "beststories": "Best Stories",
}
_METRIC_LABELS = {
    "avg_score": "Score Surge",
    "avg_comments": "Comment Surge",
    "story_volume": "Arrival Spike",
    "engagement_score": "Engagement Spike",
}
_METRIC_TRIGGER_LABELS = {
    "story_volume": "Arrivals",
    "avg_score": "Avg Score",
    "avg_comments": "Avg Comments",
    "engagement_score": "Engagement",
    "growth_rate": "Growth Rate",
}


def _humanize_event_title(source_feed: str, metric_name: str) -> str:
    """Convert internal feed/metric codes into a readable event brief title."""
    feed = _FEED_LABELS.get(source_feed, source_feed.replace("_", " ").title())
    metric = _METRIC_LABELS.get(metric_name, metric_name.replace("_", " ").title())
    return f"{feed} {metric}"


def _summarize_trigger_metrics(value: object) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"none", "unknown", "n/a"}:
        return "No elevated trigger", "No elevated trigger"

    metrics = []
    for item in raw.split(","):
        key = item.strip()
        if not key:
            continue
        metrics.append(_METRIC_TRIGGER_LABELS.get(key, key.replace("_", " ").title()))

    if not metrics:
        return "No elevated trigger", "No elevated trigger"

    full = ", ".join(metrics)
    if len(metrics) == 1:
        return metrics[0], full
    if len(metrics) == 2:
        return f"{metrics[0]} + {metrics[1]}", full
    return f"{len(metrics)} metrics flagged", full


def _clean_headline(text: str) -> str:
    """Strip verbose AI essay openings from headlines to create monitoring-brief style."""
    text = text.strip()
    if not text or text.lower() in ("unknown", "none"):
        return "Landscape assessment pending — insufficient signal."
    # Strip common AI essay patterns
    _ESSAY_PREFIXES = [
        "The rapid advancement and pervasive impact of ",
        "The current landscape is dominated by ",
        "The current Hacker News landscape is ",
        "The dominant theme is ",
        "The primary focus is on ",
    ]
    for prefix in _ESSAY_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            text = text[0].upper() + text[1:] if text else text
            break
    text = _compact_phrase(text, 96)
    if text.endswith("."):
        text = text[:-1]
    return text


# ---------------------------------------------------------------------------
# Dash Layout
# ---------------------------------------------------------------------------

def serve_layout() -> dbc.Container:
    return dbc.Container(
        [
            dcc.Interval(id="refresh", interval=settings.dashboard_refresh_ms, n_intervals=0),
            dcc.Store(id="session-reset-store", data=None),

            # ── SECTION 1 — Header / Command Center ──────────────
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Sonar", className="hero-kicker"),
                            html.H1("Hacker News signal radar", className="hero-title"),
                            html.P("Live HN signals & AI intent monitoring.", className="hero-copy"),
                        ],
                        md=8,
                        className="hero-title-col",
                    ),
                    dbc.Col(
                        [
                            html.Div(
                                dcc.ConfirmDialogProvider(
                                    id="reset-monitoring-dialog",
                                    message="Clear all local Sonar monitoring data and restart the timeline from a fresh session? This cannot be undone.",
                                    children=html.Button("Reset Session Data", className="hero-reset-button"),
                                ),
                                className="hero-utility-row",
                            ),
                            html.Div(id="status-panel", className="status-panel-shell"),
                        ],
                        md=4,
                        className="hero-status-col",
                    ),
                ],
                className="hero-row align-items-start",
            ),

            # ── SECTION 2 — KPI Row ──────────────────────────────
            dbc.Row(id="metric-cards", className="g-3 mb-3"),

            # ── SECTION 3 — Primary Monitoring ────────────────────
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Row(
                            [
                                dbc.Col(
                                    html.Div(
                                        dcc.Graph(id="created-story-trend", config={"displaylogo": False}),
                                        className="graph-wrapper",
                                    ),
                                    md=6,
                                ),
                                dbc.Col(
                                    html.Div(
                                        dcc.Graph(id="top-feed-activity-trend", config={"displaylogo": False}),
                                        className="graph-wrapper",
                                    ),
                                    md=6,
                                ),
                            ],
                            className="g-3",
                        ),
                        md=8,
                    ),
                    dbc.Col(
                        html.Div(dcc.Graph(id="anomaly-alerts", config={"displaylogo": False}), className="graph-wrapper"),
                        md=4,
                    ),
                ],
                className="g-3 mb-3",
            ),
            dbc.Row(
                [dbc.Col(html.Div(id="trend-story-detail"), md=12)],
                className="g-3 trend-detail-row",
            ),

            # ── SECTION 4 — Evidence (Top Movers) ────────────────
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(dcc.Graph(id="story-deltas", config={"displaylogo": False}), className="graph-wrapper"),
                        md=12,
                    ),
                ],
                className="g-3 mb-3",
            ),

            # ── SECTION 5 — AI Insight Summary ────────────────────
            dcc.Store(id="kw-store", data={}),
            dcc.Store(id="selected-kw", data=None),
            dcc.Store(id="event-brief-state", data={"active_item": None, "user_interacted": False}),
            dcc.Store(id="story-explorer-store", data=[]),
            dbc.Row(
                [dbc.Col(html.Div(id="monitoring-summary"), md=12)],
                className="g-3 mb-3",
            ),

            # ── SECTION 6 — Event Briefs (AI Explanations) ───────
            dbc.Row(
                [dbc.Col(html.Div(id="explanation-cards"), md=12)],
                className="g-3 mb-3",
            ),

            # ── SECTION 7 — Story Explorer ────────────────────────
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div("Story Explorer", className="section-super-title"),
                        html.Div(
                            id="story-explorer-copy",
                            className="story-view-summary mb-1",
                        ),
                        html.Div(id="story-explorer-mode-note", className="story-view-helper mb-3"),
                        # Change 10: Keep the icon legend compact and aligned with the current table semantics.
                        html.Div(
                            "Flags: ★ briefing evidence · ⚠ anomaly-adjacent",
                            className="story-icon-legend mb-2",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div("Time Window", className="story-control-label"),
                                        dcc.Dropdown(
                                            id="story-window-filter",
                                            options=[
                                                {"label": "Current", "value": "current"},
                                                {"label": "Last 24h", "value": "24h"},
                                                {"label": "Last 7d", "value": "7d"},
                                            ],
                                            value="current",
                                            clearable=False,
                                            className="story-filter-dropdown",
                                        ),
                                    ],
                                    className="story-control-group story-control-time",
                                ),
                                html.Div(
                                    [
                                        html.Div("Rank By", className="story-control-label"),
                                        dcc.Dropdown(
                                            id="story-rank-filter",
                                            options=[
                                                {"label": "Highest Score", "value": "score"},
                                                {"label": "Most Comments", "value": "comments"},
                                                {"label": "Highest Engagement", "value": "engagement"},
                                                {"label": "Newest", "value": "newest"},
                                            ],
                                            value="score",
                                            clearable=False,
                                            className="story-filter-dropdown",
                                        ),
                                    ],
                                    className="story-control-group story-control-rank",
                                ),
                                html.Div(
                                    [
                                        html.Div("Feed Scope", className="story-control-label"),
                                        dcc.Dropdown(
                                            id="story-feed-filter",
                                            options=[
                                                {"label": "All Feeds", "value": "all"},
                                                {"label": "Top Stories", "value": "topstories"},
                                                {"label": "New Stories", "value": "newstories"},
                                            ],
                                            value="all",
                                            clearable=False,
                                            className="story-filter-dropdown",
                                        ),
                                    ],
                                    className="story-control-group story-control-feed",
                                ),
                                html.Div(
                                    [
                                        html.Div("Search", className="story-control-label"),
                                        dcc.Input(
                                            id="story-search-input",
                                            type="text",
                                            placeholder="Search titles or keywords",
                                            debounce=True,
                                            className="story-toolbar-input",
                                            style={"width": "100%"},
                                        ),
                                    ],
                                    className="story-control-group story-control-search",
                                ),
                                html.Div(
                                    [
                                        html.Div("Evidence Type", className="story-control-label"),
                                        dcc.Dropdown(
                                            id="story-flag-filter",
                                            options=[
                                                {"label": "All Stories", "value": "all"},
                                                {"label": "Briefing Evidence", "value": "briefing"},
                                                {"label": "Anomaly-Adjacent", "value": "anomaly"},
                                            ],
                                            value="all",
                                            clearable=False,
                                            className="story-filter-dropdown",
                                        ),
                                    ],
                                    className="story-control-group story-control-evidence",
                                ),
                            ],
                            className="story-control-toolbar",
                        ),
                        dash_table.DataTable(
                            id="top-stories-table",
                            data=[],
                            columns=[],
                            page_size=10,
                            sort_action="native",
                            filter_action="none",
                            cell_selectable=False,
                            style_table={"overflowX": "auto", "borderRadius": "8px", "minHeight": "132px"},
                            style_cell={
                                "textAlign": "left",
                                "padding": "8px 10px",
                                "fontFamily": "Inter, sans-serif",
                                "fontSize": "12px",
                                "backgroundColor": "rgba(28, 43, 71, 0.38)",
                                "color": "#c9d5e6",
                                "border": "1px solid rgba(122, 158, 206, 0.08)",
                                "borderLeft": "none",
                                "borderRight": "none",
                                "whiteSpace": "normal",
                                "height": "auto",
                            },
                            style_header={
                                "backgroundColor": "rgba(45, 69, 116, 0.24)",
                                "fontWeight": "600",
                                "color": "#d7e2f0",
                                "border": "1px solid rgba(122, 158, 206, 0.1)",
                                "borderLeft": "none",
                                "borderRight": "none",
                            },
                            style_cell_conditional=[
                                {"if": {"column_id": "flag"}, "width": "42px", "minWidth": "42px", "maxWidth": "42px", "textAlign": "center", "padding": "8px 6px"},
                                {"if": {"column_id": "source_feed"}, "width": "110px", "minWidth": "110px", "maxWidth": "110px"},
                                {"if": {"column_id": "title"}, "width": "46%", "maxWidth": "46%", "overflow": "hidden", "textOverflow": "ellipsis"},
                                {"if": {"column_id": "score"}, "width": "96px", "minWidth": "96px", "maxWidth": "96px", "textAlign": "right"},
                                {"if": {"column_id": "num_comments"}, "width": "120px", "minWidth": "120px", "maxWidth": "120px", "textAlign": "right"},
                                {"if": {"column_id": "collected_at"}, "width": "124px", "minWidth": "124px", "maxWidth": "124px"},
                                {"if": {"column_id": "permalink"}, "width": "84px", "minWidth": "84px", "maxWidth": "84px", "textAlign": "center"},
                            ],
                            style_data_conditional=[
                                {"if": {"row_index": "odd"}, "backgroundColor": "rgba(42, 65, 108, 0.08)"},
                                {"if": {"state": "active"}, "backgroundColor": "rgba(46, 70, 116, 0.22)", "color": "#eaf1f9", "border": "1px solid rgba(70, 196, 245, 0.14)"},
                                {"if": {"state": "selected"}, "backgroundColor": "rgba(46, 70, 116, 0.22)", "color": "#eaf1f9", "border": "1px solid rgba(70, 196, 245, 0.14)"},
                            ],
                            markdown_options={"link_target": "_blank"},
                            tooltip_header={
                                "flag": "Flags: ★ briefing evidence, ⚠ anomaly-adjacent",
                            },
                            css=[
                                {
                                    "selector": "td.focused",
                                    "rule": "background-color: rgba(46, 70, 116, 0.22) !important; color: #eaf1f9 !important; outline: none !important;",
                                },
                                {
                                    "selector": "td.cell--selected",
                                    "rule": "background-color: rgba(46, 70, 116, 0.22) !important; color: #eaf1f9 !important; outline: none !important;",
                                },
                                {
                                    "selector": "td.cell--active",
                                    "rule": "background-color: rgba(46, 70, 116, 0.22) !important; color: #eaf1f9 !important;",
                                },
                                {
                                    "selector": "input.dash-cell-value",
                                    "rule": "background-color: rgba(20, 32, 54, 0.72) !important; color: #eaf1f9 !important; caret-color: #46c4f5 !important;",
                                },
                            ],
                        ),
                    ]
                ),
                className="panel-card story-explorer-card mb-3",
            ),
        ],
        fluid=True,
        className="dashboard-shell py-3",
    )


app.layout = serve_layout


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("status-panel", "children"),
    Output("metric-cards", "children"),
    Output("created-story-trend", "figure"),
    Output("top-feed-activity-trend", "figure"),
    Output("anomaly-alerts", "figure"),
    Output("story-deltas", "figure"),
    Output("story-explorer-store", "data"),
    Output("top-stories-table", "columns"),
    Output("monitoring-summary", "children"),
    Output("explanation-cards", "children"),
    Output("kw-store", "data"),
    Input("refresh", "n_intervals"),
    Input("session-reset-store", "data"),
)
def refresh_dashboard(_: int, __reset_state):

    # ── Data loading ──────────────────────────────────────────
    metrics = _load_frame(
        f"""
        SELECT source_feed, window_start, window_end, collected_at, story_volume, avg_score, avg_comments, engagement_score
        FROM aggregated_metrics
        WHERE metric_version = {settings.metric_semantics_version}
        ORDER BY collected_at ASC
        """
    )
    chart_snapshots = _load_frame(
        """
        SELECT story_id, source_feed, created_at, collected_at,
               COALESCE(monitor_gap_flag, 0) AS monitor_gap_flag,
               COALESCE(gap_duration_minutes, 0) AS gap_duration_minutes
        FROM hn_story_snapshots
        WHERE source_feed IN ('newstories', 'topstories')
        ORDER BY collected_at ASC
        """
    )
    anomalies = _load_frame(
        f"""
        SELECT source_feed, metric_name, metric_value, baseline_value, z_score, detected_at, triggered_by
        FROM anomalies
        WHERE metric_version = {settings.metric_semantics_version}
        ORDER BY detected_at DESC
        LIMIT 20
        """
    )
    story_deltas = _load_frame(
        """
        SELECT title,
               MAX(permalink) AS permalink,
               MAX(score) - MIN(score) AS score_change,
               MAX(num_comments) - MIN(num_comments) AS comment_change
        FROM hn_story_snapshots
        GROUP BY story_id, title
        HAVING COUNT(*) > 1
        ORDER BY score_change DESC, comment_change DESC
        LIMIT 6
        """
    )
    explanations = _load_frame(
        f"""
        SELECT a.source_feed, a.metric_name, e.response_json, e.created_at
        FROM explanations e
        JOIN anomalies a ON a.id = e.anomaly_id
        WHERE a.metric_version = {settings.metric_semantics_version}
        ORDER BY e.created_at DESC
        LIMIT 5
        """
    )
    monitoring = _load_frame(
        """
        SELECT source_scope, response_json, story_count, created_at
        FROM monitoring_summaries
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    story_links = _load_frame(
        """
        SELECT story_id, title, permalink, MAX(score) AS score, MAX(num_comments) AS num_comments
        FROM hn_story_snapshots
        GROUP BY story_id, title, permalink
        ORDER BY MAX(score + num_comments) DESC
        LIMIT 200
        """
    )

    # ── Empty-state guard ─────────────────────────────────────
    if metrics.empty:
        empty_fig = _apply_figure_style(px.line(title="Waiting for the first ingestion cycle"))
        status = dbc.Card(
            dbc.CardBody(
                [
                    html.Div("Pipeline Status", className="status-label"),
                    html.Div("Collecting initial HN snapshots", className="status-title"),
                    html.Div(
                        "The dashboard will populate automatically after the collector writes its first metrics batch.",
                        className="status-copy",
                    ),
                ]
            ),
            className="status-card",
        )
        return (
            status, [], empty_fig, empty_fig, empty_fig, empty_fig, [], [],
            html.P("No monitoring summary yet."),
            html.P("No AI explanations yet."),
            {},
        )

    # ── Metric computation ────────────────────────────────────
    metrics, recovery_periods = _apply_arrival_recovery_guard(metrics)

    if not anomalies.empty:
        anomalies["detected_at"] = pd.to_datetime(anomalies["detected_at"], utc=True)
        if recovery_periods:
            valid_mask = pd.Series(True, index=anomalies.index)
            for source_feed, start, end in recovery_periods:
                valid_mask &= ~(
                    (anomalies["source_feed"] == source_feed)
                    & (anomalies["detected_at"] >= pd.Timestamp(start))
                    & (anomalies["detected_at"] < pd.Timestamp(end))
                )
            anomalies = anomalies[valid_mask].copy()

    display_metrics = metrics.copy()
    display_metrics.loc[~display_metrics["arrival_trusted"], "story_volume"] = pd.NA
    total_story_volume = 0

    # Compute deltas for KPI subtitles
    vol_sub = "Fresh stories observed across monitored feeds"
    previous_total_story_volume = 0
    has_previous_cycle = False
    latest_by_feed = metrics.sort_values("collected_at").groupby("source_feed", as_index=False).tail(1).copy()
    latest_by_feed["display_story_volume"] = latest_by_feed.apply(
        lambda row: int(row["story_volume"]) if bool(row["arrival_trusted"]) else 0,
        axis=1,
    )
    total_story_volume = int(latest_by_feed["display_story_volume"].sum())

    rebuilding_feeds = [
        _FEED_LABELS.get(str(feed), str(feed).replace("_", " ").title())
        for feed in latest_by_feed.loc[~latest_by_feed["arrival_trusted"], "source_feed"].tolist()
    ]

    for _, feed_metrics in metrics.sort_values("collected_at").groupby("source_feed"):
        feed_display = feed_metrics.copy()
        feed_display["display_story_volume"] = feed_display.apply(
            lambda row: int(row["story_volume"]) if bool(row["arrival_trusted"]) else 0,
            axis=1,
        )
        if len(feed_metrics) > 1:
            previous_total_story_volume += int(feed_display.iloc[-2]["display_story_volume"])
            has_previous_cycle = True
        else:
            previous_total_story_volume += int(feed_display.iloc[-1]["display_story_volume"])

    if rebuilding_feeds:
        feeds_label = ", ".join(rebuilding_feeds[:2])
        if len(rebuilding_feeds) > 2:
            feeds_label = f"{feeds_label} +{len(rebuilding_feeds) - 2}"
        vol_sub = f"Rebuilding new-story baseline after monitor gap ({feeds_label})"
    elif has_previous_cycle:
        vol_delta = total_story_volume - previous_total_story_volume
        if vol_delta == 0:
            vol_sub = "Steady versus the previous monitoring window"
        elif vol_delta > 0:
            vol_sub = f"▲ {abs(vol_delta)} more new stories than the previous window"
        else:
            vol_sub = f"▼ {abs(vol_delta)} fewer new stories than the previous window"

    # Anomaly & Gemini metadata
    alert_window_start = datetime.now(timezone.utc) - timedelta(minutes=settings.alert_window_minutes)
    recent_anomalies = anomalies.copy()
    if not recent_anomalies.empty:
        recent_anomalies = recent_anomalies[recent_anomalies["detected_at"] >= pd.Timestamp(alert_window_start)].copy()
    active_anomaly_count = int(len(recent_anomalies))
    gemini_status = db.get_status("gemini_status")
    gemini_status_value = gemini_status["value"] if gemini_status else "unknown"
    gemini_status_updated = gemini_status["updated_at"] if gemini_status else "n/a"

    raw_topic = ""
    dom_topic = "Scanning…"
    last_scan_ts = gemini_status_updated
    if not monitoring.empty:
        mon_row = monitoring.iloc[0]
        mon_payload = _safe_json_loads(mon_row["response_json"])
        raw_topic = mon_payload.get("dominant_theme") or mon_payload.get("dominant_topic") or mon_payload.get("topic") or ""
        dom_topic = _clean_headline(raw_topic) if raw_topic and raw_topic.lower() not in ("unknown", "none", "") else "Not yet classified"
        last_scan_ts = mon_row["created_at"]

    # Determine peak scores from story_links
    top_score = int(story_links["score"].max()) if not story_links.empty else 0
    top_comments = int(story_links["num_comments"].max()) if not story_links.empty else 0

    # ── SECTION 1 — Command Center ────────────────────────────
    sys_health = "STABLE" if active_anomaly_count == 0 else "ALERT MODE"
    health_class = "status-title status-stable-mode" if active_anomaly_count == 0 else "status-title status-alert-mode"
    gemini_dot = "cmd-dot cmd-dot-ok" if gemini_status_value == "ok" else "cmd-dot cmd-dot-warn"

    # Human-readable Gemini status
    _GEMINI_LABELS = {"ok": "Online", "unknown": "Pending", "n/a": "Pending"}
    gemini_display = _GEMINI_LABELS.get(gemini_status_value, gemini_status_value.replace("_", " ").title())

    # Format last scan as relative if possible
    last_scan_display = _format_command_timestamp(last_scan_ts)
    active_feeds = int(metrics["source_feed"].nunique())
    priority_alert = "Monitoring stable across live feeds."
    priority_rule = "No elevated trigger"
    priority_rule_full = "No elevated trigger"
    if not recent_anomalies.empty:
        latest_alert_row = recent_anomalies.sort_values("detected_at").iloc[-1]
        priority_alert = _humanize_event_title(latest_alert_row["source_feed"], latest_alert_row["metric_name"])
        priority_rule, priority_rule_full = _summarize_trigger_metrics(latest_alert_row["triggered_by"])
    alert_window_label = f"last {settings.alert_window_minutes} minute{'s' if settings.alert_window_minutes != 1 else ''}"
    cmd_summary = (
        f"{active_anomaly_count} anomal{'y' if active_anomaly_count == 1 else 'ies'} detected in the {alert_window_label}."
        if active_anomaly_count
        else f"No anomalies detected in the {alert_window_label}."
    )

    status = dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.Span("Command Center", className="status-label"),
                        html.Span(className=gemini_dot),
                    ],
                    className="cmd-header",
                ),
                html.Div(sys_health, className=health_class),
                html.Div(cmd_summary, className="cmd-summary", title=cmd_summary),
                html.Div(
                    [
                        html.Span("Primary Driver", className="cmd-inline-key"),
                        html.Span(priority_alert, className="cmd-inline-value cmd-driver-value", title=priority_alert),
                    ],
                    className="cmd-inline-row cmd-driver-row",
                ),
                html.Div(
                    [
                        html.Span("Focus", className="cmd-inline-key"),
                        html.Span(dom_topic, className="cmd-inline-value", title=str(raw_topic or dom_topic)),
                    ],
                    className="cmd-inline-row cmd-inline-wrap cmd-focus-row",
                    title=str(raw_topic) if not monitoring.empty else "",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(str(active_anomaly_count), className="cmd-signal-value cmd-val-alert" if active_anomaly_count else "cmd-signal-value"),
                                html.Span("Active Alerts", className="cmd-signal-label"),
                            ],
                            className="cmd-signal-item",
                        ),
                        html.Div(
                            [
                                html.Span(
                                    priority_rule,
                                    className="cmd-signal-value cmd-signal-value-wide",
                                    title=priority_rule_full,
                                ),
                                html.Span("Trigger", className="cmd-signal-label"),
                            ],
                            className="cmd-signal-item cmd-signal-item-wide",
                            title=priority_rule_full,
                        ),
                        html.Div(
                            [
                                html.Span(
                                    last_scan_display,
                                    className="cmd-signal-value cmd-signal-value-wide",
                                    title=last_scan_display,
                                ),
                                html.Span("Last Scan", className="cmd-signal-label"),
                            ],
                            className="cmd-signal-item cmd-signal-item-wide",
                        ),
                    ],
                    className="cmd-signal-strip",
                ),
                html.Div(
                    [
                        html.Span(f"{active_feeds} feeds live", className="cmd-footer-pill"),
                        html.Span(f"Gemini {gemini_display}", className="cmd-footer-pill"),
                    ],
                    className="cmd-footer-meta",
                ),
            ],
            className="cmd-card-body",
        ),
        className="status-card hero-status-card cmd-card",
    )

    # ── SECTION 2 — KPI Cards ─────────────────────────────────
    metric_cards = [
        dbc.Col(_metric_card("New Story Volume", str(total_story_volume), vol_sub), md=3),
        dbc.Col(_metric_card("Peak Score", f"{top_score:,}", "Highest observed HN points this window"), md=3),
        dbc.Col(_metric_card("Peak Comments", f"{top_comments:,}", "Highest comment count in this window"), md=3),
        # Change 2: Remove duplicate ACTIVE ALERTS subtitle detail from the KPI card.
        dbc.Col(_metric_card(
            "Active Alerts",
            str(active_anomaly_count),
            "",
            "alert" if active_anomaly_count else "calm",
        ), md=3),
    ]

    # Change 1: split the time-series section into created-time and observed-time views.
    gap_spans = _extract_monitor_gap_spans(chart_snapshots)
    created_story_fig = _build_story_creation_figure(chart_snapshots, gap_spans)
    top_feed_activity_fig = _build_top_feed_new_entries_figure(chart_snapshots, gap_spans)

    # ── Anomaly scatter ───────────────────────────────────────
    if not anomalies.empty:
        anomalies["detected_at"] = pd.to_datetime(anomalies["detected_at"])
        anomalies["severity"] = pd.to_numeric(anomalies["z_score"], errors="coerce").fillna(0).abs()
        anomalies["metric_label"] = anomalies["metric_name"].str.replace("_", " ").str.title()
        anomalies["rule_label"] = anomalies["triggered_by"].str.replace("_", " ").str.title()
        anomalies["alert_label"] = anomalies.apply(
            lambda row: _humanize_event_title(row["source_feed"], row["metric_name"]),
            axis=1,
        )
        anomaly_fig = px.scatter(
            anomalies,
            x="detected_at",
            y="metric_value",
            color="source_feed",
            size="severity",
            title="Anomaly Alerts",
            color_discrete_map=FEED_COLORS,
            labels={
                "detected_at": "Time",
                "metric_value": "Metric Deviation",
                "source_feed": "Feed",
                "severity": "Severity",
            },
        )
        anomaly_fig.update_traces(
            marker=dict(opacity=0.88, line=dict(width=1.25, color="rgba(18, 30, 50, 0.86)")),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Value: %{y:.1f}<br>"
                "Z-Score: %{customdata[1]:.2f}<br>"
                "Rule: %{customdata[2]}<br>"
                "<extra>%{customdata[3]}</extra>"
            ),
            customdata=anomalies[["metric_label", "z_score", "rule_label", "source_feed"]].values,
        )
        latest_alert = anomalies.sort_values("detected_at").iloc[-1]
        latest_trigger_short, latest_trigger_full = _summarize_trigger_metrics(latest_alert["triggered_by"])
        anomaly_fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.01,
            y=1.025,
            xanchor="left",
            yanchor="bottom",
            showarrow=False,
            text=f"Latest: {latest_alert['alert_label']}",
            font=dict(size=10, color="#e2e8f0", family="Inter, sans-serif"),
            bgcolor="rgba(23, 36, 59, 0.8)",
            bordercolor="rgba(122, 158, 206, 0.16)",
            borderwidth=1,
            borderpad=4,
        )
        anomaly_fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.99,
            y=1.025,
            xanchor="right",
            yanchor="bottom",
            showarrow=False,
            text=f"Trigger: {latest_trigger_short}",
            font=dict(size=10, color="#94a3b8", family="Inter, sans-serif"),
            bgcolor="rgba(23, 36, 59, 0.68)",
            bordercolor="rgba(122, 158, 206, 0.08)",
            borderwidth=1,
            borderpad=4,
            hovertext=latest_trigger_full,
        )
    else:
        anomaly_fig = px.scatter(
            pd.DataFrame(columns=["detected_at", "metric_value"]),
            x="detected_at",
            y="metric_value",
            title="Anomaly Alerts",
        )
    anomaly_fig = _apply_figure_style(anomaly_fig)
    anomaly_fig.update_layout(
        margin=dict(l=24, r=24, t=78, b=24),
        title=dict(y=0.96, yanchor="top"),
    )

    # ── SECTION 4 — Top Movers (Evidence) ─────────────────────
    if not story_deltas.empty:
        story_deltas["display_title"] = story_deltas.apply(
            lambda row: (
                f"<a href='{row['permalink']}' target='_blank' "
                f"style='color: #38bdf8; text-decoration: underline;'>"
                f"{_truncate(row['title'], 55)}</a>&nbsp;&nbsp;&nbsp;"
            ),
            axis=1,
        )
        delta_fig = px.bar(
            story_deltas,
            x="score_change",
            y="display_title",
            orientation="h",
            title="Top Movers by Score Gain",
            hover_name="title",
            color="score_change",
            color_continuous_scale=["#1e3a8a", "#38bdf8", "#7dd3fc"],
            labels={"score_change": "Points Gained", "display_title": ""},
        )
        # Change 4: Always show the full story title on hover.
        delta_fig.update_traces(
            customdata=story_deltas[["title"]],
            hovertemplate="<b>%{customdata[0]}</b><br>Points Gained: %{x}<extra></extra>",
        )
    else:
        delta_fig = px.bar(
            pd.DataFrame(columns=["display_title", "score_change"]),
            x="score_change",
            y="display_title",
            orientation="h",
            title="Top Movers by Score Gain",
            labels={"score_change": "Points Gained", "display_title": ""},
        )
    delta_fig = _apply_figure_style(delta_fig)
    delta_fig.update_layout(height=420, coloraxis_showscale=False)
    delta_fig.update_yaxes(autorange="reversed", tickfont=dict(size=14))

    # ── SECTION 5 — AI Insight Summary ────────────────────────
    if monitoring.empty:
        monitoring_message = "Awaiting first semantic scan — landscape summary will appear after the next Gemini analysis cycle."
        if gemini_status_value.startswith("quota_exceeded"):
            monitoring_message = f"Semantic analysis paused — Gemini quota exhausted. Last attempt: {gemini_status_updated}."
        elif gemini_status_value.startswith("api_error"):
            monitoring_message = f"Semantic analysis paused — Gemini API error. Last attempt: {gemini_status_updated}."
        monitoring_node = dbc.Card(
            dbc.CardBody(
                [
                    html.Div("AI Insight Summary", className="section-super-title"),
                    html.Div(monitoring_message, className="section-copy"),
                ]
            ),
            className="panel-card",
        )
        kw_store_data = {}
    else:
        row = monitoring.iloc[0]
        payload = _safe_json_loads(row["response_json"])
        insight = _normalize_gemini_output(payload, int(row["story_count"]))
        sentiment_distribution = payload.get(
            "sentiment_distribution",
            {"positive": 0.0, "neutral": 0.0, "mixed": 0.0, "negative": 0.0},
        )
        story_link_map = {
            str(item.story_id): {
                "title": item.title,
                "permalink": item.permalink,
                "score": int(item.score or 0),
                "num_comments": int(item.num_comments or 0),
            }
            for item in story_links.itertuples()
        }

        # Build keyword → related stories mapping for interactive cloud
        kw_stories_map: dict[str, list[dict]] = {}
        raw_cloud_keywords = insight["top_keywords"][:12]
        keyword_signals = _build_keyword_signals(raw_cloud_keywords, story_link_map)
        keyword_signals = [signal for signal in keyword_signals if signal["story_count"] > 0]
        cloud_keywords = [signal["keyword"] for signal in keyword_signals]
        cloud_scores = [max(1, int(signal["visibility"])) for signal in keyword_signals]
        cloud_story_counts = [int(signal["story_count"]) for signal in keyword_signals]

        for signal in keyword_signals:
            kw_stories_map[signal["keyword"]] = [
                {
                    "title": story["title"],
                    "score": story["score"],
                    "num_comments": story["num_comments"],
                    "permalink": story["permalink"],
                }
                for story in signal["stories"]
            ]

        # 1. Build serializable notable stories for browser Store and default view
        notable_data = []
        for sid in insight["notable_stories"]:
            meta = story_link_map.get(str(sid))
            if meta:
                notable_data.append({
                    "title": meta["title"],
                    "score": meta["score"],
                    "num_comments": meta["num_comments"],
                    "permalink": meta["permalink"],
                })

        display_headline = _build_brief_headline(insight)
        display_bullets = [
            _clean_phrase(item)
            for item in insight["bullet_insights"]
            if str(item).strip()
        ][:3]
        display_topics = [_clean_phrase(topic) for topic in insight["top_topics"][:5]]
        display_focus = _clean_phrase(insight["dominant_topic"])

        # 2. Build the final 3-layer Layout Node
        monitoring_node = dbc.Card(
            dbc.CardBody(
                [
                    html.Div("AI Insight Briefing", className="section-super-title mb-3"),
                    html.H4(display_headline, className="insight-headline mb-3"),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Div(
                                        [
                                            html.Div("Brief Insights", className="insight-chart-title insight-group-title"),
                                            html.Ul(
                                                [html.Li(item, className="insight-bullet") for item in display_bullets]
                                                or [html.Li("Semantic summary pending for this window.", className="insight-bullet")],
                                                className="insight-bullet-list",
                                            ),
                                        ],
                                        className="insight-summary-block insight-summary-block-left",
                                    ),
                                    html.Div(
                                        dcc.Graph(
                                            figure=_build_keyword_figure(insight["top_keywords"], story_link_map, height=300),
                                            config={"displayModeBar": False, "displaylogo": False},
                                            className="monitoring-graph",
                                            style={"height": "100%"},
                                        ),
                                        className="insight-fixed-height-280",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Div("Keyword Explorer", className="insight-chart-title"),
                                                    html.Div(
                                                        "Bubble size reflects visibility across related stories, weighted by HN score and comments.",
                                                        className="insight-panel-hint",
                                                    ),
                                                ],
                                                className="insight-panel-header",
                                            ),
                                            html.Div(
                                                dcc.Graph(
                                                    id="kw-cloud",
                                                    figure=_build_keyword_cloud_figure(cloud_keywords, cloud_scores, cloud_story_counts, height=280),
                                                    config={"displayModeBar": False, "displaylogo": False},
                                                    className="kw-cloud-graph",
                                                    style={"height": "100%"},
                                                ),
                                                className="insight-context-body",
                                            ),
                                        ],
                                        className="insight-panel-stack",
                                    ),
                                ],
                                md=7,
                                className="insight-column-stack",
                                style={"padding": "0 10px"},
                            ),
                            dbc.Col(
                                [
                                    html.Div(
                                        html.Div(
                                            [
                                                html.Div("Ranked Themes", className="insight-chart-title insight-group-title ranked-themes-title"),
                                                html.Div(
                                                    [
                                                        html.Div(
                                                            [
                                                                html.Span(f"{idx}.", className="ranked-theme-rank"),
                                                                html.Span(topic, className="ranked-theme-label"),
                                                            ],
                                                            className="ranked-theme-item",
                                                        )
                                                        for idx, topic in enumerate(display_topics, start=1)
                                                    ]
                                                    or [html.Div("Not yet inferred", className="topic-list-item-muted")],
                                                    className="ranked-themes-list",
                                                ),
                                                html.Div(
                                                    html.Span(
                                                        f"Focus: {display_focus or 'Not yet classified'}",
                                                        className="ranked-focus-tag",
                                                    ),
                                                    className="ranked-focus-wrap",
                                                ),
                                            ],
                                            className="ranked-themes-rail",
                                        ),
                                        className="insight-summary-block insight-summary-block-right",
                                    ),
                                    html.Div(
                                        dcc.Graph(
                                            figure=_apply_figure_style(
                                                px.bar(
                                                    pd.DataFrame({"sentiment": list(sentiment_distribution.keys()), "value": list(sentiment_distribution.values())}),
                                                    x="sentiment", y="value", title="Signal Sentiment", labels={"value": "Ratio", "sentiment": ""},
                                                    color="sentiment", color_discrete_map={"positive": "#10b981", "neutral": "#64748b", "negative": "#ef4444", "mixed": "#f59e0b"}
                                                ).update_layout(height=300, showlegend=False, margin=dict(l=10, r=10, t=40, b=10), font=dict(family="Inter, sans-serif"))
                                            ),
                                            config={"displayModeBar": False, "displaylogo": False},
                                            className="monitoring-graph",
                                            style={"height": "100%"},
                                        ),
                                        className="insight-fixed-height-280",
                                    ),
                                    html.Div(
                                        id="right-context-panel",
                                        className="right-context-panel-fixed insight-panel-stack",
                                        children=_build_notable_panel(notable_data),
                                    ),
                                ],
                                md=5,
                                className="insight-column-stack",
                                style={"padding": "0 10px"},
                            ),
                        ],
                        style={"margin": "0", "padding": "0"},
                    ),

                    html.Details(
                        [
                            html.Summary("View raw Gemini summary", className="json-toggle"),
                            html.Pre(insight["raw_summary"], className="explanation-json"),
                            html.Pre(json.dumps(payload, indent=2), className="explanation-json"),
                        ],
                        className="json-details border-0 pt-0",
                    ),
                ]
            ),
            className="panel-card insight-panel-card h-100",
        )
        kw_store_data = {
            "keywords": kw_stories_map,
            "notable": notable_data,
            "cloud": {
                "keywords": cloud_keywords,
                "scores": cloud_scores,
                "story_counts": cloud_story_counts,
            },
        }

    # ── SECTION 6 — Event Briefs (Accordion) ──────────────────
    explanation_nodes: list = []
    if not explanations.empty:
        # Collect notable story IDs for Story Explorer flagging
        notable_ids_set: set[str] = set()
        if not monitoring.empty:
            mon_p = _safe_json_loads(monitoring.iloc[0]["response_json"])
            notable_ids_set = set(_coerce_list(mon_p.get("notable_story_ids")))

        accordion_items: list = []
        accordion_item_ids: list[str] = []
        for idx, row in enumerate(explanations.itertuples()):
            payload = _safe_json_loads(row.response_json)
            norm = _normalize_gemini_output(
                payload,
                story_count=0,
                fallback_triggered_by=_coerce_list(row.metric_name),
            )
            event_type = str(payload.get("event_type") or "")
            pretty_json = json.dumps(payload, indent=2)
            item_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"event-{row.source_feed}-{row.metric_name}-{row.created_at}").strip("-")

            # Human-readable accordion header
            header_text = _humanize_event_title(row.source_feed, row.metric_name)

            # Triggered-by in human form
            triggered_labels = [t.replace("_", " ").title() for t in norm["triggered_by"]]
            case_lines = _build_case_brief_lines(norm, triggered_labels)
            brief_headline = _clean_phrase(_clean_headline(norm["headline_summary"]))

            # Full expanded body
            body = dbc.CardBody(
                [
                    html.Div(
                        [
                            _graceful("Event Type", event_type),
                            _graceful("Confidence", norm["confidence"]),
                            _graceful("News Aligned", norm["is_news_aligned"]),
                            html.Span(
                                f"Triggered By: {', '.join(triggered_labels)}",
                                className="insight-badge insight-badge-wide",
                            ) if triggered_labels else None,
                        ],
                        className="insight-badge-row event-brief-meta",
                    ),
                    html.Div(brief_headline, className="event-brief-headline"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(label, className="event-brief-line-label"),
                                    html.Span(text, className="event-brief-line-text"),
                                ],
                                className="event-brief-line",
                            )
                            for label, text in case_lines
                        ],
                        className="event-brief-summary",
                    ),
                    html.Div(
                        [html.Span(kw, className="monitoring-chip") for kw in norm["top_keywords"][:3]]
                        or [html.Span("No keywords extracted", className="monitoring-chip monitoring-chip-muted")],
                        className="monitoring-chip-row event-brief-keywords",
                    ),
                    html.Details(
                        [
                            html.Summary("View raw JSON", className="json-toggle"),
                            html.Pre(norm["raw_summary"], className="explanation-json"),
                            html.Pre(pretty_json, className="explanation-json"),
                        ],
                        className="json-details",
                    ),
                ]
            )

            accordion_items.append(
                dbc.AccordionItem(body, title=header_text, item_id=item_id)
            )
            accordion_item_ids.append(item_id)

        active_item = accordion_item_ids[0] if accordion_item_ids else None

        explanation_nodes.append(
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div("Event Briefs", className="section-super-title mb-1"),
                        html.Div(
                            f"{len(accordion_items)} active investigation{'s' if len(accordion_items) != 1 else ''} — open a brief for the short case file.",
                            className="section-copy mb-3",
                        ),
                        # Change 7: Expand the first event brief by default.
                        dbc.Accordion(
                            accordion_items,
                            id="event-briefs-accordion",
                            active_item=active_item,
                            start_collapsed=active_item is None,
                            flush=True,
                        ),
                    ]
                ),
                className="panel-card event-briefs-card",
            )
        )

    # ── SECTION 7 — Story Explorer data ───────────────────────
    story_explorer_rows, columns = _build_story_explorer_snapshot()

    return (
        status,
        metric_cards,
        created_story_fig,
        top_feed_activity_fig,
        anomaly_fig,
        delta_fig,
        story_explorer_rows,
        columns,
        monitoring_node,
        explanation_nodes,
        kw_store_data,
    )


# ---------------------------------------------------------------------------
# Keyword click → Right-column contextual swap
# ---------------------------------------------------------------------------


def _build_notable_panel(notable_data: list[dict]) -> list:
    """Reconstruct the default Notable Stories panel from stored data."""
    rows = []
    for s in notable_data[:20]: # Allow more in Store, layout handles 6 scrollable
        rows.append(
            html.Tr(
                [
                    html.Td(
                        html.A(
                            _truncate(s["title"], 72),
                            href=s["permalink"],
                            target="_blank",
                            className="monitoring-link-inline",
                            title=s["title"],
                        )
                    ),
                    html.Td(f"{s['score']:,}"),
                    html.Td(f"{s['num_comments']:,}"),
                ]
            )
        )
    return [
        html.Div(
            [
                html.Div("Notable Stories", className="insight-chart-title"),
                html.Div("Curated evidence from the active window.", className="insight-panel-hint"),
            ],
            className="insight-panel-header",
        ),
        html.Div(
            html.Table(
                [
                    html.Thead(html.Tr([html.Th("Story"), html.Th("Score"), html.Th("Comments")])),
                    html.Tbody(
                        rows or [html.Tr([html.Td("Insufficient signal", colSpan=3, className="topic-list-item-muted")])]
                    ),
                ],
                className="notable-stories-table",
            ),
            className="investigation-table-container",
            style={"height": "280px"}
        ),
    ]


def _build_keyword_drilldown(keyword: str, stories: list[dict]) -> list:
    """Build the Related Stories panel for a selected keyword."""
    header = [
        html.Div(
            [
                html.Div("Related Stories", className="insight-chart-title"),
                html.Div(
                    f"Matched to “{keyword}” · click the same bubble to reset",
                    className="insight-panel-hint",
                ),
            ],
            className="insight-panel-header",
        ),
    ]
    if not stories:
        return header + [
            html.Div(
                html.Div(
                    f"No stories match \u201c{keyword}\u201d in this window.",
                    className="section-copy",
                    style={"fontSize": "0.82rem"},
                ),
                className="investigation-table-container insight-context-empty",
            ),
        ]
    rows = []
    for s in stories[:20]:
        rows.append(
            html.Tr(
                [
                    html.Td(
                        html.A(
                            _truncate(s["title"], 72),
                            href=s["permalink"],
                            target="_blank",
                            className="monitoring-link-inline",
                            title=s["title"],
                        )
                    ),
                    html.Td(f"{s['score']:,}"),
                    html.Td(f"{s['num_comments']:,}"),
                ]
            )
        )
    return header + [
        html.Div(
            html.Table(
                [
                    html.Thead(html.Tr([html.Th("Story"), html.Th("Score"), html.Th("Comments")])),
                    html.Tbody(rows),
                ],
                className="notable-stories-table",
            ),
            className="investigation-table-container",
            style={"height": "280px"}
        ),
    ]


def _load_created_bucket_stories(bucket_start: str, bucket_end: str) -> pd.DataFrame:
    return _load_frame(
        """
        WITH latest_snapshot AS (
            SELECT story_id, MAX(collected_at) AS latest_collected_at
            FROM hn_story_snapshots
            WHERE source_feed = 'newstories'
            GROUP BY story_id
        )
        SELECT s.story_id,
               s.title,
               s.permalink,
               s.score,
               s.num_comments,
               s.created_at AS event_time
        FROM latest_snapshot
        JOIN hn_story_snapshots s
          ON s.source_feed = 'newstories'
         AND s.story_id = latest_snapshot.story_id
         AND s.collected_at = latest_snapshot.latest_collected_at
        WHERE s.created_at >= ?
          AND s.created_at < ?
        ORDER BY s.created_at DESC, s.score DESC, s.num_comments DESC
        LIMIT 20
        """,
        params=(bucket_start, bucket_end),
    )


def _load_top_feed_new_entry_stories(bucket_start: str, bucket_end: str) -> pd.DataFrame:
    window_rows = _load_frame(
        """
        SELECT story_id, title, permalink, score, num_comments, collected_at
        FROM hn_story_snapshots
        WHERE source_feed = 'topstories'
          AND collected_at >= ?
          AND collected_at < ?
        ORDER BY collected_at ASC, score DESC, num_comments DESC
        """,
        params=(bucket_start, bucket_end),
    )
    if window_rows.empty:
        return pd.DataFrame(
            columns=["story_id", "title", "permalink", "score", "num_comments", "event_time"]
        )

    previous_snapshot = _load_frame(
        """
        SELECT MAX(collected_at) AS previous_collected_at
        FROM hn_story_snapshots
        WHERE source_feed = 'topstories'
          AND collected_at < ?
        """,
        params=(bucket_start,),
    )
    previous_observed_at = str(previous_snapshot.iloc[0]["previous_collected_at"] or "").strip()
    previous_story_ids: set[str] = set()
    if previous_observed_at:
        previous_rows = _load_frame(
            """
            SELECT DISTINCT story_id
            FROM hn_story_snapshots
            WHERE source_feed = 'topstories'
              AND collected_at = ?
            """,
            params=(previous_observed_at,),
        )
        previous_story_ids = set(previous_rows["story_id"].dropna().astype(str).tolist())

    window_rows["story_id"] = window_rows["story_id"].astype(str)
    window_rows["collected_at"] = pd.to_datetime(window_rows["collected_at"], utc=True)

    discovered_rows: list[dict[str, object]] = []
    seen_story_ids: set[str] = set()

    for observed_at, group in window_rows.groupby("collected_at", sort=True):
        snapshot = (
            group.sort_values(["score", "num_comments"], ascending=[False, False])
            .drop_duplicates(subset=["story_id"], keep="first")
        )
        current_story_ids = set(snapshot["story_id"].dropna().astype(str).tolist())
        new_story_ids = current_story_ids - previous_story_ids
        if new_story_ids:
            for item in snapshot.itertuples():
                if item.story_id not in new_story_ids or item.story_id in seen_story_ids:
                    continue
                discovered_rows.append(
                    {
                        "story_id": item.story_id,
                        "title": item.title,
                        "permalink": item.permalink,
                        "score": item.score,
                        "num_comments": item.num_comments,
                        "event_time": observed_at,
                    }
                )
                seen_story_ids.add(item.story_id)
        previous_story_ids = current_story_ids

    if not discovered_rows:
        return pd.DataFrame(
            columns=["story_id", "title", "permalink", "score", "num_comments", "event_time"]
        )

    result = pd.DataFrame(discovered_rows).sort_values(
        ["score", "num_comments", "event_time"],
        ascending=[False, False, False],
    )
    return result.head(20)


def _build_trend_story_panel(
    stories: pd.DataFrame,
    panel_title: str | None = None,
    intro_text: str | None = None,
    count_label: str | None = None,
    bucket_label: str | None = None,
    time_column_label: str = "Time",
) -> html.Div | dbc.Card:
    if not panel_title:
        return html.Div()

    rows: list = []
    if not stories.empty:
        for item in stories.itertuples():
            rows.append(
                html.Tr(
                    [
                        html.Td(
                            html.A(
                                _truncate(item.title, 82),
                                href=item.permalink,
                                target="_blank",
                                className="monitoring-link-inline",
                                title=item.title,
                            )
                        ),
                        html.Td(f"{int(item.score or 0):,}"),
                        html.Td(f"{int(item.num_comments or 0):,}"),
                        html.Td(_format_table_timestamp(item.event_time)),
                    ]
                )
            )

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.Div(panel_title, className="section-title"),
                        html.Button("Close detail", id="trend-story-close", className="trend-story-close"),
                    ],
                    className="trend-story-header",
                ),
                html.Div(
                    [
                        html.Span(count_label or f"{len(stories)} stories", className="cmd-footer-pill"),
                        html.Span(bucket_label or "Current selection", className="cmd-footer-pill"),
                    ],
                    className="cmd-footer-meta mb-2",
                ),
                html.Div(
                    intro_text or "Stories in the selected monitoring window.",
                    className="section-copy mb-3",
                ),
                html.Div(
                    html.Table(
                        [
                            html.Thead(html.Tr([html.Th("Story"), html.Th("Score"), html.Th("Comments"), html.Th(time_column_label)])),
                            html.Tbody(
                                rows
                                or [
                                    html.Tr(
                                        [
                                            html.Td(
                                                "No stories for the selected time bucket.",
                                                colSpan=4,
                                                className="topic-list-item-muted",
                                            )
                                        ]
                                    )
                                ]
                            ),
                        ],
                        className="notable-stories-table",
                    ),
                    className="investigation-table-container trend-story-table-container",
                ),
            ]
        ),
        className="panel-card trend-drilldown-card",
    )


@app.callback(
    Output("trend-story-detail", "children", allow_duplicate=True),
    Input("created-story-trend", "clickData"),
    prevent_initial_call=True,
)
def update_created_story_detail(click_data):
    if not click_data:
        return _build_trend_story_panel(pd.DataFrame())

    point = click_data.get("points", [{}])[0]
    custom = point.get("customdata") or []
    if len(custom) < 5:
        return _build_trend_story_panel(pd.DataFrame())

    bucket_start = str(custom[0])
    bucket_end = str(custom[1])
    story_volume = int(float(custom[3] or 0))
    stories = _load_created_bucket_stories(bucket_start, bucket_end)
    return _build_trend_story_panel(
        stories,
        panel_title="New Stories Created",
        intro_text="Stories created in the selected 30-minute time bucket.",
        count_label=f"{story_volume} stories",
        bucket_label=_format_window_label(bucket_start, bucket_end),
        time_column_label="Created At",
    )


@app.callback(
    Output("trend-story-detail", "children", allow_duplicate=True),
    Input("top-feed-activity-trend", "clickData"),
    prevent_initial_call=True,
)
def update_top_feed_detail(click_data):
    if not click_data:
        return _build_trend_story_panel(pd.DataFrame())

    point = click_data.get("points", [{}])[0]
    custom = point.get("customdata") or []
    if len(custom) < 8:
        return _build_trend_story_panel(pd.DataFrame())

    bucket_start = str(custom[0])
    bucket_end = str(custom[1])
    story_volume = int(float(custom[3] or 0))
    current_size = int(float(custom[5] or 0))
    previous_size = int(float(custom[6] or 0))
    observed_windows = int(float(custom[7] or 0))
    stories = _load_top_feed_new_entry_stories(bucket_start, bucket_end)
    intro_text = (
        "Stories newly observed across the selected 30-minute Top Stories bucket, compared with the immediately previous observed window at each collection step."
    )
    return _build_trend_story_panel(
        stories,
        panel_title="Top Feed New Entries",
        intro_text=f"{intro_text} Observed windows: {observed_windows}. Ending snapshot size: {current_size}. Starting comparison snapshot: {previous_size}.",
        count_label=f"Showing top {len(stories)} of {story_volume} newly observed stories",
        bucket_label=_format_window_label(bucket_start, bucket_end),
        time_column_label="Observed At",
    )


@app.callback(
    Output("trend-story-detail", "children", allow_duplicate=True),
    Output("created-story-trend", "clickData", allow_duplicate=True),
    Output("top-feed-activity-trend", "clickData", allow_duplicate=True),
    Input("trend-story-close", "n_clicks"),
    prevent_initial_call=True,
)
def close_trend_story_detail(n_clicks: int | None):
    if not n_clicks:
        return no_update, no_update, no_update
    return html.Div(), None, None


@app.callback(
    Output("top-stories-table", "data"),
    Input("story-window-filter", "value"),
    Input("story-rank-filter", "value"),
    Input("story-search-input", "value"),
    Input("story-feed-filter", "value"),
    Input("story-flag-filter", "value"),
    Input("story-explorer-store", "data"),
)
def filter_story_explorer(window_filter, rank_filter, search_text, feed_filter, flag_filter, story_rows):
    window_key = window_filter or "current"
    rank_key = rank_filter or "score"
    feed_scope = feed_filter or "all"
    base_rows = (
        story_rows
        if window_key == "current"
        else _load_ranked_story_window(window_key, rank_key, feed_scope)
    )

    if not base_rows:
        return []

    frame = pd.DataFrame(base_rows)
    if frame.empty:
        return []

    frame = _sort_story_explorer_frame(frame, rank_key)

    if feed_scope and feed_scope != "all":
        frame = frame[frame["source_feed"] == feed_scope]

    if flag_filter == "briefing":
        frame = frame[frame["flag"] == "★"]
    elif flag_filter == "anomaly":
        frame = frame[frame["flag"] == "⚠"]

    if search_text:
        terms = [term.strip().lower() for term in str(search_text).split() if term.strip()]
        if terms:
            titles = frame["title"].fillna("").astype(str).str.lower()
            mask = pd.Series(True, index=frame.index)
            for term in terms:
                mask &= titles.str.contains(re.escape(term), na=False)
            frame = frame[mask]

    return frame[
        ["flag", "source_feed", "title", "score", "num_comments", "collected_at", "permalink"]
    ].to_dict("records")


@app.callback(
    Output("story-explorer-copy", "children"),
    Output("story-explorer-mode-note", "children"),
    Input("story-window-filter", "value"),
    Input("story-rank-filter", "value"),
    Input("story-feed-filter", "value"),
)
def update_story_explorer_mode_copy(window_filter, rank_filter, feed_filter):
    window_key = window_filter or "current"
    rank_key = rank_filter or "score"
    feed_scope = feed_filter or "all"
    copy_text, note_text = _story_window_copy(window_key, rank_key, feed_scope)
    return copy_text, note_text


@app.callback(
    Output("session-reset-store", "data"),
    Output("trend-story-detail", "children", allow_duplicate=True),
    Output("created-story-trend", "clickData", allow_duplicate=True),
    Output("top-feed-activity-trend", "clickData", allow_duplicate=True),
    Output("selected-kw", "data", allow_duplicate=True),
    Output("event-brief-state", "data", allow_duplicate=True),
    Input("reset-monitoring-dialog", "submit_n_clicks"),
    prevent_initial_call=True,
)
def reset_monitoring_session(submit_n_clicks: int | None):
    if not submit_n_clicks:
        return no_update, no_update, no_update, no_update, no_update, no_update

    collector.reset_session_data()
    return (
        {"reset_at": datetime.now(timezone.utc).isoformat()},
        html.Div(),
        None,
        None,
        None,
        {"active_item": None, "user_interacted": False},
    )


@app.callback(
    Output("event-brief-state", "data"),
    Input("event-briefs-accordion", "active_item"),
    State("event-brief-state", "data"),
    prevent_initial_call=True,
)
def sync_event_brief_state(active_item, current_state):
    state = current_state if isinstance(current_state, dict) else {}
    state["active_item"] = active_item
    state["user_interacted"] = True
    return state


@app.callback(
    Output("event-briefs-accordion", "active_item", allow_duplicate=True),
    Input("explanation-cards", "children"),
    State("event-brief-state", "data"),
    State("event-briefs-accordion", "active_item"),
    prevent_initial_call=True,
)
def restore_event_brief_state(_explanation_children, state, current_active_item):
    if not isinstance(state, dict):
        return no_update
    if not bool(state.get("user_interacted")):
        return no_update
    desired = state.get("active_item")
    if desired == current_active_item:
        return no_update
    return desired


@app.callback(
    Output("right-context-panel", "children"),
    Output("selected-kw", "data"),
    Output("kw-cloud", "figure"),
    Input("kw-cloud", "clickData"),
    State("kw-store", "data"),
    State("selected-kw", "data"),
    prevent_initial_call=True,
)
def update_right_context(click_data, kw_data, current_kw):
    """Swap the right-column panel between Notable Stories and keyword drill-down."""
    if not kw_data or not click_data:
        return no_update, no_update, no_update

    cloud_meta = kw_data.get("cloud", {})
    cloud_keywords = cloud_meta.get("keywords", [])
    cloud_scores = cloud_meta.get("scores", [])
    cloud_story_counts = cloud_meta.get("story_counts", [])

    keyword = click_data.get("points", [{}])[0].get("text", "")
    if not keyword:
        return no_update, no_update, no_update

    # Click same keyword again → toggle back to Notable Stories
    if keyword == current_kw:
        return (
            _build_notable_panel(kw_data.get("notable", [])),
            None,
            _build_keyword_cloud_figure(cloud_keywords, cloud_scores, cloud_story_counts, height=280),
        )

    # Show drill-down for selected keyword
    stories = kw_data.get("keywords", {}).get(keyword, [])
    return (
        _build_keyword_drilldown(keyword, stories),
        keyword,
        _build_keyword_cloud_figure(cloud_keywords, cloud_scores, cloud_story_counts, height=280, selected_keyword=keyword),
    )


def run() -> None:
    collector.start()
    app.run(host=settings.dashboard_host, port=settings.dashboard_port, debug=False)
