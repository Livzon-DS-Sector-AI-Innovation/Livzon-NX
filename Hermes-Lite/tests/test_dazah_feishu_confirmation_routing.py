import uuid

import pytest

from services import dazah_agent_service as service


def test_unverified_confirmation_claims_are_blocked() -> None:
    result = service._verified_agent_message("已执行确认操作：发送消息", [], [])

    assert result == "没有查询到后端真实确认记录，本次未执行任何操作。请重新提交完整的收件人和消息内容。"


def test_direct_feishu_resource_response_skips_dazah_write_claim_verifier() -> None:
    message = "已经执行 Base 资源查询，但飞书返回资源不存在。"

    result = service._verified_agent_message(
        message,
        [],
        [],
        enforce_write_confirmation=False,
    )

    assert result == message


def test_direct_feishu_resource_cannot_claim_missing_confirmation() -> None:
    message = "已生成待确认项，请在下方卡片中点击确认执行。"

    result = service._verified_agent_message(
        message,
        [],
        [{"operation": "lark_cli base +record-get", "status": "completed"}],
        enforce_write_confirmation=False,
    )

    assert result == (
        "未生成真实待确认项，本次没有可执行的确认卡片，也未执行任何写入。"
        "请重新提交操作。"
    )


def test_current_run_confirmation_list_ignores_stale_session_confirmation() -> None:
    stale = {
        "id": "stale-confirmation",
        "operation": "base +record-upsert",
        "summary": "旧确认",
        "risk_level": "medium",
        "status": "pending",
        "expires_at": "2026-08-06T03:00:00Z",
    }
    agent = type("Agent", (), {"_session_messages": [stale]})()

    confirmations = service._extract_confirmations(
        agent,
        {"current_pending_confirmations": []},
    )

    assert confirmations == []


def test_unverified_business_data_claims_are_blocked() -> None:
    message = (
        "查询结果\n数据来源：Dazah 平台 quality.list_deviations 操作\n"
        "记录 1：DEV-FAKE"
    )

    result = service._verified_agent_message(message, [], [])

    assert result == (
        "没有取得 Dazah 平台本轮真实工具查询结果，本次不展示任何业务记录。"
        "请稍后重试并向管理员提供 Trace ID。"
    )


def test_verified_business_data_claims_are_preserved() -> None:
    message = "查询结果\n数据来源：quality.list_deviations\n当前没有偏差记录。"

    result = service._verified_agent_message(
        message,
        [],
        [{"operation": "quality.list_deviations", "ok": True}],
    )

    assert result == message


def test_quality_deviation_query_gets_strict_business_read_route() -> None:
    instruction = service._business_read_routing_instruction(
        "请查询质量模块最近3条偏差记录"
    )

    assert "quality.list_deviations" in instruction
    assert "只能来自本轮成功的 Tool Trace" in instruction


def test_explicit_send_command_requires_real_confirmation_without_extra_question() -> None:
    instruction = service._write_confirmation_routing_instruction("请汇总2026年6月采购清单，然后发送给但昊")

    assert "必须立即调用 identity.deliver_feishu_message" in instruction
    assert "不得再询问‘是否发送’" in instruction
    assert "query='identity.deliver_feishu_message'" in instruction


def test_send_status_query_does_not_enter_write_confirmation_route() -> None:
    instruction = service._write_confirmation_routing_instruction("查询昨天的飞书发送状态")

    assert instruction == ""


def test_self_delivery_uses_trusted_local_user_without_recipient_question() -> None:
    instruction = service._write_confirmation_routing_instruction(
        "请给我发送一条飞书消息，内容是验收成功",
        current_user_id="00000000-0000-0000-0000-000000000001",
    )

    assert 'body.recipient_user_ids=["00000000-0000-0000-0000-000000000001"]' in instruction
    assert "不得再次询问收件人" in instruction


