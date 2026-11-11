#!/usr/bin/env python3
"""Bound dependency HTTP requests, check CI prerequisites, and time phases."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = (
    "environment",
    "dependencies",
    "quality",
    "migration",
    "contract",
    "tests",
    "coverage",
)
# uv retries individual HTTP requests, never a failed pytest/migration command.
HTTP_POLICY = {
    "UV_HTTP_CONNECT_TIMEOUT": "10",
    "UV_HTTP_TIMEOUT": "60",
    "UV_HTTP_RETRIES": "3",
    "UV_CONCURRENT_DOWNLOADS": "8",
}


def phase_file() -> Path:
    return Path(
        os.getenv(
            "CI_PHASE_FILE",
            str(
                Path(os.getenv("RUNNER_TEMP", tempfile.gettempdir()))
                / "ci-phases.jsonl"
            ),
        )
    )


def run_phase(
    name: str,
    category: str,
    command: list[str],
    *,
    cwd: Path | None = None,
    install: bool = False,
) -> int:
    started = time.monotonic()
    failure = None
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env={**os.environ, **(HTTP_POLICY if install else {})},
            timeout=600 if install else None,
            check=False,
        )
        code = result.returncode if result.returncode >= 0 else 128 - result.returncode
        if code:
            failure = category
    except subprocess.TimeoutExpired:
        code, failure = 124, "dependency-timeout"
    except OSError:
        code, failure = 127, "environment"
    record = {
        "phase": name,
        "category": category,
        "duration_seconds": round(time.monotonic() - started, 3),
        "exit_code": code,
        "failure_category": failure,
    }
    try:
        with phase_file().open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
    except OSError:
        print(
            "::warning::CI phase statistics unavailable; command result is unchanged."
        )
    print(
        f"CI phase {name}: exit={code}, duration={record['duration_seconds']}s",
        flush=True,
    )
    return code


def install_project(project: str) -> int:
    directory = ROOT / ("Hermes-Lite" if project == "hermes" else "dazah-backend")
    command = ["uv", "sync", "--frozen"]
    if project == "coverage":
        command += ["--only-group", "ci-coverage"]
    else:
        command += ["--extra", "dev"]
    if project == "backend":
        command += ["--group", "dev"]
    return run_phase(
        f"{project}-install", "dependencies", command, cwd=directory, install=True
    )


def preflight(kind: str) -> None:
    if kind == "tools":
        release = dict(
            line.split("=", 1)
            for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        if (
            platform.system() != "Linux"
            or release.get("ID", "").strip('"') != "ubuntu"
            or release.get("VERSION_ID", "").strip('"') != "24.04"
        ):
            raise ValueError("CI requires Ubuntu 24.04")
        expected_python = os.environ["PYTHON_VERSION"]
        if not platform.python_version().startswith(expected_python + "."):
            raise ValueError("Unexpected CI Python version")
        installed_uv = subprocess.check_output(["uv", "--version"], text=True).split()[
            1
        ]
        if installed_uv != os.environ["UV_VERSION"]:
            raise ValueError("Unexpected CI uv version")
        print(
            f"CI toolchain: Ubuntu 24.04, Python {platform.python_version()}, uv {installed_uv}"
        )
    else:
        from PIL import ImageFont

        for tool in ("psql", "pg_isready"):
            if not shutil.which(tool):
                raise ValueError(f"Missing CI prerequisite: {tool}")
        font = ImageFont.truetype(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 24
        )
        if not font.getmask("设备报修").getbbox():
            raise ValueError("CI CJK font cannot render Chinese")
        print("CI backend prerequisites: PostgreSQL client and CJK rendering ready")


def read_phases(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        duration = item["duration_seconds"]
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]*", item["phase"])
            or item["category"] not in CATEGORIES
            or type(duration) not in (int, float)
            or not math.isfinite(duration)
            or duration < 0
            or type(item["exit_code"]) is not int
            or item.get("failure_category")
            not in (*CATEGORIES, "dependency-timeout", None)
        ):
            raise ValueError("Invalid CI phase observation")
        # Only export known fields, never command lines or environment values.
        records.append(
            {
                key: item.get(key)
                for key in (
                    "phase",
                    "category",
                    "duration_seconds",
                    "exit_code",
                    "failure_category",
                )
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("project", choices=("backend", "hermes", "coverage"))
    check = subparsers.add_parser("preflight")
    check.add_argument("kind", choices=("tools", "backend"))
    subparsers.add_parser("summarize")
    run = subparsers.add_parser("run")
    run.add_argument("--phase", required=True)
    run.add_argument("--category", choices=CATEGORIES, required=True)
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "install":
        return install_project(args.project)
    if args.action == "preflight":
        try:
            preflight(args.kind)
        except (OSError, ValueError, KeyError, ImportError, subprocess.SubprocessError):
            print(
                "CI environment preflight failed: check the declared tools, font and client prerequisites.",
                file=sys.stderr,
            )
            return 1
        return 0
    if args.action == "summarize":
        records = read_phases(phase_file())
        if output := os.getenv("GITHUB_OUTPUT"):
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(
                    "phases=" + json.dumps(records, separators=(",", ":")) + "\n"
                )
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not re.fullmatch(r"[a-z][a-z0-9-]*", args.phase):
        parser.error("A phase name and command are required")
    return run_phase(args.phase, args.category, command)


if __name__ == "__main__":
    raise SystemExit(main())
