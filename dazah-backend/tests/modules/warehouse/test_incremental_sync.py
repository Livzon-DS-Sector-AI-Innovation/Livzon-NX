"""仓储飞书 → 本地增量同步测试。

Covers:
- 重复同步同一 source_record_id 原地更新（不翻倍）
- 全量同步对飞书侧删除做本地软删
- 增量 upsert 不软删未变更的历史行、不复活已软删行
- 无日期排序字段的页面增量回退全量
- 增量拉取按水线早停（不翻完整大表）
- sync_material_page_to_local 依据前次快照选择增量/全量
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.feishu_material_pages import FEISHU_WAREHOUSE_MATERIAL_PAGES
from app.modules.warehouse.models import MaterialPageRow
from app.modules.warehouse.service import WarehouseService


async def _create_snapshot(
    service: WarehouseService, page_key: str, table_id: str
) -> None:
    await service.repo.upsert_material_page_snapshot(
        page_key=page_key,
        page_title=page_key,
        table_name=page_key,
        table_id=table_id,
        columns=[{"key": "物料名称", "title": "物料名称"}],
        total_rows=0,
        source="test",
        last_synced_at=datetime.now(UTC),
    )


def _row_models(
    snapshot_id: object,
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[MaterialPageRow]:
    now = now or datetime.now(UTC)
    models: list[MaterialPageRow] = []
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        record_id = str(record.get("__record_id"))
        if record_id in seen:
            continue
        seen.add(record_id)
        models.append(
            MaterialPageRow(
                page_snapshot_id=snapshot_id,
                source_record_id=record_id,
                row_order=index,
                cells={k: v for k, v in record.items() if k != "__record_id"},
                search_text=str(record.get("物料名称", "")),
                last_synced_at=now,
            )
        )
    return models


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


async def test_duplicate_sync_updates_in_place(
    db_session: AsyncSession,
) -> None:
    """重复同步同一 source_record_id 不翻倍，仅更新字段。"""
    service = WarehouseService(db_session)
    page_key = "incr-test-duplicate"
    await _create_snapshot(service, page_key, "tbl-incr-1")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None

    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(
            snapshot.id,
            [
                {"__record_id": "rec-1", "物料名称": "物料A"},
                {"__record_id": "rec-2", "物料名称": "物料B"},
            ],
        ),
    )
    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(
            snapshot.id,
            [
                {"__record_id": "rec-1", "物料名称": "物料A-改"},
                {"__record_id": "rec-2", "物料名称": "物料B"},
            ],
        ),
    )
    rows = await _all_page_rows(service, page_key)
    assert len(rows) == 2
    cells_by_id = {row.source_record_id: row.cells for row in rows}
    assert cells_by_id["rec-1"]["物料名称"] == "物料A-改"


async def test_full_sync_soft_deletes_remote_removed_rows(
    db_session: AsyncSession,
) -> None:
    """全量同步：本地有但本次未传入的记录被软删（对账删除）。"""
    service = WarehouseService(db_session)
    page_key = "incr-test-full-delete"
    await _create_snapshot(service, page_key, "tbl-incr-2")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None

    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(
            snapshot.id,
            [
                {"__record_id": "rec-1", "物料名称": "物料A"},
                {"__record_id": "rec-2", "物料名称": "物料B"},
            ],
        ),
    )
    # 全量：飞书侧只剩 rec-1
    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(snapshot.id, [{"__record_id": "rec-1", "物料名称": "物料A"}]),
    )
    rows = await _all_page_rows(service, page_key)
    by_id = {row.source_record_id: row for row in rows}
    assert by_id["rec-1"].is_deleted is False
    assert by_id["rec-2"].is_deleted is True


async def test_incremental_upsert_keeps_unchanged_rows(
    db_session: AsyncSession,
) -> None:
    """增量 upsert：未传入的历史行保持原状，不误标软删。"""
    service = WarehouseService(db_session)
    page_key = "incr-test-keep-rows"
    await _create_snapshot(service, page_key, "tbl-incr-3")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None

    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(
            snapshot.id,
            [
                {"__record_id": "rec-1", "物料名称": "物料A"},
                {"__record_id": "rec-2", "物料名称": "物料B"},
                {"__record_id": "rec-3", "物料名称": "物料C"},
            ],
        ),
    )
    # 增量：只传入 rec-1 的变更，rec-2 / rec-3 不在本次拉取结果里
    await service.repo.upsert_material_page_rows_incremental(
        snapshot.id,
        _row_models(snapshot.id, [{"__record_id": "rec-1", "物料名称": "物料A-改"}]),
    )
    rows = await _all_page_rows(service, page_key)
    assert len(rows) == 3
    by_id = {row.source_record_id: row for row in rows}
    assert all(row.is_deleted is False for row in rows)
    assert by_id["rec-1"].cells["物料名称"] == "物料A-改"
    assert by_id["rec-2"].cells["物料名称"] == "物料B"


async def test_incremental_upsert_does_not_resurrect_soft_deleted(
    db_session: AsyncSession,
) -> None:
    """增量 upsert：已软删记录不因飞书侧仍返回而复活。"""
    service = WarehouseService(db_session)
    page_key = "incr-test-no-resurrect"
    await _create_snapshot(service, page_key, "tbl-incr-4")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None

    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(snapshot.id, [{"__record_id": "rec-1", "物料名称": "物料A"}]),
    )
    await service.repo.upsert_material_page_rows(
        snapshot.id, _row_models(snapshot.id, [])
    )
    rows = await _all_page_rows(service, page_key)
    assert rows[0].is_deleted is True

    # 增量又拉到该记录（飞书删除未生效场景）：保持软删
    await service.repo.upsert_material_page_rows_incremental(
        snapshot.id,
        _row_models(snapshot.id, [{"__record_id": "rec-1", "物料名称": "物料A"}]),
    )
    rows = await _all_page_rows(service, page_key)
    assert len(rows) == 1
    assert rows[0].is_deleted is True


async def test_incremental_fetch_falls_back_without_sort_field(
    db_session: AsyncSession,
) -> None:
    """无日期排序字段的页面（hardware-summary）增量回退全量拉取。"""
    service = WarehouseService(db_session)
    full_mock = AsyncMock()
    with patch.object(
        WarehouseService, "fetch_material_page_from_feishu", new=full_mock
    ):
        await service.fetch_material_page_from_feishu_incremental(
            "hardware-summary",
            last_synced_at=datetime.now(UTC),
        )
    full_mock.assert_awaited_once_with("hardware-summary")


async def test_incremental_fetch_dual_route_single_page_dedup(
    db_session: AsyncSession,
) -> None:
    """records/search 无 filter 翻页失效（实测）：增量每路只取一页。

    - has_more/page_token 不再触发后续请求（共 2 次：业务日期 + 修改时间）
    - 两路记录按 record_id 去重合并
    """
    service = WarehouseService(db_session)
    service.feishu_client = AsyncMock()
    watermark = datetime.now(UTC) - timedelta(minutes=10)
    last_synced_ms = int(watermark.timestamp() * 1000)

    service.feishu_client.request = AsyncMock(
        side_effect=[
            {  # 路一：业务日期降序第一页（含 1 条新增）
                "items": [
                    {
                        "record_id": "rec-new",
                        "fields": {"入库日期": last_synced_ms + 60_000},
                    }
                ],
                # 复现翻页失效场景：仍返回 token，但不得再发请求
                "has_more": True,
                "page_token": "tok-2",
            },
            {  # 路二：last_modified_time 降序第一页（1 条重复 + 1 条新增）
                "items": [
                    {
                        "record_id": "rec-new",
                        "fields": {"入库日期": last_synced_ms + 60_000},
                    },
                    {
                        "record_id": "rec-modified",
                        "fields": {"入库日期": last_synced_ms - 3_600_000},
                        "last_modified_time": last_synced_ms + 30_000,
                    },
                ],
                "has_more": True,
            },
        ]
    )

    items = await service.fetch_feishu_table_records_incremental(
        app_token="app-x",
        table_id="tbl-x",
        page_size=500,
        sort_field="入库日期",
        last_synced_at=watermark,
    )

    assert [item["record_id"] for item in items] == ["rec-new", "rec-modified"]
    assert service.feishu_client.request.await_count == 2
    first_body = service.feishu_client.request.await_args_list[0].kwargs["json_body"]
    second_body = service.feishu_client.request.await_args_list[1].kwargs["json_body"]
    assert first_body["sort"][0]["field_name"] == "入库日期"
    assert second_body["sort"][0]["field_name"] == "last_modified_time"


async def test_incremental_fetch_no_changes_returns_empty(
    db_session: AsyncSession,
) -> None:
    """两路页面内所有记录都早于水线：返回空列表（零写库）。"""
    service = WarehouseService(db_session)
    service.feishu_client = AsyncMock()
    watermark = datetime.now(UTC) - timedelta(minutes=10)
    last_synced_ms = int(watermark.timestamp() * 1000)
    service.feishu_client.request = AsyncMock(
        side_effect=[
            {
                "items": [
                    {
                        "record_id": "rec-old",
                        "fields": {"入库日期": last_synced_ms - 1_000},
                    }
                ],
                "has_more": False,
            },
            {
                "items": [
                    {
                        "record_id": "rec-old-2",
                        "fields": {},
                        "last_modified_time": last_synced_ms - 1_000,
                    }
                ],
                "has_more": False,
            },
        ]
    )

    items = await service.fetch_feishu_table_records_incremental(
        app_token="app-x",
        table_id="tbl-x",
        page_size=500,
        sort_field="入库日期",
        last_synced_at=watermark,
    )

    assert items == []
    assert service.feishu_client.request.await_count == 2


async def test_incremental_fetch_second_route_error_tolerated(
    db_session: AsyncSession,
) -> None:
    """last_modified_time 排序不被支持（请求报错）时只返回路一结果。"""
    service = WarehouseService(db_session)
    service.feishu_client = AsyncMock()
    watermark = datetime.now(UTC) - timedelta(minutes=10)
    last_synced_ms = int(watermark.timestamp() * 1000)
    service.feishu_client.request = AsyncMock(
        side_effect=[
            {
                "items": [
                    {
                        "record_id": "rec-new",
                        "fields": {"入库日期": last_synced_ms + 60_000},
                    }
                ],
                "has_more": False,
            },
            RuntimeError("InvalidField: last_modified_time"),
        ]
    )

    items = await service.fetch_feishu_table_records_incremental(
        app_token="app-x",
        table_id="tbl-x",
        page_size=500,
        sort_field="入库日期",
        last_synced_at=watermark,
    )

    assert [item["record_id"] for item in items] == ["rec-new"]


async def test_sync_chooses_incremental_when_snapshot_exists(
    db_session: AsyncSession,
) -> None:
    """有前次快照且页面有日期字段时，sync 走增量拉取。"""
    service = WarehouseService(db_session)
    page_key = "product-inbound-detail"
    await _create_snapshot(service, page_key, "tblA5XrTrmoCv9SW")

    incr_mock = AsyncMock(
        return_value=(
            FEISHU_WAREHOUSE_MATERIAL_PAGES[page_key],
            [],
            [],
            {},
        )
    )
    full_mock = AsyncMock()
    with (
        patch.object(
            WarehouseService,
            "fetch_material_page_from_feishu_incremental",
            new=incr_mock,
        ),
        patch.object(
            WarehouseService, "fetch_material_page_from_feishu", new=full_mock
        ),
    ):
        await service.sync_material_page_to_local(page_key, incremental=True)

    incr_mock.assert_awaited_once()
    full_mock.assert_not_awaited()


async def test_sync_falls_back_to_full_without_snapshot(
    db_session: AsyncSession,
) -> None:
    """无前次快照（首跑）时即使 incremental=True 也走全量。"""
    service = WarehouseService(db_session)
    page_key = "product-outbound-ledger"
    service.repo.get_material_page_snapshot = AsyncMock(return_value=None)

    full_mock = AsyncMock(
        return_value=(
            FEISHU_WAREHOUSE_MATERIAL_PAGES[page_key],
            [],
            [],
            {},
        )
    )
    incr_mock = AsyncMock()
    with (
        patch.object(
            WarehouseService, "fetch_material_page_from_feishu", new=full_mock
        ),
        patch.object(
            WarehouseService,
            "fetch_material_page_from_feishu_incremental",
            new=incr_mock,
        ),
    ):
        await service.sync_material_page_to_local(page_key, incremental=True)

    full_mock.assert_awaited_once()
    incr_mock.assert_not_awaited()


async def test_sync_incremental_updates_snapshot_total_rows(
    db_session: AsyncSession,
) -> None:
    """增量同步后快照 total_rows 记录本地存量（而非本批变更行数）。"""
    service = WarehouseService(db_session)
    page_key = "product-inbound-detail"
    await _create_snapshot(service, page_key, "tblA5XrTrmoCv9SW")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None
    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(
            snapshot.id,
            [
                {"__record_id": "rec-1", "物料名称": "物料A"},
                {"__record_id": "rec-2", "物料名称": "物料B"},
            ],
        ),
    )

    incr_mock = AsyncMock(
        return_value=(
            FEISHU_WAREHOUSE_MATERIAL_PAGES[page_key],
            [],
            [{"__record_id": "rec-3", "物料名称": "物料C"}],
            {},
        )
    )
    with patch.object(
        WarehouseService,
        "fetch_material_page_from_feishu_incremental",
        new=incr_mock,
    ):
        response = await service.sync_material_page_to_local(page_key, incremental=True)

    rows = await _all_page_rows(service, page_key)
    assert len([row for row in rows if not row.is_deleted]) == 3
    refreshed = await service.repo.get_material_page_snapshot(page_key)
    assert refreshed is not None
    assert refreshed.total_rows == 3
    assert response.total == 3
