from __future__ import annotations

import asyncio
import json
import threading
import uuid
from types import SimpleNamespace
from typing import Any

from services import dazah_agent_service as service
from tools import lark_cli as lark_cli_tool
from tools.dazah_platform import (
    current_dazah_request_context,
    record_dazah_task_confirmation,
    record_dazah_task_tool_trace,
    register_dazah_task_context,
    unregister_dazah_task_context,
)


def _payload(*, chat_type: str = "dm") -> service.AgentBackendV2Request:
    return service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
        session_id="feishu:oc_test:ou_test",
        message="你好，请回复当前会话类型",
        subject=service.AgentTrustedSubject(
            tenant_id="test-tenant",
            user_id=str(uuid.uuid4()),
            display_name="测试用户",
            source="feishu",
            external_binding_id=str(uuid.uuid4()),
        ),
        source=service.AgentBackendSource(
            platform="feishu",
            chat_type=chat_type,
            chat_id="oc_test",
            sender_open_id="ou_test",
        ),
    )


def test_feishu_private_conversation_has_authoritative_channel_instruction() -> None:
    instruction = service._conversation_channel_instruction(_payload(chat_type="dm"))

    assert "飞书私聊会话" in instruction
    assert "必须使用 lark_cli" in instruction
    assert "不得使用 dazah_tool 代理" in instruction
    assert "--as bot" in instruction
    assert "--as user" in instruction
    assert "不得回答普通文本会话、非飞书会话" in instruction
    assert "oc_test" not in instruction
    assert "ou_test" not in instruction


def test_feishu_group_conversation_is_identified_as_group() -> None:
    instruction = service._conversation_channel_instruction(_payload(chat_type="group"))

    assert "飞书群聊会话" in instruction
    assert "chat_type=group" in instruction


def test_persistent_feishu_session_is_forwarded_to_dazah_tools() -> None:
    payload = _payload()
    persistent_id = uuid.uuid4()
    payload.session_id = f"feishu:{persistent_id}"

    assert payload.context["platform_session_id"] == str(persistent_id)


def test_untrusted_channel_without_feishu_session_prefix_is_not_feishu() -> None:
    payload = _payload()
    payload.session_id = "web:test"

    assert service._is_feishu_conversation(payload) is False
    assert "不是 Hermes Feishu Gateway 标记的飞书会话" in (service._conversation_channel_instruction(payload))


def test_channel_type_query_returns_deterministic_feishu_response() -> None:
    response = service._try_conversation_context_response(_payload(chat_type="dm"))

    assert response is not None
    assert response.message.startswith("当前会话类型：飞书私聊会话")
    assert "直接使用官方 lark_cli" in response.message
    assert "不经过 Dazah 工具网关" in response.message
    assert response.pending_confirmations == []
    assert response.tool_trace == []


def test_regular_feishu_request_still_uses_agent() -> None:
    payload = _payload()
    payload.message = "读取这份电子表格"

    assert service._try_conversation_context_response(payload) is None


def test_feishu_resource_link_forces_lark_cli_routing() -> None:
    payload = _payload()
    payload.message = "读取这个多维表格的数据表和字段 [203提炼](https://example.feishu.cn/base/bascnExample)"

    assert service._is_direct_feishu_resource_request(payload) is True
    instruction = service._feishu_resource_routing_instruction(payload)
    assert "必须实际调用 lark_cli" in instruction
    assert "不得调用 energy.*" in instruction
    assert "平台当前配置的数据源类型不同" in instruction
    assert "显式传 --as bot" in instruction
    assert "bot-only" in instruction
    assert "base +record-list" in instruction
    assert "base +record-search" in instruction
    assert "lark_cli 参数中不存在 subject" in instruction


def test_base_table_name_follow_up_preserves_lark_cli_route() -> None:
    payload = _payload()
    payload.message = "进料数据记录表"
    payload.messages = [
        {
            "role": "user",
            "content": (
                "读取这个多维表格的数据表和字段 "
                "[203提炼](https://example.feishu.cn/base/bascnExample)"
            ),
        },
        {
            "role": "assistant",
            "content": "可用数据表：进料数据记录表（tblExample123）",
        },
    ]

    assert service._is_direct_feishu_resource_request(payload) is True
    instruction = service._feishu_resource_routing_instruction(payload)
    assert "复用列表结果中的 table_id" in instruction
    assert "不得要求 Dazah subject" in instruction


