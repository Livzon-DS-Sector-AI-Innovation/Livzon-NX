"""Add purchase request import duplicate key.

Revision ID: a1b2c3d4e5f6
Revises: e6d5c4b3a291
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "e6d5c4b3a291"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_procurement_purchase_request_import_duplicate_key"


def upgrade() -> None:
    op.add_column(
        "purchase_requests",
        sa.Column(
            "import_duplicate_key",
            sa.String(64),
            nullable=True,
            comment="导入幂等键（文件内容哈希+工作表名），防止同一表格重复导入",
        ),
        schema="procurement",
    )
    op.create_index(
        INDEX_NAME,
        "purchase_requests",
        ["import_duplicate_key"],
        unique=False,
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="purchase_requests", schema="procurement")
    op.drop_column(
        "purchase_requests",
        "import_duplicate_key",
        schema="procurement",
    )
