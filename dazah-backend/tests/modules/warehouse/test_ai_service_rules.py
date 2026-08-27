from datetime import UTC, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.warehouse.ai_service import (
    WarehouseAIService,
    WarehouseAnomalyItem,
    WarehouseHardwareCostAnomalyItem,
    WarehouseTrendAnomalyItem,
    build_query_plan,
    parse_chat_question,
)

SimpleNamespace: Any = _SimpleNamespace


@pytest.mark.parametrize(
    ("question", "domain", "metric", "dimension", "intent", "time_type"),
    [
        (
            "2026年6月五金费用最高的车间",
            "hardware",
            "cost",
            "workshop",
            "topn",
            "specific_month",
        ),
        (
            "12月五金领用费用明细",
            "hardware",
            "cost",
            "material",
            "detail",
            "specific_month",
        ),
        (
            "2026-05五金成本情况",
            "hardware",
            "cost",
            "material",
            "summary",
            "specific_month",
        ),
        (
            "本月包材库存不足有哪些",
            "packaging",
            "inventory",
            "material",
            "anomaly",
            "current_month",
        ),
        (
            "上月原辅料库存最低排名",
            "raw",
            "inventory",
            "month",
            "topn",
            "last_month",
        ),
        ("最近14天原料用量趋势", "raw", "usage", "material", None, "last_n_days"),
        (
            "最近7天产品线包材消耗变化",
            "packaging",
            "usage",
            "product_line",
            None,
            "last_n_days",
        ),
        (
            "最近30天成品库存概览",
            "product",
            "inventory",
            "day",
            "summary",
            "last_n_days",
        ),
        ("本周原料趋势异常", "raw", "trend", "material", "anomaly", "current_week"),
        ("上周包材用量明细", "packaging", "usage", "material", "detail", "last_week"),
        (
            "当前仓储情况怎么样",
            "warehouse_all",
            "inventory",
            None,
            "summary",
            "current",
        ),
    ],
)
def test_parse_chat_question_recognizes_business_dimensions(
    question: str,
    domain: str,
    metric: str,
    dimension: str | None,
    intent: str | None,
    time_type: str,
) -> None:
    parsed = parse_chat_question(question)

    assert parsed["domain"] == domain
    assert parsed["metric"] == metric
    assert parsed["dimension"] == dimension
    assert parsed["intent"] == intent
    assert parsed["time_range"]["type"] == time_type  # type: ignore[index]
    assert parsed["filters"]["_raw_question"] == question.lower()


def test_parse_chat_question_requests_required_clarification() -> None:
    hardware = parse_chat_question("五金费用异常")
    unspecified = parse_chat_question("异常偏高")

    assert hardware["needs_clarification"] is True
    assert hardware["clarification_question"] == "你看本月、上月，还是指定月份？"
    assert unspecified["needs_clarification"] is True
    assert unspecified["clarification_question"] == "你看原辅料/包材，还是五金？"


@pytest.mark.parametrize(
    ("question", "query_type", "sources", "group_by", "limit"),
    [
        (
            "原料快用完，一周内会不会断料",
            "stockout_risk",
            ["raw-ledger", "packaging-ledger", "raw_materials", "packaging_materials"],
            "material",
            20,
        ),
        (
            "本月五金费用最高车间排名",
            "hardware_cost_ranking",
            ["hardware-outbound-ledger"],
            "workshop",
            5,
        ),
        (
            "上月五金费用详细列表",
            "hardware_cost_anomaly",
            ["hardware-outbound-ledger"],
            "workshop",
            20,
        ),
        ("原料库存不足异常", "inventory_shortage", ["raw_materials"], "material", 10),
        (
            "包材库存最低排名",
            "inventory_ranking",
            ["packaging_materials"],
            "material",
            10,
        ),
        (
            "最近7天产品线原料用量趋势",
            "product_line_trend",
            ["raw-ledger", "raw_materials"],
            "product_line",
            10,
        ),
        ("成品库存最多排名", "product_ranking", ["products"], None, 10),
        ("成品情况怎么样", "product_overview", ["products"], None, 10),
        (
            "总结当前最需要关注的核心问题",
            "warehouse_focus",
            [
                "raw_materials",
                "packaging_materials",
                "products",
                "hardware-outbound-ledger",
            ],
            None,
            20,
        ),
        (
            "仓储整体情况",
            "warehouse_summary",
            [
                "raw_materials",
                "packaging_materials",
                "products",
                "hardware-outbound-ledger",
            ],
            None,
            20,
        ),
        (
            "你好",
            "warehouse_summary",
            ["raw_materials", "packaging_materials", "products"],
            None,
            10,
        ),
    ],
)
def test_build_query_plan_routes_supported_questions(
    question: str,
    query_type: str,
    sources: list[str],
    group_by: str | None,
    limit: int,
) -> None:
    plan = build_query_plan(parse_chat_question(question))

    assert plan["query_type"] == query_type
    assert plan["data_sources"] == sources
    assert plan["group_by"] == group_by
    assert plan["limit"] == limit