def test_web_resource_link_uses_native_file_route() -> None:
    payload = _payload()
    payload.session_id = "web:test"
    payload.subject.source = "web"
    payload.source.platform = "web"
    payload.message = (
        "修改这个电子表格 "
        "[测试表格](https://example.feishu.cn/sheets/shtcnExample)"
    )

    assert service._is_direct_feishu_resource_request(payload) is True
    instruction = service._feishu_resource_routing_instruction(payload)
    assert "verification_mode" in instruction
    assert "不得操作共享、成员、权限、所有权、角色" in instruction


def test_document_follow_up_preserves_native_file_route() -> None:
    payload = _payload()
    payload.message = "把该文档第二段改成已复核"
    payload.messages = [
        {
            "role": "user",
            "content": (
                "读取这个文档 "
                "[SOP](https://example.feishu.cn/docx/doccnExample)"
            ),
        }
    ]

    assert service._is_direct_feishu_resource_request(payload) is True
    assert service._recent_feishu_resource_url(payload) == (
        "https://example.feishu.cn/docx/doccnExample"
    )


def test_recent_resource_window_means_eight_conversation_rounds() -> None:
    payload = _payload()
    resource_url = "https://example.feishu.cn/wiki/wikcnExample"
    payload.message = "请继续修改刚才的文档"
    payload.messages = [
        {"role": "user", "content": f"读取 {resource_url}"},
        *[
            {"role": "assistant" if index % 2 == 0 else "user", "content": f"消息 {index}"}
            for index in range(14)
        ],
    ]

    assert service._recent_feishu_resource_url(payload) == resource_url


def test_native_file_follow_up_discards_stale_tool_failure_reply() -> None:
    payload = _payload()
    payload.message = "请在刚才的文档末尾追加一行"
    payload.messages = [
        {
            "role": "user",
            "content": "读取 https://example.feishu.cn/wiki/wikcnExample",
        },
        {
            "role": "assistant",
            "content": (
                "无法执行写入操作：write operations require an explicit resource "
                "or parent location"
            ),
        },
        {"role": "assistant", "content": "文档标题是测试文档。"},
    ]

    history = service._native_resource_conversation_history(
        payload,
        service._history(payload.messages),
    )

    assert all("explicit resource" not in item["content"] for item in history)
    assert any("必须在本轮实际调用 lark_cli" in item["content"] for item in history)
    assert any(item["content"] == "文档标题是测试文档。" for item in history)


def test_follow_up_write_reuses_trusted_recent_resource(monkeypatch) -> None:
    resource_url = "https://example.feishu.cn/docx/doccnExample"
    monkeypatch.setenv("HERMES_FEISHU_CREDENTIAL_KEY", "test-key")
    monkeypatch.setattr(lark_cli_tool, "load_credentials", lambda: ("app-id", "secret", 1))
    monkeypatch.setattr(lark_cli_tool, "enqueue_audit", lambda *_args, **_kwargs: "audit-id")
    monkeypatch.setattr(lark_cli_tool, "has_active_grant", lambda **_kwargs: False)
    captured: dict[str, str] = {}

    def fake_fingerprint(value: str) -> str:
        captured["resource"] = value
        return "resource-fingerprint"

    async def fake_run_cli(_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="", elapsed_ms=1)

    async def fake_verify(*_args, **_kwargs):
        return {"mode": "readback", "verified": True}, True

    monkeypatch.setattr(lark_cli_tool, "resource_fingerprint", fake_fingerprint)
    monkeypatch.setattr(lark_cli_tool, "run_cli", fake_run_cli)
    monkeypatch.setattr(lark_cli_tool, "verify_write_result", fake_verify)
    monkeypatch.setattr(
        lark_cli_tool,
        "create_confirmation",
        lambda **_kwargs: {"id": "confirmation-id", "risk": "medium"},
    )
    register_dazah_task_context(
        "follow-up-task",
        {"user_id": "web-user", "feishu_resource_url": resource_url},
    )
    try:
        result = asyncio.run(
            lark_cli_tool.lark_cli(
                [
                    "docs",
                    "+update",
                    "--command",
                    "append",
                    "--content",
                    "UAT-APPEND-01",
                    "--as",
                    "bot",
                ],
                verification_mode="readback",
                verification_args=[
                    "docs",
                    "+fetch",
                    "--doc",
                    resource_url,
                    "--as",
                    "bot",
                ],
                task_id="follow-up-task",
            )
        )
    finally:
        unregister_dazah_task_context("follow-up-task")

    assert captured["resource"] == resource_url
    assert json.loads(result)["status"] == "completed"


