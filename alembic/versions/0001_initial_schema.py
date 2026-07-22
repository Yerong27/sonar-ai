"""Create the initial Sonar PostgreSQL schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-22

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def identity_primary_key() -> sa.Column[int]:
    return sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True)


def upgrade() -> None:
    op.create_table(
        "hn_story_snapshots",
        identity_primary_key(),
        sa.Column("story_id", sa.Text(), nullable=False),
        sa.Column("source_feed", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("num_comments", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("permalink", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.Text(), nullable=False),
        sa.Column("monitor_gap_flag", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("gap_duration_minutes", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_hn_story_snapshot_unique",
        "hn_story_snapshots",
        ["story_id", "source_feed", "collected_at"],
        unique=True,
    )
    op.create_index(
        "idx_hn_story_snapshot_feed_time",
        "hn_story_snapshots",
        ["source_feed", "collected_at"],
        unique=False,
    )

    op.create_table(
        "aggregated_metrics",
        identity_primary_key(),
        sa.Column("source_feed", sa.Text(), nullable=False),
        sa.Column("window_start", sa.Text(), nullable=False),
        sa.Column("window_end", sa.Text(), nullable=False),
        sa.Column("story_volume", sa.Integer(), nullable=False),
        sa.Column("avg_score", sa.Float(), nullable=False),
        sa.Column("avg_comments", sa.Float(), nullable=False),
        sa.Column("engagement_score", sa.Float(), nullable=False),
        sa.Column("growth_rate", sa.Float(), nullable=False),
        sa.Column("metric_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("collected_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "anomalies",
        identity_primary_key(),
        sa.Column("source_feed", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("z_score", sa.Float(), nullable=False),
        sa.Column("triggered_by", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.Text(), nullable=False),
        sa.Column("news_aligned", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column(
            "explanation_status",
            sa.Text(),
            nullable=True,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("metric_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "monitoring_summaries",
        identity_primary_key(),
        sa.Column("source_scope", sa.Text(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("story_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "documents",
        identity_primary_key(),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("source", "source_id", name="uq_documents_source_source_id"),
    )
    op.create_index(
        "idx_documents_source_id",
        "documents",
        ["source", "source_id"],
        unique=False,
    )

    op.create_table(
        "system_status",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "news_matches",
        identity_primary_key(),
        sa.Column("anomaly_id", sa.Integer(), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False),
        sa.Column("top_headlines", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["anomaly_id"],
            ["anomalies.id"],
            name="fk_news_matches_anomaly_id_anomalies",
        ),
    )

    op.create_table(
        "explanations",
        identity_primary_key(),
        sa.Column("anomaly_id", sa.Integer(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["anomaly_id"],
            ["anomalies.id"],
            name="fk_explanations_anomaly_id_anomalies",
        ),
        sa.UniqueConstraint("anomaly_id", name="uq_explanations_anomaly_id"),
    )

    op.create_table(
        "document_terms",
        identity_primary_key(),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("terms_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_terms_document_id_documents",
        ),
    )

    op.create_table(
        "ai_runs",
        identity_primary_key(),
        sa.Column("anomaly_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("parsed_json", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["anomaly_id"],
            ["anomalies.id"],
            name="fk_ai_runs_anomaly_id_anomalies",
        ),
    )
    op.create_index(
        "idx_ai_runs_anomaly_created",
        "ai_runs",
        ["anomaly_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "brief_evidence",
        identity_primary_key(),
        sa.Column("ai_run_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("reason_used", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_run_id"],
            ["ai_runs.id"],
            name="fk_brief_evidence_ai_run_id_ai_runs",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_brief_evidence_document_id_documents",
        ),
    )


def downgrade() -> None:
    op.drop_table("brief_evidence")
    op.drop_index("idx_ai_runs_anomaly_created", table_name="ai_runs")
    op.drop_table("ai_runs")
    op.drop_table("document_terms")
    op.drop_table("explanations")
    op.drop_table("news_matches")
    op.drop_table("system_status")
    op.drop_index("idx_documents_source_id", table_name="documents")
    op.drop_table("documents")
    op.drop_table("monitoring_summaries")
    op.drop_table("anomalies")
    op.drop_table("aggregated_metrics")
    op.drop_index("idx_hn_story_snapshot_feed_time", table_name="hn_story_snapshots")
    op.drop_index("idx_hn_story_snapshot_unique", table_name="hn_story_snapshots")
    op.drop_table("hn_story_snapshots")
