"""drop quality.department_contacts

部门联系人功能下线：人员/部门数据统一改由人事管理-飞书联系人
（hr_feishu_members）提供，质量模块的本地镜像表不再需要。
原数据仍在飞书「部门联系人」多维表格中保留，需要时可从飞书侧恢复。

Revision ID: c9d400000026
Revises: c9d400000025
Create Date: 2026-09-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000026"
down_revision: str | None = "c9d400000025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "department_contacts"
SCHEMA_NAME = "quality"


def upgrade() -> None:
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)


def downgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=False),
        sa.Column("enterprise_email", sa.String(length=255), nullable=True),
        sa.Column("open_id", sa.String(length=255), nullable=True),
        sa.Column("department_head_name", sa.String(length=255), nullable=True),
        sa.Column(
            "department_head_enterprise_email", sa.String(length=255), nullable=True
        ),
        sa.Column("department_head_open_id", sa.String(length=255), nullable=True),
        sa.Column("feishu_record_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("open_id", name="department_contacts_open_id_key"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_department_contacts_department",
        TABLE_NAME,
        ["department"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_department_contacts_name", TABLE_NAME, ["name"], schema=SCHEMA_NAME
    )
    op.create_index(
        "ix_department_contacts_open_id", TABLE_NAME, ["open_id"], schema=SCHEMA_NAME
    )
    op.create_index(
        "ix_department_contacts_feishu_record_id",
        TABLE_NAME,
        ["feishu_record_id"],
        schema=SCHEMA_NAME,
    )
