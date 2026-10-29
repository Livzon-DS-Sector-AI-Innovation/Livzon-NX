"""A service restart must never inherit permission to change a database."""

import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alembic.util import CommandError
from sqlalchemy.engine import make_url

from app.core import dev_migration as guard


@pytest.fixture
def pending(monkeypatch):
    plan = guard.MigrationPlan("db:5432/development", "old", "reviewed", ("reviewed",))
    config = object()
    boundary = Mock()

    @contextmanager
    def database(**kwargs):
        boundary(**kwargs)
        yield config, object()

    monkeypatch.setattr(guard, "_database", database)
    monkeypatch.setattr(guard, "_read_plan", Mock(return_value=plan))
    upgrade = Mock()
    monkeypatch.setattr(guard.command, "upgrade", upgrade)
    return SimpleNamespace(plan=plan, config=config, boundary=boundary, upgrade=upgrade)


@pytest.mark.parametrize(
    "approval", ["", "YES", "MIGRATE " + "x" * 513, "MIGRATE x\x00"]
)
def test_upgrade_without_fresh_stdin_does_not_even_connect(pending, approval):
    with pytest.raises(guard.MigrationGuardError, match="stdin"):
        guard.execute_upgrade(approval)
    pending.boundary.assert_not_called()
    pending.upgrade.assert_not_called()


@pytest.mark.parametrize("action", [[], ["check"], ["plan"], ["serve"]])
def test_default_check_plan_and_startup_cannot_upgrade(pending, action, capsys):
    assert guard.main(action, stdin=io.StringIO(pending.plan.confirmation)) == (
        0 if action == ["plan"] else 2
    )
    pending.upgrade.assert_not_called()
    if action == ["plan"]:
        assert (
            json.loads(capsys.readouterr().out)["confirmation"]
            == pending.plan.confirmation
        )


def test_only_exact_approval_applies_the_reviewed_revision(pending):
    assert guard.execute_upgrade(pending.plan.confirmation) == pending.plan
    pending.boundary.assert_called_once_with(upgrade_lock=True)
    pending.upgrade.assert_called_once_with(pending.config, "reviewed")


@pytest.mark.parametrize("change", ["database", "current", "target", "extra"])
def test_stale_or_different_target_confirmation_is_rejected(pending, change):
    approval = pending.plan.confirmation
    approval = {
        "database": approval.replace("development", "other"),
        "current": approval.replace("old", "older"),
        "target": approval.replace("reviewed", "newer"),
        "extra": approval + " extra",
    }[change]
    with pytest.raises(guard.MigrationGuardError, match="does not match"):
        guard.execute_upgrade(approval)
    pending.upgrade.assert_not_called()


def test_current_database_never_reapplies_an_upgrade(pending, monkeypatch):
    plan = guard.MigrationPlan("db:5432/development", "reviewed", "reviewed", ())
    guard._read_plan.return_value = plan
    assert guard.execute_upgrade(plan.confirmation) == plan
    pending.upgrade.assert_not_called()
    execv = Mock()
    monkeypatch.setattr(guard.os, "execv", execv)
    assert guard.main(["serve"]) == 0
    assert execv.call_args.args[1][1:4] == ["-m", "uvicorn", "app.main:app"]


def test_container_restart_with_closed_stdin_cannot_reuse_prior_approval(pending):
    assert (
        guard.main(["upgrade"], stdin=io.StringIO(pending.plan.confirmation + "\n"))
        == 0
    )
    pending.upgrade.reset_mock()
    pending.boundary.reset_mock()
    assert guard.main(["upgrade"], stdin=io.StringIO("")) == 2
    pending.upgrade.assert_not_called()
    pending.boundary.assert_not_called()


def test_persisted_environment_cannot_approve_a_restart(pending, monkeypatch):
    monkeypatch.setenv("MIGRATION_APPROVAL", pending.plan.confirmation)
    monkeypatch.setenv("ALLOW_MIGRATIONS", "true")
    assert guard.main(["upgrade"], stdin=io.StringIO("")) == 2
    pending.upgrade.assert_not_called()


def test_upstream_errors_never_print_connection_secrets(pending, monkeypatch, capsys):
    monkeypatch.setattr(
        guard, "read_plan", Mock(side_effect=RuntimeError("synthetic-secret"))
    )
    assert guard.main(["plan"]) == 1
    assert "synthetic-secret" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "environment,url",
    [
        ("production", "postgresql+asyncpg://u:synthetic-secret@db/dev"),
        ("development", "postgresql+asyncpg://u:synthetic-secret@remote.example/dev"),
        ("development", "sqlite:///dev.db"),
        ("development", "postgresql+asyncpg://u:synthetic-secret@db/"),
        ("development", "postgresql+asyncpg://u:synthetic-secret@db/dev?host=remote.invalid"),
        ("development", "postgresql+asyncpg://u:synthetic-secret@db/dev?database=shared"),
        ("development", "postgresql+asyncpg://u:synthetic-secret@db/dev?unix_sock=/tmp/pg"),
    ],
)
def test_nonlocal_or_production_configuration_fails_before_connect(
    monkeypatch, environment, url
):
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(APP_ENV=environment, DATABASE_URL=url),
    )
    create = Mock()
    monkeypatch.setattr(guard, "create_engine", create)
    with pytest.raises(guard.MigrationGuardError):
        guard._configuration()
    create.assert_not_called()


