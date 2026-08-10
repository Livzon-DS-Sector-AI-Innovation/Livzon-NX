from __future__ import annotations

from pathlib import Path

from scripts.configure_local_memory_security import configure


def _read_values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def test_configure_generates_and_preserves_memory_key(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=value\n", encoding="utf-8")

    assert configure(env_path, require_policy=False) is True
    first = _read_values(env_path)
    assert first["EXISTING"] == "value"
    assert first["HERMES_USER_MEMORY_KEYS"]
    assert first["HERMES_USER_MEMORY_REQUIRE_POLICY"] == "false"

    assert configure(env_path, require_policy=True) is False
    second = _read_values(env_path)
    assert second["HERMES_USER_MEMORY_KEYS"] == first["HERMES_USER_MEMORY_KEYS"]
    assert second["HERMES_USER_MEMORY_REQUIRE_POLICY"] == "true"
