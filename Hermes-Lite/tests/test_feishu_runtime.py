from __future__ import annotations

import base64
import asyncio
from pathlib import Path

import pytest
from cryptography.fernet import Fernet


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_FEISHU_CREDENTIAL_KEY", Fernet.generate_key().decode())
    from services import feishu_runtime

    monkeypatch.setattr(feishu_runtime, "_db_path", lambda: tmp_path / "control.sqlite3")
    feishu_runtime.initialize_store()
    return feishu_runtime


def test_credentials_are_encrypted_at_rest(runtime, tmp_path: Path) -> None:
    runtime.save_encrypted_credentials("cli_test", "secret-value", 7)
    raw = (tmp_path / "control.sqlite3").read_bytes()
    assert b"secret-value" not in raw
    assert runtime.load_credentials() == ("cli_test", "secret-value", 7)


def test_invalid_credential_key_is_rejected(runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_FEISHU_CREDENTIAL_KEY", base64.urlsafe_b64encode(b"short").decode())
    with pytest.raises(RuntimeError, match="Fernet key"):
        runtime.save_encrypted_credentials("app", "secret", 1)


@pytest.mark.parametrize("bad", [["drive", "list;whoami"], ["api", "$(id)"], ["config", "show"]])
def test_cli_argument_injection_and_control_commands_are_blocked(runtime, bad: list[str]) -> None:
    with pytest.raises(ValueError):
        runtime.validate_args(bad)


def test_risk_can_only_be_raised(runtime) -> None:
    assert runtime.classify_risk(["drive", "delete"], "low")[0] == "high"
    assert runtime.classify_risk(["drive", "list"], "high")[0] == "high"
    assert runtime.classify_risk(["api", "approval", "approve"])[0] == "prohibited"


def test_stale_snapshot_fails_closed_for_write(runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime.save_access_snapshot(
        {
            "version": 1,
            "users": [{"open_id": "ou_1", "active": True, "modules": ["quality"], "scopes": []}],
        }
    )
    real_time = runtime.time.time
    monkeypatch.setattr(runtime.time, "time", lambda: real_time() + runtime.WRITE_MAX_AGE_SECONDS + 1)
    with pytest.raises(PermissionError, match="stale"):
        runtime.authorize("ou_1", write=True, module="quality")


def test_module_scope_is_enforced(runtime) -> None:
    runtime.save_access_snapshot(
        {
            "version": 1,
            "users": [{"open_id": "ou_1", "active": True, "modules": ["quality"], "scopes": []}],
        }
    )
    with pytest.raises(PermissionError, match="module scope"):
        runtime.authorize("ou_1", write=False, module="warehouse")


def test_confirmation_executes_once_and_creates_remembered_grant(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.save_access_snapshot(
        {
            "version": 1,
            "users": [
                {
                    "open_id": "ou_1",
                    "active": True,
                    "modules": ["quality"],
                    "scopes": ["feishu.workspace.write_any"],
                }
            ],
        }
    )
    confirmation = runtime.create_confirmation(
        user_id="ou_1",
        app_id="cli_test",
        resource="docx_1",
        action="docs update",
        args=["docs", "update", "--document-id", "docx_1"],
        stdin_json={"text": "new"},
        module="quality",
        risk="medium",
    )
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        return runtime.CliResult(0, '{"ok":true}', "", 12)

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    result = asyncio.run(
        runtime.resolve_confirmation(
            confirmation["id"], user_id="ou_1", choice="always"
        )
    )
    assert result["status"] == "completed"
    assert len(calls) == 2
    assert runtime.has_active_grant(
        user_id="ou_1",
        app_id="cli_test",
        resource="docx_1",
        action="docs update",
    )
    with pytest.raises(ValueError, match="no longer pending"):
        asyncio.run(
            runtime.resolve_confirmation(
                confirmation["id"], user_id="ou_1", choice="allow"
            )
        )


def test_high_risk_confirmation_cannot_be_remembered(runtime) -> None:
    confirmation = runtime.create_confirmation(
        user_id="ou_1",
        app_id="cli_test",
        resource="file_1",
        action="drive delete",
        args=["drive", "delete", "--file-token", "file_1"],
        stdin_json=None,
        module="quality",
        risk="high",
    )
    with pytest.raises(ValueError, match="cannot be remembered"):
        asyncio.run(
            runtime.resolve_confirmation(
                confirmation["id"], user_id="ou_1", choice="always"
            )
        )


def test_credential_rotation_uses_stdin_and_atomically_activates(
    runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("HERMES_FEISHU_TMPFS", str(runtime_root))
    calls: list[tuple[list[str], str, str | None]] = []

    async def fake_run(args, *, stdin_text="", home_dir=None, **_kwargs):
        calls.append((args, stdin_text, home_dir))
        if home_dir:
            Path(home_dir, "config-created").write_text("ok", encoding="utf-8")
        return runtime.CliResult(0, '{"ok":true}', "", 5)

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    result = asyncio.run(runtime.stage_credentials("cli_test", "super-secret", 9))
    assert result["version"] == 9
    assert "super-secret" not in " ".join(calls[0][0])
    assert calls[0][1] == "super-secret"
    assert (runtime_root / "active" / "config-created").is_file()
    assert runtime.load_credentials() == ("cli_test", "super-secret", 9)
