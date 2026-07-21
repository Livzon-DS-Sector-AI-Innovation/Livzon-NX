"""Run the strict type gate for the backend identity platform."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Check identity without reporting unrelated imported-module debt."""
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--follow-imports=silent",
        "app/platform/identity",
    ]
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
