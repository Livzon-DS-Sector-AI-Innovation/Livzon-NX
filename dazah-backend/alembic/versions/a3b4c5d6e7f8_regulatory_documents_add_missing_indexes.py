"""regulatory_documents add missing indexes

补齐模型声明但 e2f7a4c1b9d3 迁移遗漏的两个索引
（ix_regulatory_documents_source_site_code / ix_regulatory_documents_content_hash），
消除 alembic check 漂移。

Revision ID: a3b4c5d6e7f8
Revises: c8d9e0f1a2b3
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_regulatory_documents_source_site_code
            ON regulatory_tracker.regulatory_documents (source_site_code)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_regulatory_documents_content_hash
            ON regulatory_tracker.regulatory_documents (content_hash)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS regulatory_tracker.ix_regulatory_documents_content_hash"
    )
    op.execute(
        "DROP INDEX IF EXISTS "
        "regulatory_tracker.ix_regulatory_documents_source_site_code"
    )
