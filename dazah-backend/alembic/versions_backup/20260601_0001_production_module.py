"""production module tables

Revision ID: 20260601_0001
Revises: 20260529_0001
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0001"
down_revision: str | None = "20260529_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ========== Batches Table ==========
    op.create_table(
        "batches",
        sa.Column("batch_no", sa.String(length=64), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("specification", sa.String(length=100), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("planned_qty", sa.Float(), nullable=True),
        sa.Column("actual_qty", sa.Float(), nullable=True),
        sa.Column("process_spec_id", sa.Uuid(), nullable=True),
        sa.Column("production_line", sa.String(length=100), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_no", name="uq_batches_batch_no"),
        schema="production",
    )
    op.create_index(
        "idx_batches_batch_no", "batches", ["batch_no"], unique=False, schema="production"
    )
    op.create_index(
        "idx_batches_product_code", "batches", ["product_code"], unique=False, schema="production"
    )
    op.create_index(
        "idx_batches_status", "batches", ["status"], unique=False, schema="production"
    )

    # ========== Batch Materials Table ==========
    op.create_table(
        "batch_materials",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("material_code", sa.String(length=64), nullable=False),
        sa.Column("material_name", sa.String(length=255), nullable=True),
        sa.Column("material_type", sa.String(length=50), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("planned_qty", sa.Float(), nullable=True),
        sa.Column("actual_qty", sa.Float(), nullable=True),
        sa.Column("lot_no", sa.String(length=64), nullable=True),
        sa.Column("stage", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["production.batches.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "idx_batch_materials_batch_id", "batch_materials", ["batch_id"], unique=False, schema="production"
    )

    # ========== Production Plans Table ==========
    op.create_table(
        "production_plans",
        sa.Column("plan_no", sa.String(length=64), nullable=False),
        sa.Column("plan_name", sa.String(length=255), nullable=True),
        sa.Column("plan_type", sa.String(length=50), nullable=True),
        sa.Column("plan_month", sa.String(length=7), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("total_batches", sa.Integer(), nullable=True),
        sa.Column("completed_batches", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_no", name="uq_production_plans_plan_no"),
        schema="production",
    )
    op.create_index(
        "idx_production_plans_plan_month", "production_plans", ["plan_month"], unique=False, schema="production"
    )
    op.create_index(
        "idx_production_plans_status", "production_plans", ["status"], unique=False, schema="production"
    )

    # ========== Plan Tasks Table ==========
    op.create_table(
        "plan_tasks",
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("batch_qty", sa.Integer(), nullable=True),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_name", sa.String(length=100), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["production.production_plans.id"]),
        sa.ForeignKeyConstraint(["assigned_to"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "idx_plan_tasks_plan_id", "plan_tasks", ["plan_id"], unique=False, schema="production"
    )

    # ========== Process Specs Table ==========
    op.create_table(
        "process_specs",
        sa.Column("spec_code", sa.String(length=64), nullable=False),
        sa.Column("spec_name", sa.String(length=255), nullable=True),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("version", sa.String(length=20), server_default=sa.text("'1.0'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_by_name", sa.String(length=100), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_version", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("spec_code", "version", name="uq_process_specs_code_version"),
        schema="production",
    )
    op.create_index(
        "idx_process_specs_product_code", "process_specs", ["product_code"], unique=False, schema="production"
    )
    op.create_index(
        "idx_process_specs_status", "process_specs", ["status"], unique=False, schema="production"
    )

    # ========== Process Steps Table ==========
    op.create_table(
        "process_steps",
        sa.Column("spec_id", sa.Uuid(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("equipment_type", sa.String(length=100), nullable=True),
        sa.Column("equipment_spec", sa.String(length=255), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("sequence_order", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["spec_id"], ["production.process_specs.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "idx_process_steps_spec_id", "process_steps", ["spec_id"], unique=False, schema="production"
    )

    # ========== Process Parameters Table ==========
    op.create_table(
        "process_parameters",
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("param_name", sa.String(length=255), nullable=False),
        sa.Column("param_code", sa.String(length=64), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("is_critical", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("data_type", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["step_id"], ["production.process_steps.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "idx_process_parameters_step_id", "process_parameters", ["step_id"], unique=False, schema="production"
    )

    # ========== Production Records Table ==========
    op.create_table(
        "production_records",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("record_no", sa.String(length=64), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=True),
        sa.Column("step_name", sa.String(length=255), nullable=True),
        sa.Column("operator", sa.Uuid(), nullable=True),
        sa.Column("operator_name", sa.String(length=100), nullable=True),
        sa.Column(
            "operation_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("operation_type", sa.String(length=50), nullable=False),
        sa.Column("parameters", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["production.batches.id"]),
        sa.ForeignKeyConstraint(["operator"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "record_no", name="uq_production_records_batch_record"),
        schema="production",
    )
    op.create_index(
        "idx_production_records_batch_id", "production_records", ["batch_id"], unique=False, schema="production"
    )
    op.create_index(
        "idx_production_records_operation_time", "production_records", ["operation_time"], unique=False, schema="production"
    )

    # ========== Material Balances Table ==========
    op.create_table(
        "material_balances",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("input_qty", sa.Float(), nullable=True),
        sa.Column("output_qty", sa.Float(), nullable=True),
        sa.Column("loss_qty", sa.Float(), nullable=True),
        sa.Column("balance_rate", sa.Float(), nullable=True),
        sa.Column("min_balance_rate", sa.Float(), server_default=sa.text("95.0"), nullable=False),
        sa.Column("is_balanced", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deviation_rate", sa.Float(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["production.batches.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", name="uq_material_balances_batch_id"),
        schema="production",
    )


def downgrade() -> None:
    op.drop_table("material_balances", schema="production")
    op.drop_table("production_records", schema="production")
    op.drop_table("process_parameters", schema="production")
    op.drop_table("process_steps", schema="production")
    op.drop_table("process_specs", schema="production")
    op.drop_table("plan_tasks", schema="production")
    op.drop_table("production_plans", schema="production")
    op.drop_table("batch_materials", schema="production")
    op.drop_table("batches", schema="production")