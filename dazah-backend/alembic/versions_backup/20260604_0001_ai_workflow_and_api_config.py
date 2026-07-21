"""add AI workflow config and API call config tables

Revision ID: 20260604_0001
Revises: a9387cd590c5
Create Date: 2026-06-04 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20260604_0001b'
down_revision: Union[str, None] = 'a9387cd590c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AI 工作流配置表
    op.create_table(
        'ai_workflow_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('module_code', sa.String(64), nullable=False, comment='模块代码'),
        sa.Column('workflow_name', sa.String(128), nullable=False, comment='工作流名称'),
        sa.Column('workflow_description', sa.Text(), nullable=True, comment='工作流描述'),
        sa.Column('trigger_event', sa.String(64), nullable=True, comment='触发事件'),
        sa.Column('is_enabled', sa.Boolean(), server_default='true', nullable=False, comment='是否启用'),
        sa.Column('script_configs', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='脚本配置 JSON 数组'),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False, comment='排序顺序'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('module_code', name='uq_ai_workflow_config_module_code'),
        schema='safety',
    )

    # API 调用配置表
    op.create_table(
        'api_call_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('config_name', sa.String(128), nullable=False, comment='配置名称'),
        sa.Column('api_base_url', sa.String(500), nullable=False, comment='API 基础 URL'),
        sa.Column('api_key', sa.String(500), nullable=False, comment='API 密钥'),
        sa.Column('model_name', sa.String(128), nullable=False, comment='模型名称'),
        sa.Column('temperature', sa.Float(), server_default='0.1', nullable=False, comment='温度参数'),
        sa.Column('timeout_seconds', sa.Integer(), server_default='120', nullable=False, comment='超时秒数'),
        sa.Column('max_tokens', sa.Integer(), nullable=True, comment='最大 Token 数'),
        sa.Column('extra_config', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='额外配置 JSON'),
        sa.Column('is_active', sa.Boolean(), server_default='false', nullable=False, comment='是否激活'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='safety',
    )


def downgrade() -> None:
    op.drop_table('api_call_configs', schema='safety')
    op.drop_table('ai_workflow_configs', schema='safety')
