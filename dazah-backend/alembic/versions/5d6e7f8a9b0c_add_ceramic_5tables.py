"""add_ceramic_5tables

Revision ID: 5d6e7f8a9b0c
Revises: 4c5d6e7f8a9b
Create Date: 2026-07-09
"""

import sqlalchemy as sa

from alembic import op

revision = "5d6e7f8a9b0c"
down_revision = "4c5d6e7f8a9b"

TABLES = {
    "ceramic_feeds": [
        ("feed_date", sa.DateTime(timezone=True)),
        ("feed_batch", sa.String(128), False),
        ("feed_total_volume", sa.Float()),
        ("feed_titer", sa.Float()),
        ("feed_temp", sa.Float()),
        ("feed_ph", sa.Float()),
        ("operator", sa.String(64)),
    ],
    "ceramic_membrane_ops": [
        ("run_date", sa.DateTime(timezone=True)),
        ("batch_no", sa.String(128), False),
        ("membrane_no", sa.String(64)),
        ("run_duration", sa.Float()),
        ("tmp", sa.Float()),
        ("inlet_pressure", sa.Float()),
        ("outlet_pressure", sa.Float()),
        ("membrane_flux", sa.Float()),
        ("circulation_flow", sa.Float()),
        ("filter_temp", sa.Float()),
        ("operator", sa.String(64)),
    ],
    "ceramic_membrane_cleans": [
        ("clean_date", sa.DateTime(timezone=True)),
        ("membrane_no", sa.String(64)),
        ("clean_batch", sa.String(128), False),
        ("cleaner_type", sa.String(64)),
        ("cleaner_amount", sa.Float()),
        ("clean_duration", sa.Float()),
        ("flux_before", sa.Float()),
        ("flux_after", sa.Float()),
        ("flux_recovery", sa.Float()),
        ("clean_evaluation", sa.String(256)),
        ("operator", sa.String(64)),
    ],
    "ceramic_material_separations": [
        ("batch_no", sa.String(128), False),
        ("feed_total", sa.Float()),
        ("feed_titer", sa.Float()),
        ("permeate_total", sa.Float()),
        ("permeate_titer", sa.Float()),
        ("permeate_volume", sa.Float()),
        ("concentrate_weight", sa.Float()),
        ("residue_titer", sa.Float()),
        ("solid_content", sa.Float()),
        ("filter_yield", sa.Float()),
        ("filter_loss", sa.Float()),
        ("clogging_pressure", sa.Float()),
        ("operator", sa.String(64)),
    ],
    "ceramic_equipment_logs": [
        ("record_date", sa.DateTime(timezone=True)),
        ("membrane_no", sa.String(64)),
        ("total_runtime", sa.Float()),
        ("current_runtime", sa.Float()),
        ("run_status", sa.String(32)),
        ("pressure_abnormal", sa.String(256)),
        ("abnormal_desc", sa.Text()),
        ("action_taken", sa.Text()),
        ("action_result", sa.Text()),
        ("recorder", sa.String(64)),
    ],
}


def upgrade():
    for tname, cols in TABLES.items():
        columns = [sa.Column("seq_no", sa.Integer(), nullable=True)]
        for cname, ctype, *rest in [
            (c[0], c[1], c[2] if len(c) > 2 else True) for c in cols
        ]:
            nullable = rest[0] if rest else True
            columns.append(sa.Column(cname, ctype, nullable=nullable))
        columns += [
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
            sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
            sa.PrimaryKeyConstraint("id"),
        ]
        op.create_table(tname, *columns, schema="production")


def downgrade():
    for tname in reversed(list(TABLES.keys())):
        op.drop_table(tname, schema="production")
