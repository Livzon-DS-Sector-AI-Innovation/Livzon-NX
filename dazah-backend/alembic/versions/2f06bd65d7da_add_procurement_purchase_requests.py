"""add procurement purchase requests

Revision ID: 2f06bd65d7da
Revises: ccd803220bd9
Create Date: 2026-06-28 13:02:22.229198
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f06bd65d7da"
down_revision: str | None = "ccd803220bd9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS procurement")
    op.create_table(
        "purchase_requests",
        sa.Column(
            "category",
            sa.String(length=64),
            nullable=False,
            comment="采购分类",
        ),
        sa.Column(
            "request_department",
            sa.String(length=200),
            nullable=False,
            comment="申购部门",
        ),
        sa.Column("request_date", sa.Date(), nullable=False, comment="申请日期"),
        sa.Column(
            "status",
            sa.String(length=64),
            server_default="draft",
            nullable=False,
            comment="流程状态",
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=18, scale=2),
            server_default="0",
            nullable=False,
            comment="申请总额",
        ),
        sa.Column(
            "rejected_step",
            sa.String(length=64),
            nullable=True,
            comment="驳回步骤",
        ),
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="状态更新时间",
        ),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="procurement",
    )
    op.create_table(
        "purchase_request_items",
        sa.Column(
            "purchase_request_id",
            sa.String(length=36),
            nullable=False,
            comment="采购申请 ID",
        ),
        sa.Column("sequence", sa.Integer(), nullable=False, comment="序号"),
        sa.Column(
            "product_name",
            sa.String(length=255),
            nullable=False,
            comment="商品名称",
        ),
        sa.Column(
            "specification",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="规格",
        ),
        sa.Column(
            "purpose",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="用途",
        ),
        sa.Column(
            "material",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="材质",
        ),
        sa.Column(
            "brand",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="品牌",
        ),
        sa.Column(
            "quantity",
            sa.Numeric(precision=18, scale=4),
            nullable=False,
            comment="数量",
        ),
        sa.Column(
            "unit",
            sa.String(length=64),
            server_default="",
            nullable=False,
            comment="单位",
        ),
        sa.Column(
            "unit_price",
            sa.Numeric(precision=18, scale=4),
            nullable=False,
            comment="单价",
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
            comment="总额",
        ),
        sa.Column(
            "remarks",
            sa.Text(),
            server_default="",
            nullable=False,
            comment="备注",
        ),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="procurement",
    )
    op.create_table(
        "purchase_request_approvals",
        sa.Column(
            "purchase_request_id",
            sa.String(length=36),
            nullable=False,
            comment="采购申请 ID",
        ),
        sa.Column(
            "approval_role",
            sa.String(length=64),
            nullable=False,
            comment="审批角色",
        ),
        sa.Column("result", sa.String(length=32), nullable=False, comment="审批结果"),
        sa.Column(
            "opinion",
            sa.Text(),
            server_default="",
            nullable=False,
            comment="审批意见",
        ),
        sa.Column(
            "approver_name",
            sa.String(length=100),
            server_default="",
            nullable=False,
            comment="审批人姓名",
        ),
        sa.Column(
            "approval_time",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="审批时间",
        ),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_category",
        "purchase_requests",
        ["category"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_status",
        "purchase_requests",
        ["status"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_request_date",
        "purchase_requests",
        ["request_date"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_department",
        "purchase_requests",
        ["request_department"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_created_at",
        "purchase_requests",
        ["created_at"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_item_request_id",
        "purchase_request_items",
        ["purchase_request_id"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_approval_request_id",
        "purchase_request_approvals",
        ["purchase_request_id"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_approval_role",
        "purchase_request_approvals",
        ["approval_role"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_purchase_request_approval_time",
        "purchase_request_approvals",
        ["approval_time"],
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_procurement_purchase_request_approval_time",
        table_name="purchase_request_approvals",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_purchase_request_approval_role",
        table_name="purchase_request_approvals",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_purchase_request_approval_request_id",
        table_name="purchase_request_approvals",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_purchase_request_item_request_id",
        table_name="purchase_request_items",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_purchase_request_created_at",
        table_name="purchase_requests",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_purchase_request_department",
        table_name="purchase_requests",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_purchase_request_request_date",
        table_name="purchase_requests",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_purchase_request_status",
        table_name="purchase_requests",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_purchase_request_category",
        table_name="purchase_requests",
        schema="procurement",
    )
    op.drop_table("purchase_request_approvals", schema="procurement")
    op.drop_table("purchase_request_items", schema="procurement")
    op.drop_table("purchase_requests", schema="procurement")
