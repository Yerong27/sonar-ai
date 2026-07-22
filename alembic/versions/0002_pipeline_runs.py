"""Add retry-safe pipeline run tracking and logical uniqueness.

Revision ID: 0002_pipeline_runs
Revises: 0001_initial_schema
Create Date: 2026-07-22

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_pipeline_runs"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("collected_at", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("current_stage", sa.Text(), nullable=False, server_default=sa.text("'starting'")),
        sa.Column("error_stage", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stories_seen", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("stories_inserted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("metrics_inserted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("anomalies_detected", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("briefs_generated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "monitoring_summary_checked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "monitor_gap_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("gap_duration_minutes", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_pipeline_runs_status",
        ),
        sa.UniqueConstraint("run_id", name="uq_pipeline_runs_run_id"),
    )
    op.create_index(
        "idx_pipeline_runs_status_started",
        "pipeline_runs",
        ["status", "started_at"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_aggregated_metrics_logical_window",
        "aggregated_metrics",
        ["source_feed", "window_start", "window_end", "metric_version"],
    )
    op.create_unique_constraint(
        "uq_anomalies_logical_signal",
        "anomalies",
        ["source_feed", "metric_name", "detected_at", "metric_version"],
    )
    op.create_unique_constraint(
        "uq_news_matches_anomaly_id",
        "news_matches",
        ["anomaly_id"],
    )
    op.create_unique_constraint(
        "uq_monitoring_summaries_scope_created",
        "monitoring_summaries",
        ["source_scope", "created_at"],
    )
    op.create_unique_constraint(
        "uq_brief_evidence_run_document",
        "brief_evidence",
        ["ai_run_id", "document_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_brief_evidence_run_document", "brief_evidence", type_="unique")
    op.drop_constraint(
        "uq_monitoring_summaries_scope_created",
        "monitoring_summaries",
        type_="unique",
    )
    op.drop_constraint("uq_news_matches_anomaly_id", "news_matches", type_="unique")
    op.drop_constraint("uq_anomalies_logical_signal", "anomalies", type_="unique")
    op.drop_constraint(
        "uq_aggregated_metrics_logical_window",
        "aggregated_metrics",
        type_="unique",
    )
    op.drop_index("idx_pipeline_runs_status_started", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
