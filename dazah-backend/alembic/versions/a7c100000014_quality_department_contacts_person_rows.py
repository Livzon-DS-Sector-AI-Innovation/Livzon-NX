"""refactor quality department contacts to person rows

Revision ID: a7c100000014
Revises: a7c100000013
Create Date: 2026-07-03 21:25:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000014"
down_revision: str | None = "a7c100000013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "department_contacts"
SCHEMA_NAME = "quality"


def _get_existing_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {
        column["name"]
        for column in inspector.get_columns(TABLE_NAME, schema=SCHEMA_NAME)
    }


def _get_existing_indexes() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {
        index["name"] for index in inspector.get_indexes(TABLE_NAME, schema=SCHEMA_NAME)
    }


def _get_existing_unique_constraints() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            TABLE_NAME, schema=SCHEMA_NAME
        )
        if constraint.get("name")
    }


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    existing_columns = _get_existing_columns()
    existing_indexes = _get_existing_indexes()
    existing_unique_constraints = _get_existing_unique_constraints()

    if "name" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("name", sa.String(length=255), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "enterprise_email" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("enterprise_email", sa.String(length=255), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "open_id" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("open_id", sa.String(length=255), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "department_head_name" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("department_head_name", sa.String(length=255), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "department_head_enterprise_email" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "department_head_enterprise_email",
                sa.String(length=255),
                nullable=True,
            ),
            schema=SCHEMA_NAME,
        )
    if "department_head_open_id" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("department_head_open_id", sa.String(length=255), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "feishu_record_id" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("feishu_record_id", sa.String(length=255), nullable=True),
            schema=SCHEMA_NAME,
        )

    if "department_contacts_department_key" in existing_unique_constraints:
        op.drop_constraint(
            "department_contacts_department_key",
            TABLE_NAME,
            schema=SCHEMA_NAME,
            type_="unique",
        )

    # Old foreign-key-backed columns need explicit constraint cleanup before dropping.
    op.execute(
        "ALTER TABLE quality.department_contacts "
        "DROP CONSTRAINT IF EXISTS department_contacts_dept_head_id_fkey"
    )
    op.execute(
        "ALTER TABLE quality.department_contacts "
        "DROP CONSTRAINT IF EXISTS department_contacts_production_head_id_fkey"
    )
    op.execute(
        "ALTER TABLE quality.department_contacts "
        "DROP CONSTRAINT IF EXISTS department_contacts_quality_head_id_fkey"
    )

    existing_columns = _get_existing_columns()
    for column_name in (
        "dept_head_id",
        "qa_staff_ids",
        "gmp_staff_ids",
        "production_head_id",
        "quality_head_id",
        "additional_contacts",
        "is_production_workshop",
    ):
        if column_name in existing_columns:
            op.drop_column(TABLE_NAME, column_name, schema=SCHEMA_NAME)

    if "ix_quality_department_contacts_name" not in existing_indexes:
        op.create_index(
            "ix_quality_department_contacts_name",
            TABLE_NAME,
            ["name"],
            unique=False,
            schema=SCHEMA_NAME,
        )
    if "ix_quality_department_contacts_department" not in existing_indexes:
        op.create_index(
            "ix_quality_department_contacts_department",
            TABLE_NAME,
            ["department"],
            unique=False,
            schema=SCHEMA_NAME,
        )
    if "ix_quality_department_contacts_open_id" not in existing_indexes:
        op.create_index(
            "ix_quality_department_contacts_open_id",
            TABLE_NAME,
            ["open_id"],
            unique=True,
            schema=SCHEMA_NAME,
        )
    if "ix_quality_department_contacts_feishu_record_id" not in existing_indexes:
        op.create_index(
            "ix_quality_department_contacts_feishu_record_id",
            TABLE_NAME,
            ["feishu_record_id"],
            unique=False,
            schema=SCHEMA_NAME,
        )


def downgrade() -> None:
    existing_indexes = _get_existing_indexes()
    for index_name in (
        "ix_quality_department_contacts_feishu_record_id",
        "ix_quality_department_contacts_open_id",
        "ix_quality_department_contacts_name",
        "ix_quality_department_contacts_department",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=TABLE_NAME, schema=SCHEMA_NAME)

    existing_columns = _get_existing_columns()
    if "is_production_workshop" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "is_production_workshop",
                sa.Boolean(),
                nullable=True,
                server_default="false",
            ),
            schema=SCHEMA_NAME,
        )
    if "additional_contacts" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("additional_contacts", sa.ARRAY(sa.Text()), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "quality_head_id" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("quality_head_id", sa.UUID(), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "production_head_id" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("production_head_id", sa.UUID(), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "gmp_staff_ids" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("gmp_staff_ids", sa.ARRAY(sa.Text()), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "qa_staff_ids" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("qa_staff_ids", sa.ARRAY(sa.Text()), nullable=True),
            schema=SCHEMA_NAME,
        )
    if "dept_head_id" not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("dept_head_id", sa.UUID(), nullable=True),
            schema=SCHEMA_NAME,
        )

    op.execute(
        "ALTER TABLE quality.department_contacts "
        "ADD CONSTRAINT department_contacts_dept_head_id_fkey "
        "FOREIGN KEY (dept_head_id) REFERENCES identity.users (id)"
    )
    op.execute(
        "ALTER TABLE quality.department_contacts "
        "ADD CONSTRAINT department_contacts_production_head_id_fkey "
        "FOREIGN KEY (production_head_id) REFERENCES identity.users (id)"
    )
    op.execute(
        "ALTER TABLE quality.department_contacts "
        "ADD CONSTRAINT department_contacts_quality_head_id_fkey "
        "FOREIGN KEY (quality_head_id) REFERENCES identity.users (id)"
    )

    existing_columns = _get_existing_columns()
    for column_name in (
        "feishu_record_id",
        "department_head_open_id",
        "department_head_enterprise_email",
        "department_head_name",
        "open_id",
        "enterprise_email",
        "name",
    ):
        if column_name in existing_columns:
            op.drop_column(TABLE_NAME, column_name, schema=SCHEMA_NAME)

    existing_unique_constraints = _get_existing_unique_constraints()
    if "department_contacts_department_key" not in existing_unique_constraints:
        op.create_unique_constraint(
            "department_contacts_department_key",
            TABLE_NAME,
            ["department"],
            schema=SCHEMA_NAME,
        )
