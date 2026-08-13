#!/usr/bin/env python3
"""Resolve CI change scopes from a Git revision range."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import PurePosixPath

OUTPUT_NAMES = (
    "frontend_changed",
    "backend_changed",
    "hermes_changed",
    "docker_changed",
    "shared_changed",
    "docs_only",
)

SHARED_CONTRACTS = {
    "dazah-backend/openapi.json",
    "dazah-frontend/src/types/generated/schema.ts",
}
SHARED_PREFIXES = (".ci/", ".github/", "scripts/")


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
    ).stdout


def revision_exists(revision: str | None) -> bool:
    if not revision or set(revision) == {"0"}:
        return False
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def resolve_head(head: str | None) -> str:
    return head if revision_exists(head) else "HEAD"


def collect_changed_paths(base: str | None, head: str | None) -> set[str]:
    """Return changed paths, failing safe to the complete tree for an unknown base."""
    resolved_head = resolve_head(head)
    if revision_exists(base):
        output = _git(
            "-c",
            "core.quotePath=false",
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACMRD",
            base or "",
            resolved_head,
        )
    elif base is None and revision_exists(f"{resolved_head}^"):
        output = _git(
            "-c",
            "core.quotePath=false",
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACMRD",
            f"{resolved_head}^",
            resolved_head,
        )
    else:
        # A first push or an explicitly unavailable/all-zero before SHA must not
        # skip checks, even when the pushed branch contains several commits.
        output = _git("ls-tree", "-r", "--name-only", "-z", resolved_head)
    return {
        item.decode("utf-8").replace("\\", "/")
        for item in output.split(b"\0")
        if item
    }


def is_documentation(path: str) -> bool:
    normalized = path.lower()
    return normalized.startswith("docs/") or normalized.endswith(
        (".md", ".mdx", ".rst")
    )


def is_docker_path(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return name.startswith("dockerfile") or name in {
        "compose.yml",
        "compose.yaml",
        "docker-compose.yml",
        "docker-compose.yaml",
    }


def classify_paths(paths: set[str]) -> dict[str, bool]:
    code_paths = {path for path in paths if not is_documentation(path)}
    shared = any(
        "/" not in path
        or path in SHARED_CONTRACTS
        or path.startswith(SHARED_PREFIXES)
        for path in code_paths
    )
    return {
        "frontend_changed": any(
            path.startswith("dazah-frontend/") for path in code_paths
        ),
        "backend_changed": any(
            path.startswith("dazah-backend/") for path in code_paths
        ),
        "hermes_changed": any(
            path.startswith("Hermes-Lite/") for path in code_paths
        ),
        "docker_changed": any(is_docker_path(path) for path in code_paths),
        "shared_changed": shared,
        "docs_only": bool(paths) and not code_paths,
    }


def write_outputs(scopes: dict[str, bool], output_file: str | None) -> None:
    if not output_file:
        return
    with open(output_file, "a", encoding="utf-8") as stream:
        for name in OUTPUT_NAMES:
            stream.write(f"{name}={str(scopes[name]).lower()}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.getenv("CI_BASE_SHA"))
    parser.add_argument("--head", default=os.getenv("CI_HEAD_SHA"))
    parser.add_argument("--github-output", default=os.getenv("GITHUB_OUTPUT"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = collect_changed_paths(args.base, args.head)
    scopes = classify_paths(paths)
    write_outputs(scopes, args.github_output)
    print(json.dumps({"paths": sorted(paths), **scopes}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
