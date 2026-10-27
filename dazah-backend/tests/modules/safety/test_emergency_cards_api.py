"""应急处置卡 API 路由测试（真实服务 + 独立测试库）。

用子应用挂载 emergency_cards 路由、覆盖 get_db 指向测试库会话并模拟
`get_current_user`，真实走 Schema 校验、服务层与序列化，覆盖成功路径与
最可能失败路径（不存在 404、重名 409、未登录 401、关键字筛选）。
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.emergency_cards import emergency_cards_router
from app.modules.safety.models import EmergencyCard
from app.platform.identity.models import User


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"应急卡测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(
        emergency_cards_router, prefix="/api/v1/safety"
    )
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


@pytest.fixture
async def seeded_card(db_session: AsyncSession) -> EmergencyCard:
    card = EmergencyCard(
        workshop="103车间",
        position="配料",
        title="103车间测试泄漏应急处置卡",
        subject="测试泄漏",
        accident_type="泄漏",
        steps=[
            {
                "order": "1",
                "step": "发现异常",
                "action": "立即示警",
                "person": "岗位员工",
            },
            {"order": "2", "step": "疏散", "action": "组织疏散", "person": "员工"},
        ],
        extras=[{"label": "次生、衍生事故", "content": "中毒窒息"}],
        phones="消防：119；急救：120",
        risks="中毒、灼烫",
        precautions="处置人员必须穿戴防护装备",
        source_file="test.html",
        search_text="103车间测试泄漏应急处置卡 测试泄漏 泄漏 103车间 配料",
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def _cleanup(db: AsyncSession, title: str) -> None:
    await db.execute(
        delete(EmergencyCard).where(EmergencyCard.title.like(f"%{title}%"))
    )
    await db.commit()


async def test_list_cards_returns_seeded_card(
    client: AsyncClient, seeded_card: EmergencyCard, db_session: AsyncSession
) -> None:
    resp = await client.get(
        "/api/v1/safety/emergency-cards",
        params={"workshop": "103车间", "keyword": "测试泄漏"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    items = body["data"]["items"]
    assert body["data"]["total"] >= 1
    target = next(i for i in items if i["id"] == str(seeded_card.id))
    assert target["title"] == "103车间测试泄漏应急处置卡"
    assert target["position"] == "配料"
    assert len(target["steps"]) == 2
    assert target["steps"][0]["step"] == "发现异常"
    assert target["extras"][0]["label"] == "次生、衍生事故"
    await _cleanup(db_session, "测试泄漏")


async def test_list_cards_filter_by_accident_type(
    client: AsyncClient, seeded_card: EmergencyCard
) -> None:
    resp = await client.get(
        "/api/v1/safety/emergency-cards",
        params={"workshop": "103车间", "accident_type": "火灾"},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(i["accident_type"] == "火灾" for i in items)
    assert all(i["id"] != str(seeded_card.id) for i in items)


async def test_get_card_detail_and_404(
    client: AsyncClient, seeded_card: EmergencyCard
) -> None:
    resp = await client.get(f"/api/v1/safety/emergency-cards/{seeded_card.id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["phones"].startswith("消防：119")

    resp = await client.get(f"/api/v1/safety/emergency-cards/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "应急处置卡不存在"


async def test_stats_returns_workshop_distribution(
    client: AsyncClient, seeded_card: EmergencyCard
) -> None:
    resp = await client.get("/api/v1/safety/emergency-cards/stats")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    workshop = next(w for w in data["workshops"] if w["workshop"] == "103车间")
    assert workshop["total"] >= 1
    assert "配料" in workshop["positions"]
    assert "泄漏" in data["accident_types"]


async def test_create_card_success_and_duplicate_conflict(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    payload = {
        "workshop": "测试车间",
        "position": "化测",
        "title": "测试车间化测触电应急处置卡",
        "subject": "触电",
        "accident_type": "触电",
        "steps": [
            {"order": "1", "step": "脱离电源", "action": "断电", "person": "电工"}
        ],
        "extras": [],
        "phones": "急救：120",
        "risks": "电击伤",
        "precautions": "严禁徒手拉拽",
    }
    resp = await client.post("/api/v1/safety/emergency-cards", json=payload)
    assert resp.status_code == 200
    created = resp.json()["data"]
    assert created["title"] == payload["title"]
    assert created["steps"][0]["action"] == "断电"

    resp = await client.post("/api/v1/safety/emergency-cards", json=payload)
    assert resp.status_code == 409
    assert "同名" in resp.json()["detail"]

    await _cleanup(db_session, "测试车间化测触电应急处置卡")


async def test_create_card_requires_login(
    sub_app: FastAPI, db_session: AsyncSession
) -> None:
    sub_app.dependency_overrides[get_current_user] = lambda: None
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    sub_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=sub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/safety/emergency-cards",
            json={"workshop": "测试车间", "title": "未登录卡"},
        )
    assert resp.status_code == 401


async def test_update_card_and_404(
    client: AsyncClient, seeded_card: EmergencyCard, db_session: AsyncSession
) -> None:
    resp = await client.put(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}",
        json={"precautions": "更新后的注意事项", "sort_order": 5},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["precautions"] == "更新后的注意事项"
    assert data["sort_order"] == 5
    assert data["title"] == seeded_card.title

    resp = await client.put(
        f"/api/v1/safety/emergency-cards/{uuid4()}",
        json={"precautions": "x"},
    )
    assert resp.status_code == 404
    await _cleanup(db_session, "测试泄漏")


async def test_update_card_title_conflict(
    client: AsyncClient, seeded_card: EmergencyCard, db_session: AsyncSession
) -> None:
    other = EmergencyCard(
        workshop="103车间",
        position="化测",
        title="103车间测试火灾应急处置卡",
        subject="火灾",
        accident_type="火灾",
        steps=[],
        extras=[],
        phones="",
        risks="",
        precautions="",
        search_text="",
    )
    db_session.add(other)
    await db_session.flush()

    resp = await client.put(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}",
        json={
            "title": "103车间测试火灾应急处置卡",
            "position": "化测",
        },
    )
    assert resp.status_code == 409
    await _cleanup(db_session, "103车间测试火灾应急处置卡")
    await _cleanup(db_session, "测试泄漏")


async def test_delete_card_soft_deletes(
    client: AsyncClient, seeded_card: EmergencyCard, db_session: AsyncSession
) -> None:
    resp = await client.delete(f"/api/v1/safety/emergency-cards/{seeded_card.id}")
    assert resp.status_code == 200

    result = await db_session.execute(
        select(EmergencyCard).where(EmergencyCard.id == seeded_card.id)
    )
    row = result.scalar_one()
    assert row.is_deleted is True

    resp = await client.delete(f"/api/v1/safety/emergency-cards/{seeded_card.id}")
    assert resp.status_code == 404
    await _cleanup(db_session, "测试泄漏")
