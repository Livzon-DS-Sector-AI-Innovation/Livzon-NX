"""Dazah extensions around the pinned Hermes native Feishu gateway."""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class FeishuGatewayAdapter(Protocol):
    """Public Hermes adapter surface consumed by the Dazah worker."""

    def set_message_handler(
        self,
        handler: Callable[[Any], Awaitable[str | None]],
    ) -> None: ...

    async def connect(self) -> bool: ...

    async def disconnect(self) -> None: ...

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any: ...

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
        *,
        finalize: bool = False,
    ) -> Any: ...


class ConversationHistoryStore:
    """Bounded, process-local history for AgentBackend V2 Feishu turns."""

    def __init__(self, *, max_sessions: int = 256, max_messages: int = 20) -> None:
        if max_sessions < 1 or max_messages < 1:
            raise ValueError("conversation history limits must be positive")
        self._max_sessions = max_sessions
        self._max_messages = max_messages
        self._sessions: OrderedDict[str, list[dict[str, str]]] = OrderedDict()

    def snapshot(
        self,
        session_id: str,
        *,
        reply_to_text: str = "",
    ) -> list[dict[str, str]]:
        messages = list(self._sessions.get(session_id, []))
        if reply_to_text and (
            not messages
            or messages[-1] != {"role": "assistant", "content": reply_to_text}
        ):
            messages.append({"role": "assistant", "content": reply_to_text})
        return [dict(item) for item in messages[-self._max_messages :]]

    def append_exchange(
        self,
        session_id: str,
        *,
        user_message: str,
        assistant_message: str,
    ) -> None:
        messages = list(self._sessions.pop(session_id, []))
        if user_message:
            messages.append({"role": "user", "content": user_message})
        if assistant_message:
            messages.append({"role": "assistant", "content": assistant_message})
        self._sessions[session_id] = messages[-self._max_messages :]
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)


def _string_attr(value: Any, name: str) -> str:
    return str(getattr(value, name, None) or "")


def _message_type_value(event: Any) -> str:
    message_type = getattr(event, "message_type", None)
    return str(getattr(message_type, "value", message_type) or "text").lower()


def _attachment_kind(message_type: str, content_type: str) -> str:
    if content_type.startswith("image/") or message_type == "photo":
        return "image"
    if content_type.startswith("audio/") or message_type in {"audio", "voice"}:
        return "audio"
    if content_type.startswith("video/") or message_type == "video":
        return "video"
    return "document"


@dataclass(frozen=True)
class DazahGatewayAttachment:
    """Stable attachment metadata after Hermes has cached inbound media."""

    kind: str
    content_type: str
    local_path: str
    filename: str

    def to_request(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "content_type": self.content_type,
            "local_path": self.local_path,
            "filename": self.filename,
        }


@dataclass(frozen=True)
class DazahCardSendResult:
    """Stable send receipt normalized from the pinned private card API."""

    success: bool
    message_id: str | None = None
    error: str | None = None


def cleanup_cached_attachments(
    attachments: tuple[DazahGatewayAttachment, ...],
) -> int:
    """Remove per-message Gateway cache files after processing completes."""
    hermes_home = Path(os.getenv("HERMES_HOME", "/data/hermes")).resolve()
    roots = (
        hermes_home / "cache",
        hermes_home / "image_cache",
        hermes_home / "audio_cache",
        hermes_home / "video_cache",
        hermes_home / "document_cache",
        Path(
            os.getenv(
                "HERMES_FEISHU_FILES_DIR",
                str(hermes_home / "feishu-files"),
            )
        ).resolve(),
    )
    removed = 0
    for attachment in attachments:
        candidate = Path(attachment.local_path).resolve()
        if not candidate.is_file() or not any(
            candidate.is_relative_to(root.resolve()) for root in roots
        ):
            continue
        try:
            candidate.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def read_cached_attachment(
    attachment: DazahGatewayAttachment,
    *,
    max_bytes: int = 10 * 1024 * 1024,
) -> bytes | None:
    """Read only an inbound file located under an approved Hermes cache root."""
    hermes_home = Path(os.getenv("HERMES_HOME", "/data/hermes")).resolve()
    roots = (
        hermes_home / "cache",
        hermes_home / "image_cache",
        hermes_home / "audio_cache",
        hermes_home / "video_cache",
        hermes_home / "document_cache",
        Path(
            os.getenv(
                "HERMES_FEISHU_FILES_DIR",
                str(hermes_home / "feishu-files"),
            )
        ).resolve(),
    )
    candidate = Path(attachment.local_path).resolve()
    if (
        not candidate.is_file()
        or candidate.stat().st_size > max_bytes
        or not any(candidate.is_relative_to(root.resolve()) for root in roots)
    ):
        return None
    return candidate.read_bytes()


