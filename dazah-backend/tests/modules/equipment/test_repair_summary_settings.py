"""检修汇总全厂默认设置：读取、保存、恢复与权限。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models.repair_ledger import RepairSummarySettings
from app.modules.equipment.service import repair_ledger as service
from app.modules.equipment.service import workshop as workshop_service


async def _purge(db: AsyncSession) -> None:
    # 不能 rollback：client 共用会话里的测试用户尚未提交，回滚会触发 updated_by 外键失败
    await db.execute(delete(RepairSummarySettings))
    await db.commit()


async def test_settings_defaults_update_and_reset(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        workshop_service,
        "list_enabled",
        AsyncMock(
            return_value=[SimpleNamespace(code="102-1", name="102一车间")]
        ),
    )
    await _purge(db_session)
    try:
        defaults = await service.get_summary_settings(db_session)
        assert defaults == {
            "sort_field": "workshop",
            "sort_order": "ascend",
            "range_key": "30d",
            "workshops": None,
            "updated_by_name": None,
            "updated_at": None,
        }

        updated = await service.update_summary_settings(
            db_session,
            sort_field="repair_count",
            sort_order="descend",
            range_key="90d",
            workshops=["102-1", "not-exist"],
            updated_by=None,
        )
        # 不存在的车间被过滤掉
        assert updated["workshops"] == ["102-1"]
        assert updated["sort_field"] == "repair_count"
        assert updated["sort_order"] == "descend"
        assert updated["range_key"] == "90d"

        read_back = await service.get_summary_settings(db_session)
        assert read_back["sort_field"] == "repair_count"
        assert read_back["workshops"] == ["102-1"]

        reset = await service.reset_summary_settings(
            db_session, updated_by=None
        )
        assert reset["sort_field"] == "workshop"
        assert reset["sort_order"] == "ascend"
        assert reset["range_key"] == "30d"
        assert reset["workshops"] is None
    finally:
        await _purge(db_session)


async def test_settings_reject_invalid_values(db_session: AsyncSession) -> None:
    with pytest.raises(AppException, match="排序字段"):
        await service.update_summary_settings(
            db_session,
            sort_field="bad",
            sort_order="ascend",
            range_key="30d",
            workshops=None,
            updated_by=None,
        )


async def test_settings_endpoints_read_save_and_reset(
    _equipment_session: AsyncSession, client: AsyncClient
) -> None:
    await _purge(_equipment_session)
    try:
        response = await client.get(
            "/api/v1/equipment/repair/summary/settings"
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["sort_field"] == "workshop"
        assert payload["range_key"] == "30d"
        assert payload["can_edit"] is True

        saved = await client.put(
            "/api/v1/equipment/repair/summary/settings",
            json={
                "sort_field": "abnormal_count",
                "sort_order": "descend",
                "range_key": "year",
                "workshops": [],
            },
        )
        assert saved.status_code == 200
        assert saved.json()["data"]["sort_field"] == "abnormal_count"
        assert saved.json()["data"]["range_key"] == "year"
        assert saved.json()["data"]["workshops"] is None

        reset = await client.delete(
            "/api/v1/equipment/repair/summary/settings"
        )
        assert reset.status_code == 200
        assert reset.json()["data"]["sort_field"] == "workshop"
        assert reset.json()["data"]["range_key"] == "30d"
    finally:
        await _purge(_equipment_session)


async def test_settings_write_requires_operate_permission(
    _equipment_session: AsyncSession,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "can_edit_summary_settings",
        AsyncMock(return_value=False),
    )
    response = await client.put(
        "/api/v1/equipment/repair/summary/settings",
        json={
            "sort_field": "workshop",
            "sort_order": "ascend",
            "range_key": "30d",
            "workshops": None,
        },
    )
    assert response.status_code == 403
