"""仓储 public_api 聚合集成测试（成品入库总账 KG 合计）。

走真实 PostgreSQL（JSONB 聚合），事务内自建快照与行数据，
测试结束由 db_session 夹具统一回滚。
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select

from app.modules.warehouse.feishu_material_pages import (
    FINISHED_INBOUND_LEDGER_PAGE_KEY,
)
from app.modules.warehouse.models import MaterialPageRow, MaterialPageSnapshot
from app.modules.warehouse.public_api import get_finished_inbound_kg_total

_TZ = ZoneInfo("Asia/Shanghai")


def _feishu_ms(day: str) -> int:
    """按飞书日期字段口径取北京时间零点毫秒时间戳。"""
    return int(
        datetime.fromisoformat(day).replace(tzinfo=_TZ).timestamp() * 1000
    )


async def _clear_inbound_snapshot(session) -> None:
    """清掉环境中可能存在的入库总账快照（事务内，回滚可恢复）。"""
    await session.execute(
        delete(MaterialPageRow).where(
            MaterialPageRow.page_snapshot_id.in_(
                select(MaterialPageSnapshot.id).where(
                    MaterialPageSnapshot.page_key
                    == FINISHED_INBOUND_LEDGER_PAGE_KEY
                )
            )
        )
    )
    await session.execute(
        delete(MaterialPageSnapshot).where(
            MaterialPageSnapshot.page_key == FINISHED_INBOUND_LEDGER_PAGE_KEY
        )
    )
    await session.flush()


async def _seed_inbound_rows(session) -> None:
    """建一张入库总账快照并写入覆盖各边界条件的行。"""
    snapshot = MaterialPageSnapshot(
        page_key=FINISHED_INBOUND_LEDGER_PAGE_KEY,
        page_title="入库总账",
        table_name="入库总账",
        table_id="tbloVqkVZEYmLfyB",
        source="feishu_bitable",
    )
    session.add(snapshot)
    await session.flush()
    # (record_id, 产品名称, 入库日期, 入库数量（KG）)
    rows = [
        ("rec-1", "L-苯丙氨酸", "2026-09-01", 1000),  # 区间下界（含）
        ("rec-2", "L-苯丙氨酸", "2026-09-15", "500.5"),  # 字符串数值节点
        ("rec-3", "L-苯丙氨酸", "2026-08-31", 9999),  # 区间外
        ("rec-4", "多拉菌素", "2026-09-10", 777),  # 其他产品
        ("rec-5", "  L-苯丙氨酸  ", "2026-09-20", 100),  # 名称带空白
        ("rec-6", "L-苯丙氨酸", "2026-09-21", ""),  # 空 KG
        ("rec-7", "L-苯丙氨酸", "2026-09-22", "abc"),  # 脏文本 KG
        ("rec-8", "L-苯丙氨酸", "2026-09-30", 200),  # 区间上界（含）
    ]
    for record_id, product, day, kg in rows:
        session.add(
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id=record_id,
                cells={
                    "产品名称": product,
                    "入库日期": _feishu_ms(day),
                    "入库数量（KG）": kg,
                },
            )
        )
    await session.flush()


@pytest.mark.anyio
async def test_returns_none_without_snapshot(db_session) -> None:
    await _clear_inbound_snapshot(db_session)
    result = await get_finished_inbound_kg_total(
        db_session,
        product_name="L-苯丙氨酸",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )
    assert result is None


@pytest.mark.anyio
async def test_sums_product_kg_within_inclusive_date_range(db_session) -> None:
    await _clear_inbound_snapshot(db_session)
    await _seed_inbound_rows(db_session)

    result = await get_finished_inbound_kg_total(
        db_session,
        product_name="L-苯丙氨酸",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )
    # 1000 + 500.5 + 100（btrim 命中）+ 200；区间外/其他产品/空与脏 KG 均不计
    assert result == pytest.approx(1800.5)


@pytest.mark.anyio
async def test_returns_zero_when_product_has_no_rows_in_range(db_session) -> None:
    await _clear_inbound_snapshot(db_session)
    await _seed_inbound_rows(db_session)

    result = await get_finished_inbound_kg_total(
        db_session,
        product_name="洛伐他汀",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )
    assert result == 0.0
