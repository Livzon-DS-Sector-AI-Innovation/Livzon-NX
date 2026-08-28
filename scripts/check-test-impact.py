#!/usr/bin/env python3
"""Require production changes to include tests selected by a repository policy."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Requirement:
    rule_id: str
    description: str
    captures: tuple[tuple[str, str], ...]
    test_patterns: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".ci/test-impact-policy.toml"),
    )
    parser.add_argument("--base")
    parser.add_argument("--head")
    return parser.parse_args()


def revision_exists(revision: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def resolve_revisions(base: str | None, head: str | None) -> tuple[str, str]:
    resolved_head = (
        head or os.environ.get("CI_HEAD_SHA") or os.environ.get("GITHUB_SHA") or "HEAD"
    )
    if not revision_exists(resolved_head):
        resolved_head = "HEAD"

    resolved_base = (
        base
        or os.environ.get("CI_BASE_SHA")
        or os.environ.get("GITHUB_BASE_SHA")
        or os.environ.get("GITHUB_EVENT_BEFORE")
        or "HEAD^"
    )
    if revision_exists(resolved_base):
        return resolved_base, resolved_head
    if revision_exists(f"{resolved_head}^"):
        return f"{resolved_head}^", resolved_head

    root = subprocess.run(
        ["git", "rev-list", "--max-parents=0", resolved_head],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()[0]
    return root, resolved_head


def changed_paths(base: str, head: str, diff_filter: str) -> set[str]:
    completed = subprocess.run(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "diff",
            "--name-only",
            "-z",
            f"--diff-filter={diff_filter}",
            base,
            head,
        ],
        check=True,
        capture_output=True,
    )
    return {
        item.decode("utf-8").replace("\\", "/")
        for item in completed.stdout.split(b"\0")
        if item
    }


def load_policy(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        policy = tomllib.load(stream)
    if policy.get("version") != 1:
        raise ValueError("test impact policy version must be 1")
    return policy


def render_pattern(pattern: str, captures: dict[str, str]) -> str:
    for name, value in captures.items():
        pattern = pattern.replace("{" + name + "}", re.escape(value))
    return pattern


def evaluate(
    policy: dict[str, Any],
    changed_sources: set[str],
    changed_tests: set[str],
) -> tuple[list[tuple[Requirement, list[str]]], list[str]]:
    roots = tuple(policy["production_roots"])
    includes = [re.compile(pattern) for pattern in policy["production_include"]]
    ignores = [re.compile(pattern) for pattern in policy.get("ignore", [])]
    rules = [(rule, re.compile(rule["source"])) for rule in policy["rules"]]
    requirements: dict[Requirement, list[str]] = {}
    unmatched: list[str] = []

    production_changes = sorted(
        path
        for path in changed_sources
        if path.startswith(roots)
        and any(pattern.search(path) for pattern in includes)
        and not any(pattern.search(path) for pattern in ignores)
    )
    for path in production_changes:
        matched = False
        for rule, source_pattern in rules:
            match = source_pattern.search(path)
            if not match:
                continue
            matched = True
            captures = match.groupdict()
            requirement = Requirement(
                rule_id=rule["id"],
                description=rule["description"],
                captures=tuple(sorted(captures.items())),
                test_patterns=tuple(
                    render_pattern(pattern, captures) for pattern in rule["tests"]
                ),
            )
            requirements.setdefault(requirement, []).append(path)
        if not matched:
            unmatched.append(path)

    violations = []
    for requirement, sources in requirements.items():
        patterns = [re.compile(pattern) for pattern in requirement.test_patterns]
        if not any(
            pattern.search(test_path)
            for pattern in patterns
            for test_path in changed_tests
        ):
            violations.append((requirement, sources))
    return violations, unmatched


def main() -> int:
    args = parse_args()
    policy = load_policy(args.policy)
    base, head = resolve_revisions(args.base, args.head)
    sources = changed_paths(base, head, "ACMRD")
    tests = changed_paths(base, head, "ACMR")
    violations, unmatched = evaluate(policy, sources, tests)

    if not violations and not unmatched:
        print(f"Test impact policy passed for {base}..{head}.")
        return 0

    if unmatched:
        print("Unclassified production changes:", file=sys.stderr)
        for path in unmatched:
            print(f"  {path}", file=sys.stderr)

    for requirement, source_paths in violations:
        captures = ", ".join(f"{name}={value}" for name, value in requirement.captures)
        suffix = f" ({captures})" if captures else ""
        print(
            f"Missing tests for {requirement.rule_id}{suffix}: "
            f"{requirement.description}",
            file=sys.stderr,
        )
        for source_path in source_paths:
            print(f"  source: {source_path}", file=sys.stderr)
        print("  expected a changed test matching one of:", file=sys.stderr)
        for pattern in requirement.test_patterns:
            print(f"    {pattern}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
