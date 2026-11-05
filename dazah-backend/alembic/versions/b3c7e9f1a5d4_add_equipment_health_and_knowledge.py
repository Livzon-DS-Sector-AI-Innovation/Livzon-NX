"""add equipment health snapshots, repair profiles, knowledge cases and monthly reports

Revision ID: b3c7e9f1a5d4
Revises: 9af3c6bb8778
Create Date: 2026-11-03 10:00:00.000000

设备模块方案B：设备健康档案 + AI 维修知识库。
- equipment_health_snapshots：健康度每日快照（评分 + 分项指标 JSON）
- repair_profiles：维修病历冗余聚合表（每设备一行，闭环触发更新）
- repair_knowledge_cases：维修知识案例库（draft → verified/dismissed）
- equipment_monthly_reports：月度健康报告（SQL 聚合 + LLM 叙述）
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3c7e9f1a5d4'
down_revision: str | None = '9af3c6bb8778'
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
        'equipment_health_snapshots',
        *(_base_columns() + [
            sa.Column(
                'equipment_id',
                sa.Uuid(),
                sa.ForeignKey('equipment.equipments.id'),
                nullable=False,
                comment='设备ID',
            ),
            sa.Column('snapshot_date', sa.Date(), nullable=False, comment='快照日期'),
            sa.Column(
                'score',
                sa.Numeric(5, 2),
                nullable=False,
                comment='健康度评分 0-100',
            ),
            sa.Column(
                'grade', sa.String(1), nullable=False, comment='分档：G绿/Y黄/R红'
            ),
            sa.Column(
                'metrics',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment=(
                    '分项指标：fault_count_90d/mttr_min_90d/overdue_maintenance_count/'
                    'overdue_calibration_count/max_repeat_fault_90d 及各分项罚分'
                ),
            ),
        ]),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'equipment_id',
            'snapshot_date',
            'is_deleted',
            name='uq_equipment_health_snapshot_date',
        ),
        sa.CheckConstraint(
            'score >= 0 AND score <= 100',
            name='ck_equipment_health_snapshots_score',
        ),
        sa.CheckConstraint(
            "grade IN ('G', 'Y', 'R')",
            name='ck_equipment_health_snapshots_grade',
        ),
        schema='equipment',
    )
    op.create_index(
        'idx_equipment_health_snapshots_equipment',
        'equipment_health_snapshots',
        ['equipment_id', 'snapshot_date'],
        schema='equipment',
    )

    op.create_table(
        'repair_profiles',
        *(_base_columns() + [
            sa.Column(
                'equipment_id',
                sa.Uuid(),
                sa.ForeignKey('equipment.equipments.id'),
                nullable=False,
                comment='设备ID（一台设备一行）',
            ),
            sa.Column(
                'total_orders', sa.Integer(), nullable=False, comment='累计工单数'
            ),
            sa.Column(
                'total_faults', sa.Integer(), nullable=False, comment='累计故障维修数'
            ),
            sa.Column(
                'total_downtime_min',
                sa.Integer(),
                nullable=False,
                comment='累计维修用时（分钟）',
            ),
            sa.Column(
                'total_spare_cost',
                sa.Numeric(12, 2),
                nullable=False,
                comment='累计备件费用',
            ),
            sa.Column(
                'mtbf_days',
                sa.Numeric(10, 1),
                nullable=True,
                comment='平均故障间隔（天）',
            ),
            sa.Column(
                'last_3_faults',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment='最近 3 次故障摘要（工单号/日期/现象/原因）',
            ),
        ]),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('equipment_id', name='uq_repair_profiles_equipment'),
        schema='equipment',
    )

    op.create_table(
        'repair_knowledge_cases',
        *(_base_columns() + [
            sa.Column(
                'source_work_order_id',
                sa.Uuid(),
                sa.ForeignKey('equipment.work_orders.id'),
                nullable=True,
                comment='来源工单ID（人工补录可为空）',
            ),
            sa.Column(
                'equipment_id',
                sa.Uuid(),
                sa.ForeignKey('equipment.equipments.id'),
                nullable=True,
                comment='设备ID（检索本设备层）',
            ),
            sa.Column(
                'equipment_category_id',
                sa.Uuid(),
                sa.ForeignKey('equipment.equipment_categories.id'),
                nullable=True,
                comment='设备分类ID（检索同分类层）',
            ),
            sa.Column(
                'workshop_code',
                sa.String(20),
                nullable=True,
                comment='车间代码（展示用）',
            ),
            sa.Column(
                'symptom_code', sa.String(50), nullable=True, comment='故障现象代码'
            ),
            sa.Column(
                'symptom_name', sa.String(100), nullable=True, comment='故障现象名称'
            ),
            sa.Column(
                'cause_code', sa.String(50), nullable=True, comment='故障原因代码'
            ),
            sa.Column(
                'cause_name', sa.String(100), nullable=True, comment='故障原因名称'
            ),
            sa.Column(
                'action_code', sa.String(50), nullable=True, comment='维修措施代码'
            ),
            sa.Column(
                'action_name', sa.String(100), nullable=True, comment='维修措施名称'
            ),
            sa.Column(
                'fault_description', sa.Text(), nullable=True, comment='故障描述'
            ),
            sa.Column(
                'repair_summary', sa.Text(), nullable=True, comment='维修过程描述'
            ),
            sa.Column(
                'key_steps',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment='关键维修步骤（LLM 抽取建议，人工确认后入库）',
            ),
            sa.Column(
                'parts_used',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment='使用备件清单 [{spare_part_id,name,qty}]',
            ),
            sa.Column(
                'status',
                sa.String(20),
                nullable=False,
                comment='状态：draft草稿/verified已入库/dismissed已忽略',
            ),
            sa.Column(
                'verified_by',
                sa.Uuid(),
                sa.ForeignKey('identity.users.id'),
                nullable=True,
                comment='确认人ID',
            ),
            sa.Column(
                'verified_at',
                sa.DateTime(timezone=True),
                nullable=True,
                comment='确认时间',
            ),
            sa.Column(
                'use_count', sa.Integer(), nullable=False, comment='被推荐采纳次数'
            ),
            sa.Column(
                'equipment_name',
                sa.String(200),
                nullable=True,
                comment='设备名称快照（列表展示）',
            ),
            sa.Column(
                'equipment_no',
                sa.String(100),
                nullable=True,
                comment='设备编号快照',
            ),
        ]),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('draft', 'verified', 'dismissed')",
            name='ck_repair_knowledge_cases_status',
        ),
        schema='equipment',
    )
    op.create_index(
        'idx_repair_knowledge_cases_search',
        'repair_knowledge_cases',
        ['equipment_category_id', 'symptom_code'],
        schema='equipment',
        postgresql_where=sa.text('is_deleted = false AND status = \'verified\''),
    )

    op.create_table(
        'equipment_monthly_reports',
        *(_base_columns() + [
            sa.Column(
                'report_month',
                sa.String(7),
                nullable=False,
                comment='报告月份 YYYY-MM（全厂汇总一份）',
            ),
            sa.Column(
                'metrics',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment='SQL 聚合指标（LLM 不参与计算）',
            ),
            sa.Column(
                'content_md', sa.Text(), nullable=True, comment='报告正文（Markdown）'
            ),
            sa.Column(
                'generated_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
                comment='生成时间',
            ),
        ]),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'report_month',
            'is_deleted',
            name='uq_equipment_monthly_reports_month',
        ),
        sa.CheckConstraint(
            "report_month ~ '^[0-9]{4}-[0-9]{2}$'",
            name='ck_equipment_monthly_reports_month',
        ),
        schema='equipment',
    )


def downgrade() -> None:
    op.drop_table('equipment_monthly_reports', schema='equipment')
    op.drop_index(
        'idx_repair_knowledge_cases_search',
        table_name='repair_knowledge_cases',
        schema='equipment',
    )
    op.drop_table('repair_knowledge_cases', schema='equipment')
    op.drop_table('repair_profiles', schema='equipment')
    op.drop_index(
        'idx_equipment_health_snapshots_equipment',
        table_name='equipment_health_snapshots',
        schema='equipment',
    )
    op.drop_table('equipment_health_snapshots', schema='equipment')
