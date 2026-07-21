"""safety module tables

Revision ID: 20260602_0001
Revises: 20260601_0001
Create Date: 2026-06-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260602_0001"
down_revision: str | None = "20260601_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ========== Safety Checks Table ==========
    op.create_table(
        "safety_checks",
        sa.Column("check_no", sa.String(length=64), nullable=False),
        sa.Column("check_type", sa.String(length=32), server_default=sa.text("'daily'"), nullable=False),
        sa.Column("check_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("inspector", sa.Uuid(), nullable=True),
        sa.Column("inspector_name", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=True),
        sa.Column("rectification_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rectification_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rectification_status", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["inspector"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("check_no", name="uq_safety_checks_check_no"),
        schema="safety",
    )
    op.create_index("idx_safety_checks_check_no", "safety_checks", ["check_no"], schema="safety")
    op.create_index("idx_safety_checks_status", "safety_checks", ["status"], schema="safety")
    op.create_index("idx_safety_checks_check_type", "safety_checks", ["check_type"], schema="safety")
    op.create_index("idx_safety_checks_check_date", "safety_checks", ["check_date"], schema="safety")

    # ========== Hazard Reports Table ==========
    op.create_table(
        "hazard_reports",
        sa.Column("hazard_no", sa.String(length=64), nullable=False),
        sa.Column("hazard_type", sa.String(length=32), nullable=False),
        sa.Column("hazard_level", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("discovered_by", sa.Uuid(), nullable=True),
        sa.Column("discovered_by_name", sa.String(length=100), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("control_measures", sa.Text(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rectification_status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("verified_by_name", sa.String(length=100), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'open'"), nullable=False),
        sa.Column("check_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["check_id"], ["safety.safety_checks.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["discovered_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["verified_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hazard_no", name="uq_hazard_reports_hazard_no"),
        schema="safety",
    )
    op.create_index("idx_hazard_reports_hazard_no", "hazard_reports", ["hazard_no"], schema="safety")
    op.create_index("idx_hazard_reports_status", "hazard_reports", ["status"], schema="safety")
    op.create_index("idx_hazard_reports_hazard_type", "hazard_reports", ["hazard_type"], schema="safety")
    op.create_index("idx_hazard_reports_hazard_level", "hazard_reports", ["hazard_level"], schema="safety")
    op.create_index("idx_hazard_reports_department", "hazard_reports", ["department"], schema="safety")
    op.create_index("idx_hazard_reports_check_id", "hazard_reports", ["check_id"], schema="safety")

    # ========== Accidents Table ==========
    op.create_table(
        "accidents",
        sa.Column("accident_no", sa.String(length=64), nullable=False),
        sa.Column("accident_type", sa.String(length=32), nullable=False),
        sa.Column("accident_level", sa.String(length=32), nullable=False),
        sa.Column("happened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("casualties", sa.String(length=255), nullable=True),
        sa.Column("property_damage", sa.Float(), nullable=True),
        sa.Column("direct_cause", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("handling_measures", sa.Text(), nullable=True),
        sa.Column("corrective_actions", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'reported'"), nullable=False),
        sa.Column("reported_by", sa.Uuid(), nullable=True),
        sa.Column("reported_by_name", sa.String(length=100), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("investigator", sa.Uuid(), nullable=True),
        sa.Column("investigator_name", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["investigator"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["reported_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("accident_no", name="uq_accidents_accident_no"),
        schema="safety",
    )
    op.create_index("idx_accidents_accident_no", "accidents", ["accident_no"], schema="safety")
    op.create_index("idx_accidents_status", "accidents", ["status"], schema="safety")
    op.create_index("idx_accidents_accident_type", "accidents", ["accident_type"], schema="safety")
    op.create_index("idx_accidents_happened_at", "accidents", ["happened_at"], schema="safety")

    # ========== Safety Trainings Table ==========
    op.create_table(
        "safety_trainings",
        sa.Column("training_no", sa.String(length=64), nullable=False),
        sa.Column("training_name", sa.String(length=255), nullable=False),
        sa.Column("training_type", sa.String(length=32), nullable=False),
        sa.Column("training_mode", sa.String(length=16), nullable=False),
        sa.Column("trainer", sa.Uuid(), nullable=True),
        sa.Column("trainer_name", sa.String(length=100), nullable=True),
        sa.Column("training_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_hours", sa.Float(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["trainer"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("training_no", name="uq_safety_trainings_training_no"),
        schema="safety",
    )
    op.create_index("idx_safety_trainings_training_no", "safety_trainings", ["training_no"], schema="safety")
    op.create_index("idx_safety_trainings_status", "safety_trainings", ["status"], schema="safety")
    op.create_index("idx_safety_trainings_training_type", "safety_trainings", ["training_type"], schema="safety")
    op.create_index("idx_safety_trainings_training_date", "safety_trainings", ["training_date"], schema="safety")

    # ========== Training Records Table ==========
    op.create_table(
        "training_records",
        sa.Column("training_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("employee_name", sa.String(length=100), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("attendance", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["training_id"], ["safety.safety_trainings.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="safety",
    )
    op.create_index("idx_training_records_training_id", "training_records", ["training_id"], schema="safety")
    op.create_index("idx_training_records_employee_id", "training_records", ["employee_id"], schema="safety")


def downgrade() -> None:
    op.drop_table("training_records", schema="safety")
    op.drop_table("safety_trainings", schema="safety")
    op.drop_table("accidents", schema="safety")
    op.drop_table("hazard_reports", schema="safety")
    op.drop_table("safety_checks", schema="safety")
