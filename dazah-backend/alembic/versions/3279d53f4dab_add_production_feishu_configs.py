"""add_production_feishu_configs

Revision ID: 3279d53f4dab
Revises: 2f0b698eb4d8
Create Date: 2026-07-01 15:22:15.676502
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3279d53f4dab'
down_revision: Union[str, None] = '2f0b698eb4d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('production_feishu_configs',
    sa.Column('name', sa.String(length=128), nullable=False, comment='配置名称'),
    sa.Column('product_name', sa.String(length=128), nullable=False, comment='关联产品（L-苯丙氨酸/洛伐他汀/美伐他汀）'),
    sa.Column('app_id', sa.String(length=128), nullable=False, comment='飞书应用 App ID'),
    sa.Column('encrypted_app_secret', sa.String(length=1024), nullable=False, comment='加密后的 App Secret'),
    sa.Column('bitable_app_token', sa.String(length=128), nullable=False, comment='多维表格 app_token'),
    sa.Column('table_id', sa.String(length=128), nullable=False, comment='发酵记录表 table_id'),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False, comment='是否启用'),
    sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='production'
    )


def downgrade() -> None:
    op.drop_table('production_feishu_configs', schema='production')
