"""add system_prompts table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-23 10:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_PROMPT = """你是 BeeInventor 的內部知識助理，名為「BeeBot」。
BeeInventor 是一家專注於建築工地 IoT 安全解決方案的科技公司，產品包含 DasLoop、DasTrack、DasAoA、DasAir、DasGas、DasCAS、DasWater、DasPower 及 DasIoT 平台。
請依據以下從內部文件中擷取的參考段落，以專業、清晰的口吻回答問題。
若參考段落中未包含相關資訊，請誠實說明「內部文件中未有相關記載，建議聯繫對應部門確認」，切勿自行捏造。
回答應以繁體中文撰寫，語調專業而親切。

【參考段落】
{context}
"""


def upgrade() -> None:
    op.create_table(
        'system_prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True, precision=3), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True, precision=3), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_system_prompts_name'),
    )
    op.create_index(op.f('ix_system_prompts_id'), 'system_prompts', ['id'], unique=False)

    # 預設提示詞（啟用狀態）
    op.execute(
        sa.text(
            "INSERT INTO system_prompts (name, content, is_active) VALUES (:name, :content, true)"
        ).bindparams(name="default", content=_DEFAULT_PROMPT)
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_system_prompts_id'), table_name='system_prompts')
    op.drop_table('system_prompts')
