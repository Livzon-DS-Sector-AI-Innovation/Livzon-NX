"""add inspection routes tasks photos

Revision ID: cf818aa211ef
Revises: 4cc0d68d67fe
Create Date: 2026-06-06 12:21:38.154915
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf818aa211ef'
down_revision: Union[str, None] = '4cc0d68d67fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── inspection_routes ──
    op.create_table('inspection_routes',
        sa.Column('name', sa.String(length=200), nullable=False, comment='路线名称'),
        sa.Column('description', sa.Text(), nullable=True, comment='路线描述'),
        sa.Column('area', sa.String(length=100), nullable=True, comment='区域'),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False, comment='是否启用'),
        sa.Column('period_type', sa.String(length=20), nullable=False, comment='巡检周期类型'),
        sa.Column('period_value', sa.Integer(), nullable=True, comment='周期数值'),
        sa.Column('template_id', sa.Uuid(), nullable=True, comment='默认检查模板ID'),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.CheckConstraint(
            "period_type IN ('每日', '每周', '每月', '专项')",
            name='ck_inspection_routes_period_type',
        ),
        sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'],),
        sa.ForeignKeyConstraint(['template_id'], ['equipment.inspection_templates.id'],),
        sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'],),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'is_deleted', name='uq_inspection_routes_name'),
        schema='equipment',
    )

    # ── inspection_route_equipments ──
    op.create_table('inspection_route_equipments',
        sa.Column('route_id', sa.Uuid(), nullable=False, comment='路线ID'),
        sa.Column('equipment_id', sa.Uuid(), nullable=False, comment='设备ID'),
        sa.Column('sort_order', sa.Integer(), nullable=False, comment='巡检顺序'),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'],),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.equipments.id'],),
        sa.ForeignKeyConstraint(['route_id'], ['equipment.inspection_routes.id'],),
        sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'],),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'route_id', 'equipment_id', 'is_deleted',
            name='uq_route_equipments_route_equipment',
        ),
        schema='equipment',
    )

    # ── inspection_tasks ──
    op.create_table('inspection_tasks',
        sa.Column('task_no', sa.String(length=50), nullable=False, comment='任务编号 IT-yyyymmdd-xxxx'),
        sa.Column('route_id', sa.Uuid(), nullable=True, comment='关联路线ID（路线模式）'),
        sa.Column('equipment_id', sa.Uuid(), nullable=True, comment='单设备ID（单设备模式）'),
        sa.Column('template_id', sa.Uuid(), nullable=False, comment='检查模板ID'),
        sa.Column('plan_type', sa.String(length=20), nullable=False, comment='巡检类型'),
        sa.Column('assigned_to', sa.Uuid(), nullable=True, comment='巡检人员ID'),
        sa.Column('planned_date', sa.Date(), nullable=False, comment='计划日期'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='任务状态'),
        sa.Column('overall_result', sa.String(length=10), nullable=True, comment='总体结果'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True, comment='开始时间'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='完成时间'),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True, comment='关闭时间'),
        sa.Column('closure_remark', sa.Text(), nullable=True, comment='关闭备注'),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.CheckConstraint(
            "overall_result IS NULL OR overall_result IN ('正常', '异常')",
            name='ck_inspection_tasks_overall_result',
        ),
        sa.CheckConstraint(
            "plan_type IN ('日常巡检', '周巡检', '月巡检', '专项巡检')",
            name='ck_inspection_tasks_plan_type',
        ),
        sa.CheckConstraint(
            "status IN ('待执行', '执行中', '已完成', '已关闭')",
            name='ck_inspection_tasks_status',
        ),
        sa.ForeignKeyConstraint(['assigned_to'], ['identity.users.id'],),
        sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'],),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.equipments.id'],),
        sa.ForeignKeyConstraint(['route_id'], ['equipment.inspection_routes.id'],),
        sa.ForeignKeyConstraint(['template_id'], ['equipment.inspection_templates.id'],),
        sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'],),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_no', 'is_deleted', name='uq_inspection_tasks_task_no'),
        schema='equipment',
    )

    # ── inspection_photos ──
    op.create_table('inspection_photos',
        sa.Column('task_id', sa.Uuid(), nullable=False, comment='巡检任务ID'),
        sa.Column('equipment_id', sa.Uuid(), nullable=False, comment='设备ID'),
        sa.Column('file_name', sa.String(length=255), nullable=False, comment='原始文件名'),
        sa.Column('file_path', sa.String(length=500), nullable=False, comment='服务器文件路径'),
        sa.Column('file_size', sa.Integer(), nullable=True, comment='文件大小（字节）'),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='上传时间'),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'],),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.equipments.id'],),
        sa.ForeignKeyConstraint(['task_id'], ['equipment.inspection_tasks.id'],),
        sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'],),
        sa.PrimaryKeyConstraint('id'),
        schema='equipment',
    )

    # ── inspection_records 改造: work_order_id → task_id + equipment_id ──
    op.add_column('inspection_records',
        sa.Column('task_id', sa.Uuid(), nullable=True, comment='关联巡检任务ID'),
        schema='equipment',
    )
    op.add_column('inspection_records',
        sa.Column('equipment_id', sa.Uuid(), nullable=True, comment='关联设备ID'),
        schema='equipment',
    )
    op.drop_constraint(
        op.f('inspection_records_work_order_id_fkey'),
        'inspection_records', schema='equipment', type_='foreignkey',
    )
    op.create_foreign_key(
        None, 'inspection_records', 'equipments',
        ['equipment_id'], ['id'],
        source_schema='equipment', referent_schema='equipment',
    )
    op.create_foreign_key(
        None, 'inspection_records', 'inspection_tasks',
        ['task_id'], ['id'],
        source_schema='equipment', referent_schema='equipment',
    )
    op.drop_column('inspection_records', 'work_order_id', schema='equipment')


def downgrade() -> None:
    op.add_column('inspection_records',
        sa.Column('work_order_id', sa.UUID(), autoincrement=False, nullable=True, comment='关联巡检工单ID'),
        schema='equipment',
    )
    op.drop_constraint(None, 'inspection_records', schema='equipment', type_='foreignkey')
    op.drop_constraint(None, 'inspection_records', schema='equipment', type_='foreignkey')
    op.create_foreign_key(
        op.f('inspection_records_work_order_id_fkey'),
        'inspection_records', 'work_orders',
        ['work_order_id'], ['id'],
        source_schema='equipment', referent_schema='equipment',
    )
    op.drop_column('inspection_records', 'equipment_id', schema='equipment')
    op.drop_column('inspection_records', 'task_id', schema='equipment')
    op.drop_table('inspection_photos', schema='equipment')
    op.drop_table('inspection_tasks', schema='equipment')
    op.drop_table('inspection_route_equipments', schema='equipment')
    op.drop_table('inspection_routes', schema='equipment')