def test_configuration_preserves_escaped_credentials_without_printing_them(monkeypatch):
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(
            APP_ENV="development",
            DATABASE_URL="postgresql+asyncpg://u:synthetic%40password@db/dev",
        ),
    )
    create = Mock()
    monkeypatch.setattr(guard, "create_engine", create)
    guard._configuration()
    url = create.call_args.args[0]
    assert url.password == "synthetic@password"
    assert url.drivername == "postgresql+pg8000"


@pytest.mark.parametrize("lock_available", [True, False])
def test_database_boundary_is_read_only_and_releases_locks(monkeypatch, lock_available):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    transaction = Mock(__enter__=Mock(), __exit__=Mock(return_value=False))
    connection.begin.return_value = transaction
    connection.scalar.return_value = lock_available
    engine = Mock()
    engine.connect.return_value = connection
    monkeypatch.setattr(guard, "_configuration", lambda: (object(), engine))
    if lock_available:
        with guard._database(upgrade_lock=True):
            pass
    else:
        with pytest.raises(guard.MigrationGuardError, match="Another"):
            with guard._database(upgrade_lock=True):
                pytest.fail("Concurrent migration must not enter the database boundary")
    connection.exec_driver_sql.assert_called_once_with("SET TRANSACTION READ ONLY")
    assert (
        str(connection.scalar.call_args.args[0]) == "SELECT pg_try_advisory_lock(:key)"
    )
    engine.dispose.assert_called_once()


@pytest.mark.parametrize(
    "db_heads,code_heads,unknown",
    [
        (("a", "b"), ["target"], False),
        (("old",), ["a", "b"], False),
        (("unknown",), ["target"], True),
    ],
)
def test_invalid_migration_chain_never_produces_an_approved_plan(
    monkeypatch, db_heads, code_heads, unknown
):
    script = SimpleNamespace(get_heads=lambda: code_heads, iterate_revisions=Mock())
    if unknown:
        script.iterate_revisions.side_effect = CommandError("unknown revision")
    monkeypatch.setattr(guard.ScriptDirectory, "from_config", lambda _: script)
    monkeypatch.setattr(
        guard.MigrationContext,
        "configure",
        lambda _: SimpleNamespace(get_current_heads=lambda: db_heads),
    )
    connection = SimpleNamespace(
        scalar=lambda _: "dev",
        engine=SimpleNamespace(url=make_url("postgresql://db/dev")),
    )
    with pytest.raises(guard.MigrationGuardError):
        guard._read_plan(object(), connection)


def test_plan_binds_target_database_and_lists_pending_revisions(monkeypatch):
    script = SimpleNamespace(
        get_heads=lambda: ["target"],
        iterate_revisions=lambda *_: [
            SimpleNamespace(revision="target"),
            SimpleNamespace(revision="middle"),
        ],
    )
    monkeypatch.setattr(guard.ScriptDirectory, "from_config", lambda _: script)
    monkeypatch.setattr(
        guard.MigrationContext,
        "configure",
        lambda _: SimpleNamespace(get_current_heads=lambda: ("old",)),
    )
    connection = SimpleNamespace(
        scalar=lambda _: "dev",
        engine=SimpleNamespace(url=make_url("postgresql://db/dev")),
    )
    plan = guard._read_plan(object(), connection)
    assert plan.confirmation == "MIGRATE db:5432/dev old target"
    assert plan.pending_revisions == ("middle", "target")


def test_unversioned_database_plan_is_read_only(monkeypatch):
    script = SimpleNamespace(
        get_heads=lambda: ["target"],
        iterate_revisions=Mock(return_value=[SimpleNamespace(revision="target")]),
    )
    monkeypatch.setattr(guard.ScriptDirectory, "from_config", lambda _: script)
    monkeypatch.setattr(
        guard.MigrationContext,
        "configure",
        lambda _: SimpleNamespace(get_current_heads=lambda: ()),
    )
    connection = SimpleNamespace(
        scalar=lambda _: "dev",
        engine=SimpleNamespace(url=make_url("postgresql://db/dev")),
    )
    plan = guard._read_plan(object(), connection)
    assert plan.current_revision == "base"
    script.iterate_revisions.assert_called_once_with("target", "base")


def test_actual_database_mismatch_is_refused(monkeypatch):
    script = SimpleNamespace(get_heads=lambda: ["target"])
    monkeypatch.setattr(guard.ScriptDirectory, "from_config", lambda _: script)
    monkeypatch.setattr(
        guard.MigrationContext,
        "configure",
        lambda _: SimpleNamespace(get_current_heads=lambda: ("old",)),
    )
    connection = SimpleNamespace(
        scalar=lambda _: "unexpected",
        engine=SimpleNamespace(url=make_url("postgresql://db/dev")),
    )
    with pytest.raises(guard.MigrationGuardError, match="connected database"):
        guard._read_plan(object(), connection)
