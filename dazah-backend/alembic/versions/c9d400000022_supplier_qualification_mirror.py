"""add supplier qualification mirror table

供应商资质页从"每次实时直读飞书"改为读本地镜像表：
新增 quality.supplier_qualification_records，按飞书 record_id 镜像
供应商资质子表行，source_updated_at 作增量水位；业务唯一键使用
"仅未删除行唯一"的部分唯一索引（对齐 AGENTS 软删除唯一约束规范）。

Revision ID: c9d400000022
Revises: a7c100000022
Create Date: 2026-09-07 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000022"
down_revision: str | None = "a7c100000022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table(
        "supplier_qualification_records", schema="quality"
    ):
        op.create_table(
            "supplier_qualification_records",
            sa.Column("feishu_record_id", sa.String(length=64), nullable=False),
            sa.Column("supplier_name", sa.String(length=500), nullable=True),
            sa.Column("material_name", sa.String(length=500), nullable=True),
            sa.Column("material_type", sa.String(length=200), nullable=True),
            sa.Column("qualification_name", sa.String(length=500), nullable=True),
            sa.Column("qualification_file", sa.String(length=1000), nullable=True),
            sa.Column(
                "is_completed",
                sa.Boolean(),
                server_default="false",
                nullable=False,
            ),
            sa.Column("deadline", sa.String(length=64), nullable=True),
            sa.Column("responsible_person", sa.String(length=500), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("expiry_status", sa.String(length=100), nullable=True),
            sa.Column(
                "source_created_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "source_updated_at", sa.DateTime(timezone=True), nullable=True
            ),
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
                "is_deleted", sa.Boolean(), server_default="false", nullable=False
            ),
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )
        op.execute(
            """
            CREATE UNIQUE INDEX uq_quality_supplier_qualification_records_feishu_active
                ON quality.supplier_qualification_records (feishu_record_id)
                WHERE is_deleted = false
            """
        )
        op.execute(
            """
            CREATE INDEX ix_quality_supplier_qualification_records_deadline
                ON quality.supplier_qualification_records (is_deleted, deadline)
            """
        )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS "
        "quality.ix_quality_supplier_qualification_records_deadline"
    )
    op.execute(
        "DROP INDEX IF EXISTS "
        "quality.uq_quality_supplier_qualification_records_feishu_active"
    )
    op.drop_table("supplier_qualification_records", schema="quality")
