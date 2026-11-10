"""8大作业票聊天签名与默认值记忆

- ``safety.work_permit_signatures``：作业票手写签名存档（发起行 + 审批/确认/
  验票/验收节点），(permit_id, round, sign_key) 唯一——重签覆盖。
- ``safety.work_permit_form_defaults``：按 用户+票种 记忆上次填写内容，
  下次发起预填。

Revision ID: d7b2f9a4c1e6
Revises: c3a8e5f2b7d4
Create Date: 2026-11-09 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7b2f9a4c1e6"
down_revision: str | None = "c3a8e5f2b7d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

jsonb = postgresql.JSONB(astext_type=sa.Text())


def _base_columns() -> list[sa.Column]:
    """每张表独立生成基础列（Column 对象不可跨表复用）。"""
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
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default="false"
        ),
    ]


def _base_constraints() -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    op.create_table(
        "work_permit_signatures",
        *_base_columns(),
        sa.Column(
            "permit_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="所属作业票",
        ),
        sa.Column(
            "node_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="节点（发起行 为空）",
        ),
        sa.Column(
            "round",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="审批轮次（发起行 为 1）",
        ),
        sa.Column(
            "sign_key",
            sa.String(64),
            nullable=False,
            comment="签字行标识（节点 key 或 initiator/briefer/briefer_receiver）",
        ),
        sa.Column("signer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "signer_name",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="签字行显示名（如交底人姓名）",
        ),
        sa.Column(
            "image_key",
            sa.String(500),
            nullable=False,
            comment="签名 PNG 存储键",
        ),
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="签名时间",
        ),
        sa.ForeignKeyConstraint(
            ["permit_id"], ["safety.work_permits.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], ["safety.work_permit_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["signer_user_id"], ["identity.users.id"]),
        *_base_constraints(),
        sa.UniqueConstraint(
            "permit_id", "round", "sign_key", name="uq_work_permit_signatures_row"
        ),
        schema="safety",
    )
    op.create_index(
        "ix_work_permit_signatures_permit",
        "work_permit_signatures",
        ["permit_id", "round"],
        schema="safety",
    )

    op.create_table(
        "work_permit_form_defaults",
        *_base_columns(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="用户（聊天发起人）",
        ),
        sa.Column("permit_type", sa.String(32), nullable=False, comment="票种"),
        sa.Column(
            "values",
            jsonb,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="上次填写快照（type_data/persons/gas/risk/measures）",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"]),
        *_base_constraints(),
        sa.UniqueConstraint(
            "user_id", "permit_type", name="uq_work_permit_form_defaults_user"
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_table("work_permit_form_defaults", schema="safety")
    op.drop_index(
        "ix_work_permit_signatures_permit",
        table_name="work_permit_signatures",
        schema="safety",
    )
    op.drop_table("work_permit_signatures", schema="safety")
