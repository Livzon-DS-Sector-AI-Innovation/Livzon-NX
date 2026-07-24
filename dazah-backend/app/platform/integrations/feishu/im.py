"""Feishu IM message sending."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL

logger = logging.getLogger(__name__)

_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$")
_MARKDOWN_RULE_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^\s)]+)\)")
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\((https?://[^\s)]+)\)")


@dataclass(frozen=True)
class FeishuMessageSendResult:
    ok: bool
    message_id: str | None = None
    code: int | None = None
    error_message: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class FeishuMessageReactionResult:
    ok: bool
    reaction_id: str | None = None
    code: int | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class FeishuBotInfoResult:
    ok: bool
    open_id: str | None = None
    app_name: str | None = None
    code: int | None = None
    error_message: str | None = None


def build_text_message_content(text: str) -> str:
    return json.dumps({"text": text}, ensure_ascii=False)


def normalize_feishu_card_markdown(markdown: str) -> str:
    """Normalize common Markdown into the syntax accepted by Feishu cards.

    Feishu JSON 1.0 cards support only a Markdown subset. Convert common syntax
    that is otherwise shown literally: headings become bold text, standard
    Markdown links become Feishu links, and image syntax degrades to a labelled
    link. Standalone separators are converted to native ``hr`` card elements by
    :func:`_build_feishu_markdown_elements`.
    """
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for line in normalized.split("\n"):
        heading = _MARKDOWN_HEADING_RE.match(line)
        if heading:
            heading_text = heading.group(1).strip()
            line = (
                heading_text
                if heading_text.startswith("**") and heading_text.endswith("**")
                else f"**{heading_text}**"
            )
        elif line.lstrip().startswith("> "):
            line = f"▌ {line.lstrip()[2:]}"
        line = re.sub(r"^(\s*[-*+]\s+)\[x\]\s+", r"\1☑ ", line, flags=re.I)
        line = re.sub(r"^(\s*[-*+]\s+)\[ \]\s+", r"\1☐ ", line)
        line = _MARKDOWN_IMAGE_RE.sub(r"[图片：\1](\2)", line)
        line = _MARKDOWN_LINK_RE.sub(r"<a href='\2'>\1</a>", line)
        lines.append(line)
    return "\n".join(lines)


def _build_feishu_markdown_elements(markdown: str) -> list[dict[str, str]]:
    """Split Markdown into renderable Feishu card components."""
    elements: list[dict[str, str]] = []
    block: list[str] = []

    def flush_block() -> None:
        content = normalize_feishu_card_markdown("\n".join(block)).strip("\n")
        if content:
            elements.append({"tag": "markdown", "content": content})
        block.clear()

    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    for line in normalized.split("\n"):
        if _MARKDOWN_RULE_RE.match(line):
            flush_block()
            if not elements or elements[-1].get("tag") != "hr":
                elements.append({"tag": "hr"})
            continue
        block.append(line)
    flush_block()
    return elements or [{"tag": "markdown", "content": ""}]


def build_markdown_card_content(
    *,
    title: str,
    markdown: str,
    header_template: str = "blue",
) -> str:
    """Build a Feishu interactive card whose body renders Markdown."""
    card: dict[str, Any] = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": header_template,
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": _build_feishu_markdown_elements(markdown),
    }
    return json.dumps(card, ensure_ascii=False)


def build_simple_card_content(
    *,
    title: str,
    markdown: str,
    header_template: str = "blue",
    button_text: str | None = None,
    button_url: str | None = None,
) -> str:
    card = json.loads(
        build_markdown_card_content(
            title=title,
            markdown=markdown,
            header_template=header_template,
        )
    )
    if button_text and button_url:
        card["elements"].append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": button_text},
                        "type": "primary",
                        "url": button_url,
                    }
                ],
            }
        )
    return json.dumps(card, ensure_ascii=False)


def build_callback_card_content(
    *,
    title: str,
    markdown: str,
    actions: list[dict[str, str]],
    header_template: str = "blue",
) -> str:
    card: dict[str, Any] = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": header_template,
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": _build_feishu_markdown_elements(markdown),
    }
    button_actions: list[dict[str, Any]] = []
    for action in actions:
        button_actions.append(
            {
                "tag": "button",
                "text": {
                    "tag": "plain_text",
                    "content": action["label"],
                },
                "type": action.get("button_type") or "primary",
                "value": {
                    "action_id": action["action_id"],
                    "action_key": action["action_key"],
                },
                "confirm": {
                    "title": {"tag": "plain_text", "content": "确认操作"},
                    "text": {
                        "tag": "plain_text",
                        "content": f"确认{action['label']}？",
                    },
                },
            }
        )
    if button_actions:
        card["elements"].append({"tag": "action", "actions": button_actions})
    return json.dumps(card, ensure_ascii=False)


def build_callback_status_card_content(
    *,
    title: str,
    markdown: str,
    status_text: str,
    header_template: str = "green",
) -> str:
    card: dict[str, Any] = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": header_template,
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [
            *_build_feishu_markdown_elements(markdown),
            {"tag": "hr"},
            *_build_feishu_markdown_elements(status_text),
        ],
    }
    return json.dumps(card, ensure_ascii=False)


async def send_feishu_message(
    *,
    tenant_access_token: str,
    receive_id: str,
    msg_type: str,
    content: str,
    receive_id_type: str = "open_id",
) -> FeishuMessageSendResult:
    """Send one Feishu IM message with an explicit tenant access token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{OPEN_API_BASE_URL}/im/v1/messages",
            headers={
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"receive_id_type": receive_id_type},
            json={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content,
            },
        )
        resp.raise_for_status()
        body = resp.json()

    code = body.get("code")
    data = body.get("data") or {}
    if code == 0:
        return FeishuMessageSendResult(
            ok=True,
            message_id=data.get("message_id"),
            code=0,
            raw=body,
        )
    return FeishuMessageSendResult(
        ok=False,
        code=code,
        error_message=body.get("msg") or str(body),
        raw=body,
    )


