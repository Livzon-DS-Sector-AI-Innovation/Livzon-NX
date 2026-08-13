#!/usr/bin/env python3
"""Verify that Claude Code imports every repository AGENTS.md instruction file."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


EXCLUDED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    ".pnpm-store",
    "temp",
    "tmp",
    "venv",
}
IMPORT_LINE = "@AGENTS.md"


def _instruction_files(root: Path, filename: str) -> list[Path]:
    matches: list[Path] = []
    for current, directories, files in os.walk(root, topdown=True):
        current_path = Path(current)
        directories[:] = [
            directory
            for directory in directories
            if directory not in EXCLUDED_DIRECTORIES
        ]
        if filename in files:
            matches.append(current_path / filename)
    return sorted(matches)


def _imports_agents(claude_file: Path) -> bool:
    return IMPORT_LINE in {
        line.strip()
        for line in claude_file.read_text(encoding="utf-8").splitlines()
    }


def validate_bridges(root: Path) -> list[str]:
    """Return validation errors for missing, invalid, or orphaned bridges."""
    root = root.resolve()
    errors: list[str] = []

    for agents_file in _instruction_files(root, "AGENTS.md"):
        claude_file = agents_file.with_name("CLAUDE.md")
        relative_agents = agents_file.relative_to(root).as_posix()
        if not claude_file.is_file():
            errors.append(f"{relative_agents}: missing same-directory CLAUDE.md")
            continue
        if not _imports_agents(claude_file):
            relative_claude = claude_file.relative_to(root).as_posix()
            errors.append(f"{relative_claude}: missing exact import line {IMPORT_LINE}")

    for claude_file in _instruction_files(root, "CLAUDE.md"):
        if not _imports_agents(claude_file):
            continue
        agents_file = claude_file.with_name("AGENTS.md")
        if not agents_file.is_file():
            relative_claude = claude_file.relative_to(root).as_posix()
            errors.append(f"{relative_claude}: imports missing same-directory AGENTS.md")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to validate",
    )
    return parser.parse_args()


def main() -> int:
    errors = validate_bridges(parse_args().root)
    if errors:
        print("Agent instruction bridge validation failed:")
        for error in errors:
            print(f"  {error}")
        return 1

    print("Agent instruction bridges passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
