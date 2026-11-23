"""Keep legacy seed-culture text columns alongside structured person data."""

import sqlalchemy as sa

from alembic import op

revision = "4bd62e5d78a1"
down_revision = "c7d9e1f3a5b7"
branch_labels = None
depends_on = None

SCHEMA = "production"
TABLE = "seed_cultures"
PERSON_COLUMNS = (
    "prepare_operator",
    "sterilization_operator",
    "shaker_setup_operator",
    "inoculation_operator",
    "tank_setup_operator",
    "merge_operator",
    "workshop_inoculation_operator",
)


def _legacy_text(value: str) -> str:
    return f"""CASE jsonb_typeof({value})
        WHEN 'string' THEN {value} #>> '{{}}'
        WHEN 'array' THEN (
            SELECT string_agg(
                NULLIF(btrim(person ->> 'name'), ''), '、' ORDER BY position
            )
            FROM jsonb_array_elements({value}) WITH ORDINALITY
                AS people(person, position)
        )
    END"""


def upgrade() -> None:
    for name in PERSON_COLUMNS:
        op.alter_column(TABLE, name, new_column_name=f"{name}_people", schema=SCHEMA)
        op.add_column(
            TABLE,
            sa.Column(name, sa.Text(), comment=f"Legacy projection of {name}_people"),
            schema=SCHEMA,
        )

    assignments = ",\n".join(
        f"{name} = {_legacy_text(f'{name}_people')}" for name in PERSON_COLUMNS
    )
    op.execute(f"UPDATE {SCHEMA}.{TABLE} SET {assignments}")

    # Resubmitting the same legacy display name preserves the identity and avatar.
    synchronize = "\n".join(
        f"""
        IF TG_OP = 'INSERT' THEN
            IF NEW.{name}_people IS NULL THEN
                NEW.{name}_people := to_jsonb(NEW.{name});
            ELSE
                NEW.{name} := {_legacy_text(f"NEW.{name}_people")};
            END IF;
        ELSIF NEW.{name}_people IS DISTINCT FROM OLD.{name}_people THEN
            NEW.{name} := {_legacy_text(f"NEW.{name}_people")};
        ELSIF NEW.{name} IS DISTINCT FROM OLD.{name} THEN
            NEW.{name}_people := to_jsonb(NEW.{name});
        END IF;"""
        for name in PERSON_COLUMNS
    )
    op.execute(f"""
        CREATE FUNCTION {SCHEMA}.sync_seed_culture_people() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            {synchronize}
            RETURN NEW;
        END;
        $$
    """)
    op.execute(f"""
        CREATE TRIGGER sync_seed_culture_people
        BEFORE INSERT OR UPDATE ON {SCHEMA}.{TABLE}
        FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.sync_seed_culture_people()
    """)


def downgrade() -> None:
    op.execute(f"DROP TRIGGER sync_seed_culture_people ON {SCHEMA}.{TABLE}")
    op.execute(f"DROP FUNCTION {SCHEMA}.sync_seed_culture_people()")
    for name in PERSON_COLUMNS:
        op.drop_column(TABLE, name, schema=SCHEMA)
        op.alter_column(
            TABLE,
            f"{name}_people",
            new_column_name=name,
            schema=SCHEMA,
        )
