from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.warehouse.ai_service import (
    CHINA_TIMEZONE,
    WarehouseAIService,
    build_query_plan,
    parse_chat_question,
)
from app.modules.warehouse.models import MaterialPageRow
from app.modules.warehouse.service import WarehouseService


def _timestamp_days_ago(days_ago: int) -> int:
    target = datetime.now(UTC) - timedelta(days=days_ago)
    return int(target.timestamp() * 1000)


async def _seed_trend_snapshots(db_session) -> None:
    service = WarehouseService(db_session)

    await service.upsert_raw_material_snapshot(
        source_id="raw-trend-1",
        code="YS-TREND-1",
        name="趋势测试原料",
        spec="25kg/袋",
        unit="kg",
        available=90,
        safety=120,
        last_month=0,
        two_months_ago=0,
        today_balance=90,
        front_stock=0,
        this_month_use=0,
        warning="",
        product_line="FA",
        erp_no=None,
        delivery="",
        remark="",
        source="test",
    )
    await service.upsert_packaging_snapshot(
        source_id="pack-trend-1",
        code="BO-TREND-1",
        name="趋势测试包材",
        spec="420*620mm",
        batch="batch-1",
        available=200,
        safety=80,
        last_month=0,
        two_months_ago=0,
        today_balance=200,
        front_stock=0,
        this_month_use=0,
        warning="",
        product_line="MC",
        erp_no=None,
        delivery="",
        remark="",
        source="test",
    )

    raw_snapshot = await service.repo.upsert_material_page_snapshot(
        page_key="raw-ledger",
        page_title="原辅料出库总账",
        table_name="原辅料出库总账",
        table_id="tbl-raw-ledger-trend",
        columns=[
            {"key": "出库日期", "title": "出库日期"},
            {"key": "物料名称", "title": "物料名称"},
            {"key": "领用数量（Kg）", "title": "领用数量（Kg）"},
        ],
        total_rows=6,
        source="test",
        last_synced_at=datetime.now(UTC),
    )
    await service.repo.replace_material_page_rows(
        raw_snapshot.id,
        [
            MaterialPageRow(
                page_snapshot_id=raw_snapshot.id,
                source_record_id=f"raw-trend-{idx}",
                row_order=idx,
                cells={
                    "出库日期": _timestamp_days_ago(days_ago),
                    "物料名称": "趋势测试原料",
                    "领用数量（Kg）": quantity,
                },
                search_text="趋势测试原料",
            )
            for idx, (days_ago, quantity) in enumerate(
                [
                    (1, 80),
                    (3, 70),
                    (10, 20),
                    (17, 15),
                    (24, 10),
                    (31, 15),
                ],
                start=1,
            )
        ],
    )

    packaging_snapshot = await service.repo.upsert_material_page_snapshot(
        page_key="packaging-ledger",
        page_title="包材出库总账",
        table_name="包材出库总账",
        table_id="tbl-packaging-ledger-trend",
        columns=[
            {"key": "出库日期", "title": "出库日期"},
            {"key": "物料名称", "title": "物料名称"},
            {"key": "出库数量", "title": "出库数量"},
        ],
        total_rows=5,
        source="test",
        last_synced_at=datetime.now(UTC),
    )
    await service.repo.replace_material_page_rows(
        packaging_snapshot.id,
        [
            MaterialPageRow(
                page_snapshot_id=packaging_snapshot.id,
                source_record_id=f"pack-trend-{idx}",
                row_order=idx,
                cells={
                    "出库日期": _timestamp_days_ago(days_ago),
                    "物料名称": "趋势测试包材",
                    "出库数量": quantity,
                },
                search_text="趋势测试包材",
            )
            for idx, (days_ago, quantity) in enumerate(
                [
                    (2, 40),
                    (5, 30),
                    (11, 25),
                    (18, 20),
                    (25, 15),
                ],
                start=1,
            )
        ],
    )
    await db_session.commit()