def test_mismatched_readback_target_is_blocked_before_any_cli_call(monkeypatch) -> None:
    calls: list[list[str]] = []

    async def fake_run_cli(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="", elapsed_ms=1)

    monkeypatch.setattr(lark_cli_tool, "run_cli", fake_run_cli)
    register_dazah_task_context("mismatch-task", {"user_id": "web-user"})
    try:
        result = asyncio.run(
            lark_cli_tool.lark_cli(
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
                    "--as",
                    "bot",
                ],
                resource="https://example.feishu.cn/sheets/sheetA",
                verification_mode="readback",
                verification_args=[
                    "sheets",
                    "+cells-get",
                    "--spreadsheet-token",
                    "sheetB",
                    "--sheet-id",
                    "tab1",
                    "--range",
                    "A1",
                    "--as",
                    "bot",
                ],
                task_id="mismatch-task",
            )
        )
    finally:
        unregister_dazah_task_context("mismatch-task")

    payload = json.loads(result)
    assert payload["ok"] is False
    assert "different resource" in payload["error"]
    assert calls == []


def test_direct_write_is_not_successful_when_readback_fails(monkeypatch) -> None:
    resource_url = "https://example.feishu.cn/docx/doccnExample"
    monkeypatch.setenv("HERMES_FEISHU_CREDENTIAL_KEY", "test-key")
    monkeypatch.setattr(lark_cli_tool, "load_credentials", lambda: ("app-id", "secret", 1))
    audit_events: list[str] = []
    monkeypatch.setattr(
        lark_cli_tool,
        "enqueue_audit",
        lambda *_args, **kwargs: audit_events.append(str(kwargs.get("event_type") or "tool")),
    )

    async def fake_run_cli(_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="", elapsed_ms=1)

    async def fake_verify(*_args, **_kwargs):
        return {"mode": "readback", "verified": False}, False

    monkeypatch.setattr(lark_cli_tool, "run_cli", fake_run_cli)
    monkeypatch.setattr(lark_cli_tool, "verify_write_result", fake_verify)
    register_dazah_task_context(
        "unverified-write-task",
        {"user_id": "web-user", "feishu_resource_url": resource_url},
    )
    try:
        result = asyncio.run(
            lark_cli_tool.lark_cli(
                [
                    "docs",
                    "+update",
                    "--command",
                    "append",
                    "--content",
                    "UAT-APPEND-UNVERIFIED",
                    "--as",
                    "bot",
                ],
                verification_mode="readback",
                verification_args=["docs", "+fetch", "--doc", resource_url, "--as", "bot"],
                task_id="unverified-write-task",
            )
        )
    finally:
        unregister_dazah_task_context("unverified-write-task")

    payload = json.loads(result)
    assert payload["ok"] is False
    assert payload["status"] == "verification_failed"
    assert payload["output"] == ""
    assert "resource_change" not in audit_events


