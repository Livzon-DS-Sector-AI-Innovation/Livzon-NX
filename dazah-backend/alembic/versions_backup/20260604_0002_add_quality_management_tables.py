"""add quality management tables

Revision ID: 20260604_0002
Revises: 20260604_0001
Create Date: 2026-06-04
"""

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = '20260604_0002'
down_revision = '20260604_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create quality schema
    op.execute('CREATE SCHEMA IF NOT EXISTS quality')
    
    # Create deviations table
    op.create_table(
        'deviations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('deviation_code', sa.String(50), nullable=False, comment='偏差编号'),
        sa.Column('title', sa.String(255), nullable=False, comment='标题'),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft', 
                  comment='状态: draft/pending_ai_analysis/pending_investigation/pending_dept_head_review/pending_cross_dept_head_review/pending_qa_review/pending_qa_head_review/pending_quality_head_review/pending_final_code/returned/closed/cancelled'),
        sa.Column('level', sa.String(20), nullable=True, comment='级别: minor/moderate/major'),
        sa.Column('reporter_id', sa.UUID(), nullable=True, comment='报告人ID'),
        sa.Column('department', sa.String(100), nullable=True, comment='部门'),
        sa.Column('discovery_date', sa.DateTime(timezone=True), nullable=True, comment='发现日期'),
        sa.Column('ai_analysis', sa.JSON(), nullable=True, comment='AI分析结果'),
        sa.Column('investigation_records', sa.JSON(), nullable=True, comment='调查记录'),
        sa.Column('review_opinions', sa.JSON(), nullable=True, comment='审核意见'),
        sa.Column('attachments', postgresql.ARRAY(sa.String()), nullable=True, comment='附件URL列表'),
        sa.Column('final_code', sa.String(50), nullable=True, comment='最终编号'),
        sa.Column('root_cause_category', sa.String(50), nullable=True, 
                  comment='根本原因类别: 人员/设施/设备/产品/物料/文件/环境/其它'),
        sa.Column('description', sa.Text(), nullable=True, comment='偏差描述'),
        sa.Column('immediate_actions', sa.Text(), nullable=True, comment='即时措施'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['reporter_id'], ['identity.users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('deviation_code'),
        schema='quality'
    )
    op.create_index('ix_quality_deviations_deviation_code', 'deviations', ['deviation_code'], schema='quality')
    op.create_index('ix_quality_deviations_status', 'deviations', ['status'], schema='quality')
    op.create_index('ix_quality_deviations_final_code', 'deviations', ['final_code'], schema='quality')
    
    # Create capas table
    op.create_table(
        'capas',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('capa_code', sa.String(50), nullable=False, comment='CAPA编号'),
        sa.Column('title', sa.String(255), nullable=False, comment='标题'),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft',
                  comment='状态: draft/submitted/under_execution/evaluation/closed/returned/cancelled'),
        sa.Column('deviation_id', sa.UUID(), nullable=True, comment='关联偏差ID'),
        sa.Column('source', sa.String(50), nullable=True,
                  comment='来源: deviation/audit/customer_complaint/internal_inspection'),
        sa.Column('category', sa.String(50), nullable=True, comment='类别: A/B/C'),
        sa.Column('root_cause_category', sa.String(50), nullable=True,
                  comment='根本原因类别: 人员/设施/设备/产品/物料/文件/环境/其它'),
        sa.Column('non_conformity_description', sa.Text(), nullable=True, comment='不符合事项描述'),
        sa.Column('root_cause_analysis', sa.Text(), nullable=True, comment='根本原因分析'),
        sa.Column('capa_content', sa.Text(), nullable=True, comment='CAPA内容'),
        sa.Column('capa_items', sa.JSON(), nullable=True, comment='CAPA项目列表'),
        sa.Column('executors', postgresql.ARRAY(sa.String()), nullable=True, comment='执行人ID列表'),
        sa.Column('expected_completion_date', sa.DateTime(timezone=True), nullable=True, comment='预期完成日期'),
        sa.Column('qa_reviewer_id', sa.UUID(), nullable=True, comment='QA审核人ID'),
        sa.Column('qa_review_opinion', sa.Text(), nullable=True, comment='QA审核意见'),
        sa.Column('qa_review_time', sa.DateTime(timezone=True), nullable=True, comment='QA审核时间'),
        sa.Column('q_head_approver_id', sa.UUID(), nullable=True, comment='Q负责人审批人ID'),
        sa.Column('q_head_approval_opinion', sa.Text(), nullable=True, comment='Q负责人审批意见'),
        sa.Column('q_head_approval_time', sa.DateTime(timezone=True), nullable=True, comment='Q负责人审批时间'),
        sa.Column('execution_status', sa.String(100), nullable=True, comment='执行状态'),
        sa.Column('execution_tracks', sa.JSON(), nullable=True, comment='执行跟踪记录'),
        sa.Column('dept_head_confirmations', sa.JSON(), nullable=True, comment='部门负责人确认记录'),
        sa.Column('evaluation_result', sa.String(50), nullable=True, comment='有效性评估结果: effective/ineffective'),
        sa.Column('evaluation_target', sa.Text(), nullable=True, comment='评估目标'),
        sa.Column('evaluation_confirmer_id', sa.UUID(), nullable=True, comment='评估确认人ID'),
        sa.Column('evaluation_confirm_date', sa.DateTime(timezone=True), nullable=True, comment='评估确认日期'),
        sa.Column('closure_date', sa.DateTime(timezone=True), nullable=True, comment='关闭日期'),
        sa.Column('closure_remark', sa.Text(), nullable=True, comment='关闭备注'),
        sa.Column('final_code', sa.String(50), nullable=True, comment='最终编号'),
        sa.Column('report_content', sa.Text(), nullable=True, comment='报告内容'),
        sa.Column('report_versions', sa.JSON(), nullable=True, comment='报告版本历史'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['deviation_id'], ['quality.deviations.id']),
        sa.ForeignKeyConstraint(['qa_reviewer_id'], ['identity.users.id']),
        sa.ForeignKeyConstraint(['q_head_approver_id'], ['identity.users.id']),
        sa.ForeignKeyConstraint(['evaluation_confirmer_id'], ['identity.users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('capa_code'),
        schema='quality'
    )
    op.create_index('ix_quality_capas_capa_code', 'capas', ['capa_code'], schema='quality')
    op.create_index('ix_quality_capas_status', 'capas', ['status'], schema='quality')
    op.create_index('ix_quality_capas_final_code', 'capas', ['final_code'], schema='quality')
    
    # Create department_contacts table
    op.create_table(
        'department_contacts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('department', sa.String(100), nullable=False, comment='部门名称'),
        sa.Column('dept_head_id', sa.UUID(), nullable=True, comment='部门负责人ID'),
        sa.Column('qa_staff_ids', postgresql.ARRAY(sa.String()), nullable=True, comment='QA人员ID列表'),
        sa.Column('gmp_staff_ids', postgresql.ARRAY(sa.String()), nullable=True, comment='GMP人员ID列表'),
        sa.Column('production_head_id', sa.UUID(), nullable=True, comment='生产负责人ID'),
        sa.Column('quality_head_id', sa.UUID(), nullable=True, comment='质量负责人ID'),
        sa.Column('additional_contacts', postgresql.ARRAY(sa.String()), nullable=True, comment='其他联系人ID列表'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['dept_head_id'], ['identity.users.id']),
        sa.ForeignKeyConstraint(['production_head_id'], ['identity.users.id']),
        sa.ForeignKeyConstraint(['quality_head_id'], ['identity.users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('department'),
        schema='quality'
    )
    op.create_index('ix_quality_department_contacts_department', 'department_contacts', ['department'], schema='quality')
    
    # Create department_weekly_confirmations table
    op.create_table(
        'department_weekly_confirmations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('department', sa.String(100), nullable=False, comment='部门名称'),
        sa.Column('week_key', sa.String(20), nullable=False, comment='周标识(如2024-W01)'),
        sa.Column('production_status', sa.String(20), nullable=False, comment='生产状态: production/stopped'),
        sa.Column('deviation_status', sa.String(50), nullable=False, server_default='unsubmitted',
                  comment='偏差状态: submitted/unsubmitted'),
        sa.Column('confirmed_by_id', sa.UUID(), nullable=True, comment='确认人ID'),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True, comment='确认时间'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['confirmed_by_id'], ['identity.users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('department', 'week_key', name='uq_dept_weekly_confirmation'),
        schema='quality'
    )
    op.create_index('ix_quality_dept_weekly_confirmations_department', 'department_weekly_confirmations', ['department'], schema='quality')
    op.create_index('ix_quality_dept_weekly_confirmations_week_key', 'department_weekly_confirmations', ['week_key'], schema='quality')
    
    # Create attachment_reviews table
    op.create_table(
        'attachment_reviews',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('deviation_id', sa.UUID(), nullable=True, comment='偏差ID'),
        sa.Column('capa_id', sa.UUID(), nullable=True, comment='CAPA ID'),
        sa.Column('attachment_url', sa.String(500), nullable=False, comment='附件URL'),
        sa.Column('reviewer_id', sa.UUID(), nullable=False, comment='审核人ID'),
        sa.Column('review_time', sa.DateTime(timezone=True), nullable=True, comment='审核时间'),
        sa.Column('content', sa.Text(), nullable=False, comment='批注内容'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending',
                  comment='状态: pending/approved/rejected'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['deviation_id'], ['quality.deviations.id']),
        sa.ForeignKeyConstraint(['capa_id'], ['quality.capas.id']),
        sa.ForeignKeyConstraint(['reviewer_id'], ['identity.users.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='quality'
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('attachment_reviews', schema='quality')
    op.drop_table('department_weekly_confirmations', schema='quality')
    op.drop_table('department_contacts', schema='quality')
    op.drop_table('capas', schema='quality')
    op.drop_table('deviations', schema='quality')
    op.execute('DROP SCHEMA IF EXISTS quality CASCADE')