async def _seed_zero_safety_materials(db_session) -> None:
    service = WarehouseService(db_session)

    await service.upsert_raw_material_snapshot(
        source_id="raw-zero-safety-1",
        code="YS-ZERO-1",
        name="零安全库存原料",
        spec="25kg/袋",
        unit="kg",
        available=0,
        safety=0,
        last_month=0,
        two_months_ago=0,
        today_balance=0,
        front_stock=0,
        this_month_use=0,
        warning="缺货",
        product_line="FA",
        erp_no=None,
        delivery="",
        remark="",
        source="test",
    )
    await service.upsert_packaging_snapshot(
        source_id="pack-zero-safety-1",
        code="BO-ZERO-1",
        name="零安全库存包材",
        spec="420*620mm",
        batch="batch-1",
        available=0,
        safety=0,
        last_month=0,
        two_months_ago=0,
        today_balance=0,
        front_stock=0,
        this_month_use=0,
        warning="缺货",
        product_line="MC",
        erp_no=None,
        delivery="",
        remark="",
        source="test",
    )

    raw_snapshot = await service.repo.upsert_material_page_snapshot(
        page_key="raw-ledger",
        page_title="原辅料出库总账",
        table_name="原辅料出库总账",
        table_id="tbl-raw-ledger-zero-safety",
        columns=[
            {"key": "出库日期", "title": "出库日期"},
            {"key": "物料名称", "title": "物料名称"},
            {"key": "领用数量（Kg）", "title": "领用数量（Kg）"},
        ],
        total_rows=6,
        source="test",
        last_synced_at=datetime.now(UTC),
    )
    await service.repo.replace_material_page_rows(
        raw_snapshot.id,
        [
            MaterialPageRow(
                page_snapshot_id=raw_snapshot.id,
                source_record_id=f"raw-zero-safety-{idx}",
                row_order=idx,
                cells={
                    "出库日期": _timestamp_days_ago(days_ago),
                    "物料名称": "零安全库存原料",
                    "领用数量（Kg）": quantity,
                },
                search_text="零安全库存原料",
            )
            for idx, (days_ago, quantity) in enumerate(
                [
                    (1, 20),
                    (3, 20),
                    (5, 20),
                    (10, 1),
                    (17, 1),
                    (24, 1),
                ],
                start=1,
            )
        ],
    )
    await db_session.commit()


async def _seed_real_inventory_shortage_materials(db_session) -> None:
    service = WarehouseService(db_session)

    await service.upsert_raw_material_snapshot(
        source_id="raw-real-shortage-1",
        code="YS-REAL-1",
        name="真实缺料原料",
        spec="25kg/袋",
        unit="kg",
        available=10,
        safety=100,
        last_month=0,
        two_months_ago=0,
        today_balance=10,
        front_stock=0,
        this_month_use=0,
        warning="库存不足",
        product_line="FA",
        erp_no=None,
        delivery="",
        remark="",
        source="feishu",
    )
    await service.upsert_packaging_snapshot(
        source_id="pack-real-shortage-1",
        code="BO-REAL-1",
        name="真实缺料包材",
        spec="420*620mm",
        batch="batch-1",
        available=0,
        safety=50,
        last_month=0,
        two_months_ago=0,
        today_balance=0,
        front_stock=0,
        this_month_use=0,
        warning="库存严重不足",
        product_line="MC",
        erp_no=None,
        delivery="",
        remark="",
        source="feishu",
    )
    await service.upsert_raw_material_snapshot(
        source_id="raw-test-shortage-1",
        code="YS-TEST-1",
        name="测试缺料原料",
        spec="25kg/袋",
        unit="kg",
        available=0,
        safety=80,
        last_month=0,
        two_months_ago=0,
        today_balance=0,
        front_stock=0,
        this_month_use=0,
        warning="库存严重不足",
        product_line="FA",
        erp_no=None,
        delivery="",
        remark="",
        source="test",
    )
    await db_session.commit()


