from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from services.dazah_feishu_gateway import (
    ConversationHistoryStore,
    DazahFeishuGateway,
    DazahGatewayAttachment,
    DazahInboundEnvelope,
    build_dazah_confirmation_card,
    cleanup_cached_attachments,
    read_cached_attachment,
)


def _confirmation(
    risk: str = "medium",
    resource_domain: str = "dazah_business",
) -> dict[str, Any]:
    return {
        "id": "confirmation-1",
        "risk_level": risk,
        "resource": "deviation:DEV-001",
        "operation": "close",
        "impact_count": 1,
        "reason": "状态变更不可自动撤销",
        "preview": '{"status": "closed"}',
        "expires_at": "2026-07-30T12:00:00Z",
        "resource_domain": resource_domain,
    }


class _Adapter:
    def __init__(self) -> None:
        self.handler: Any = None
        self.calls: list[tuple[str, Any]] = []

    def set_message_handler(self, handler: Any) -> None:
        self.handler = handler

    async def connect(self) -> bool:
        self.calls.append(("connect", None))
        return True

    async def disconnect(self) -> None:
        self.calls.append(("disconnect", None))

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append(
            (
                "send",
                {
                    "chat_id": chat_id,
                    "content": content,
                    "reply_to": reply_to,
                    "metadata": metadata,
                },
            )
        )
        return True

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
        *,
        finalize: bool = False,
    ) -> bool:
        self.calls.append(
            (
                "edit",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "content": content,
                    "finalize": finalize,
                },
            )
        )
        return True

    async def _feishu_send_with_retry(self, **kwargs: Any) -> None:
        self.calls.append(("compat_card", kwargs))


class _PublicCardAdapter(_Adapter):
    async def send_interactive_card(
        self,
        chat_id: str,
        card: dict[str, Any],
    ) -> None:
        self.calls.append(("public_card", {"chat_id": chat_id, "card": card}))


class _SendResult:
    def __init__(
        self,
        success: bool,
        message_id: str | None = None,
        error: str | None = None,
    ) -> None:
        self.success = success
        self.message_id = message_id
        self.error = error


def _envelope() -> DazahInboundEnvelope:
    return DazahInboundEnvelope(
        text="分析偏差",
        message_type="text",
        sender_id="on_union",
        sender_primary_id="ou_open",
        sender_union_id="on_union",
        sender_name="测试用户",
        chat_id="oc_chat",
        chat_type="group",
        thread_id="omt_thread",
        parent_chat_id="oc_parent",
        message_id="om_event",
        reply_to_message_id="om_reply",
        reply_to_text="上一条消息",
        attachments=(),
    )


async def _events(
    *items: tuple[str, dict[str, Any]],
) -> Any:
    for sequence, (event_type, data) in enumerate(items, start=1):
        yield event_type, {
            "protocol_version": "2.0",
            "event_id": f"event-{sequence}",
            "trace_id": "trace-1",
            "run_id": "run-1",
            "sequence": sequence,
            "occurred_at": "2026-07-30T08:00:00Z",
            "type": event_type,
            "data": data,
        }


def test_confirmation_card_buttons_follow_risk_policy() -> None:
    medium = build_dazah_confirmation_card(_confirmation("medium"))
    high = build_dazah_confirmation_card(_confirmation("high"))

    medium_choices = [button["value"]["livzon_choice"] for button in medium["elements"][1]["actions"]]
    high_choices = [button["value"]["livzon_choice"] for button in high["elements"][1]["actions"]]

    native_medium = build_dazah_confirmation_card(_confirmation("medium", "feishu_native"))
    native_medium_choices = [button["value"]["livzon_choice"] for button in native_medium["elements"][1]["actions"]]

    assert medium_choices == ["allow", "reject"]
    assert native_medium_choices == ["allow", "always", "reject"]
    assert high_choices == ["allow", "reject"]
    assert high["header"]["template"] == "red"


def test_confirmation_card_displays_expiry_in_beijing_time() -> None:
    card = build_dazah_confirmation_card(_confirmation())
    content = card["elements"][0]["content"]

    assert "过期时间：** 2026-07-30 20:00:00（北京时间）" in content
    assert "2026-07-30T12:00:00Z" not in content


