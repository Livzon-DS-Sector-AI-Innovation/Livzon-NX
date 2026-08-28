"""add_seed_cultures_table

Revision ID: 8e5f6a7b9c0d
Revises: 7d4e5f6a8b9c
Create Date: 2026-07-06 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8e5f6a7b9c0d"
down_revision: str | None = "7d4e5f6a8b9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seed_cultures",
        sa.Column("batch_no", sa.String(64), nullable=False, comment="摇瓶批号"),
        sa.Column("prepare_date", sa.Date(), nullable=True, comment="配制日期"),
        sa.Column(
            "glucose_batch", sa.String(128), nullable=True, comment="葡萄糖/批号"
        ),
        sa.Column(
            "corn_starch_batch", sa.String(128), nullable=True, comment="玉米淀粉/批号"
        ),
        sa.Column(
            "corn_syrup_batch", sa.String(128), nullable=True, comment="玉米浆/批号"
        ),
        sa.Column(
            "ammonium_sulfate_batch",
            sa.String(128),
            nullable=True,
            comment="硫酸铵/批号",
        ),
        sa.Column(
            "soybean_meal_batch", sa.String(128), nullable=True, comment="黄豆饼粉/批号"
        ),
        sa.Column(
            "calcium_carbonate_batch",
            sa.String(128),
            nullable=True,
            comment="碳酸钙/批号",
        ),
        sa.Column(
            "prepare_operator",
            sa.String(64),
            nullable=True,
            comment="配制操作人/复核人",
        ),
        sa.Column(
            "sterilization_operator",
            sa.String(64),
            nullable=True,
            comment="种子消毒人员",
        ),
        sa.Column("ph_before_adjust", sa.Float(), nullable=True, comment="调前PH"),
        sa.Column("ph_after_adjust", sa.Float(), nullable=True, comment="调后PH"),
        sa.Column(
            "ph_after_sterilization", sa.Float(), nullable=True, comment="消后PH"
        ),
        sa.Column("reducing_sugar", sa.Float(), nullable=True, comment="还原糖"),
        sa.Column("total_sugar", sa.Float(), nullable=True, comment="总糖"),
        sa.Column("amino_nitrogen", sa.Float(), nullable=True, comment="氨基氮"),
        sa.Column("strain_tube_no", sa.String(64), nullable=True, comment="冻管菌号"),
        sa.Column(
            "shaker_setup_operator",
            sa.String(64),
            nullable=True,
            comment="上摇床摆东西人员",
        ),
        sa.Column("shaker_no", sa.String(64), nullable=True, comment="摇床编号"),
        sa.Column("shaker_start_date", sa.Date(), nullable=True, comment="上摇床日期"),
        sa.Column(
            "inoculation_operator",
            sa.String(64),
            nullable=True,
            comment="接种人员/复核人",
        ),
        sa.Column("tool_no", sa.String(64), nullable=True, comment="用具编号"),
        sa.Column(
            "merge_time", sa.DateTime(timezone=True), nullable=True, comment="并瓶时间"
        ),
        sa.Column("merge_count", sa.Integer(), nullable=True, comment="并瓶数量(瓶)"),
        sa.Column("merge_cycle", sa.String(64), nullable=True, comment="并瓶周期"),
        sa.Column("merge_ph", sa.Float(), nullable=True, comment="并瓶PH"),
        sa.Column(
            "merge_bacteria_density", sa.Float(), nullable=True, comment="并瓶菌浓"
        ),
        sa.Column("merge_total_sugar", sa.Float(), nullable=True, comment="并瓶总糖"),
        sa.Column(
            "merge_reducing_sugar", sa.Float(), nullable=True, comment="并瓶还原糖"
        ),
        sa.Column(
            "merge_amino_nitrogen", sa.Float(), nullable=True, comment="并瓶氨基氮"
        ),
        sa.Column(
            "tank_setup_operator",
            sa.String(64),
            nullable=True,
            comment="进罐摆东西人员",
        ),
        sa.Column("cylinder_no", sa.String(64), nullable=True, comment="钢瓶编号"),
        sa.Column(
            "merge_operator", sa.String(64), nullable=True, comment="并瓶操作人/复核人"
        ),
        sa.Column(
            "workshop_inoculation_operator",
            sa.String(64),
            nullable=True,
            comment="车间接种人员",
        ),
        sa.Column(
            "tank_remarks", sa.String(256), nullable=True, comment="备注（罐号）"
        ),
        sa.Column("tank_yield", sa.Float(), nullable=True, comment="罐产"),
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
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["identity.users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["identity.users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_seed_cultures_batch_no",
        "seed_cultures",
        ["batch_no"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_seed_cultures_prepare_date",
        "seed_cultures",
        ["prepare_date"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_seed_cultures_prepare_date", table_name="seed_cultures", schema="production"
    )
    op.drop_index(
        "ix_seed_cultures_batch_no", table_name="seed_cultures", schema="production"
    )
    op.drop_table("seed_cultures", schema="production")
