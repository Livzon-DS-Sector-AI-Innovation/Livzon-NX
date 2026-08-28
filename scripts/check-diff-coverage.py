#!/usr/bin/env python3
"""Fail when executable lines changed by a pull request are insufficiently tested."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-file", type=Path, required=True)
    parser.add_argument("--path-prefix", required=True)
    parser.add_argument("--minimum", type=float, default=80.0)
    parser.add_argument("--base")
    parser.add_argument("--head")
    return parser.parse_args()


def resolve_revision(
    explicit: str | None,
    env_names: tuple[str, ...],
    fallback: str,
) -> str:
    if explicit:
        return explicit
    for name in env_names:
        if value := os.environ.get(name):
            return value
    return fallback


def revision_exists(revision: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def validated_revisions(base: str, head: str) -> tuple[str, str]:
    if not revision_exists(head):
        head = "HEAD"
    if revision_exists(base):
        return base, head
    if revision_exists(f"{head}^"):
        return f"{head}^", head
    root = subprocess.run(
        ["git", "rev-list", "--max-parents=0", head],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()[0]
    return root, head


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def repository_root() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return Path(completed.stdout.strip())


def read_coverage(path: Path) -> dict[str, dict[int, int]]:
    root = ET.parse(path).getroot()
    result: dict[str, dict[int, int]] = {}
    for class_node in root.findall(".//class"):
        filename = normalize_path(class_node.attrib["filename"])
        result[filename] = {
            int(line.attrib["number"]): int(line.attrib.get("hits", "0"))
            for line in class_node.findall("./lines/line")
        }
    return result


def read_changed_lines(
    base: str,
    head: str,
    path_prefix: str,
) -> dict[str, set[int]]:
    prefix = normalize_path(path_prefix).rstrip("/") + "/"
    command = [
        "git",
        "-c",
        "core.quotePath=false",
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--unified=0",
        "--diff-filter=ACMR",
        base,
        head,
        "--",
        prefix,
    ]
    completed = subprocess.run(
        command,
        # ``git diff`` returns 1 when differences exist.  That is the normal
        # input for this checker, so only command errors should abort it.
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=repository_root(),
    )
    if completed.returncode not in (0, 1):
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    changed: dict[str, set[int]] = defaultdict(set)
    current_file: str | None = None
    for raw_line in completed.stdout.splitlines():
        if raw_line.startswith("+++ b/"):
            repository_path = normalize_path(raw_line[6:])
            current_file = (
                repository_path[len(prefix) :]
                if repository_path.startswith(prefix)
                else None
            )
            continue
        match = HUNK_PATTERN.match(raw_line)
        if current_file and match:
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            changed[current_file].update(range(start, start + count))
    return changed


def main() -> int:
    args = parse_args()
    base = resolve_revision(
        args.base,
        ("COVERAGE_BASE_SHA", "CI_BASE_SHA", "GITHUB_BASE_SHA"),
        "HEAD^",
    )
    head = resolve_revision(
        args.head,
        ("COVERAGE_HEAD_SHA", "CI_HEAD_SHA", "GITHUB_SHA"),
        "HEAD",
    )
    base, head = validated_revisions(base, head)
    coverage = read_coverage(args.coverage_file)
    changed = read_changed_lines(base, head, args.path_prefix)

    executable: list[tuple[str, int, int]] = []
    for filename, line_numbers in changed.items():
        file_coverage = coverage.get(filename, {})
        executable.extend(
            (filename, line_number, file_coverage[line_number])
            for line_number in sorted(line_numbers)
            if line_number in file_coverage
        )

    if not executable:
        print(f"No changed executable lines between {base} and {head}.")
        return 0

    covered = sum(hits > 0 for _, _, hits in executable)
    rate = covered / len(executable) * 100
    print(
        f"Changed-line coverage: {rate:.2f}% "
        f"({covered}/{len(executable)}), required {args.minimum:.2f}%."
    )
    if rate + 1e-9 >= args.minimum:
        return 0

    uncovered = [
        f"{filename}:{line}" for filename, line, hits in executable if not hits
    ]
    print("Uncovered changed executable lines:", file=sys.stderr)
    for item in uncovered[:50]:
        print(f"  {item}", file=sys.stderr)
    if len(uncovered) > 50:
        print(f"  ... and {len(uncovered) - 50} more", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
