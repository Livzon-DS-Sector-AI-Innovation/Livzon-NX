"""add local auth user fields

Revision ID: c2e7a4d9f8b6
Revises: d4a1c9b7e6f3
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2e7a4d9f8b6"
down_revision: str | None = "d4a1c9b7e6f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("username", sa.String(length=64), nullable=True),
        schema="identity",
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.Text(), nullable=True),
        schema="identity",
    )
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            server_default="user",
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_source",
            sa.String(length=20),
            server_default="feishu",
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_unique_constraint(
        "uq_identity_users_username", "users", ["username"], schema="identity"
    )


def downgrade() -> None:
    op.drop_constraint("uq_identity_users_username", "users", schema="identity")
    op.drop_column("users", "last_login_at", schema="identity")
    op.drop_column("users", "auth_source", schema="identity")
    op.drop_column("users", "status", schema="identity")
    op.drop_column("users", "role", schema="identity")
    op.drop_column("users", "password_hash", schema="identity")
    op.drop_column("users", "username", schema="identity")
