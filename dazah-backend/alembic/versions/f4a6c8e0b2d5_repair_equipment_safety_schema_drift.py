"""Restore missing objects already owned by the equipment/safety parent history.

Revision ID: f4a6c8e0b2d5
Revises: d1f2a3b4c5d6

Some installations record the parent head without its last additive objects.
Keep historical revisions unchanged and repair only those known omissions.
Existing rows, column values, and correctly migrated installations are preserved.
"""

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision = "f4a6c8e0b2d5"
down_revision = "d1f2a3b4c5d6"
branch_labels = None
depends_on = None

EQUIPMENT_SCHEMA = "equipment"
SAFETY_SCHEMA = "safety"


def _standard_columns() -> tuple[
    sa.Column[UUID],
    sa.Column[datetime],
    sa.Column[datetime],
    sa.Column[UUID],
    sa.Column[UUID],
    sa.Column[bool],
]:
    return (
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("identity.users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("identity.users.id")),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )


def _preflight(inspector: Inspector) -> None:
    for schema, table in (
        (EQUIPMENT_SCHEMA, "inspection_feishu_config"),
        (SAFETY_SCHEMA, "feishu_app_settings"),
        (SAFETY_SCHEMA, "page_feishu_configs"),
        (SAFETY_SCHEMA, "hazard_identifications"),
    ):
        if not inspector.has_table(table, schema=schema):
            raise RuntimeError(f"{schema}.{table} is missing; review schema drift")
    # An unexpectedly incomplete old table needs review rather than silent reuse.
    for table, required in {
        "fire_equipment": {"id", "page_key", "table_id", "record_id", "fields"},
        "fire_inspection_records": {"id", "equipment_id", "items", "result"},
        "fire_expiry_notification_log": {"id", "equipment_id", "milestone_days"},
    }.items():
        if inspector.has_table(table, schema=SAFETY_SCHEMA):
            actual = {
                column["name"]
                for column in inspector.get_columns(table, schema=SAFETY_SCHEMA)
            }
            if required - actual:
                raise RuntimeError(
                    f"{SAFETY_SCHEMA}.{table} is incomplete; review schema drift"
                )


def _add_column[ColumnValue](
    schema: str, table: str, column: sa.Column[ColumnValue]
) -> None:
    columns = sa.inspect(op.get_bind()).get_columns(table, schema=schema)
    if not any(item["name"] == column.name for item in columns):
        op.add_column(table, column, schema=schema)


def _create_index(
    name: str,
    table: str,
    columns: list[str],
    *,
    unique: bool = False,
    active_only: bool = False,
) -> None:
    indexes = sa.inspect(op.get_bind()).get_indexes(table, schema=SAFETY_SCHEMA)
    if not any(item["name"] == name for item in indexes):
        if active_only:
            op.create_index(
                name,
                table,
                columns,
                unique=unique,
                schema=SAFETY_SCHEMA,
                postgresql_where=sa.text("is_deleted = false"),
            )
        else:
            op.create_index(name, table, columns, unique=unique, schema=SAFETY_SCHEMA)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    _preflight(inspector)
    _add_column(
        EQUIPMENT_SCHEMA,
        "inspection_feishu_config",
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
    )
    _add_column(
        SAFETY_SCHEMA,
        "page_feishu_configs",
        sa.Column("writeback_table_id", sa.String(100), nullable=True),
    )
    for name, kind in (
        ("tense", sa.String(50)),
        ("state", sa.String(50)),
        ("responsible_unit", sa.String(100)),
        ("check_frequency", sa.String(100)),
        ("check_standard", sa.Text()),
        ("is_major_hazard", sa.String(10)),
    ):
        _add_column(SAFETY_SCHEMA, "hazard_identifications", sa.Column(name, kind))
    _add_column(
        SAFETY_SCHEMA,
        "feishu_app_settings",
        sa.Column(
            "fire_expiry_notify_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    for name in ("milestones", "chat_ids", "user_ids"):
        _add_column(
            SAFETY_SCHEMA,
            "feishu_app_settings",
            sa.Column(f"fire_expiry_notify_{name}", sa.JSON(), nullable=True),
        )

    if not inspector.has_table("fire_equipment", schema=SAFETY_SCHEMA):
        op.create_table(
            "fire_equipment",
            sa.Column("page_key", sa.String(160), nullable=False),
            sa.Column("table_id", sa.String(64), nullable=False),
            sa.Column("record_id", sa.String(64), nullable=False),
            sa.Column("tab_name", sa.String(120), nullable=False, server_default=""),
            sa.Column(
                "equipment_type",
                sa.String(20),
                nullable=False,
                server_default="extinguisher",
            ),
            sa.Column(
                "equipment_no", sa.String(100), nullable=False, server_default=""
            ),
            sa.Column("department", sa.String(200), nullable=False, server_default=""),
            sa.Column("location", sa.String(200), nullable=False, server_default=""),
            sa.Column("fields", JSONB(), nullable=False),
            sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("last_inspected_at", sa.DateTime(timezone=True)),
            sa.Column("last_inspection_result", sa.String(20)),
            sa.Column(
                "last_synced_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            *_standard_columns(),
            schema=SAFETY_SCHEMA,
        )
    _add_column(SAFETY_SCHEMA, "fire_equipment", sa.Column("expiry_date", sa.Date()))
    _create_index(
        "uq_safety_fire_equipment_source_record",
        "fire_equipment",
        ["table_id", "record_id"],
        unique=True,
        active_only=True,
    )
    _create_index(
        "ix_safety_fire_equipment_page", "fire_equipment", ["page_key", "is_deleted"]
    )

    if not inspector.has_table("fire_inspection_records", schema=SAFETY_SCHEMA):
        op.create_table(
            "fire_inspection_records",
            sa.Column(
                "equipment_id",
                sa.Uuid(),
                sa.ForeignKey(f"{SAFETY_SCHEMA}.fire_equipment.id"),
                nullable=False,
            ),
            sa.Column("equipment_type", sa.String(20), nullable=False),
            sa.Column(
                "equipment_no", sa.String(100), nullable=False, server_default=""
            ),
            sa.Column("department", sa.String(200), nullable=False, server_default=""),
            sa.Column("location", sa.String(200), nullable=False, server_default=""),
            sa.Column("items", JSONB(), nullable=False),
            sa.Column("result", sa.String(20), nullable=False),
            sa.Column("failed_items", JSONB()),
            sa.Column("abnormal_action", sa.Text()),
            sa.Column("inspector_id", sa.Uuid()),
            sa.Column(
                "inspector_name", sa.String(100), nullable=False, server_default=""
            ),
            sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source", sa.String(20), nullable=False, server_default="web"),
            *_standard_columns(),
            schema=SAFETY_SCHEMA,
        )
    _add_column(
        SAFETY_SCHEMA,
        "fire_inspection_records",
        sa.Column("feishu_record_id", sa.String(64)),
    )
    _create_index(
        "ix_safety_fire_inspections_equipment",
        "fire_inspection_records",
        ["equipment_id", "inspected_at"],
    )
    _create_index(
        "ix_safety_fire_inspections_inspected_at",
        "fire_inspection_records",
        ["inspected_at"],
    )
    if not inspector.has_table("fire_expiry_notification_log", schema=SAFETY_SCHEMA):
        op.create_table(
            "fire_expiry_notification_log",
            sa.Column(
                "equipment_id",
                sa.Uuid(),
                sa.ForeignKey(f"{SAFETY_SCHEMA}.fire_equipment.id"),
                nullable=False,
            ),
            sa.Column("milestone_days", sa.Integer(), nullable=False),
            sa.Column("notified_at", sa.DateTime(timezone=True), nullable=False),
            *_standard_columns(),
            sa.UniqueConstraint(
                "equipment_id",
                "milestone_days",
                name="uq_fire_expiry_notify_once_per_milestone",
            ),
            schema=SAFETY_SCHEMA,
        )


def downgrade() -> None:
    # Parent revisions still own these objects; keep their rows and values.
    pass
