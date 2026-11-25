"""设备检修台账（飞书镜像）同步与查询测试。"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.llm.encryption import encrypt_api_key
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.repair_ledger import (
    RepairFeishuConfig,
    RepairRecord,
)
from app.modules.equipment.schemas.repair_ledger import RepairConfigUpdateRequest
from app.modules.equipment.service import repair_ledger as service


@pytest.fixture(autouse=True)
def _test_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(), "LLM_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )


# ── 字段映射 ─────────────────────────────────────────────────────


def test_normalize_maps_standard_columns() -> None:
    fields = {
        "车间及地点": "201二车间一楼泵房",
        "设备名称/型号": "薄膜蒸发器 4",
        "维修日期": 1790000000000,
        "维修人员": [{"id": "ou_1", "name": "张三"}, {"id": "ou_2", "name": "李四"}],
        "故障描述/原因": "机械密封泄漏",
        "更换备件": "机械密封 1 套",
        "维修后状态": "正常运行",
        "备注": "紧固压盖",
    }
    values = service.normalize_record_fields(fields)
    assert values["workshop_text"] == "201二车间一楼泵房"
    assert values["equipment_text"] == "薄膜蒸发器 4"
    assert (
        values["repaired_at"]
        == datetime.fromtimestamp(1790000000000 / 1000, tz=service._CST).date()
    )
    assert values["person_text"] == "张三、李四"
    assert values["fault_desc"] == "机械密封泄漏"
    assert values["spare_parts"] == "机械密封 1 套"
    assert values["result"] == "正常运行"
    assert values["remark"] == "紧固压盖"


def test_normalize_tolerates_column_name_variations_and_unknowns() -> None:
    fields = {
        "日期": "2026-11-01",
        "设备名称": "离心泵A",
        "故障原因": "叶轮磨损",
        "状态": "待观察",
        "自定义列": "不识别",
    }
    values = service.normalize_record_fields(fields)
    assert values["repaired_at"] == date(2026, 11, 1)
    assert values["equipment_text"] == "离心泵A"
    assert values["fault_desc"] == "叶轮磨损"
    assert values["result"] == "待观察"
    assert "自定义列" not in values
    assert "workshop_text" not in values


def test_normalize_ignores_empty_values() -> None:
    values = service.normalize_record_fields({"设备名称/型号": "  ", "备注": None})
    assert values == {}


# ── 同步 ────────────────────────────────────────────────────────


def _feishu_item(record_id: str, **field_values: Any) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "fields": {
            "车间及地点": "201二车间",
            "设备名称/型号": "薄膜蒸发器 4",
            "维修日期": 1790000000000,
            "维修人员": "王五",
            "故障描述/原因": "机械密封泄漏",
            "更换备件": "",
            "维修后状态": "正常运行",
            **field_values,
        },
        "last_modified_time": 1790000100000,
    }


class _FakeClient:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items
        # 底层 FeishuClient 替身：人员解析用它读通讯录；默认无权限（返回空）
        self.client = SimpleNamespace(request=self._contact_request)

    async def _contact_request(
        self, _method: str, path: str, **_kwargs: Any
    ) -> dict[str, Any]:
        if path.startswith("/contact/v3/users/find_by_department"):
            return {"data": {"items": [], "has_more": False}}
        return {"data": {}}

    async def search_records_page(self, table_id: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "items": self._items,
            "has_more": False,
            "page_token": None,
            "total": len(self._items),
        }


async def _make_config(db: AsyncSession, workshop: str) -> None:
    app = EquipmentFeishuApp(
        name=f"检修测试应用-{workshop}",
        app_id=f"cli_test_{workshop}",
        app_secret=encrypt_api_key("test-secret"),
    )
    db.add(app)
    await db.flush()
    db.add(
        RepairFeishuConfig(
            workshop_code=workshop,
            feishu_app_id=app.id,
            app_token=f"base-{workshop}",
            table_id=f"tbl-{workshop}",
            is_enabled=True,
        )
    )
    await db.flush()


@pytest.fixture
async def repair_workshop(db_session: AsyncSession) -> str:
    code = f"t{uuid4().hex[:6]}"
    await _make_config(db_session, code)
    yield code
    await db_session.rollback()
    # 配置与应用行在服务层 commit 后无法靠 fixture 回滚，显式清理
    await db_session.execute(
        delete(RepairFeishuConfig).where(RepairFeishuConfig.workshop_code == code)
    )
    await db_session.execute(
        delete(EquipmentFeishuApp).where(
            EquipmentFeishuApp.app_id == f"cli_test_{code}"
        )
    )
    await db_session.commit()


async def test_sync_workshop_upserts_and_reconciles(
    db_session: AsyncSession, repair_workshop: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = [
        _feishu_item("rec-1", **{"设备名称/型号": "离心泵A"}),
        _feishu_item("rec-2", **{"设备名称/型号": "薄膜蒸发器 4"}),
    ]
    monkeypatch.setattr(service, "_build_client", lambda config: _FakeClient(items))
    result = await service.sync_workshop(db_session, repair_workshop)
    assert result == {"synced": 2, "total": 2}

    # 修改 + 删除一条后再次同步：UPSERT 生效、消失行被清理
    items[0]["fields"]["故障描述/原因"] = "叶轮磨损（更新）"
    items.pop()
    result = await service.sync_workshop(db_session, repair_workshop)
    assert result == {"synced": 1, "total": 1}
    rows, total = await service.list_records(db_session, workshop=repair_workshop)
    assert total == 1
    assert rows[0].fault_desc == "叶轮磨损（更新）"

    state = await service.get_sync_state(db_session, repair_workshop)
    assert state["last_status"] == "success"
    assert state["total_rows"] == 1


async def test_sync_workshop_requires_enabled_config(
    db_session: AsyncSession, repair_workshop: str
) -> None:
    # 未登记配置的车间：未启用，直接报错
    with pytest.raises(Exception, match="未配置"):
        await service.sync_workshop(db_session, "tx-none")


# ── 查询 ────────────────────────────────────────────────────────


@pytest.fixture
async def frequency_rows(db_session: AsyncSession) -> str:
    code = f"t{uuid4().hex[:6]}"
    today = date(2026, 11, 20)
    rows = [
        RepairRecord(
            workshop_code=code,
            record_id=f"{code}-1",
            equipment_text="离心泵A",
            repaired_at=today,
            fault_desc="泄漏",
        ),
        RepairRecord(
            workshop_code=code,
            record_id=f"{code}-2",
            equipment_text="离心泵A",
            repaired_at=today - timedelta(days=3),
            fault_desc="异响",
        ),
        RepairRecord(
            workshop_code=code,
            record_id=f"{code}-3",
            equipment_text="离心泵A",
            repaired_at=today - timedelta(days=40),
            fault_desc="旧记录",
        ),
        RepairRecord(
            workshop_code=code,
            record_id=f"{code}-4",
            equipment_text="薄膜蒸发器 4",
            repaired_at=today - timedelta(days=1),
            fault_desc="密封",
        ),
        RepairRecord(
            workshop_code=code,
            record_id=f"{code}-5",
            equipment_text=None,
            repaired_at=today,
            fault_desc="无设备名不参与聚合",
        ),
    ]
    db_session.add_all(rows)
    await db_session.flush()
    yield code
    await db_session.rollback()


async def test_frequency_ranks_by_times_then_recent(
    db_session: AsyncSession, frequency_rows: str
) -> None:
    items = await service.frequency(db_session, workshop=frequency_rows)
    assert [item["equipment_text"] for item in items] == ["离心泵A", "薄膜蒸发器 4"]
    assert items[0]["times"] == 3
    assert items[0]["last_repaired_at"] == date(2026, 11, 20)

    # date_from 只统计近 30 天：离心泵A 剩 2 次
    items_30d = await service.frequency(
        db_session, workshop=frequency_rows, date_from=date(2026, 10, 22)
    )
    assert items_30d[0]["times"] == 2
    assert items_30d[0]["last_repaired_at"] == date(2026, 11, 20)


async def test_list_records_filters(
    db_session: AsyncSession, frequency_rows: str
) -> None:
    # 关键字
    rows, total = await service.list_records(
        db_session, workshop=frequency_rows, keyword="离心泵"
    )
    assert total == 3
    # 设备原文
    rows, total = await service.list_records(
        db_session, workshop=frequency_rows, equipment="薄膜蒸发器 4"
    )
    assert total == 1
    assert rows[0].equipment_text == "薄膜蒸发器 4"
    # 日期范围：11-19 ~ 11-21 覆盖 rec-1(11-20) / rec-4(11-19) / rec-5(11-20)
    rows, total = await service.list_records(
        db_session,
        workshop=frequency_rows,
        date_from=date(2026, 11, 19),
        date_to=date(2026, 11, 21),
    )
    assert total == 3
    # 排序：维修日期倒序
    assert rows[0].repaired_at == date(2026, 11, 20)


# ── 配置 ────────────────────────────────────────────────────────


async def test_update_config_registers_manual_app(db_session: AsyncSession) -> None:
    workshop = f"t{uuid4().hex[:6]}"
    try:
        detail = await service.update_config(
            db_session,
            workshop,
            RepairConfigUpdateRequest(
                app_id=f"cli_manual_{workshop}",
                app_secret="test-secret",
                app_token="https://example.feishu.cn/base/testbase123",
                table_id=(
                    "https://example.feishu.cn/base/testbase123?table=tblXYZ&view=vewABC"
                ),
                base_url="https://example.feishu.cn/base/testbase123",
                is_enabled=True,
            ),
        )
        assert detail["app_token"] == "testbase123"
        assert detail["table_id"] == "tblXYZ"
        assert detail["enabled"] is True
    finally:
        await db_session.execute(
            delete(RepairFeishuConfig).where(
                RepairFeishuConfig.workshop_code == workshop
            )
        )
        await db_session.execute(
            delete(EquipmentFeishuApp).where(
                EquipmentFeishuApp.app_id == f"cli_manual_{workshop}"
            )
        )
        await db_session.commit()


async def test_update_config_rejects_view_id(db_session: AsyncSession) -> None:
    workshop = f"t{uuid4().hex[:6]}"
    app = EquipmentFeishuApp(
        name="视图校验应用", app_id=f"cli_view_{workshop}", app_secret="enc"
    )
    db_session.add(app)
    await db_session.flush()
    try:
        with pytest.raises(Exception, match="视图 ID"):
            await service.update_config(
                db_session,
                workshop,
                RepairConfigUpdateRequest(
                    feishu_app_id=app.id,
                    app_token="base1234567890",
                    table_id="vewABC123",
                    is_enabled=True,
                ),
            )
    finally:
        await db_session.rollback()
        await db_session.execute(
            delete(EquipmentFeishuApp).where(
                EquipmentFeishuApp.app_id == f"cli_view_{workshop}"
            )
        )
        await db_session.commit()


async def test_test_config_reports_incomplete(db_session: AsyncSession) -> None:
    workshop = f"t{uuid4().hex[:6]}"
    result = await service.test_config(db_session, workshop)
    assert result["success"] is False
    assert "未启用" in result["message"] or "配置不完整" in result["message"]


# ── API ──────────────────────────────────────────────────────────


async def test_records_and_frequency_endpoints(
    _equipment_session: AsyncSession,
    client: AsyncClient,
) -> None:
    """接口层验证：响应经 Schema 校验后序列化，不返回 500。"""
    code = f"t{uuid4().hex[:6]}"
    _equipment_session.add_all(
        [
            RepairRecord(
                workshop_code=code,
                record_id=f"{code}-1",
                equipment_text="离心泵A",
                repaired_at=date(2026, 11, 20),
                fault_desc="泄漏",
                result="正常运行",
                person_text="张三",
            ),
            RepairRecord(
                workshop_code=code,
                record_id=f"{code}-2",
                equipment_text="离心泵A",
                repaired_at=date(2026, 11, 18),
                fault_desc="异响",
                result="待观察",
            ),
            RepairRecord(
                workshop_code=code,
                record_id=f"{code}-3",
                equipment_text="薄膜蒸发器 4",
                repaired_at=date(2026, 11, 19),
                fault_desc="密封泄漏",
                result="正常运行",
            ),
        ]
    )
    await _equipment_session.flush()

    records = await client.get(f"/api/v1/equipment/repair/records?workshop={code}")
    assert records.status_code == 200
    body = records.json()
    assert body["meta"]["total"] == 3
    # 维修日期倒序
    assert [item["equipment_text"] for item in body["data"]] == [
        "离心泵A",
        "薄膜蒸发器 4",
        "离心泵A",
    ]
    assert body["data"][0]["repaired_at"] == "2026-11-20"
    assert body["data"][0]["person_text"] == "张三"

    filtered = await client.get(
        f"/api/v1/equipment/repair/records?workshop={code}&equipment=薄膜蒸发器 4"
    )
    assert filtered.status_code == 200
    assert filtered.json()["meta"]["total"] == 1

    frequency = await client.get(f"/api/v1/equipment/repair/frequency?workshop={code}")
    assert frequency.status_code == 200
    assert frequency.json()["data"] == [
        {"equipment_text": "离心泵A", "times": 2, "last_repaired_at": "2026-11-20"},
        {
            "equipment_text": "薄膜蒸发器 4",
            "times": 1,
            "last_repaired_at": "2026-11-19",
        },
    ]

    results = await client.get(f"/api/v1/equipment/repair/results?workshop={code}")
    assert results.status_code == 200
    assert set(results.json()["data"]) == {"正常运行", "待观察"}

    status = await client.get(f"/api/v1/equipment/repair/sync-status?workshop={code}")
    assert status.status_code == 200
    assert status.json()["data"]["enabled"] is False
