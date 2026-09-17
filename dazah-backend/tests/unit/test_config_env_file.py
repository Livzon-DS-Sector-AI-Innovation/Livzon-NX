"""Backend settings read environment files from the workspace root."""

from pathlib import Path

import pytest

from app.core import config


@pytest.mark.parametrize(
    ("app_env", "filename"),
    [
        ("development", ".env.local"),
        ("test", ".env.local"),
        ("production", ".env"),
    ],
)
def test_env_file_is_selected_from_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    app_env: str,
    filename: str,
) -> None:
    monkeypatch.setattr(config, "_WORKSPACE_ROOT", tmp_path)
    monkeypatch.setenv("APP_ENV", app_env)

    assert config._get_env_file() == str(tmp_path / filename)


def test_settings_load_frontend_url_from_selected_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text("FRONTEND_URL=http://localhost:3000\n", encoding="utf-8")
    monkeypatch.setattr(config, "_WORKSPACE_ROOT", tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.setitem(
        config.Settings.model_config, "env_file", config._get_env_file()
    )

    settings = config.Settings()

    assert settings.FRONTEND_URL == "http://localhost:3000"
    settings.check()
