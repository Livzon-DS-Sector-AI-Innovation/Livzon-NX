"""Legacy route tasks use the same current completion service as equipment tasks."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.equipment.service import inspection, inspection_feishu, spare_part_sync


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["_cmd_submit", "_cmd_skip"])
async def test_legacy_route_finishes_through_current_service(monkeypatch, command):
    db = SimpleNamespace(commit=AsyncMock())

    @asynccontextmanager
    async def session_factory():
        yield db

    task_id, equipment_id = uuid4(), uuid4()
    monkeypatch.setattr(inspection_feishu, "async_session_factory", session_factory)
    monkeypatch.setattr(
        inspection_feishu,
        "get_current_equipment",
        lambda _: {
            "equipment_id": str(equipment_id),
            "equipment_name": "泵",
        },
    )
    for name in [
        "mark_equipment_completed",
        "mark_equipment_skipped",
        "clear_session",
        "send_user_card",
        "_reply_text",
    ]:
        monkeypatch.setattr(inspection_feishu, name, AsyncMock())
    monkeypatch.setattr(
        inspection_feishu, "advance_to_next_equipment", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(inspection, "submit_equipment_check", AsyncMock())
    monkeypatch.setattr(inspection, "skip_equipment_check", AsyncMock())
    complete = AsyncMock(return_value=SimpleNamespace(overall_result="正常"))
    monkeypatch.setattr(inspection, "complete_task", complete)
    await getattr(inspection_feishu, command)(
        "test_open_id",
        {
            "task_id": str(task_id),
            "plan_type": "线路巡检",
            "task_no": "IT-test",
            "pending_results": [{"template_item_id": str(uuid4()), "result": "正常"}],
        },
    )
    complete.assert_awaited_once_with(db, task_id)
    inspection_feishu._reply_text.assert_not_awaited()
    inspection_feishu.send_user_card.assert_awaited_once()


@pytest.mark.asyncio
async def test_fractional_stock_is_rejected_before_database_writes(monkeypatch):
    monkeypatch.setattr(
        spare_part_sync.warehouse_public_api,
        "get_material_page_rows",
        AsyncMock(
            return_value=(
                [{"物料编号": "fractional", "结存量": "1.25"}],
                None,
            )
        ),
    )
    db = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock())
    with pytest.raises(AppException) as error:
        await spare_part_sync.sync_workshop(db, "101-1")
    assert error.value.status_code == 422
    db.execute.assert_not_awaited()
    db.flush.assert_not_awaited()