@pytest.mark.anyio
async def test_get_material_trend_anomalies_flags_high_risk_raw_material(
    db_session,
) -> None:
    await _seed_trend_snapshots(db_session)

    ai_service = WarehouseAIService(db_session)
    anomalies = await ai_service.get_material_trend_anomalies()

    target = next(item for item in anomalies if item["material_name"] == "趋势测试原料")
    assert target["material_type"] == "raw"
    assert target["risk_level"] == "high"
    assert target["current_week_usage"] == 150.0
    assert target["history_week_avg_usage"] == 15.0
    assert target["usage_delta_ratio"] == 9.0
    assert target["estimated_cover_days"] == 4.2


@pytest.mark.anyio
async def test_run_anomaly_detection_only_returns_real_inventory_shortage_materials(
    db_session,
) -> None:
    ai_service = WarehouseAIService(db_session)
    before_summary = await ai_service.get_inventory_summary()

    await _seed_real_inventory_shortage_materials(db_session)

    anomalies = await ai_service.run_anomaly_detection()
    summary = await ai_service.get_inventory_summary()

    anomaly_pairs = {(item.material_name, item.material_type) for item in anomalies}
    assert ("真实缺料原料", "raw") in anomaly_pairs
    assert ("真实缺料包材", "packaging") in anomaly_pairs
    assert ("测试缺料原料", "raw") not in anomaly_pairs
    assert (
        summary["summary"]["anomaly_count"]
        >= before_summary["summary"]["anomaly_count"]
    )


@pytest.mark.anyio
async def test_zero_safety_materials_are_excluded_from_ai_anomalies(
    db_session,
) -> None:
    ai_service = WarehouseAIService(db_session)
    summary_before = await ai_service.get_inventory_summary()

    await _seed_zero_safety_materials(db_session)

    anomalies = await ai_service.run_anomaly_detection()
    summary_after = await ai_service.get_inventory_summary()
    trend_anomalies = await ai_service.get_material_trend_anomalies()

    excluded_names = {"零安全库存原料", "零安全库存包材"}

    assert all(item.material_name not in excluded_names for item in anomalies)
    assert all(item["material_name"] not in excluded_names for item in trend_anomalies)
    assert (
        summary_after["raw_materials"]["zero_stock"]
        == summary_before["raw_materials"]["zero_stock"]
    )
    assert (
        summary_after["raw_materials"]["low_stock"]
        == summary_before["raw_materials"]["low_stock"]
    )
    assert (
        summary_after["raw_materials"]["warning"]
        == summary_before["raw_materials"]["warning"]
    )
    assert (
        summary_after["packaging_materials"]["zero_stock"]
        == summary_before["packaging_materials"]["zero_stock"]
    )
    assert (
        summary_after["packaging_materials"]["low_stock"]
        == summary_before["packaging_materials"]["low_stock"]
    )
    assert (
        summary_after["packaging_materials"]["warning"]
        == summary_before["packaging_materials"]["warning"]
    )
    assert (
        summary_after["summary"]["anomaly_count"]
        == summary_before["summary"]["anomaly_count"]
    )


@pytest.mark.anyio
async def test_get_product_line_trend_overview_and_summary(
    db_session,
) -> None:
    await _seed_trend_snapshots(db_session)

    ai_service = WarehouseAIService(db_session)
    overview = await ai_service.get_product_line_trend_overview()
    summary = await ai_service.get_trend_anomaly_summary()

    assert summary == {
        "total": 2,
        "high_risk": 1,
        "medium_risk": 1,
        "raw_count": 1,
        "packaging_count": 1,
    }
    assert overview[0]["product_line"] == "FA"
    assert overview[0]["high_risk_count"] == 1

    packaging_line = next(item for item in overview if item["product_line"] == "MC")
    assert packaging_line["medium_risk_count"] == 1
    assert packaging_line["current_week_usage"] == 70.0
    assert packaging_line["history_week_avg_usage"] == 15.0


