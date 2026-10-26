"""add equipment workshop registry

设备车间注册表：车间清单从写死常量迁移为数据库管理（车间管理页新增/
改名/停用），统一工作台车间块、各功能视图与飞书配置页清单由此派生。
建表后初始化现有 9 个车间，保持与原前端常量一致。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3d8c1f6e2b7"
down_revision: str | None = "b5e9f2a7c8d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "equipment"

# 与前端原写死常量 EQUIPMENT_WORKSHOPS 一致的初始 9 车间
_SEED_WORKSHOPS = [
    ("101-1", "101一车间"),
    ("101-2", "101二车间"),
    ("102-1", "102一车间"),
    ("102-2", "102二车间"),
    ("103", "103车间"),
    ("201-1", "201一车间"),
    ("201-2", "201二车间"),
    ("201-3", "201三车间"),
    ("203", "203车间"),
]


def upgrade() -> None:
    op.create_table(
        "workshops",
        sa.Column("code", sa.String(length=10), nullable=False,
                  comment="车间代码（如 101-1 / 201-1，全系统数据标识）"),
        sa.Column("name", sa.String(length=50), nullable=False,
                  comment="车间显示名（如 101一车间）"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("true"),
                  comment="启用；停用后各处隐藏，数据保留可再启用"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema=_SCHEMA,
    )
    op.create_index(
        "uq_equipment_workshops_code",
        "workshops",
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema=_SCHEMA,
    )
    # 表在本迁移中新建，直接初始化种子数据
    values = ", ".join(
        f"(gen_random_uuid(), '{code}', '{name}', now(), now(), true, false)"
        for code, name in _SEED_WORKSHOPS
    )
    op.execute(
        f"""
        INSERT INTO {_SCHEMA}.workshops
            (id, code, name, created_at, updated_at, is_enabled, is_deleted)
        VALUES {values}
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_equipment_workshops_code", table_name="workshops", schema=_SCHEMA
    )
    op.drop_table("workshops", schema=_SCHEMA)
