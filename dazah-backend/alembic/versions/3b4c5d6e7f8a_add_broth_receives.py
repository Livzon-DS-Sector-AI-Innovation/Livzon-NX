"""add_broth_receives_table

Revision ID: 3b4c5d6e7f8a
Revises: 2a3b4c5d6e7f
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = '3b4c5d6e7f8a'
down_revision = '2a3b4c5d6e7f'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('broth_receives',
    sa.Column('seq_no', sa.Integer(), nullable=True, comment='序号'),
    sa.Column('received_batch', sa.String(128), nullable=False, comment='接收批次'),
    sa.Column('fermenter_no', sa.String(64), nullable=True, comment='发酵罐号'),
    sa.Column('fermentation_batch', sa.String(128), nullable=True, comment='发酵批号'),
    sa.Column('received_volume', sa.String(64), nullable=True, comment='接收体积/重量'),
    sa.Column('broth_od', sa.Float(), nullable=True, comment='发酵液OD'),
    sa.Column('titer_u_ml', sa.Float(), nullable=True, comment='效价(u/mL)'),
    sa.Column('titer_mg_l', sa.Float(), nullable=True, comment='效价(mg/L)'),
    sa.Column('broth_ph', sa.Float(), nullable=True, comment='发酵液pH'),
    sa.Column('temperature', sa.Float(), nullable=True, comment='温度'),
    sa.Column('mycelium_concentration', sa.Float(), nullable=True, comment='菌丝浓度'),
    sa.Column('residual_sugar', sa.Float(), nullable=True, comment='残糖'),
    sa.Column('amino_nitrogen', sa.Float(), nullable=True, comment='氨基氮'),
    sa.Column('receive_time', sa.DateTime(timezone=True), nullable=True, comment='进厂/接收时间'),
    sa.Column('supplier_team', sa.String(128), nullable=True, comment='供方班组'),
    sa.Column('tank_bottom_residue', sa.Float(), nullable=True, comment='罐底渣量'),
    sa.Column('sample_no', sa.String(64), nullable=True, comment='取样编号'),
    sa.Column('sample_time', sa.DateTime(timezone=True), nullable=True, comment='取样时间'),
    sa.Column('inspection_result', sa.String(256), nullable=True, comment='检验结果'),
    sa.Column('qualified', sa.String(32), nullable=True, comment='合格判定'),
    sa.Column('receive_loss', sa.Float(), nullable=True, comment='接收损耗量'),
    sa.Column('pipeline_leak_record', sa.Text(), nullable=True, comment='输送管路跑冒滴漏记录'),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['identity.users.id']),
    sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id']),
    sa.PrimaryKeyConstraint('id'),
    schema='production')
    op.create_index('ix_broth_receive_batch', 'broth_receives', ['received_batch'], unique=False, schema='production')
    op.create_index('ix_broth_receive_fermenter', 'broth_receives', ['fermenter_no'], unique=False, schema='production')

def downgrade():
    op.drop_table('broth_receives', schema='production')