def test_block_delete_requires_pre_read_text_and_forces_absence_verification(
    monkeypatch,
) -> None:
    resource_url = "https://example.feishu.cn/docx/doccnExample"
    monkeypatch.setenv("HERMES_FEISHU_CREDENTIAL_KEY", "test-key")
    monkeypatch.setattr(lark_cli_tool, "load_credentials", lambda: ("app-id", "secret", 1))
    monkeypatch.setattr(lark_cli_tool, "enqueue_audit", lambda *_args, **_kwargs: "audit-id")
    monkeypatch.setattr(lark_cli_tool, "has_active_grant", lambda **_kwargs: False)
    monkeypatch.setattr(lark_cli_tool, "resource_fingerprint", lambda _value: "fingerprint")
    calls: list[list[str]] = []
    captured: dict[str, object] = {}

    async def fake_run_cli(args, **_kwargs):
        calls.append(args)
        output = "UAT-PREVIEW-02" if args[:2] == ["docs", "+fetch"] else '{"ok":true}'
        return SimpleNamespace(returncode=0, stdout=output, stderr="", elapsed_ms=1)

    def fake_create_confirmation(**kwargs):
        captured.update(kwargs)
        return {"id": "confirmation-id", "risk": "high"}

    monkeypatch.setattr(lark_cli_tool, "run_cli", fake_run_cli)
    monkeypatch.setattr(lark_cli_tool, "create_confirmation", fake_create_confirmation)
    register_dazah_task_context("delete-task", {"user_id": "web-user"})
    try:
        result = asyncio.run(
            lark_cli_tool.lark_cli(
                [
                    "docs",
                    "+update",
                    "--doc",
                    resource_url,
                    "--command",
                    "block_delete",
                    "--block-id",
                    "doxcnExample",
                    "--as",
                    "bot",
                ],
                resource=resource_url,
                verification_mode="readback",
                verification_args=[
                    "docs",
                    "+fetch",
                    "--doc",
                    resource_url,
                    "--scope",
                    "range",
                    "--start-block-id",
                    "doxcnExample",
                    "--max-depth",
                    "0",
                    "--as",
                    "bot",
                ],
                verification_text="UAT-PREVIEW-02",
                task_id="delete-task",
            )
        )
    finally:
        unregister_dazah_task_context("delete-task")

    assert json.loads(result)["status"] == "pending_confirmation"
    assert calls[0][:2] == ["docs", "+fetch"]
    assert "--dry-run" in calls[1]
    assert captured["verification_mode"] == "absence"
    assert captured["verification_text"] == "UAT-PREVIEW-02"
    assert "删除内容：UAT-PREVIEW-02" in str(captured["preview"])


def test_plain_table_name_without_recent_base_context_is_not_forced() -> None:
    payload = _payload()
    payload.message = "进料数据记录表"

    assert service._is_direct_feishu_resource_request(payload) is False


def test_explicit_platform_sync_query_keeps_dazah_route() -> None:
    payload = _payload()
    payload.message = "查看能源配置中的已配置数据源和同步状态"

    assert service._is_direct_feishu_resource_request(payload) is False
    assert service._feishu_resource_routing_instruction(payload) == ""


def test_lark_cli_remains_visible_when_credential_key_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("LARK_CLI_PATH", "/usr/local/bin/lark-cli")
    monkeypatch.delenv("HERMES_FEISHU_CREDENTIAL_KEY", raising=False)

    assert lark_cli_tool.check_lark_cli_requirements() is True


def test_lark_cli_schema_uses_provider_compatible_optional_fields() -> None:
    entry = lark_cli_tool.registry._tools["lark_cli"]
    properties = entry.schema["parameters"]["properties"]

    assert "base +record-list" in entry.schema["description"]
    assert "base +record-search" in entry.schema["description"]
    assert "subject" in entry.schema["description"]
    assert "+record-list" in properties["args"]["description"]
    assert properties["stdin_json"]["type"] == "object"
    assert properties["module"]["type"] == "string"
    assert properties["risk_hint"]["type"] == "string"
    assert properties["verification_text"]["maxLength"] == 500
    assert None not in properties["risk_hint"]["enum"]


def test_task_context_crosses_tool_worker_boundary() -> None:
    context_token = service.dazah_request_context.set({"unrelated": "context"})
    register_dazah_task_context(
        "runtime-task",
        {"channel": "feishu", "feishu_sender_id": "ou_test"},
    )
    try:
        assert current_dazah_request_context("runtime-task")["feishu_sender_id"] == "ou_test"
    finally:
        unregister_dazah_task_context("runtime-task")
        service.dazah_request_context.reset(context_token)

    assert current_dazah_request_context("runtime-task") == {}


