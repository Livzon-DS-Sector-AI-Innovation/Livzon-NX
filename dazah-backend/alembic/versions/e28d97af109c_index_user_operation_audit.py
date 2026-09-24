"""Index user operation audit by module and time.

Revision ID: e28d97af109c
Revises: bdcce6ff5b42
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e28d97af109c"
down_revision: str | None = "bdcce6ff5b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_audit_logs_operations_module_time",
        "logs",
        ["resource_type", "created_at"],
        schema="audit",
        postgresql_where=sa.text("action = 'platform_api_request'"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_audit_logs_operations_module_time", table_name="logs", schema="audit"
    )
