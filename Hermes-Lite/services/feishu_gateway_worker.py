"""Worker that runs the pinned upstream Hermes Feishu adapter unchanged."""

from __future__ import annotations

import asyncio
import base64
import inspect
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
    DazahFeishuGateway,
    DazahInboundEnvelope,
    cleanup_cached_attachments,
    read_cached_attachment,
)
from services.command_help import build_agent_command_help
from services.feishu_runtime import (
    claim_due_deliveries,
    claim_inbound_message,
    complete_delivery,
    complete_inbound_message,
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
AGENT_BACKEND_PROTOCOL_VERSION = "2.0"


def _public_command_response(text: str) -> str | None:
    """Return commands that are safe before local identity resolution."""
    if text.strip().lower() not in {"/help", "/帮助"}:
        return None
    return build_agent_command_help(identity_resolved=False)


def _identity_denial_message(response: httpx.Response) -> str:
    detail = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = str(body.get("detail") or body.get("message") or "")
    except (TypeError, ValueError):
        pass
    normalized = detail.lower()
    if "not the active" in normalized:
        return (
            "当前飞书 App 与 Livzon Agent 后台激活 App 不一致。请管理员前往“系统设置 → "
            "Livzon Agent → 飞书接入”，激活当前 App，或改用已激活 App 后重试。"
        )
    if "inconsistent" in normalized:
        return (
            "当前飞书账号的 user_id/open_id/union_id 绑定发生冲突，系统已拒绝继续。"
            "请管理员在飞书接入中清理重复绑定并重新同步目录。"
        )
    if "not bound" in normalized:
        return (
            "当前飞书账号尚未绑定 Dazah 用户。请管理员先在“系统设置 → Livzon Agent → "
            "飞书接入”确认 App 与租户，再到“身份与准入”同步飞书目录并绑定当前用户；"
            "完成后重新发送命令。"
        )
    if "not active" in normalized:
        return "绑定的 Dazah 用户已停用或删除。请管理员恢复账号，或将飞书身份重新绑定到有效用户。"
    if "group is not admitted" in normalized:
        return (
            "当前飞书群尚未加入 Livzon Agent 群聊白名单。请管理员在“飞书接入”中添加本群，"
            "保存配置后重试。"
        )
    return (
        "飞书身份尚未获得助手准入。请管理员在“系统设置 → Livzon Agent”中核对“飞书接入”"
        "的 App、租户和群聊白名单，并在“身份与准入”检查目录绑定。"
    )


async def _resolve_trusted_subject(
    config: dict[str, Any],
    envelope: DazahInboundEnvelope,
) -> dict[str, Any]:
    base_url = str(config.get("dazah_api_base_url") or "").rstrip("/")
    token = str(config.get("internal_token") or "")
    if not base_url or not token:
        raise RuntimeError("Dazah external identity resolver is not configured")
    private_chat_types = {"dm", "p2p", "private", "direct"}
    is_confirmation_action = _parse_confirmation_action(envelope.text) is not None
    payload = {
        "tenant_id": str(config.get("tenant_id") or "default"),
        "app_fingerprint": str(config["app_id"]),
        # The pinned adapter exposes ``source.user_id`` as tenant user_id when
        # available, otherwise as app-scoped open_id. The envelope classifies
        # the primary value by Feishu's documented ``ou_`` open_id prefix.
        "external_user_id": envelope.sender_user_id or None,
        "external_open_id": envelope.sender_open_id or None,
        "external_union_id": envelope.sender_union_id or None,
        # The pinned upstream adapter currently labels card callbacks from a
        # P2P chat as ``group``. Confirmation ownership is enforced again by
        # the backend against the resolved local user, so valid card actions
        # must not be rejected by an incorrectly inferred group allowlist.
        "chat_id": (
            envelope.chat_id
            if not is_confirmation_action
            and envelope.chat_type.strip().lower() not in private_chat_types
            else None
        ),
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{base_url}/internal/feishu/identity/resolve",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    if response.status_code == 403:
        raise PermissionError(_identity_denial_message(response))
    response.raise_for_status()
    data = response.json()
    subject = data.get("subject") if isinstance(data, dict) else None
    if not isinstance(subject, dict) or not subject.get("user_id"):
        raise RuntimeError("Dazah identity resolver returned an invalid subject")
    return subject


async def _prepare_persistent_conversation(
    config: dict[str, Any],
    *,
    envelope: DazahInboundEnvelope,
    subject: dict[str, Any],
    trace_id: str,
    run_id: str,
) -> dict[str, Any]:
    base_url = str(config.get("dazah_api_base_url") or "").rstrip("/")
    token = str(config.get("internal_token") or "")
    if not base_url or not token:
        raise RuntimeError("Dazah persistent conversation API is not configured")
    persistent_attachments: list[dict[str, Any]] = []
    for item in envelope.attachments:
        attachment: dict[str, Any] = {
            "filename": item.filename,
            "content_type": item.content_type,
            "kind": item.kind,
        }
        try:
            raw = read_cached_attachment(item) or b""
        except OSError:
            raw = b""
        if raw and len(raw) <= 10 * 1024 * 1024:
            attachment["size"] = len(raw)
            attachment["data_base64"] = base64.b64encode(raw).decode("ascii")
        persistent_attachments.append(attachment)

    payload = {
        "subject": subject,
        "peer_id": envelope.session_id,
        "external_message_id": envelope.message_id,
        "message": envelope.request_text,
        "trace_id": trace_id,
        "run_id": run_id,
        "source": {
            "platform": "feishu",
            "sender_user_id": envelope.sender_user_id or None,
            "sender_open_id": envelope.sender_open_id or None,
            "sender_union_id": envelope.sender_union_id or None,
            "chat_id": envelope.chat_id or None,
            "chat_type": envelope.chat_type or None,
            "thread_id": envelope.thread_id or None,
            "reply_to": envelope.reply_to_message_id or None,
            "message_id": envelope.message_id,
        },
        "attachments": persistent_attachments,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{base_url}/agent/internal/feishu/conversations/prepare",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not data.get("session_id"):
        raise RuntimeError("Dazah persistent conversation API returned invalid data")
    return data


async def _complete_persistent_conversation(
    config: dict[str, Any],
    *,
    session_id: str,
    external_message_id: str,
    subject: dict[str, Any],
    trace_id: str,
    run_id: str,
    assistant_message: str,
    memory_notice_delivered: bool = False,
) -> None:
    base_url = str(config.get("dazah_api_base_url") or "").rstrip("/")
    token = str(config.get("internal_token") or "")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{base_url}/agent/internal/feishu/conversations/{session_id}/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "subject": subject,
                "external_message_id": external_message_id,
                "trace_id": trace_id,
                "run_id": run_id,
                "assistant_message": assistant_message,
                "tool_trace": [],
                "memory_notice_delivered": memory_notice_delivered,
            },
        )
    response.raise_for_status()


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


def _confirmation_error_feedback(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code in {409, 410}:
            return "该确认已处理或已过期，未重复执行。"
        if status_code == 403:
            return "确认处理失败：仅原请求人可操作。"
    if isinstance(exc, PermissionError):
        return "确认处理失败：仅原请求人可操作。"
    if isinstance(exc, ValueError) and any(
        marker in str(exc).lower()
        for marker in ("already", "pending", "expired", "handled")
    ):
        return "该确认已处理或已过期，未重复执行。"
    return "确认处理失败，请稍后重试或联系管理员查看 Trace。"


def _trusted_confirmation_owner(subject: dict[str, Any]) -> str:
    owner = str(subject.get("user_id") or "").strip()
    if not owner:
        raise PermissionError("trusted confirmation owner is missing")
    return owner


def _confirmation_result_feedback(result: dict[str, Any], choice: str) -> str:
    envelope = result.get("data")
    if isinstance(envelope, dict):
        result = envelope.get("result") if isinstance(envelope.get("result"), dict) else envelope
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    success_count = data.get("success_count", result.get("success_count"))
    failed_count = data.get("failed_count", result.get("failed_count"))
    if (
        result.get("status") in {"partial", "partial_success"}
        or isinstance(success_count, int)
        and isinstance(failed_count, int)
        and success_count > 0
        and failed_count > 0
    ):
        return (
            f"操作部分成功：成功 {success_count or 0} 项，失败 {failed_count or 0} 项。"
            "系统未自动重试失败项；请发送 `/tasks` 查看进度，核对后再决定是否重试。"
        )
    if choice == "reject" or result.get("status") == "rejected":
        return "操作已拒绝。"
    status_value = str(result.get("status") or "")
    if status_value in {"completed_unverified", "verification_failed"}:
        return "回读验证未通过，系统未将本次操作判定为成功；请先核对目标当前状态，避免重复写入。"
    if result.get("ok") is False or status_value == "failed":
        return "操作执行失败，未产生已验证变更。"
    if status_value == "completed":
        return "操作已确认、执行并完成回读验证。"
    return "操作状态不明确，系统未将本次操作判定为成功；请联系管理员查看 Trace。"


async def _send_confirmation_feedback(
    gateway: DazahFeishuGateway,
    envelope: DazahInboundEnvelope,
    message: str,
) -> None:
    result = await gateway.send(
        envelope.chat_id,
        message,
        reply_to=None,
        metadata={"source": "confirmation_callback"},
    )
    success, _, error = _delivery_result(result)
    if not success:
        logging.getLogger(__name__).warning(
            "Unable to send Feishu confirmation feedback: %s",
            error or "native send returned false",
        )


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
        event.get("protocol_version") != AGENT_BACKEND_PROTOCOL_VERSION
        or not isinstance(event.get("event_id"), str)
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
    on_complete: Callable[[str, bool], Any] | None = None,
) -> str | None:
    accumulated = ""
    sent_message_id: str | None = None
    delivered_partial = False
    last_edit_at = 0.0
    final_message = ""
    confirmations: list[dict[str, Any]] = []
    stream_error = ""
    finished_received = False
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
            finished_received = True
            final_message = str(data.get("message") or accumulated or "Livzon 助手没有生成有效回复。")
            raw_confirmations = data.get("pending_confirmations")
            if isinstance(raw_confirmations, list):
                confirmations = [item for item in raw_confirmations if isinstance(item, dict)]
        elif event_name == "error":
            stream_error = str(data.get("message") or "Livzon Agent 流式响应异常，请稍后重试。")

    if not finished_received and not stream_error:
        stream_error = "Livzon Agent 连接已中断，未收到完整回复，请重试。"
        confirmations = []
    final_content = stream_error or final_message or accumulated
    if not delivered_partial:
        result = await gateway.send(
            envelope.chat_id,
            final_content or "Livzon 助手没有生成有效回复。",
            reply_to=reply_to,
            metadata=metadata,
        )
        delivered, _, _ = _delivery_result(result)
        if on_complete is not None:
            completion = on_complete(final_content, delivered)
            if inspect.isawaitable(completion):
                await completion
        if confirmations:
            await gateway.send_confirmations(envelope.chat_id, confirmations)
        return None if delivered else final_content or "Livzon 助手没有生成有效回复。"

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
                if on_complete is not None:
                    completion = on_complete(final_content, True)
                    if inspect.isawaitable(completion):
                        await completion
                if confirmations:
                    await gateway.send_confirmations(envelope.chat_id, confirmations)
                return None
            if attempt + 1 < final_edit_attempts:
                await asyncio.sleep(0.25 * (2**attempt))
        logging.getLogger(__name__).warning(
            "Final Feishu stream edit failed after %d attempts; "
            "suppressing a second message bubble: %s",
            max(1, final_edit_attempts),
            last_error or "native edit returned false",
        )

    if on_complete is not None:
        completion = on_complete(final_content, False)
        if inspect.isawaitable(completion):
            await completion
    if confirmations:
        await gateway.send_confirmations(envelope.chat_id, confirmations)

    # A partial response is already visible. Sending the full response as a new
    # message when the final edit fails creates an apparent delayed replay.
    return None


async def _deliver_pending(gateway: DazahFeishuGateway) -> int:
    deliveries = claim_due_deliveries()
    for delivery in deliveries:
        try:
            if delivery["delivery_type"] == "card":
                result = await gateway.send_card(delivery["chat_id"], delivery["card"])
                success, message_id, error = _delivery_result(result)
                if success:
                    complete_delivery(delivery["id"], message_id)
                else:
                    fail_delivery(delivery["id"], error or "native card send failed")
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
    async def handle_message(event: Any) -> str | None:
        envelope = DazahInboundEnvelope.from_event(event)
        receipt_key = _inbound_receipt_key(envelope)
        if not claim_inbound_message(receipt_key):
            logging.getLogger(__name__).warning(
                "Suppressed duplicate Feishu inbound message"
            )
            cleanup_cached_attachments(envelope.attachments)
            return None
        try:
            public_response = _public_command_response(envelope.text)
            if public_response is not None:
                return public_response
            try:
                subject = await _resolve_trusted_subject(config_data, envelope)
            except (PermissionError, httpx.HTTPError, RuntimeError) as exc:
                return f"Livzon 助手拒绝访问：{exc}"
            confirmation_owner = _trusted_confirmation_owner(subject)

            text = envelope.text.strip()
            confirmation_action = _parse_confirmation_action(text)
            if confirmation_action is not None:
                confirmation_id, choice, resource_domain = confirmation_action
                try:
                    if resource_domain == "feishu_native":
                        result = await resolve_confirmation(
                            confirmation_id,
                            user_id=confirmation_owner,
                            choice=choice,
                        )
                    else:
                        result = await _resolve_dazah_confirmation(
                            config_data,
                            confirmation_id=confirmation_id,
                            subject=subject,
                            choice=choice,
                        )
                    await _send_confirmation_feedback(
                        gateway,
                        envelope,
                        _confirmation_result_feedback(result, choice),
                    )
                    return None
                except (ValueError, PermissionError, RuntimeError, httpx.HTTPError) as exc:
                    await _send_confirmation_feedback(
                        gateway,
                        envelope,
                        _confirmation_error_feedback(exc),
                    )
                    return None
            command, _, command_arg = text.partition(" ")
            if text == "查看授权":
                grants = list_grants(confirmation_owner)
                return json.dumps({"authorizations": grants}, ensure_ascii=False)
            if command == "撤销授权" and command_arg:
                revoked = revoke_grant(command_arg.strip(), confirmation_owner)
                return "授权已撤销。" if revoked else "未找到可撤销的授权。"

            trace_id = str(uuid.uuid4())
            run_id = str(uuid.uuid4())
            try:
                conversation = await _prepare_persistent_conversation(
                    config_data,
                    envelope=envelope,
                    subject=subject,
                    trace_id=trace_id,
                    run_id=run_id,
                )
            except (httpx.HTTPError, RuntimeError):
                logging.getLogger(__name__).exception(
                    "Failed to prepare persistent Feishu conversation"
                )
                return "Livzon 助手暂时无法恢复会话，请稍后重试。"
            if conversation.get("duplicate"):
                return str(
                    conversation.get("response_text")
                    or "该消息已被 Livzon 助手接收，正在处理中。"
                )
            if conversation.get("response_text"):
                return str(conversation["response_text"])
            persistent_session_id = str(conversation["session_id"])
            persistent_messages = list(conversation.get("messages") or [])
            attachment_catalog = list(conversation.get("attachment_catalog") or [])
            if envelope.reply_to_text and (
                not persistent_messages
                or persistent_messages[-1]
                != {"role": "assistant", "content": envelope.reply_to_text}
            ):
                persistent_messages.append(
                    {"role": "assistant", "content": envelope.reply_to_text}
                )
            payload = envelope.to_agent_backend_v2_request(
                subject=subject,
                trace_id=trace_id,
                run_id=run_id,
                messages=persistent_messages,
                attachment_catalog=attachment_catalog,
                persistent_session_id=persistent_session_id,
                memory_policy=(
                    conversation.get("memory_policy")
                    if isinstance(conversation.get("memory_policy"), dict)
                    else None
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
                        async def persist_response(
                            assistant_message: str,
                            delivered: bool,
                        ) -> None:
                            try:
                                await _complete_persistent_conversation(
                                    config_data,
                                    session_id=persistent_session_id,
                                    external_message_id=envelope.message_id,
                                    subject=subject,
                                    trace_id=trace_id,
                                    run_id=run_id,
                                    assistant_message=assistant_message,
                                    memory_notice_delivered=(
                                        delivered
                                        and bool(
                                            isinstance(conversation.get("memory_policy"), dict)
                                            and conversation["memory_policy"].get("notice_required")
                                        )
                                    ),
                                )
                            except httpx.HTTPError:
                                logging.getLogger(__name__).exception(
                                    "Failed to persist Feishu conversation result"
                                )

                        return await _consume_agent_stream(
                            _iter_sse_events(
                                response,
                                trace_id=str(payload["trace_id"]),
                                run_id=str(payload["run_id"]),
                            ),
                            gateway,
                            envelope,
                            on_complete=persist_response,
                        )
            except (httpx.HTTPError, RuntimeError) as exc:
                logging.getLogger(__name__).exception("Dazah agent stream failed")
                return f"Livzon Agent 流式响应异常：{type(exc).__name__}"
        finally:
            cleanup_cached_attachments(envelope.attachments)
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
