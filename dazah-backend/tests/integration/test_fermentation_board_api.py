"""发酵车间看板端点集成测试。

- HTTP 层：真实路由；服务层 DB 调用 mock（conftest 共享回滚会话不承载
  真实查询，任何事务都会在其 teardown 触发跨事件循环错误）。
- 真库冒烟：测试体内自建会话走检修 CRUD 与看板加载。

认证：override get_current_user 提供内存管理员。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.main import app
from app.modules.production import fermentation_board_service as board
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

API = "/api/v1/production"


def _fake_maintenance(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "tank_no": "302A",
        "reason": "滤芯更换",
        "started_at": "2026-09-08T08:00:00",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def mock_db_service(monkeypatch: Any) -> None:
    """HTTP 层不触碰数据库。"""
    monkeypatch.setattr(
        board,
        "load_latest_archive",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(board, "list_active_maintenance", AsyncMock(return_value=[]))
    monkeypatch.setattr(board, "upsert_maintenance", AsyncMock())
    monkeypatch.setattr(board, "delete_maintenance", AsyncMock())
    monkeypatch.setattr(board, "get_maintenance", AsyncMock(return_value=None))


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    async def _override_current_user() -> User:
        return User(
            id=uuid.uuid4(),
            name="看板测试用户",
            username=f"board-test-{uuid.uuid4().hex[:10]}",
            role="admin",
            status="active",
            auth_source="local",
            grant_version=0,
        )

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_board_returns_no_archive_message(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    response = await auth_client.get(f"{API}/fermentation-board")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"] is None
    assert "排产" in body["message"]


@pytest.mark.anyio
async def test_board_builds_payload_from_latest_archive(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    fake_payload = {
        "now": "2026-09-08T12:00:00",
        "period": {
            "start": "2026-08-27",
            "end": "2026-09-26",
            "label": "8月27日～9月26日",
        },
        "kpis": {
            "month_planned": 31,
            "month_done_planned": 10,
            "running": 2,
            "pending": 5,
        },
        "tanks": [
            {
                "tank_no": "302A",
                "status": "running",
                "batch_no": "FA26234",
                "inoculate_at": "2026-09-06T21:00:00",
                "cultured_hours": 39.0,
                "cycle_hours": 72,
                "dump_at": "2026-09-09T10:00:00",
                "note": "距放罐约 46h",
            }
        ],
        "recent": [],
        "trend": None,
        "alerts": [{"level": "info", "text": "车间运行正常，无待处理预警"}],
    }
    monkeypatch.setattr(
        board,
        "load_latest_archive",
        AsyncMock(return_value=SimpleNamespace(rows=[])),  # 非 None 即继续
    )
    monkeypatch.setattr(board, "build_board", lambda *a, **k: fake_payload)

    response = await auth_client.get(f"{API}/fermentation-board")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kpis"]["month_planned"] == 31
    assert data["tanks"][0]["tank_no"] == "302A"


@pytest.mark.anyio
async def test_maintenance_mark_list_release_via_mock(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    client = auth_client
    item_id = str(uuid.uuid4())

    async def _fake_upsert(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            id=item_id,
            tank_no="302A",
            reason="滤芯更换",
            started_at=datetime(2026, 9, 8, 8, 0, 0),
        )

    board.upsert_maintenance.side_effect = _fake_upsert
    marked = await client.post(
        f"{API}/tank-maintenance",
        json={"tank_no": "302A", "reason": "滤芯更换"},
    )
    assert marked.status_code == 200
    assert marked.json()["data"]["id"] == item_id
    assert marked.json()["data"]["reason"] == "滤芯更换"

    listed = await client.get(f"{API}/tank-maintenance")
    assert listed.status_code == 200


@pytest.mark.anyio
async def test_maintenance_delete_404(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    missing = str(uuid.uuid4())
    deleted = await auth_client.delete(f"{API}/tank-maintenance/{missing}")
    assert deleted.status_code == 404


@pytest.mark.anyio
async def test_maintenance_rejects_empty_reason(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    response = await auth_client.post(
        f"{API}/tank-maintenance",
        json={"tank_no": "302A", "reason": ""},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_service_persistence_roundtrip() -> None:
    """真库冒烟：检修标注 upsert → list → delete（自建会话，避免跨循环）。"""
    from sqlalchemy import pool as sa_pool
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from tests.db_safety import get_pytest_database_url

    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            item = await board.upsert_maintenance(
                session, tank_no="303A", reason="仪表校验"
            )
            assert item.tank_no == "303A"
            item_id = item.id

            # 同罐重复标记 → 更新
            again = await board.upsert_maintenance(
                session, tank_no="303A", reason="仪表校验-复查"
            )
            assert again.id == item_id
            assert again.reason == "仪表校验-复查"

            active = await board.list_active_maintenance(session)
            assert any(m.id == item_id for m in active)

            fetched = await board.get_maintenance(session, item_id)
            assert fetched is not None
            await board.delete_maintenance(session, fetched)
            assert await board.get_maintenance(session, item_id) is None

            # 看板加载：测试库无存档 → None（端点分支已覆盖消息）
            assert await board.load_latest_archive(session) is None
    finally:
        await engine.dispose()
