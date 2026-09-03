"""Retire the EDBO menu without deleting experimental records.

Revision ID: e4a9c2d7b601
Revises: d1e2f3a4b5c6
"""

import sqlalchemy as sa

from alembic import op

revision: str = "e4a9c2d7b601"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    menus = sa.Table(
        "menus",
        sa.MetaData(),
        sa.Column("key", sa.String),
        sa.Column("route_path", sa.String),
        sa.Column("status", sa.String),
        sa.Column("is_deleted", sa.Boolean),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="identity",
    )
    op.execute(
        menus.update()
        .where(
            menus.c.key == "rd:bayesian",
            menus.c.route_path == "/rd/bayesian",
            menus.c.status == "active",
            menus.c.is_deleted.is_(False),
        )
        .values(status="disabled", updated_at=sa.func.now())
    )


def downgrade() -> None:
    # Keep the menu disabled: a downgrade cannot distinguish retirement from
    # an administrator's prior decision to disable it. Records are untouched;
    # an administrator can explicitly re-enable it after restoring the feature.
    pass