@dataclass(frozen=True)
class DazahInboundEnvelope:
    """Stable Dazah view of a Hermes platform-neutral message event."""

    text: str
    message_type: str
    sender_id: str
    sender_primary_id: str
    sender_union_id: str
    sender_name: str
    chat_id: str
    chat_type: str
    thread_id: str
    parent_chat_id: str
    message_id: str
    reply_to_message_id: str
    reply_to_text: str
    attachments: tuple[DazahGatewayAttachment, ...]

    @classmethod
    def from_event(cls, event: Any) -> DazahInboundEnvelope:
        source = getattr(event, "source", None)
        primary_id = _string_attr(source, "user_id")
        union_id = _string_attr(source, "user_id_alt")
        message_type = _message_type_value(event)
        media_paths = list(getattr(event, "media_urls", None) or [])
        media_types = list(getattr(event, "media_types", None) or [])
        attachments = tuple(
            DazahGatewayAttachment(
                kind=_attachment_kind(
                    message_type,
                    str(media_types[index] if index < len(media_types) else ""),
                ),
                content_type=str(media_types[index] if index < len(media_types) else "application/octet-stream"),
                local_path=str(path),
                filename=Path(str(path)).name,
            )
            for index, path in enumerate(media_paths)
        )
        return cls(
            text=str(getattr(event, "text", None) or ""),
            message_type=message_type,
            sender_id=union_id or primary_id,
            sender_primary_id=primary_id,
            sender_union_id=union_id,
            sender_name=_string_attr(source, "user_name"),
            chat_id=_string_attr(source, "chat_id"),
            chat_type=_string_attr(source, "chat_type") or "dm",
            thread_id=_string_attr(source, "thread_id"),
            parent_chat_id=_string_attr(source, "parent_chat_id"),
            message_id=_string_attr(event, "message_id") or _string_attr(source, "message_id"),
            reply_to_message_id=_string_attr(event, "reply_to_message_id"),
            reply_to_text=_string_attr(event, "reply_to_text"),
            attachments=attachments,
        )

    @property
    def sender_open_id(self) -> str:
        return self.sender_primary_id if self.sender_primary_id.startswith("ou_") else ""

    @property
    def sender_user_id(self) -> str:
        return self.sender_primary_id if self.sender_primary_id and not self.sender_open_id else ""

    @property
    def session_id(self) -> str:
        conversation = self.thread_id or self.chat_id
        participant = self.sender_union_id or self.sender_open_id or "unknown"
        return f"feishu:{conversation}:{participant}"

    @property
    def request_text(self) -> str:
        text = self.text.strip()
        if text:
            return text
        if self.attachments:
            return "请分析用户发送的附件并概括主要内容。"
        return "请处理用户发送的飞书消息。"

    def to_agent_backend_v2_request(
        self,
        *,
        subject: dict[str, Any],
        trace_id: str,
        run_id: str,
        messages: list[dict[str, str]] | None = None,
        attachment_catalog: list[dict[str, Any]] | None = None,
        persistent_session_id: str | None = None,
        memory_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "protocol_version": "2.0",
            "run_id": run_id,
            "trace_id": trace_id,
            "session_id": (
                f"feishu:{persistent_session_id}"
                if persistent_session_id
                else self.session_id
            ),
            "subject": subject,
            "source": {
                "platform": "feishu",
                "sender_user_id": self.sender_user_id or None,
                "sender_open_id": self.sender_open_id or None,
                "sender_union_id": self.sender_union_id or None,
                "chat_id": self.chat_id,
                "chat_type": self.chat_type,
                "thread_id": self.thread_id or None,
                "reply_to": self.reply_to_message_id or None,
                "message_id": self.message_id or None,
            },
            "message": self.request_text,
            "messages": list(messages or []),
            "attachments": [attachment.to_request() for attachment in self.attachments],
            "attachment_catalog": list(attachment_catalog or []),
            "client_capabilities": [
                "structured_events",
                "streaming",
                "feishu_rich_text_edit",
                "confirmation_card",
            ],
        }
        if memory_policy is not None:
            payload["memory_policy"] = memory_policy
        return payload


def _confirmation_button(
    confirmation_id: str,
    *,
    label: str,
    choice: str,
    button_type: str,
    resource_domain: str,
) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": button_type,
        "value": {
            "livzon_choice": choice,
            "confirmation_id": confirmation_id,
            "resource_domain": resource_domain,
        },
    }