def test_native_confirmation_card_uses_readable_summary_without_json_block() -> None:
    confirmation = _confirmation("medium", "feishu_native")
    confirmation["preview"] = (
        "- 操作：局部文本替换\n"
        "- 原内容：UAT-APPEND-01\n"
        "- 新内容：UAT-UPDATED-01"
    )

    card = build_dazah_confirmation_card(confirmation)
    content = card["elements"][0]["content"]

    assert "变更摘要" in content
    assert "局部文本替换" in content
    assert "UAT-APPEND-01" in content
    assert "UAT-UPDATED-01" in content
    assert "```" not in content


def test_business_confirmation_card_shows_summary_scope_and_default_impact() -> None:
    confirmation = _confirmation()
    confirmation.update(
        {
            "summary": "重试失败的质量日报任务",
            "request_payload": {
                "operation": "agent.retry_automation_run",
                "reason": "原运行失败，需要创建新的独立运行",
            },
        }
    )
    confirmation.pop("reason")

    card = build_dazah_confirmation_card(confirmation)
    content = card["elements"][0]["content"]

    assert "操作摘要：** 重试失败的质量日报任务" in content
    assert "预计影响：** 1 项" in content
    assert "原运行失败，需要创建新的独立运行" in content
    assert '"data"' not in content


def test_inbound_envelope_preserves_native_feishu_context_and_attachments() -> None:
    source = SimpleNamespace(
        user_id="ou_open",
        user_id_alt="on_union",
        user_name="测试用户",
        chat_id="oc_chat",
        chat_type="group",
        thread_id="omt_thread",
        parent_chat_id="oc_parent",
        message_id="om_source",
    )
    event = SimpleNamespace(
        text="请分析附件",
        message_type=SimpleNamespace(value="document"),
        source=source,
        message_id="om_event",
        reply_to_message_id="om_reply",
        reply_to_text="上一条消息",
        media_urls=["/data/hermes/cache/documents/report.pdf"],
        media_types=["application/pdf"],
    )

    envelope = DazahInboundEnvelope.from_event(event)
    request = envelope.to_agent_backend_v2_request(
        subject={
            "tenant_id": "tenant",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "source": "feishu",
        },
        trace_id="00000000-0000-0000-0000-000000000002",
        run_id="00000000-0000-0000-0000-000000000003",
        messages=[{"role": "user", "content": "上一轮"}],
        memory_policy={"effective_mode": "explicit_only", "policy_version": 2},
    )

    assert envelope.sender_id == "on_union"
    assert request["session_id"] == "feishu:omt_thread:on_union"
    assert request["source"]["sender_open_id"] == "ou_open"
    assert request["source"]["reply_to"] == "om_reply"
    assert request["messages"] == [{"role": "user", "content": "上一轮"}]
    assert request["memory_policy"]["effective_mode"] == "explicit_only"
    assert request["attachments"] == [
        {
            "kind": "document",
            "content_type": "application/pdf",
            "local_path": "/data/hermes/cache/documents/report.pdf",
            "filename": "report.pdf",
        }
    ]

    persistent_request = envelope.to_agent_backend_v2_request(
        subject={
            "tenant_id": "tenant",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "source": "feishu",
        },
        trace_id="00000000-0000-0000-0000-000000000002",
        run_id="00000000-0000-0000-0000-000000000003",
        persistent_session_id="00000000-0000-0000-0000-000000000004",
    )
    assert persistent_request["session_id"] == (
        "feishu:00000000-0000-0000-0000-000000000004"
    )


def test_inbound_envelope_falls_back_to_open_id_and_chat_session() -> None:
    event = SimpleNamespace(
        text="你好",
        message_type="text",
        source=SimpleNamespace(
            user_id="ou_open",
            user_id_alt=None,
            user_name=None,
            chat_id="oc_chat",
            chat_type="dm",
            thread_id=None,
            parent_chat_id=None,
            message_id=None,
        ),
        message_id="om_event",
        reply_to_message_id=None,
        reply_to_text=None,
        media_urls=[],
        media_types=[],
    )

    envelope = DazahInboundEnvelope.from_event(event)

    assert envelope.sender_id == "ou_open"
    assert envelope.sender_open_id == "ou_open"
    assert envelope.sender_user_id == ""
    assert envelope.session_id == "feishu:oc_chat:ou_open"
    assert envelope.attachments == ()


