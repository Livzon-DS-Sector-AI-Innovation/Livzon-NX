"""add_procurement_invoice_recognition_records

Revision ID: 0f3a6d9c1b2e
Revises: 7ef205f0db8c
Create Date: 2026-06-27 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0f3a6d9c1b2e"
down_revision: str | None = "7ef205f0db8c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS procurement")
    op.create_table(
        "invoice_recognition_records",
        sa.Column(
            "file_name",
            sa.String(length=255),
            nullable=False,
            comment="上传文件名",
        ),
        sa.Column(
            "include_details",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="是否开启明细识别",
        ),
        sa.Column(
            "invoice_number",
            sa.String(length=64),
            nullable=True,
            comment="发票号码",
        ),
        sa.Column(
            "invoice_date",
            sa.String(length=32),
            nullable=True,
            comment="开票日期",
        ),
        sa.Column(
            "seller_name",
            sa.String(length=255),
            nullable=True,
            comment="销售方名称",
        ),
        sa.Column(
            "total_tax_amount",
            sa.Numeric(precision=18, scale=2),
            nullable=True,
            comment="税额合计",
        ),
        sa.Column(
            "total_amount_with_tax_small",
            sa.Numeric(precision=18, scale=2),
            nullable=True,
            comment="价税合计（小写）",
        ),
        sa.Column(
            "line_items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="识别到的发票明细",
        ),
        sa.Column(
            "raw_text",
            sa.Text(),
            server_default="",
            nullable=False,
            comment="PDF 文本层原文",
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
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_invoice_recognition_created_at",
        "invoice_recognition_records",
        ["created_at"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_invoice_recognition_invoice_number",
        "invoice_recognition_records",
        ["invoice_number"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_invoice_recognition_seller_name",
        "invoice_recognition_records",
        ["seller_name"],
        unique=False,
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_procurement_invoice_recognition_seller_name",
        table_name="invoice_recognition_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_invoice_recognition_invoice_number",
        table_name="invoice_recognition_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_invoice_recognition_created_at",
        table_name="invoice_recognition_records",
        schema="procurement",
    )
    op.drop_table("invoice_recognition_records", schema="procurement")