async def reply_feishu_message(
    *,
    tenant_access_token: str,
    message_id: str,
    msg_type: str,
    content: str,
) -> FeishuMessageSendResult:
    """Reply to one existing Feishu message with an explicit tenant token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{OPEN_API_BASE_URL}/im/v1/messages/{message_id}/reply",
            headers={
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"msg_type": msg_type, "content": content},
        )
        resp.raise_for_status()
        body = resp.json()

    code = body.get("code")
    data = body.get("data") or {}
    if code == 0:
        return FeishuMessageSendResult(
            ok=True,
            message_id=data.get("message_id"),
            code=0,
            raw=body,
        )
    return FeishuMessageSendResult(
        ok=False,
        code=code,
        error_message=body.get("msg") or str(body),
        raw=body,
    )


async def get_feishu_bot_info(
    *,
    tenant_access_token: str,
) -> FeishuBotInfoResult:
    """Return the current application's bot identity."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{OPEN_API_BASE_URL}/bot/v3/info",
            headers={
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        body = resp.json()
        if resp.is_error and body.get("code") is None:
            resp.raise_for_status()

    code = body.get("code")
    if code == 0:
        bot = body.get("bot") or (body.get("data") or {}).get("bot") or {}
        return FeishuBotInfoResult(
            ok=True,
            open_id=bot.get("open_id"),
            app_name=bot.get("app_name") or bot.get("bot_name"),
            code=0,
        )
    return FeishuBotInfoResult(
        ok=False,
        code=code,
        error_message=body.get("msg") or str(body),
    )


async def update_feishu_message(
    *,
    tenant_access_token: str,
    message_id: str,
    content: str,
) -> FeishuMessageSendResult:
    """Update an existing Feishu interactive card message with explicit token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            f"{OPEN_API_BASE_URL}/im/v1/messages/{message_id}",
            headers={
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"content": content},
        )
        resp.raise_for_status()
        body = resp.json()

    code = body.get("code")
    data = body.get("data") or {}
    if code == 0:
        return FeishuMessageSendResult(
            ok=True,
            message_id=data.get("message_id") or message_id,
            code=0,
            raw=body,
        )
    return FeishuMessageSendResult(
        ok=False,
        code=code,
        error_message=body.get("msg") or str(body),
        raw=body,
    )


async def create_feishu_message_reaction(
    *,
    tenant_access_token: str,
    message_id: str,
    emoji_type: str,
) -> FeishuMessageReactionResult:
    """Add a bot reaction to an existing Feishu message."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{OPEN_API_BASE_URL}/im/v1/messages/{message_id}/reactions",
            headers={
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"reaction_type": {"emoji_type": emoji_type}},
        )
        body = resp.json()
        if resp.is_error and body.get("code") is None:
            resp.raise_for_status()

    code = body.get("code")
    data = body.get("data") or {}
    if code == 0:
        reaction = data.get("reaction") or {}
        return FeishuMessageReactionResult(
            ok=True,
            reaction_id=data.get("reaction_id") or reaction.get("reaction_id"),
            code=0,
        )
    return FeishuMessageReactionResult(
        ok=False,
        code=code,
        error_message=body.get("msg") or str(body),
    )


