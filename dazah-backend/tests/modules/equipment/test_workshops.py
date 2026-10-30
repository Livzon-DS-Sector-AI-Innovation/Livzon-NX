"""设备车间注册表服务与 API 测试。"""

from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models.workshop import EquipmentWorkshop
from app.modules.equipment.schemas.workshop import (
    WorkshopCreateRequest,
    WorkshopUpdateRequest,
)
from app.modules.equipment.service import workshop as workshop_service


@pytest.fixture(autouse=True)
async def _clean_workshops_table(
    db_session: AsyncSession,
    _equipment_session: AsyncSession,
) -> Any:
    """前后清空车间注册表：服务写操作会 commit，不能依赖回滚隔离。

    同时覆盖服务级会话与 API 级共享会话两条写入路径。
    """
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentWorkshop))
        await session.commit()
    yield
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentWorkshop))
        await session.commit()


async def _seed_workshops(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            EquipmentWorkshop(code="101-1", name="101一车间"),
            EquipmentWorkshop(code="101-2", name="101二车间"),
            EquipmentWorkshop(code="204", name="204车间", is_enabled=False),
        ]
    )
    await db_session.commit()


# ---------- 服务 ----------


async def test_list_enabled_orders_by_code_and_skips_disabled(
    db_session: AsyncSession,
) -> None:
    await _seed_workshops(db_session)
    enabled = await workshop_service.list_enabled(db_session)
    assert [ws.code for ws in enabled] == ["101-1", "101-2"]
    assert enabled[0].name == "101一车间"


async def test_list_all_includes_disabled(db_session: AsyncSession) -> None:
    await _seed_workshops(db_session)
    all_rows = await workshop_service.list_all(db_session)
    assert [ws.code for ws in all_rows] == ["101-1", "101-2", "204"]
    assert all_rows[2].is_enabled is False


async def test_create_workshop_success(db_session: AsyncSession) -> None:
    created = await workshop_service.create_workshop(
        db_session, WorkshopCreateRequest(code="204-1", name="204一车间")
    )
    assert created.code == "204-1"
    assert created.is_enabled is True
    enabled = await workshop_service.list_enabled(db_session)
    assert [ws.code for ws in enabled] == ["204-1"]


async def test_create_workshop_letter_code(db_session: AsyncSession) -> None:
    """车间代码支持小写字母（如 动力站 → dlz）；大写与非法格式被拒。"""
    from pydantic import ValidationError

    created = await workshop_service.create_workshop(
        db_session, WorkshopCreateRequest(code="dlz", name="动力站")
    )
    assert created.code == "dlz"
    assert created.name == "动力站"

    with pytest.raises(ValidationError):
        WorkshopCreateRequest(code="DLZ", name="大写不行")
    with pytest.raises(ValidationError):
        WorkshopCreateRequest(code="-dlz", name="连字符开头不行")
    with pytest.raises(ValidationError):
        WorkshopCreateRequest(code="动力站", name="中文代码不行")


async def test_create_workshop_duplicate_code_rejected(
    db_session: AsyncSession,
) -> None:
    await _seed_workshops(db_session)
    with pytest.raises(AppException, match="已存在"):
        await workshop_service.create_workshop(
            db_session, WorkshopCreateRequest(code="101-1", name="重复车间")
        )


async def test_update_workshop_rename_and_toggle(
    db_session: AsyncSession,
) -> None:
    await _seed_workshops(db_session)
    updated = await workshop_service.update_workshop(
        db_session, "101-1", WorkshopUpdateRequest(name="101新一车间")
    )
    assert updated.name == "101新一车间"

    updated = await workshop_service.update_workshop(
        db_session, "204", WorkshopUpdateRequest(is_enabled=True)
    )
    assert updated.is_enabled is True
    enabled = await workshop_service.list_enabled(db_session)
    assert "204" in [ws.code for ws in enabled]


async def test_update_workshop_blank_name_rejected(
    db_session: AsyncSession,
) -> None:
    await _seed_workshops(db_session)
    with pytest.raises(AppException, match="不能为空"):
        await workshop_service.update_workshop(
            db_session, "101-1", WorkshopUpdateRequest(name="  ")
        )


async def test_update_workshop_missing_raises_404(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(AppException) as exc_info:
        await workshop_service.update_workshop(
            db_session, "999", WorkshopUpdateRequest(name="不存在")
        )
    assert exc_info.value.status_code == 404


# ---------- API ----------


async def test_workshops_api_requires_login(db_session: AsyncSession) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.main import app

    async def _override_get_db() -> Any:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            for method, path in (
                ("GET", "/api/v1/equipment/workshops"),
                ("GET", "/api/v1/equipment/workshops/all"),
                ("POST", "/api/v1/equipment/workshops"),
                ("PUT", "/api/v1/equipment/workshops/101-1"),
            ):
                resp = await ac.request(method, path, json={})
                assert resp.status_code == 401, (method, path, resp.status_code)
    finally:
        app.dependency_overrides.clear()


async def test_workshops_api_crud_flow(client: Any) -> None:
    resp = await client.get("/api/v1/equipment/workshops")
    assert resp.status_code == 200
    assert resp.json()["data"] == []

    resp = await client.post(
        "/api/v1/equipment/workshops",
        json={"code": "204", "name": "204车间"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["code"] == "204"

    # 重复代码返回业务 4xx
    resp = await client.post(
        "/api/v1/equipment/workshops",
        json={"code": "204", "name": "再来一个"},
    )
    assert resp.status_code == 400
    assert "已存在" in resp.json()["message"]

    # 非法代码格式被 Schema 校验拦截
    resp = await client.post(
        "/api/v1/equipment/workshops",
        json={"code": "研发部", "name": "格式不对"},
    )
    assert resp.status_code == 422

    resp = await client.get("/api/v1/equipment/workshops")
    assert [ws["code"] for ws in resp.json()["data"]] == ["204"]

    # 改名 + 停用；停用后从启用清单消失、仍在管理清单
    resp = await client.put(
        "/api/v1/equipment/workshops/204",
        json={"name": "204新车间", "is_enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_enabled"] is False

    resp = await client.get("/api/v1/equipment/workshops")
    assert resp.json()["data"] == []
    resp = await client.get("/api/v1/equipment/workshops/all")
    assert [ws["code"] for ws in resp.json()["data"]] == ["204"]
    assert resp.json()["data"][0]["name"] == "204新车间"

    # 更新不存在的车间返回 404
    resp = await client.put(
        "/api/v1/equipment/workshops/999",
        json={"name": "不存在"},
    )
    assert resp.status_code == 404


async def test_workshop_feishu_chat_id_roundtrip(
    db_session, _clean_workshops_table, client
) -> None:
    """车间维修群 chat_id：创建可带、更新可改可清空。"""
    from app.modules.equipment.schemas.workshop import (
        WorkshopCreateRequest,
        WorkshopUpdateRequest,
    )
    from app.modules.equipment.service import workshop as ws_svc

    created = await ws_svc.create_workshop(
        db_session,
        WorkshopCreateRequest(
            code="204-1", name="204一车间", feishu_chat_id="oc_chat_204"
        ),
    )
    assert created.feishu_chat_id == "oc_chat_204"

    updated = await ws_svc.update_workshop(
        db_session, "204-1", WorkshopUpdateRequest(feishu_chat_id="oc_new")
    )
    assert updated.feishu_chat_id == "oc_new"

    cleared = await ws_svc.update_workshop(
        db_session, "204-1", WorkshopUpdateRequest(feishu_chat_id="")
    )
    assert cleared.feishu_chat_id is None
