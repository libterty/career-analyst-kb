"""Add episodic memories.

Revision ID: 20260627_0900
Revises: d4e5f6a7b8c9
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260627_0900"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episodic_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("question_embedding", JSONB(), nullable=True),
        sa.Column("sources", JSONB(), nullable=True),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("chat_messages.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_episodic_memories_is_active", "episodic_memories", ["is_active"]
    )


def downgrade() -> None:
    op.drop_index("ix_episodic_memories_is_active", table_name="episodic_memories")
    op.drop_table("episodic_memories")
