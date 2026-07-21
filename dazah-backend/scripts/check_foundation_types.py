"""Run the strict type gate for shared and core backend foundations."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Check foundation packages without reporting unrelated import errors."""
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--follow-imports=silent",
        "app/shared",
        "app/core",
    ]
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