@pytest.mark.anyio
async def test_parse_chat_question_hardware_cost_last_month() -> None:
    """Test parsing hardware cost question with last_month time range."""
    query = parse_chat_question("上月哪些车间五金领用费用异常偏高")

    assert query["domain"] == "hardware"
    assert query["metric"] == "cost"
    assert query["dimension"] == "workshop"
    assert query["intent"] == "anomaly"
    assert query["time_range"]["type"] == "last_month"
    assert query["needs_clarification"] is False


@pytest.mark.anyio
async def test_parse_chat_question_hardware_cost_needs_clarification() -> None:
    """Test parsing hardware cost question without time range."""
    query = parse_chat_question("哪些车间五金费用异常")

    assert query["domain"] == "hardware"
    assert query["metric"] == "cost"
    assert query["needs_clarification"] is True
    assert query["clarification_question"] == "你看本月、上月，还是指定月份？"


@pytest.mark.anyio
async def test_parse_chat_question_raw_inventory() -> None:
    """Test parsing raw material inventory question."""
    query = parse_chat_question("哪些原辅料库存不足")

    assert query["domain"] == "raw"
    assert query["metric"] == "inventory"
    assert query["intent"] == "anomaly"
    assert query["needs_clarification"] is False


@pytest.mark.anyio
async def test_parse_chat_question_product_overview() -> None:
    """Test parsing product overview question."""
    query = parse_chat_question("现在成品库存情况怎么样")

    assert query["domain"] == "product"
    assert query["metric"] == "inventory"
    assert query["intent"] == "summary"
    assert query["time_range"]["type"] == "current"


@pytest.mark.anyio
async def test_build_query_plan_hardware_cost() -> None:
    """Test building query plan for hardware cost."""
    query = parse_chat_question("上月哪些车间五金领用费用异常偏高")
    plan = build_query_plan(query)

    assert plan["query_type"] == "hardware_cost_anomaly"
    assert plan["data_sources"] == ["hardware-outbound-ledger"]
    assert plan["group_by"] == "workshop"
    assert plan["comparison_mode"] == "month_vs_3month_avg"
    assert plan["needs_clarification"] is False


@pytest.mark.anyio
async def test_build_query_plan_inventory_shortage() -> None:
    """Test building query plan for inventory shortage."""
    query = parse_chat_question("哪些原辅料库存不足")
    plan = build_query_plan(query)

    assert plan["query_type"] == "inventory_shortage"
    assert plan["data_sources"] == ["raw_materials"]
    assert plan["group_by"] == "material"
    assert plan["comparison_mode"] == "safety_stock"


@pytest.mark.anyio
async def test_build_query_plan_needs_clarification() -> None:
    """Test building query plan when clarification is needed."""
    query = parse_chat_question("哪些车间五金费用异常")
    plan = build_query_plan(query)

    assert plan["needs_clarification"] is True
    assert plan["clarification_question"] == "你看本月、上月，还是指定月份？"


@pytest.mark.anyio
async def test_query_hardware_cost_by_time_range(db_session) -> None:
    """Test querying hardware cost by dynamic time range."""
    await _seed_trend_snapshots(db_session)

    ai_service = WarehouseAIService(db_session)

    # Query current month hardware cost
    now = datetime.now(UTC)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    time_window = {
        "start": current_month_start,
        "end": now,
        "type": "current_month",
    }

    results = await ai_service.query_hardware_cost_by_time_range(
        time_window=time_window,
        group_by="workshop",
        limit=10,
        sort_by="cost",
    )

    # Results should be a list (may be empty if no hardware data in test)
    assert isinstance(results, list)


@pytest.mark.anyio
async def test_query_inventory_shortage_data(db_session) -> None:
    """Test querying inventory shortage data."""
    await _seed_trend_snapshots(db_session)

    ai_service = WarehouseAIService(db_session)

    results = await ai_service.query_inventory_shortage_data(
        domain="raw",
        limit=10,
    )

    # Results should be a list
    assert isinstance(results, list)

    # If there are results, check structure
    if results:
        item = results[0]
        assert "material_name" in item
        assert "material_type" in item
        assert "available" in item
        assert "safety" in item
        assert "gap" in item


