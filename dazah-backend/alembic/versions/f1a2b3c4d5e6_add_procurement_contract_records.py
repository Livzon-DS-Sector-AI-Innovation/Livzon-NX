"""add procurement contract records

Revision ID: f1a2b3c4d5e6
Revises: e5b7a6c9d8f0
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e5b7a6c9d8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS procurement")
    op.create_table(
        "contract_records",
        sa.Column("title", sa.String(length=255), nullable=False, comment="合同标题"),
        sa.Column("category", sa.String(length=64), nullable=False, comment="合同分类"),
        sa.Column(
            "contract_number",
            sa.String(length=128),
            nullable=False,
            comment="合同编号",
        ),
        sa.Column("contract_date", sa.Date(), nullable=False, comment="签订日期"),
        sa.Column(
            "seller_name",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="卖方名称",
        ),
        sa.Column(
            "filename",
            sa.String(length=255),
            nullable=False,
            comment="合同文件名",
        ),
        sa.Column(
            "file_path",
            sa.String(length=500),
            nullable=False,
            comment="合同文件路径或对象存储 key",
        ),
        sa.Column(
            "content_type",
            sa.String(length=255),
            nullable=False,
            comment="文件 MIME 类型",
        ),
        sa.Column(
            "file_size", sa.Integer(), nullable=False, comment="文件大小（字节）"
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
            comment="合同生成请求快照",
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
        "ix_procurement_contract_record_title",
        "contract_records",
        ["title"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_contract_record_category",
        "contract_records",
        ["category"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_contract_record_contract_number",
        "contract_records",
        ["contract_number"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_contract_record_seller_name",
        "contract_records",
        ["seller_name"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_contract_record_created_at",
        "contract_records",
        ["created_at"],
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_procurement_contract_record_created_at",
        table_name="contract_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_contract_record_seller_name",
        table_name="contract_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_contract_record_contract_number",
        table_name="contract_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_contract_record_category",
        table_name="contract_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_contract_record_title",
        table_name="contract_records",
        schema="procurement",
    )
    op.drop_table("contract_records", schema="procurement")
