"""add quality oos oot foundation

Revision ID: 7a69407edc70
Revises: 07d131578c71
Create Date: 2026-07-13 10:41:07.025423
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a69407edc70"
down_revision: str | None = "07d131578c71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    op.create_table(
        "oos_oot_records",
        sa.Column(
            "record_code", sa.String(length=50), nullable=False, comment="记录编号"
        ),
        sa.Column(
            "record_type", sa.String(length=10), nullable=False, comment="OOS 或 OOT"
        ),
        sa.Column("title", sa.String(length=200), nullable=False, comment="事件标题"),
        sa.Column(
            "department", sa.String(length=100), nullable=True, comment="责任部门"
        ),
        sa.Column(
            "product_name", sa.String(length=200), nullable=True, comment="产品名称"
        ),
        sa.Column("batch_no", sa.String(length=100), nullable=True, comment="批号"),
        sa.Column(
            "test_item", sa.String(length=500), nullable=True, comment="检验项目"
        ),
        sa.Column("specification", sa.Text(), nullable=True, comment="标准规定"),
        sa.Column("test_result", sa.Text(), nullable=True, comment="检验结果"),
        sa.Column("discovered_date", sa.Date(), nullable=True, comment="发现日期"),
        sa.Column("description", sa.Text(), nullable=True, comment="事件描述"),
        sa.Column("investigation_result", sa.Text(), nullable=True, comment="调查结论"),
        sa.Column(
            "corrective_actions", sa.Text(), nullable=True, comment="纠正预防措施"
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="open",
            nullable=False,
            comment="状态",
        ),
        sa.Column(
            "closed_at", sa.DateTime(timezone=True), nullable=True, comment="关闭时间"
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "record_code", name="uq_quality_oos_oot_records_record_code"
        ),
        schema="quality",
    )
    op.create_index(
        "ix_quality_oos_oot_records_active_type_status_date",
        "oos_oot_records",
        ["is_deleted", "record_type", "status", "discovered_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_oos_oot_records_product_batch",
        "oos_oot_records",
        ["product_name", "batch_no"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "oot_limit_products",
        sa.Column(
            "product_code", sa.String(length=100), nullable=False, comment="产品编码"
        ),
        sa.Column(
            "product_name", sa.String(length=200), nullable=False, comment="产品名称"
        ),
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
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="是否启用",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_code", name="uq_quality_oot_limit_products_product_code"
        ),
        schema="quality",
    )
    op.create_index(
        "ix_quality_oot_limit_products_active_code",
        "oot_limit_products",
        ["is_deleted", "product_code"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_oot_limit_products_active_name",
        "oot_limit_products",
        ["is_deleted", "product_name"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "oot_limit_items",
        sa.Column(
            "product_id",
            sa.Uuid(),
            nullable=False,
            comment="OOT限度产品ID（应用层关联）",
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="显示顺序",
        ),
        sa.Column(
            "item_group", sa.String(length=100), nullable=True, comment="项目分组"
        ),
        sa.Column(
            "item_name", sa.String(length=500), nullable=False, comment="项目名称"
        ),
        sa.Column("specification", sa.Text(), nullable=True, comment="标准规定"),
        sa.Column("oot_limit", sa.Text(), nullable=False, comment="OOT限度"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "display_order",
            name="uq_quality_oot_limit_items_product_order",
        ),
        schema="quality",
    )
    op.create_index(
        "ix_quality_oot_limit_items_active_product",
        "oot_limit_items",
        ["is_deleted", "product_id"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_oot_limit_items_name",
        "oot_limit_items",
        ["item_name"],
        unique=False,
        schema="quality",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quality_oot_limit_items_name",
        table_name="oot_limit_items",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_oot_limit_items_active_product",
        table_name="oot_limit_items",
        schema="quality",
    )
    op.drop_table("oot_limit_items", schema="quality")
    op.drop_index(
        "ix_quality_oot_limit_products_active_name",
        table_name="oot_limit_products",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_oot_limit_products_active_code",
        table_name="oot_limit_products",
        schema="quality",
    )
    op.drop_table("oot_limit_products", schema="quality")
    op.drop_index(
        "ix_quality_oos_oot_records_product_batch",
        table_name="oos_oot_records",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_oos_oot_records_active_type_status_date",
        table_name="oos_oot_records",
        schema="quality",
    )
    op.drop_table("oos_oot_records", schema="quality")
