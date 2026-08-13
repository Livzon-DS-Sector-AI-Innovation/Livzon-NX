"""Stable cross-module entry points for Livzon Agent capabilities."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.event_service import AgentDomainEventService, DomainEventEnvelope
from app.modules.agent.models import AgentConfirmation, AgentDomainEvent
from app.modules.agent.repository import AgentRepository
from app.modules.agent.schemas import AgentChatRequest, AgentToolExecuteResponse
from app.modules.agent.service import AgentService
from app.platform.identity.models import User


@dataclass(frozen=True)
class FeishuDirectMessageResult:
    text: str
    session_id: UUID | None = None
    pending_confirmations: tuple[Any, ...] = ()
    reset: bool = False


async def publish_domain_event(
    db: AsyncSession, *, envelope: DomainEventEnvelope
) -> AgentDomainEvent:
    return await AgentDomainEventService().publish(db, envelope=envelope)


async def handle_feishu_direct_message(
    db: AsyncSession,
    *,
    user: User,
    sender_open_id: str,
    message_id: str,
    text: str,
    conversation_peer_id: str | None = None,
) -> FeishuDirectMessageResult:
    """Run a Feishu message through a channel-isolated Livzon chat boundary."""
    peer_id = conversation_peer_id or sender_open_id
    normalized = text.strip()
    if normalized.lower() in {
        "/new",
        "/restart",
        "/reset",
        "/新建会话",
    }:
        await AgentRepository().archive_active_channel_sessions(
            db,
            user_id=user.id,
            channel="feishu",
            peer_id=peer_id,
        )
        return FeishuDirectMessageResult(
            text="已开启新对话。请发送你的问题。",
            reset=True,
        )

    await AgentAccessScopeService().get_current_scope(db, user=user)
    repository = AgentRepository()
    session = await repository.get_active_channel_session(
        db,
        user_id=user.id,
        channel="feishu",
        peer_id=peer_id,
    )
    response = await AgentService(get_settings()).chat(
        db,
        request=AgentChatRequest(
            session_id=session.id if session else None,
            message=normalized,
            context={
                "channel": "feishu",
                "peer_id": peer_id,
                "sender_open_id": sender_open_id,
                "feishu_message_id": message_id,
            },
        ),
        current_user=user,
    )
    return FeishuDirectMessageResult(
        text=response.message.content,
        session_id=response.session_id,
        pending_confirmations=tuple(response.pending_confirmations),
    )


async def execute_feishu_confirmation(
    db: AsyncSession,
    *,
    confirmation_id: UUID,
    user: User,
) -> tuple[AgentConfirmation, AgentToolExecuteResponse | None]:
    return await AgentService(get_settings()).execute_confirmation(
        db,
        confirmation_id=confirmation_id,
        current_user=user,
    )


async def cancel_feishu_confirmation(
    db: AsyncSession,
    *,
    confirmation_id: UUID,
    user: User,
) -> AgentConfirmation:
    return await AgentService(get_settings()).cancel_confirmation(
        db,
        confirmation_id=confirmation_id,
        current_user=user,
    )
