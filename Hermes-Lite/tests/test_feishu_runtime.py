from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
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


@pytest.mark.anyio
async def test_restart_feishu_gateway_reconnects_child_process(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import dazah_agent_service as service

    class Process:
        returncode: int | None = None

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    old_process = Process()
    new_process = Process()
    service.app.state.feishu_gateway_process = old_process
    service.app.state.feishu_gateway_status = "connected"
    service.app.state.feishu_gateway_reconnects = 2
    monkeypatch.setattr(service, "load_credentials", lambda: ("cli_test", "secret", 4))
    monkeypatch.setattr(
        service,
        "load_gateway_settings",
        lambda: {"tenant_id": "default", "gateway_enabled": True, "version": 3},
    )

    async def reconnect() -> None:
        await asyncio.sleep(0)
        service.app.state.feishu_gateway_process = new_process
        service.app.state.feishu_gateway_reconnects = 3
        service.app.state.feishu_gateway_status = "connected"

    reconnect_task = asyncio.create_task(reconnect())
    result = await service._restart_feishu_gateway(timeout_seconds=1)
    await reconnect_task

    assert old_process.returncode == 0
    assert result == {
        "status": "connected",
        "message": "Hermes 飞书 Gateway 已重新建立连接",
        "previous_reconnects": 2,
        "gateway_reconnects": 3,
        "credential_version": 4,
        "config_version": 3,
    }


@pytest.mark.anyio
async def test_restart_feishu_gateway_rejects_disabled_runtime(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import dazah_agent_service as service

    monkeypatch.setattr(service, "load_credentials", lambda: ("cli_test", "secret", 4))
    monkeypatch.setattr(
        service,
        "load_gateway_settings",
        lambda: {"tenant_id": "default", "gateway_enabled": False, "version": 3},
    )

    with pytest.raises(HTTPException) as exc_info:
        await service._restart_feishu_gateway(timeout_seconds=0.01)

    assert exc_info.value.status_code == 409
    assert "未启用" in str(exc_info.value.detail)


@pytest.mark.parametrize("bad", [["drive", "list;whoami"], ["api", "$(id)"], ["config", "show"]])
def test_cli_argument_injection_and_control_commands_are_blocked(runtime, bad: list[str]) -> None:
    with pytest.raises(ValueError):
        runtime.validate_args(bad)


def test_doc_xml_and_markdown_are_allowed_as_literal_content(runtime) -> None:
    xml = "<p>UAT-APPEND-01</p>"
    markdown = "| column |\n| --- |\n| `$(literal)` |"

    assert runtime.validate_args(
        ["docs", "+update", "--content", xml, "--as", "bot"]
    )[3] == xml
    assert runtime.validate_args(
        ["docs", "+update", "--content", markdown, "--as", "bot"]
    )[3] == markdown
    with pytest.raises(ValueError, match="shell syntax"):
        runtime.validate_args(["docs", "+update", "--doc", "$(unsafe)"])


def test_document_append_rejects_empty_visible_content(runtime) -> None:
    with pytest.raises(ValueError, match="must contain visible text"):
        runtime.validate_nonempty_write_content(
            [
                "docs",
                "+update",
                "--command",
                "append",
                "--content",
                "<p></p>",
            ]
        )

    runtime.validate_nonempty_write_content(
        [
            "docs",
            "+update",
            "--command",
            "append",
            "--content",
            "<p>UAT-APPEND-01</p>",
        ]
    )


def test_plain_document_append_is_normalized_to_xml(runtime) -> None:
    args = [
        "docs",
        "+update",
        "--command",
        "append",
        "--content",
        "UAT-APPEND-01 & checked",
    ]

    normalized = runtime.normalize_document_write_content(args)

    assert normalized[5] == "<p>UAT-APPEND-01 &amp; checked</p>"
    assert args[5] == "UAT-APPEND-01 & checked"
    assert runtime.normalize_document_write_content(
        [*args, "--doc-format", "markdown"]
    )[5] == "UAT-APPEND-01 & checked"
    assert runtime.normalize_document_write_content(
        [*args[:5], "<p>Already XML</p>"]
    )[5] == "<p>Already XML</p>"


@pytest.mark.parametrize("command", ["replace_all", "str_replace"])
def test_document_replace_aliases_are_normalized_before_cli(
    runtime,
    command: str,
) -> None:
    normalized = runtime.normalize_document_write_content(
        [
            "docs",
            "+update",
            "--doc",
            "docxExample",
            "--command",
            command,
            "--old_str",
            "UAT-APPEND-01",
            "--new_str",
            "UAT-UPDATED-01",
            "--as",
            "bot",
        ]
    )

    assert normalized[normalized.index("--command") + 1] == "str_replace"
    assert normalized[normalized.index("--pattern") + 1] == "UAT-APPEND-01"
    assert normalized[normalized.index("--content") + 1] == "UAT-UPDATED-01"
    assert "--old_str" not in normalized
    assert "--new_str" not in normalized


def test_document_replace_aliases_reject_ambiguous_canonical_flags(runtime) -> None:
    with pytest.raises(ValueError, match="ambiguous document update flags"):
        runtime.normalize_document_write_content(
            [
                "docs",
                "+update",
                "--command",
                "str_replace",
                "--pattern",
                "old",
                "--old_str",
                "other",
                "--content",
                "new",
            ]
        )


def test_base_single_record_legacy_args_are_normalized(runtime) -> None:
    inline_json = '{"日期":"2026-08-06","数量":12}'

    normalized = runtime.normalize_base_record_write_args(
        [
            "base",
            "+record-create",
            "--base-token",
            "bascnExample",
            "--table-id",
            "tblExample",
            inline_json,
            "--as",
            "bot",
        ]
    )

    assert normalized[1] == "+record-upsert"
    assert normalized[normalized.index("--json") + 1] == inline_json
    assert runtime.effective_verification_mode(normalized, None) == "creation_receipt"


def test_base_record_update_does_not_infer_creation_verification(runtime) -> None:
    args = [
        "base",
        "+record-upsert",
        "--base-token",
        "bascnExample",
        "--table-id",
        "tblExample",
        "--record-id",
        "recExample",
        "--json",
        '{"数量":13}',
    ]

    assert runtime.effective_verification_mode(args, None) is None


def test_single_base_fast_path_converts_one_item_batch_to_upsert(runtime) -> None:
    normalized = runtime.normalize_base_record_write_args(
        [
            "base",
            "+record-batch-create",
            "--base-token",
            "bascnExample",
            "--table-id",
            "tblExample",
            "--json",
            '{"records":[{"日期":"2026-08-06","数量":12}]}',
        ],
        force_single_create=True,
    )

    assert normalized[1] == "+record-upsert"
    assert json.loads(normalized[normalized.index("--json") + 1]) == {
        "日期": "2026-08-06",
        "数量": 12,
    }


def test_single_base_fast_path_rejects_numeric_or_inconsistent_dates(runtime) -> None:
    numeric_args = [
        "base",
        "+record-upsert",
        "--base-token",
        "bascnExample",
        "--table-id",
        "tblExample",
        "--json",
        json.dumps(
            {"日期": 1752518400000, "批次号": "BT-20260721-011"},
            ensure_ascii=False,
        ),
    ]

    with pytest.raises(ValueError, match="禁止由模型计算 Unix 时间戳"):
        runtime.validate_base_record_write_values(
            numeric_args,
            require_date_strings=True,
        )

    inconsistent_args = list(numeric_args)
    inconsistent_args[-1] = json.dumps(
        {"日期": "2025-07-15 00:00:00", "批次号": "BT-20260721-011"},
        ensure_ascii=False,
    )
    with pytest.raises(ValueError, match="与同一记录编号中的日期"):
        runtime.validate_base_record_write_values(inconsistent_args)


def test_base_preview_uses_actual_submitted_date(runtime) -> None:
    args = [
        "base",
        "+record-upsert",
        "--base-token",
        "bascnExample",
        "--table-id",
        "tblExample",
        "--json",
        json.dumps(
            {"日期": 1752518400000, "批次号": "BT-20250715-011"},
            ensure_ascii=False,
        ),
    ]

    preview = runtime.safe_change_preview(args, impact_count=1)

    assert "提交数据（与实际 CLI 参数一致）" in preview
    assert "日期：2025-07-15" in preview


def test_base_creation_receipt_reads_back_record_fields(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = [
        "base",
        "+record-upsert",
        "--base-token",
        "bascnExample",
        "--table-id",
        "tblExample",
        "--json",
        json.dumps(
            {
                "日期": "2026-07-21 00:00:00",
                "批次号": "BT-20260721-011",
                "物料名称": "发酵液",
                "进料体积(m³)": 14.2,
            },
            ensure_ascii=False,
        ),
    ]

    async def fake_run(read_args, **_kwargs):
        assert read_args[:2] == ["base", "+record-get"]
        return runtime.CliResult(
            0,
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "fields": ["日期", "批次号", "物料名称", "进料体积(m³)"],
                        "data": [
                            [1784563200000, "BT-20260721-011", ["发酵液"], 14.2]
                        ],
                        "record_id_list": ["recExample"],
                    },
                },
                ensure_ascii=False,
            ),
            "",
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    write_result = runtime.CliResult(
        0,
        '{"ok":true,"data":{"record_id_list":["recExample"]}}',
        "",
        1,
    )

    verification, verified = asyncio.run(
        runtime.verify_write_result(
            write_result,
            None,
            "creation_receipt",
            write_args=args,
        )
    )

    assert verified is True
    assert verification["readback"] == "record_get"
    assert verification["matched_field_count"] == 4


def test_base_batch_creation_receipt_reads_back_every_record(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = [
        "base",
        "+record-batch-create",
        "--base-token",
        "bascnExample",
        "--table-id",
        "tblExample",
        "--json",
        json.dumps(
            {
                "records": [
                    {"fields": {"批次号": "B-001", "数量": 10}},
                    {"fields": {"批次号": "B-002", "数量": 20}},
                ]
            },
            ensure_ascii=False,
        ),
    ]

    async def fake_run(read_args, **_kwargs):
        assert read_args.count("--record-id") == 2
        return runtime.CliResult(
            0,
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "fields": ["批次号", "数量"],
                        "data": [["B-001", 10], ["B-002", 20]],
                        "record_id_list": ["rec1", "rec2"],
                    },
                },
                ensure_ascii=False,
            ),
            "",
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    verification, verified = asyncio.run(
        runtime.verify_write_result(
            runtime.CliResult(
                0,
                '{"ok":true,"data":{"record_id_list":["rec1","rec2"]}}',
                "",
                1,
            ),
            None,
            "creation_receipt",
            write_args=args,
        )
    )

    assert verified is True
    assert verification["record_count"] == 2
    assert verification["matched_field_count"] == 4


