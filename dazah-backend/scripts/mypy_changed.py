"""Check changed backend runtime files and their imports without hiding errors."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
SOURCE_ROOT = "dazah-backend/app/"


def git_output(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_DIR,
        check=True,
        capture_output=True,
    ).stdout


def commit_id(ref: str) -> str:
    return (
        git_output("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
        .decode()
        .strip()
    )


def parse_paths(output: bytes) -> list[str]:
    return [os.fsdecode(path) for path in output.split(b"\0") if path]


def changed_paths(base: str | None, head: str | None, *, ci: bool) -> list[str]:
    if base is None and head is None and not ci:
        return parse_paths(
            git_output(
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                "-z",
                "HEAD",
                "--",
                SOURCE_ROOT,
            )
        ) + parse_paths(
            git_output(
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                SOURCE_ROOT,
            )
        )
    resolved_head = commit_id(head or "HEAD")
    if base and set(base) == {"0"}:
        # The first push has no before commit: every runtime file is new.
        return parse_paths(
            git_output(
                "ls-tree",
                "-r",
                "--name-only",
                "-z",
                resolved_head,
                "--",
                SOURCE_ROOT,
            )
        )
    if base:
        resolved_base = commit_id(base)
    else:
        # Manual dispatch: inspect the branch against main. If it is already
        # main, inspect its latest commit instead of silently checking nothing.
        main = commit_id("origin/main")
        resolved_base = git_output("merge-base", main, resolved_head).decode().strip()
        if resolved_base == resolved_head:
            resolved_base = commit_id(f"{resolved_head}^")
    return parse_paths(
        git_output(
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            "-z",
            resolved_base,
            resolved_head,
            "--",
            SOURCE_ROOT,
        )
    )


def select_targets(paths: Sequence[str], *, explicit: bool = False) -> list[str]:
    targets: set[str] = set()
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            root = (
                REPOSITORY_DIR if path.parts[:1] == ("dazah-backend",) else BACKEND_DIR
            )
            path = root / path
        path = path.resolve()
        if not path.is_relative_to(BACKEND_DIR / "app") or path.suffix != ".py":
            if explicit:
                raise ValueError(f"Mypy entry must be a backend app Python file: {raw}")
            continue
        if not path.is_file():
            raise ValueError(f"Selected Mypy entry is missing: {raw}")
        targets.add(path.relative_to(BACKEND_DIR).as_posix())
    return sorted(targets)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Explicit app files for local checks")
    parser.add_argument("--base", default=os.environ.get("CI_BASE_SHA") or None)
    parser.add_argument("--head", default=os.environ.get("CI_HEAD_SHA") or None)
    args = parser.parse_args(argv)
    try:
        targets = (
            select_targets(args.files, explicit=True)
            if args.files
            else select_targets(
                changed_paths(args.base, args.head, ci=os.environ.get("CI") == "true")
            )
        )
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(
            f"Cannot determine changed Mypy entries; gate failed: {exc}",
            file=sys.stderr,
        )
        return 2
    if not targets:
        print("No changed backend app Python files; incremental Mypy check skipped.")
        return 0
    print(
        f"Mypy changed runtime files and dependency chains ({len(targets)} entries):",
        flush=True,
    )
    for target in targets:
        print(f"  {target}", flush=True)
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--follow-imports=normal", "--", *targets],
        cwd=BACKEND_DIR,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
