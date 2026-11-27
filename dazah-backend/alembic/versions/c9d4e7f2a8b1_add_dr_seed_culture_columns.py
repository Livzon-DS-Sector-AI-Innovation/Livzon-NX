"""add_dr_seed_culture_columns

Revision ID: c9d4e7f2a8b1
Revises: b5e8a3f7c2d6
Create Date: 2026-11-27 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d4e7f2a8b1"
down_revision: str | None = "b5e8a3f7c2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "seed_cultures",
        sa.Column(
            "maltodextrin_batch",
            sa.String(length=128),
            nullable=True,
            comment="麦芽糊精/批号（多拉菌素）",
        ),
        schema="production",
    )
    op.add_column(
        "seed_cultures",
        sa.Column(
            "cottonseed_meal_batch",
            sa.String(length=128),
            nullable=True,
            comment="棉籽饼粉/批号（多拉菌素）",
        ),
        schema="production",
    )
    op.add_column(
        "seed_cultures",
        sa.Column(
            "yeast_extract_batch",
            sa.String(length=128),
            nullable=True,
            comment="酵母浸粉/批号（多拉菌素）",
        ),
        schema="production",
    )
    op.add_column(
        "seed_cultures",
        sa.Column(
            "dimethylbutyric_acid_batch",
            sa.String(length=128),
            nullable=True,
            comment="二甲基丁酸/批号（多拉菌素）",
        ),
        schema="production",
    )
    op.add_column(
        "seed_cultures",
        sa.Column(
            "antifoam_batch",
            sa.String(length=128),
            nullable=True,
            comment="消泡剂/批号（多拉菌素）",
        ),
        schema="production",
    )
    op.add_column(
        "seed_cultures",
        sa.Column(
            "shaker_operator_people",
            JSONB(none_as_null=True),
            nullable=True,
            comment="上摇床人员/复核人（多拉菌素）",
        ),
        schema="production",
    )
    op.add_column(
        "seed_cultures",
        sa.Column(
            "bottle_washing_people",
            JSONB(none_as_null=True),
            nullable=True,
            comment="洗瓶子（多拉菌素）",
        ),
        schema="production",
    )


def downgrade() -> None:
    op.drop_column("seed_cultures", "bottle_washing_people", schema="production")
    op.drop_column("seed_cultures", "shaker_operator_people", schema="production")
    op.drop_column("seed_cultures", "antifoam_batch", schema="production")
    op.drop_column("seed_cultures", "dimethylbutyric_acid_batch", schema="production")
    op.drop_column("seed_cultures", "yeast_extract_batch", schema="production")
    op.drop_column("seed_cultures", "cottonseed_meal_batch", schema="production")
    op.drop_column("seed_cultures", "maltodextrin_batch", schema="production")
