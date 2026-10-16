"""create production.user_board_preferences for per-user board prefs"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c9d400000059"
down_revision: str | None = "c4e6f8a0b2d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 生产看板个人偏好：平均单产口径与标签后缀按登录账户持久化
    # （首次访问无行，接口返回默认值；user_id 跨模块不建外键）
    op.create_table(
        "user_board_preferences",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="用户 ID（identity.users 稳定标识，跨模块不建外键）",
        ),
        sa.Column(
            "avg_pilot_incl",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment=(
                "平均单产口径：true=含中试（总产量÷大罐批数）"
                "false=不含中试（大罐批均值）"
            ),
        ),
        sa.Column(
            "avg_note",
            sa.String(length=64),
            server_default="含中试",
            nullable=False,
            comment="含中试模式下的平均线标签后缀（默认「含中试」，可改可清空）",
        ),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "uq_user_board_preferences_user",
        "user_board_preferences",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_user_board_preferences_user",
        table_name="user_board_preferences",
        schema="production",
    )
    op.drop_table("user_board_preferences", schema="production")