def test_native_change_preview_is_readable_and_redacted(runtime) -> None:
    preview = runtime.safe_change_preview(
        [
            "docs",
            "+update",
            "--doc",
            "https://example.feishu.cn/docx/doccnSensitiveToken",
            "--command",
            "str_replace",
            "--pattern",
            "UAT-APPEND-01",
            "--content",
            "UAT-UPDATED-01",
            "--as",
            "bot",
        ],
        impact_count=1,
    )

    assert "局部文本替换" in preview
    assert "原内容：UAT-APPEND-01" in preview
    assert "新内容：UAT-UPDATED-01" in preview
    assert "dry-run 已通过" in preview
    assert "https://" not in preview
    assert "doccnSensitiveToken" not in preview
    assert '"data"' not in preview


def test_document_text_deletion_is_high_risk_and_readable(runtime) -> None:
    args = [
        "docs",
        "+update",
        "--doc",
        "docxExample",
        "--command",
        "str_replace",
        "--pattern",
        "UAT-PREVIEW-02",
        "--content",
        "",
    ]

    assert runtime.validate_args(args) == args
    assert runtime.classify_risk(args)[0] == "high"
    assert runtime.expected_absence_text(args) == "UAT-PREVIEW-02"
    preview = runtime.safe_change_preview(args, impact_count=1)
    assert "删除匹配文本" in preview
    assert "删除内容：UAT-PREVIEW-02" in preview