@pytest.mark.anyio
async def test_chat_with_ai_returns_clarification(db_session) -> None:
    """Test chat_with_ai returns clarification when needed."""
    ai_service = WarehouseAIService(db_session)

    response = await ai_service.chat_with_ai("哪些车间五金费用异常")

    # Should return clarification question
    assert "你看本月、上月" in response or "请补充" in response


@pytest.mark.anyio
async def test_chat_with_ai_returns_structured_answer(db_session) -> None:
    """Test chat_with_ai returns structured answer."""
    await _seed_trend_snapshots(db_session)

    ai_service = WarehouseAIService(db_session)

    response = await ai_service.chat_with_ai("哪些原辅料库存不足")

    # Should return structured answer with sections
    assert "## 结论" in response or "共发现" in response or "暂无" in response


def _row(**cells: object) -> SimpleNamespace:
    return SimpleNamespace(cells=cells)


@pytest.mark.anyio
async def test_hardware_cost_and_ledger_anomaly_paths_cover_realistic_rows() -> None:
    """Exercise the migrated warehouse analytics against representative ledger data."""

    now = datetime.now(CHINA_TIMEZONE)
    current = now.replace(day=max(1, now.day - 1), hour=10, minute=0, second=0)
    history = now.replace(day=2, hour=10, minute=0, second=0)
    if history >= now.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
        history = now - timedelta(days=45)
    rows = [
        _row(领用车间="动力部", 物料名称="螺栓", 日期=current.isoformat(), 金额="100"),
        _row(领用车间="动力部", 物料名称="垫片", 日期=history.isoformat(), 金额="50"),
        _row(
            领用车间="动力部",
            物料名称="螺母",
            日期=(history - timedelta(days=5)).isoformat(),
            金额="50",
        ),
        _row(
            领用车间="动力部",
            物料名称="扳手",
            日期=(history - timedelta(days=10)).isoformat(),
            金额="50",
        ),
        _row(领用车间="质量部", 物料名称="手套", 日期=current.isoformat(), 金额="130"),
        _row(
            领用车间="质量部",
            物料名称="手套",
            日期=(history - timedelta(days=5)).isoformat(),
            金额="100",
        ),
        _row(
            领用车间="质量部",
            物料名称="手套",
            日期=(history - timedelta(days=10)).isoformat(),
            金额="100",
        ),
        _row(
            领用车间="质量部",
            物料名称="手套",
            日期=(history - timedelta(days=15)).isoformat(),
            金额="100",
        ),
        _row(领用车间="", 物料名称="忽略", 日期=current.isoformat(), 金额="10"),
        _row(领用车间="仓储部", 物料名称="坏日期", 日期="bad", 金额="10"),
        _row(领用车间="仓储部", 物料名称="负数", 日期=current.isoformat(), 金额="-1"),
        _row(
            领用车间="仓储部",
            物料名称="超范围",
            日期=(now - timedelta(days=200)).isoformat(),
            金额="10",
        ),
    ]
    snapshot = SimpleNamespace(id=1)

    repo = SimpleNamespace(
        get_material_page_snapshot=AsyncMock(return_value=snapshot),
        list_material_page_rows=AsyncMock(return_value=(rows, len(rows))),
        list_raw_materials=AsyncMock(
            return_value=[SimpleNamespace(name="乙醇", safety="10")]
        ),
    )
    service = WarehouseAIService.__new__(WarehouseAIService)
    service.repo = repo
    service.session = SimpleNamespace()

    anomalies = await service.get_hardware_cost_anomalies()
    assert [item["workshop_name"] for item in anomalies] == ["质量部", "动力部"]
    assert anomalies[0]["risk_level"] == "medium"
    assert anomalies[1]["risk_level"] == "high"

    summary = await service.get_hardware_cost_summary()
    assert summary["total_workshops"] == 3
    assert summary["anomaly_workshops"] == 2

    workshop = await service.query_hardware_cost_by_time_range(
        {"start": current, "end": now, "type": "current_month"},
        group_by="workshop",
        sort_by="count",
    )
    assert workshop[0]["key"] in {"动力部", "质量部"}
    material = await service.query_hardware_cost_by_time_range(
        {"start": current, "end": now, "type": "current_month"},
        group_by="material",
        sort_by="unknown",
    )
    assert material[0]["key"] in {"螺栓", "手套"}
    daily = await service.query_hardware_cost_by_time_range(
        {"start": current, "end": now, "type": "current_month"},
        group_by="day",
    )
    assert daily and daily[0]["key"] == current.strftime("%Y-%m-%d")

    ledger_rows = [
        _row(物料名称="乙醇", **{"领用数量（Kg）": 1}),
        _row(物料名称="乙醇", **{"领用数量（Kg）": "1"}),
        _row(物料名称="乙醇", **{"领用数量（Kg）": 1}),
        _row(物料名称="乙醇", **{"出库数量": 100}),
        _row(物料名称="未知", **{"出库数量": 7}),
        _row(物料名称="乙醇", **{"出库数量": "bad"}),
    ]
    repo.get_material_page_snapshot = AsyncMock(return_value=snapshot)
    repo.list_material_page_rows = AsyncMock(
        return_value=(ledger_rows, len(ledger_rows))
    )
    ledger = await service._detect_ledger_anomalies(now)
    assert ledger and ledger[0].anomaly_type == "unusual_outbound"


