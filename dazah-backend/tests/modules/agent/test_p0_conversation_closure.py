import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.service import AgentService
from app.platform.identity.models import User

SimpleNamespace: Any = _SimpleNamespace


@pytest.mark.anyio
async def test_user_can_restore_own_session_with_confirmation_state(
    db_session: AsyncSession,
) -> None:
    user = User(
        name="Livzon P0 用户",
        username=f"livzon-p0-{uuid.uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="local",
    )
    db_session.add(user)
    await db_session.flush()
    service = AgentService(settings=SimpleNamespace())
    session = await service.repo.create_session(
        db_session,
        user_id=user.id,
        context={"channel": "web"},
        title="查询偏差并创建跟踪",
    )
    await service.repo.add_message(
        db_session,
        session_id=session.id,
        role="user",
        content="查询未关闭偏差",
        user_id=user.id,
    )
    await service.repo.add_message(
        db_session,
        session_id=session.id,
        role="assistant",
        content="发现 2 条未关闭偏差",
        metadata={"evidence": {"sources": [{"operation": "quality.list_deviations"}]}},
        user_id=user.id,
    )
    confirmation = await service.repo.create_confirmation(
        db_session,
        session_id=session.id,
        user_id=user.id,
        operation="quality.create_capa",
        summary="创建 CAPA 跟踪",
        risk_level="medium",
        request_payload={"body": {"deviation_id": "DEV-1"}},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    expired_confirmation = await service.repo.create_confirmation(
        db_session,
        session_id=session.id,
        user_id=user.id,
        operation="identity.deliver_feishu_message",
        summary="已过期的飞书投递",
        risk_level="medium",
        request_payload={"body": {"message": "不会发送"}},
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    detail = await service.get_session_detail(
        db_session, session_id=session.id, current_user=user
    )

    assert [message.role for message in detail.messages] == ["user", "assistant"]
    assert detail.confirmations[0].id == confirmation.id
    assert detail.confirmations[0].status == "pending"
    assert detail.confirmations[1].id == expired_confirmation.id
    assert detail.confirmations[1].status == "expired"
    assert detail.session.pending_confirmation_count == 1

    page = await service.list_sessions(
        db_session, current_user=user, page=1, page_size=20
    )
    assert page.total == 1
    assert page.items[0].last_message_preview == "发现 2 条未关闭偏差"