async def delete_feishu_message_reaction(
    *,
    tenant_access_token: str,
    message_id: str,
    reaction_id: str,
) -> FeishuMessageReactionResult:
    """Remove a bot reaction from an existing Feishu message."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(
            (
                f"{OPEN_API_BASE_URL}/im/v1/messages/{message_id}"
                f"/reactions/{reaction_id}"
            ),
            headers={
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        body = resp.json()
        if resp.is_error and body.get("code") is None:
            resp.raise_for_status()

    code = body.get("code")
    if code == 0:
        return FeishuMessageReactionResult(ok=True, code=0)
    return FeishuMessageReactionResult(
        ok=False,
        code=code,
        error_message=body.get("msg") or str(body),
    )


class FeishuIM:
    """Send messages via Feishu IM API."""

    base_url = "https://open.feishu.cn/open-apis"

    def __init__(self, auth: FeishuAuth | None = None) -> None:
        self._auth = auth or FeishuAuth.default()

    async def _batch_get_ids(self, payload: dict) -> dict[str, str]:
        """Internal helper to call batch_get_id and extract open_id mapping."""
        token = await self._auth.get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/contact/v3/users/batch_get_id",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                "Feishu batch_get_id failed: "
                f"code={data.get('code')}, msg={data.get('msg')}"
            )

        result: dict[str, str] = {}
        for item in data.get("data", {}).get("user_list", []):
            open_id = item.get("open_id") or item.get("user_id")
            if not open_id:
                continue
            # Match back by whichever key was in the request
            if "mobiles" in payload:
                key = item.get("mobile")
            elif "emails" in payload:
                key = item.get("email")
            elif "employee_ids" in payload:
                key = item.get("employee_id")
            else:
                key = None
            if key:
                result[key] = open_id
        return result

    async def batch_get_open_ids_by_mobile(self, mobiles: list[str]) -> dict[str, str]:
        """Return mapping mobile -> open_id."""
        return await self._batch_get_ids({"mobiles": mobiles, "include_resigned": True})

    async def batch_get_open_ids_by_email(self, emails: list[str]) -> dict[str, str]:
        """Return mapping email -> open_id."""
        return await self._batch_get_ids({"emails": emails, "include_resigned": True})

    async def batch_get_open_ids_by_employee_id(
        self, employee_ids: list[str]
    ) -> dict[str, str]:
        """Return mapping employee_id -> open_id."""
        return await self._batch_get_ids(
            {"employee_ids": employee_ids, "include_resigned": True}
        )

    async def send_text_message(
        self, receive_id: str, content: str, *, receive_id_type: str = "open_id"
    ) -> None:
        """Send text message to a single user."""
        token = await self._auth.get_token()
        result = await send_feishu_message(
            tenant_access_token=token,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="text",
            content=build_text_message_content(content),
        )
        if not result.ok:
            raise RuntimeError(
                "Feishu send message failed: "
                f"code={result.code}, msg={result.error_message}"
            )
