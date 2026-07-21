"""Run quality-module tests against an isolated PostgreSQL database."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings

_SAFE_DATABASE_NAME_MARKERS = ("test", "testing", "pytest")


def _build_test_database_url(database_name: str) -> str:
    normalized_name = database_name.lower()
    if not any(marker in normalized_name for marker in _SAFE_DATABASE_NAME_MARKERS):
        raise ValueError(
            "Test database name must contain 'test', 'testing', or 'pytest'."
        )

    parsed = urlsplit(get_settings().DATABASE_URL)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{database_name}",
            parsed.query,
            parsed.fragment,
        )
    )


def _run(command: list[str], *, env: dict[str, str]) -> None:
    result = subprocess.run(command, env=env, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run quality tests without using the development database."
    )
    parser.add_argument(
        "--database-name",
        default="dazah_test",
        help="Dedicated PostgreSQL database name (default: dazah_test).",
    )
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Do not run Alembic upgrade before pytest.",
    )
    args = parser.parse_args()

    try:
        test_database_url = _build_test_database_url(args.database_name)
    except ValueError as error:
        parser.error(str(error))
    test_env = os.environ.copy()
    test_env["DATABASE_URL"] = test_database_url
    test_env["TEST_DATABASE_URL"] = test_database_url

    print(f"Using isolated test database: {args.database_name}")
    if not args.skip_migrate:
        _run(["uv", "run", "alembic", "upgrade", "head"], env=test_env)
    _run(["uv", "run", "pytest", "tests/modules/quality", "-q"], env=test_env)


if __name__ == "__main__":
    main()
