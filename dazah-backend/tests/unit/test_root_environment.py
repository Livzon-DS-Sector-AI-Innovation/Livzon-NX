from __future__ import annotations

import os

from app.core import config


def test_environment_file_is_selected_from_workspace_root(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(config, "_WORKSPACE_ROOT", tmp_path)

    monkeypatch.setenv("APP_ENV", "development")
    assert config.get_env_file() == tmp_path / ".env.local"

    monkeypatch.setenv("APP_ENV", "production")
    assert config.get_env_file() == tmp_path / ".env"


def test_workspace_environment_load_does_not_override_process_values(
    tmp_path, monkeypatch
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "ROOT_ENV_TEST_FROM_FILE=file-value\nROOT_ENV_TEST_SHELL=shell-from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_WORKSPACE_ROOT", tmp_path)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ROOT_ENV_TEST_FROM_FILE", raising=False)
    monkeypatch.setenv("ROOT_ENV_TEST_SHELL", "shell-value")
    monkeypatch.setattr(config, "_LOADED_ENV_FILE", None)

    loaded_path = config.load_workspace_env()

    assert loaded_path == env_file
    assert os.environ["ROOT_ENV_TEST_FROM_FILE"] == "file-value"
    assert os.environ["ROOT_ENV_TEST_SHELL"] == "shell-value"
