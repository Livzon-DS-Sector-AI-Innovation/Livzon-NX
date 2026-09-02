import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.feishu_material_pages import FEISHU_WAREHOUSE_MATERIAL_PAGES
from app.modules.warehouse.models import MaterialPageRow
from app.modules.warehouse.service import WarehouseService, normalize_feishu_cell_value
from tests.modules.warehouse.test_ai_service_migration import _seed_trend_snapshots


def _suffix() -> str:
    return uuid.uuid4().hex[:6].upper()


async def _seed(session: AsyncSession) -> None:
    service = WarehouseService(session)
    suffix = _suffix()

    await service.upsert_raw_material_snapshot(
        source_id=f"raw-{suffix}",
        code=f"YS-{suffix}",
        name="测试原料",
        spec="25kg/袋",
        unit="kg",
        available=120,
        safety=100,
        last_month=80,
        two_months_ago=90,
        today_balance=130,
        front_stock=10,
        this_month_use=20,
        warning="库存不足",
        product_line="FA",
        erp_no=f"ERP-{suffix}",
        delivery="本周到货",
        remark="原料测试",
        source="test",
    )
    await service.upsert_packaging_snapshot(
        source_id=f"pack-{suffix}",
        code=f"BO-{suffix}",
        name="测试包材",
        spec="420*620mm",
        batch="2501001",
        available=50,
        safety=40,
        last_month=35,
        two_months_ago=30,
        today_balance=60,
        front_stock=10,
        this_month_use=25,
        warning=None,
        product_line="MC",
        erp_no=f"EPR-{suffix}",
        delivery=None,
        remark="包材测试",
        source="test",
    )
    await service.upsert_product_snapshot(
        source_id=f"prod-{suffix}",
        name="测试成品",
        spec="25KG/袋",
        order_quantity=100,
        pending_quantity=10,
        qualified_quantity=85,
        subtotal_quantity=95,
        remaining_quantity=5,
        unit="KG",
        remark="成品测试",
        source="test",
    )
    await session.commit()


@pytest.mark.anyio
async def test_list_raw_materials(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)
    response = await client.get("/api/v1/warehouse/raw-materials")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert any(item["name"] == "测试原料" for item in body["data"])


@pytest.mark.anyio
async def test_list_packaging_materials(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)
    response = await client.get("/api/v1/warehouse/packaging-materials")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert any(item["name"] == "测试包材" for item in body["data"])


