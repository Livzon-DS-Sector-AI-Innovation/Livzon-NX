"""add Agent governance identity and Feishu admission controls

Revision ID: 7a31c9e4d2b8
Revises: 4e7b9c1d2f30
Create Date: 2026-07-31 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7a31c9e4d2b8"
down_revision: str | None = "4e7b9c1d2f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "external_identity_bindings",
        sa.Column(
            "source",
            sa.String(length=32),
            server_default="admin",
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "external_identity_bindings",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        schema="identity",
    )
    op.execute(
        """
        UPDATE identity.external_identity_bindings
        SET source = COALESCE(binding_metadata->>'migration_source', 'admin'),
            verified_at = COALESCE(last_seen_at, created_at)
        """
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "allowed_group_chat_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "require_group_mention",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_column("feishu_configs", "require_group_mention", schema="identity")
    op.drop_column("feishu_configs", "allowed_group_chat_ids", schema="identity")
    op.drop_column(
        "external_identity_bindings", "verified_at", schema="identity"
    )
    op.drop_column("external_identity_bindings", "source", schema="identity")
