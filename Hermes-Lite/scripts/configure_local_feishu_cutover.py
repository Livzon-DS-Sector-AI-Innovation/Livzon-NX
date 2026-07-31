"""Configure the local Dazah-to-Hermes Feishu cutover without printing secrets."""

from __future__ import annotations

import secrets
from pathlib import Path

from cryptography.fernet import Fernet


def _read_values(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    values: dict[str, str] = {}
    for line in lines:
        name, separator, value = line.partition("=")
        if separator and name.strip() and not name.lstrip().startswith("#"):
            values[name.strip()] = value.strip()
    return lines, values


def _set_values(path: Path, updates: dict[str, str]) -> None:
    lines, _ = _read_values(path)
    remaining = dict(updates)
    rendered: list[str] = []
    for line in lines:
        name, separator, _ = line.partition("=")
        normalized_name = name.strip()
        if separator and normalized_name in remaining:
            rendered.append(f"{normalized_name}={remaining.pop(normalized_name)}")
        else:
            rendered.append(line)
    if rendered and rendered[-1]:
        rendered.append("")
    rendered.extend(f"{name}={value}" for name, value in remaining.items())
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def configure(project_root: Path) -> None:
    hermes_env = project_root / "Hermes-Lite" / ".env"
    backend_env = project_root / "dazah-backend" / ".env"
    _, hermes_values = _read_values(hermes_env)

    encryption_key = hermes_values.get("HERMES_FEISHU_CREDENTIAL_KEY")
    if not encryption_key:
        encryption_key = Fernet.generate_key().decode("ascii")
    internal_token = hermes_values.get("HERMES_INTERNAL_TOKEN")
    if not internal_token:
        internal_token = secrets.token_urlsafe(48)

    _set_values(
        hermes_env,
        {
            "HERMES_FEISHU_CREDENTIAL_KEY": encryption_key,
            "HERMES_INTERNAL_TOKEN": internal_token,
            "HERMES_FEISHU_GATEWAY_ENABLED": "true",
        },
    )
    _set_values(
        backend_env,
        {
            "HERMES_INTERNAL_URL": "http://hermes-lite:8100",
            "HERMES_INTERNAL_TOKEN": internal_token,
        },
    )


if __name__ == "__main__":
    configure(Path(__file__).resolve().parents[2])
    print("Local Feishu cutover configuration updated; no secrets were printed.")
