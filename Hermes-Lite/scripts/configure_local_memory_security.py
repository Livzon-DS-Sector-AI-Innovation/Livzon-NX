#!/usr/bin/env python3
"""Configure persistent local-only Hermes user-memory security settings."""

from __future__ import annotations

import argparse
import base64
import os
import tempfile
from pathlib import Path


def _replace_env_value(lines: list[str], name: str, value: str) -> list[str]:
    prefix = f"{name}="
    replacement = f"{prefix}{value}\n"
    replaced = False
    result: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            if not replaced:
                result.append(replacement)
                replaced = True
            continue
        result.append(line)
    if not replaced:
        if result and not result[-1].endswith("\n"):
            result[-1] += "\n"
        result.append(replacement)
    return result


def configure(env_path: Path, *, require_policy: bool) -> bool:
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = existing.splitlines(keepends=True)
    current_key = next(
        (
            line.split("=", 1)[1].strip()
            for line in lines
            if line.startswith("HERMES_USER_MEMORY_KEYS=")
        ),
        "",
    )
    generated = not current_key
    key = current_key or base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    lines = _replace_env_value(lines, "HERMES_USER_MEMORY_KEYS", key)
    lines = _replace_env_value(
        lines,
        "HERMES_USER_MEMORY_REQUIRE_POLICY",
        "true" if require_policy else "false",
    )

    env_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{env_path.name}.", dir=env_path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, env_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".env",
    )
    parser.add_argument(
        "--require-policy",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()
    generated = configure(args.env_file.resolve(), require_policy=args.require_policy)
    action = "generated" if generated else "preserved"
    print(f"Memory key {action}; trusted-policy enforcement configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