def test_build_query_plan_preserves_clarification_and_time_window() -> None:
    clarification = build_query_plan(parse_chat_question("五金费用"))
    timed = build_query_plan(parse_chat_question("2026年6月五金费用明细"))

    assert clarification["needs_clarification"] is True
    assert clarification["query_type"] == ""
    assert timed["time_window"]["type"] == "specific_month"  # type: ignore[index]
    assert timed["sort_by"] == "cost"


def test_anomaly_value_objects_serialize_all_business_fields() -> None:
    detected_at = datetime(2026, 8, 20, 8, tzinfo=UTC)
    anomaly = WarehouseAnomalyItem(
        "stock_low", "high", "乙醇", "raw", {"gap": 20}, "立即补货", detected_at
    )
    trend = WarehouseTrendAnomalyItem(
        material_name="标签",
        material_type="packaging",
        product_line="制剂线",
        current_week_usage=100,
        history_week_avg_usage=50,
        usage_delta_ratio=1,
        current_inventory=20,
        safety_inventory=50,
        estimated_cover_days=1.4,
        risk_level="high",
        reason="消耗上升",
        suggestion="补货",
    )
    hardware = WarehouseHardwareCostAnomalyItem(
        workshop_name="201车间",
        current_month_cost=2000,
        history_month_avg_cost=1000,
        cost_delta_ratio=1,
        risk_level="high",
        reason="费用翻倍",
        suggestion="核查领用",
    )

    assert anomaly.to_dict()["detected_at"] == detected_at.isoformat()
    assert trend.to_dict()["estimated_cover_days"] == 1.4
    assert hardware.to_dict()["workshop_name"] == "201车间"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            datetime(2026, 8, 20, tzinfo=UTC),
            datetime(
                2026,
                8,
                20,
                8,
                tzinfo=WarehouseAIService._parse_datetime_value(  # type: ignore[union-attr]
                    datetime(2026, 8, 20, tzinfo=UTC)
                ).tzinfo,
            ),
        ),
        (
            1_777_500_000_000,
            datetime.fromtimestamp(
                1_777_500_000,
                tz=WarehouseAIService._parse_datetime_value(1_777_500_000).tzinfo,  # type: ignore[union-attr]
            ),
        ),
        ("2026/08/20", WarehouseAIService._parse_datetime_value("2026-08-20")),
        ("not-a-date", None),
        ("", None),
        (object(), None),
    ],
)
def test_parse_datetime_value_handles_supported_and_invalid_values(
    value: object, expected: datetime | None
) -> None:
    assert WarehouseAIService._parse_datetime_value(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(12, 12.0), ("1,234.5", 1234.5), ("", None), ("bad", None), (None, None)],
)
def test_parse_float_value(value: object, expected: float | None) -> None:
    assert WarehouseAIService._parse_float_value(value) == expected


def test_inventory_shortage_rule_excludes_unmonitored_and_test_rows() -> None:
    service = WarehouseAIService(MagicMock())
    now = datetime(2026, 8, 20, tzinfo=UTC)

    assert (
        service._build_inventory_shortage_anomaly(
            material=SimpleNamespace(
                source="test", safety=10, available=0, name="测试物料"
            ),
            material_type="raw",
            now=now,
        )
        is None
    )
    assert (
        service._build_inventory_shortage_anomaly(
            material=SimpleNamespace(
                source="feishu", safety=0, available=0, name="未监控物料"
            ),
            material_type="raw",
            now=now,
        )
        is None
    )
    assert (
        service._build_inventory_shortage_anomaly(
            material=SimpleNamespace(
                source="feishu",
                safety=10,
                available=20,
                warning="正常",
                name="充足物料",
            ),
            material_type="raw",
            now=now,
        )
        is None
    )


@pytest.mark.parametrize(
    ("material_type", "available", "warning", "severity"),
    [
        ("raw", 0, "库存严重不足", "high"),
        ("packaging", 5, "库存不足", "medium"),
        ("raw", 5, "", "medium"),
    ],
)
def test_inventory_shortage_rule_builds_actionable_anomaly(
    material_type: str, available: float, warning: str, severity: str
) -> None:
    service = WarehouseAIService(MagicMock())
    anomaly = service._build_inventory_shortage_anomaly(
        material=SimpleNamespace(
            source="feishu",
            safety="10",
            available=available,
            warning=warning,
            name="乙醇",
            code="RM-001",
            product_line="原料药",
        ),
        material_type=material_type,
        now=datetime(2026, 8, 20, tzinfo=UTC),
    )

    assert anomaly is not None
    assert anomaly.severity == severity
    assert anomaly.details["gap"] == 10 - available
    assert "请结合原辅料/包材总表尽快处理" in anomaly.suggestion


