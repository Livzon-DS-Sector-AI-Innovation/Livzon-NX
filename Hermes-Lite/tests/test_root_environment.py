from __future__ import annotations

import os
from pathlib import Path

import hermes_cli.config as config


def test_environment_path_uses_workspace_root(monkeypatch) -> None:
    workspace_root = Path(__file__).resolve().parents[2]

    monkeypatch.setenv("APP_ENV", "development")
    assert config.get_env_path() == workspace_root / ".env.local"

    monkeypatch.setenv("APP_ENV", "production")
    assert config.get_env_path() == workspace_root / ".env"


def test_load_env_reads_the_selected_root_file_without_overriding_process_values(
    tmp_path, monkeypatch
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "HERMES_ROOT_ENV_TEST_FROM_FILE=file-value\n"
        "HERMES_ROOT_ENV_TEST_SHELL=shell-from-file\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(config, "get_env_path", lambda: env_file)
    monkeypatch.setattr(config, "_ENV_LOADED", False)
    monkeypatch.setattr(config, "_ENV_VALUES", None)
    monkeypatch.delenv("HERMES_ROOT_ENV_TEST_FROM_FILE", raising=False)
    monkeypatch.setenv("HERMES_ROOT_ENV_TEST_SHELL", "shell-value")

    values = config.load_env()

    assert values["HERMES_ROOT_ENV_TEST_FROM_FILE"] == "file-value"
    assert values["HERMES_ROOT_ENV_TEST_SHELL"] == "shell-from-file"
    assert os.environ["HERMES_ROOT_ENV_TEST_FROM_FILE"] == "file-value"
    assert os.environ["HERMES_ROOT_ENV_TEST_SHELL"] == "shell-value"
