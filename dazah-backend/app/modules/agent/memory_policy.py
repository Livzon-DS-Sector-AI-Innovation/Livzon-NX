from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.platform.audit.models import AuditLog
from app.platform.identity.models import User

from .models import (
    AgentMemoryClearConfirmation,
    AgentMemoryTenantPolicy,
    AgentMemoryUserPreference,
)
from .schemas import AgentMemoryPolicyEnvelope, AgentMemoryTenantPolicyOut

TenantMode = Literal["auto", "explicit_only", "disabled"]
UserMode = Literal["auto", "explicit_only", "paused"]
CommandAction = Literal[
    "status",
    "list",
    "auto",
    "explicit",
    "pause",
    "resume",
    "forget",
    "clear",
    "clear_confirm",
    "help",
]

_MODE_RANK = {"disabled": 0, "paused": 0, "explicit_only": 1, "auto": 2}
_MODE_LABELS = {
    "auto": "自动记忆",
    "explicit_only": "仅显式记忆",
    "paused": "已暂停",
    "disabled": "已禁用",
}
_PRIVATE_CHAT_TYPES = {"dm", "p2p", "private", "direct"}
logger = logging.getLogger(__name__)


def anonymous_scope_ref(tenant_id: str, user_id: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{user_id}".encode()).hexdigest()[:16]


def memory_command_help_text() -> str:
    return (
        "个人长期记忆命令（仅 Web 或飞书私聊）：\n"
        "- `/memory status`：查看个人选择、租户限制和当前实际模式\n"
        "- `/memory`：查看个人长期记忆\n"
        "- `/memory auto`：开启自动记忆\n"
        "- `/memory explicit`：仅在明确要求时记忆\n"
        "- `/memory pause`：暂停记忆，保留已有数据\n"
        "- `/memory resume`：恢复暂停前的模式\n"
        "- `/memory forget <关键词>`：删除唯一匹配的记忆\n"
        "- `/memory clear`：发起五分钟有效的全部清空确认\n"
        "- `/memory clear confirm`：确认并执行全部清空\n"
        "- `/memory help`：查看本说明\n"
        "群聊不读取或修改个人记忆。"
    )


@dataclass(frozen=True)
class MemoryCommand:
    action: CommandAction
    argument: str | None = None


def parse_memory_command(message: str) -> MemoryCommand | None:
    raw = re.sub(r"\s+", " ", message.strip())
    lowered = raw.casefold()
    slash_commands: dict[str, CommandAction] = {
        "/memory": "list",
        "/memory status": "status",
        "/memory auto": "auto",
        "/memory explicit": "explicit",
        "/memory pause": "pause",
        "/memory resume": "resume",
        "/memory clear": "clear",
        "/memory clear confirm": "clear_confirm",
        "/memory help": "help",
    }
    if lowered in slash_commands:
        return MemoryCommand(slash_commands[lowered])
    if lowered.startswith("/memory forget "):
        argument = raw[len("/memory forget ") :].strip()
        return MemoryCommand("forget", argument or None)
    if lowered.startswith("/memory"):
        return MemoryCommand("help")

    compact = re.sub(r"\s+", "", raw).rstrip("。！？?!")
    exact: dict[str, CommandAction] = {
        "你记得什么": "list",
        "你记住了什么": "list",
        "查看我的记忆": "list",
        "查看记忆状态": "status",
        "开启自动记忆": "auto",
        "打开自动记忆": "auto",
        "只在我明确要求时记忆": "explicit",
        "只在我说记住时记忆": "explicit",
        "暂停记忆": "pause",
        "关闭记忆": "pause",
        "恢复记忆": "resume",
        "清空我的记忆": "clear",
        "消除我的记忆": "clear",
        "确认清空记忆": "clear_confirm",
        "记忆帮助": "help",
    }
    if compact in exact:
        return MemoryCommand(exact[compact])
    match = re.fullmatch(r"(?:请)?(?:你)?忘记(?:关于)?[：:]?(.+)", compact)
    if match and match.group(1).strip():
        return MemoryCommand("forget", match.group(1).strip())
    return None


def is_private_memory_channel(*, platform: str, chat_type: str | None = None) -> bool:
    return (
        platform == "web" or str(chat_type or "").strip().lower() in _PRIVATE_CHAT_TYPES
    )


def policy_limitation_sources(
    *, global_mode: str, tenant_mode: str, user_mode: str
) -> list[str]:
    """Return the trusted upstream levels that make the user's choice stricter."""
    user_rank = _MODE_RANK[user_mode]
    upstream = (
        ("全局策略", global_mode),
        ("租户策略", tenant_mode),
    )
    strictest_rank = min(_MODE_RANK[mode] for _, mode in upstream)
    if strictest_rank >= user_rank:
        return []
    return [label for label, mode in upstream if _MODE_RANK[mode] == strictest_rank]


class AgentMemoryPolicyService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    async def _tenant_row(
        db: AsyncSession, tenant_id: str
    ) -> AgentMemoryTenantPolicy | None:
        return cast(
            AgentMemoryTenantPolicy | None,
            await db.scalar(
                select(AgentMemoryTenantPolicy).where(
                    AgentMemoryTenantPolicy.tenant_id == tenant_id,
                    AgentMemoryTenantPolicy.is_deleted.is_(False),
                )
            ),
        )

    @staticmethod
    async def _preference_row(
        db: AsyncSession, tenant_id: str, user_id: UUID
    ) -> AgentMemoryUserPreference | None:
        return cast(
            AgentMemoryUserPreference | None,
            await db.scalar(
                select(AgentMemoryUserPreference).where(
                    AgentMemoryUserPreference.tenant_id == tenant_id,
                    AgentMemoryUserPreference.user_id == user_id,
                    AgentMemoryUserPreference.is_deleted.is_(False),
                )
            ),
        )

    async def _preference(
        self, db: AsyncSession, user: User
    ) -> AgentMemoryUserPreference:
        tenant_id = getattr(user, "tenant_key", None) or "default"
        row = await self._preference_row(db, tenant_id, user.id)
        if row is None:
            row = AgentMemoryUserPreference(
                tenant_id=tenant_id,
                user_id=user.id,
                mode="auto",
                preference_version=1,
                notice_sent_version=0,
                created_by=user.id,
                updated_by=user.id,
            )
            db.add(row)
            await db.flush()
        return row

    async def resolve(
        self,
        db: AsyncSession,
        *,
        user: User,
    ) -> AgentMemoryPolicyEnvelope:
        tenant_id = getattr(user, "tenant_key", None) or "default"
        tenant = await self._tenant_row(db, tenant_id)
        preference = await self._preference(db, user)
        global_mode = getattr(self.settings, "AGENT_USER_MEMORY_MODE", "auto")
        tenant_mode = tenant.mode if tenant else "auto"
        effective = min(
            (global_mode, tenant_mode, preference.mode),
            key=lambda mode: _MODE_RANK[mode],
        )
        if effective == "paused":
            effective = "disabled"
        notice_version = max(
            1, getattr(self.settings, "AGENT_USER_MEMORY_NOTICE_VERSION", 1)
        )
        notice_required = preference.notice_sent_version < notice_version
        tenant_version = tenant.policy_version if tenant else 1
        policy_version = (
            tenant_version * 1_000_000
            + preference.preference_version * 10
            + _MODE_RANK[global_mode]
        )
        return AgentMemoryPolicyEnvelope(
            effective_mode=effective,
            policy_version=policy_version,
            notice_required=notice_required,
            last_cleared_at=preference.last_cleared_at,
        )

    async def mark_notice_sent(self, db: AsyncSession, *, user: User) -> bool:
        """Persist privacy-notice delivery only after the channel confirms it."""
        preference = await self._preference(db, user)
        notice_version = max(
            1, getattr(self.settings, "AGENT_USER_MEMORY_NOTICE_VERSION", 1)
        )
        if preference.notice_sent_version >= notice_version:
            return False
        preference.notice_sent_version = notice_version
        preference.preference_version += 1
        preference.updated_by = user.id
        await db.flush()
        return True

    async def tenant_policy(
        self, db: AsyncSession, *, tenant_id: str
    ) -> AgentMemoryTenantPolicyOut:
        row = await self._tenant_row(db, tenant_id)
        tenant_mode = cast(TenantMode, row.mode if row else "auto")
        global_mode = getattr(self.settings, "AGENT_USER_MEMORY_MODE", "auto")
        effective = min((global_mode, tenant_mode), key=lambda mode: _MODE_RANK[mode])
        return AgentMemoryTenantPolicyOut(
            tenant_id=tenant_id,
            global_mode=global_mode,
            tenant_mode=tenant_mode,
            effective_mode=effective,
            policy_version=row.policy_version if row else 1,
        )

    async def update_tenant_policy(
        self,
        db: AsyncSession,
        *,
        user: User,
        mode: TenantMode,
    ) -> AgentMemoryTenantPolicyOut:
        tenant_id = getattr(user, "tenant_key", None) or "default"
        row = await self._tenant_row(db, tenant_id)
        previous_mode: TenantMode = cast(TenantMode, row.mode if row else "auto")
        if _MODE_RANK[mode] > _MODE_RANK[previous_mode]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "租户记忆策略只能收紧，不能通过管理页面放宽",
            )
        if row is None:
            row = AgentMemoryTenantPolicy(
                tenant_id=tenant_id,
                mode=mode,
                policy_version=1,
                created_by=user.id,
                updated_by=user.id,
            )
            db.add(row)
        elif row.mode != mode:
            row.mode = mode
            row.policy_version += 1
            row.updated_by = user.id
        db.add(
            AuditLog(
                user_id=user.id,
                method="PUT",
                path="/api/v1/agent/memory/tenant-policy",
                status_code=200,
                resource_type="agent_memory_tenant_policy",
                resource_id=row.id,
                action="update",
                old_value={"mode": previous_mode},
                new_value={"mode": mode},
            )
        )
        await db.flush()
        return await self.tenant_policy(db, tenant_id=tenant_id)

    async def _hermes_control(
        self,
        *,
        tenant_id: str,
        user_id: str,
        action: Literal["list", "forget", "clear"],
        argument: str | None = None,
        cleared_at: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not self.settings.HERMES_INTERNAL_URL
            or not self.settings.HERMES_INTERNAL_TOKEN
        ):
            raise RuntimeError("Hermes 记忆控制接口未配置")
        payload = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action": action,
            "argument": argument,
            "cleared_at": cleared_at.isoformat() if cleared_at else None,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.settings.HERMES_INTERNAL_URL.rstrip('/')}/internal/user-memory/control",
                headers={
                    "Authorization": f"Bearer {self.settings.HERMES_INTERNAL_TOKEN}"
                },
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Hermes 记忆控制接口返回无效数据")
        return data

    async def handle_command(
        self,
        db: AsyncSession,
        *,
        user: User,
        message: str,
        private_channel: bool,
    ) -> str | None:
        command = parse_memory_command(message)
        if command is None:
            return None
        if not private_channel:
            return (
                "为保护个人隐私，群聊不读取或修改个人记忆。请在 Web 或飞书私聊中操作。"
            )

        preference = await self._preference(db, user)
        tenant_id = getattr(user, "tenant_key", None) or "default"
        if command.action == "help":
            return memory_command_help_text()
        if command.action == "status":
            policy = await self.resolve(db, user=user)
            tenant = await self.tenant_policy(db, tenant_id=tenant_id)
            sources = policy_limitation_sources(
                global_mode=tenant.global_mode,
                tenant_mode=tenant.tenant_mode,
                user_mode=preference.mode,
            )
            source_text = "、".join(sources) if sources else "个人选择"
            return (
                f"你的记忆模式：{_MODE_LABELS[preference.mode]}；"
                f"全局上限：{_MODE_LABELS[tenant.global_mode]}；"
                f"租户上限：{_MODE_LABELS[tenant.tenant_mode]}；"
                f"当前实际模式：{_MODE_LABELS[policy.effective_mode]}；"
                f"生效来源：{source_text}。"
            )
        if command.action in {"auto", "explicit", "pause", "resume"}:
            if command.action == "pause":
                if preference.mode != "paused":
                    preference.mode_before_pause = preference.mode
                preference.mode = "paused"
            elif command.action == "resume":
                preference.mode = preference.mode_before_pause or "auto"
                preference.mode_before_pause = None
            else:
                preference.mode = (
                    "auto" if command.action == "auto" else "explicit_only"
                )
                preference.mode_before_pause = None
            preference.preference_version += 1
            preference.updated_by = user.id
            await db.flush()
            policy = await self.resolve(db, user=user)
            tenant = await self.tenant_policy(db, tenant_id=tenant_id)
            sources = policy_limitation_sources(
                global_mode=tenant.global_mode,
                tenant_mode=tenant.tenant_mode,
                user_mode=preference.mode,
            )
            suffix = (
                ""
                if not sources
                else (
                    f"受{'、'.join(sources)}限制，当前实际模式为"
                    f"{_MODE_LABELS[policy.effective_mode]}。"
                )
            )
            return f"已将你的记忆模式设置为{_MODE_LABELS[preference.mode]}。{suffix}"
        if command.action == "clear":
            expires_at = datetime.now(UTC) + timedelta(minutes=5)
            confirmation = await db.scalar(
                select(AgentMemoryClearConfirmation).where(
                    AgentMemoryClearConfirmation.tenant_id == tenant_id,
                    AgentMemoryClearConfirmation.user_id == user.id,
                    AgentMemoryClearConfirmation.is_deleted.is_(False),
                )
            )
            if confirmation is None:
                confirmation = AgentMemoryClearConfirmation(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    expires_at=expires_at,
                    created_by=user.id,
                    updated_by=user.id,
                )
                db.add(confirmation)
            else:
                confirmation.expires_at = expires_at
                confirmation.updated_by = user.id
            await db.flush()
            return (
                "这将删除你的全部在线长期记忆。灾备副本将在最长30天内随备份轮转清除。"
                "如确认，请在5分钟内发送 `/memory clear confirm`。"
            )
        if command.action == "clear_confirm":
            confirmation = await db.scalar(
                select(AgentMemoryClearConfirmation).where(
                    AgentMemoryClearConfirmation.tenant_id == tenant_id,
                    AgentMemoryClearConfirmation.user_id == user.id,
                    AgentMemoryClearConfirmation.is_deleted.is_(False),
                )
            )
            if confirmation is None or confirmation.expires_at <= datetime.now(UTC):
                return "清空确认不存在或已过期。请重新发送 `/memory clear`。"
            cleared_at = datetime.now(UTC)
            preference.last_cleared_at = cleared_at
            preference.preference_version += 1
            preference.updated_by = user.id
            confirmation.is_deleted = True
            confirmation.updated_by = user.id
            await db.commit()
            try:
                await self._hermes_control(
                    tenant_id=tenant_id,
                    user_id=str(user.id),
                    action="clear",
                    cleared_at=cleared_at,
                )
            except (RuntimeError, httpx.HTTPError) as exc:
                logger.error(
                    "agent_memory_clear_pending scope_ref=%s error_type=%s",
                    anonymous_scope_ref(tenant_id, str(user.id)),
                    type(exc).__name__,
                )
                return (
                    "已登记清空并停止使用旧记忆；Hermes 在线副本暂未确认清除，"
                    "服务恢复后会根据删除时间标记继续清理。"
                )
            return "在线长期记忆已清空且不再用于回答；灾备副本将在最长30天内清除。"
        if command.action == "forget" and not command.argument:
            return "请提供要忘记的关键词，例如：`/memory forget 表格输出`。"
        try:
            result = await self._hermes_control(
                tenant_id=tenant_id,
                user_id=str(user.id),
                action="forget" if command.action == "forget" else "list",
                argument=command.argument,
            )
        except (RuntimeError, httpx.HTTPError):
            return "记忆服务暂时不可用，请稍后重试。"
        if command.action == "forget":
            if result.get("removed"):
                return "已删除唯一匹配的记忆。"
            matches = (
                result.get("items") if isinstance(result.get("items"), list) else []
            )
            if not matches:
                return "没有找到匹配的记忆。"
            return "匹配到多条记忆，为避免误删，本次未执行。请使用更具体的关键词。"
        items = result.get("items") if isinstance(result.get("items"), list) else []
        if not items:
            return "目前没有保存任何长期记忆。"
        lines = ["我保存的长期记忆："]
        for item in items[:50]:
            lines.append(
                f"- 【{item.get('category_label', '其他')}】{item.get('content', '')}"
            )
        return "\n".join(lines)


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
