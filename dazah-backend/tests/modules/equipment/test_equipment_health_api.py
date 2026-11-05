"""设备健康/知识案例 API 集成测试（AsyncClient 真实调用路由）。"""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    EquipmentCategoryLink,
    Location,
    RepairKnowledgeCase,
)


def _uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


@pytest.fixture
async def api_equipment(_equipment_session: AsyncSession) -> Equipment:
    category = EquipmentCategory(name="压滤类", code=f"FL-{_uuid_hex()[:6]}")
    _equipment_session.add(category)
    await _equipment_session.flush()
    location = Location(name="二楼压滤间", code=f"FLC-{_uuid_hex()[:6]}")
    _equipment_session.add(location)
    await _equipment_session.flush()
    eq = Equipment(
        equipment_no=f"EQ-API-{_uuid_hex()[:6]}",
        name="隔膜压滤机",
        location_id=location.id,
        status="在用",
        workshop_code="201-1",
    )
    _equipment_session.add(eq)
    await _equipment_session.flush()
    _equipment_session.add(
        EquipmentCategoryLink(equipment_id=eq.id, category_id=category.id)
    )
    await _equipment_session.flush()
    return eq


@pytest.fixture
async def verified_case(
    _equipment_session: AsyncSession, api_equipment: Equipment
) -> RepairKnowledgeCase:
    case = RepairKnowledgeCase(
        equipment_id=api_equipment.id,
        symptom_code="LEAK",
        symptom_name="泄漏",
        cause_code="SEAL",
        cause_name="密封老化",
        action_code="REPLACE",
        action_name="更换密封",
        fault_description="滤板间泄漏",
        repair_summary="更换密封垫片",
        status="verified",
        equipment_name=api_equipment.name,
        equipment_no=api_equipment.equipment_no,
    )
    _equipment_session.add(case)
    await _equipment_session.flush()
    return case


async def test_health_equipment_endpoint_empty(
    client: AsyncClient, api_equipment: Equipment
) -> None:
    resp = await client.get(
        f"/api/v1/equipment/health/equipment/{api_equipment.id}"
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["equipment_id"] == str(api_equipment.id)
    assert body["latest"] is None


async def test_health_board_endpoint(
    client: AsyncClient,
    _equipment_session: AsyncSession,
    api_equipment: Equipment,
) -> None:
    from app.modules.equipment.service import generate_daily_snapshots

    await generate_daily_snapshots(_equipment_session, snapshot_date=date.today())
    resp = await client.get("/api/v1/equipment/health/board")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data and "summary" in data
    assert data["summary"]["total"] >= 1

    # workshop filter
    resp_ws = await client.get(
        "/api/v1/equipment/health/board", params={"workshop": "201-1"}
    )
    assert resp_ws.status_code == 200
    codes = {
        item["workshop_code"] for item in resp_ws.json()["data"]["items"]
    }
    assert codes <= {"201-1"}

    # 非法分档参数 → 422
    resp_bad = await client.get(
        "/api/v1/equipment/health/board", params={"grade": "X"}
    )
    assert resp_bad.status_code == 422


async def test_repair_profile_endpoint(
    client: AsyncClient, api_equipment: Equipment
) -> None:
    resp = await client.get(
        f"/api/v1/equipment/health/repair-profile/{api_equipment.id}"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["equipment_id"] == str(api_equipment.id)
    assert data["total_orders"] == 0


async def test_knowledge_search_endpoint(
    client: AsyncClient, api_equipment: Equipment, verified_case: RepairKnowledgeCase
) -> None:
    resp = await client.get(
        "/api/v1/equipment/repair-knowledge/search",
        params={"q": "滤板间泄漏", "equipment_id": api_equipment.id},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items and items[0]["id"] == str(verified_case.id)

    # 缺 q → 422
    resp_bad = await client.get("/api/v1/equipment/repair-knowledge/search")
    assert resp_bad.status_code == 422


async def test_knowledge_cases_list_and_verify_flow(
    client: AsyncClient,
    _equipment_session: AsyncSession,
    api_equipment: Equipment,
) -> None:
    draft = RepairKnowledgeCase(
        equipment_id=api_equipment.id,
        symptom_code="VIB",
        symptom_name="振动",
        status="draft",
    )
    _equipment_session.add(draft)
    await _equipment_session.flush()

    resp = await client.get(
        "/api/v1/equipment/repair-knowledge/cases",
        params={"status": "draft"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["data"], "草稿应出现在列表中"

    # 确认入库
    resp_verify = await client.post(
        f"/api/v1/equipment/repair-knowledge/cases/{draft.id}/verify"
    )
    assert resp_verify.status_code == 200
    assert resp_verify.json()["data"]["status"] == "verified"

    # 重复确认 → 4xx 业务错误
    resp_repeat = await client.post(
        f"/api/v1/equipment/repair-knowledge/cases/{draft.id}/verify"
    )
    assert 400 <= resp_repeat.status_code < 500


async def test_knowledge_dismiss_flow(
    client: AsyncClient,
    _equipment_session: AsyncSession,
    api_equipment: Equipment,
) -> None:
    draft = RepairKnowledgeCase(
        equipment_id=api_equipment.id,
        symptom_code="NOISE",
        symptom_name="异响",
        status="draft",
    )
    _equipment_session.add(draft)
    await _equipment_session.flush()

    resp = await client.post(
        f"/api/v1/equipment/repair-knowledge/cases/{draft.id}/dismiss"
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "dismissed"

    # 已忽略再忽略 → 4xx
    resp_repeat = await client.post(
        f"/api/v1/equipment/repair-knowledge/cases/{draft.id}/dismiss"
    )
    assert 400 <= resp_repeat.status_code < 500


async def test_knowledge_case_not_found(client: AsyncClient) -> None:
    import uuid

    resp = await client.post(
        f"/api/v1/equipment/repair-knowledge/cases/{uuid.uuid4()}/verify"
    )
    assert 400 <= resp.status_code < 500


async def test_monthly_report_generate_and_fetch(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 不触碰 llm 单例：替换 app.core.llm 模块名下的 llm_client（函数
    # 体内局部 import 每次取该名字）。anyio 测试间对单例方法打补丁存在
    # teardown 交错残留，会连锁影响 hr/quality 的 LLM mock。
    from types import SimpleNamespace as _NS

    class _FailChat:
        async def chat(self, *a: object, **k: object) -> str:
            raise RuntimeError("llm unavailable in test")

    monkeypatch.setattr("app.core.llm.llm_client", _NS(chat=_FailChat().chat))

    month = "2026-01"
    resp = await client.post(
        "/api/v1/equipment/health/monthly-reports/generate",
        json={"report_month": month},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["report_month"] == month
    assert resp.json()["data"]["content_md"]

    resp_get = await client.get(
        f"/api/v1/equipment/health/monthly-reports/{month}"
    )
    assert resp_get.status_code == 200
    assert resp_get.json()["data"]["report_month"] == month

    resp_list = await client.get(
        "/api/v1/equipment/health/monthly-reports"
    )
    assert resp_list.status_code == 200
    assert any(
        r["report_month"] == month for r in resp_list.json()["data"]
    )

    # 未生成的月份 → 4xx
    resp_missing = await client.get(
        "/api/v1/equipment/health/monthly-reports/2030-12"
    )
    assert 400 <= resp_missing.status_code < 500
