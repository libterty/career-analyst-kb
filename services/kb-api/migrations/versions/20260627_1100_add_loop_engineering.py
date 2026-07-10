"""Add loop engineering run, gap, trace and change records.

Revision ID: 20260627_1100
Revises: 20260627_1000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260627_1100"
down_revision = "20260627_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False, unique=True),
        sa.Column("trigger_event", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("dataset_version", sa.String(128), nullable=True),
        sa.Column("model_version", sa.String(128), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("regression", sa.Boolean(), nullable=True),
        sa.Column("result_json", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_eval_runs_status", "eval_runs", ["status"])

    op.create_table(
        "knowledge_gaps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_hash", sa.String(64), nullable=False, index=True),
        sa.Column("redacted_question", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("trigger", sa.String(50), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "eval_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("expected", sa.String(50), nullable=True),
        sa.Column("predicted", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "harness_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("before_text", sa.Text(), nullable=False),
        sa.Column("after_text", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="candidate"),
        sa.Column("metrics", JSONB(), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("harness_changes")
    op.drop_table("eval_traces")
    op.drop_table("knowledge_gaps")
    op.drop_table("eval_runs")