def test_document_str_replace_without_content_is_also_high_risk_deletion(
    runtime,
) -> None:
    args = [
        "docs",
        "+update",
        "--doc",
        "docxExample",
        "--command",
        "str_replace",
        "--pattern",
        "UAT-PREVIEW-02",
    ]

    assert runtime.validate_args(args) == args
    assert runtime.classify_risk(args)[0] == "high"
    assert runtime.expected_absence_text(args) == "UAT-PREVIEW-02"
    preview = runtime.safe_change_preview(args, impact_count=1)
    assert "删除匹配文本" in preview
    assert "删除内容：UAT-PREVIEW-02" in preview
    assert runtime.effective_verification_mode(args, "readback") == "absence"


def test_document_block_delete_preview_shows_bounded_verification_text(runtime) -> None:
    args = [
        "docs",
        "+update",
        "--doc",
        "docxExample",
        "--command",
        "block_delete",
        "--block-id",
        "doxcnExample",
    ]

    preview = runtime.safe_change_preview(
        args,
        impact_count=1,
        verification_text="UAT-PREVIEW-02",
    )

    assert "删除内容块" in preview
    assert "删除内容：UAT-PREVIEW-02" in preview


def test_empty_cli_argument_is_only_allowed_for_str_replace_content(runtime) -> None:
    with pytest.raises(ValueError, match="invalid lark-cli argument"):
        runtime.validate_args(["docs", "+fetch", "--doc", ""])
    with pytest.raises(ValueError, match="invalid lark-cli argument"):
        runtime.validate_args(
            ["docs", "+update", "--command", "append", "--content", ""]
        )


def test_document_overwrite_requires_explicit_whole_document_intent(runtime) -> None:
    args = [
        "docs",
        "+update",
        "--doc",
        "docxExample",
        "--command",
        "overwrite",
        "--content",
        "<p>remaining content</p>",
    ]

    with pytest.raises(ValueError, match="whole-document intent"):
        runtime.validate_destructive_intent(
            args,
            "删除文档中的 UAT-PREVIEW-02，仅删除这一处",
        )
    runtime.validate_destructive_intent(args, "请覆盖整个文档并写入以下新内容")


