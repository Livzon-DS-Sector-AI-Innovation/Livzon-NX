"""目标责任与绩效 API 路由测试（真实服务 + 独立测试库）。"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.targets import safety_targets_router
from app.modules.safety.models import SafetyTarget, SafetyTargetRecord
from app.platform.identity.models import User

_TITLE_PREFIX = "测试安全目标-"


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"目标测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(safety_targets_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: test_user
    return application


@pytest.fixture
async def client(
    sub_app: FastAPI, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    sub_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=sub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    sub_app.dependency_overrides.pop(get_db, None)


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(SafetyTargetRecord).where(
            SafetyTargetRecord.target_id.in_(
                select(SafetyTarget.id).where(
                    SafetyTarget.title.like(f"{_TITLE_PREFIX}%")
                )
            )
        )
    )
    await db.execute(
        delete(SafetyTarget).where(SafetyTarget.title.like(f"{_TITLE_PREFIX}%"))
    )
    await db.commit()


async def test_create_list_update_target_roundtrip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    payload = {
        "year": 2026,
        "title": f"{_TITLE_PREFIX}杜绝重伤事故",
        "category": "事故控制",
        "metric": "重伤事故起数",
        "target_value": "0",
        "unit": "起",
        "owner_department": "安环部",
        "owner_name": "张三",
        "status": "in_progress",
    }
    resp = await client.post("/api/v1/safety/safety-targets", json=payload)
    assert resp.status_code == 200
    created = resp.json()["data"]
    assert created["title"] == payload["title"]
    assert created["records"] == []

    resp = await client.get(
        "/api/v1/safety/safety-targets", params={"year": 2026, "keyword": _TITLE_PREFIX}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    resp = await client.put(
        f"/api/v1/safety/safety-targets/{created['id']}",
        json={"status": "achieved", "remark": "全年达成"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "achieved"

    resp = await client.post("/api/v1/safety/safety-targets", json=payload)
    assert resp.status_code == 409
    await _cleanup(db_session)


async def test_target_record_upsert_and_stats(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    payload = {
        "year": 2026,
        "title": f"{_TITLE_PREFIX}隐患整改率",
        "category": "隐患治理",
        "target_value": "100",
        "unit": "%",
        "owner_department": "提炼四部",
        "status": "in_progress",
    }
    created = (await client.post("/api/v1/safety/safety-targets", json=payload)).json()[
        "data"
    ]
    target_id = created["id"]

    resp = await client.put(
        f"/api/v1/safety/safety-targets/{target_id}/records/2026-Q1",
        json={"actual_value": "92", "completion_pct": 92, "note": "季度复盘"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["period"] == "2026-Q1"
    assert resp.json()["data"]["actual_value"] == "92"

    # 同期再次保存 → 覆盖（upsert 语义）
    resp = await client.put(
        f"/api/v1/safety/safety-targets/{target_id}/records/2026-Q1",
        json={"actual_value": "96", "completion_pct": 96},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["actual_value"] == "96"

    resp = await client.get(f"/api/v1/safety/safety-targets/{target_id}")
    assert resp.status_code == 200
    records = resp.json()["data"]["records"]
    assert len(records) == 1
    assert records[0]["completion_pct"] == 96

    resp = await client.delete(
        f"/api/v1/safety/safety-targets/{target_id}/records/2026-Q1"
    )
    assert resp.status_code == 200

    resp = await client.get(
        "/api/v1/safety/safety-targets/stats", params={"year": 2026}
    )
    assert resp.status_code == 200
    stats = resp.json()["data"]
    assert stats["total"] >= 1
    dept = next(d for d in stats["departments"] if d["department"] == "提炼四部")
    assert dept["total"] >= 1
    await _cleanup(db_session)


async def test_delete_target_soft_deletes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    payload = {
        "year": 2026,
        "title": f"{_TITLE_PREFIX}待删除目标",
        "category": "培训教育",
        "status": "in_progress",
    }
    created = (await client.post("/api/v1/safety/safety-targets", json=payload)).json()[
        "data"
    ]
    resp = await client.delete(f"/api/v1/safety/safety-targets/{created['id']}")
    assert resp.status_code == 200
    result = await db_session.execute(
        select(SafetyTarget).where(SafetyTarget.id == created["id"])  # type: ignore[arg-type]
    )
    assert result.scalar_one().is_deleted is True
    await _cleanup(db_session)


async def test_create_target_requires_login(
    sub_app: FastAPI, db_session: AsyncSession
) -> None:
    sub_app.dependency_overrides[get_current_user] = lambda: None

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    sub_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=sub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/safety/safety-targets",
            json={"year": 2026, "title": "未登录目标", "category": "其他"},
        )
    assert resp.status_code == 401
