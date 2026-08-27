"""Incremental sync tests for warehouse feishu → local data sync.

Covers:
- duplicate source_record_id sync updates in place (no row duplication)
- feishu-side record deletion is soft-deleted locally after sync
- inventory tables upsert from summary pages (raw/packaging/product)

Tests run against a shared dev DB but every write is rolled back after the
test (conftest commit is a no-op). Assertions are scoped to records created
inside each test to stay isolated from pre-existing data.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.modules.warehouse.models import (
    MaterialPageRow,
    RawMaterialInventory,
)
from app.modules.warehouse.schemas import WarehouseFeishuColumn
from app.modules.warehouse.service import WarehouseService


async def _create_snapshot(service: WarehouseService, page_key: str, table_id: str):
    return await service.repo.upsert_material_page_snapshot(
        page_key=page_key,
        page_title=page_key,
        table_name=page_key,
        table_id=table_id,
        columns=[{"key": "物料名称", "title": "物料名称"}],
        total_rows=0,
        source="test",
        last_synced_at=datetime.now(UTC),
    )


async def _sync_rows(
    service: WarehouseService,
    page_key: str,
    records: list[dict],
) -> None:
    """模拟 fetch_material_page_from_feishu 返回数据并走增量同步。"""
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None

    now = datetime.now(UTC)
    row_models = []
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        record_id = str(record.get("__record_id"))
        if record_id in seen:
            continue
        seen.add(record_id)
        row_models.append(
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id=record_id,
                row_order=index,
                cells={k: v for k, v in record.items() if k != "__record_id"},
                search_text=str(record.get("物料名称", "")),
                last_synced_at=now,
            )
        )
    await service.repo.upsert_material_page_rows(snapshot.id, row_models)


async def _all_page_rows(
    service: WarehouseService, page_key: str
) -> list[MaterialPageRow]:
    """查询某快照下全部行（含软删）。"""
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None
    result = await service.repo.session.execute(
        select(MaterialPageRow).where(MaterialPageRow.page_snapshot_id == snapshot.id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_duplicate_sync_updates_in_place(db_session) -> None:
    """重复同步同一 source_record_id 不翻倍，仅更新字段。"""
    service = WarehouseService(db_session)
    page_key = "incr-test-raw-ledger"
    await _create_snapshot(service, page_key, "tbl-incr-1")

    await _sync_rows(
        service,
        page_key,
        [
            {"__record_id": "rec-1", "物料名称": "物料A"},
            {"__record_id": "rec-2", "物料名称": "物料B"},
        ],
    )
    rows = await _all_page_rows(service, page_key)
    assert len(rows) == 2
    assert all(not row.is_deleted for row in rows)

    # 重复同步：rec-1 内容变化，rec-2 不变；不应新增行
    await _sync_rows(
        service,
        page_key,
        [
            {"__record_id": "rec-1", "物料名称": "物料A-改"},
            {"__record_id": "rec-2", "物料名称": "物料B"},
        ],
    )
    rows = await _all_page_rows(service, page_key)
    assert len(rows) == 2
    cells_by_id = {row.source_record_id: row.cells for row in rows}
    assert cells_by_id["rec-1"]["物料名称"] == "物料A-改"


@pytest.mark.asyncio
async def test_feishu_delete_soft_deletes_locally(db_session) -> None:
    """飞书侧删除记录后同步，本地对应行 is_deleted=True。"""
    service = WarehouseService(db_session)
    page_key = "incr-test-packaging-ledger"
    await _create_snapshot(service, page_key, "tbl-incr-2")

    await _sync_rows(
        service,
        page_key,
        [
            {"__record_id": "rec-a", "物料名称": "包材A"},
            {"__record_id": "rec-b", "物料名称": "包材B"},
        ],
    )
    assert len(await _all_page_rows(service, page_key)) == 2

    # 飞书删除 rec-a：仅同步 rec-b
    await _sync_rows(
        service,
        page_key,
        [{"__record_id": "rec-b", "物料名称": "包材B"}],
    )
    rows = await _all_page_rows(service, page_key)
    assert len(rows) == 2  # 含软删
    by_id = {row.source_record_id: row for row in rows}
    assert by_id["rec-a"].is_deleted is True
    assert by_id["rec-b"].is_deleted is False


@pytest.mark.asyncio
async def test_inventory_upsert_from_summary(db_session) -> None:
    """库存表 upsert：重复同步同一 import_key 更新而非翻倍。"""
    service = WarehouseService(db_session)

    await service.upsert_raw_material_snapshot(
        source_id="rec-incr-r1",
        code="YS-INCR-001",
        name="增量测试原料",
        spec="25kg",
        unit="kg",
        available=100.0,
        safety=50.0,
        last_month=0,
        two_months_ago=0,
        today_balance=100.0,
        front_stock=100.0,
        this_month_use=0,
        warning="",
        product_line="FA",
        erp_no=None,
        delivery=None,
        remark=None,
        source="feishu_bitable",
    )
    # 重复同步同一 import_key → 更新而非新增
    await service.upsert_raw_material_snapshot(
        source_id="rec-incr-r1",
        code="YS-INCR-001",
        name="增量测试原料",
        spec="25kg",
        unit="kg",
        available=80.0,
        safety=50.0,
        last_month=0,
        two_months_ago=0,
        today_balance=80.0,
        front_stock=80.0,
        this_month_use=0,
        warning="",
        product_line="FA",
        erp_no=None,
        delivery=None,
        remark=None,
        source="feishu_bitable",
    )

    # 按 code 精确查询本次写入的记录
    result = await db_session.execute(
        select(RawMaterialInventory).where(RawMaterialInventory.code == "YS-INCR-001")
    )
    matches = list(result.scalars().all())
    assert len(matches) == 1
    assert matches[0].available == 80.0
    assert matches[0].source == "feishu_bitable"


@pytest.mark.asyncio
async def test_sync_inventory_from_feishu_page_isolation(
    db_session, monkeypatch
) -> None:
    """sync_inventory_from_feishu 单页失败不阻断其他页。"""
    service = WarehouseService(db_session)

    async def fake_fetch(page_key: str):
        if page_key == "raw-summary":
            raise RuntimeError("feishu down")
        if page_key == "packaging-summary":
            return (
                None,
                [
                    WarehouseFeishuColumn(key="物料名称", title="物料名称"),
                    WarehouseFeishuColumn(key="规格", title="规格"),
                    WarehouseFeishuColumn(key="单位", title="单位"),
                    WarehouseFeishuColumn(key="可用库存", title="可用库存"),
                    WarehouseFeishuColumn(
                        key="安全库存（30天）", title="安全库存（30天）"
                    ),
                    WarehouseFeishuColumn(key="本日结存", title="本日结存"),
                    WarehouseFeishuColumn(key="前台库存", title="前台库存"),
                    WarehouseFeishuColumn(key="预警", title="预警"),
                    WarehouseFeishuColumn(key="使用产品/类别", title="使用产品/类别"),
                    WarehouseFeishuColumn(key="ERP编号", title="ERP编号"),
                ],
                [
                    {
                        "__record_id": "rec-incr-pack-1",
                        "物料名称": "增量包材X",
                        "规格": "A",
                        "单位": "个",
                        "可用库存": 10.0,
                        "安全库存（30天）": 5.0,
                        "本日结存": 10.0,
                        "前台库存": 10.0,
                        "预警": "",
                        "使用产品/类别": "MC",
                        "ERP编号": None,
                    }
                ],
                {},
            )
        # product-summary
        return (
            None,
            [
                WarehouseFeishuColumn(key="产品名称", title="产品名称"),
                WarehouseFeishuColumn(key="包装规格", title="包装规格"),
                WarehouseFeishuColumn(key="单位", title="单位"),
                WarehouseFeishuColumn(key="剩余量", title="剩余量"),
            ],
            [
                {
                    "__record_id": "rec-incr-prod-1",
                    "产品名称": "增量成品Y",
                    "包装规格": "25kg/桶",
                    "单位": "kg",
                    "剩余量": 99.0,
                }
            ],
            {},
        )

    monkeypatch.setattr(service, "fetch_material_page_from_feishu", fake_fetch)

    result = await service.sync_inventory_from_feishu()
    assert result["raw-summary"] == 0  # 失败页计 0，不抛异常
    assert result["packaging-summary"] == 1
    assert result["product-summary"] == 1

    from app.modules.warehouse.models import (
        PackagingMaterialInventory,
        ProductInventory,
    )

    # 包材 name 精确匹配
    pkg_result = await db_session.execute(
        select(PackagingMaterialInventory).where(
            PackagingMaterialInventory.name == "增量包材X"
        )
    )
    pkg_items = list(pkg_result.scalars().all())
    assert len(pkg_items) == 1
    assert pkg_items[0].source == "feishu_bitable"

    prod_result = await db_session.execute(
        select(ProductInventory).where(ProductInventory.name == "增量成品Y")
    )
    prod_items = list(prod_result.scalars().all())
    assert len(prod_items) == 1
    assert prod_items[0].remaining_quantity == 99.0
