from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient


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


def test_delivery_outbox_is_idempotent_and_records_receipt(runtime) -> None:
    first = runtime.enqueue_delivery(
        idempotency_key="event-1",
        chat_id="oc_chat",
        content="偏差单已更新",
        metadata={"source": "quality"},
    )
    repeated = runtime.enqueue_delivery(
        idempotency_key="event-1",
        chat_id="oc_chat",
        content="不同内容不会重复投递",
    )

    assert repeated["id"] == first["id"]
    assert repeated["content"] == "偏差单已更新"
    claimed = runtime.claim_due_deliveries()
    assert [item["id"] for item in claimed] == [first["id"]]
    assert claimed[0]["attempts"] == 1

    runtime.complete_delivery(first["id"], "om_receipt")

    delivered = runtime.get_delivery(first["id"])
    assert delivered is not None
    assert delivered["status"] == "delivered"
    assert delivered["message_id"] == "om_receipt"
    assert runtime.claim_due_deliveries() == []


def test_delivery_outbox_retries_then_fails(runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    current_time = runtime.time.time()
    monkeypatch.setattr(runtime.time, "time", lambda: current_time)
    delivery = runtime.enqueue_delivery(
        idempotency_key="event-2",
        chat_id="oc_chat",
        card={"header": {"title": "待确认"}},
    )

    for attempt in range(1, 4):
        claimed = runtime.claim_due_deliveries()
        assert claimed[0]["attempts"] == attempt
        runtime.fail_delivery(delivery["id"], "temporary failure")
        current_time += 2**attempt

    failed = runtime.get_delivery(delivery["id"])
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["last_error"] == "temporary failure"


def test_inbound_message_receipt_is_atomic_durable_and_lease_recoverable(runtime) -> None:
    assert runtime.claim_inbound_message("om_inbound", now=1000) is True
    assert runtime.claim_inbound_message("om_inbound", now=1001) is False

    runtime.complete_inbound_message("om_inbound", now=1002)
    assert runtime.claim_inbound_message("om_inbound", now=5000) is False

    assert runtime.claim_inbound_message("om_crashed", now=1000) is True
    assert (
        runtime.claim_inbound_message(
            "om_crashed",
            now=1002,
            processing_lease_seconds=1,
        )
        is True
    )


def test_inbound_message_receipt_allows_only_one_concurrent_claim(runtime) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(
            pool.map(
                lambda _: runtime.claim_inbound_message("om_concurrent", now=1000),
                range(8),
            )
        )

    assert claims.count(True) == 1
    assert claims.count(False) == 7


def test_inbound_message_receipt_prunes_completed_rows_after_retention(runtime) -> None:
    assert runtime.claim_inbound_message("om_old", now=1000) is True
    runtime.complete_inbound_message("om_old", now=1001)

    assert (
        runtime.claim_inbound_message(
            "om_new",
            now=1012,
            retention_seconds=10,
        )
        is True
    )
    assert runtime.claim_inbound_message("om_old", now=1012) is True


def test_internal_delivery_api_requires_auth_and_returns_status(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.dazah_agent_service import app

    monkeypatch.setenv("HERMES_INTERNAL_TOKEN", "internal-test-token")
    client = TestClient(app)
    request = {
        "idempotency_key": "api-event-1",
        "chat_id": "oc_chat",
        "content": "请关注最新偏差记录",
    }

    assert client.post("/internal/feishu/deliveries", json=request).status_code == 401
    response = client.post(
        "/internal/feishu/deliveries",
        headers={"Authorization": "Bearer internal-test-token"},
        json=request,
    )
    assert response.status_code == 202

    delivery_id = response.json()["id"]
    status_response = client.get(
        f"/internal/feishu/deliveries/{delivery_id}",
        headers={"Authorization": "Bearer internal-test-token"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "pending"


@pytest.mark.anyio
async def test_feishu_config_migrates_legacy_runtime_version(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import dazah_agent_service as service

    token = "internal-test-token"
    secret = "new-secret"
    source_version = 3
    runtime_version = 1_784_884_127_348_647_672
    signed = f"cli_test\ndefault\ntrue\n{source_version}\n{secret}".encode()
    payload = service.FeishuCredentialConfig(
        app_id="cli_test",
        app_secret=secret,
        tenant_id="default",
        gateway_enabled=True,
        version=source_version,
        signature=hmac.new(token.encode(), signed, hashlib.sha256).hexdigest(),
    )
    staged: list[int] = []
    saved: list[int] = []

    monkeypatch.setenv("HERMES_INTERNAL_TOKEN", token)
    monkeypatch.setattr(
        service,
        "load_credentials",
        lambda: ("cli_old", "old-secret", runtime_version),
    )
    monkeypatch.setattr(
        service,
        "load_gateway_settings",
        lambda: {"tenant_id": "default", "gateway_enabled": True, "version": 2},
    )

    async def fake_stage(app_id: str, app_secret: str, version: int) -> dict:
        staged.append(version)
        return {"app_id": app_id, "version": version, "status": "active"}

    def fake_save_gateway_settings(**kwargs) -> None:
        saved.append(kwargs["version"])

    monkeypatch.setattr(service, "stage_credentials", fake_stage)
    monkeypatch.setattr(service, "save_gateway_settings", fake_save_gateway_settings)

    response = await service.put_feishu_config(payload, f"Bearer {token}")

    assert response["version"] == runtime_version + 1
    assert staged == [runtime_version + 1]
    assert saved == [source_version]


@pytest.mark.anyio
async def test_feishu_config_rejects_replayed_source_version(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import dazah_agent_service as service

    token = "internal-test-token"
    secret = "new-secret"
    source_version = 2
    signed = f"cli_test\ndefault\ntrue\n{source_version}\n{secret}".encode()
    payload = service.FeishuCredentialConfig(
        app_id="cli_test",
        app_secret=secret,
        tenant_id="default",
        gateway_enabled=True,
        version=source_version,
        signature=hmac.new(token.encode(), signed, hashlib.sha256).hexdigest(),
    )

    monkeypatch.setenv("HERMES_INTERNAL_TOKEN", token)
    monkeypatch.setattr(
        service,
        "load_gateway_settings",
        lambda: {"tenant_id": "default", "gateway_enabled": True, "version": 2},
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.put_feishu_config(payload, f"Bearer {token}")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "configuration version must increase"


@pytest.mark.parametrize("bad", [["drive", "list;whoami"], ["api", "$(id)"], ["config", "show"]])
def test_cli_argument_injection_and_control_commands_are_blocked(runtime, bad: list[str]) -> None:
    with pytest.raises(ValueError):
        runtime.validate_args(bad)


@pytest.mark.parametrize(
    "args",
    [
        [
            "base",
            "+url-resolve",
            "--url",
            "https://example/base/token",
            "--as",
            "user",
        ],
        ["base", "+table-list", "--base-token", "token", "--as=user"],
    ],
)
def test_cli_bot_only_policy_rejects_user_identity(
    runtime,
    args: list[str],
) -> None:
    with pytest.raises(ValueError, match="bot-only policy"):
        runtime.validate_args(args)


def test_risk_can_only_be_raised(runtime) -> None:
    assert runtime.classify_risk(["drive", "delete"], "low")[0] == "high"
    assert runtime.classify_risk(["drive", "list"], "high")[0] == "high"
    assert runtime.classify_risk(["api", "approval", "approve"])[0] == "prohibited"


def test_native_confirmation_executes_once_and_creates_remembered_grant(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    result = asyncio.run(runtime.resolve_confirmation(confirmation["id"], user_id="ou_1", choice="always"))
    assert result["status"] == "completed"
    assert len(calls) == 2
    assert runtime.has_active_grant(
        user_id="ou_1",
        app_id="cli_test",
        resource="docx_1",
        action="docs update",
    )
    with pytest.raises(ValueError, match="no longer pending"):
        asyncio.run(runtime.resolve_confirmation(confirmation["id"], user_id="ou_1", choice="allow"))


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
        asyncio.run(runtime.resolve_confirmation(confirmation["id"], user_id="ou_1", choice="always"))


def test_confirmation_rejects_other_sender(runtime) -> None:
    confirmation = runtime.create_confirmation(
        user_id="ou_owner",
        app_id="cli_test",
        resource="docx_1",
        action="docs update",
        args=["docs", "update", "--document-id", "docx_1"],
        stdin_json={"text": "new"},
        module="quality",
        risk="medium",
    )

    with pytest.raises(PermissionError, match="does not belong"):
        asyncio.run(
            runtime.resolve_confirmation(
                confirmation["id"],
                user_id="ou_other",
                choice="allow",
            )
        )


def test_confirmation_rejects_expired_action(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = runtime.time.time()
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
    monkeypatch.setattr(runtime.time, "time", lambda: now + 11 * 60)

    with pytest.raises(ValueError, match="no longer pending"):
        asyncio.run(
            runtime.resolve_confirmation(
                confirmation["id"],
                user_id="ou_1",
                choice="allow",
            )
        )


def test_credential_rotation_uses_stdin_and_atomically_activates(
    runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("HERMES_FEISHU_TMPFS", str(runtime_root))
    calls: list[tuple[list[str], str, str | None, str | None]] = []
    binding_source: Path | None = None

    async def fake_run(
        args,
        *,
        stdin_text="",
        home_dir=None,
        hermes_home_dir=None,
        **_kwargs,
    ):
        nonlocal binding_source
        calls.append((args, stdin_text, home_dir, hermes_home_dir))
        if home_dir:
            Path(home_dir, "config-created").write_text("ok", encoding="utf-8")
        if args[:2] == ["config", "bind"]:
            binding_source = Path(hermes_home_dir)
            binding_env = binding_source / ".env"
            if os.name != "nt":
                assert binding_env.stat().st_mode & 0o777 == 0o600
            assert binding_env.read_text(encoding="utf-8") == (
                "FEISHU_APP_ID=cli_test\nFEISHU_APP_SECRET=super-secret\n"
            )
        return runtime.CliResult(0, '{"ok":true}', "", 5)

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    result = asyncio.run(runtime.stage_credentials("cli_test", "super-secret", 9))
    assert result["version"] == 9
    assert "super-secret" not in " ".join(calls[0][0])
    assert calls[0][1] == "super-secret"
    assert [call[0] for call in calls] == [
        [
            "config",
            "init",
            "--app-id",
            "cli_test",
            "--app-secret-stdin",
            "--brand",
            "feishu",
            "--force-init",
        ],
        [
            "config",
            "bind",
            "--source",
            "hermes",
            "--identity",
            "bot-only",
        ],
        ["config", "strict-mode", "bot", "--global"],
        ["doctor"],
    ]
    assert binding_source is not None
    assert not binding_source.exists()
    assert (runtime_root / "active" / "config-created").is_file()
    assert runtime.load_credentials() == ("cli_test", "super-secret", 9)


def test_credential_binding_failure_keeps_active_version(
    runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    active = runtime_root / "active"
    active.mkdir(parents=True)
    (active / "old-config").write_text("active", encoding="utf-8")
    monkeypatch.setenv("HERMES_FEISHU_TMPFS", str(runtime_root))
    runtime.save_encrypted_credentials("cli_old", "old-secret", 4)
    binding_source: Path | None = None

    async def fake_run(
        args,
        *,
        hermes_home_dir=None,
        **_kwargs,
    ):
        nonlocal binding_source
        if args[:2] == ["config", "bind"]:
            binding_source = Path(hermes_home_dir)
            return runtime.CliResult(
                1,
                '{"error":{"message":"bind failed for super-secret"}}',
                "",
                5,
            )
        return runtime.CliResult(0, '{"ok":true}', "", 5)

    monkeypatch.setattr(runtime, "run_cli", fake_run)

    with pytest.raises(
        RuntimeError,
        match=r"Hermes bot-only binding failed.*\[REDACTED\]",
    ):
        asyncio.run(runtime.stage_credentials("cli_new", "super-secret", 5))

    assert (active / "old-config").read_text(encoding="utf-8") == "active"
    assert runtime.load_credentials() == ("cli_old", "old-secret", 4)
    assert binding_source is not None
    assert not binding_source.exists()
