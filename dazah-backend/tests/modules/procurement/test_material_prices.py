"""Unit and API tests for material price queries."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.procurement import api, price_service
from app.modules.procurement.schemas import (
    MaterialPriceDetail,
    MaterialPriceSummary,
)


def make_record(
    *,
    code: str = "51069308",
    year: int = 2025,
    price: str = "34.12",
    quantity: str = "10",
    batch: str = "B001",
    supplier: str = "测试供应商",
    sub_inventory: str = "C03 五金备件仓",
    flag: str = "normal",
) -> SimpleNamespace:
    unit_price = Decimal(price)
    qty = Decimal(quantity)
    return SimpleNamespace(
        id=uuid4(),
        data_year=year,
        data_date=None,
        doc_no="",
        department="",
        sub_inventory=sub_inventory,
        batch_no=batch,
        material_code=code,
        material_name="隔膜垫,DN15卫生级",
        material_alias="隔膜垫",
        unit="片",
        material_category="五金机械.机械五金辅材",
        cost_category="五金备件",
        unit_price=unit_price,
        quantity=qty,
        amount=(qty * unit_price).quantize(Decimal("0.01")),
        supplier_name=supplier,
        price_flag=flag,
        source_type="erp_stock",
        source_file="cux.xls",
        source_sheet="Sheet1",
        source_row=4,
        is_deleted=False,
    )


class FakePriceRepository:
    records: list[SimpleNamespace] = []

    def __init__(self, session=None) -> None:
        self.session = session

    async def search(self, **kwargs):
        keyword = kwargs.get("keyword")
        rows = self.records
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in row.material_code or keyword in row.material_name
            ]
        if not rows:
            return [], 0
        summary = {
            "material_code": rows[0].material_code,
            "material_name": rows[0].material_name,
            "unit": rows[0].unit,
            "cost_category": rows[0].cost_category,
            "sub_inventory": "C03 五金备件仓",
            "batch_count": len(rows),
            "supplier_count": 1,
            "latest_year": max(row.data_year for row in rows),
            "min_price": min(row.unit_price for row in rows),
            "max_price": max(row.unit_price for row in rows),
            "avg_price": sum(row.unit_price for row in rows) / len(rows),
            "has_suspicious": any(row.price_flag == "suspicious" for row in rows),
        }
        return ([summary], 1) if rows else ([], 0)

    async def list_records(self, material_code: str):
        return [row for row in self.records if row.material_code == material_code]


@pytest.fixture(autouse=True)
def fake_price_repository(monkeypatch):
    FakePriceRepository.records = [
        make_record(year=2024, price="30.00", batch="B1"),
        make_record(year=2025, price="34.12", batch="B2"),
        make_record(year=2025, price="95.00", batch="B3", flag="suspicious"),
    ]
    monkeypatch.setattr(
        price_service,
        "MaterialPriceRepository",
        FakePriceRepository,
    )

    async def fake_live_prices(
        db,
        *,
        material_codes=None,
        keyword=None,
        limit=5000,
    ):
        from datetime import date
        from decimal import Decimal

        from app.modules.procurement.price_live_source import LivePriceRecord

        records = [
            LivePriceRecord(
                material_code="51069308",
                material_name="隔膜垫,DN15卫生级",
                unit="片",
                unit_price=Decimal("36.00"),
                quantity=Decimal("5"),
                amount=Decimal("180.00"),
                supplier_name="实时供应商",
                department="101-2 车间",
                batch_no="25-101-2/12-28",
                data_date=date(2026, 10, 1),
            )
        ]
        if material_codes:
            records = [
                record
                for record in records
                if record.material_code in material_codes
            ]
        return records

    monkeypatch.setattr(price_service, "list_live_prices", fake_live_prices)
    yield


@pytest.fixture
async def price_http():
    test_app = FastAPI()
    test_app.include_router(api.router, prefix="/api/v1/procurement")
    test_app.dependency_overrides[get_db] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.anyio
async def test_search_returns_aggregated_summary():
    async with _session() as session:
        rows, total = await price_service.search_material_prices(
            session, keyword="隔膜垫"
        )
    assert total == 1
    assert rows[0].material_code == "51069308"
    assert rows[0].batch_count == 3
    assert rows[0].has_suspicious is True
    assert isinstance(rows[0], MaterialPriceSummary)
    # 实时层只补充最近入库价，不并入历史金额统计
    assert rows[0].live_batch_count == 1
    assert rows[0].live_latest_price == Decimal("36.00")


@pytest.mark.anyio
async def test_search_without_match_returns_empty():
    async with _session() as session:
        rows, total = await price_service.search_material_prices(
            session, keyword="不存在的物料"
        )
    assert rows == []
    assert total == 0

@pytest.mark.anyio
async def test_search_without_ask_returns_empty():
    """未输入关键词且未带筛选时，不返回全量数据。"""
    async with _session() as session:
        rows, total = await price_service.search_material_prices(session)
    assert rows == []
    assert total == 0


@pytest.mark.anyio
async def test_detail_aggregates_years_and_dedupes_warehouses():
    async with _session() as session:
        detail = await price_service.get_material_price_detail(session, "51069308")
    assert isinstance(detail, MaterialPriceDetail)
    assert detail.material_code == "51069308"
    assert len(detail.batches) == 3
    assert [item.data_year for item in detail.years] == [2024, 2025]
    year_2025 = detail.years[1]
    assert year_2025.batch_count == 2
    assert year_2025.min_price == Decimal("34.12")
    assert year_2025.max_price == Decimal("95.00")
    assert detail.sub_inventory == "C03 五金备件仓"
    assert len(detail.live_batches) == 1
    assert detail.live_batches[0].source_type == "warehouse_live"
    assert detail.live_batches[0].supplier_name == "实时供应商"
    assert detail.live_batches[0].data_year == 2026


@pytest.mark.anyio
async def test_detail_missing_material_raises():
    async with _session() as session:
        with pytest.raises(ValueError):
            await price_service.get_material_price_detail(session, "00000000")


@pytest.mark.anyio
async def test_material_prices_api_lists_and_returns_detail(price_http):
    response = await price_http.get(
        "/api/v1/procurement/material-prices", params={"keyword": "隔膜垫"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["material_code"] == "51069308"

    detail = await price_http.get("/api/v1/procurement/material-prices/51069308")
    assert detail.status_code == 200
    payload = detail.json()["data"]
    assert payload["material_code"] == "51069308"
    assert len(payload["years"]) == 2


@pytest.mark.anyio
async def test_material_prices_api_missing_detail_returns_404(price_http):
    response = await price_http.get(
        "/api/v1/procurement/material-prices/not-exist"
    )
    assert response.status_code == 404


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _session():
    return _Session()
