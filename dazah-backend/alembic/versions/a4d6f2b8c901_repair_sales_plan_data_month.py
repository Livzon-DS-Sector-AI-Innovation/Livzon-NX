"""Repair the historical sales-plan month column on drifted installations.

Revision ID: a4d6f2b8c901
Revises: f6b8d2c4a190

The column belongs to c9d400000047 in the parent history. Preserve existing
monthly snapshots, including when this repair revision is downgraded.
"""

import sqlalchemy as sa

from alembic import op

revision = "a4d6f2b8c901"
down_revision = "f6b8d2c4a190"
branch_labels = None
depends_on = None
SCHEMA = "production"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("sales_plan_details", schema=SCHEMA):
        raise RuntimeError("sales_plan_details is missing; review schema drift first")
    columns = inspector.get_columns("sales_plan_details", schema=SCHEMA)
    if not any(column["name"] == "data_month" for column in columns):
        op.add_column(
            "sales_plan_details",
            sa.Column(
                "data_month",
                sa.String(7),
                nullable=True,
                comment="数据月份(YYYY-MM)，按源数据表名归属",
            ),
            schema=SCHEMA,
        )
    indexes = inspector.get_indexes("sales_plan_details", schema=SCHEMA)
    if not any(index["name"] == "ix_sales_plan_data_month" for index in indexes):
        op.create_index(
            "ix_sales_plan_data_month",
            "sales_plan_details",
            ["data_month"],
            schema=SCHEMA,
        )


def downgrade() -> None:
    # The parent chain already owns this column. Do not delete recorded months.
    pass
