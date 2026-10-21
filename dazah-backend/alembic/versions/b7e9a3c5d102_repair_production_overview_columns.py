"""Repair historical overview columns on drifted development installations.

Revision ID: b7e9a3c5d102
Revises: a4d6f2b8c901

These columns are owned by a9e3c1f8b2d4 and b5d2e8a4c6f9 in the parent
history. This repair never removes existing plan order or extraction values.
"""

import sqlalchemy as sa

from alembic import op

revision = "b7e9a3c5d102"
down_revision = "a4d6f2b8c901"
branch_labels = None
depends_on = None
SCHEMA = "production"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in ("production_plans", "fermentation_batch_actuals"):
        if not inspector.has_table(table, schema=SCHEMA):
            raise RuntimeError(f"{table} is missing; review schema drift first")
    plan_columns = inspector.get_columns("production_plans", schema=SCHEMA)
    if not any(column["name"] == "row_order" for column in plan_columns):
        op.add_column(
            "production_plans",
            sa.Column(
                "row_order",
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="飞书表行序（同步写入，用于稳定排序）",
            ),
            schema=SCHEMA,
        )
    actual_columns = inspector.get_columns("fermentation_batch_actuals", schema=SCHEMA)
    if not any(column["name"] == "extract_kg" for column in actual_columns):
        op.add_column(
            "fermentation_batch_actuals",
            sa.Column(
                "extract_kg", sa.Float(), nullable=True, comment="提炼成品产量(kg)"
            ),
            schema=SCHEMA,
        )


def downgrade() -> None:
    # The parent chain still owns both columns, so keep their recorded values.
    pass