@pytest.mark.anyio
async def test_list_products(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed(db_session)
    response = await client.get("/api/v1/warehouse/products")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert any(item["name"] == "测试成品" for item in body["data"])


@pytest.mark.anyio
async def test_get_material_page_returns_dynamic_columns_and_rows(
    client: AsyncClient,
) -> None:
    with (
        patch.object(
            WarehouseService,
            "fetch_feishu_table_fields",
            new=AsyncMock(
                return_value=[
                    {"field_name": "物料编码"},
                    {"field_name": "物料名称"},
                    {"field_name": "负责人"},
                    {"field_name": "标签"},
                ]
            ),
        ),
        patch.object(
            WarehouseService,
            "fetch_feishu_table_records",
            new=AsyncMock(
                return_value=[
                    {
                        "record_id": "rec_raw_1",
                        "fields": {
                            "物料编码": "RM-001",
                            "物料名称": "黄原胶",
                            "负责人": {"name": "张三"},
                            "标签": [{"text": "A"}, {"text": "B"}],
                        },
                    }
                ]
            ),
        ),
    ):
        response = await client.get(
            "/api/v1/warehouse/material-pages/raw-summary",
            params={"page": 1, "page_size": 20, "source": "feishu"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["page_key"] == "raw-summary"
    assert body["data"]["page_title"] == "原辅料库存总表"
    assert [
        {"key": column["key"], "title": column["title"]}
        for column in body["data"]["columns"]
    ] == [
        {"key": "物料编码", "title": "物料编码"},
        {"key": "物料名称", "title": "物料名称"},
        {"key": "负责人", "title": "负责人"},
        {"key": "标签", "title": "标签"},
    ]
    assert body["data"]["rows"] == [
        {
            "物料编码": "RM-001",
            "物料名称": "黄原胶",
            "负责人": "张三",
            "标签": "A, B",
            "__record_id": "rec_raw_1",
        }
    ]
    assert body["data"]["total"] == 1


@pytest.mark.anyio
async def test_get_finished_product_material_page_returns_configured_title(
    client: AsyncClient,
) -> None:
    with (
        patch.object(
            WarehouseService,
            "fetch_feishu_table_fields",
            new=AsyncMock(
                return_value=[{"field_name": "入库日期"}, {"field_name": "产品名称"}]
            ),
        ),
        patch.object(
            WarehouseService,
            "fetch_feishu_table_records",
            new=AsyncMock(
                return_value=[
                    {
                        "record_id": "rec_product_1",
                        "fields": {
                            "入库日期": "2026/06/27",
                            "产品名称": "L-苯丙氨酸",
                        },
                    }
                ]
            ),
        ),
    ):
        response = await client.get(
            "/api/v1/warehouse/material-pages/product-inbound-ledger",
            params={"page": 1, "page_size": 20, "source": "feishu"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["page_key"] == "product-inbound-ledger"
    assert body["data"]["page_title"] == "入库总账"
    assert [
        {"key": column["key"], "title": column["title"]}
        for column in body["data"]["columns"]
    ] == [
        {"key": "入库日期", "title": "入库日期"},
        {"key": "产品名称", "title": "产品名称"},
    ]
    assert body["data"]["rows"] == [
        {
            "入库日期": "2026/06/27",
            "产品名称": "L-苯丙氨酸",
            "__record_id": "rec_product_1",
        }
    ]


@pytest.mark.anyio
async def test_get_hardware_material_page_returns_configured_title(
    client: AsyncClient,
) -> None:
    with (
        patch.object(
            WarehouseService,
            "fetch_feishu_table_fields",
            new=AsyncMock(
                return_value=[
                    {"field_name": "名称"},
                    {"field_name": "规格"},
                    {"field_name": "结存量"},
                ]
            ),
        ),
        patch.object(
            WarehouseService,
            "fetch_feishu_table_records",
            new=AsyncMock(
                return_value=[
                    {
                        "record_id": "rec_hardware_1",
                        "fields": {"名称": "轴承座", "规格": "P208", "结存量": 10},
                    }
                ]
            ),
        ),
    ):
        response = await client.get(
            "/api/v1/warehouse/material-pages/hardware-summary",
            params={"page": 1, "page_size": 20, "source": "feishu"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["page_key"] == "hardware-summary"
    assert body["data"]["page_title"] == "五金"
    assert body["data"]["table_name"] == "五金"
    assert [
        {"key": column["key"], "title": column["title"]}
        for column in body["data"]["columns"]
    ] == [
        {"key": "名称", "title": "名称"},
        {"key": "规格", "title": "规格"},
        {"key": "结存量", "title": "结存量"},
    ]
    assert body["data"]["rows"] == [
        {
            "名称": "轴承座",
            "规格": "P208",
            "结存量": 10,
            "__record_id": "rec_hardware_1",
        }
    ]


@pytest.mark.anyio
async def test_get_material_page_rejects_unknown_page_key(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/warehouse/material-pages/not-exists",
        params={"source": "feishu"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["message"] == "仓储飞书模板页不存在"


def test_normalize_feishu_cell_values() -> None:
    assert normalize_feishu_cell_value("文本") == "文本"
    assert normalize_feishu_cell_value(12.5) == 12.5
    assert normalize_feishu_cell_value([{"text": "A"}, {"text": "B"}]) == "A, B"
    assert normalize_feishu_cell_value({"name": "张三"}) == "张三"


def test_snapshot_seed_covers_finished_product_pages() -> None:
    expected_pages = {
        page_key: page
        for page_key, page in FEISHU_WAREHOUSE_MATERIAL_PAGES.items()
        if page_key.startswith("product-")
    }

    for page_key, page in expected_pages.items():
        assert page.page_key == page_key
        assert page.title
        assert page.table_id
        assert page.app_token


@pytest.mark.anyio
async def test_get_feishu_material_page_applies_keyword_filter(
    db_session: AsyncSession,
) -> None:
    service = WarehouseService(db_session)

    with (
        patch.object(
            WarehouseService,
            "fetch_feishu_table_fields",
            new=AsyncMock(
                return_value=[
                    {"field_name": "物料编码"},
                    {"field_name": "物料名称"},
                ]
            ),
        ),
        patch.object(
            WarehouseService,
            "fetch_feishu_table_records",
            new=AsyncMock(
                return_value=[
                    {
                        "record_id": "rec_1",
                        "fields": {"物料编码": "RM-001", "物料名称": "黄原胶"},
                    },
                    {
                        "record_id": "rec_2",
                        "fields": {"物料编码": "RM-002", "物料名称": "葡萄糖"},
                    },
                ]
            ),
        ),
    ):
        data = await service.get_feishu_material_page(
            "raw-summary",
            page=1,
            page_size=20,
            keyword="葡萄",
            source="feishu",
            force=True,
        )

    assert data.total == 1
    assert data.rows == [
        {
            "物料编码": "RM-002",
            "物料名称": "葡萄糖",
            "__record_id": "rec_2",
        }
    ]


@pytest.mark.anyio
async def test_get_feishu_material_page_local_force_runs_incremental_sync(
    db_session: AsyncSession,
) -> None:
    """本地快照模式下手动刷新（force=1）先做增量同步，再读镜像，不全量拉取。"""
    service = WarehouseService(db_session)
    sync_mock = AsyncMock()
    local_mock = AsyncMock(return_value={"source": "local_snapshot", "total": 5})
    with (
        patch.object(
            WarehouseService,
            "_resolve_material_page_source",
            new=AsyncMock(return_value="local"),
        ),
        patch.object(
            WarehouseService, "sync_material_page_to_local", new=sync_mock
        ),
        patch.object(WarehouseService, "get_local_material_page", new=local_mock),
    ):
        result = await service.get_feishu_material_page(
            "raw-ledger",
            page=2,
            page_size=50,
            keyword="葡萄糖",
            force=True,
        )
    assert result == {"source": "local_snapshot", "total": 5}
    sync_mock.assert_awaited_once_with("raw-ledger", incremental=True)
    local_mock.assert_awaited_once()
    assert local_mock.await_args.kwargs["page"] == 2
    assert local_mock.await_args.kwargs["page_size"] == 50
    assert local_mock.await_args.kwargs["keyword"] == "葡萄糖"


@pytest.mark.anyio
async def test_get_feishu_material_page_local_no_force_skips_sync(
    db_session: AsyncSession,
) -> None:
    """本地快照模式非刷新（force=false）直接读镜像，不触发同步。"""
    service = WarehouseService(db_session)
    sync_mock = AsyncMock()
    local_mock = AsyncMock(return_value={"source": "local_snapshot"})
    with (
        patch.object(
            WarehouseService,
            "_resolve_material_page_source",
            new=AsyncMock(return_value="local"),
        ),
        patch.object(
            WarehouseService, "sync_material_page_to_local", new=sync_mock
        ),
        patch.object(WarehouseService, "get_local_material_page", new=local_mock),
    ):
        await service.get_feishu_material_page("raw-ledger", force=False)
    sync_mock.assert_not_awaited()
    local_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_get_material_page_can_read_local_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    service = WarehouseService(db_session)
    snapshot = await service.repo.upsert_material_page_snapshot(
        page_key="raw-summary",
        page_title="原辅料库存总表",
        table_name="原辅料库存总表",
        table_id="tbl-local-test",
        columns=[
            {"key": "物料编码", "title": "物料编码"},
            {"key": "物料名称", "title": "物料名称"},
        ],
        total_rows=2,
        source="feishu_bitable",
        last_synced_at=datetime.now(UTC),
    )
    await service.repo.replace_material_page_rows(
        snapshot.id,
        [
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_local_1",
                row_order=1,
                cells={"物料编码": "RM-LOCAL-001", "物料名称": "本地黄原胶"},
                search_text="rm-local-001 本地黄原胶",
            ),
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_local_2",
                row_order=2,
                cells={"物料编码": "RM-LOCAL-002", "物料名称": "本地葡萄糖"},
                search_text="rm-local-002 本地葡萄糖",
            ),
        ],
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/warehouse/material-pages/raw-summary",
        params={"source": "local", "keyword": "葡萄"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["source"] == "local_snapshot"
    assert body["data"]["total"] == 1
    assert body["data"]["rows"] == [
        {
            "物料编码": "RM-LOCAL-002",
            "物料名称": "本地葡萄糖",
            "__record_id": "rec_local_2",
        }
    ]


@pytest.mark.anyio
async def test_get_finished_product_material_page_can_read_local_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    service = WarehouseService(db_session)
    snapshot = await service.repo.upsert_material_page_snapshot(
        page_key="product-summary",
        page_title="产品汇总",
        table_name="产品汇总",
        table_id="tbl-product-summary-test",
        columns=[
            {"key": "产品名称", "title": "产品名称"},
            {"key": "规格", "title": "规格"},
        ],
        total_rows=2,
        source="feishu_bitable",
        last_synced_at=datetime.now(UTC),
    )
    await service.repo.replace_material_page_rows(
        snapshot.id,
        [
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_product_local_1",
                row_order=1,
                cells={"产品名称": "L-苯丙氨酸", "规格": "25KG/袋"},
                search_text="l-苯丙氨酸 25kg/袋",
            ),
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_product_local_2",
                row_order=2,
                cells={"产品名称": "多拉菌素", "规格": "10KG/桶"},
                search_text="多拉菌素 10kg/桶",
            ),
        ],
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/warehouse/material-pages/product-summary",
        params={"source": "local", "keyword": "多拉"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["page_key"] == "product-summary"
    assert body["data"]["page_title"] == "产品汇总"
    assert body["data"]["source"] == "local_snapshot"
    assert body["data"]["total"] == 1
    assert body["data"]["rows"] == [
        {
            "产品名称": "多拉菌素",
            "规格": "10KG/桶",
            "__record_id": "rec_product_local_2",
        }
    ]


@pytest.mark.anyio
async def test_finished_product_detail_page_hides_zero_inventory_rows_in_local_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    service = WarehouseService(db_session)
    snapshot = await service.repo.upsert_material_page_snapshot(
        page_key="product-detail-l-phenylalanine",
        page_title="L-苯丙氨酸库存明细",
        table_name="L-苯丙氨酸库存明细",
        table_id="tbl-product-detail-test",
        columns=[
            {"key": "产品名称", "title": "产品名称"},
            {"key": "库存量", "title": "库存量"},
            {"key": "客户", "title": "客户"},
        ],
        total_rows=3,
        source="feishu_bitable",
        last_synced_at=datetime.now(UTC),
    )
    await service.repo.replace_material_page_rows(
        snapshot.id,
        [
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_product_detail_1",
                row_order=1,
                cells={"产品名称": "L-苯丙氨酸", "库存量": "0", "客户": "维多"},
                search_text="l-苯丙氨酸 0 维多",
            ),
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_product_detail_2",
                row_order=2,
                cells={"产品名称": "L-苯丙氨酸", "库存量": "1250", "客户": "内销客户"},
                search_text="l-苯丙氨酸 1250 内销客户",
            ),
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_product_detail_3",
                row_order=3,
                cells={"产品名称": "L-苯丙氨酸", "库存量": "", "客户": "测试客户"},
                search_text="l-苯丙氨酸 测试客户",
            ),
        ],
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/warehouse/material-pages/product-detail-l-phenylalanine",
        params={"source": "local"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["page_key"] == "product-detail-l-phenylalanine"
    assert body["data"]["total"] == 1
    assert body["data"]["rows"] == [
        {
            "产品名称": "L-苯丙氨酸",
            "库存量": "1250",
            "客户": "内销客户",
            "__record_id": "rec_product_detail_2",
        }
    ]


@pytest.mark.anyio
async def test_get_material_page_applies_local_filters_after_paging(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    service = WarehouseService(db_session)
    snapshot = await service.repo.upsert_material_page_snapshot(
        page_key="raw-ledger",
        page_title="原辅料出库总账",
        table_name="原辅料出库总账",
        table_id="tbl-local-ledger-test",
        columns=[
            {"key": "出库日期", "title": "出库日期"},
            {"key": "物料名称", "title": "物料名称"},
            {"key": "领用车间", "title": "领用车间"},
        ],
        total_rows=3,
        source="feishu_bitable",
        last_synced_at=datetime.now(UTC),
    )
    await service.repo.replace_material_page_rows(
        snapshot.id,
        [
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_ledger_1",
                row_order=1,
                cells={
                    "出库日期": 1761580800000,
                    "物料名称": "葡萄糖",
                    "领用车间": "202车间",
                },
                search_text="葡萄糖 202车间",
            ),
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_ledger_2",
                row_order=2,
                cells={
                    "出库日期": 1761494400000,
                    "物料名称": "黄原胶",
                    "领用车间": "203车间",
                },
                search_text="黄原胶 203车间",
            ),
            MaterialPageRow(
                page_snapshot_id=snapshot.id,
                source_record_id="rec_ledger_3",
                row_order=3,
                cells={
                    "出库日期": 1761580800000,
                    "物料名称": "蛋白胨",
                    "领用车间": "202车间",
                },
                search_text="蛋白胨 202车间",
            ),
        ],
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/warehouse/material-pages/raw-ledger",
        params={
            "source": "local",
            "date_field": "出库日期",
            "start_date": "2025-10-28",
            "end_date": "2025-10-28",
            "filters": json.dumps(
                [{"field": "领用车间", "operator": "eq", "value": "202车间"}],
                ensure_ascii=False,
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["total"] == 2
    assert [row["__record_id"] for row in body["data"]["rows"]] == [
        "rec_ledger_1",
        "rec_ledger_3",
    ]


@pytest.mark.anyio
async def test_get_material_page_rejects_invalid_advanced_filters(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/warehouse/material-pages/raw-summary",
        params={"source": "local", "filters": "{bad-json}"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["message"] == "高级筛选参数格式错误"


@pytest.mark.anyio
async def test_get_warehouse_trend_summary(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_trend_snapshots(db_session)

    response = await client.get("/api/v1/warehouse/ai/trend-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"] == {
        "total": 2,
        "high_risk": 1,
        "medium_risk": 1,
        "raw_count": 1,
        "packaging_count": 1,
    }


@pytest.mark.anyio
async def test_get_warehouse_trend_anomalies(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_trend_snapshots(db_session)

    response = await client.get("/api/v1/warehouse/ai/trend-anomalies")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert len(body["data"]) == 2
    assert body["data"][0]["material_name"] == "趋势测试原料"
    assert body["data"][0]["risk_level"] == "high"


@pytest.mark.anyio
async def test_get_warehouse_trend_product_lines(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_trend_snapshots(db_session)

    response = await client.get("/api/v1/warehouse/ai/trend-product-lines")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert any(item["product_line"] == "FA" for item in body["data"])
    assert any(item["product_line"] == "MC" for item in body["data"])