def test_only_pending_confirmations_are_collected() -> None:
    base = {
        "id": "7ff93cb9-1e5b-4e2c-aa43-9572f9a99bdd",
        "operation": "identity.deliver_feishu_message",
        "summary": "发送交互卡片",
        "risk_level": "medium",
        "expires_at": "2026-07-16T16:00:00+08:00",
    }

    assert service._collect_confirmations({**base, "status": "pending"}, set())
    assert service._collect_confirmations({**base, "status": "executed"}, set()) == []
    assert service._collect_confirmations({**base, "status": "expired"}, set()) == []


def test_real_confirmation_replaces_redundant_send_question() -> None:
    confirmation = {
        "id": "7ff93cb9-1e5b-4e2c-aa43-9572f9a99bdd",
        "operation": "identity.deliver_feishu_message",
        "summary": "发送交互卡片",
        "risk_level": "medium",
        "status": "pending",
        "expires_at": "2026-07-16T16:00:00+08:00",
    }

    message = service._verified_agent_message(
        "采购清单已汇总。请确认是否发送？",
        [confirmation],
        [],
    )

    assert "是否发送" not in message
    assert "点击“确认执行”" in message


def test_pending_confirmation_instruction_is_deduplicated_and_canonical() -> None:
    confirmation = {
        "id": "7ff93cb9-1e5b-4e2c-aa43-9572f9a99bdd",
        "operation": "base +record-upsert",
        "summary": "新增记录",
        "risk_level": "medium",
        "status": "pending",
        "expires_at": "2026-08-06T10:03:28+08:00",
    }
    model_message = (
        "待确认项已生成。\n"
        '已生成待确认项，请在下方卡片中点击 "*****"。\n\n'
        "操作预览\n- 日期：2026-07-21\n\n"
        '待确认项已生成，请在下方卡片中点击 ""。\n'
        "待确认项已生成，请在下方确认执行卡片中点击“确认执行”。"
    )

    message = service._verified_agent_message(
        model_message,
        [confirmation],
        [],
    )

    instruction = "待确认项已生成，请在下方确认执行卡片中点击“确认执行”。"
    assert "操作预览" in message
    assert "日期：2026-07-21" in message
    assert "*****" not in message
    assert '点击 ""' not in message
    assert message.count(instruction) == 1
    assert message.endswith(instruction)


def test_write_route_is_injected_per_turn_for_continuing_session(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def run_conversation(self, message, **kwargs):
            captured["message"] = message
            captured.update(kwargs)
            return {"response": "已创建待确认操作", "messages": []}

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    payload = service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
        session_id=f"feishu:{uuid.uuid4()}",
        subject=service.AgentTrustedSubject(
            tenant_id="default",
            user_id="00000000-0000-0000-0000-000000000001",
            source="feishu",
        ),
        source=service.AgentBackendSource(
            platform="feishu",
            chat_type="p2p",
        ),
        message="给我发送一条飞书消息，内容是验收成功。",
        messages=[
            {"role": "user", "content": "之前的请求"},
            {
                "role": "assistant",
                "content": "operation is required for execute",
            },
        ],
    )

    service._run_agent_conversation(payload)

    history = captured["conversation_history"]
    assert isinstance(history, list)
    assert history[-1]["role"] == "system"
    assert "本轮重新实际调用工具" in history[-1]["content"]
    assert "identity.deliver_feishu_message" in history[-1]["content"]
    assert "本轮写操作确认强制路由" not in captured["system_message"]
    assert captured["persist_user_message"] == payload.message