def test_inbound_envelope_classifies_tenant_user_id_without_forging_open_id() -> None:
    event = SimpleNamespace(
        text="/tasks",
        message_type="text",
        source=SimpleNamespace(
            user_id="tenant-user-123",
            user_id_alt="on_union",
            user_name="测试用户",
            chat_id="oc_chat",
            chat_type="dm",
            thread_id=None,
            parent_chat_id=None,
            message_id="om_event",
        ),
        message_id="om_event",
        reply_to_message_id=None,
        reply_to_text=None,
        media_urls=[],
        media_types=[],
    )

    envelope = DazahInboundEnvelope.from_event(event)
    request = envelope.to_agent_backend_v2_request(
        subject={"tenant_id": "tenant", "user_id": "local-user", "source": "feishu"},
        trace_id="00000000-0000-0000-0000-000000000002",
        run_id="00000000-0000-0000-0000-000000000003",
    )

    assert envelope.sender_user_id == "tenant-user-123"
    assert envelope.sender_open_id == ""
    assert request["source"]["sender_user_id"] == "tenant-user-123"
    assert request["source"]["sender_open_id"] is None


def test_attachment_only_envelope_synthesizes_request_text() -> None:
    event = SimpleNamespace(
        text="",
        message_type="document",
        source=SimpleNamespace(
            user_id="ou_open",
            user_id_alt=None,
            user_name=None,
            chat_id="oc_chat",
            chat_type="dm",
            thread_id=None,
            parent_chat_id=None,
            message_id=None,
        ),
        message_id="om_document",
        reply_to_message_id=None,
        reply_to_text=None,
        media_urls=["/data/hermes/cache/documents/report.pdf"],
        media_types=["application/pdf"],
    )
    envelope = DazahInboundEnvelope.from_event(event)

    request = envelope.to_agent_backend_v2_request(
        subject={
            "tenant_id": "tenant",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "source": "feishu",
        },
        trace_id="00000000-0000-0000-0000-000000000002",
        run_id="00000000-0000-0000-0000-000000000003",
    )

    assert envelope.request_text == "请分析用户发送的附件并概括主要内容。"
    assert request["message"] == envelope.request_text
    assert request["attachments"][0]["kind"] == "document"


def test_cached_attachments_are_removed_only_from_hermes_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    cached_path = tmp_path / "hermes" / "cache" / "documents" / "report.pdf"
    cached_path.parent.mkdir(parents=True)
    cached_path.write_bytes(b"pdf")
    outside_path = tmp_path / "outside.pdf"
    outside_path.write_bytes(b"outside")
    attachments = (
        DazahGatewayAttachment(
            kind="document",
            content_type="application/pdf",
            local_path=str(cached_path),
            filename="report.pdf",
        ),
        DazahGatewayAttachment(
            kind="document",
            content_type="application/pdf",
            local_path=str(outside_path),
            filename="outside.pdf",
        ),
    )

    removed = cleanup_cached_attachments(attachments)

    assert removed == 1
    assert not cached_path.exists()
    assert outside_path.exists()


def test_cached_attachment_read_is_bounded_to_hermes_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    cached_path = tmp_path / "hermes" / "cache" / "documents" / "sales.xlsx"
    cached_path.parent.mkdir(parents=True)
    cached_path.write_bytes(b"workbook")
    outside_path = tmp_path / "outside.xlsx"
    outside_path.write_bytes(b"outside")

    assert read_cached_attachment(
        DazahGatewayAttachment(
            kind="document",
            content_type="application/octet-stream",
            local_path=str(cached_path),
            filename="sales.xlsx",
        )
    ) == b"workbook"
    assert read_cached_attachment(
        DazahGatewayAttachment(
            kind="document",
            content_type="application/octet-stream",
            local_path=str(outside_path),
            filename="outside.xlsx",
        )
    ) is None


def test_conversation_history_preserves_base_follow_up_and_is_bounded() -> None:
    history = ConversationHistoryStore(max_sessions=2, max_messages=4)
    history.append_exchange(
        "feishu:chat-1:user",
        user_message=(
            "读取 [203提炼](https://example.feishu.cn/base/bascnExample) "
            "中的数据表"
        ),
        assistant_message="进料数据记录表（tblExample123）",
    )

    snapshot = history.snapshot(
        "feishu:chat-1:user",
        reply_to_text="进料数据记录表（tblExample123）",
    )
    assert snapshot == [
        {
            "role": "user",
            "content": (
                "读取 [203提炼](https://example.feishu.cn/base/bascnExample) "
                "中的数据表"
            ),
        },
        {
            "role": "assistant",
            "content": "进料数据记录表（tblExample123）",
        },
    ]

    history.append_exchange("feishu:chat-2:user", user_message="二", assistant_message="二")
    history.append_exchange("feishu:chat-3:user", user_message="三", assistant_message="三")
    assert history.snapshot("feishu:chat-1:user") == []