def test_lark_cli_accepts_registry_payload_and_execution_metadata(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LARK_CLI_PATH", "/usr/local/bin/lark-cli")
    monkeypatch.delenv("HERMES_FEISHU_CREDENTIAL_KEY", raising=False)
    token = service.dazah_request_context.set({"feishu_sender_id": "ou_test"})
    try:
        result = asyncio.run(
            lark_cli_tool.lark_cli(
                {
                    "args": ["base", "tables", "list"],
                    "resource": "bascnExample",
                    "impact_count": 0,
                },
                task_id="test-task",
                user_task="read base",
            )
        )
    finally:
        service.dazah_request_context.reset(token)

    assert "credential encryption key is not configured" in result
    assert "unexpected keyword argument" not in result


def test_native_confirmation_owner_prefers_stable_dazah_subject() -> None:
    assert lark_cli_tool._confirmation_owner_id(
        {"user_id": "stable-user", "feishu_sender_id": "event-specific-id"}
    ) == "stable-user"
    assert lark_cli_tool._confirmation_owner_id(
        {"feishu_sender_id": "legacy-feishu-id"}
    ) == "legacy-feishu-id"


def test_agent_receives_feishu_platform_and_chat_type(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def run_conversation(self, message: str, **kwargs: Any) -> dict[str, Any]:
            captured["message"] = message
            captured["run"] = kwargs
            captured["request_context"] = current_dazah_request_context()
            captured["task_context"] = current_dazah_request_context(kwargs["task_id"])
            return {"final_response": "ok"}

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)

    agent, result = service._run_agent_conversation(_payload(chat_type="p2p"))

    assert isinstance(agent, FakeAgent)
    assert result == {
        "final_response": "ok",
        "tool_trace": [],
        "current_pending_confirmations": [],
    }
    assert captured["init"]["platform"] == "feishu"
    assert captured["init"]["chat_type"] == "dm"
    assert captured["request_context"]["feishu_sender_id"] == "ou_test"
    assert captured["task_context"]["feishu_sender_id"] == "ou_test"
    assert captured["task_context"]["current_user_message"] == _payload(
        chat_type="p2p"
    ).message
    assert "当前请求来自 Hermes 原生 Feishu Gateway" in captured["run"]["system_message"]
    assert "必须使用 lark_cli" in captured["run"]["system_message"]
    assert service.dazah_request_context.get({}) == {}
    assert current_dazah_request_context() == {}


def test_single_base_record_create_uses_bounded_fast_path(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def run_conversation(self, _message: str, **kwargs: Any) -> dict[str, Any]:
            captured["system_message"] = kwargs["system_message"]
            record_dazah_task_tool_trace(
                kwargs["task_id"],
                {
                    "action": "execute",
                    "operation": "lark_cli base +record-upsert",
                    "status": "confirmation_required",
                },
            )
            return {"final_response": "待确认项已生成"}

    payload = _payload()
    payload.message = "增加一行数据，内容根据该表生成即可"
    payload.messages = [
        {
            "role": "assistant",
            "content": (
                "已读取多维表格 https://example.feishu.cn/base/bascnExample，"
                "Base Token 和进料数据记录表已解析。"
            ),
        },
        {"role": "user", "content": payload.message},
    ]
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)

    _agent, result = service._run_agent_conversation(payload)

    assert service._is_single_base_record_create(payload) is True
    assert captured["init"]["max_iterations"] == 10
    assert "Base 单行新增快速路径" in captured["system_message"]
    assert "+record-upsert" in captured["system_message"]
    assert "不得使用 record-create、record-batch-create" in captured["system_message"]
    assert "禁止自行计算 Unix 时间戳" in captured["system_message"]
    assert "confirmation.preview" in captured["system_message"]
    assert len(result["tool_trace"]) == 1


def test_cancelled_agent_run_rejects_lark_cli_before_side_effect(
    monkeypatch,
) -> None:
    cancellation = threading.Event()
    cancellation.set()
    called = False

    async def fake_run_cli(_args, **_kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(returncode=0, stdout="{}", stderr="", elapsed_ms=1)

    monkeypatch.setenv("HERMES_FEISHU_CREDENTIAL_KEY", "test-key")
    monkeypatch.setattr(lark_cli_tool, "run_cli", fake_run_cli)
    register_dazah_task_context(
        "cancelled-task",
        {
            "user_id": "web-user",
            "_cancellation_event": cancellation,
        },
    )
    try:
        result = asyncio.run(
            lark_cli_tool.lark_cli(
                ["base", "+table-list", "--base-token", "bascnExample", "--as", "bot"],
                task_id="cancelled-task",
            )
        )
    finally:
        unregister_dazah_task_context("cancelled-task")

    assert json.loads(result)["ok"] is False
    assert "cancelled" in json.loads(result)["error"]
    assert called is False


def test_single_base_write_rejects_model_generated_timestamp_before_dry_run(
    monkeypatch,
) -> None:
    called = False

    async def fake_run_cli(_args, **_kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(returncode=0, stdout="{}", stderr="", elapsed_ms=1)

    monkeypatch.setenv("HERMES_FEISHU_CREDENTIAL_KEY", "test-key")
    monkeypatch.setattr(lark_cli_tool, "run_cli", fake_run_cli)
    register_dazah_task_context(
        "invalid-date-task",
        {
            "user_id": "web-user",
            "_single_base_record_create": True,
        },
    )
    try:
        result = asyncio.run(
            lark_cli_tool.lark_cli(
                [
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
                    "--as",
                    "bot",
                ],
                task_id="invalid-date-task",
            )
        )
    finally:
        unregister_dazah_task_context("invalid-date-task")

    payload = json.loads(result)
    assert payload["ok"] is False
    assert "禁止由模型计算 Unix 时间戳" in payload["error"]
    assert called is False


def test_native_file_request_retries_once_when_model_skips_tool(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def run_conversation(self, _message: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            if len(calls) == 2:
                record_dazah_task_tool_trace(
                    kwargs["task_id"],
                    {
                        "action": "execute",
                        "operation": "lark_cli docs +update",
                        "status": "attempted",
                    },
                )
                return {"final_response": "已调用工具"}
            return {"final_response": "复述旧错误"}

    payload = _payload()
    payload.message = "请在刚才的文档末尾追加一行"
    payload.messages = [
        {
            "role": "user",
            "content": "读取 https://example.feishu.cn/wiki/wikcnExample",
        }
    ]
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)

    _agent, result = service._run_agent_conversation(payload)

    assert len(calls) == 2
    assert calls[1]["persist_user_message"] is None
    assert result["final_response"] == "已调用工具"
    assert result["tool_trace"][0]["operation"] == "lark_cli docs +update"


def test_native_write_request_retries_when_first_turn_only_reads(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    confirmation = {
        "id": "confirmation-delete-1",
        "operation": "base +record-delete",
        "summary": "删除第12条记录",
        "risk_level": "high",
        "status": "pending",
        "expires_at": "2026-08-06T03:00:00Z",
    }

    class FakeAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def run_conversation(self, _message: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            if len(calls) == 1:
                record_dazah_task_tool_trace(
                    kwargs["task_id"],
                    {
                        "action": "execute",
                        "operation": "lark_cli base +record-get",
                        "status": "completed",
                    },
                )
                return {"final_response": "待确认项已生成"}
            record_dazah_task_tool_trace(
                kwargs["task_id"],
                {
                    "action": "execute",
                    "operation": "lark_cli base +record-delete",
                    "status": "confirmation_required",
                },
            )
            record_dazah_task_confirmation(kwargs["task_id"], confirmation)
            return {"final_response": "待确认项已生成"}

    payload = _payload()
    payload.message = "进料数据记录表删除第12条数据"
    payload.messages = [
        {
            "role": "user",
            "content": "请读取 https://example.feishu.cn/base/bascnExample",
        },
        {
            "role": "assistant",
            "content": "已读取多维表格，Base Token 和进料数据记录表已解析。",
        },
        {"role": "user", "content": payload.message},
    ]
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)

    agent, result = service._run_agent_conversation(payload)

    assert len(calls) == 2
    assert "仅读取目标不算完成" in calls[1]["conversation_history"][-1]["content"]
    assert service._extract_confirmations(agent, result) == [confirmation]
    assert service._has_native_resource_write_attempt(result["tool_trace"]) is True


def test_native_file_request_uses_latest_user_history_when_message_is_blank(
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def run_conversation(self, message: str, **kwargs: Any) -> dict[str, Any]:
            calls.append((message, kwargs))
            record_dazah_task_tool_trace(
                kwargs["task_id"],
                {
                    "action": "execute",
                    "operation": "lark_cli docs +update",
                    "status": "attempted",
                },
            )
            return {"final_response": "已调用工具"}

    payload = _payload()
    payload.message = " "
    current_message = "请在刚才的文档末尾追加一行 UAT-APPEND-01，只追加一次。"
    payload.messages = [
        {
            "role": "user",
            "content": "读取 https://example.feishu.cn/wiki/wikcnExample",
        },
        {
            "role": "assistant",
            "content": "Instruction produced no document changes，文档仍保持原始状态。",
        },
        {"role": "user", "content": current_message},
    ]
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)

    _agent, result = service._run_agent_conversation(payload)

    assert service._is_direct_feishu_resource_request(payload) is True
    assert len(calls) == 1
    assert calls[0][0] == current_message
    assert calls[0][1]["persist_user_message"] == current_message
    history = calls[0][1]["conversation_history"]
    assert not any(item.get("content") == current_message for item in history)
    assert not any("Instruction produced" in item.get("content", "") for item in history)
    assert result["tool_trace"][0]["operation"] == "lark_cli docs +update"


def test_native_file_follow_up_survives_repeated_failure_history() -> None:
    payload = _payload()
    payload.message = "请在刚才的文档末尾追加一行 UAT-APPEND-01，只追加一次。"
    payload.messages = [
        {
            "role": "user",
            "content": "读取 https://example.feishu.cn/wiki/wikcnExample",
        }
    ]
    for index in range(9):
        payload.messages.extend(
            [
                {"role": "assistant", "content": f"第 {index} 次旧失败：降级代码：1011"},
                {"role": "user", "content": "请继续处理刚才的文档"},
            ]
        )

    assert len(payload.messages) > 16
    assert service._recent_feishu_resource_url(payload).endswith("wikcnExample")
    assert service._is_direct_feishu_resource_request(payload) is True


def test_native_file_skill_read_alone_does_not_count_as_resource_attempt(
    monkeypatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def run_conversation(self, _message: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            operation = "lark_cli skills read" if len(calls) == 1 else "lark_cli docs +update"
            record_dazah_task_tool_trace(
                kwargs["task_id"],
                {"action": "execute", "operation": operation, "status": "attempted"},
            )
            return {"final_response": operation}

    payload = _payload()
    payload.message = "请在刚才的文档末尾追加一行"
    payload.messages = [
        {"role": "user", "content": "读取 https://example.feishu.cn/wiki/wikcnExample"}
    ]
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)

    _agent, result = service._run_agent_conversation(payload)

    assert len(calls) == 2
    assert result["final_response"] == "lark_cli docs +update"
    assert service._has_native_resource_tool_attempt(result["tool_trace"]) is True


def test_agent_replaces_untrusted_session_tool_trace_with_current_run_trace(
    monkeypatch,
) -> None:
    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def run_conversation(self, message: str, **kwargs: Any) -> dict[str, Any]:
            return {
                "final_response": "数据来源：Dazah 平台 quality.list_deviations 操作",
                "tool_trace": [
                    {"operation": "quality.list_deviations", "ok": True}
                ],
            }

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)

    _, result = service._run_agent_conversation(_payload(chat_type="p2p"))

    assert result["tool_trace"] == []
    assert service._verified_agent_message(
        result["final_response"],
        [],
        result["tool_trace"],
    ).startswith("没有取得 Dazah 平台本轮真实工具查询结果")


def test_explicit_self_delivery_binds_forced_operation_to_trusted_task_context(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def run_conversation(self, message: str, **kwargs: Any) -> dict[str, Any]:
            captured.update(current_dazah_request_context(kwargs["task_id"]))
            return {"final_response": "ok"}

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    payload = _payload()
    payload.message = "请给我发送一条飞书消息"

    service._run_agent_conversation(payload)

    assert captured["forced_operation"] == "identity.deliver_feishu_message"


def test_agent_prompt_places_feishu_resource_route_after_progressive_skill(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def run_conversation(self, message: str, **kwargs: Any) -> dict[str, Any]:
            captured["system_message"] = kwargs["system_message"]
            return {"final_response": "ok"}

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    payload = _payload()
    payload.message = "读取这个电子表格 [测试表格](https://example.feishu.cn/sheets/shtcnExample)"
    service._run_agent_conversation(
        payload,
        progressive_skills=[{"name": "legacy-energy", "title": "旧能源规则", "content": "使用 energy.*"}],
    )

    prompt = captured["system_message"]
    assert prompt.index("旧能源规则") < prompt.index("# 本轮飞书原生资源强制路由")
