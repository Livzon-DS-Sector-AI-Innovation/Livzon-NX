"""registration 软删除唯一约束改为部分唯一索引

软删除表的原 UniqueConstraint 把 is_deleted 一并纳入唯一列，
同一逻辑键第二次软删除（出现两行 is_deleted=true）会触发
IntegrityError。改为 partial unique index（仅约束未删除行），
删除行不再参与唯一性，历史软删版本可共存。

Revision ID: b7c3d9e4f6a1
Revises: f7a8b9c0d1e2
Create Date: 2026-08-30
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c3d9e4f6a1"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None

# (schema.table, 约束名, 唯一列, partial index 名)
TARGETS = [
    (
        "registration.declaration_progress_versions",
        "uq_registration_declaration_progress_versions_group_version",
        ["record_group_id", "version_number"],
        "uq_registration_declaration_progress_versions_group_version",
    ),
    (
        "registration.declaration_progress_workbook_versions",
        "uq_registration_declaration_progress_workbook_group_version",
        ["record_group_id", "version_number"],
        "uq_registration_declaration_progress_workbook_group_version",
    ),
    (
        "registration.drug_nodes",
        "uq_drug_nodes_drug_node",
        ["drug_id", "node_index"],
        "uq_drug_nodes_drug_node",
    ),
]


def upgrade() -> None:
    for table, constraint, columns, index_name in TARGETS:
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{constraint}"')
        columns_csv = ", ".join(f'"{c}"' for c in columns)
        op.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" '
            f"ON {table} ({columns_csv}) "
            "WHERE is_deleted = false"
        )


def downgrade() -> None:
    for table, constraint, columns, index_name in TARGETS:
        op.execute(f'DROP INDEX IF EXISTS "{index_name}"')
        columns_csv = ", ".join(f'"{c}"' for c in columns) + ', "is_deleted"'
        op.execute(
            f'ALTER TABLE {table} ADD CONSTRAINT "{constraint}" UNIQUE ({columns_csv})'
        )
