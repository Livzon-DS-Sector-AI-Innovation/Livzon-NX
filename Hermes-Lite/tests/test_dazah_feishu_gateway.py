from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from services.dazah_feishu_gateway import (
    ConversationHistoryStore,
    DazahFeishuGateway,
    DazahInboundEnvelope,
    build_dazah_confirmation_card,
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
        sender_open_id="ou_open",
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
    )

    assert envelope.sender_id == "on_union"
    assert request["session_id"] == "feishu:omt_thread:on_union"
    assert request["source"]["sender_open_id"] == "ou_open"
    assert request["source"]["reply_to"] == "om_reply"
    assert request["messages"] == [{"role": "user", "content": "上一轮"}]
    assert request["attachments"] == [
        {
            "kind": "document",
            "content_type": "application/pdf",
            "local_path": "/data/hermes/cache/documents/report.pdf",
            "filename": "report.pdf",
        }
    ]


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
    assert envelope.session_id == "feishu:oc_chat:ou_open"
    assert envelope.attachments == ()


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
        "public_card",
        {
            "chat_id": "oc_chat",
            "card": build_dazah_confirmation_card(_confirmation()),
        },
    )
    assert adapter.calls[1] == (
        "edit",
        {
            "chat_id": "oc_chat",
            "message_id": "om_agent",
            "content": "**分析完成**",
            "finalize": True,
        },
    )


@pytest.mark.asyncio
async def test_native_stream_without_delta_returns_final_for_base_delivery() -> None:
    from services.feishu_gateway_worker import _consume_agent_stream

    adapter = _Adapter()
    completed: list[str] = []
    result = await _consume_agent_stream(
        _events(("finished", {"message": "直接回复"})),
        DazahFeishuGateway(adapter),
        _envelope(),
        on_complete=completed.append,
    )

    assert result == "直接回复"
    assert completed == ["直接回复"]
    assert adapter.calls == []


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
async def test_sse_parser_requires_agent_backend_v2_envelopes() -> None:
    from services.feishu_gateway_worker import _iter_sse_events

    class _Response:
        async def aiter_lines(self) -> Any:
            payload = {
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
