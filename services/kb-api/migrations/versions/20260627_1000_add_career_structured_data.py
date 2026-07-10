"""Add structured career role and salary data.

Revision ID: 20260627_1000
Revises: 20260627_0900
"""
from alembic import op
import sqlalchemy as sa

revision = "20260627_1000"
down_revision = "20260627_0900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "career_role_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("role", sa.String(120), nullable=False),
        sa.Column("level", sa.String(50), nullable=False),
        sa.Column("skill", sa.String(120), nullable=False),
        sa.Column("competency", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("role", "level", "skill", name="uq_role_level_skill"),
    )
    op.create_index("ix_career_role_profiles_role", "career_role_profiles", ["role"])
    op.create_index("ix_career_role_profiles_level", "career_role_profiles", ["level"])

    op.create_table(
        "salary_benchmarks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("role", sa.String(120), nullable=False),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("seniority", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("p25", sa.Numeric(14, 2), nullable=False),
        sa.Column("p50", sa.Numeric(14, 2), nullable=False),
        sa.Column("p75", sa.Numeric(14, 2), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "role", "region", "seniority", "currency", "period_start", "period_end",
            name="uq_salary_benchmark_scope",
        ),
    )
    op.create_index("ix_salary_benchmarks_role", "salary_benchmarks", ["role"])
    op.create_index("ix_salary_benchmarks_region", "salary_benchmarks", ["region"])
    op.create_index("ix_salary_benchmarks_seniority", "salary_benchmarks", ["seniority"])


def downgrade() -> None:
    op.drop_table("salary_benchmarks")
    op.drop_table("career_role_profiles")
