"""add spare part purchase suggestions, labor rates and work order cost columns

Revision ID: c2d8f4b6e7a9
Revises: b3c7e9f1a5d4
Create Date: 2026-11-03 06:00:00.000000

设备模块方案C：备件采购联动 + 维修成本核算。
- spare_part_purchase_suggestions：采购建议（安全线扫描自动生成 / 工单申请）
- maintenance_labor_rates：维修工时费率（岗位级/人员级）
- work_orders 加列：labor_cost / external_cost / external_vendor
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2d8f4b6e7a9'
down_revision: str | None = 'b3c7e9f1a5d4'
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
        'spare_part_purchase_suggestions',
        *(_base_columns() + [
            sa.Column(
                'spare_part_id',
                sa.Uuid(),
                sa.ForeignKey('equipment.spare_parts.id'),
                nullable=False,
                comment='备件ID',
            ),
            sa.Column(
                'current_qty', sa.Integer(), nullable=False, comment='生成时库存'
            ),
            sa.Column('safety_qty', sa.Integer(), nullable=False, comment='安全线'),
            sa.Column(
                'suggest_qty', sa.Integer(), nullable=False, comment='建议采购数量'
            ),
            sa.Column(
                'status',
                sa.String(20),
                nullable=False,
                comment='状态',
            ),
            sa.Column(
                'source',
                sa.String(20),
                nullable=False,
                comment='来源：auto扫描/work_order工单/manual手动',
            ),
            sa.Column(
                'source_work_order_id',
                sa.Uuid(),
                sa.ForeignKey('equipment.work_orders.id'),
                nullable=True,
                comment='来源工单ID（source=work_order 时填）',
            ),
            sa.Column(
                'purchase_request_id',
                sa.String(36),
                nullable=True,
                comment='采购申请单ID（提交采购后回填）',
            ),
            sa.Column(
                'purchase_ref',
                sa.String(200),
                nullable=True,
                comment='采购回执摘要（单号/时间，冗余展示）',
            ),
            sa.Column(
                'submitted_by',
                sa.Uuid(),
                sa.ForeignKey('identity.users.id'),
                nullable=True,
                comment='提交人',
            ),
            sa.Column(
                'submitted_at',
                sa.DateTime(timezone=True),
                nullable=True,
                comment='提交时间',
            ),
            sa.Column(
                'arrived_qty',
                sa.Integer(),
                nullable=False,
                server_default=sa.text('0'),
                comment='已到货数量',
            ),
            sa.Column(
                'unit_price',
                sa.Numeric(12, 2),
                nullable=True,
                comment='参考单价快照',
            ),
        ]),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('suggested', 'submitted', 'partial', 'done', 'cancelled')",
            name='ck_spare_part_purchase_suggestions_status',
        ),
        sa.CheckConstraint(
            "source IN ('auto', 'work_order', 'manual')",
            name='ck_spare_part_purchase_suggestions_source',
        ),
        schema='equipment',
    )
    op.create_index(
        'uq_spare_part_purchase_suggestions_open',
        'spare_part_purchase_suggestions',
        ['spare_part_id'],
        unique=True,
        schema='equipment',
        postgresql_where=sa.text(
            "is_deleted = false AND status IN "
            "('suggested', 'submitted', 'partial')"
        ),
    )

    op.create_table(
        'maintenance_labor_rates',
        *(_base_columns() + [
            sa.Column(
                'scope', sa.String(10), nullable=False, comment='范围：role/person'
            ),
            sa.Column(
                'role_id',
                sa.Uuid(),
                nullable=True,
                # 软引用 equipment.equipment_roles（无迁移不建 FK）
                comment='设备角色ID（scope=role，软引用）',
            ),
            sa.Column(
                'person_id',
                sa.Uuid(),
                sa.ForeignKey('identity.users.id'),
                nullable=True,
                comment='人员用户ID（scope=person）',
            ),
            sa.Column(
                'hourly_rate',
                sa.Numeric(10, 2),
                nullable=False,
                comment='时薪（元/小时）',
            ),
            sa.Column('effective_from', sa.Date(), nullable=False, comment='生效日期'),
            sa.Column('remark', sa.String(200), nullable=True, comment='备注'),
        ]),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "scope IN ('role', 'person')",
            name='ck_maintenance_labor_rates_scope',
        ),
        sa.CheckConstraint(
            "(scope = 'role' AND role_id IS NOT NULL) "
            "OR (scope = 'person' AND person_id IS NOT NULL)",
            name='ck_maintenance_labor_rates_target',
        ),
        sa.UniqueConstraint(
            'scope',
            'role_id',
            'person_id',
            'is_deleted',
            name='uq_maintenance_labor_rates_target',
        ),
        schema='equipment',
    )

    op.add_column(
        'work_orders',
        sa.Column(
            'labor_cost',
            sa.Numeric(12, 2),
            nullable=True,
            comment='工时成本（完成时按维修人费率×时长计算）',
        ),
        schema='equipment',
    )
    op.add_column(
        'work_orders',
        sa.Column(
            'external_cost',
            sa.Numeric(12, 2),
            nullable=True,
            comment='外委费用（人工补录）',
        ),
        schema='equipment',
    )
    op.add_column(
        'work_orders',
        sa.Column(
            'external_vendor',
            sa.String(100),
            nullable=True,
            comment='外委厂商',
        ),
        schema='equipment',
    )


def downgrade() -> None:
    op.drop_column('work_orders', 'external_vendor', schema='equipment')
    op.drop_column('work_orders', 'external_cost', schema='equipment')
    op.drop_column('work_orders', 'labor_cost', schema='equipment')
    op.drop_table('maintenance_labor_rates', schema='equipment')
    op.drop_index(
        'uq_spare_part_purchase_suggestions_open',
        table_name='spare_part_purchase_suggestions',
        schema='equipment',
    )
    op.drop_table('spare_part_purchase_suggestions', schema='equipment')
