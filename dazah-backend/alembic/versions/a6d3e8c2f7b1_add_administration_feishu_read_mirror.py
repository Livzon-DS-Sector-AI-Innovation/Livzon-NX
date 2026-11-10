"""add administration feishu read mirror (烟酒礼品管理)

创建 administration schema 与烟酒礼品管理所需的飞书只读镜像表：

- ``administration.feishu_configs``：行政模块飞书应用凭证（secret 加密存储）。
- ``administration.feishu_read_source_roots``：飞书数据入口（Wiki/Base）。
- ``administration.feishu_read_resources``：已发现的数据表。
- ``administration.feishu_read_fields``：字段结构快照。
- ``administration.feishu_read_records``：记录镜像（按 mirror_version 版本化）。
- ``administration.feishu_read_page_bindings``：页面 ↔ 数据表绑定。
- ``administration.feishu_read_sync_runs``：同步运行记录。

Revision ID: a6d3e8c2f7b1
Revises: e4c7a1b9d5f3
Create Date: 2026-11-09 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6d3e8c2f7b1"
down_revision: str | None = "e4c7a1b9d5f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "administration"


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS administration")

    op.create_table(
        "feishu_configs",
        sa.Column(
            "config_name",
            sa.String(length=255),
            nullable=False,
            server_default="行政管理飞书配置",
            comment="配置名称",
        ),
        sa.Column(
            "app_id",
            sa.String(length=100),
            nullable=False,
            server_default="",
            comment="飞书应用 App ID",
        ),
        sa.Column(
            "encrypted_app_secret",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="加密后的飞书应用 App Secret",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="是否启用",
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="Asia/Shanghai",
            comment="时区",
        ),
        sa.Column(
            "daily_sync_time",
            sa.String(length=16),
            nullable=False,
            server_default="02:00",
            comment="每日同步时间",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_administration_feishu_configs_is_active",
        "feishu_configs",
        ["is_active"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "feishu_read_source_roots",
        sa.Column(
            "config_id", sa.Uuid(), nullable=False, comment="所属配置 id"
        ),
        sa.Column("name", sa.String(length=255), nullable=False, comment="入口名称"),
        sa.Column(
            "source_type",
            sa.String(length=16),
            nullable=False,
            comment="入口类型：wiki 或 base",
        ),
        sa.Column("source_url", sa.Text(), nullable=False, comment="入口链接"),
        sa.Column("root_token", sa.String(length=256), nullable=False, comment="入口 token"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="是否启用",
        ),
        sa.Column(
            "discovery_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
            comment="发现状态：pending/running/success/failed",
        ),
        sa.Column(
            "last_discovered_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("discovery_error", sa.Text(), nullable=True),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "config_id",
            "source_type",
            "root_token",
            "is_deleted",
            name="uq_administration_feishu_read_source_root",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_administration_feishu_read_roots_config",
        "feishu_read_source_roots",
        ["config_id", "is_active"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "feishu_read_resources",
        sa.Column(
            "source_root_id", sa.Uuid(), nullable=False, comment="所属入口 id"
        ),
        sa.Column(
            "app_token", sa.String(length=256), nullable=False, comment="多维表格 app_token"
        ),
        sa.Column(
            "table_id", sa.String(length=256), nullable=False, comment="数据表 table_id"
        ),
        sa.Column("title", sa.String(length=255), nullable=False, comment="数据表名称"),
        sa.Column(
            "source_path",
            JSONB(),
            nullable=False,
            comment="来源路径（Wiki 节点链）",
        ),
        sa.Column("schema_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "active_mirror_version", sa.Uuid(), nullable=True
        ),
        sa.Column(
            "last_complete_sync_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "sync_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
            comment="同步状态：pending/running/success/failed",
        ),
        sa.Column("sync_error", sa.Text(), nullable=True),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "app_token",
            "table_id",
            "is_deleted",
            name="uq_administration_feishu_read_resource",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_administration_feishu_read_resources_root",
        "feishu_read_resources",
        ["source_root_id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "feishu_read_fields",
        sa.Column(
            "resource_id", sa.Uuid(), nullable=False, comment="所属数据表 id"
        ),
        sa.Column("field_id", sa.String(length=256), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("field_type", sa.String(length=64), nullable=False),
        sa.Column("property", JSONB(), nullable=False, comment="字段属性"),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="字段顺序",
        ),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_id",
            "field_id",
            "is_deleted",
            name="uq_administration_feishu_read_field",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_administration_feishu_read_fields_resource",
        "feishu_read_fields",
        ["resource_id", "sort_order"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "feishu_read_records",
        sa.Column(
            "resource_id", sa.Uuid(), nullable=False, comment="所属数据表 id"
        ),
        sa.Column("record_id", sa.String(length=256), nullable=False),
        sa.Column(
            "mirror_version", sa.Uuid(), nullable=False, comment="镜像版本"
        ),
        sa.Column(
            "raw_fields", JSONB(), nullable=False, comment="飞书原始字段值"
        ),
        sa.Column(
            "normalized_fields", JSONB(), nullable=False, comment="归一化字段值"
        ),
        sa.Column(
            "search_text",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="关键字检索拼接文本",
        ),
        sa.Column(
            "source_created_time", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "source_modified_time", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_id",
            "record_id",
            "mirror_version",
            name="uq_administration_feishu_read_record_version",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_administration_feishu_read_records_page",
        "feishu_read_records",
        ["resource_id", "mirror_version", "record_id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "feishu_read_page_bindings",
        sa.Column(
            "page_key", sa.String(length=255), nullable=False, comment="页面 key"
        ),
        sa.Column(
            "resource_id", sa.Uuid(), nullable=False, comment="数据表 id"
        ),
        sa.Column("tab_name", sa.String(length=255), nullable=False),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="页签顺序",
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "visible_field_ids",
            JSONB(),
            nullable=False,
            comment="可见字段 id 列表（空=全部）",
        ),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "page_key",
            "resource_id",
            "is_deleted",
            name="uq_administration_feishu_read_page_binding",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_administration_feishu_read_bindings_page",
        "feishu_read_page_bindings",
        ["page_key", "sort_order"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "feishu_read_sync_runs",
        sa.Column(
            "resource_id", sa.Uuid(), nullable=False, comment="数据表 id"
        ),
        sa.Column(
            "mirror_version", sa.Uuid(), nullable=False, comment="镜像版本"
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="running",
            comment="运行状态：running/success/failed",
        ),
        sa.Column(
            "expected_count",
            sa.Integer(),
            nullable=True,
            comment="飞书侧期望记录数",
        ),
        sa.Column(
            "actual_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="实际同步记录数",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_administration_feishu_read_runs_resource",
        "feishu_read_sync_runs",
        ["resource_id", "started_at"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_administration_feishu_read_runs_resource",
        table_name="feishu_read_sync_runs",
        schema=SCHEMA,
    )
    op.drop_table("feishu_read_sync_runs", schema=SCHEMA)
    op.drop_index(
        "ix_administration_feishu_read_bindings_page",
        table_name="feishu_read_page_bindings",
        schema=SCHEMA,
    )
    op.drop_table("feishu_read_page_bindings", schema=SCHEMA)
    op.drop_index(
        "ix_administration_feishu_read_records_page",
        table_name="feishu_read_records",
        schema=SCHEMA,
    )
    op.drop_table("feishu_read_records", schema=SCHEMA)
    op.drop_index(
        "ix_administration_feishu_read_fields_resource",
        table_name="feishu_read_fields",
        schema=SCHEMA,
    )
    op.drop_table("feishu_read_fields", schema=SCHEMA)
    op.drop_index(
        "ix_administration_feishu_read_resources_root",
        table_name="feishu_read_resources",
        schema=SCHEMA,
    )
    op.drop_table("feishu_read_resources", schema=SCHEMA)
    op.drop_index(
        "ix_administration_feishu_read_roots_config",
        table_name="feishu_read_source_roots",
        schema=SCHEMA,
    )
    op.drop_table("feishu_read_source_roots", schema=SCHEMA)
    op.drop_index(
        "ix_administration_feishu_configs_is_active",
        table_name="feishu_configs",
        schema=SCHEMA,
    )
    op.drop_table("feishu_configs", schema=SCHEMA)
