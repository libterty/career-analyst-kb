"""add semantic_cache_entries table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-23 10:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'semantic_cache_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cache_key', sa.String(length=64), nullable=False),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('sources_json', sa.Text(), nullable=True),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True, precision=3), nullable=True),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True, precision=3), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cache_key', name='uq_semantic_cache_key'),
    )
    op.create_index(op.f('ix_semantic_cache_entries_id'), 'semantic_cache_entries', ['id'], unique=False)
    op.create_index(op.f('ix_semantic_cache_entries_cache_key'), 'semantic_cache_entries', ['cache_key'], unique=True)
    op.create_index('ix_semantic_cache_expires_at', 'semantic_cache_entries', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_semantic_cache_expires_at', table_name='semantic_cache_entries')
    op.drop_index(op.f('ix_semantic_cache_entries_cache_key'), table_name='semantic_cache_entries')
    op.drop_index(op.f('ix_semantic_cache_entries_id'), table_name='semantic_cache_entries')
    op.drop_table('semantic_cache_entries')
