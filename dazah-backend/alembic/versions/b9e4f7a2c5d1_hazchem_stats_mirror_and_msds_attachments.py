"""hazchem stats mirror columns + chemical_msds_attachments

危化品统计表镜像改造：
1. ``safety.page_feishu_configs`` 增加超储计算列配置（存量/上限/品名列字段名），
   由飞书设置页维护，不在代码里写死列名。
2. 新建 ``safety.chemical_msds_attachments`` 多附件表，并把
   ``hazardous_chemicals.msds_file_path/msds_file_name`` 旧单文件数据搬迁为
   附件记录；旧列保留不删，便于回滚（代码不再写入）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b9e4f7a2c5d1"
# 并行开发先后在 a7c3e5f1b8d2 之后新增迁移（b2e9d4f7a6c3 职业病检测报告），
# 本迁移接在其后恢复单链。
down_revision: str | None = "b2e9d4f7a6c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "over_limit_quantity_field",
            sa.String(length=120),
            nullable=True,
            comment="超储计算-存量列字段名（危化品统计表页专用，空=不启用超储计算）",
        ),
        schema="safety",
    )
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "over_limit_limit_field",
            sa.String(length=120),
            nullable=True,
            comment="超储计算-上限列字段名（与存量列一起配置才生效）",
        ),
        schema="safety",
    )
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "over_limit_name_field",
            sa.String(length=120),
            nullable=True,
            comment="超储计算-品名列字段名（空=取表格第一个文本列）",
        ),
        schema="safety",
    )

    op.create_table(
        "chemical_msds_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "chemical_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="危化品档案",
        ),
        sa.Column(
            "file_name",
            sa.String(length=255),
            nullable=False,
            comment="原始文件名",
        ),
        sa.Column(
            "storage_key",
            sa.String(length=500),
            nullable=False,
            comment="存储 key（MinIO 对象名或本地相对路径）",
        ),
        sa.Column(
            "content_type",
            sa.String(length=120),
            nullable=False,
            server_default="",
            comment="文件 MIME 类型",
        ),
        sa.Column(
            "size_bytes",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="文件大小（字节）",
        ),
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
        sa.ForeignKeyConstraint(
            ["chemical_id"], ["safety.hazardous_chemicals.id"]
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        schema="safety",
    )
    op.create_index(
        "ix_safety_chemical_msds_attachments_chemical",
        "chemical_msds_attachments",
        ["chemical_id", "is_deleted"],
        schema="safety",
    )

    # 旧单文件 MSDS 数据搬迁为附件记录（storage_key 存本地相对路径，读取端
    # 以“uploads/safety/hazchem/ 为根”兼容旧路径）
    op.execute(
        """
        INSERT INTO safety.chemical_msds_attachments (
            id, chemical_id, file_name, storage_key, content_type, size_bytes,
            created_at, updated_at, is_deleted
        )
        SELECT
            gen_random_uuid(),
            hc.id,
            CASE WHEN hc.msds_file_name = '' THEN 'msds' ELSE hc.msds_file_name END,
            hc.msds_file_path,
            '',
            0,
            hc.updated_at,
            hc.updated_at,
            false
        FROM safety.hazardous_chemicals hc
        WHERE hc.is_deleted = false AND hc.msds_file_path <> ''
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_safety_chemical_msds_attachments_chemical",
        table_name="chemical_msds_attachments",
        schema="safety",
    )
    op.drop_table("chemical_msds_attachments", schema="safety")
    op.drop_column(
        "page_feishu_configs", "over_limit_name_field", schema="safety"
    )
    op.drop_column(
        "page_feishu_configs", "over_limit_limit_field", schema="safety"
    )
    op.drop_column(
        "page_feishu_configs", "over_limit_quantity_field", schema="safety"
    )
