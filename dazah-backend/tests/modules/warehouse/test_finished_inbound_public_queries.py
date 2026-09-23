"""成品入库汇总与批次明细查询（FL 看板联动）测试。

覆盖 public_api 新增能力的核心分支：
- 总账快照未建立时 get_finished_inbound_summary 返回 None
- 日期区间按北京时间毫秒闭区间下推给仓储聚合（口径与 KG 汇总一致）
- 明细快照未建立时 get_finished_inbound_batches 返回 None
- 批号清洗（去空格/大写/全角连字符）、空批号跳过
- 入库日期毫秒解析为北京时间日期，异常值降级 None
- 数量解析四舍五入到两位，非数值降级 None；确认位兼容 bool 与文本
"""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.modules.warehouse.feishu_material_pages import (
    FINISHED_INBOUND_DATE_FIELD,
    FINISHED_INBOUND_DETAIL_BATCH_FIELD,
    FINISHED_INBOUND_DETAIL_CONFIRM_FIELD,
    FINISHED_INBOUND_DETAIL_PAGE_KEY,
    FINISHED_INBOUND_DETAIL_QTY_FIELD,
    FINISHED_INBOUND_KG_FIELD,
    FINISHED_INBOUND_LEDGER_PAGE_KEY,
    FINISHED_INBOUND_PRODUCT_FIELD,
)
from app.modules.warehouse.service import WarehouseService

PRODUCT = "氟苯尼考预混剂"


def _service_with_repo() -> tuple[WarehouseService, AsyncMock]:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = AsyncMock()
    return service, service.repo


async def test_summary_returns_none_when_ledger_snapshot_missing() -> None:
    """总账快照从未同步成功时按无数据处理，不抛错。"""
    service, repo = _service_with_repo()
    repo.get_material_page_snapshot = AsyncMock(return_value=None)

    result = await service.get_finished_inbound_summary(
        product_name=PRODUCT,
        start_date=dt.date(2026, 9, 1),
        end_date=dt.date(2026, 9, 30),
    )

    assert result is None
    repo.aggregate_finished_inbound.assert_not_awaited()


async def test_summary_pushes_beijing_ms_range_and_returns_aggregate() -> None:
    """闭区间日期按北京时间零点换算毫秒下推，聚合结果原样返回。"""
    service, repo = _service_with_repo()
    snapshot = SimpleNamespace(id=uuid4())
    repo.get_material_page_snapshot = AsyncMock(return_value=snapshot)
    repo.aggregate_finished_inbound = AsyncMock(return_value=(3, 5950.5))

    result = await service.get_finished_inbound_summary(
        product_name=PRODUCT,
        start_date=dt.date(2026, 9, 1),
        end_date=dt.date(2026, 9, 30),
    )

    assert result == (3, 5950.5)
    repo.get_material_page_snapshot.assert_awaited_once_with(
        FINISHED_INBOUND_LEDGER_PAGE_KEY
    )
    kwargs = repo.aggregate_finished_inbound.await_args.kwargs
    assert kwargs["product_field"] == FINISHED_INBOUND_PRODUCT_FIELD
    assert kwargs["product_name"] == PRODUCT
    assert kwargs["date_field"] == FINISHED_INBOUND_DATE_FIELD
    assert kwargs["kg_field"] == FINISHED_INBOUND_KG_FIELD
    # 2026-09-01/09-30 北京时间零点对应的毫秒时间戳
    assert kwargs["start_ms"] == 1788192000000
    assert kwargs["end_ms"] == 1790697600000


async def test_batches_returns_none_when_detail_snapshot_missing() -> None:
    """明细快照未建立时返回 None，调用方按无入库处理。"""
    service, repo = _service_with_repo()
    repo.get_material_page_snapshot = AsyncMock(return_value=None)

    result = await service.get_finished_inbound_batches(product_name=PRODUCT)

    assert result is None
    repo.list_finished_inbound_cells.assert_not_awaited()


async def test_batches_parses_cells_with_normalization_and_fallbacks() -> None:
    """批号清洗、日期/数量/确认位解析与脏数据降级。"""
    service, repo = _service_with_repo()
    repo.get_material_page_snapshot = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    # 1788202800000 = 北京时间 2026-09-01 03:00
    repo.list_finished_inbound_cells = AsyncMock(
        return_value=[
            {
                FINISHED_INBOUND_PRODUCT_FIELD: PRODUCT,
                FINISHED_INBOUND_DETAIL_BATCH_FIELD: " fl-2609001－A ",
                FINISHED_INBOUND_DATE_FIELD: 1788202800000,
                FINISHED_INBOUND_DETAIL_QTY_FIELD: "1980.556",
                FINISHED_INBOUND_DETAIL_CONFIRM_FIELD: "true",
            },
            {
                FINISHED_INBOUND_PRODUCT_FIELD: PRODUCT,
                FINISHED_INBOUND_DETAIL_BATCH_FIELD: None,
            },
            {
                FINISHED_INBOUND_PRODUCT_FIELD: PRODUCT,
                FINISHED_INBOUND_DETAIL_BATCH_FIELD: "FL-2609002",
                FINISHED_INBOUND_DATE_FIELD: "not-a-number",
                FINISHED_INBOUND_DETAIL_QTY_FIELD: "abc",
                FINISHED_INBOUND_DETAIL_CONFIRM_FIELD: False,
            },
        ]
    )

    batches = await service.get_finished_inbound_batches(product_name=PRODUCT)

    repo.get_material_page_snapshot.assert_awaited_once_with(
        FINISHED_INBOUND_DETAIL_PAGE_KEY
    )
    assert batches == [
        {
            "batch_no": "FL-2609001-A",
            "inbound_date": dt.date(2026, 9, 1),
            "qty": 1980.56,
            "confirmed": True,
        },
        {
            "batch_no": "FL-2609002",
            "inbound_date": None,
            "qty": None,
            "confirmed": False,
        },
    ]