@pytest.mark.anyio
async def test_product_inventory_and_shortage_queries_cover_filters() -> None:
    class _Result:
        def __init__(self, values: list[object]) -> None:
            self.values = values

        def scalars(self) -> "_Result":
            return self

        def all(self) -> list[object]:
            return self.values

    raw = SimpleNamespace(
        name="原料A",
        code="R-A",
        safety="10",
        available=0,
        warning="库存严重不足",
        product_line="FA",
        source="feishu",
    )
    packaging = SimpleNamespace(
        name="包材A",
        code="P-A",
        safety=20,
        available=5,
        warning="库存不足",
        product_line="MC",
        source="feishu",
    )
    products = [
        SimpleNamespace(
            name="成品A",
            spec="S-A",
            remaining_quantity=20,
            unit="kg",
            qualified_quantity=18,
            pending_quantity=2,
            subtotal_quantity=20,
            source="feishu",
        ),
        SimpleNamespace(
            name="成品B",
            spec=None,
            remaining_quantity=0,
            unit=None,
            qualified_quantity=None,
            pending_quantity=None,
            subtotal_quantity=None,
            source="feishu",
        ),
    ]
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[_Result([raw]), _Result([packaging]), _Result(products)]
        )
    )
    service = WarehouseAIService.__new__(WarehouseAIService)
    service.session = session
    service.repo = SimpleNamespace()

    assert (await service.query_inventory_shortage_data("raw", 10))[0][
        "severity"
    ] == "high"
    assert (await service.query_inventory_shortage_data("packaging", 10))[0][
        "severity"
    ] == "medium"
    assert await service.query_inventory_shortage_data("other", 10) == []
    product_items = await service.query_product_inventory_overview(10, sort_by="name")
    assert [item["product_name"] for item in product_items] == ["成品A", "成品B"]


