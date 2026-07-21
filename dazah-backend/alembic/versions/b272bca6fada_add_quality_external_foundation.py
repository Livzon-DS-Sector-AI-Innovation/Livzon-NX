"""add quality external foundation

Revision ID: b272bca6fada
Revises: 7a69407edc70
Create Date: 2026-07-13 11:18:51.278127
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b272bca6fada"
down_revision: str | None = "7a69407edc70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    op.create_table(
        "suppliers",
        sa.Column(
            "supplier_code", sa.String(length=50), nullable=False, comment="供应商编号"
        ),
        sa.Column("name", sa.String(length=200), nullable=False, comment="供应商名称"),
        sa.Column(
            "category", sa.String(length=50), nullable=True, comment="供应商类别"
        ),
        sa.Column(
            "contact_person", sa.String(length=100), nullable=True, comment="联系人"
        ),
        sa.Column(
            "contact_phone", sa.String(length=30), nullable=True, comment="联系电话"
        ),
        sa.Column("address", sa.String(length=300), nullable=True, comment="地址"),
        sa.Column(
            "qualification_status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
            comment="资质状态",
        ),
        sa.Column("audit_date", sa.Date(), nullable=True, comment="最近审计日期"),
        sa.Column("audit_result", sa.Text(), nullable=True, comment="审计结论"),
        sa.Column("next_audit_date", sa.Date(), nullable=True, comment="下次审计日期"),
        sa.Column("scope_of_supply", sa.Text(), nullable=True, comment="供应范围"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="active",
            nullable=False,
            comment="供应商状态",
        ),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_code", name="uq_quality_suppliers_supplier_code"),
        schema="quality",
    )
    op.create_index(
        "ix_quality_suppliers_active_status",
        "suppliers",
        ["is_deleted", "status"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_suppliers_active_category",
        "suppliers",
        ["is_deleted", "category"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_suppliers_name",
        "suppliers",
        ["name"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "supplier_qualifications",
        sa.Column(
            "supplier_id", sa.Uuid(), nullable=False, comment="供应商ID（应用层关联）"
        ),
        sa.Column(
            "qualification_code",
            sa.String(length=50),
            nullable=False,
            comment="资质编号",
        ),
        sa.Column(
            "qualification_name",
            sa.String(length=200),
            nullable=False,
            comment="资质名称",
        ),
        sa.Column(
            "document_no", sa.String(length=100), nullable=True, comment="文件编号"
        ),
        sa.Column("obtained_date", sa.Date(), nullable=True, comment="取得日期"),
        sa.Column("expiry_date", sa.Date(), nullable=True, comment="到期日期"),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
            comment="资质状态",
        ),
        sa.Column(
            "responsible_person", sa.String(length=100), nullable=True, comment="责任人"
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "qualification_code", name="uq_quality_supplier_qualifications_code"
        ),
        schema="quality",
    )
    op.create_index(
        "ix_quality_supplier_qualifications_active_supplier_expiry",
        "supplier_qualifications",
        ["is_deleted", "supplier_id", "expiry_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_supplier_qualifications_active_status",
        "supplier_qualifications",
        ["is_deleted", "status"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "complaint_records",
        sa.Column(
            "complaint_code", sa.String(length=50), nullable=False, comment="投诉编号"
        ),
        sa.Column("title", sa.String(length=200), nullable=False, comment="投诉标题"),
        sa.Column(
            "complaint_source", sa.String(length=100), nullable=True, comment="投诉来源"
        ),
        sa.Column(
            "customer_name", sa.String(length=200), nullable=True, comment="客户名称"
        ),
        sa.Column(
            "product_name", sa.String(length=200), nullable=True, comment="涉及产品"
        ),
        sa.Column("batch_number", sa.String(length=100), nullable=True, comment="批号"),
        sa.Column("complaint_date", sa.Date(), nullable=True, comment="投诉日期"),
        sa.Column(
            "complaint_category",
            sa.String(length=50),
            nullable=True,
            comment="投诉类别",
        ),
        sa.Column("description", sa.Text(), nullable=True, comment="投诉描述"),
        sa.Column("handler", sa.String(length=100), nullable=True, comment="处理人"),
        sa.Column("investigation_result", sa.Text(), nullable=True, comment="调查结论"),
        sa.Column("response_content", sa.Text(), nullable=True, comment="回复内容"),
        sa.Column("response_date", sa.Date(), nullable=True, comment="回复日期"),
        sa.Column(
            "capa_code", sa.String(length=50), nullable=True, comment="关联CAPA编号"
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
            comment="投诉状态",
        ),
        sa.Column(
            "closed_at", sa.DateTime(timezone=True), nullable=True, comment="关闭时间"
        ),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("complaint_code", name="uq_quality_complaint_records_code"),
        schema="quality",
    )
    op.create_index(
        "ix_quality_complaint_records_active_status_date",
        "complaint_records",
        ["is_deleted", "status", "complaint_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_complaint_records_product_batch",
        "complaint_records",
        ["product_name", "batch_number"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "return_recall_records",
        sa.Column(
            "record_code", sa.String(length=50), nullable=False, comment="记录编号"
        ),
        sa.Column(
            "record_type", sa.String(length=10), nullable=False, comment="退货或召回"
        ),
        sa.Column("title", sa.String(length=200), nullable=False, comment="标题"),
        sa.Column(
            "product_name", sa.String(length=200), nullable=True, comment="产品名称"
        ),
        sa.Column("batch_number", sa.String(length=100), nullable=True, comment="批号"),
        sa.Column(
            "quantity", sa.Numeric(precision=12, scale=4), nullable=True, comment="数量"
        ),
        sa.Column("unit", sa.String(length=20), nullable=True, comment="单位"),
        sa.Column(
            "customer_name",
            sa.String(length=200),
            nullable=True,
            comment="客户或退货方",
        ),
        sa.Column("reason", sa.Text(), nullable=True, comment="退货或召回原因"),
        sa.Column("occurrence_date", sa.Date(), nullable=True, comment="发生日期"),
        sa.Column("handler", sa.String(length=100), nullable=True, comment="处理人"),
        sa.Column("assessment_date", sa.Date(), nullable=True, comment="评估日期"),
        sa.Column(
            "disposition", sa.String(length=50), nullable=True, comment="处置方式"
        ),
        sa.Column("completion_date", sa.Date(), nullable=True, comment="完成日期"),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
            comment="处理状态",
        ),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "record_code", name="uq_quality_return_recall_records_code"
        ),
        schema="quality",
    )
    op.create_index(
        "ix_quality_return_recall_records_active_type_status",
        "return_recall_records",
        ["is_deleted", "record_type", "status"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_return_recall_records_product_batch",
        "return_recall_records",
        ["product_name", "batch_number"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "product_quality_records",
        sa.Column(
            "record_code", sa.String(length=50), nullable=False, comment="质量记录编号"
        ),
        sa.Column(
            "record_type",
            sa.String(length=30),
            nullable=False,
            comment="年度回顾或客户标准",
        ),
        sa.Column("title", sa.String(length=200), nullable=False, comment="标题"),
        sa.Column(
            "product_name", sa.String(length=200), nullable=False, comment="产品名称"
        ),
        sa.Column(
            "customer_name", sa.String(length=200), nullable=True, comment="客户名称"
        ),
        sa.Column("batch_number", sa.String(length=100), nullable=True, comment="批号"),
        sa.Column(
            "document_no", sa.String(length=100), nullable=True, comment="标准文件编号"
        ),
        sa.Column(
            "document_version",
            sa.String(length=50),
            nullable=True,
            comment="标准文件版本",
        ),
        sa.Column(
            "review_type", sa.String(length=50), nullable=True, comment="评审类型"
        ),
        sa.Column(
            "review_period_start", sa.Date(), nullable=True, comment="回顾周期开始"
        ),
        sa.Column(
            "review_period_end", sa.Date(), nullable=True, comment="回顾周期结束"
        ),
        sa.Column("batch_count", sa.Integer(), nullable=True, comment="批次数量"),
        sa.Column("qualified_count", sa.Integer(), nullable=True, comment="合格批次"),
        sa.Column(
            "unqualified_count", sa.Integer(), nullable=True, comment="不合格批次"
        ),
        sa.Column("oos_count", sa.Integer(), nullable=True, comment="OOS次数"),
        sa.Column("deviation_count", sa.Integer(), nullable=True, comment="偏差次数"),
        sa.Column("change_count", sa.Integer(), nullable=True, comment="变更次数"),
        sa.Column(
            "quality_trend", sa.String(length=30), nullable=True, comment="质量趋势"
        ),
        sa.Column("quality_standard", sa.Text(), nullable=True, comment="质量标准"),
        sa.Column("special_requirements", sa.Text(), nullable=True, comment="特殊要求"),
        sa.Column(
            "packaging_requirements", sa.Text(), nullable=True, comment="包装要求"
        ),
        sa.Column("label_requirements", sa.Text(), nullable=True, comment="标签要求"),
        sa.Column("pallet_requirements", sa.Text(), nullable=True, comment="打托要求"),
        sa.Column(
            "target_market", sa.String(length=100), nullable=True, comment="目标市场"
        ),
        sa.Column(
            "registration_status",
            sa.String(length=100),
            nullable=True,
            comment="注册情况",
        ),
        sa.Column("conclusion", sa.Text(), nullable=True, comment="评审结论"),
        sa.Column("suggestions", sa.Text(), nullable=True, comment="改进建议"),
        sa.Column("reviewer", sa.String(length=100), nullable=True, comment="评审人"),
        sa.Column("review_date", sa.Date(), nullable=True, comment="评审日期"),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="draft",
            nullable=False,
            comment="记录状态",
        ),
        sa.Column(
            "approved_at", sa.DateTime(timezone=True), nullable=True, comment="批准时间"
        ),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "record_code", name="uq_quality_product_quality_records_code"
        ),
        schema="quality",
    )
    op.create_index(
        "ix_quality_product_quality_records_active_type_status",
        "product_quality_records",
        ["is_deleted", "record_type", "status"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_product_quality_records_product",
        "product_quality_records",
        ["product_name"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "product_quality_standard_items",
        sa.Column(
            "product_quality_id",
            sa.Uuid(),
            nullable=False,
            comment="产品质量记录ID（应用层关联）",
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="显示顺序",
        ),
        sa.Column("category", sa.String(length=100), nullable=True, comment="要求分类"),
        sa.Column(
            "item_name", sa.String(length=500), nullable=False, comment="要求项目"
        ),
        sa.Column("requirement", sa.Text(), nullable=False, comment="要求内容"),
        sa.Column(
            "is_critical",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="是否关键要求",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_quality_id",
            "display_order",
            name="uq_quality_product_quality_standard_items_order",
        ),
        schema="quality",
    )
    op.create_index(
        "ix_quality_product_quality_standard_items_active_record",
        "product_quality_standard_items",
        ["is_deleted", "product_quality_id"],
        unique=False,
        schema="quality",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quality_product_quality_standard_items_active_record",
        table_name="product_quality_standard_items",
        schema="quality",
    )
    op.drop_table("product_quality_standard_items", schema="quality")
    op.drop_index(
        "ix_quality_product_quality_records_product",
        table_name="product_quality_records",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_product_quality_records_active_type_status",
        table_name="product_quality_records",
        schema="quality",
    )
    op.drop_table("product_quality_records", schema="quality")
    op.drop_index(
        "ix_quality_return_recall_records_product_batch",
        table_name="return_recall_records",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_return_recall_records_active_type_status",
        table_name="return_recall_records",
        schema="quality",
    )
    op.drop_table("return_recall_records", schema="quality")
    op.drop_index(
        "ix_quality_complaint_records_product_batch",
        table_name="complaint_records",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_complaint_records_active_status_date",
        table_name="complaint_records",
        schema="quality",
    )
    op.drop_table("complaint_records", schema="quality")
    op.drop_index(
        "ix_quality_supplier_qualifications_active_status",
        table_name="supplier_qualifications",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_supplier_qualifications_active_supplier_expiry",
        table_name="supplier_qualifications",
        schema="quality",
    )
    op.drop_table("supplier_qualifications", schema="quality")
    op.drop_index(
        "ix_quality_suppliers_name",
        table_name="suppliers",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_suppliers_active_category",
        table_name="suppliers",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_suppliers_active_status",
        table_name="suppliers",
        schema="quality",
    )
    op.drop_table("suppliers", schema="quality")


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
    ]
