"""extract equipment feishu apps into standalone table

设备模块飞书自建应用独立化：应用凭据从 ``inspection_feishu_config`` 行内
字段抽出为 ``equipment.feishu_apps``（登记一次、多车间复用），配置行改为
``feishu_app_id`` 引用：
- 建应用表并将存量行内凭据按 App ID 去重回填（取各 App ID 最近更新的
  Secret）；
- 配置行加外键并按 App ID 回填关联后，删除行内 ``app_id`` / ``app_secret``
  列（downgrade 逆向恢复行内值）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b5e9f2a7c8d1"
down_revision: str | None = "c8e4a2f6d9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONFIG_TABLE = "inspection_feishu_config"
_APP_TABLE = "feishu_apps"
_SCHEMA = "equipment"


def upgrade() -> None:
    op.create_table(
        _APP_TABLE,
        sa.Column("name", sa.String(length=100), nullable=False,
                  comment="应用备注名（下拉展示用）"),
        sa.Column("app_id", sa.String(length=100), nullable=False,
                  comment="飞书应用 App ID"),
        sa.Column("app_secret", sa.Text(), nullable=False,
                  server_default="", comment="飞书应用 App Secret（加密存储）"),
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
        "uq_feishu_apps_app_id",
        _APP_TABLE,
        ["app_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema=_SCHEMA,
    )

    # 存量行内凭据按 App ID 去重回填；同一 App ID 多行时取最近更新的 Secret
    op.execute(
        f"""
        INSERT INTO {_SCHEMA}.{_APP_TABLE}
            (id, name, app_id, app_secret, created_at, updated_at, is_deleted)
        SELECT gen_random_uuid(), src.app_id, src.app_id, src.app_secret,
               now(), now(), false
        FROM (
            SELECT DISTINCT ON (app_id) app_id, app_secret
            FROM {_SCHEMA}.{_CONFIG_TABLE}
            WHERE is_deleted = false AND app_id <> '' AND app_secret <> ''
            ORDER BY app_id, updated_at DESC
        ) AS src
        """
    )

    op.add_column(
        _CONFIG_TABLE,
        sa.Column(
            "feishu_app_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="关联的飞书自建应用（凭据存于 feishu_apps）",
        ),
        schema=_SCHEMA,
    )
    op.execute(
        f"""
        UPDATE {_SCHEMA}.{_CONFIG_TABLE} AS cfg
        SET feishu_app_id = app.id
        FROM {_SCHEMA}.{_APP_TABLE} AS app
        WHERE cfg.app_id <> '' AND cfg.app_id = app.app_id
        """
    )
    op.create_foreign_key(
        "fk_inspection_feishu_config_feishu_app",
        source_table=_CONFIG_TABLE,
        referent_table=_APP_TABLE,
        local_cols=["feishu_app_id"],
        remote_cols=["id"],
        source_schema=_SCHEMA,
        referent_schema=_SCHEMA,
    )
    op.drop_column(_CONFIG_TABLE, "app_secret", schema=_SCHEMA)
    op.drop_column(_CONFIG_TABLE, "app_id", schema=_SCHEMA)


def downgrade() -> None:
    op.add_column(
        _CONFIG_TABLE,
        sa.Column("app_id", sa.String(length=100), nullable=False,
                  server_default="", comment="飞书应用 App ID"),
        schema=_SCHEMA,
    )
    op.add_column(
        _CONFIG_TABLE,
        sa.Column("app_secret", sa.Text(), nullable=False, server_default="",
                  comment="飞书应用 App Secret（加密存储）"),
        schema=_SCHEMA,
    )
    op.execute(
        f"""
        UPDATE {_SCHEMA}.{_CONFIG_TABLE} AS cfg
        SET app_id = app.app_id, app_secret = app.app_secret
        FROM {_SCHEMA}.{_APP_TABLE} AS app
        WHERE cfg.feishu_app_id = app.id
        """
    )
    op.drop_constraint(
        "fk_inspection_feishu_config_feishu_app",
        _CONFIG_TABLE,
        schema=_SCHEMA,
        type_="foreignkey",
    )
    op.drop_column(_CONFIG_TABLE, "feishu_app_id", schema=_SCHEMA)
    op.drop_index("uq_feishu_apps_app_id", table_name=_APP_TABLE, schema=_SCHEMA)
    op.drop_table(_APP_TABLE, schema=_SCHEMA)
