"""生产看板个人偏好端点测试（按账户持久化口径切换与标签后缀）。

HTTP 层：真实路由 + mock 会话；认证：override get_current_user。
覆盖：GET 默认值（无记录）、POST 新建、POST 更新已存在记录、
后缀 strip 归一与长度上限 422。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.modules.production.board_preferences_models import (
    ProductionUserBoardPreference,
)
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

API = "/api/v1/production/board-preferences"


def _row(avg_pilot_incl: bool, avg_note: str) -> ProductionUserBoardPreference:
    return ProductionUserBoardPreference(
        user_id=uuid4(), avg_pilot_incl=avg_pilot_incl, avg_note=avg_note
    )


def _result(row: ProductionUserBoardPreference | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    return result


@pytest.fixture
async def pref_client() -> AsyncIterator[tuple[AsyncClient, AsyncMock]]:
    user = User(
        id=uuid4(),
        name="看板偏好测试",
        username="board-pref-admin",
        role="admin",
        status="active",
        auth_source="local",
    )

    async def _override_user() -> User:
        return user

    db = AsyncMock(spec=AsyncSession)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, db
    app.dependency_overrides.clear()


async def test_get_returns_defaults_when_no_record(
    pref_client: tuple[AsyncClient, AsyncMock],
) -> None:
    """首次登录无记录：返回默认（含中试 + 后缀「含中试」）。"""
    ac, db = pref_client
    db.execute = AsyncMock(side_effect=[_result(None)])
    res = await ac.get(API)
    assert res.status_code == 200
    assert res.json()["data"] == {"avg_pilot_incl": True, "avg_note": "含中试"}


async def test_get_returns_saved_preference(
    pref_client: tuple[AsyncClient, AsyncMock],
) -> None:
    """已有记录：返回该账户持久化的口径与后缀。"""
    ac, db = pref_client
    db.execute = AsyncMock(side_effect=[_result(_row(False, "大罐口径"))])
    res = await ac.get(API)
    assert res.status_code == 200
    assert res.json()["data"] == {"avg_pilot_incl": False, "avg_note": "大罐口径"}


async def test_post_inserts_new_preference(
    pref_client: tuple[AsyncClient, AsyncMock],
) -> None:
    """无记录时 POST 新建：后缀 strip 归一，add+commit+refresh 依序执行。"""
    ac, db = pref_client
    db.execute = AsyncMock(side_effect=[_result(None)])
    res = await ac.post(
        API, json={"avg_pilot_incl": False, "avg_note": "  大罐口径  "}
    )
    assert res.status_code == 200
    assert res.json()["data"] == {"avg_pilot_incl": False, "avg_note": "大罐口径"}
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert isinstance(added, ProductionUserBoardPreference)
    assert added.avg_pilot_incl is False
    assert added.avg_note == "大罐口径"
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()


async def test_post_updates_existing_preference(
    pref_client: tuple[AsyncClient, AsyncMock],
) -> None:
    """已有记录时 POST 原位更新：不新增行，空串后缀允许（=无后缀）。"""
    ac, db = pref_client
    existing = _row(True, "含中试")
    db.execute = AsyncMock(side_effect=[_result(existing)])
    res = await ac.post(API, json={"avg_pilot_incl": False, "avg_note": ""})
    assert res.status_code == 200
    assert res.json()["data"] == {"avg_pilot_incl": False, "avg_note": ""}
    assert existing.avg_pilot_incl is False
    assert existing.avg_note == ""
    db.add.assert_not_called()
    db.commit.assert_awaited_once()


async def test_post_rejects_overlong_note(
    pref_client: tuple[AsyncClient, AsyncMock],
) -> None:
    """后缀超过 64 字：422 校验失败，不触碰数据库。"""
    ac, db = pref_client
    res = await ac.post(API, json={"avg_pilot_incl": True, "avg_note": "长" * 65})
    assert res.status_code == 422
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
