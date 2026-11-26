"""Warehouse hardware inbound ledger as a live price source.

跨模块边界：只通过 ``warehouse.public_api.get_material_page_rows`` 读取飞书
镜像，不直接访问仓储的表。实时数据与 ERP 历史表是两套口径，合并时分开统计，
不做金额相加。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.public_api import get_material_page_rows

HARDWARE_INBOUND_PAGE_KEY = "hardware-inbound-ledger"

CODE_FIELD = "物料编号"
NAME_FIELD = "物料说明"
UNIT_FIELD = "单位"
PRICE_FIELD = "单价（元）"
QUANTITY_FIELD = "入库量"
AMOUNT_FIELD = "金额"
SUPPLIER_FIELD = "供应商名称"
DEPARTMENT_FIELD = "归属车间"
BATCH_FIELD = "厂内批号"
DATE_FIELD = "日期"


@dataclass(frozen=True)
class LivePriceRecord:
    """一条实时入库记录（已归一化为价格查询所需字段）。"""

    material_code: str
    material_name: str
    unit: str
    unit_price: Decimal
    quantity: Decimal
    amount: Decimal
    supplier_name: str
    department: str
    batch_no: str
    data_date: date | None


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).replace(",", "").strip()
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _to_date(value: object) -> date | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000, UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.strip()[:10], fmt).date()
            except ValueError:
                continue
    return None


def parse_row(cells: dict[str, object]) -> LivePriceRecord | None:
    code = str(cells.get(CODE_FIELD) or "").strip()
    if not code:
        return None
    unit_price = _to_decimal(cells.get(PRICE_FIELD))
    if unit_price <= 0:
        return None
    quantity = _to_decimal(cells.get(QUANTITY_FIELD))
    amount = _to_decimal(cells.get(AMOUNT_FIELD))
    if amount == 0:
        amount = (quantity * unit_price).quantize(Decimal("0.01"))
    return LivePriceRecord(
        material_code=code,
        material_name=str(cells.get(NAME_FIELD) or "").strip(),
        unit=str(cells.get(UNIT_FIELD) or "").strip(),
        unit_price=unit_price,
        quantity=quantity,
        amount=amount,
        supplier_name=str(cells.get(SUPPLIER_FIELD) or "").strip(),
        department=str(cells.get(DEPARTMENT_FIELD) or "").strip(),
        batch_no=str(cells.get(BATCH_FIELD) or "").strip(),
        data_date=_to_date(cells.get(DATE_FIELD)),
    )


async def list_live_prices(
    db: AsyncSession,
    *,
    material_codes: set[str] | None = None,
    keyword: str | None = None,
    limit: int | None = None,
) -> list[LivePriceRecord]:
    """按物料编码或关键词读取实时入库价格，日期倒序。

    指定 ``material_codes`` 时用 JSONB 字段精确过滤，避免全量拉取镜像；
    关键词搜索走 ``search_text`` 收窄后再在内存中复核。
    """
    field_values: dict[str, list[str]] | None = None
    if material_codes:
        field_values = {CODE_FIELD: sorted(material_codes)}
    rows, _synced_at = await get_material_page_rows(
        db,
        page_key=HARDWARE_INBOUND_PAGE_KEY,
        search_text=keyword,
        field_values=field_values,
        limit=limit,
    )
    records: list[LivePriceRecord] = []
    for cells in rows:
        record = parse_row(cells)
        if record is None:
            continue
        if material_codes and record.material_code not in material_codes:
            continue
        records.append(record)
    records.sort(
        key=lambda item: item.data_date or date.min,
        reverse=True,
    )
    return records
