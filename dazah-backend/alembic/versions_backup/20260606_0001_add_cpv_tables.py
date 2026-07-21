"""add cpv tables

Revision ID: 20260606_0001
Revises: 3093dedbc980
Create Date: 2026-06-06 11:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260606_0001"
down_revision: Union[str, None] = "1e3a6f5002da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create cpv_products table
    op.create_table(
        "cpv_products",
        sa.Column("name", sa.String(length=200), nullable=False, comment="产品名称"),
        sa.Column("specification", sa.String(length=200), nullable=True, comment="规格"),
        sa.Column("process_version", sa.String(length=50), nullable=True, comment="工艺版本"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active", comment="状态: active/inactive"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注描述"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="quality",
    )

    # Create cpv_import_tasks table
    op.create_table(
        "cpv_import_tasks",
        sa.Column("file_name", sa.String(length=255), nullable=False, comment="文件名"),
        sa.Column("product_id", sa.Uuid(), nullable=False, comment="产品ID"),
        sa.Column("data_type", sa.String(length=10), nullable=False, comment="数据类型: CPP/CQA"),
        sa.Column("import_mode", sa.String(length=20), nullable=False, comment="导入模式: create/update/overwrite"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending", comment="状态: pending/processing/completed/failed"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0", comment="总行数"),
        sa.Column("success_rows", sa.Integer(), nullable=False, server_default="0", comment="成功行数"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0", comment="失败行数"),
        sa.Column("error_details", sa.JSON(), nullable=True, comment="错误详情"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["quality.cpv_products.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="quality",
    )

    # Create cpv_parameters table
    op.create_table(
        "cpv_parameters",
        sa.Column("product_id", sa.Uuid(), nullable=False, comment="产品ID"),
        sa.Column("parameter_type", sa.String(length=10), nullable=False, comment="参数类型: CPP/CQA"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="参数名称"),
        sa.Column("code", sa.String(length=100), nullable=True, comment="参数代码(Excel表头匹配键)"),
        sa.Column("unit", sa.String(length=50), nullable=True, comment="单位"),
        sa.Column("lower_limit", sa.Float(), nullable=True, comment="标准下限"),
        sa.Column("upper_limit", sa.Float(), nullable=True, comment="标准上限"),
        sa.Column("control_lower", sa.Float(), nullable=True, comment="控制下限(内控限)"),
        sa.Column("control_upper", sa.Float(), nullable=True, comment="控制上限(内控限)"),
        sa.Column("target_value", sa.Float(), nullable=True, comment="目标值"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true", comment="是否启用"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="排序"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["quality.cpv_products.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="quality",
    )

    # Create cpv_batches table
    op.create_table(
        "cpv_batches",
        sa.Column("product_id", sa.Uuid(), nullable=False, comment="产品ID"),
        sa.Column("batch_no", sa.String(length=100), nullable=False, comment="批号"),
        sa.Column("production_date", sa.Date(), nullable=False, comment="生产日期"),
        sa.Column("data_type", sa.String(length=10), nullable=False, comment="数据类型: CPP/CQA"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual", comment="数据来源: excel/feishu/manual"),
        sa.Column("import_task_id", sa.Uuid(), nullable=True, comment="导入任务ID"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["quality.cpv_products.id"]),
        sa.ForeignKeyConstraint(["import_task_id"], ["quality.cpv_import_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "batch_no", "data_type", name="uq_cpv_batches_product_batch_type"),
        schema="quality",
    )

    # Create cpv_values table
    op.create_table(
        "cpv_values",
        sa.Column("batch_id", sa.Uuid(), nullable=False, comment="批次ID"),
        sa.Column("parameter_id", sa.Uuid(), nullable=False, comment="参数ID"),
        sa.Column("actual_value", sa.String(length=100), nullable=True, comment="实测值"),
        sa.Column("is_abnormal", sa.Boolean(), nullable=False, server_default="false", comment="是否异常"),
        sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["quality.cpv_batches.id"]),
        sa.ForeignKeyConstraint(["parameter_id"], ["quality.cpv_parameters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "parameter_id", name="uq_cpv_values_batch_parameter"),
        schema="quality",
    )


def downgrade() -> None:
    op.drop_table("cpv_values", schema="quality")
    op.drop_table("cpv_batches", schema="quality")
    op.drop_table("cpv_parameters", schema="quality")
    op.drop_table("cpv_import_tasks", schema="quality")
    op.drop_table("cpv_products", schema="quality")
