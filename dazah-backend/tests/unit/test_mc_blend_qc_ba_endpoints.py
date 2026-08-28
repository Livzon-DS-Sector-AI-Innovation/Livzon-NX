"""MC 混粉/QC/BA 台账 端点测试（SQL 全 mock）。"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.modules.production import mc_blend_qc_ba_api as ba


class _Scalars:
    def __init__(self, items: Any) -> None:
        self._items = items

    def all(self) -> Any:
        return self._items


class _Result:
    def __init__(self, items: Any) -> None:
        self._s = _Scalars(items)

    def scalars(self) -> Any:
        return self._s


def _scalars_result(items: Any) -> Any:
    return _Result(items)


@pytest.mark.anyio
async def test_full_list_blending_with_inputs() -> Any:
    """全量混粉台账：month 匹配 + 投入明细嵌套。"""
    record = SimpleNamespace(
        batch_no="MC-250301",
        workshop="201-2",
        blending_ratio="3:2",
    )
    inp = SimpleNamespace(
        blend_batch="MC-250301",
        seq_no=1,
        input_weight=50,
    )
    calls = iter([_scalars_result([record]), _scalars_result([inp])])

    async def fake_exec(stmt: Any, *a: Any, **kw: Any) -> Any:
        return next(calls)

    s = AsyncMock()
    s.execute.side_effect = fake_exec
    resp = await ba.full_list_blending(month=3, workshop="201-2", session=s)
    data = json.loads(resp.body)["data"]
    assert len(data) == 1
    assert data[0]["batch_no"] == "MC-250301"
    assert data[0]["inputs"][0]["input_weight"] == 50


@pytest.mark.anyio
async def test_full_list_blending_empty() -> Any:
    """无记录 → 空列表。"""
    s = AsyncMock()
    s.execute.return_value = _scalars_result([])
    resp = await ba.full_list_blending(month=None, session=s)
    assert json.loads(resp.body)["data"] == []


@pytest.mark.anyio
async def test_create_blending() -> Any:
    """创建混粉记录：add + commit。"""
    s = AsyncMock()
    s.commit = AsyncMock()
    resp = await ba.create_blending(data={"batch_no": "MC-2"}, session=s)
    assert json.loads(resp.body)["message"] == "创建成功"


@pytest.mark.anyio
async def test_update_blending_found_and_missing() -> Any:
    """更新混粉记录：记录存在/不存在两种分支。"""
    s = AsyncMock()
    s.commit = AsyncMock()
    s.get.return_value = SimpleNamespace(id="r2", is_deleted=False, batch_no="MC-2")
    resp = await ba.update_blending(
        UUID("00000000-0000-0000-0000-000000000002"), data={"tank_yield": 10}, session=s
    )
    assert json.loads(resp.body)["message"] == "更新成功"

    s2 = AsyncMock()
    s2.get.return_value = None
    resp2 = await ba.update_blending(
        UUID("00000000-0000-0000-0000-000000000099"), data={}, session=s2
    )
    assert json.loads(resp2.body)["message"] == "记录不存在"


@pytest.mark.anyio
async def test_delete_blending_existing_and_missing() -> Any:
    """删除混粉记录：存在 → 标记删除；不存在 → 记录不存在。"""
    s = AsyncMock()
    s.commit = AsyncMock()
    s.get.return_value = SimpleNamespace(id="r3", is_deleted=False)
    resp = await ba.delete_blending(
        UUID("00000000-0000-0000-0000-000000000003"), session=s
    )
    assert json.loads(resp.body)["message"] == "删除成功"

    s2 = AsyncMock()
    s2.get.return_value = None
    resp2 = await ba.delete_blending(
        UUID("00000000-0000-0000-0000-000000000099"), session=s2
    )
    assert json.loads(resp2.body)["message"] == "记录不存在"


@pytest.mark.anyio
async def test_create_and_delete_blending_input() -> Any:
    """添加/删除混粉投入。"""
    s = AsyncMock()
    s.commit = AsyncMock()
    resp = await ba.create_blending_input(data={"blend_batch": "MC-1"}, session=s)
    assert json.loads(resp.body)["message"] == "添加成功"

    s2 = AsyncMock()
    s2.get.return_value = None
    resp2 = await ba.delete_blending_input(
        UUID("00000000-0000-0000-0000-000000000099"), session=s2
    )
    assert json.loads(resp2.body)["message"] == "记录不存在"


@pytest.mark.anyio
async def test_calculate_blending_impurities_with_inputs() -> Any:
    """加权杂质计算：有投入明细 → 加权求和 + 更新主表 + 超限警告。"""
    inp = SimpleNamespace(
        input_weight=50.0,
        rrt_053=0.06,
        rrt_0755=0.05,
        rrt_094_096=0.1,
        rrt_103_106=0.05,
        rrt_201=0.05,
        total_impurity=0.5,
        content=98.0,
        is_deleted=False,
        blend_batch="MC-1",
    )
    main = SimpleNamespace(
        batch_no="MC-1",
        pack_spec="25kg",
        total_weight=0,
        barrel_count=None,
        status=1,
        is_deleted=False,
    )
    main_res = _main_result(main)

    calls = iter([_scalars_result([inp]), main_res])

    async def fake_exec(stmt: Any, *a: Any, **kw: Any) -> Any:
        return next(calls)

    s = AsyncMock()
    s.execute.side_effect = fake_exec
    s.commit = AsyncMock()
    resp = await ba.calculate_blending_impurities(batch_no="MC-1", session=s)
    data = json.loads(resp.body)["data"]
    assert data["total_weight"] == 50.0
    assert data["impurities"]["rrt_053"] == 0.06
    assert data["warnings"]["rrt_053"] == 0.06
    assert s.commit.called
    # pack_size="50kg" → barrel_count = ceil(50/25)=2
    assert main.barrel_count == 2
    assert main.status == 2


@pytest.mark.anyio
async def test_calculate_no_inputs() -> Any:
    """无投入明细 → 400。"""
    s = AsyncMock()
    s.execute.return_value = _scalars_result([])
    resp = await ba.calculate_blending_impurities(batch_no="X", session=s)
    assert json.loads(resp.body)["code"] == 400


@pytest.mark.anyio
async def test_get_ba_records_cross_table() -> Any:
    """丁酯台账交叉表：日期列、设备行、消耗/入库矩阵。"""
    records = [
        SimpleNamespace(
            check_date=date(2026, 5, 1),
            equipment="1#萃取罐",
            is_check=False,
            is_inbound=False,
            consumption=5.0,
        ),
        SimpleNamespace(
            check_date=date(2026, 5, 2),
            equipment="1#萃取罐",
            is_check=False,
            is_inbound=False,
            consumption=8.0,
        ),
    ]
    s = AsyncMock()
    s.execute.return_value = _scalars_result(records)
    resp = await ba.get_ba_records(session=s)
    data = json.loads(resp.body)["data"]
    assert len(data["dates"]) == 2
    assert "matrix" in data
    assert data["matrix"]["1#萃取罐"]["2026-05-01"] == 5.0


@pytest.mark.anyio
async def test_qc_full_list_and_inputs() -> Any:
    """QC 台账完整列表 + 投入明细列表。"""
    insp = SimpleNamespace(
        batch_no="QC-1",
        input_date=date(2026, 5, 1),
    )
    qc_inp = SimpleNamespace(
        qc_batch="QC-1",
        input_batch="MC-1",
    )
    calls = iter([_scalars_result([insp]), _scalars_result([qc_inp])])

    async def fake_exec(stmt: Any, *a: Any, **kw: Any) -> Any:
        return next(calls)

    s = AsyncMock()
    s.execute.side_effect = fake_exec
    resp = await ba.full_list_qc(month=5, session=s)
    data = json.loads(resp.body)["data"]
    assert len(data) == 1
    assert data[0]["batch_no"] == "QC-1"
    assert data[0]["inputs"][0]["input_batch"] == "MC-1"

    s2 = AsyncMock()
    s2.execute.return_value = _scalars_result([])
    resp2 = await ba.list_qc_inputs(qc_batch="QC-1", session=s2)
    assert json.loads(resp2.body)["data"] == []


def _main_result(obj: Any) -> Any:
    class R:
        def scalar_one_or_none(self) -> Any:
            return obj

    return R()
