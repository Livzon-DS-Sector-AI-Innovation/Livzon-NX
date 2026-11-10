from io import StringIO
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateIndex

from app.platform.identity.models import Role

REVISION = "b3a6d7e8f902"
OLD_CONSTRAINT = "uq_identity_roles_code"
ACTIVE_INDEX = "uq_identity_roles_active_code"


def test_role_code_upgrade_matches_model_and_keeps_active_uniqueness() -> None:
    migration = ScriptDirectory("alembic").get_revision(REVISION)
    assert migration is not None
    statements = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": statements}
    )
    with Operations.context(context):
        migration.module.upgrade()
        migration.module.downgrade()

    index = next(
        index for index in Role.__table__.indexes if index.name == ACTIVE_INDEX
    )
    expected_index = (
        f"CREATE UNIQUE INDEX {ACTIVE_INDEX} ON identity.roles (code) "
        "WHERE is_deleted = false"
    )
    assert str(CreateIndex(index).compile(dialect=dialect())) == expected_index
    assert [line for line in statements.getvalue().splitlines() if line] == [
        f"{expected_index};",
        f"ALTER TABLE identity.roles DROP CONSTRAINT {OLD_CONSTRAINT};",
        f"ALTER TABLE identity.roles ADD CONSTRAINT {OLD_CONSTRAINT} UNIQUE (code);",
        f"DROP INDEX identity.{ACTIVE_INDEX};",
    ]


async def test_role_code_reuse_preserves_history_and_blocks_active_duplicates(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = ScriptDirectory("alembic").get_revision(REVISION)
    assert migration is not None
    schema = f"role_code_{uuid4().hex}"
    monkeypatch.setattr(migration.module, "SCHEMA", schema)
    roles = sa.Table(
        "roles",
        sa.MetaData(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code", name=OLD_CONSTRAINT),
        schema=schema,
    )
    connection = await db_session.connection()

    def verify(conn: sa.Connection) -> None:
        with Operations.context(MigrationContext.configure(conn)):
            conn.execute(sa.schema.CreateSchema(schema))
            roles.create(conn)
            old_role, second_role, active_role = uuid4(), uuid4(), uuid4()
            code = "qa_auditor"
            conn.execute(roles.insert().values(id=old_role, code=code, is_deleted=True))

            migration.module.upgrade()
            migration.module.downgrade()
            assert (
                sa.inspect(conn).get_unique_constraints("roles", schema=schema)[0][
                    "name"
                ]
                == OLD_CONSTRAINT
            )
            migration.module.upgrade()

            conn.execute(
                roles.insert().values(id=second_role, code=code, is_deleted=False)
            )
            with pytest.raises(sa.exc.IntegrityError), conn.begin_nested():
                conn.execute(
                    roles.insert().values(id=active_role, code=code, is_deleted=False)
                )
            conn.execute(
                roles.update().where(roles.c.id == second_role).values(is_deleted=True)
            )
            conn.execute(
                roles.insert().values(id=active_role, code=code, is_deleted=False)
            )

            with pytest.raises(sa.exc.IntegrityError), conn.begin_nested():
                migration.module.downgrade()
            indexes = sa.inspect(conn).get_indexes("roles", schema=schema)
            assert [index["name"] for index in indexes] == [ACTIVE_INDEX]
            assert set(conn.execute(sa.select(roles.c.id, roles.c.is_deleted))) == {
                (old_role, True),
                (second_role, True),
                (active_role, False),
            }

    await connection.run_sync(verify)
