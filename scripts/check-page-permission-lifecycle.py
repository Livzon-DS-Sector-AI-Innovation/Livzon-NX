"""Validate the immutable page/action ledger and compare with a Git base ref."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dazah-backend"))

from app.platform.identity.page_lifecycle import (  # noqa: E402
    LEDGER_PATH,
    ledger_history_errors,
    lifecycle_catalog_errors,
    load_ledger,
)
from app.platform.identity.page_policy import PAGE_DEFINITIONS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    ci_base = os.environ.get("CI_BASE_SHA", "")
    parser.add_argument(
        "--base",
        default=ci_base if ci_base and set(ci_base) != {"0"} else None,
        help="Target Git ref; no fetch or Git writes",
    )
    args = parser.parse_args()
    ledger = load_ledger()
    errors = lifecycle_catalog_errors(PAGE_DEFINITIONS, ledger)
    if args.base:
        path = LEDGER_PATH.relative_to(ROOT).as_posix()
        # A missing ledger at a valid base is allowed only on its first addition.
        subprocess.run(
            ["git", "rev-parse", "--verify", args.base],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        names = subprocess.check_output(
            ["git", "ls-tree", "--name-only", args.base, "--", path],
            cwd=ROOT,
            text=True,
        )
        if names.strip():
            previous = json.loads(
                subprocess.check_output(
                    ["git", "show", f"{args.base}:{path}"],
                    cwd=ROOT,
                    text=True,
                    encoding="utf-8",
                )
            )
            errors.extend(ledger_history_errors(previous, ledger))
    for error in errors:
        print(error)
    if errors:
        return 1
    print(f"Page permission lifecycle passed: {len(PAGE_DEFINITIONS)} active pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
