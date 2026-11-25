"""检修汇总全厂默认设置

汇总页的排序、默认时间范围、默认车间筛选由管理员保存为全厂默认，
其他账号打开页面时按此初始化。单行表（scope 固定 global）。

Revision ID: d4c8e2f7a1b9
Revises: c7e3a1b9d5f2
Create Date: 2026-11-25 15:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4c8e2f7a1b9"
down_revision: str | None = "c7e3a1b9d5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    ]


def _base_constraints() -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    op.create_table(
        "repair_summary_settings",
        *_base_columns(),
        sa.Column(
            "scope", sa.String(length=20), nullable=False, server_default="global"
        ),
        sa.Column(
            "sort_field",
            sa.String(length=32),
            nullable=False,
            server_default="workshop",
        ),
        sa.Column(
            "sort_order",
            sa.String(length=12),
            nullable=False,
            server_default="ascend",
        ),
        sa.Column(
            "range_key", sa.String(length=20), nullable=False, server_default="30d"
        ),
        sa.Column(
            "workshops",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        *_base_constraints(),
        schema="equipment",
    )
    op.create_index(
        "uq_repair_summary_settings_scope",
        "repair_summary_settings",
        ["scope"],
        unique=True,
        schema="equipment",
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_repair_summary_settings_scope",
        table_name="repair_summary_settings",
        schema="equipment",
    )
    op.drop_table("repair_summary_settings", schema="equipment")
