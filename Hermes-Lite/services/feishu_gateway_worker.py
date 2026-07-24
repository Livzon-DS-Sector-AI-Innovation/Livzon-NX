"""Worker that runs the pinned upstream Hermes Feishu adapter unchanged."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx

from services.feishu_runtime import (
    authorize,
    is_group_allowed,
    list_grants,
    resolve_confirmation,
    revoke_grant,
)


async def _main() -> None:
    raw = await asyncio.to_thread(sys.stdin.readline)
    config_data = json.loads(raw)
    upstream = Path(
        os.getenv("HERMES_UPSTREAM_DIR", "/opt/hermes-upstream")
    ).resolve()
    if not (upstream / "plugins/platforms/feishu/adapter.py").is_file():
        raise RuntimeError("pinned Hermes Feishu Gateway source is unavailable")
    sys.path.insert(0, str(upstream))

    from gateway.config import PlatformConfig
    from plugins.platforms.feishu.adapter import FeishuAdapter

    # Admission is enforced against the local versioned snapshot in the
    # handler. The upstream adapter still enforces group @mention gating,
    # sender/card checks, deduplication and per-chat serialization.
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

    async def send_confirmation_card(
        chat_id: str, confirmations: list[dict[str, Any]]
    ) -> None:
        for confirmation in confirmations:
            risk = str(confirmation.get("risk_level") or "medium")

            def button(label: str, choice: str, button_type: str) -> dict[str, Any]:
                return {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": label},
                    "type": button_type,
                    "value": {
                        "livzon_choice": choice,
                        "confirmation_id": confirmation["id"],
                    },
                }

            actions = [button("允许", "allow", "primary")]
            if risk == "medium":
                actions.append(button("始终允许", "always", "default"))
            actions.append(button("拒绝", "reject", "danger"))
            card = {
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
                            f"**文件/资源：** {confirmation.get('resource') or '-'}\n"
                            f"**动作：** {confirmation.get('operation') or '-'}\n"
                            f"**影响数量：** {confirmation.get('impact_count') or 0}\n"
                            f"**风险原因：** {confirmation.get('reason') or '-'}\n"
                            f"**关键变更预览：**\n```\n"
                            f"{str(confirmation.get('preview') or '-')[:1800]}\n```\n"
                            f"**过期时间：** {confirmation.get('expires_at') or '-'}"
                        ),
                    },
                    {"tag": "action", "actions": actions},
                ],
            }
            await adapter._feishu_send_with_retry(
                chat_id=chat_id,
                msg_type="interactive",
                payload=json.dumps(card, ensure_ascii=False),
                reply_to=None,
                metadata=None,
            )

    async def handle_message(event: Any) -> str:
        source = event.source
        sender_id = str(
            getattr(source, "user_id_alt", None)
            or getattr(source, "user_id", None)
            or ""
        )
        chat_id = str(getattr(source, "chat_id", "") or "")
        chat_type = str(getattr(source, "chat_type", "") or "")
        write_capable = False
        try:
            authorize(sender_id, write=write_capable, enforce_scope=False)
            if chat_type != "dm" and not is_group_allowed(chat_id):
                return "该群未在 Livzon 助手后台白名单中登记。"
        except PermissionError as exc:
            return f"Livzon 助手拒绝访问：{exc}"

        text = str(event.text or "").strip()
        if text.startswith("/card "):
            try:
                action = json.loads(text[text.index("{") :])
            except (ValueError, json.JSONDecodeError):
                action = {}
            if action.get("livzon_choice") and action.get("confirmation_id"):
                try:
                    result = await resolve_confirmation(
                        str(action["confirmation_id"]),
                        user_id=sender_id,
                        choice=str(action["livzon_choice"]),
                    )
                    return json.dumps(result, ensure_ascii=False)
                except (ValueError, PermissionError, RuntimeError) as exc:
                    return f"确认处理失败：{exc}"
        command, _, command_arg = text.partition(" ")
        choices = {"允许": "allow", "始终允许": "always", "拒绝": "reject"}
        if command in choices and command_arg:
            try:
                result = await resolve_confirmation(
                    command_arg.strip(),
                    user_id=sender_id,
                    choice=choices[command],
                )
                return json.dumps(result, ensure_ascii=False)
            except (ValueError, PermissionError, RuntimeError) as exc:
                return f"确认处理失败：{exc}"
        if text == "查看授权":
            grants = list_grants(sender_id)
            return json.dumps({"authorizations": grants}, ensure_ascii=False)
        if command == "撤销授权" and command_arg:
            revoked = revoke_grant(command_arg.strip(), sender_id)
            return "授权已撤销。" if revoked else "未找到可撤销的授权。"

        context = {
            "user_id": sender_id,
            "feishu_sender_id": sender_id,
            "feishu_chat_id": chat_id,
            "feishu_chat_type": chat_type,
            "feishu_message_id": getattr(event, "message_id", None),
            "channel": "feishu",
        }
        session_participant = str(
            getattr(source, "user_id_alt", None)
            or getattr(source, "user_id", None)
            or "unknown"
        )
        payload = {
            "session_id": f"feishu:{chat_id}:{session_participant}",
            "message": event.text,
            "messages": [],
            "context": context,
            "attachments": [],
        }
        headers = {}
        if config_data.get("agent_token"):
            headers["Authorization"] = f"Bearer {config_data['agent_token']}"
        async with httpx.AsyncClient(timeout=240) as client:
            response = await client.post(
                config_data.get("agent_url", "http://127.0.0.1:8100/v1/chat"),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        response_data = response.json()
        confirmations = response_data.get("pending_confirmations") or []
        if confirmations:
            await send_confirmation_card(chat_id, confirmations)
        return str(response_data.get("message") or "Livzon 助手没有生成有效回复。")

    adapter.set_message_handler(handle_message)
    if not await adapter.connect():
        raise RuntimeError("pinned Hermes Feishu Gateway failed to connect")
    try:
        await asyncio.Event().wait()
    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_main())
