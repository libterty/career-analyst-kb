"""add max_sessions to users

Revision ID: a1b2c3d4e5f6
Revises: 0a6980e2578f
Create Date: 2026-03-19 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0a6980e2578f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('max_sessions', sa.Integer(), nullable=False, server_default='20'),
    )


def downgrade() -> None:
    op.drop_column('users', 'max_sessions')
