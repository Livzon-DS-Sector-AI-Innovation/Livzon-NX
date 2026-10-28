"""危化品与安全设施 API 路由测试（档案/存量/设施 CRUD 与统计，真实服务 + 测试库）。"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.facilities import safety_facilities_router
from app.modules.safety.api.hazchem import hazchem_router
from app.modules.safety.models import (
    ChemicalInventory,
    HazardousChemical,
    SafetyFacility,
    SafetyFacilityInspection,
)
from app.platform.identity.models import User

_CHEM_PREFIX = "测试化学品-"
_FAC_PREFIX = "测试设施-"


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"治理测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(hazchem_router, prefix="/api/v1/safety")
    application.include_router(safety_facilities_router, prefix="/api/v1/safety")
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
        delete(ChemicalInventory).where(
            ChemicalInventory.chemical_id.in_(
                __import__("sqlalchemy")
                .select(HazardousChemical.id)
                .where(HazardousChemical.name.like(f"{_CHEM_PREFIX}%"))
            )
        )
    )
    await db.execute(
        delete(HazardousChemical).where(HazardousChemical.name.like(f"{_CHEM_PREFIX}%"))
    )
    await db.execute(
        delete(SafetyFacilityInspection).where(
            SafetyFacilityInspection.facility_id.in_(
                __import__("sqlalchemy")
                .select(SafetyFacility.id)
                .where(SafetyFacility.name.like(f"{_FAC_PREFIX}%"))
            )
        )
    )
    await db.execute(
        delete(SafetyFacility).where(SafetyFacility.name.like(f"{_FAC_PREFIX}%"))
    )
    await db.commit()


async def test_chemical_catalog_crud_and_stats(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    name = f"{_CHEM_PREFIX}乙醇-{uuid4().hex[:6]}"
    created = await client.post(
        "/api/v1/safety/hazardous-chemicals",
        json={"name": name, "category": "flammable_liquid"},
    )
    assert created.status_code == 200, created.text
    chem_id = created.json()["data"]["id"]

    listed = await client.get(
        "/api/v1/safety/hazardous-chemicals", params={"keyword": name}
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] >= 1

    stats = await client.get("/api/v1/safety/hazardous-chemicals/stats")
    assert stats.status_code == 200

    over_limit = await client.get("/api/v1/safety/hazardous-chemicals/over-limit")
    assert over_limit.status_code == 200

    updated = await client.put(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}",
        json={"alias": "酒精"},
    )
    assert updated.status_code == 200

    deleted = await client.delete(f"/api/v1/safety/hazardous-chemicals/{chem_id}")
    assert deleted.status_code == 200
    await _cleanup(db_session)


async def test_chemical_inventory_crud(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    chem_name = f"{_CHEM_PREFIX}丙酮-{uuid4().hex[:6]}"
    chem = await client.post(
        "/api/v1/safety/hazardous-chemicals",
        json={"name": chem_name, "category": "flammable_liquid"},
    )
    assert chem.status_code == 200, chem.text
    chem_id = chem.json()["data"]["id"]

    inv = await client.post(
        "/api/v1/safety/chemical-inventories",
        json={"chemical_id": chem_id, "workshop": "101一车间", "quantity": 5},
    )
    assert inv.status_code == 200, inv.text
    inv_id = inv.json()["data"]["id"]

    inv_listed = await client.get("/api/v1/safety/chemical-inventories")
    assert inv_listed.status_code == 200

    inv_updated = await client.put(
        f"/api/v1/safety/chemical-inventories/{inv_id}",
        json={"quantity": 8, "upper_limit": 10},
    )
    assert inv_updated.status_code == 200

    inv_deleted = await client.delete(f"/api/v1/safety/chemical-inventories/{inv_id}")
    assert inv_deleted.status_code == 200
    await _cleanup(db_session)


async def test_facility_crud_checklist_and_inspection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    name = f"{_FAC_PREFIX}洗眼器-{uuid4().hex[:6]}"
    created = await client.post(
        "/api/v1/safety/safety-facilities",
        json={"name": name, "category": "eyewash", "department": "101一车间"},
    )
    assert created.status_code == 200, created.text
    facility_id = created.json()["data"]["id"]

    listed = await client.get(
        "/api/v1/safety/safety-facilities", params={"category": "eyewash"}
    )
    assert listed.status_code == 200

    stats = await client.get("/api/v1/safety/safety-facilities/stats")
    assert stats.status_code == 200

    checklist = await client.get(
        "/api/v1/safety/safety-facilities/checklist", params={"category": "eyewash"}
    )
    assert checklist.status_code == 200

    detail = await client.get(f"/api/v1/safety/safety-facilities/{facility_id}")
    assert detail.status_code == 200

    updated = await client.put(
        f"/api/v1/safety/safety-facilities/{facility_id}",
        json={"location": "罐区东侧"},
    )
    assert updated.status_code == 200

    items = [
        {"key": item["key"], "label": item["label"], "result": "ok", "remark": ""}
        for item in checklist.json()["data"]["items"]
    ]
    inspection = await client.post(
        f"/api/v1/safety/safety-facilities/{facility_id}/inspections",
        json={"items": items, "inspector_name": "测试员"},
    )
    assert inspection.status_code == 200, inspection.text

    inspections = await client.get("/api/v1/safety/safety-facility-inspections")
    assert inspections.status_code == 200

    deleted = await client.delete(f"/api/v1/safety/safety-facilities/{facility_id}")
    assert deleted.status_code == 200
    await _cleanup(db_session)
