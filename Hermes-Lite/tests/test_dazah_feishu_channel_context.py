from __future__ import annotations

import asyncio
import uuid
from typing import Any

from services import dazah_agent_service as service
from tools import lark_cli as lark_cli_tool
from tools.dazah_platform import (
    current_dazah_request_context,
    register_dazah_task_context,
    unregister_dazah_task_context,
)


def _payload(*, chat_type: str = "dm") -> service.AgentBackendV2Request:
    return service.AgentBackendV2Request(
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
    assert result == {"final_response": "ok"}
    assert captured["init"]["platform"] == "feishu"
    assert captured["init"]["chat_type"] == "dm"
    assert captured["request_context"]["feishu_sender_id"] == "ou_test"
    assert captured["task_context"]["feishu_sender_id"] == "ou_test"
    assert "当前请求来自 Hermes 原生 Feishu Gateway" in captured["run"]["system_message"]
    assert "必须使用 lark_cli" in captured["run"]["system_message"]
    assert service.dazah_request_context.get({}) == {}
    assert current_dazah_request_context() == {}


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