def test_readback_requires_expected_written_text(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = {"value": "UAT-INITIAL-VALUE"}

    async def fake_run(_args, **_kwargs):
        return runtime.CliResult(0, output["value"], "", 1)

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    write_result = runtime.CliResult(0, '{"ok":true}', "", 1)
    verification_args = ["docs", "+fetch", "--doc", "doccnExample"]

    verification, verified = asyncio.run(
        runtime.verify_write_result(
            write_result,
            verification_args,
            "readback",
            "UAT-APPEND-01",
        )
    )
    assert verified is False
    assert verification["expected_text_present"] is False

    output["value"] = "UAT-INITIAL-VALUE UAT-APPEND-01"
    verification, verified = asyncio.run(
        runtime.verify_write_result(
            write_result,
            verification_args,
            "readback",
            "UAT-APPEND-01",
        )
    )
    assert verified is True
    assert verification["expected_text_present"] is True


def test_readback_retries_and_matches_structured_document_content(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def fake_run(_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return runtime.CliResult(0, '{"blocks":[]}', "", 1)
        return runtime.CliResult(
            0,
            json.dumps(
                {
                    "blocks": [
                        {"text": "日期 产品 地区 销售员"},
                        {"text": "2024-01-15 盘丝 中张三 10299.00"},
                        {"text": "2024-02-05 显示器 华东 王五 5089.00"},
                    ]
                },
                ensure_ascii=False,
            ),
            "",
            1,
        )

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    monkeypatch.setattr(runtime.asyncio, "sleep", no_wait)
    write_result = runtime.CliResult(0, '{"ok":true}', "", 1)
    expected = (
        "<p>日期 产品 地区 销售员</p>"
        "<p>2024-01-15 盘丝 中张三 10299.00</p>"
        "<p>2024-02-05 显示器 华东 王五 5089.00</p>"
    )

    verification, verified = asyncio.run(
        runtime.verify_write_result(
            write_result,
            ["docs", "+fetch", "--doc", "doccnExample"],
            "readback",
            expected,
        )
    )

    assert verified is True
    assert verification["attempts"] == 2
    assert verification["matched_anchor_count"] == verification["expected_anchor_count"]


def test_document_text_absence_requires_successful_readback_without_old_text(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = {"value": "UAT-INITIAL-VALUE UAT-PREVIEW-02"}

    async def fake_run(_args, **_kwargs):
        return runtime.CliResult(0, output["value"], "", 1)

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    write_result = runtime.CliResult(0, '{"ok":true}', "", 1)
    verification_args = ["docs", "+fetch", "--doc", "doccnExample"]

    verification, verified = asyncio.run(
        runtime.verify_write_result(
            write_result,
            verification_args,
            "absence",
            absent_text="UAT-PREVIEW-02",
        )
    )
    assert verified is False
    assert verification["absent_text_present"] is True

    output["value"] = "UAT-INITIAL-VALUE"
    verification, verified = asyncio.run(
        runtime.verify_write_result(
            write_result,
            verification_args,
            "absence",
            absent_text="UAT-PREVIEW-02",
        )
    )
    assert verified is True
    assert verification["absent_text_present"] is False


def test_base_record_delete_uses_exact_record_get_absence(runtime, monkeypatch) -> None:
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        return runtime.CliResult(
            0,
            '{"ok":true,"data":{"record_id_list":["recDeleted"],'
            '"record_not_found":["recDeleted"]}}',
            "",
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    write_args = [
        "base",
        "+record-delete",
        "--base-token",
        "bascnExample",
        "--table-id",
        "tblExample",
        "--record-id",
        "recDeleted",
        "--as",
        "bot",
    ]

    verification, verified = asyncio.run(
        runtime.verify_write_result(
            runtime.CliResult(0, '{"ok":true}', "", 1),
            ["base", "+record-list", "--base-token", "bascnExample"],
            "absence",
            write_args=write_args,
        )
    )

    assert verified is True
    assert verification["readback"] == "record_get"
    assert verification["record_not_found"] is True
    assert calls == [
        [
            "base",
            "+record-get",
            "--base-token",
            "bascnExample",
            "--table-id",
            "tblExample",
            "--record-id",
            "recDeleted",
            "--format",
            "json",
            "--as",
            "bot",
        ]
    ]


def test_base_record_delete_fails_when_exact_record_still_exists(runtime, monkeypatch) -> None:
    async def fake_run(_args, **_kwargs):
        return runtime.CliResult(
            0,
            '{"data":{"record":{"record_id":"recExisting"}}}',
            "",
            1,
        )

    async def no_wait(_delay):
        return None

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    monkeypatch.setattr(runtime.asyncio, "sleep", no_wait)
    write_args = [
        "base",
        "+record-delete",
        "--base-token",
        "bascnExample",
        "--table-id",
        "tblExample",
        "--record-id",
        "recExisting",
        "--as",
        "bot",
    ]

    verification, verified = asyncio.run(
        runtime.verify_write_result(
            runtime.CliResult(0, '{"ok":true}', "", 1),
            None,
            "absence",
            write_args=write_args,
        )
    )

    assert verified is False
    assert verification["attempts"] == 3
    assert verification["record_not_found"] is False


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ('{"ok":true,"data":{}}', True),
        ('{"ok":false,"error":"permission denied"}', False),
        ('{"code":1254045,"message":"field missing"}', False),
        ('{"ok":true,"data":{"task_status":"failed"}}', False),
        ('{"ok":true,"data":{"task_status":"in_progress"}}', False),
        ('{"ok":true,"data":{"total_count":3,"success_count":2}}', False),
        ('{"ok":true,"data":{"failed_count":1}}', False),
        ('{"ok":true,"data":{"failed_items":[{"id":"item-2"}]}}', False),
        ("operation completed", True),
        ("Error: semantic failure", False),
    ],
)
def test_cli_semantic_success_is_not_based_only_on_exit_code(
    runtime,
    stdout: str,
    expected: bool,
) -> None:
    assert runtime.cli_result_succeeded(
        runtime.CliResult(0, stdout, "", 1)
    ) is expected


def test_verification_contract_rejects_different_resource(runtime) -> None:
    with pytest.raises(ValueError, match="different resource"):
        runtime.validate_verification_contract(
            [
                "sheets",
                "+cells-set",
                "--spreadsheet-token",
                "sheetA",
                "--sheet-id",
                "tab1",
                "--range",
                "A1",
                "--cells",
                '[[{"value":"done"}]]',
            ],
            [
                "sheets",
                "+cells-get",
                "--spreadsheet-token",
                "sheetB",
                "--sheet-id",
                "tab1",
                "--range",
                "A1",
            ],
            "readback",
        )


def test_verification_contract_requires_concrete_assertion(runtime) -> None:
    with pytest.raises(ValueError, match="concrete readback assertion"):
        runtime.validate_verification_contract(
            ["drive", "+move", "--file-token", "fileA", "--folder-token", "folderB"],
            ["drive", "+inspect", "--url", "fileA"],
            "readback",
        )


def test_sheets_value_write_has_target_bound_derived_assertion(runtime) -> None:
    write_args = [
        "sheets",
        "+cells-set",
        "--spreadsheet-token",
        "sheetA",
        "--sheet-id",
        "tab1",
        "--range",
        "A1:B1",
        "--cells",
        '[[{"value":"done"},{"value":42}]]',
    ]
    read_args = [
        "sheets",
        "+cells-get",
        "--spreadsheet-token",
        "sheetA",
        "--sheet-id",
        "tab1",
        "--range",
        "A1:B1",
    ]

    runtime.validate_verification_contract(
        write_args,
        read_args,
        "readback",
    )

    assert runtime.expected_verification_text(write_args) == "done 42"


def test_sheets_style_assertion_includes_all_structured_properties(runtime) -> None:
    write_args = [
        "sheets",
        "+cells-set-style",
        "--spreadsheet-token",
        "sheetA",
        "--sheet-id",
        "tab1",
        "--range",
        "A1:B2",
        "--styles",
        '{"font":{"bold":true,"color":"#112233"},"number_format":"0.00"}',
        "--width",
        "120",
    ]

    assert runtime.expected_verification_text(write_args) == "#112233 0.00 120"


def test_document_block_verification_must_bind_exact_block(runtime) -> None:
    write_args = [
        "docs",
        "+update",
        "--doc",
        "docA",
        "--command",
        "block_replace",
        "--block-id",
        "blockA",
        "--content",
        "replacement",
    ]
    exact_read = [
        "docs",
        "+fetch",
        "--doc",
        "docA",
        "--scope",
        "range",
        "--start-block-id",
        "blockA",
    ]

    runtime.validate_verification_contract(write_args, exact_read, "readback")
    with pytest.raises(ValueError, match="missing a write target identifier"):
        runtime.validate_verification_contract(
            write_args,
            ["docs", "+fetch", "--doc", "docA"],
            "readback",
        )


def test_slides_verification_accepts_real_presentation_flag(runtime) -> None:
    runtime.validate_verification_contract(
        [
            "slides",
            "+replace-slide",
            "--presentation",
            "presentationA",
            "--slide-id",
            "slideA",
            "--content",
            "Quarterly result",
        ],
        [
            "slides",
            "+xml-get",
            "--presentation",
            "presentationA",
            "--slide-id",
            "slideA",
        ],
        "readback",
    )


def test_drive_delete_accepts_semantic_not_found_from_exact_lookup(
    runtime,
    monkeypatch,
) -> None:
    async def fake_run(_args, **_kwargs):
        return runtime.CliResult(
            0,
            '{"ok":false,"error":"file not found"}',
            "",
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    write_args = ["drive", "+delete", "--file-token", "fileA"]
    read_args = ["drive", "+inspect", "--url", "fileA", "--type", "file"]

    runtime.validate_verification_contract(
        write_args,
        read_args,
        "absence",
    )
    verification, verified = asyncio.run(
        runtime.verify_write_result(
            runtime.CliResult(0, '{"ok":true}', "", 1),
            read_args,
            "absence",
            write_args=write_args,
        )
    )

    assert verified is True
    assert verification["attempts"] == 1


def test_sheet_delete_checks_exhaustive_workbook_listing(runtime, monkeypatch) -> None:
    async def fake_run(_args, **_kwargs):
        return runtime.CliResult(
            0,
            '{"ok":true,"data":{"sheets":[{"sheet_id":"tab2"}]}}',
            "",
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    write_args = [
        "sheets",
        "+sheet-delete",
        "--spreadsheet-token",
        "sheetA",
        "--sheet-id",
        "tab1",
    ]
    read_args = [
        "sheets",
        "+workbook-info",
        "--spreadsheet-token",
        "sheetA",
    ]
    absent_text = runtime.expected_absence_text(write_args)

    runtime.validate_verification_contract(
        write_args,
        read_args,
        "absence",
    )
    _verification, verified = asyncio.run(
        runtime.verify_write_result(
            runtime.CliResult(0, '{"ok":true}', "", 1),
            read_args,
            "absence",
            absent_text=absent_text,
            write_args=write_args,
        )
    )

    assert absent_text == "tab1"
    assert verified is True


def test_raw_api_verification_requires_matching_structured_identifier(runtime) -> None:
    with pytest.raises(ValueError, match="matching structured target"):
        runtime.validate_verification_target(
            [
                "api",
                "PATCH",
                "/open-apis/bitable/v1/apps/app/tables/table/records/record",
                "--params",
                '{"app_token":"appA","table_id":"tableA","record_id":"recA"}',
                "--data",
                '{"fields":{"Status":"Done"}}',
            ],
            [
                "api",
                "GET",
                "/open-apis/bitable/v1/apps/app/tables/table/records/record",
                "--params",
                '{"app_token":"appB","table_id":"tableA","record_id":"recA"}',
            ],
        )


def test_raw_api_verification_requires_every_write_identifier(runtime) -> None:
    with pytest.raises(ValueError, match="matching structured target"):
        runtime.validate_verification_target(
            [
                "api",
                "PATCH",
                "/open-apis/bitable/v1/apps/app/tables/table/records/record",
                "--params",
                '{"app_token":"appA","table_id":"tableA","record_id":"recA"}',
            ],
            [
                "api",
                "GET",
                "/open-apis/bitable/v1/apps/app/tables/table/records/record",
                "--params",
                '{"app_token":"appA","table_id":"tableA"}',
            ],
        )


def test_non_base_creation_receipt_performs_derived_readback(
    runtime,
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        return runtime.CliResult(
            0,
            '{"ok":true,"data":{"title":"UAT document","content":"created body"}}',
            "",
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    write_args = [
        "docs",
        "+create",
        "--title",
        "UAT document",
        "--content",
        "created body",
    ]
    verification, verified = asyncio.run(
        runtime.verify_write_result(
            runtime.CliResult(
                0,
                '{"ok":true,"data":{"document_id":"docCreated"}}',
                "",
                1,
            ),
            None,
            "creation_receipt",
            write_args=write_args,
        )
    )

    assert verified is True
    assert calls[0][:4] == ["docs", "+fetch", "--doc", "docCreated"]
    assert verification["expected_anchor_count"] == 3


def test_unsupported_creation_receipt_is_rejected(runtime) -> None:
    with pytest.raises(ValueError, match="not valid"):
        runtime.validate_verification_contract(
            ["drive", "+create-shortcut", "--file-token", "sourceA"],
            None,
            "creation_receipt",
        )


def test_base_record_update_compares_exact_fields(runtime, monkeypatch) -> None:
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        return runtime.CliResult(
            0,
            runtime.json.dumps(
                {
                    "ok": True,
                    "data": {
                        "fields": ["状态", "数量"],
                        "data": [["完成", 3]],
                        "record_id_list": ["recA"],
                    },
                },
                ensure_ascii=False,
            ),
            "",
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    write_args = [
        "base",
        "+record-upsert",
        "--base-token",
        "baseA",
        "--table-id",
        "tblA",
        "--record-id",
        "recA",
        "--json",
        '{"状态":"完成","数量":3}',
    ]

    verification, verified = asyncio.run(
        runtime.verify_write_result(
            runtime.CliResult(0, '{"ok":true}', "", 1),
            None,
            "readback",
            write_args=write_args,
        )
    )

    assert verified is True
    assert verification["matched_field_count"] == 2
    assert calls[0][:2] == ["base", "+record-get"]


def test_base_batch_delete_requires_every_record_to_be_missing(runtime, monkeypatch) -> None:
    async def fake_run(_args, **_kwargs):
        return runtime.CliResult(
            0,
            '{"ok":true,"data":{"record_not_found":["recA"]}}',
            "",
            1,
        )

    async def no_wait(_delay):
        return None

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    monkeypatch.setattr(runtime.asyncio, "sleep", no_wait)
    write_args = [
        "base",
        "+record-delete",
        "--base-token",
        "baseA",
        "--table-id",
        "tblA",
        "--record-id",
        "recA",
        "--record-id",
        "recB",
    ]

    verification, verified = asyncio.run(
        runtime.verify_write_result(
            runtime.CliResult(0, '{"ok":true}', "", 1),
            None,
            "absence",
            write_args=write_args,
        )
    )

    assert verified is False
    assert verification["record_count"] == 2


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


@pytest.mark.parametrize(
    ("args", "risk"),
    [
        (["sheets", "+csv-put"], "medium"),
        (["sheets", "+table-put"], "medium"),
        (["base", "+record-upsert"], "medium"),
        (["base", "+record-batch-create"], "high"),
        (
            [
                "docs",
                "+update",
                "--doc",
                "docxExample",
                "--command",
                "str_replace",
                "--pattern",
                "old",
                "--content",
                "new",
            ],
            "medium",
        ),
        (
            [
                "docs",
                "+update",
                "--doc",
                "docxExample",
                "--command",
                "block_replace",
                "--block-id",
                "blockExample",
                "--content",
                "new",
            ],
            "medium",
        ),
        (
            [
                "docs",
                "+update",
                "--doc",
                "docxExample",
                "--command",
                "overwrite",
                "--content",
                "new",
            ],
            "high",
        ),
        (["api", "POST", "/open-apis/bitable/v1/apps/app/records"], "medium"),
        (["api", "DELETE", "/open-apis/drive/v1/files/file"], "high"),
    ],
)
def test_file_write_risk_covers_shortcuts_and_http_verbs(
    runtime,
    args: list[str],
    risk: str,
) -> None:
    assert runtime.is_write_operation(args) is True
    assert runtime.classify_risk(args)[0] == risk


@pytest.mark.parametrize(
    "args",
    [
        ["drive", "+permission-add"],
        ["wiki", "+member-add"],
        ["base", "+role-update"],
        ["drive", "+share"],
    ],
)
def test_file_permission_and_sharing_operations_are_prohibited(
    runtime,
    args: list[str],
) -> None:
    assert runtime.classify_risk(args)[0] == "prohibited"


def test_write_metadata_is_bounded_and_resource_is_hashed(runtime) -> None:
    resource = "https://example.feishu.cn/sheets/shtcnSensitiveToken"

    assert runtime.resource_fingerprint(resource) != resource
    assert "shtcnSensitiveToken" not in runtime.safe_resource_label(resource)
    assert runtime.infer_impact_count(
        ["base", "+record-batch-create"],
        {"records": [{}, {}, {}]},
        1,
    ) >= 21


def test_explicit_resource_is_inferred_from_typed_target_flags(runtime) -> None:
    resource = "https://example.feishu.cn/docx/doccnExample"

    assert runtime.infer_explicit_resource(
        ["docs", "+update", "--doc", resource, "--command", "append"]
    ) == resource
    assert runtime.infer_explicit_resource(
        ["base", "+record-upsert", "--base-token", "bascnExample"]
    ) == "bascnExample"
    assert runtime.infer_explicit_resource(
        ["api", "PATCH", "/open-apis/docx/v1/documents/doccnExample"]
    ) == "/open-apis/docx/v1/documents/doccnExample"
    assert runtime.infer_explicit_resource(
        ["docs", "+create", "--content", "not-a-resource"]
    ) == ""


def test_raw_api_is_limited_to_file_resources(runtime) -> None:
    assert runtime.validate_args(
        ["api", "POST", "/open-apis/bitable/v1/apps/app/records"]
    )
    with pytest.raises(ValueError, match="file resources"):
        runtime.validate_args(["api", "POST", "/open-apis/im/v1/messages"])


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
        verification_args=["docs", "+fetch", "--doc", "docx_1"],
        verification_mode="readback",
        verification_text="new",
    )
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        output = "new" if args[:2] == ["docs", "+fetch"] else '{"ok":true}'
        return runtime.CliResult(0, output, "", 12)

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    result = asyncio.run(runtime.resolve_confirmation(confirmation["id"], user_id="ou_1", choice="always"))
    assert result["status"] == "completed"
    assert len(calls) == 3
    assert runtime.has_active_grant(
        user_id="ou_1",
        app_id="cli_test",
        resource="docx_1",
        action="docs update",
    )
    repeated = asyncio.run(
        runtime.resolve_confirmation(
            confirmation["id"],
            user_id="ou_1",
            choice="allow",
        )
    )
    assert repeated["deduplicated"] is True


def test_internal_native_confirmation_api_is_authenticated_and_idempotent(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.dazah_agent_service import app

    token = "internal-test-token"
    monkeypatch.setenv("HERMES_INTERNAL_TOKEN", token)
    confirmation = runtime.create_confirmation(
        user_id="web-user-1",
        app_id="cli_test",
        resource="resource-fingerprint",
        resource_label="飞书资源 …ample",
        action="docs update",
        args=["docs", "update", "--document-id", "docx_1"],
        stdin_json={"text": "new"},
        module=None,
        risk="medium",
        verification_args=["docs", "+fetch", "--doc", "docx_1"],
        verification_mode="readback",
        verification_text="new",
    )

    async def fake_run(args, **_kwargs):
        output = "new" if args[:2] == ["docs", "+fetch"] else '{"ok":true}'
        return runtime.CliResult(0, output, "", 12)

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    endpoint = f"/internal/feishu/confirmations/{confirmation['id']}"

    assert client.get(endpoint, params={"user_id": "web-user-1"}).status_code == 401
    assert client.get(
        endpoint,
        headers=headers,
        params={"user_id": "web-user-1"},
    ).json()["status"] == "pending"
    first = client.post(
        f"{endpoint}/resolve",
        headers=headers,
        json={"user_id": "web-user-1", "choice": "allow"},
    )
    repeated = client.post(
        f"{endpoint}/resolve",
        headers=headers,
        json={"user_id": "web-user-1", "choice": "allow"},
    )

    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert repeated.status_code == 200
    assert repeated.json()["deduplicated"] is True


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


def test_write_without_enforceable_readback_is_stopped_before_execution(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    confirmation = runtime.create_confirmation(
        user_id="ou_1",
        app_id="cli_test",
        resource="docx_1",
        action="docs +update",
        args=[
            "docs",
            "+update",
            "--doc",
            "docx_1",
            "--command",
            "str_replace",
            "--pattern",
            "delete me",
        ],
        stdin_json=None,
        module=None,
        risk="high",
    )
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        return runtime.CliResult(0, '{"ok":true}', "", 1)

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    with pytest.raises(RuntimeError, match="enforceable readback contract"):
        asyncio.run(
            runtime.resolve_confirmation(
                confirmation["id"], user_id="ou_1", choice="allow"
            )
        )

    assert calls == []
    assert runtime.get_confirmation_status(
        confirmation["id"], user_id="ou_1"
    )["status"] == "stale"


def test_failed_base_delete_can_be_reconciled_without_replaying_write(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = [
        "base",
        "+record-delete",
        "--base-token",
        "bascnExample",
        "--table-id",
        "tblExample",
        "--record-id",
        "recDeleted",
        "--as",
        "bot",
    ]
    confirmation = runtime.create_confirmation(
        user_id="ou_1",
        app_id="cli_test",
        resource="base_fingerprint",
        action="base +record-delete",
        args=args,
        stdin_json=None,
        module=None,
        risk="high",
        verification_mode="absence",
    )
    with runtime._connect() as connection:
        connection.execute(
            "UPDATE confirmations SET status='verification_failed' WHERE id=?",
            (confirmation["id"],),
        )
    calls: list[list[str]] = []

    async def fake_run(read_args, **_kwargs):
        calls.append(read_args)
        return runtime.CliResult(
            0,
            '{"ok":true,"data":{"record_not_found":["recDeleted"]}}',
            "",
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)

    result = asyncio.run(
        runtime.resolve_confirmation(
            confirmation["id"], user_id="ou_1", choice="allow"
        )
    )

    assert result["status"] == "completed"
    assert result["reconciled"] is True
    assert result["deduplicated"] is True
    assert len(calls) == 1
    assert calls[0][:2] == ["base", "+record-get"]
    assert ["base", "+record-delete"] != calls[0][:2]
    assert runtime.get_confirmation_status(
        confirmation["id"], user_id="ou_1"
    )["status"] == "completed"


def test_failed_document_write_reconciles_with_readback_only(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    confirmation = runtime.create_confirmation(
        user_id="ou_1",
        app_id="cli_test",
        resource="doc_fingerprint",
        action="docs +update",
        args=[
            "docs",
            "+update",
            "--doc",
            "docA",
            "--command",
            "append",
            "--content",
            "RECOVERY-MARKER",
        ],
        stdin_json=None,
        module=None,
        risk="medium",
        verification_args=["docs", "+fetch", "--doc", "docA"],
        verification_mode="readback",
    )
    with runtime._connect() as connection:
        connection.execute(
            "UPDATE confirmations SET status='verification_failed' WHERE id=?",
            (confirmation["id"],),
        )
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        return runtime.CliResult(0, "existing RECOVERY-MARKER", "", 1)

    monkeypatch.setattr(runtime, "run_cli", fake_run)

    result = asyncio.run(
        runtime.resolve_confirmation(
            confirmation["id"], user_id="ou_1", choice="allow"
        )
    )

    assert result["status"] == "completed"
    assert result["reconciled"] is True
    assert calls == [["docs", "+fetch", "--doc", "docA"]]


def test_cli_confirmation_gate_retries_once_with_yes_after_user_confirmation(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    confirmation = runtime.create_confirmation(
        user_id="ou_1",
        app_id="cli_test",
        resource="file_1",
        action="drive +delete",
        args=["drive", "+delete", "--file-token", "file_1"],
        stdin_json=None,
        module=None,
        risk="high",
        verification_args=[
            "drive",
            "+inspect",
            "--url",
            "file_1",
            "--type",
            "file",
        ],
        verification_mode="absence",
        verification_text="file_1",
    )
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        if args[:2] == ["drive", "+inspect"]:
            return runtime.CliResult(0, '{"ok":true,"data":[]}', "", 1)
        if "--dry-run" in args or "--yes" in args:
            return runtime.CliResult(0, '{"ok":true}', "", 1)
        return runtime.CliResult(
            10,
            "",
            runtime.json.dumps(
                {
                    "error": {
                        "type": "confirmation",
                        "subtype": "confirmation_required",
                    }
                }
            ),
            1,
        )

    monkeypatch.setattr(runtime, "run_cli", fake_run)
    result = asyncio.run(
        runtime.resolve_confirmation(
            confirmation["id"], user_id="ou_1", choice="allow"
        )
    )

    assert result["status"] == "completed"
    assert len(calls) == 4
    assert "--yes" not in calls[1]
    assert calls[2][-1] == "--yes"
    assert calls[3][:2] == ["drive", "+inspect"]


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
