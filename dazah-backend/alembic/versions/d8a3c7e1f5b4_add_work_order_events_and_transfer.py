"""add work order events and transfer count

Revision ID: d8a3c7e1f5b4
Revises: c5f1a8d3b6e2
Create Date: 2026-11-04 07:00:00.000000

设备模块方案E：工单事件流水（时间线/审计唯一事实源）+ 转派支持。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd8a3c7e1f5b4'
down_revision: str | None = 'c5f1a8d3b6e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column(
            'is_deleted',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        'work_order_events',
        *(_base_columns() + [
            sa.Column(
                'work_order_id',
                sa.Uuid(),
                sa.ForeignKey('equipment.work_orders.id'),
                nullable=False,
                comment='工单ID',
            ),
            sa.Column(
                'event_type',
                sa.String(30),
                nullable=False,
                comment=(
                    'created/assigned/transferred/started/completed/verified/'
                    'rejected/closed/claimed/material_requested/suggested_purchase'
                ),
            ),
            sa.Column(
                'operator_id',
                sa.Uuid(),
                nullable=True,
                comment='操作人（空=系统）',
            ),
            sa.Column(
                'operator_name', sa.String(100), nullable=True,
                comment='操作人姓名',
            ),
            sa.Column(
                'source',
                sa.String(20),
                nullable=False,
                server_default='web',
                comment='来源：web/feishu/voice/scheduler/system',
            ),
            sa.Column(
                'message_id',
                sa.String(64),
                nullable=True,
                comment='关联卡片消息ID（更新原卡片用）',
            ),
            sa.Column(
                'detail',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment='事件附加信息（如转派 from/to/reason）',
            ),
        ]),
        sa.PrimaryKeyConstraint('id'),
        schema='equipment',
    )
    op.create_index(
        'idx_work_order_events_order',
        'work_order_events',
        ['work_order_id', 'created_at'],
        schema='equipment',
    )

    op.add_column(
        'work_orders',
        sa.Column(
            'transfer_count',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),
            comment='转派次数',
        ),
        schema='equipment',
    )


def downgrade() -> None:
    op.drop_column('work_orders', 'transfer_count', schema='equipment')
    op.drop_index(
        'idx_work_order_events_order',
        table_name='work_order_events',
        schema='equipment',
    )
    op.drop_table('work_order_events', schema='equipment')
