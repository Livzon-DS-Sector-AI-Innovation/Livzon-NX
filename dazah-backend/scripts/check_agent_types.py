"""Run strict mypy checks for the Livzon Agent boundary.

Imported modules remain typed, but their existing diagnostics are suppressed so
unrelated application debt cannot hide regressions in ``app.modules.agent``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--follow-imports=silent",
            "app/modules/agent",
        ],
        cwd=project_root,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
