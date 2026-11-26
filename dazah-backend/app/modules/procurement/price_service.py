"""Material price queries and detail aggregation.

历史层（ERP 导入表）与实时层（仓储五金入库飞书镜像）是两套口径：金额和数量
只按历史层统计，实时层只补充"最近一次入库价"与独立的明细列表，两者不相加。
"""

from collections import defaultdict
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.procurement.models import MaterialPriceRecord
from app.modules.procurement.price_live_source import (
    LivePriceRecord,
    list_live_prices,
)
from app.modules.procurement.repository import MaterialPriceRepository
from app.modules.procurement.schemas import (
    MaterialPriceBatch,
    MaterialPriceDetail,
    MaterialPriceSummary,
    MaterialPriceYear,
)


def _latest_by_material(
    records: list[LivePriceRecord],
) -> tuple[dict[str, LivePriceRecord], dict[str, int]]:
    latest: dict[str, LivePriceRecord] = {}
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record.material_code] += 1
        current = latest.get(record.material_code)
        if current is None or (record.data_date or date.min) > (
            current.data_date or date.min
        ):
            latest[record.material_code] = record
    return latest, dict(counts)


def _live_to_batch(record: LivePriceRecord) -> MaterialPriceBatch:
    record_date = record.data_date
    return MaterialPriceBatch(
        id=uuid5(
            NAMESPACE_URL,
            "warehouse_live:"
            f"{record.material_code}:{record.batch_no}:{record_date}:"
            f"{record.unit_price}:{record.quantity}",
        ),
        data_year=record_date.year if record_date else 0,
        data_date=record_date,
        doc_no="",
        department=record.department,
        sub_inventory="五金备件仓",
        batch_no=record.batch_no,
        supplier_name=record.supplier_name,
        unit=record.unit,
        unit_price=record.unit_price,
        quantity=record.quantity,
        amount=record.amount,
        price_flag="normal",
        source_type="warehouse_live",
    )


async def search_material_prices(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    source_type: str | None = None,
    cost_category: str | None = None,
    sub_inventory: str | None = None,
    data_year: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[MaterialPriceSummary], int]:
    rows, total = await MaterialPriceRepository(db).search(
        keyword=keyword,
        source_type=source_type,
        cost_category=cost_category,
        sub_inventory=sub_inventory,
        data_year=data_year,
        page=page,
        page_size=page_size,
    )
    summaries = [MaterialPriceSummary.model_validate(row) for row in rows]
    if summaries:
        codes = {summary.material_code for summary in summaries}
        live_records = await list_live_prices(db, material_codes=codes)
        latest, counts = _latest_by_material(live_records)
        for summary in summaries:
            summary.live_batch_count = counts.get(summary.material_code, 0)
            live = latest.get(summary.material_code)
            if live is not None:
                summary.live_latest_price = live.unit_price
                summary.live_latest_date = live.data_date
    return summaries, total


def _year_summary(
    data_year: int, records: list[MaterialPriceRecord]
) -> MaterialPriceYear:
    prices = [record.unit_price for record in records]
    return MaterialPriceYear(
        data_year=data_year,
        batch_count=len(records),
        min_price=min(prices),
        max_price=max(prices),
        avg_price=sum(prices) / len(prices),
        quantity=sum(record.quantity for record in records),
    )


async def get_material_price_detail(
    db: AsyncSession,
    material_code: str,
) -> MaterialPriceDetail:
    records = await MaterialPriceRepository(db).list_records(material_code)
    if not records:
        raise ValueError("物料价格记录不存在")

    first = records[0]
    grouped: dict[int, list[MaterialPriceRecord]] = defaultdict(list)
    for record in records:
        grouped[record.data_year].append(record)

    live_records = await list_live_prices(db, material_codes={material_code})

    sub_inventory = "、".join(
        dict.fromkeys(
            record.sub_inventory for record in records if record.sub_inventory
        )
    )
    return MaterialPriceDetail(
        material_code=first.material_code,
        material_name=first.material_name,
        material_alias=first.material_alias,
        unit=first.unit,
        material_category=first.material_category,
        cost_category=first.cost_category,
        sub_inventory=sub_inventory,
        years=[_year_summary(year, rows) for year, rows in sorted(grouped.items())],
        batches=[MaterialPriceBatch.model_validate(record) for record in records],
        live_batches=[_live_to_batch(record) for record in live_records],
    )
