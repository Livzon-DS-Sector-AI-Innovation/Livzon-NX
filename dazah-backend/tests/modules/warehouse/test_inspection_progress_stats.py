"""检验进度概览统计（build_inspection_overview）测试。

通过两阶段 upsert（初始 → 出结果）自然生成状态变更日志，
验证 raw（原辅料及包材入库总账）与 product（成品明细按批号关联入库日期）
两个口径的统计数字、起点日过滤与分段时长。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.inspection_progress import (
    FINISHED_PRODUCT_DETAIL_PAGE_KEYS,
    INBOUND_LEDGER_PAGE_KEY,
    PRODUCT_INBOUND_DETAIL_PAGE_KEY,
    build_inspection_overview,
    build_record_inspection_cycle,
    clear_inspection_overview_cache,
    load_page_rows,
)
from app.modules.warehouse.models import (
    MaterialPageRow,
    MaterialStatusTransition,
)
from app.modules.warehouse.service import WarehouseService

CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
_NOW = datetime(2026, 9, 20, 12, 0, tzinfo=CHINA_TIMEZONE)


def _cst_ms(year: int, month: int, day: int, hour: int = 0) -> int:
    local = datetime(year, month, day, hour, tzinfo=CHINA_TIMEZONE).astimezone(UTC)
    return int(local.timestamp() * 1000)


async def _seed_page(
    db_session: AsyncSession, service: WarehouseService, page_key: str
) -> object:
    await db_session.run_sync(
        lambda sync_db: MaterialStatusTransition.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    await service.repo.upsert_material_page_snapshot(
        page_key=page_key,
        page_title=page_key,
        table_name=page_key,
        table_id=f"tbl-{page_key}",
        columns=[],
        total_rows=0,
        source="test",
        last_synced_at=datetime.now(UTC),
    )
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None
    return snapshot.id


def _row(snapshot_id: object, record_id: str, cells: dict[str, Any]) -> MaterialPageRow:
    return MaterialPageRow(
        page_snapshot_id=snapshot_id,
        source_record_id=record_id,
        row_order=1,
        cells=cells,
        search_text=" ".join(str(v) for v in cells.values() if v),
        last_synced_at=datetime.now(UTC),
    )


def _meta(record_id: str, created_ms: int, modified_ms: int | None = None):
    return {
        record_id: {
            "created_ms": created_ms,
            "modified_ms": modified_ms or created_ms,
        }
    }


class _PageSeeder:
    """模拟真实全量同步：每轮携带全部记录（否则 upsert 会软删未携带行）。

    record_meta 只带本轮发生变化的记录；其余行值未变，跳过检测即可。
    """

    def __init__(self, service: WarehouseService, snapshot_id: object, page_key: str):
        self._service = service
        self._snapshot_id = snapshot_id
        self._page_key = page_key
        self._cells: dict[str, dict[str, Any]] = {}

    async def sync(self, record_id: str, cells: dict[str, Any], meta: dict) -> None:
        self._cells[record_id] = cells
        rows = [
            _row(self._snapshot_id, rid, self._cells[rid]) for rid in self._cells
        ]
        await self._service.repo.upsert_material_page_rows(
            self._snapshot_id,
            rows,
            page_key=self._page_key,
            record_meta=meta,
        )


async def _seed_raw(db_session: AsyncSession) -> WarehouseService:
    service = WarehouseService(db_session)
    snapshot_id = await _seed_page(db_session, service, INBOUND_LEDGER_PAGE_KEY)
    seeder = _PageSeeder(service, snapshot_id, INBOUND_LEDGER_PAGE_KEY)

    def cells_ok(result: str | None) -> dict[str, Any]:
        return {
            "入库日期": _cst_ms(2026, 9, 10),
            "物料名称": "玉米淀粉",
            "物料类别": "原辅料类",
            "是否请检": "是",
            "检测结果": result,
            "厂内批号": "YL-100",
        }

    # rec-ok：09-10 入库，09-12 09:00 出合格 → 57h
    await seeder.sync("rec-ok", cells_ok(None), _meta("rec-ok", _cst_ms(2026, 9, 10)))
    await seeder.sync(
        "rec-ok", cells_ok("合格"),
        _meta("rec-ok", _cst_ms(2026, 9, 10), _cst_ms(2026, 9, 12, 9)),
    )

    # rec-bad：09-11 入库（包材类），09-14 00:00 出不合格 → 72h
    await seeder.sync(
        "rec-bad",
        {
            "入库日期": _cst_ms(2026, 9, 11),
            "物料名称": "铝箔袋",
            "物料类别": "包材类",
            "是否请检": "是",
            "检测结果": None,
            "厂内批号": "BC-200",
        },
        _meta("rec-bad", _cst_ms(2026, 9, 11)),
    )
    await seeder.sync(
        "rec-bad",
        {
            "入库日期": _cst_ms(2026, 9, 11),
            "物料名称": "铝箔袋",
            "物料类别": "包材类",
            "是否请检": "是",
            "检测结果": "不合格",
            "厂内批号": "BC-200",
        },
        _meta("rec-bad", _cst_ms(2026, 9, 11), _cst_ms(2026, 9, 14)),
    )

    # rec-pending：09-18 入库，待验中（now 09-20 12:00 → 60h）
    await seeder.sync(
        "rec-pending",
        {
            "入库日期": _cst_ms(2026, 9, 18),
            "物料名称": "乳糖",
            "物料类别": "原辅料类",
            "是否请检": "是",
            "检测结果": None,
            "厂内批号": "YL-300",
        },
        _meta("rec-pending", _cst_ms(2026, 9, 18)),
    )

    # rec-old：起点日（09-09）之前入库的已出结果行 → 不统计
    await seeder.sync(
        "rec-old",
        {
            "入库日期": _cst_ms(2026, 9, 1),
            "物料名称": "旧物料",
            "物料类别": "原辅料类",
            "是否请检": "是",
            "检测结果": "合格",
            "厂内批号": "YL-001",
        },
        _meta("rec-old", _cst_ms(2026, 9, 1)),
    )

    # rec-noreq：请检=否 → 不统计
    await seeder.sync(
        "rec-noreq",
        {
            "入库日期": _cst_ms(2026, 9, 15),
            "物料名称": "试样品",
            "物料类别": "托盘类",
            "是否请检": "否",
            "检测结果": None,
            "厂内批号": "TP-400",
        },
        _meta("rec-noreq", _cst_ms(2026, 9, 15)),
    )
    return service


async def _seed_product(db_session: AsyncSession) -> WarehouseService:
    service = WarehouseService(db_session)
    # 隔离测试库中其他历史用例残留的产品明细行（事务内软删，回滚自动恢复）
    for other_page in FINISHED_PRODUCT_DETAIL_PAGE_KEYS:
        if other_page == "product-detail-lovastatin":
            continue
        for item in await load_page_rows(db_session, other_page):
            item.is_deleted = True
    inbound_snapshot = await _seed_page(
        db_session, service, PRODUCT_INBOUND_DETAIL_PAGE_KEY
    )
    detail_snapshot = await _seed_page(
        db_session, service, "product-detail-lovastatin"
    )
    inbound_seeder = _PageSeeder(
        service, inbound_snapshot, PRODUCT_INBOUND_DETAIL_PAGE_KEY
    )
    detail_seeder = _PageSeeder(service, detail_snapshot, "product-detail-lovastatin")

    # 成品入库明细：批号 → 入库日期
    await inbound_seeder.sync(
        "in-1",
        {
            "入库日期": _cst_ms(2026, 9, 10),
            "入库标签批号": "B-100",
            "产品名称": "洛伐他汀",
        },
        _meta("in-1", _cst_ms(2026, 9, 10)),
    )
    await inbound_seeder.sync(
        "in-2",
        {
            "入库日期": _cst_ms(2026, 9, 15),
            "入库标签批号": "B-200",
            "产品名称": "洛伐他汀",
        },
        _meta("in-2", _cst_ms(2026, 9, 15)),
    )
    # 同前台批号兜底关联
    await inbound_seeder.sync(
        "in-3",
        {
            "入库日期": _cst_ms(2026, 9, 16),
            "对应前台批号": "F-300",
            "产品名称": "洛伐他汀",
        },
        _meta("in-3", _cst_ms(2026, 9, 16)),
    )

    def detail_cells(batch_field: str, batch: str, status: str) -> dict[str, Any]:
        return {batch_field: batch, "产品名称": "洛伐他汀", "质量状态": status}

    # pd-ok：B-100 入库 09-10，09-10 12:00 入待验，09-12 12:00 合格
    #   → 入库→待验 12h，待验→合格 48h，总 60h
    await detail_seeder.sync(
        "pd-ok",
        detail_cells("入库标签批号", "B-100", "待验"),
        _meta("pd-ok", _cst_ms(2026, 9, 10, 12)),
    )
    await detail_seeder.sync(
        "pd-ok",
        detail_cells("入库标签批号", "B-100", "合格"),
        _meta("pd-ok", _cst_ms(2026, 9, 10, 12), _cst_ms(2026, 9, 12, 12)),
    )

    # pd-pending：B-200 入库 09-15，09-15 06:00 入待验，至今（now 09-20 12:00 → 132h）
    await detail_seeder.sync(
        "pd-pending",
        detail_cells("入库标签批号", "B-200", "待验"),
        _meta("pd-pending", _cst_ms(2026, 9, 15, 6)),
    )

    # pd-front：无标签批号，用前台批号 F-300 兜底（入库 09-16）
    await detail_seeder.sync(
        "pd-front",
        detail_cells("对应前台批号", "F-300", "待验"),
        _meta("pd-front", _cst_ms(2026, 9, 16, 8)),
    )

    # pd-no-inbound：批号在入库明细中无匹配 → 跳过
    await detail_seeder.sync(
        "pd-no-inbound",
        detail_cells("入库标签批号", "B-999", "待验"),
        _meta("pd-no-inbound", _cst_ms(2026, 9, 17)),
    )
    return service


async def test_raw_overview_statistics(db_session: AsyncSession) -> None:
    await _seed_raw(db_session)
    clear_inspection_overview_cache()
    payload = await build_inspection_overview(
        db_session, "raw", days=30, now=_NOW
    )

    assert payload["scope"] == "raw"
    assert payload["scope_label"] == "原辅料及包材"
    assert payload["start_date"] == "2026-09-09"

    # 当前待验：仅 rec-pending（60h）
    assert payload["current"]["pending_count"] == 1
    assert payload["current"]["pending_avg_hours"] == 60.0
    assert payload["current"]["pending_max_hours"] == 60.0

    # 近 30 天完成：合格 1（57h）+ 不合格 1（72h）
    window = payload["window"]
    assert window["completed_count"] == 2
    assert window["qualified_count"] == 1
    assert window["unqualified_count"] == 1
    assert window["avg_hours"] == 64.5
    assert window["max_hours"] == 72.0

    # 类别拆分
    breakdown = {item["label"]: item for item in payload["breakdown"]}
    assert breakdown["原辅料类"]["completed_count"] == 1
    assert breakdown["原辅料类"]["pending_count"] == 1
    assert breakdown["包材类"]["unqualified_count"] == 1
    assert "托盘类" not in breakdown  # 请检=否 不参与

    # 最久待验 Top
    assert payload["oldest_pending"][0]["name"] == "乳糖"
    assert payload["oldest_pending"][0]["waited_hours"] == 60.0

    # 每日序列：09-12 合格 1，09-14 不合格 1
    daily = {item["date"]: item for item in payload["daily"]}
    assert daily["2026-09-12"]["qualified"] == 1
    assert daily["2026-09-14"]["unqualified"] == 1


async def test_product_overview_statistics(db_session: AsyncSession) -> None:
    await _seed_product(db_session)
    clear_inspection_overview_cache()
    payload = await build_inspection_overview(
        db_session, "product", days=30, now=_NOW
    )

    # 待验：pd-pending（132h）+ pd-front（入库 09-16 → 108h）
    assert payload["current"]["pending_count"] == 2
    assert payload["current"]["pending_max_hours"] == 132.0

    # 完成：pd-ok 总 60h
    window = payload["window"]
    assert window["completed_count"] == 1
    assert window["qualified_count"] == 1
    assert window["avg_hours"] == 60.0

    # 分段（含待验行）：入库→待验 avg(12,6,8)=8.67h；待验→结果（仅完成行）48h
    stages = payload["stages"]
    assert stages["inbound_to_pending_avg_hours"] == 8.67
    assert stages["pending_to_result_avg_hours"] == 48.0

    # 最久待验为 B-200（132h），前台批号兜底行（108h）第二
    oldest = payload["oldest_pending"]
    assert oldest[0]["batch"] == "B-200"
    assert oldest[0]["waited_hours"] == 132.0
    assert oldest[1]["waited_hours"] == 108.0


async def test_record_cycle_raw_completed_and_pending(
    db_session: AsyncSession,
) -> None:
    await _seed_raw(db_session)
    completed = await build_record_inspection_cycle(
        db_session, INBOUND_LEDGER_PAGE_KEY, "rec-ok", now=_NOW
    )
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"] == "合格"
    assert completed["inbound_date"] == "2026-09-10"
    assert completed["total_hours"] == 57.0

    pending = await build_record_inspection_cycle(
        db_session, INBOUND_LEDGER_PAGE_KEY, "rec-pending", now=_NOW
    )
    assert pending is not None
    assert pending["status"] == "pending"
    assert pending["status_label"] == "待验中"
    assert pending["total_hours"] == 60.0


async def test_record_cycle_raw_not_counted_states(
    db_session: AsyncSession,
) -> None:
    await _seed_raw(db_session)
    old = await build_record_inspection_cycle(
        db_session, INBOUND_LEDGER_PAGE_KEY, "rec-old", now=_NOW
    )
    assert old is not None
    assert old["status"] == "not_counted"

    noreq = await build_record_inspection_cycle(
        db_session, INBOUND_LEDGER_PAGE_KEY, "rec-noreq", now=_NOW
    )
    assert noreq is not None
    assert noreq["status"] == "not_applicable"
    assert noreq["status_label"] == "无需检验"


async def test_record_cycle_product_stages(db_session: AsyncSession) -> None:
    await _seed_product(db_session)
    cycle = await build_record_inspection_cycle(
        db_session, "product-detail-lovastatin", "pd-ok", now=_NOW
    )
    assert cycle is not None
    assert cycle["status"] == "completed"
    assert cycle["inbound_date"] == "2026-09-10"
    stages = {item["label"]: item["hours"] for item in cycle["stages"]}
    assert stages["入库 → 待验"] == 12.0
    assert stages["待验 → 合格"] == 48.0
    assert cycle["total_hours"] == 60.0

    pending = await build_record_inspection_cycle(
        db_session, "product-detail-lovastatin", "pd-pending", now=_NOW
    )
    assert pending is not None
    assert pending["status"] == "pending"
    assert pending["pending_since"] is not None
    assert pending["total_hours"] == 132.0


async def test_record_cycle_unwatched_page_returns_none(
    db_session: AsyncSession,
) -> None:
    cycle = await build_record_inspection_cycle(
        db_session, "raw-summary", "whatever", now=_NOW
    )
    assert cycle is None