@pytest.mark.anyio
async def test_chat_routes_all_supported_query_plans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WarehouseAIService.__new__(WarehouseAIService)
    service.repo = SimpleNamespace()
    service.session = SimpleNamespace()
    monkeypatch.setattr(
        service,
        "query_hardware_cost_by_time_range",
        AsyncMock(return_value=[{"key": "动力部", "total_cost": 100, "count": 2}]),
    )
    monkeypatch.setattr(
        service,
        "query_inventory_shortage_data",
        AsyncMock(
            return_value=[
                {
                    "material_name": "乙醇",
                    "available": 2,
                    "safety": 10,
                    "gap": 8,
                    "severity": "high",
                }
            ]
        ),
    )
    trend = [
        {
            "material_name": "乙醇",
            "estimated_cover_days": 3,
            "current_week_usage": 20,
            "risk_level": "high",
            "product_line": "FA",
            "current_inventory": 10,
            "history_week_avg_usage": 5,
            "usage_delta_ratio": 3,
        }
    ]
    monkeypatch.setattr(
        service, "get_material_trend_anomalies", AsyncMock(return_value=trend)
    )
    monkeypatch.setattr(
        service,
        "get_product_line_trend_overview",
        AsyncMock(return_value=[{"product_line": "FA", "high_risk_count": 1}]),
    )
    monkeypatch.setattr(
        service,
        "query_product_inventory_overview",
        AsyncMock(
            return_value=[{"product_name": "成品A", "inventory": 3, "unit": "kg"}]
        ),
    )
    monkeypatch.setattr(
        service,
        "get_hardware_cost_anomalies",
        AsyncMock(
            return_value=[
                {
                    "workshop_name": "动力部",
                    "current_month_cost": 100,
                    "risk_level": "high",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        service,
        "get_inventory_summary",
        AsyncMock(
            return_value={
                "raw_materials": {"total": 1, "low_stock": 1},
                "packaging_materials": {"total": 1, "low_stock": 0},
                "products": {"total": 1},
            }
        ),
    )
    monkeypatch.setattr(service, "run_anomaly_detection", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service, "get_trend_anomaly_summary", AsyncMock(return_value={"total": 1})
    )
    monkeypatch.setattr(
        service,
        "get_hardware_cost_summary",
        AsyncMock(return_value={"total_workshops": 1, "anomaly_workshops": 1}),
    )

    questions = [
        "本月五金费用",
        "原料库存不足",
        "最近7天原料用量趋势",
        "原料快用完，一周内会不会断料",
        "总结当前最需要关注的核心问题",
        "最近7天产品线原料用量趋势",
        "成品情况怎么样",
        "仓储整体情况",
    ]
    responses = [await service.chat_with_ai(question) for question in questions]
    assert all("## 结论" in response for response in responses)


@pytest.mark.anyio
async def test_generate_analysis_report_maps_llm_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.llm.exceptions import (
        LLMConfigError,
        LLMOutputError,
        LLMRateLimitError,
    )

    service = WarehouseAIService.__new__(WarehouseAIService)
    service.repo = SimpleNamespace()
    service.session = SimpleNamespace()
    monkeypatch.setattr(
        service, "get_inventory_summary", AsyncMock(return_value={"total": 1})
    )
    monkeypatch.setattr(service, "run_anomaly_detection", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service, "get_trend_anomaly_summary", AsyncMock(return_value={"total": 0})
    )
    monkeypatch.setattr(
        service, "get_material_trend_anomalies", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        service, "get_product_line_trend_overview", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        service, "get_hardware_cost_summary", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        service, "get_hardware_cost_anomalies", AsyncMock(return_value=[])
    )

    from app.modules.warehouse import ai_service as module

    for error, expected in (
        (LLMConfigError("missing"), "尚未配置"),
        (LLMRateLimitError("busy"), "繁忙"),
        (LLMOutputError("bad"), "生成失败"),
        (TimeoutError(), "生成失败"),
    ):
        monkeypatch.setattr(
            module.llm_client, "chat_json", AsyncMock(side_effect=error)
        )
        report = await service.generate_analysis_report()
        assert expected in report["summary_text"]

    monkeypatch.setattr(
        module.llm_client,
        "chat_json",
        AsyncMock(return_value={"overall_status": "正常"}),
    )
    assert (await service.generate_analysis_report())["overall_status"] == "正常"