@pytest.mark.parametrize(
    ("usage", "history", "inventory", "safety", "risk"),
    [
        (0, 0, 100, 10, None),
        (100, 40, 20, 50, "high"),
        (10, 0, 5, 10, "high"),
        (70, 50, 200, 50, "medium"),
        (10, 0, 200, 50, "medium"),
        (50, 50, 500, 50, "low"),
        (50, 50, 500, 0, None),
    ],
)
def test_evaluate_trend_risk_covers_risk_levels(
    usage: float, history: float, inventory: float, safety: float, risk: str | None
) -> None:
    service = WarehouseAIService(MagicMock())

    result = service._evaluate_trend_risk(
        current_week_usage=usage,
        history_week_avg_usage=history,
        current_inventory=inventory,
        safety_inventory=safety,
    )

    assert result[0] == risk
    if risk is None:
        assert result[3:] == ("", "")
    else:
        assert result[3]
        assert result[4]


@pytest.mark.parametrize(
    ("query_type", "details", "expected_summary", "expected_basis"),
    [
        (
            "hardware_cost_anomaly",
            [{"key": "201车间", "total_cost": 1200, "count": 3}],
            "1 个车间五金费用异常偏高",
            "本月",
        ),
        (
            "hardware_cost_ranking",
            [{"key": "动力部", "total_cost": 900, "count": 2}],
            "1 个车间五金费用异常偏高",
            "本月",
        ),
        (
            "inventory_shortage",
            [
                {
                    "material_name": "乙醇",
                    "available": 2,
                    "safety": 10,
                    "gap": 8,
                    "severity": "high",
                }
            ],
            "1 个物料库存不足",
            "安全库存",
        ),
        (
            "trend_anomaly",
            [
                {
                    "material_name": "标签",
                    "current_week_usage": 10,
                    "history_week_avg_usage": 0,
                    "usage_delta_ratio": None,
                }
            ],
            "1 个物料趋势异常",
            "最近7天",
        ),
        (
            "stockout_risk",
            [
                {
                    "material_name": "乙醇",
                    "estimated_cover_days": 3.5,
                    "current_week_usage": 70,
                    "current_inventory": 35,
                }
            ],
            "1 个物料存在一周内断料风险",
            "可支撑天数",
        ),
        (
            "warehouse_focus",
            [{"category": "库存", "name": "乙醇", "metric": "缺口8", "risk": "高"}],
            "1 项需关注的问题",
            "综合库存不足",
        ),
        (
            "product_overview",
            [{"product_name": "阿莫西林", "inventory": 10, "unit": "kg"}],
            "1 个成品有库存记录",
            "成品库存总表",
        ),
        (
            "product_ranking",
            [{"product_name": "阿莫西林", "inventory": 10, "unit": "kg"}],
            "1 个成品有库存记录",
            "成品库存总表",
        ),
        (
            "warehouse_summary",
            [{"key": "库存总量", "total_cost": 10}],
            "仓储整体数据概览",
            "仓储全模块",
        ),
        ("unknown", [{"name": "乙醇"}], "查询结果共 1 条", ""),
    ],
)
def test_format_chat_answer_covers_supported_query_types(
    query_type: str,
    details: list[dict[str, object]],
    expected_summary: str,
    expected_basis: str,
) -> None:
    service = WarehouseAIService(MagicMock())

    answer = service.format_chat_answer(
        query_type=query_type,
        details=details,
        time_window={"type": "current_month"},
    )

    assert answer["status"] == "answered"
    assert expected_summary in answer["summary"]  # type: ignore[operator]
    assert expected_basis in (answer["basis"] or "")
    assert "## 结论" in answer["answer_text"]  # type: ignore[operator]


def test_format_chat_answer_handles_clarification_and_no_data() -> None:
    service = WarehouseAIService(MagicMock())

    clarification = service.format_chat_answer(
        query_type="",
        details=None,
        time_window=None,
        needs_clarification=True,
        clarification_question="请选择月份",
    )
    no_data = service.format_chat_answer(
        query_type="inventory_shortage", details=[], time_window=None
    )

    assert clarification["status"] == "need_clarification"
    assert clarification["answer_text"] == "请选择月份"
    assert no_data["status"] == "no_data"
    assert no_data["answer_text"] == "暂无相关数据。"