def test_structured_self_delivery_body_uses_trusted_user_and_quoted_fields() -> None:
    user_id = "00000000-0000-0000-0000-000000000001"
    payload = service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
        trace_id=uuid.uuid4(),
        session_id=f"feishu:{uuid.uuid4()}",
        subject=service.AgentTrustedSubject(
            tenant_id="default",
            user_id=user_id,
            source="feishu",
        ),
        source=service.AgentBackendSource(platform="feishu", chat_type="p2p"),
        message=(
            "给我发送一条飞书消息，标题是“Livzon Agent 回执验收”，"
            "内容是“UTC+8 与 message_id 验收”。"
        ),
    )

    body = service._explicit_self_delivery_body(payload)

    assert body == {
        "recipient_user_ids": [user_id],
        "message_form": "card",
        "title": "Livzon Agent 回执验收",
        "markdown": "UTC+8 与 message_id 验收",
        "actions": [],
        "idempotency_key": "hermes-feishu:10000000-0000-0000-0000-000000000001",
    }


def test_structured_self_delivery_body_honors_explicit_text_form() -> None:
    user_id = "00000000-0000-0000-0000-000000000001"
    payload = service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid.UUID("10000000-0000-0000-0000-000000000002"),
        trace_id=uuid.uuid4(),
        session_id=f"feishu:{uuid.uuid4()}",
        subject=service.AgentTrustedSubject(
            tenant_id="default",
            user_id=user_id,
            source="feishu",
        ),
        source=service.AgentBackendSource(platform="feishu", chat_type="p2p"),
        message=(
            "给我发送一条飞书文本消息，标题是“文本投递验收”，"
            "内容是“这是一条纯文本消息”。"
        ),
    )

    body = service._explicit_self_delivery_body(payload)

    assert body is not None
    assert body["message_form"] == "text"


def test_web_self_delivery_uses_same_explicit_text_contract() -> None:
    user_id = "00000000-0000-0000-0000-000000000001"
    payload = service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid.UUID("10000000-0000-0000-0000-000000000003"),
        trace_id=uuid.uuid4(),
        session_id=f"web:{uuid.uuid4()}",
        subject=service.AgentTrustedSubject(
            tenant_id="default",
            user_id=user_id,
            source="web",
        ),
        source=service.AgentBackendSource(platform="web"),
        message=(
            "给我发送一条飞书文本消息，标题是“Web 与飞书确认一致性验收”，"
            "内容是“Web 中风险确认验收”。"
        ),
    )

    body = service._explicit_self_delivery_body(payload)

    assert body is not None
    assert body["recipient_user_ids"] == [user_id]
    assert body["message_form"] == "text"
    assert body["title"] == "Web 与飞书确认一致性验收"
    assert body["markdown"] == "Web 中风险确认验收"


@pytest.mark.asyncio
async def test_structured_self_delivery_runs_deterministic_tool_sequence(monkeypatch) -> None:
    payload = service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
        session_id=f"feishu:{uuid.uuid4()}",
        subject=service.AgentTrustedSubject(
            tenant_id="default",
            user_id="00000000-0000-0000-0000-000000000001",
            source="feishu",
        ),
        source=service.AgentBackendSource(platform="feishu", chat_type="p2p"),
        message="给我发送一条飞书消息，标题是“回执验收”，内容是“验收内容”。",
    )
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_dazah_tool(action, **kwargs):
        calls.append((action, kwargs))
        if action == "search":
            return '{"operations":["identity.deliver_feishu_message"]}'
        if action == "describe":
            return '{"operation":"identity.deliver_feishu_message"}'
        return (
            '{"requires_confirmation":true,"confirmation":'
            '{"id":"confirmation-1",'
            '"operation":"identity.deliver_feishu_message",'
            '"summary":"主动投递飞书消息","risk_level":"medium",'
            '"status":"pending","expires_at":"2026-08-03T06:00:00Z"}}'
        )

    monkeypatch.setattr(service, "dazah_tool", fake_dazah_tool)

    result = await service._try_explicit_self_delivery_confirmation(payload)

    assert result is not None
    assert len(result.pending_confirmations) == 1
    assert [action for action, _ in calls] == ["search", "describe", "execute"]
    assert calls[2][1]["operation"] == "identity.deliver_feishu_message"
    assert calls[2][1]["body"]["recipient_user_ids"] == [payload.subject.user_id]
