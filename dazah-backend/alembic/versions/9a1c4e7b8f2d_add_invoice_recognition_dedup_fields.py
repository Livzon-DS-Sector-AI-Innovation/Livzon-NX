"""add_invoice_recognition_dedup_fields

Revision ID: 9a1c4e7b8f2d
Revises: 0f3a6d9c1b2e
Create Date: 2026-06-27 16:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a1c4e7b8f2d"
down_revision: str | None = "0f3a6d9c1b2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invoice_recognition_records",
        sa.Column(
            "duplicate_key",
            sa.String(length=128),
            nullable=True,
            comment="发票业务去重指纹",
        ),
        schema="procurement",
    )
    op.add_column(
        "invoice_recognition_records",
        sa.Column(
            "source_file_sha256",
            sa.String(length=64),
            nullable=True,
            comment="上传文件 SHA256",
        ),
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_invoice_recognition_duplicate_key",
        "invoice_recognition_records",
        ["duplicate_key"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_invoice_recognition_source_file_sha256",
        "invoice_recognition_records",
        ["source_file_sha256"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "uq_procurement_invoice_recognition_active_duplicate_key",
        "invoice_recognition_records",
        ["duplicate_key"],
        unique=True,
        schema="procurement",
        postgresql_where=sa.text("is_deleted = false AND duplicate_key IS NOT NULL"),
    )
    op.create_index(
        "uq_procurement_invoice_recognition_active_source_file_sha256",
        "invoice_recognition_records",
        ["source_file_sha256"],
        unique=True,
        schema="procurement",
        postgresql_where=sa.text(
            "is_deleted = false AND source_file_sha256 IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_procurement_invoice_recognition_active_source_file_sha256",
        table_name="invoice_recognition_records",
        schema="procurement",
    )
    op.drop_index(
        "uq_procurement_invoice_recognition_active_duplicate_key",
        table_name="invoice_recognition_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_invoice_recognition_source_file_sha256",
        table_name="invoice_recognition_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_invoice_recognition_duplicate_key",
        table_name="invoice_recognition_records",
        schema="procurement",
    )
    op.drop_column(
        "invoice_recognition_records",
        "source_file_sha256",
        schema="procurement",
    )
    op.drop_column(
        "invoice_recognition_records",
        "duplicate_key",
        schema="procurement",
    )
