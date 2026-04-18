"""add message feedback table

Revision ID: a1b2c3d4e5f6
Revises: add_max_sessions_to_users
Create Date: 2026-03-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'  # add_max_sessions_to_users
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'message_feedbacks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.String(length=8), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True, precision=3), nullable=True),
        sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'user_id', name='uq_feedback_message_user'),
    )
    op.create_index(op.f('ix_message_feedbacks_id'), 'message_feedbacks', ['id'], unique=False)
    op.create_index(op.f('ix_message_feedbacks_message_id'), 'message_feedbacks', ['message_id'], unique=False)
    op.create_index(op.f('ix_message_feedbacks_user_id'), 'message_feedbacks', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_message_feedbacks_user_id'), table_name='message_feedbacks')
    op.drop_index(op.f('ix_message_feedbacks_message_id'), table_name='message_feedbacks')
    op.drop_index(op.f('ix_message_feedbacks_id'), table_name='message_feedbacks')
    op.drop_table('message_feedbacks')
