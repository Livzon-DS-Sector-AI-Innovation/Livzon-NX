"""add_non_conforming_events_table

Revision ID: 1f2e3d4c5b6a
Revises: 0a1b2c3d4e5f
Create Date: 2026-07-08
"""

import sqlalchemy as sa

from alembic import op

revision = "1f2e3d4c5b6a"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("non_conforming_events", schema="production"):
        op.drop_table("non_conforming_events", schema="production")
    op.create_table(
        "non_conforming_events",
        sa.Column(
            "event_time", sa.DateTime(timezone=True), nullable=False, comment="发生时间"
        ),
        sa.Column(
            "restore_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="恢复正常时间",
        ),
        sa.Column("impact_duration", sa.String(64), nullable=True, comment="影响时间"),
        sa.Column("event_type", sa.String(32), nullable=False, comment="事件类型"),
        sa.Column("workshop", sa.String(64), nullable=False, comment="车间"),
        sa.Column("description", sa.Text(), nullable=True, comment="事件描述"),
        sa.Column("impact_scope", sa.Text(), nullable=True, comment="影响范围"),
        sa.Column("action_taken", sa.Text(), nullable=True, comment="处理措施"),
        sa.Column("remarks", sa.Text(), nullable=True, comment="备注"),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_nce_event_time",
        "non_conforming_events",
        ["event_time"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_nce_workshop",
        "non_conforming_events",
        ["workshop"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_nce_event_type",
        "non_conforming_events",
        ["event_type"],
        unique=False,
        schema="production",
    )


def downgrade():
    op.drop_table("non_conforming_events", schema="production")
