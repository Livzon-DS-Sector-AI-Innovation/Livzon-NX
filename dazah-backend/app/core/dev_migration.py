"""Read-only development startup checks and per-invocation migration approval.

Approval is accepted only on stdin, never in an environment variable or a
persisted container command. A restarted container receives EOF and cannot
repeat a previously authorized upgrade. Production deployment uses its own flow.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import TextIO

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings

_UPGRADE_LOCK = 82467029173285
_UVICORN_ARGS = [
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--reload",
    "--reload-dir",
    "/app/app",
]


class MigrationGuardError(RuntimeError):
    """A safe, actionable refusal that contains no connection credentials."""


@dataclass(frozen=True)
class MigrationPlan:
    database: str
    current_revision: str
    target_revision: str
    pending_revisions: tuple[str, ...]

    @property
    def confirmation(self) -> str:
        return f"MIGRATE {self.database} {self.current_revision} {self.target_revision}"


def _configuration() -> tuple[Config, Engine]:
    settings = get_settings()
    if settings.APP_ENV not in {"development", "test"}:
        raise MigrationGuardError("This command is restricted to local development.")
    url = make_url(settings.DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"db", "localhost", "127.0.0.1", "::1"}
        or not url.database
        # Driver query options can override host/database after URL validation.
        # Require one unambiguous local target for both the plan and Alembic.
        or url.query
        or any(char.isspace() or ord(char) < 32 for char in url.database)
    ):
        raise MigrationGuardError("An explicit local PostgreSQL target is required.")
    config = Config("alembic.ini")
    engine = create_engine(
        url.set(drivername="postgresql+pg8000"),
        poolclass=NullPool,
        connect_args={"timeout": 10},
    )
    return config, engine


@contextmanager
def _database(*, upgrade_lock: bool = False) -> Iterator[tuple[Config, Connection]]:
    config, engine = _configuration()
    try:
        with engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            if upgrade_lock and not connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _UPGRADE_LOCK}
            ):
                raise MigrationGuardError("Another development migration is running.")
            yield config, connection
    finally:
        # NullPool closes the socket, releasing any session advisory lock.
        engine.dispose()


def _read_plan(config: Config, connection: Connection) -> MigrationPlan:
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    current = MigrationContext.configure(connection).get_current_heads()
    if len(heads) != 1 or len(current) > 1:
        raise MigrationGuardError("Exactly one migration head is required.")
    database = connection.scalar(text("SELECT current_database()"))
    url = connection.engine.url
    if database != url.database:
        raise MigrationGuardError("The connected database does not match the plan.")
    revision = current[0] if current else "base"
    try:
        pending = tuple(
            item.revision
            for item in script.iterate_revisions(heads[0], revision, implicit_base=True)
        )
    except CommandError as exc:
        raise MigrationGuardError(
            "Database revision is outside the current migration chain."
        ) from exc
    return MigrationPlan(
        database=f"{url.host}:{url.port or 5432}/{url.database}",
        current_revision=revision,
        target_revision=heads[0],
        pending_revisions=tuple(reversed(pending)),
    )


def read_plan() -> MigrationPlan:
    with _database() as (config, connection):
        return _read_plan(config, connection)


def check_current() -> MigrationPlan:
    plan = read_plan()
    if plan.pending_revisions:
        raise MigrationGuardError(
            "Database migration is pending. Review and run "
            "scripts/dev.ps1 -Migrate before starting the backend."
        )
    return plan


def execute_upgrade(approval: str) -> MigrationPlan:
    if (
        not approval.startswith("MIGRATE ")
        or len(approval) > 512
        or any(char in approval for char in "\r\n\x00")
    ):
        raise MigrationGuardError("Fresh migration confirmation on stdin is required.")
    with _database(upgrade_lock=True) as (config, connection):
        plan = _read_plan(config, connection)
        if approval != plan.confirmation:
            raise MigrationGuardError(
                "Confirmation does not match the current database and revisions."
            )
        if plan.pending_revisions:
            # Pin the reviewed revision: never pick up a newly added head here.
            command.upgrade(config, plan.target_revision)
        return plan


def main(argv: list[str] | None = None, *, stdin: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        default="check",
        choices=("check", "plan", "upgrade", "serve"),
    )
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            plan = read_plan()
            print(json.dumps({**asdict(plan), "confirmation": plan.confirmation}))
        elif args.action == "upgrade":
            approval = (stdin if stdin is not None else sys.stdin).readline(514)
            plan = execute_upgrade(approval.rstrip("\r\n"))
            print(f"Development database is at revision {plan.target_revision}.")
        else:
            plan = check_current()
            if args.action == "serve":
                os.execv(sys.executable, [sys.executable, *_UVICORN_ARGS])
            else:
                print(f"Database revision verified: {plan.target_revision}.")
    except MigrationGuardError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        # Drivers/configuration errors may contain URLs and credentials.
        print(
            f"Development migration check failed ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