def _format_beijing_datetime(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "-"
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        beijing = parsed.astimezone(ZoneInfo("Asia/Shanghai"))
    except (ValueError, ZoneInfoNotFoundError):
        return normalized
    return f"{beijing:%Y-%m-%d %H:%M:%S}（北京时间）"


def build_dazah_confirmation_card(confirmation: dict[str, Any]) -> dict[str, Any]:
    """Build the Dazah business-confirmation card carried by Hermes Feishu."""
    confirmation_id = str(confirmation["id"])
    resource_domain = str(confirmation.get("resource_domain") or "dazah_business")
    risk = str(confirmation.get("risk_level") or "medium").lower()
    actions = [
        _confirmation_button(
            confirmation_id,
            label="允许",
            choice="allow",
            button_type="primary",
            resource_domain=resource_domain,
        )
    ]
    if risk == "medium" and resource_domain == "feishu_native":
        actions.append(
            _confirmation_button(
                confirmation_id,
                label="始终允许",
                choice="always",
                button_type="default",
                resource_domain=resource_domain,
            )
        )
    actions.append(
        _confirmation_button(
            confirmation_id,
            label="拒绝",
            choice="reject",
            button_type="danger",
            resource_domain=resource_domain,
        )
    )
    request_payload = confirmation.get("request_payload")
    request_payload = request_payload if isinstance(request_payload, dict) else {}
    summary = str(confirmation.get("summary") or confirmation.get("operation") or "待确认操作")[:500]
    resource = str(
        confirmation.get("resource")
        or request_payload.get("resource")
        or request_payload.get("operation")
        or "Dazah 业务资源"
    )[:300]
    reason = str(
        confirmation.get("reason")
        or request_payload.get("reason")
        or "该操作将修改业务或飞书资源，需要本人确认"
    )[:500]
    impact_count = confirmation.get("impact_count")
    if not isinstance(impact_count, int):
        impact_count = request_payload.get("impact_count")
    if not isinstance(impact_count, int):
        impact_count = 1
    preview = str(confirmation.get("preview") or summary)[:1800]
    if resource_domain == "feishu_native":
        preview_block = f"**变更摘要：**\n{preview}\n"
    else:
        preview_block = f"**关键变更预览：**\n```\n{preview}\n```\n"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"Livzon 操作确认 · {risk.upper()}",
            },
            "template": "red" if risk == "high" else "orange",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**操作摘要：** {summary}\n"
                    f"**文件/资源：** {resource}\n"
                    f"**动作：** {confirmation.get('operation') or '-'}\n"
                    f"**预计影响：** {impact_count} 项\n"
                    f"**风险原因：** {reason}\n"
                    f"{preview_block}"
                    f"**过期时间：** "
                    f"{_format_beijing_datetime(confirmation.get('expires_at'))}"
                ),
            },
            {"tag": "action", "actions": actions},
        ],
    }


class DazahFeishuGateway:
    """Use Hermes public APIs, isolating its missing raw-card extension point."""

    def __init__(self, adapter: FeishuGatewayAdapter) -> None:
        self._adapter = adapter

    def set_message_handler(
        self,
        handler: Callable[[Any], Awaitable[str | None]],
    ) -> None:
        self._adapter.set_message_handler(handler)

    async def connect(self) -> bool:
        return await self._adapter.connect()

    async def disconnect(self) -> None:
        await self._adapter.disconnect()

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Send ordinary content through the native Hermes public API."""
        return await self._adapter.send(
            chat_id,
            content,
            reply_to=reply_to,
            metadata=metadata,
        )

    async def send_card(self, chat_id: str, card: dict[str, Any]) -> Any:
        """Send a native interactive card through the pinned adapter transport."""
        return await self._send_interactive_card(chat_id, card)

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
        *,
        finalize: bool = False,
    ) -> Any:
        """Update a native Feishu text/post message through the public API."""
        return await self._adapter.edit_message(
            chat_id,
            message_id,
            content,
            finalize=finalize,
        )

    async def send_confirmations(
        self,
        chat_id: str,
        confirmations: list[dict[str, Any]],
    ) -> None:
        for confirmation in confirmations:
            await self._send_interactive_card(
                chat_id,
                build_dazah_confirmation_card(confirmation),
            )

    async def _send_interactive_card(
        self,
        chat_id: str,
        card: dict[str, Any],
    ) -> Any:
        public_sender = getattr(self._adapter, "send_interactive_card", None)
        if callable(public_sender):
            return await public_sender(chat_id, card)

        # Hermes v2026.7.7.2 has no public raw-card API. Keep the compatibility
        # dependency in this one contract-tested method until upstream exposes it.
        compat_sender = getattr(self._adapter, "_feishu_send_with_retry", None)
        if not callable(compat_sender):
            raise RuntimeError("pinned Hermes Feishu adapter has no interactive-card transport")
        response = await compat_sender(
            chat_id=chat_id,
            msg_type="interactive",
            payload=json.dumps(card, ensure_ascii=False),
            reply_to=None,
            metadata=None,
        )
        response_succeeded = getattr(self._adapter, "_response_succeeded", None)
        success = (
            bool(response_succeeded(response))
            if callable(response_succeeded)
            else getattr(response, "code", None) == 0
        )
        data = getattr(response, "data", None)
        message_id = str(getattr(data, "message_id", None) or "") or None
        error = None if success else str(getattr(response, "msg", None) or "native card send failed")
        return DazahCardSendResult(
            success=success,
            message_id=message_id,
            error=error,
        )
