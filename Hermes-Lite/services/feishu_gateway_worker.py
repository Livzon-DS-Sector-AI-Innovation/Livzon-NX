"""Worker that runs the pinned upstream Hermes Feishu adapter unchanged."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx

from services.dazah_feishu_gateway import (
    ConversationHistoryStore,
    DazahFeishuGateway,
    DazahInboundEnvelope,
)
from services.feishu_runtime import (
    claim_inbound_message,
    claim_due_deliveries,
    complete_inbound_message,
    complete_delivery,
    fail_delivery,
    list_grants,
    resolve_confirmation,
    revoke_grant,
)

AGENT_BACKEND_V2_EVENT_TYPES = {
    "accepted",
    "thinking",
    "capability_search",
    "tool_call",
    "tool_result",
    "text_delta",
    "confirmation",
    "delivery",
    "error",
    "finished",
    "ping",
}


async def _resolve_trusted_subject(
    config: dict[str, Any],
    envelope: DazahInboundEnvelope,
) -> dict[str, Any]:
    base_url = str(config.get("dazah_api_base_url") or "").rstrip("/")
    token = str(config.get("internal_token") or "")
    if not base_url or not token:
        raise RuntimeError("Dazah external identity resolver is not configured")
    payload = {
        "tenant_id": str(config.get("tenant_id") or "default"),
        "app_fingerprint": str(config["app_id"]),
        "external_user_id": envelope.sender_id or None,
        "external_open_id": envelope.sender_open_id or None,
        "external_union_id": envelope.sender_union_id or None,
        "chat_id": envelope.chat_id if envelope.chat_type != "dm" else None,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{base_url}/internal/feishu/identity/resolve",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    if response.status_code == 403:
        raise PermissionError("飞书身份尚未绑定或未获得助手准入")
    response.raise_for_status()
    data = response.json()
    subject = data.get("subject") if isinstance(data, dict) else None
    if not isinstance(subject, dict) or not subject.get("user_id"):
        raise RuntimeError("Dazah identity resolver returned an invalid subject")
    return subject


async def _resolve_dazah_confirmation(
    config: dict[str, Any],
    *,
    confirmation_id: str,
    subject: dict[str, Any],
    choice: str,
) -> dict[str, Any]:
    if choice == "always":
        raise ValueError("Dazah business confirmations cannot be remembered")
    base_url = str(config.get("dazah_api_base_url") or "").rstrip("/")
    token = str(os.getenv("DAZAH_AGENT_TOOL_TOKEN") or "")
    if not base_url or not token:
        raise RuntimeError("Dazah confirmation resolver is not configured")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{base_url}/agent/confirmations/{confirmation_id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
            json={"subject": subject, "choice": choice},
        )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {"result": data}


def _runtime_upstream_info(upstream: Path) -> dict[str, str]:
    path = upstream / ".dazah-upstream-provenance.json"
    try:
        provenance = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("verified Hermes upstream provenance is unavailable") from exc
    required = ("release_tag", "release_version", "commit_sha")
    if any(not provenance.get(key) for key in required):
        raise RuntimeError("verified Hermes upstream provenance is incomplete")
    return {key: str(provenance[key]) for key in required}


def _parse_confirmation_action(text: str) -> tuple[str, str, str] | None:
    normalized = text.strip()
    if normalized.startswith("/card "):
        try:
            action = json.loads(normalized[normalized.index("{") :])
        except (ValueError, json.JSONDecodeError):
            return None
        choice = action.get("livzon_choice")
        confirmation_id = action.get("confirmation_id")
        resource_domain = str(action.get("resource_domain") or "dazah_business")
        if choice in {"allow", "always", "reject"} and isinstance(confirmation_id, str) and confirmation_id:
            return confirmation_id, str(choice), resource_domain
        return None

    command, _, command_arg = normalized.partition(" ")
    choices = {"允许": "allow", "始终允许": "always", "拒绝": "reject"}
    if command in choices and command_arg.strip():
        return command_arg.strip(), choices[command], "dazah_business"
    return None


def _delivery_result(result: Any) -> tuple[bool, str | None, str]:
    if isinstance(result, bool):
        return result, None, "" if result else "native send returned false"
    success = bool(getattr(result, "success", False))
    message_id = getattr(result, "message_id", None)
    error = str(getattr(result, "error", None) or "")
    return success, str(message_id) if message_id else None, error


def _inbound_receipt_key(envelope: DazahInboundEnvelope) -> str:
    """Keep distinct reaction actions on the same bot message independently idempotent."""
    if envelope.text.startswith("reaction:"):
        return f"{envelope.message_id}:{envelope.text}"
    return envelope.message_id


def _agent_backend_v2_stream_url(agent_url: str) -> str:
    normalized = agent_url.rstrip("/")
    if not normalized.endswith("/v2/agent/runs"):
        raise RuntimeError(
            "agent_url must target AgentBackend V2 (/v2/agent/runs)"
        )
    return f"{normalized}/stream"


def _validate_agent_backend_v2_event(
    event_name: str,
    event: dict[str, Any],
    *,
    last_sequence: int,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> tuple[str, dict[str, Any], int]:
    event_type = event.get("type")
    sequence = event.get("sequence")
    event_data = event.get("data")
    if (
        not isinstance(event.get("event_id"), str)
        or not isinstance(event.get("trace_id"), str)
        or not isinstance(event.get("run_id"), str)
        or not isinstance(event.get("occurred_at"), str)
        or not isinstance(event_type, str)
        or event_type not in AGENT_BACKEND_V2_EVENT_TYPES
        or event_type != event_name
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence <= last_sequence
        or not isinstance(event_data, dict)
        or (trace_id is not None and event["trace_id"] != trace_id)
        or (run_id is not None and event["run_id"] != run_id)
    ):
        raise RuntimeError("agent stream returned an invalid AgentBackend V2 event")
    return event_type, event_data, sequence


async def _iter_sse_events(
    response: httpx.Response,
    *,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    event_name = "message"
    data_lines: list[str] = []
    last_sequence = 0
    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                try:
                    data = json.loads("\n".join(data_lines))
                except json.JSONDecodeError as exc:
                    raise RuntimeError("agent stream returned invalid JSON") from exc
                if not isinstance(data, dict):
                    raise RuntimeError("agent stream event data must be an object")
                _, _, last_sequence = _validate_agent_backend_v2_event(
                    event_name,
                    data,
                    last_sequence=last_sequence,
                    trace_id=trace_id,
                    run_id=run_id,
                )
                yield event_name, data
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as exc:
            raise RuntimeError("agent stream returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("agent stream event data must be an object")
        _validate_agent_backend_v2_event(
            event_name,
            data,
            last_sequence=last_sequence,
            trace_id=trace_id,
            run_id=run_id,
        )
        yield event_name, data


async def _consume_agent_stream(
    events: AsyncIterator[tuple[str, dict[str, Any]]],
    gateway: DazahFeishuGateway,
    envelope: DazahInboundEnvelope,
    *,
    edit_interval_seconds: float = 0.8,
    final_edit_attempts: int = 3,
    on_complete: Callable[[str], None] | None = None,
) -> str | None:
    accumulated = ""
    sent_message_id: str | None = None
    delivered_partial = False
    last_edit_at = 0.0
    final_message = ""
    confirmations: list[dict[str, Any]] = []
    stream_error = ""
    last_sequence = 0
    reply_to = envelope.reply_to_message_id or envelope.message_id or None
    metadata = {"thread_id": envelope.thread_id} if envelope.thread_id else None

    async for event_name, event in events:
        event_name, data, last_sequence = _validate_agent_backend_v2_event(
            event_name,
            event,
            last_sequence=last_sequence,
        )
        if event_name == "text_delta":
            delta = data.get("text")
            if not isinstance(delta, str) or not delta:
                continue
            accumulated += delta
            if not delivered_partial:
                result = await gateway.send(
                    envelope.chat_id,
                    accumulated,
                    reply_to=reply_to,
                    metadata=metadata,
                )
                success, sent_message_id, _ = _delivery_result(result)
                delivered_partial = success
                last_edit_at = time.monotonic()
            elif sent_message_id and time.monotonic() - last_edit_at >= edit_interval_seconds:
                result = await gateway.edit_message(
                    envelope.chat_id,
                    sent_message_id,
                    accumulated,
                )
                success, _, _ = _delivery_result(result)
                if success:
                    last_edit_at = time.monotonic()
        elif event_name == "confirmation":
            confirmations.append(data)
        elif event_name == "finished":
            final_message = str(data.get("message") or accumulated or "Livzon 助手没有生成有效回复。")
            raw_confirmations = data.get("pending_confirmations")
            if isinstance(raw_confirmations, list):
                confirmations = [item for item in raw_confirmations if isinstance(item, dict)]
        elif event_name == "error":
            stream_error = str(data.get("message") or "Livzon Agent 流式响应异常，请稍后重试。")

    final_content = stream_error or final_message or accumulated
    if on_complete is not None:
        on_complete(final_content)
    if confirmations:
        await gateway.send_confirmations(envelope.chat_id, confirmations)
    if not delivered_partial:
        return final_content or "Livzon 助手没有生成有效回复。"

    if sent_message_id:
        last_error = ""
        for attempt in range(max(1, final_edit_attempts)):
            result = await gateway.edit_message(
                envelope.chat_id,
                sent_message_id,
                final_content,
                finalize=True,
            )
            success, _, last_error = _delivery_result(result)
            if success:
                return None
            if attempt + 1 < final_edit_attempts:
                await asyncio.sleep(0.25 * (2**attempt))
        logging.getLogger(__name__).warning(
            "Final Feishu stream edit failed after %d attempts; "
            "suppressing a second message bubble: %s",
            max(1, final_edit_attempts),
            last_error or "native edit returned false",
        )

    # A partial response is already visible. Sending the full response as a new
    # message when the final edit fails creates an apparent delayed replay.
    return None


async def _deliver_pending(gateway: DazahFeishuGateway) -> int:
    deliveries = claim_due_deliveries()
    for delivery in deliveries:
        try:
            if delivery["delivery_type"] == "card":
                await gateway.send_card(delivery["chat_id"], delivery["card"])
                complete_delivery(delivery["id"])
                continue
            result = await gateway.send(
                delivery["chat_id"],
                delivery["content"],
                reply_to=delivery["reply_to"],
                metadata=delivery["metadata"],
            )
            success, message_id, error = _delivery_result(result)
            if success:
                complete_delivery(delivery["id"], message_id)
            else:
                fail_delivery(delivery["id"], error or "native send failed")
        except Exception as exc:
            fail_delivery(delivery["id"], str(exc))
    return len(deliveries)


async def _delivery_loop(gateway: DazahFeishuGateway) -> None:
    while True:
        delivered = await _deliver_pending(gateway)
        await asyncio.sleep(0.2 if delivered else 1)


async def _main() -> None:
    raw = await asyncio.to_thread(sys.stdin.readline)
    config_data = json.loads(raw)
    upstream = Path(os.getenv("HERMES_UPSTREAM_DIR", "/opt/hermes-upstream")).resolve()
    if not (upstream / "plugins/platforms/feishu/adapter.py").is_file():
        raise RuntimeError("pinned Hermes Feishu Gateway source is unavailable")
    upstream_info = _runtime_upstream_info(upstream)
    sys.path.insert(0, str(upstream))

    from gateway.config import PlatformConfig
    from plugins.platforms.feishu.adapter import FeishuAdapter

    # Dazah admission is resolved per inbound message. Feishu native resource
    # authorization remains exclusively enforced by Feishu.
    os.environ["FEISHU_ALLOW_ALL_USERS"] = "true"
    adapter = FeishuAdapter(
        PlatformConfig(
            enabled=True,
            gateway_restart_notification=False,
            typing_indicator=True,
            extra={
                "app_id": config_data["app_id"],
                "app_secret": config_data["app_secret"],
                "transport": "websocket",
                "default_group_policy": "open",
                "require_mention": True,
                "group_sessions_per_user": True,
            },
        )
    )
    gateway = DazahFeishuGateway(adapter)
    conversation_history = ConversationHistoryStore()

    async def handle_message(event: Any) -> str | None:
        envelope = DazahInboundEnvelope.from_event(event)
        receipt_key = _inbound_receipt_key(envelope)
        if not claim_inbound_message(receipt_key):
            logging.getLogger(__name__).warning(
                "Suppressed duplicate Feishu inbound message"
            )
            return None
        sender_id = envelope.sender_id
        try:
            try:
                subject = await _resolve_trusted_subject(config_data, envelope)
            except (PermissionError, httpx.HTTPError, RuntimeError) as exc:
                return f"Livzon 助手拒绝访问：{exc}"

            text = envelope.text.strip()
            confirmation_action = _parse_confirmation_action(text)
            if confirmation_action is not None:
                confirmation_id, choice, resource_domain = confirmation_action
                try:
                    if resource_domain == "feishu_native":
                        result = await resolve_confirmation(
                            confirmation_id,
                            user_id=sender_id,
                            choice=choice,
                        )
                    else:
                        result = await _resolve_dazah_confirmation(
                            config_data,
                            confirmation_id=confirmation_id,
                            subject=subject,
                            choice=choice,
                        )
                    return json.dumps(result, ensure_ascii=False)
                except (ValueError, PermissionError, RuntimeError, httpx.HTTPError) as exc:
                    return f"确认处理失败：{exc}"
            command, _, command_arg = text.partition(" ")
            if text == "查看授权":
                grants = list_grants(sender_id)
                return json.dumps({"authorizations": grants}, ensure_ascii=False)
            if command == "撤销授权" and command_arg:
                revoked = revoke_grant(command_arg.strip(), sender_id)
                return "授权已撤销。" if revoked else "未找到可撤销的授权。"

            payload = envelope.to_agent_backend_v2_request(
                subject=subject,
                trace_id=str(uuid.uuid4()),
                run_id=str(uuid.uuid4()),
                messages=conversation_history.snapshot(
                    envelope.session_id,
                    reply_to_text=envelope.reply_to_text,
                ),
            )
            headers = {}
            if config_data.get("agent_token"):
                headers["Authorization"] = f"Bearer {config_data['agent_token']}"
            agent_url = str(
                config_data.get(
                    "agent_url",
                    "http://127.0.0.1:8100/v2/agent/runs",
                )
            ).rstrip("/")
            timeout = httpx.Timeout(240, read=None)
            try:
                stream_url = _agent_backend_v2_stream_url(agent_url)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        stream_url,
                        headers=headers,
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        return await _consume_agent_stream(
                            _iter_sse_events(
                                response,
                                trace_id=str(payload["trace_id"]),
                                run_id=str(payload["run_id"]),
                            ),
                            gateway,
                            envelope,
                            on_complete=lambda assistant_message: conversation_history.append_exchange(
                                envelope.session_id,
                                user_message=envelope.text,
                                assistant_message=assistant_message,
                            ),
                        )
            except (httpx.HTTPError, RuntimeError) as exc:
                logging.getLogger(__name__).exception("Dazah agent stream failed")
                return f"Livzon Agent 流式响应异常：{type(exc).__name__}"
        finally:
            complete_inbound_message(receipt_key)

    gateway.set_message_handler(handle_message)
    if not await gateway.connect():
        raise RuntimeError("pinned Hermes Feishu Gateway failed to connect")
    print(
        json.dumps({"event": "ready", "upstream": upstream_info}),
        flush=True,
    )
    delivery_task = asyncio.create_task(_delivery_loop(gateway))
    try:
        await asyncio.Event().wait()
    finally:
        delivery_task.cancel()
        await asyncio.gather(delivery_task, return_exceptions=True)
        await gateway.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_main())
