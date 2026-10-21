"""消防点检 API 路由测试（真实服务 + 独立测试库）。

用子应用挂载 fire_equipment 路由、覆盖 get_db 指向测试库会话并模拟
`get_current_user`，真实走 Schema 校验、服务层与序列化，覆盖成功路径与
最可能失败路径（缺检查项 400、器材不存在 404、未知类型 400）。
"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.safety.api.fire_equipment import (
    fire_equipment_router,
    get_current_user,
)
from app.modules.safety.models import (
    FireEquipment,
    FireInspectionRecord,
    SafetyPageFeishuConfig,
    SafetyPageTableMirrorRecord,
)
from app.modules.safety.service import fire_equipment as fire_equipment_service
from app.modules.safety.service.fire_equipment import (
    CHECK_ITEMS_BY_TYPE,
    EQUIPMENT_TYPE_EXTINGUISHER,
    sync_fire_equipment_ledger,
)

PAGE_KEY = "safety:emergency-accident:fire-equipment-inspection"
_SEEDED_RECORD_IDS = ["recApi1"]


@pytest.fixture
def sub_app() -> FastAPI:
    application = FastAPI()

    async def _page_context() -> None:  # 模拟 require_module_view
        return None

    application.include_router(
        fire_equipment_router,
        prefix="/api/v1/safety",
        dependencies=[Depends(_page_context)],
    )
    application.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), name="测试点检员", role="user"
    )
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


async def _seed_one_equipment(db: AsyncSession) -> FireEquipment:
    db.add(
        SafetyPageTableMirrorRecord(
            page_key=PAGE_KEY,
            table_id="tblApi",
            record_id="recApi1",
            fields={
                "灭火器编号": "MQC-API-1",
                "所属部门": "103三车间",
                "存放位置": "罐区西侧",
            },
            search_text="",
        )
    )
    await db.flush()
    await sync_fire_equipment_ledger(db)
    result = await db.execute(
        select(FireEquipment).where(FireEquipment.record_id == "recApi1")
    )
    equipment = result.scalar_one()
    assert equipment is not None
    return equipment


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(FireInspectionRecord).where(
            FireInspectionRecord.equipment_id.in_(
                select(FireEquipment.id).where(
                    FireEquipment.record_id.in_(_SEEDED_RECORD_IDS)
                )
            )
        )
    )
    await db.execute(
        delete(FireEquipment).where(
            FireEquipment.record_id.in_(_SEEDED_RECORD_IDS)
        )
    )
    await db.execute(
        delete(SafetyPageTableMirrorRecord).where(
            SafetyPageTableMirrorRecord.record_id.in_(_SEEDED_RECORD_IDS)
        )
    )
    await db.execute(
        delete(SafetyPageFeishuConfig).where(
            SafetyPageFeishuConfig.page_key == PAGE_KEY
        )
    )
    await db.commit()


class _FakeApiWritebackClient:
    tables: list[dict[str, str]] = []

    def __init__(
        self, app_token: str | None = None, table_id: str | None = None
    ) -> None:
        self.app_token = app_token or ""
        self.table_id = table_id or ""

    async def list_tables(self, app_token: str | None = None) -> list[dict[str, str]]:
        return list(_FakeApiWritebackClient.tables)

    async def create_table(self, name, fields, *, app_token=None, **kwargs):
        return "tblWB-Api", None


@pytest.mark.asyncio
async def test_list_and_stats_return_projected_equipment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    try:
        await _seed_one_equipment(db_session)

        resp = await client.get(
            "/api/v1/safety/fire-equipment",
            params={"keyword": "MQC-API-1"},
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        matched = [
            item for item in body["items"] if item["equipment_no"] == "MQC-API-1"
        ]
        assert len(matched) == 1
        item = matched[0]
        assert item["department"] == "103三车间"
        assert item["location"] == "罐区西侧"
        assert item["month_status"] == "uninspected"
        assert item["fields"]["灭火器编号"] == "MQC-API-1"

        stats_resp = await client.get(
            "/api/v1/safety/fire-equipment/stats",
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert stats_resp.status_code == 200
        stats = stats_resp.json()["data"]
        assert stats["is_configured"] is False
        assert stats["total"] >= 1
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_checklist_returns_card_items(
    client: AsyncClient,
) -> None:
    resp = await client.get(
        "/api/v1/safety/fire-equipment/checklist",
        params={"equipment_type": "extinguisher"},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert [item["key"] for item in items] == [
        key for key, _ in CHECK_ITEMS_BY_TYPE[EQUIPMENT_TYPE_EXTINGUISHER]
    ]

    bad = await client.get(
        "/api/v1/safety/fire-equipment/checklist",
        params={"equipment_type": "sprinkler"},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_create_inspection_roundtrip(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 屏蔽后台飞书写回（测试无独立会话，回写有专门的服务测试覆盖）
    monkeypatch.setattr(
        fire_equipment_service, "schedule_inspection_writeback", lambda _: None
    )
    try:
        equipment = await _seed_one_equipment(db_session)
        payload = {
            "items": [
                {"key": key, "result": "ok"}
                for key, _ in CHECK_ITEMS_BY_TYPE[EQUIPMENT_TYPE_EXTINGUISHER]
            ],
            "source": "scan",
        }
        resp = await client.post(
            f"/api/v1/safety/fire-equipment/{equipment.id}/inspections",
            json=payload,
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert resp.status_code == 200
        record = resp.json()["data"]
        assert record["result"] == "pass"
        assert record["inspector_name"] == "测试点检员"
        assert record["source"] == "scan"

        detail = await client.get(
            f"/api/v1/safety/fire-equipment/{equipment.id}",
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert detail.status_code == 200
        detail_body = detail.json()["data"]
        assert detail_body["equipment"]["month_status"] == "inspected"
        assert len(detail_body["recent_inspections"]) == 1
        assert detail_body["checklist"][0]["label"].startswith("灭火器钢体")
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_init_writeback_table_requires_binding(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/safety/fire-equipment/writeback-table/init",
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_init_writeback_table_creates_table(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.add(
        SafetyPageFeishuConfig(
            page_key=PAGE_KEY,
            app_token="appTokenX",
            table_id="tblMain",
        )
    )
    await db_session.commit()
    _FakeApiWritebackClient.tables = []
    monkeypatch.setattr(
        fire_equipment_service, "SafetyBitableClient", _FakeApiWritebackClient
    )
    try:
        resp = await client.post(
            "/api/v1/safety/fire-equipment/writeback-table/init",
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["created"] is True
        assert body["table_id"] == "tblWB-Api"
        assert body["table_name"] == "点检记录"

        config = (
            await db_session.execute(
                select(SafetyPageFeishuConfig).where(
                    SafetyPageFeishuConfig.page_key == PAGE_KEY
                )
            )
        ).scalar_one()
        assert config.writeback_table_id == "tblWB-Api"
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_create_inspection_incomplete_card_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    try:
        equipment = await _seed_one_equipment(db_session)
        resp = await client.post(
            f"/api/v1/safety/fire-equipment/{equipment.id}/inspections",
            json={"items": [{"key": "body", "result": "ok"}]},
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert resp.status_code == 400
        assert "未点检" in resp.json()["detail"]
    finally:
        await _cleanup(db_session)


@pytest.mark.asyncio
async def test_create_inspection_unknown_equipment_returns_404(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        f"/api/v1/safety/fire-equipment/{uuid4()}/inspections",
        json={
            "items": [
                {"key": key, "result": "ok"}
                for key, _ in CHECK_ITEMS_BY_TYPE[EQUIPMENT_TYPE_EXTINGUISHER]
            ]
        },
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_inspection_rejects_invalid_payload(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        f"/api/v1/safety/fire-equipment/{uuid4()}/inspections",
        json={"items": [{"key": "body", "result": "maybe"}]},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_returns_bitable_columns(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """列表返回当前子表的飞书动态列，隐藏字段被过滤。"""
    from app.modules.safety.feishu.field_codec import FieldSchema

    async def _fake_schema(
        app_token: str, table_id: str, *, refresh: bool = False
    ) -> list[FieldSchema]:
        assert (app_token, table_id) == ("appTokenX", "tblApi")
        return [
            FieldSchema(
                field_id="f0",
                name="序号",
                type=1,
                kind="text",
                is_primary=False,
                options=(),
                editable=True,
            ),
            FieldSchema(
                field_id="f1",
                name="型号",
                type=1,
                kind="text",
                is_primary=False,
                options=(),
                editable=True,
            ),
            FieldSchema(
                field_id="f2",
                name="内部备注",
                type=1,
                kind="text",
                is_primary=False,
                options=(),
                editable=True,
            ),
        ]

    monkeypatch.setattr(
        "app.modules.safety.service.page_table._load_field_schema",
        _fake_schema,
    )
    db_session.add(
        SafetyPageFeishuConfig(
            page_key=PAGE_KEY,
            app_token="appTokenX",
            table_id="tblApi",
            hidden_field_names=["内部备注"],
        )
    )
    await db_session.commit()
    try:
        await _seed_one_equipment(db_session)
        resp = await client.get(
            "/api/v1/safety/fire-equipment",
            params={"keyword": "MQC-API-1"},
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert resp.status_code == 200
        columns = resp.json()["data"]["columns"]
        names = [column["name"] for column in columns]
        assert "型号" in names
        assert "内部备注" not in names
        # 与管理列重复的动态列（序号等）默认抑制，避免台账列爆炸
        assert "序号" not in names
        assert columns[0]["kind"] == "text"
    finally:
        await _cleanup(db_session)


def test_expiry_fields_covers_all_statuses() -> None:
    """纯函数：过期/临期/正常/无日期四态。"""
    from datetime import date, timedelta

    from app.modules.safety.api.fire_equipment import _expiry_fields

    today = date.today()
    assert _expiry_fields(None) == (None, None, None)
    assert _expiry_fields(today - timedelta(days=1)) == (
        today - timedelta(days=1),
        -1,
        "expired",
    )
    assert _expiry_fields(today + timedelta(days=7))[2] == "expiring"
    assert _expiry_fields(today + timedelta(days=90))[2] == "ok"


@pytest.mark.asyncio
async def test_sync_fire_equipment_endpoint_orchestrates_pipeline(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """立即同步：镜像同步 → 投影 → 补回写 → 统计，按序编排。"""
    from app.modules.safety.api import fire_equipment as api_module

    calls: list[str] = []

    async def _sync_mirror(db, page_key):
        calls.append("sync")

    async def _project(db, page_key):
        calls.append("project")

    async def _retry(db):
        calls.append("retry")

    async def _stats(db):
        calls.append("stats")
        return {
            "total": 0,
            "extinguisher_count": 0,
            "hydrant_count": 0,
            "inspected_this_month": 0,
            "uninspected_this_month": 0,
            "failed_this_month": 0,
            "is_configured": False,
            "writeback_enabled": False,
            "expired_count": 0,
            "expiring_in_30_count": 0,
        }

    monkeypatch.setattr(api_module.page_table, "sync_page_table_mirror", _sync_mirror)
    monkeypatch.setattr(
        api_module.fire_equipment, "maybe_project_after_sync", _project
    )
    monkeypatch.setattr(
        api_module.fire_equipment, "retry_pending_inspection_writebacks", _retry
    )
    monkeypatch.setattr(api_module.fire_equipment, "get_fire_equipment_stats", _stats)

    resp = await client.post(
        "/api/v1/safety/fire-equipment/sync",
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert resp.status_code == 200, resp.text
    assert calls == ["sync", "project", "retry", "stats"]
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_fire_inspections_supports_filters(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fire_equipment_service, "schedule_inspection_writeback", lambda _: None
    )
    try:
        equipment = await _seed_one_equipment(db_session)
        payload = {
            "items": [
                {"key": key, "result": "ok"}
                for key, _ in CHECK_ITEMS_BY_TYPE[EQUIPMENT_TYPE_EXTINGUISHER]
            ],
            "source": "scan",
        }
        created = await client.post(
            f"/api/v1/safety/fire-equipment/{equipment.id}/inspections",
            json=payload,
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert created.status_code == 200, created.text

        resp = await client.get(
            "/api/v1/safety/fire-inspection-records"
            "?result=pass&keyword=103%E4%B8%89%E8%BD%A6%E9%97%B4",
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["total"] >= 1
        assert body["items"][0]["result"] == "pass"

        empty = await client.get(
            "/api/v1/safety/fire-inspection-records?result=abnormal",
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert empty.status_code == 200
        assert empty.json()["data"]["total"] == 0

        no_hit = await client.get(
            "/api/v1/safety/fire-inspection-records?keyword=%E4%B8%8D%E5%AD%98%E5%9C%A8",
            headers={"X-Dazah-Page-Key": PAGE_KEY},
        )
        assert no_hit.status_code == 200
        assert no_hit.json()["data"]["total"] == 0
    finally:
        await _cleanup(db_session)
