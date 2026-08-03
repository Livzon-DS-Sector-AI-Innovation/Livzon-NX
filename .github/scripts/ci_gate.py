#!/usr/bin/env python3
"""Evaluate the stable GitHub CI gate and emit a step summary."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    job: str
    expected: bool
    result: str
    ok: bool
    reason: str


def _enabled(scopes: dict[str, bool], *names: str) -> bool:
    return any(scopes.get(name, False) for name in names)


def expected_jobs(scopes: dict[str, bool]) -> dict[str, bool]:
    frontend = _enabled(scopes, "frontend_changed", "shared_changed")
    backend = _enabled(scopes, "backend_changed", "shared_changed")
    hermes = _enabled(scopes, "hermes_changed", "shared_changed")
    contract = _enabled(
        scopes,
        "backend_changed",
        "hermes_changed",
        "shared_changed",
    )
    return {
        "change-scope": True,
        "source-security": True,
        "frontend-quality": frontend,
        "frontend-e2e": frontend,
        "backend-quality": backend,
        "backend-integration": backend,
        "backend-image-verify": backend,
        "hermes-quality": hermes,
        "hermes-contract": contract,
    }


def evaluate(
    scopes: dict[str, bool],
    results: dict[str, str],
) -> list[Check]:
    checks: list[Check] = []
    for job, expected in expected_jobs(scopes).items():
        result = results.get(job, "")
        if result in {"failure", "cancelled"}:
            ok = False
            reason = f"blocking job ended as {result}"
        elif expected and result != "success":
            ok = False
            reason = f"expected success, got {result or 'missing'}"
        elif not expected and result not in {"success", "skipped"}:
            ok = False
            reason = f"unexpected result {result or 'missing'}"
        elif expected:
            ok = True
            reason = "required job succeeded"
        elif result == "skipped":
            ok = True
            reason = "scope did not require this job"
        else:
            ok = True
            reason = "extra successful validation"
        checks.append(Check(job, expected, result, ok, reason))
    return checks


def render_summary(checks: list[Check], scopes: dict[str, bool]) -> str:
    lines = [
        "## CI Gate",
        "",
        "### Change scope",
        "",
        "```json",
        json.dumps(scopes, sort_keys=True),
        "```",
        "",
        "| Job | Expected | Result | Gate | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in checks:
        lines.append(
            f"| `{check.job}` | {'yes' if check.expected else 'no'} | "
            f"`{check.result or 'missing'}` | {'pass' if check.ok else 'fail'} | "
            f"{check.reason} |"
        )
    return "\n".join(lines) + "\n"


def _boolean(name: str) -> bool:
    return os.getenv(name, "false").lower() == "true"


def main() -> int:
    scopes = {
        "frontend_changed": _boolean("FRONTEND_CHANGED"),
        "backend_changed": _boolean("BACKEND_CHANGED"),
        "hermes_changed": _boolean("HERMES_CHANGED"),
        "docker_changed": _boolean("DOCKER_CHANGED"),
        "shared_changed": _boolean("SHARED_CHANGED"),
        "docs_only": _boolean("DOCS_ONLY"),
    }
    results = {
        job: os.getenv(job.upper().replace("-", "_") + "_RESULT", "")
        for job in expected_jobs(scopes)
    }
    checks = evaluate(scopes, results)
    summary = render_summary(checks, scopes)
    print(summary)
    if summary_path := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a", encoding="utf-8") as stream:
            stream.write(summary)
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