@pytest.mark.asyncio
async def test_gateway_uses_public_native_send_for_ordinary_messages() -> None:
    adapter = _Adapter()
    gateway = DazahFeishuGateway(adapter)

    sent = await gateway.send(
        "chat-1",
        "处理完成",
        reply_to="message-1",
        metadata={"format": "markdown"},
    )

    assert sent is True
    assert adapter.calls == [
        (
            "send",
            {
                "chat_id": "chat-1",
                "content": "处理完成",
                "reply_to": "message-1",
                "metadata": {"format": "markdown"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_gateway_prefers_future_public_interactive_card_api() -> None:
    adapter = _PublicCardAdapter()
    gateway = DazahFeishuGateway(adapter)

    await gateway.send_confirmations("chat-1", [_confirmation()])

    assert adapter.calls[0][0] == "public_card"
    assert adapter.calls[0][1]["card"]["header"]["title"]["content"].endswith("MEDIUM")


@pytest.mark.asyncio
async def test_gateway_isolates_pinned_private_card_compatibility() -> None:
    adapter = _Adapter()
    gateway = DazahFeishuGateway(adapter)

    await gateway.send_confirmations("chat-1", [_confirmation("high")])

    kind, request = adapter.calls[0]
    assert kind == "compat_card"
    assert request["chat_id"] == "chat-1"
    assert request["msg_type"] == "interactive"
    assert json.loads(request["payload"])["header"]["template"] == "red"


@pytest.mark.asyncio
async def test_delivery_worker_uses_native_gateway_and_records_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import feishu_gateway_worker

    delivery = {
        "id": "delivery-1",
        "delivery_type": "text",
        "chat_id": "chat-1",
        "content": "主动通知",
        "reply_to": None,
        "metadata": {"source": "quality"},
    }
    completed: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        feishu_gateway_worker,
        "claim_due_deliveries",
        lambda: [delivery],
    )
    monkeypatch.setattr(
        feishu_gateway_worker,
        "complete_delivery",
        lambda delivery_id, message_id=None: completed.append((delivery_id, message_id)),
    )

    class _Result:
        success = True
        message_id = "om_receipt"
        error = None

    adapter = _Adapter()

    async def send_result(*_args: Any, **_kwargs: Any) -> _Result:
        return _Result()

    adapter.send = send_result  # type: ignore[method-assign]
    count = await feishu_gateway_worker._deliver_pending(DazahFeishuGateway(adapter))

    assert count == 1
    assert completed == [("delivery-1", "om_receipt")]


@pytest.mark.asyncio
async def test_card_delivery_worker_records_native_message_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import feishu_gateway_worker

    delivery = {
        "id": "delivery-card-1",
        "delivery_type": "card",
        "chat_id": "chat-1",
        "card": {"schema": "2.0"},
    }
    completed: list[tuple[str, str | None]] = []
    failed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        feishu_gateway_worker,
        "claim_due_deliveries",
        lambda: [delivery],
    )
    monkeypatch.setattr(
        feishu_gateway_worker,
        "complete_delivery",
        lambda delivery_id, message_id=None: completed.append((delivery_id, message_id)),
    )
    monkeypatch.setattr(
        feishu_gateway_worker,
        "fail_delivery",
        lambda delivery_id, error: failed.append((delivery_id, error)),
    )

    class CardGateway:
        async def send_card(self, chat_id, card):
            assert chat_id == "chat-1"
            assert card == {"schema": "2.0"}
            return _SendResult(True, "om_card_receipt")

    count = await feishu_gateway_worker._deliver_pending(CardGateway())

    assert count == 1
    assert completed == [("delivery-card-1", "om_card_receipt")]
    assert failed == []


@pytest.mark.asyncio
async def test_private_card_compatibility_normalizes_sdk_receipt() -> None:
    class RawData:
        message_id = "om_card_receipt"

    class RawResponse:
        code = 0
        msg = "ok"
        data = RawData()

    adapter = _Adapter()

    async def compat_result(**kwargs):
        adapter.calls.append(("compat_card", kwargs))
        return RawResponse()

    adapter._feishu_send_with_retry = compat_result  # type: ignore[method-assign]
    adapter._response_succeeded = lambda response: response.code == 0  # type: ignore[attr-defined]
    result = await DazahFeishuGateway(adapter).send_card(
        "chat-1",
        {"schema": "2.0"},
    )

    assert result.success is True
    assert result.message_id == "om_card_receipt"
    assert result.error is None


@pytest.mark.asyncio
async def test_native_stream_sends_then_finalizes_rich_message() -> None:
    from services.feishu_gateway_worker import _consume_agent_stream

    adapter = _PublicCardAdapter()
    adapter.send = AsyncMock(  # type: ignore[method-assign]
        return_value=_SendResult(True, "om_agent")
    )
    gateway = DazahFeishuGateway(adapter)

    result = await _consume_agent_stream(
        _events(
            ("text_delta", {"text": "分析"}),
            ("text_delta", {"text": "完成"}),
            (
                "finished",
                {
                    "message": "**分析完成**",
                    "pending_confirmations": [_confirmation()],
                },
            ),
        ),
        gateway,
        _envelope(),
        edit_interval_seconds=60,
    )

    assert result is None
    adapter.send.assert_awaited_once_with(
        "oc_chat",
        "分析",
        reply_to="om_reply",
        metadata={"thread_id": "omt_thread"},
    )
    assert adapter.calls[0] == (
        "edit",
        {
            "chat_id": "oc_chat",
            "message_id": "om_agent",
            "content": "**分析完成**",
            "finalize": True,
        },
    )
    assert adapter.calls[1] == (
        "public_card",
        {
            "chat_id": "oc_chat",
            "card": build_dazah_confirmation_card(_confirmation()),
        },
    )


@pytest.mark.asyncio
async def test_native_stream_without_delta_delivers_and_confirms_notice() -> None:
    from services.feishu_gateway_worker import _consume_agent_stream

    adapter = _Adapter()
    completed: list[tuple[str, bool]] = []
    result = await _consume_agent_stream(
        _events(("finished", {"message": "直接回复"})),
        DazahFeishuGateway(adapter),
        _envelope(),
        on_complete=lambda message, delivered: completed.append((message, delivered)),
    )

    assert result is None
    assert completed == [("直接回复", True)]
    assert adapter.calls == [
        (
            "send",
            {
                "chat_id": "oc_chat",
                "content": "直接回复",
                "reply_to": "om_reply",
                "metadata": {"thread_id": "omt_thread"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_native_stream_retries_final_edit_without_duplicate_message() -> None:
    from services.feishu_gateway_worker import _consume_agent_stream

    adapter = _Adapter()
    adapter.send = AsyncMock(  # type: ignore[method-assign]
        return_value=_SendResult(True, "om_agent")
    )
    adapter.edit_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _SendResult(False, error="update failed"),
            _SendResult(False, error="update failed"),
            _SendResult(False, error="update failed"),
        ]
    )

    result = await _consume_agent_stream(
        _events(
            ("text_delta", {"text": "部分"}),
            ("finished", {"message": "最终回复"}),
        ),
        DazahFeishuGateway(adapter),
        _envelope(),
        final_edit_attempts=3,
    )

    assert result is None
    assert adapter.send.await_count == 1
    assert adapter.edit_message.await_count == 3
    assert all(
        call.args == ("oc_chat", "om_agent", "最终回复")
        and call.kwargs == {"finalize": True}
        for call in adapter.edit_message.await_args_list
    )


@pytest.mark.asyncio
async def test_native_stream_heartbeat_does_not_create_extra_bubble() -> None:
    from services.feishu_gateway_worker import _consume_agent_stream

    adapter = _Adapter()
    adapter.send = AsyncMock(  # type: ignore[method-assign]
        return_value=_SendResult(True, "om-agent")
    )
    result = await _consume_agent_stream(
        _events(
            ("ping", {"ts": 1}),
            ("text_delta", {"text": "处理中"}),
            ("ping", {"ts": 2}),
            ("finished", {"message": "处理完成"}),
        ),
        DazahFeishuGateway(adapter),
        _envelope(),
        edit_interval_seconds=60,
    )

    assert result is None
    adapter.send.assert_awaited_once()
    assert [item[0] for item in adapter.calls] == ["edit"]


@pytest.mark.asyncio
async def test_native_stream_disconnect_fails_closed_and_hides_confirmations() -> None:
    from services.feishu_gateway_worker import _consume_agent_stream

    adapter = _Adapter()
    result = await _consume_agent_stream(
        _events(("confirmation", _confirmation())),
        DazahFeishuGateway(adapter),
        _envelope(),
    )

    assert result is None
    assert adapter.calls[0][0] == "send"
    assert "未收到完整回复" in adapter.calls[0][1]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("sequences", [(1, 1), (2, 1)])
async def test_native_stream_rejects_duplicate_or_out_of_order_events(sequences) -> None:
    from services.feishu_gateway_worker import _consume_agent_stream

    async def invalid_events():
        for index, sequence in enumerate(sequences):
            event_type = "ping"
            yield event_type, {
                "protocol_version": "2.0",
                "event_id": f"event-{index}",
                "trace_id": "trace-1",
                "run_id": "run-1",
                "sequence": sequence,
                "occurred_at": "2026-08-06T08:00:00Z",
                "type": event_type,
                "data": {"ts": index},
            }

    with pytest.raises(RuntimeError, match="invalid AgentBackend V2 event"):
        await _consume_agent_stream(
            invalid_events(),
            DazahFeishuGateway(_Adapter()),
            _envelope(),
        )


@pytest.mark.asyncio
async def test_sse_parser_requires_agent_backend_v2_envelopes() -> None:
    from services.feishu_gateway_worker import _iter_sse_events

    class _Response:
        async def aiter_lines(self) -> Any:
            payload = {
                "protocol_version": "2.0",
                "event_id": "event-1",
                "trace_id": "trace-1",
                "run_id": "run-1",
                "sequence": 1,
                "occurred_at": "2026-07-30T08:00:00Z",
                "type": "text_delta",
                "data": {"text": "内容"},
            }
            for line in ["event: text_delta", f"data: {json.dumps(payload)}", ""]:
                yield line

    parsed = [
        item
        async for item in _iter_sse_events(  # type: ignore[arg-type]
            _Response(),
            trace_id="trace-1",
            run_id="run-1",
        )
    ]
    assert parsed[0][0] == "text_delta"
    assert parsed[0][1]["data"] == {"text": "内容"}

    class _InvalidResponse:
        async def aiter_lines(self) -> Any:
            yield "event: finished"
            yield "data: {invalid}"
            yield ""

    with pytest.raises(RuntimeError, match="invalid JSON"):
        _ = [
            item
            async for item in _iter_sse_events(_InvalidResponse())  # type: ignore[arg-type]
        ]

    class _RemovedV1Response:
        async def aiter_lines(self) -> Any:
            yield "event: delta"
            yield 'data: {"text":"旧协议"}'
            yield ""

    with pytest.raises(RuntimeError, match="AgentBackend V2"):
        _ = [
            item
            async for item in _iter_sse_events(_RemovedV1Response())  # type: ignore[arg-type]
        ]


def test_worker_has_no_direct_private_upstream_dependency() -> None:
    worker = (Path(__file__).resolve().parents[1] / "services" / "feishu_gateway_worker.py").read_text(encoding="utf-8")

    assert "_feishu_send_with_retry" not in worker


def test_delivery_event_data_is_safe_and_requires_delivery_id() -> None:
    from services.dazah_agent_service import _delivery_event_data

    assert _delivery_event_data({"status": "completed"}) is None
    assert _delivery_event_data(
        {
            "operation": "agent.create_delivery",
            "result": {
                "delivery_id": "delivery-1",
                "status": "sent",
                "channel": "feishu",
                "content": "must not leak",
            },
        }
    ) == {
        "delivery_id": "delivery-1",
        "status": "sent",
        "channel": "feishu",
    }


def test_worker_rejects_removed_agent_backend_v1_url() -> None:
    from services.feishu_gateway_worker import _agent_backend_v2_stream_url

    assert (
        _agent_backend_v2_stream_url(
            "http://hermes-lite:8100/v2/agent/runs/"
        )
        == "http://hermes-lite:8100/v2/agent/runs/stream"
    )
    with pytest.raises(RuntimeError, match="AgentBackend V2"):
        _agent_backend_v2_stream_url("http://hermes-lite:8100/v1/chat")


def test_inbound_receipt_key_distinguishes_reaction_actions() -> None:
    from dataclasses import replace

    from services.feishu_gateway_worker import _inbound_receipt_key

    ordinary = _envelope()
    added = replace(ordinary, text="reaction:added:LIKE", message_id="om_bot")
    removed = replace(ordinary, text="reaction:removed:LIKE", message_id="om_bot")

    assert _inbound_receipt_key(ordinary) == "om_event"
    assert _inbound_receipt_key(added) == "om_bot:reaction:added:LIKE"
    assert _inbound_receipt_key(removed) == "om_bot:reaction:removed:LIKE"


def test_read_only_container_keeps_gateway_lock_in_private_tmpfs() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text(encoding="utf-8")
    compose = (project_root / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (project_root / ".env.example").read_text(encoding="utf-8")

    expected = "HERMES_GATEWAY_LOCK_DIR=/run/hermes-feishu/gateway-locks"
    assert expected in dockerfile
    assert "HERMES_GATEWAY_LOCK_DIR: /run/hermes-feishu/gateway-locks" in compose
    assert "- /run/hermes-feishu:mode=0700" in compose
    assert "read_only: true" in compose
    assert "DAZAH_API_BASE_URL=http://app:8000/api/v1" in env_example
    assert "DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm" in env_example


def test_runtime_upstream_info_requires_verified_provenance(tmp_path: Path) -> None:
    from services.feishu_gateway_worker import _runtime_upstream_info

    (tmp_path / ".dazah-upstream-provenance.json").write_text(
        json.dumps(
            {
                "release_tag": "v2026.7.7.2",
                "release_version": "0.18.2",
                "commit_sha": "9de9c25f620ff7f1ce0fd5457d596052d5159596",
            }
        ),
        encoding="utf-8",
    )

    assert _runtime_upstream_info(tmp_path) == {
        "release_tag": "v2026.7.7.2",
        "release_version": "0.18.2",
        "commit_sha": "9de9c25f620ff7f1ce0fd5457d596052d5159596",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            '/card button {"livzon_choice":"allow","confirmation_id":"c-1"}',
            ("c-1", "allow", "dazah_business"),
        ),
        ("始终允许 c-2", ("c-2", "always", "dazah_business")),
        ("拒绝 c-3", ("c-3", "reject", "dazah_business")),
        ("/card button {invalid}", None),
        (
            '/card button {"livzon_choice":"unexpected","confirmation_id":"c-4"}',
            None,
        ),
    ],
)
def test_confirmation_card_callback_is_parsed_fail_closed(
    text: str,
    expected: tuple[str, str, str] | None,
) -> None:
    from services.feishu_gateway_worker import _parse_confirmation_action

    assert _parse_confirmation_action(text) == expected


@pytest.mark.asyncio
async def test_confirmation_callback_identity_does_not_apply_false_group_gate(
    monkeypatch,
) -> None:
    from dataclasses import replace

    from services import feishu_gateway_worker as worker

    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"subject": {"user_id": "local-user"}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            del args

        async def post(self, url, *, headers, json):
            del url, headers
            recorded.update(json)
            return FakeResponse()

    monkeypatch.setattr(worker.httpx, "AsyncClient", FakeAsyncClient)
    envelope = replace(
        _envelope(),
        text=(
            '/card button {"livzon_choice":"allow",'
            '"confirmation_id":"confirmation-1"}'
        ),
        message_type="command",
        chat_type="group",
    )

    subject = await worker._resolve_trusted_subject(
        {
            "dazah_api_base_url": "http://app:8000/api/v1",
            "internal_token": "test-token",
            "tenant_id": "default",
            "app_id": "cli_test",
        },
        envelope,
    )

    assert subject == {"user_id": "local-user"}
    assert recorded["external_user_id"] is None
    assert recorded["external_open_id"] == envelope.sender_open_id
    assert recorded["external_union_id"] == envelope.sender_union_id
    assert recorded["chat_id"] is None


def test_native_confirmation_callback_uses_stable_trusted_subject() -> None:
    from services.feishu_gateway_worker import _trusted_confirmation_owner

    assert _trusted_confirmation_owner({"user_id": "stable-user"}) == "stable-user"
    with pytest.raises(PermissionError, match="owner"):
        _trusted_confirmation_owner({})


def test_help_is_available_before_identity_resolution() -> None:
    from services.feishu_gateway_worker import _public_command_response

    response = _public_command_response(" /help ")

    assert response is not None
    assert "无需绑定身份" in response
    assert "/tasks" in response
    assert "/new" in response
    assert "/memory clear confirm" in response
    assert "仅 Web 或飞书私聊" in response
    assert _public_command_response("/tasks") is None


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("Feishu identity is not bound", "同步飞书目录并绑定当前用户"),
        ("Feishu application is not the active Hermes Gateway application", "激活当前 App"),
        ("Feishu identity identifiers are inconsistent", "清理重复绑定"),
        ("Bound local user is not active", "Dazah 用户已停用"),
        ("Feishu group is not admitted for Livzon Agent", "群聊白名单"),
    ],
)
def test_identity_denial_message_preserves_actionable_reason(
    detail: str,
    expected: str,
) -> None:
    from services.feishu_gateway_worker import _identity_denial_message

    response = httpx.Response(403, json={"detail": detail})

    assert expected in _identity_denial_message(response)


def test_identity_denial_message_supports_standard_api_error_envelope() -> None:
    from services.feishu_gateway_worker import _identity_denial_message

    response = httpx.Response(
        403,
        json={"code": 403, "message": "Feishu identity identifiers are inconsistent"},
    )

    assert "清理重复绑定" in _identity_denial_message(response)


@pytest.mark.asyncio
async def test_ordinary_group_identity_still_applies_group_gate(monkeypatch) -> None:
    from dataclasses import replace

    from services import feishu_gateway_worker as worker

    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"subject": {"user_id": "local-user"}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            del args

        async def post(self, url, *, headers, json):
            del url, headers
            recorded.update(json)
            return FakeResponse()

    monkeypatch.setattr(worker.httpx, "AsyncClient", FakeAsyncClient)
    envelope = replace(_envelope(), text="普通群消息", chat_type="group")

    await worker._resolve_trusted_subject(
        {
            "dazah_api_base_url": "http://app:8000/api/v1",
            "internal_token": "test-token",
            "tenant_id": "default",
            "app_id": "cli_test",
        },
        envelope,
    )

    assert recorded["chat_id"] == envelope.chat_id


def test_confirmation_conflict_feedback_is_safe() -> None:
    from services.feishu_gateway_worker import _confirmation_error_feedback

    request = httpx.Request("POST", "http://app/confirmations/example/resolve")
    response = httpx.Response(409, request=request)
    error = httpx.HTTPStatusError(
        "conflict with sensitive upstream body",
        request=request,
        response=response,
    )

    assert _confirmation_error_feedback(error) == "该确认已处理或已过期，未重复执行。"


@pytest.mark.parametrize(
    ("result", "choice", "expected"),
    [
        ({"ok": False, "status": "failed"}, "allow", "操作执行失败，未产生已验证变更。"),
        (
            {"ok": False, "status": "verification_failed"},
            "allow",
            "回读验证未通过，系统未将本次操作判定为成功；请先核对目标当前状态，避免重复写入。",
        ),
        (
            {"ok": True, "status": "completed"},
            "allow",
            "操作已确认、执行并完成回读验证。",
        ),
        ({"ok": True, "status": "rejected"}, "reject", "操作已拒绝。"),
    ],
)
def test_confirmation_result_feedback_matches_real_terminal_status(
    result: dict[str, Any],
    choice: str,
    expected: str,
) -> None:
    from services.feishu_gateway_worker import _confirmation_result_feedback

    assert _confirmation_result_feedback(result, choice) == expected


def test_confirmation_feedback_reports_partial_success_counts() -> None:
    from services.feishu_gateway_worker import _confirmation_result_feedback

    result = {
        "data": {
            "result": {
                "ok": False,
                "status": "partial_success",
                "data": {"success_count": 3, "failed_count": 2},
            }
        }
    }

    assert _confirmation_result_feedback(result, "allow") == (
        "操作部分成功：成功 3 项，失败 2 项。"
        "系统未自动重试失败项；请发送 `/tasks` 查看进度，核对后再决定是否重试。"
    )


@pytest.mark.asyncio
async def test_confirmation_feedback_is_sent_without_action_token_reply() -> None:
    from services.feishu_gateway_worker import _send_confirmation_feedback

    calls: list[dict[str, object]] = []

    class FeedbackGateway:
        async def send(self, chat_id, content, *, reply_to=None, metadata=None):
            calls.append(
                {
                    "chat_id": chat_id,
                    "content": content,
                    "reply_to": reply_to,
                    "metadata": metadata,
                }
            )
            return _SendResult(True, "om_feedback")

    await _send_confirmation_feedback(
        FeedbackGateway(),
        _envelope(),
        "该确认已处理或已过期，未重复执行。",
    )

    assert calls == [
        {
            "chat_id": "oc_chat",
            "content": "该确认已处理或已过期，未重复执行。",
            "reply_to": None,
            "metadata": {"source": "confirmation_callback"},
        }
    ]
