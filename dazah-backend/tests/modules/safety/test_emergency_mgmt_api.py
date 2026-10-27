"""应急管理 API 路由测试（预案/演练/物资 CRUD 与统计，真实服务 + 测试库）。"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.emergency_mgmt import emergency_mgmt_router
from app.modules.safety.models import EmergencyDrill, EmergencyPlan, EmergencySupply
from app.platform.identity.models import User

_PREFIX = "测试应急"


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"应急测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(emergency_mgmt_router, prefix="/api/v1/safety")
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
    await db.execute(delete(EmergencySupply).where(EmergencySupply.name.like(f"{_PREFIX}%")))
    await db.execute(delete(EmergencyDrill).where(EmergencyDrill.name.like(f"{_PREFIX}%")))
    await db.execute(delete(EmergencyPlan).where(EmergencyPlan.name.like(f"{_PREFIX}%")))
    await db.commit()


async def test_plan_list_create_update_delete_roundtrip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    name = f"{_PREFIX}预案-{uuid4().hex[:6]}"
    created = await client.post(
        "/api/v1/safety/emergency-plans",
        json={"name": name, "plan_type": "onsite"},
    )
    assert created.status_code == 200, created.text
    plan_id = created.json()["data"]["id"]

    listed = await client.get("/api/v1/safety/emergency-plans", params={"keyword": name})
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] >= 1

    detail = await client.get(f"/api/v1/safety/emergency-plans/{plan_id}")
    assert detail.status_code == 200

    stats = await client.get("/api/v1/safety/emergency-mgmt/stats")
    assert stats.status_code == 200

    updated = await client.put(
        f"/api/v1/safety/emergency-plans/{plan_id}",
        json={"version": "V2.0"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["version"] == "V2.0"

    deleted = await client.delete(f"/api/v1/safety/emergency-plans/{plan_id}")
    assert deleted.status_code == 200
    await _cleanup(db_session)


async def test_drill_and_supply_crud(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    drill_name = f"{_PREFIX}演练-{uuid4().hex[:6]}"
    created = await client.post(
        "/api/v1/safety/emergency-drills",
        json={"name": drill_name, "drill_type": "tabletop"},
    )
    assert created.status_code == 200, created.text
    drill_id = created.json()["data"]["id"]

    listed = await client.get(
        "/api/v1/safety/emergency-drills", params={"keyword": drill_name}
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] >= 1

    updated = await client.put(
        f"/api/v1/safety/emergency-drills/{drill_id}",
        json={"summary": "流程顺畅"},
    )
    assert updated.status_code == 200

    deleted = await client.delete(f"/api/v1/safety/emergency-drills/{drill_id}")
    assert deleted.status_code == 200

    supply_name = f"{_PREFIX}物资-{uuid4().hex[:6]}"
    supply = await client.post(
        "/api/v1/safety/emergency-supplies",
        json={"name": supply_name, "category": "medical"},
    )
    assert supply.status_code == 200, supply.text
    supply_id = supply.json()["data"]["id"]

    supply_listed = await client.get(
        "/api/v1/safety/emergency-supplies", params={"keyword": supply_name}
    )
    assert supply_listed.status_code == 200

    supply_updated = await client.put(
        f"/api/v1/safety/emergency-supplies/{supply_id}",
        json={"quantity": 10},
    )
    assert supply_updated.status_code == 200

    supply_deleted = await client.delete(
        f"/api/v1/safety/emergency-supplies/{supply_id}"
    )
    assert supply_deleted.status_code == 200
    await _cleanup(db_session)
