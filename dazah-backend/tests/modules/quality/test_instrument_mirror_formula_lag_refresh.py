"""仪器镜像公式列迟到值补刷测试（创建/编辑写穿后延迟重拉单条）。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

import app.modules.quality.api.inspection_feishu_crud as crud_api


@pytest.fixture(autouse=True)
def _short_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crud_api, "_FORMULA_LAG_REFRESH_DELAYS", (0.0, 0.0))
    crud_api._MIRROR_REFRESH_TASKS.clear()
    yield
    crud_api._MIRROR_REFRESH_TASKS.clear()


@pytest.mark.asyncio
async def test_instrument_write_through_schedules_delayed_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_mock = AsyncMock()
    monkeypatch.setattr(crud_api, "_sync_single_record_to_mirror", sync_mock)

    await crud_api._maybe_refresh_entity_mirror(
        "qc_instr_cal_external", "rec_formula_lag"
    )
    # 等待调度出来的补刷任务执行完毕
    await asyncio.gather(
        *list(crud_api._MIRROR_REFRESH_TASKS), return_exceptions=True
    )

    # 初始写穿 + 2 次延迟补刷（补公式列迟到值）
    assert sync_mock.await_count == 3
    for call in sync_mock.await_args_list:
        assert call.args[0] == "qc_instr_cal_external"
        assert call.args[1] == "rec_formula_lag"
        assert call.kwargs.get("deleted") in (None, False)


@pytest.mark.asyncio
async def test_instrument_delete_does_not_schedule_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_mock = AsyncMock()
    monkeypatch.setattr(crud_api, "_sync_single_record_to_mirror", sync_mock)

    await crud_api._maybe_refresh_entity_mirror(
        "qc_instr_cal_external", "rec_gone", deleted=True
    )
    await asyncio.sleep(0)

    assert sync_mock.await_count == 1
    assert not list(crud_api._MIRROR_REFRESH_TASKS)


@pytest.mark.asyncio
async def test_non_instrument_entity_does_not_schedule_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_mock = AsyncMock()
    monkeypatch.setattr(crud_api, "_sync_single_record_to_mirror", sync_mock)
    material_code = next(iter(crud_api.MATERIAL_MIRROR_ENTITIES))

    await crud_api._maybe_refresh_entity_mirror(material_code, "rec_material")
    await asyncio.sleep(0)

    assert sync_mock.await_count == 1
    assert not list(crud_api._MIRROR_REFRESH_TASKS)
