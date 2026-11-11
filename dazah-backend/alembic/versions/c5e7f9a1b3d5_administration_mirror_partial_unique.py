"""administration feishu mirror: partial unique indexes (烟酒礼品管理)

按后端规范把镜像五表里「唯一约束含 is_deleted」的写法改为
WHERE is_deleted = false 的部分唯一索引：

- feishu_read_source_roots / feishu_read_resources / feishu_read_fields /
  feishu_read_page_bindings：软删除表，唯一性只约束未删除行；
- feishu_read_records：记录按 mirror_version 版本化，保持同一约定。

Revision ID: c5e7f9a1b3d5
Revises: b9c8d7e6f5a4
Create Date: 2026-11-10 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5e7f9a1b3d5"
down_revision: str | None = "b9c8d7e6f5a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "administration"

# (约束名/索引名, 表名, 列)
UNIQUENESS: list[tuple[str, str, list[str]]] = [
    (
        "uq_administration_feishu_read_source_root",
        "feishu_read_source_roots",
        ["config_id", "source_type", "root_token"],
    ),
    (
        "uq_administration_feishu_read_resource",
        "feishu_read_resources",
        ["app_token", "table_id"],
    ),
    (
        "uq_administration_feishu_read_field",
        "feishu_read_fields",
        ["resource_id", "field_id"],
    ),
    (
        "uq_administration_feishu_read_record_version",
        "feishu_read_records",
        ["resource_id", "record_id", "mirror_version"],
    ),
    (
        "uq_administration_feishu_read_page_binding",
        "feishu_read_page_bindings",
        ["page_key", "resource_id"],
    ),
]


def upgrade() -> None:
    for name, table, columns in UNIQUENESS:
        op.drop_constraint(name, table, schema=SCHEMA, type_="unique")
        op.create_index(
            name,
            table,
            columns,
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
            schema=SCHEMA,
        )


def downgrade() -> None:
    for name, table, columns in UNIQUENESS:
        op.drop_index(name, table_name=table, schema=SCHEMA)
        op.create_unique_constraint(
            name, table, columns, schema=SCHEMA
        )
