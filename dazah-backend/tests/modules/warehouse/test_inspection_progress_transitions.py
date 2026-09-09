"""仓储状态变更日志（material_status_transitions）捕获测试。

Covers:
- 全量/增量 upsert 检测受监控字段变化并落变更日志
- 取值未变化不落日志；重复同步不重复落
- 新进入镜像的行写初始状态记录（occurred_at=记录 created_time）
- 状态回退（合格→待验）同样记录
- 非监控页面 / 未传 record_meta 时不捕获（向后兼容）
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.inspection_progress import (
    INBOUND_LEDGER_PAGE_KEY,
    RESULT_FIELD,
)
from app.modules.warehouse.models import (
    MaterialPageRow,
    MaterialStatusTransition,
)
from app.modules.warehouse.service import WarehouseService

CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _cst_ms(year: int, month: int, day: int, hour: int = 0) -> int:
    """中国时区时刻 → 飞书毫秒时间戳。"""
    local = datetime(year, month, day, hour, tzinfo=CHINA_TIMEZONE).astimezone(UTC)
    return int(local.timestamp() * 1000)


async def _prepare(
    db_session: AsyncSession, page_key: str = INBOUND_LEDGER_PAGE_KEY
) -> tuple[WarehouseService, object]:
    await db_session.run_sync(
        lambda sync_db: MaterialStatusTransition.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    service = WarehouseService(db_session)
    await service.repo.upsert_material_page_snapshot(
        page_key=page_key,
        page_title=page_key,
        table_name=page_key,
        table_id=f"tbl-{page_key}",
        columns=[{"key": RESULT_FIELD, "title": RESULT_FIELD}],
        total_rows=0,
        source="test",
        last_synced_at=datetime.now(UTC),
    )
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None
    return service, snapshot.id


def _row(snapshot_id: object, record_id: str, result: str | None) -> MaterialPageRow:
    return MaterialPageRow(
        page_snapshot_id=snapshot_id,
        source_record_id=record_id,
        row_order=1,
        cells={RESULT_FIELD: result, "物料名称": "物料A"},
        search_text="物料A",
        last_synced_at=datetime.now(UTC),
    )


def _meta(record_id: str, *, created_ms: int | None, modified_ms: int | None):
    return {
        record_id: {"created_ms": created_ms, "modified_ms": modified_ms},
    }


async def _transitions(db_session: AsyncSession) -> list[MaterialStatusTransition]:
    result = await db_session.execute(
        select(MaterialStatusTransition).order_by(
            MaterialStatusTransition.created_at.asc()
        )
    )
    return list(result.scalars().all())


async def test_status_change_logs_transition(db_session: AsyncSession) -> None:
    """检测结果 null→合格：落一条变更记录，occurred_at 取 modified_ms。"""
    service, snapshot_id = await _prepare(db_session)
    await service.repo.upsert_material_page_rows(
        snapshot_id,
        [_row(snapshot_id, "rec-1", None)],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=_meta(
            "rec-1", created_ms=_cst_ms(2026, 9, 10), modified_ms=_cst_ms(2026, 9, 10)
        ),
    )
    await service.repo.upsert_material_page_rows(
        snapshot_id,
        [_row(snapshot_id, "rec-1", "合格")],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=_meta(
            "rec-1",
            created_ms=_cst_ms(2026, 9, 10),
            modified_ms=_cst_ms(2026, 9, 12, 9),
        ),
    )

    # 新行初始记录 + 状态变更记录
    logged = await _transitions(db_session)
    assert len(logged) == 2
    initial, changed = logged
    assert initial.old_value is None
    assert initial.new_value is None
    # created_ms 对应中国时区零点
    assert initial.occurred_at.astimezone(CHINA_TIMEZONE).hour == 0
    assert changed.old_value is None
    assert changed.new_value == "合格"
    # modified_ms 对应中国时区 09:00
    assert changed.occurred_at.astimezone(CHINA_TIMEZONE).hour == 9


async def test_no_change_no_extra_transition(db_session: AsyncSession) -> None:
    """取值未变化与重复同步不重复落日志。"""
    service, snapshot_id = await _prepare(db_session)
    meta = _meta(
        "rec-1", created_ms=_cst_ms(2026, 9, 10), modified_ms=_cst_ms(2026, 9, 10)
    )
    await service.repo.upsert_material_page_rows(
        snapshot_id,
        [_row(snapshot_id, "rec-1", None)],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=meta,
    )
    await service.repo.upsert_material_page_rows(
        snapshot_id,
        [_row(snapshot_id, "rec-1", "合格")],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=meta,
    )
    # 值未再变化的重复同步
    await service.repo.upsert_material_page_rows(
        snapshot_id,
        [_row(snapshot_id, "rec-1", "合格")],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=meta,
    )

    logged = await _transitions(db_session)
    assert len(logged) == 2  # 初始记录 + 一次变更


async def test_reverse_transition_logged(db_session: AsyncSession) -> None:
    """状态回退（合格→待验）同样记录。"""
    service, snapshot_id = await _prepare(db_session)
    meta = _meta(
        "rec-1", created_ms=_cst_ms(2026, 9, 10), modified_ms=_cst_ms(2026, 9, 10)
    )
    await service.repo.upsert_material_page_rows(
        snapshot_id,
        [_row(snapshot_id, "rec-1", "合格")],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=meta,
    )
    await service.repo.upsert_material_page_rows(
        snapshot_id,
        [_row(snapshot_id, "rec-1", "待验")],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=meta,
    )

    logged = await _transitions(db_session)
    assert len(logged) == 2
    assert logged[1].old_value == "合格"
    assert logged[1].new_value == "待验"


async def test_incremental_upsert_logs_transition(db_session: AsyncSession) -> None:
    """增量 upsert 同样捕获状态变化。"""
    service, snapshot_id = await _prepare(db_session)
    meta = _meta(
        "rec-9", created_ms=_cst_ms(2026, 9, 11), modified_ms=_cst_ms(2026, 9, 11)
    )
    await service.repo.upsert_material_page_rows_incremental(
        snapshot_id,
        [_row(snapshot_id, "rec-9", None)],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=meta,
    )
    await service.repo.upsert_material_page_rows_incremental(
        snapshot_id,
        [_row(snapshot_id, "rec-9", "不合格")],
        page_key=INBOUND_LEDGER_PAGE_KEY,
        record_meta=_meta(
            "rec-9", created_ms=_cst_ms(2026, 9, 11), modified_ms=_cst_ms(2026, 9, 13)
        ),
    )

    logged = await _transitions(db_session)
    assert len(logged) == 2
    assert logged[1].old_value is None
    assert logged[1].new_value == "不合格"


async def test_unwatched_page_or_missing_meta_no_capture(
    db_session: AsyncSession,
) -> None:
    """非监控页面 / 未传 record_meta 时不捕获（向后兼容）。"""
    service, snapshot_id = await _prepare(db_session, page_key="raw-summary")
    await service.repo.upsert_material_page_rows(
        snapshot_id,
        [_row(snapshot_id, "rec-1", "合格")],
        page_key="raw-summary",
        record_meta=_meta(
            "rec-1", created_ms=_cst_ms(2026, 9, 10), modified_ms=_cst_ms(2026, 9, 10)
        ),
    )
    # 监控页面但未传 meta（旧调用方式）
    service2, snapshot2 = await _prepare(db_session)
    await service2.repo.upsert_material_page_rows(
        snapshot2, [_row(snapshot2, "rec-2", None)]
    )

    assert await _transitions(db_session) == []
