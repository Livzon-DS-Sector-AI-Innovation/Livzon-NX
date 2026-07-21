"""add automation run error code index

Revision ID: 417414f45ad9
Revises: 12491ff54d46
Create Date: 2026-07-10 12:32:55.554006
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "417414f45ad9"
down_revision: str | None = "12491ff54d46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_core_agent_automation_runs_error_code",
        "agent_automation_runs",
        ["error_code"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_agent_automation_runs_error_code",
        table_name="agent_automation_runs",
        schema="core",
    )
