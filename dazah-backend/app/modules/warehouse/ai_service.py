"""Warehouse AI analysis service for anomaly detection and intelligent Q&A."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.warehouse.models import (
    PackagingMaterialInventory,
    ProductInventory,
    RawMaterialInventory,
)
from app.modules.warehouse.repository import WarehouseRepository

CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


# Detection thresholds
STOCK_WARNING_THRESHOLD_DAYS = (
    30  # Days without outbound activity considered as backlog
)
LARGE_CHANGE_THRESHOLD_RATIO = 3.0  # 3x average change considered as anomaly
NEGATIVE_STOCK_THRESHOLD = 0  # Any negative stock is anomaly
TREND_HIGH_RISK_RATIO = 0.5
TREND_MEDIUM_RISK_RATIO = 0.3
TREND_HIGH_RISK_COVER_DAYS = 7
TREND_MEDIUM_RISK_COVER_DAYS = 14
TREND_LOOKBACK_DAYS = 7
TREND_BASELINE_WEEKS = 4
SHORTAGE_WARNING_TEXTS = ("库存不足", "库存严重不足")

# Hardware cost anomaly thresholds
HARDWARE_COST_HIGH_RISK_RATIO = 0.5  # 50% above average
HARDWARE_COST_MEDIUM_RISK_RATIO = 0.3  # 30% above average
HARDWARE_COST_LOOKBACK_MONTHS = 3


# Chat query parsing types
class WarehouseChatQuery(TypedDict, total=False):
    """Parsed user question structure for warehouse AI chat."""

    domain: str | None  # "raw", "packaging", "hardware", "product", "warehouse_all"
    metric: str | None  # "inventory", "usage", "cost", "anomaly", "trend", "ranking"
    dimension: str | None  # "material", "product_line", "workshop", "day", "month"
    intent: str | None  # "summary", "detail", "compare", "anomaly", "topn"
    time_range: dict[str, Any] | None  # {"type": "last_month", "value": "2026-06"}
    filters: dict[str, Any]  # {"workshop": "动力部", "material_type": "raw"}
    needs_clarification: bool
    clarification_question: str | None


class WarehouseQueryPlan(TypedDict, total=False):
    """Query execution plan for warehouse AI chat."""

    # inventory_shortage, trend_anomaly, hardware_cost, product_overview
    query_type: str
    data_sources: list[str]  # ["raw_materials", "raw-ledger"]
    group_by: str | None  # "workshop", "material", "product_line"
    comparison_mode: str | None  # "month_vs_3month_avg", "week_vs_4week_avg"
    limit: int
    sort_by: str | None  # "cost", "usage", "inventory"
    time_window: dict[str, Any] | None  # {"start": "2026-06-01", "end": "2026-06-30"}
    needs_clarification: bool
    clarification_question: str | None


class WarehouseChatAnswer(TypedDict, total=False):
    """Structured answer for warehouse AI chat."""

    status: str  # "answered", "need_clarification", "no_data"
    summary: str | None  # Brief conclusion
    details: list[dict[str, Any]] | None  # Detail data items
    basis: str | None  # Calculation basis
    suggestions: list[str] | None  # Action suggestions
    clarification_question: str | None  # Question to ask user
    answer_text: str | None  # Full natural language answer


def parse_chat_question(question: str) -> WarehouseChatQuery:
    """Parse user natural language question into structured query.

    Args:
        question: User's natural language question about warehouse.

    Returns:
        WarehouseChatQuery with parsed domain, metric, dimension, time_range, etc.
    """
    now = datetime.now(CHINA_TIMEZONE)

    # Initialize result
    result: WarehouseChatQuery = {
        "domain": None,
        "metric": None,
        "dimension": None,
        "intent": None,
        "time_range": None,
        "filters": {},
        "needs_clarification": False,
        "clarification_question": None,
    }

    # Normalize question
    q_lower = question.lower().strip()

    # 保留原文供规则层二次匹配（断料预测/关注总结等需要看问题全文）
    result["filters"]["_raw_question"] = q_lower

    # Domain detection
    domain_keywords = {
        "raw": ["原辅料", "原料", "辅料", "raw", "原材料"],
        "packaging": ["包材", "包装材料", "packaging", "包装"],
        "hardware": ["五金", "hardware", "车间五金", "五金领用"],
        "product": ["成品", "product", "产品", "产成品"],
    }

    for domain, keywords in domain_keywords.items():
        if any(kw in q_lower for kw in keywords):
            result["domain"] = domain
            break

    # If no domain detected, check for warehouse-wide keywords
    if result["domain"] is None:
        warehouse_keywords = ["仓储", "库存", "仓库", "warehouse", "物料"]
        if any(kw in q_lower for kw in warehouse_keywords):
            result["domain"] = "warehouse_all"

    # Metric detection - order by specificity, more specific keywords first
    metric_keywords = {
        "cost": ["费用", "金额", "cost", "花费", "成本"],
        "inventory": [
            "库存不足",
            "库存量",
            "低库存",
            "零库存",
            "库存",
            "inventory",
            "存量",
        ],
        "usage": ["用量", "消耗", "领用", "usage", "使用量", "出库"],
        "trend": ["趋势", "波动", "trend", "变化", "上升", "下降"],
        "ranking": ["排名", "最高", "最低", "最多", "最少", "top", "排名"],
        "anomaly": ["异常", "anomaly", "问题", "风险", "偏高", "偏低"],
    }

    for metric, keywords in metric_keywords.items():
        if any(kw in q_lower for kw in keywords):
            result["metric"] = metric
            break

    # Dimension detection
    dimension_keywords = {
        "workshop": ["车间", "workshop", "部门", "动力部", "研发中心"],
        "product_line": ["产品线", "product_line", "生产线"],
        "material": ["物料", "material", "原料", "包材", "五金"],
        "day": ["天", "day", "日", "每天"],
        "month": ["月", "month", "每月", "本月", "上月"],
    }

    for dimension, keywords in dimension_keywords.items():
        if any(kw in q_lower for kw in keywords):
            result["dimension"] = dimension
            break

    # Intent detection - order by specificity, more specific keywords first
    intent_keywords = {
        "anomaly": [
            "库存不足",
            "异常偏高",
            "异常",
            "偏高",
            "偏低",
            "不足",
            "anomaly",
            "风险",
        ],
        "topn": ["最高", "最低", "最多", "最少", "排名", "top"],
        "compare": ["对比", "比较", "compare", "差异", "偏差"],
        "summary": ["总结", "概览", "情况怎么样", "怎么样", "情况", "summary", "整体"],
        "detail": ["哪些", "明细", "具体", "detail", "详细", "列表"],
    }

    for intent, keywords in intent_keywords.items():
        if any(kw in q_lower for kw in keywords):
            result["intent"] = intent
            break

    # Time range detection
    time_patterns: list[tuple[re.Pattern[str] | str, str]] = [
        # Specific month: "2026年6月", "6月", "2026-06"
        (re.compile(r"(\d{4})年(\d{1,2})月"), "specific_month"),
        (re.compile(r"(\d{1,2})月(?!\d)"), "specific_month_current_year"),
        (re.compile(r"(\d{4}-\d{2})"), "specific_month_iso"),
        # Relative month: "本月", "上月", "上个月"
        ("本月", "current_month"),
        ("上月", "last_month"),
        ("上个月", "last_month"),
        # Relative days: "最近7天", "最近30天", "本周", "上周"
        (re.compile(r"最近(\d+)天"), "last_n_days"),
        ("最近7天", "last_7_days"),
        ("最近30天", "last_30_days"),
        ("本周", "current_week"),
        ("上周", "last_week"),
        # Current: "现在", "当前", "目前"
        ("现在", "current"),
        ("当前", "current"),
        ("目前", "current"),
    ]

    for pattern, time_type in time_patterns:
        if isinstance(pattern, str):
            if pattern in q_lower:
                if time_type == "current_month":
                    result["time_range"] = {
                        "type": "current_month",
                        "start": now.replace(
                            day=1, hour=0, minute=0, second=0, microsecond=0
                        ),
                        "end": now,
                    }
                elif time_type == "last_month":
                    first_of_this_month = now.replace(
                        day=1, hour=0, minute=0, second=0, microsecond=0
                    )
                    last_month_end = first_of_this_month - timedelta(days=1)
                    last_month_start = last_month_end.replace(day=1)
                    result["time_range"] = {
                        "type": "last_month",
                        "start": last_month_start,
                        "end": last_month_end,
                    }
                elif time_type == "current":
                    result["time_range"] = {
                        "type": "current",
                        "value": now,
                    }
                elif time_type == "last_7_days":
                    result["time_range"] = {
                        "type": "last_7_days",
                        "start": now - timedelta(days=7),
                        "end": now,
                    }
                elif time_type == "last_30_days":
                    result["time_range"] = {
                        "type": "last_30_days",
                        "start": now - timedelta(days=30),
                        "end": now,
                    }
                elif time_type == "current_week":
                    # Current week from Monday to now
                    week_start = now - timedelta(days=now.weekday())
                    week_start = week_start.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    result["time_range"] = {
                        "type": "current_week",
                        "start": week_start,
                        "end": now,
                    }
                elif time_type == "last_week":
                    # Last complete week
                    this_week_start = now - timedelta(days=now.weekday())
                    this_week_start = this_week_start.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    last_week_end = this_week_start - timedelta(days=1)
                    last_week_start = last_week_end - timedelta(days=6)
                    last_week_start = last_week_start.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    result["time_range"] = {
                        "type": "last_week",
                        "start": last_week_start,
                        "end": last_week_end,
                    }
                break
        else:
            # Regex pattern
            match = pattern.search(q_lower)
            if match:
                if time_type == "specific_month":
                    year = int(match.group(1))
                    month = int(match.group(2))
                    month_start = datetime(year, month, 1, tzinfo=CHINA_TIMEZONE)
                    if month == 12:
                        month_end = datetime(
                            year + 1, 1, 1, tzinfo=CHINA_TIMEZONE
                        ) - timedelta(days=1)
                    else:
                        month_end = datetime(
                            year, month + 1, 1, tzinfo=CHINA_TIMEZONE
                        ) - timedelta(days=1)
                    result["time_range"] = {
                        "type": "specific_month",
                        "start": month_start,
                        "end": month_end,
                        "label": f"{year}年{month}月",
                    }
                elif time_type == "specific_month_current_year":
                    month = int(match.group(1))
                    year = now.year
                    month_start = datetime(year, month, 1, tzinfo=CHINA_TIMEZONE)
                    if month == 12:
                        month_end = datetime(
                            year + 1, 1, 1, tzinfo=CHINA_TIMEZONE
                        ) - timedelta(days=1)
                    else:
                        month_end = datetime(
                            year, month + 1, 1, tzinfo=CHINA_TIMEZONE
                        ) - timedelta(days=1)
                    result["time_range"] = {
                        "type": "specific_month",
                        "start": month_start,
                        "end": month_end,
                        "label": f"{year}年{month}月",
                    }
                elif time_type == "specific_month_iso":
                    year_month = match.group(1)
                    year, month = (
                        int(year_month.split("-")[0]),
                        int(year_month.split("-")[1]),
                    )
                    month_start = datetime(year, month, 1, tzinfo=CHINA_TIMEZONE)
                    if month == 12:
                        month_end = datetime(
                            year + 1, 1, 1, tzinfo=CHINA_TIMEZONE
                        ) - timedelta(days=1)
                    else:
                        month_end = datetime(
                            year, month + 1, 1, tzinfo=CHINA_TIMEZONE
                        ) - timedelta(days=1)
                    result["time_range"] = {
                        "type": "specific_month",
                        "start": month_start,
                        "end": month_end,
                        "label": f"{year}年{month}月",
                    }
                elif time_type == "last_n_days":
                    days = int(match.group(1))
                    result["time_range"] = {
                        "type": "last_n_days",
                        "start": now - timedelta(days=days),
                        "end": now,
                        "label": f"最近{days}天",
                    }
                break

    # Check if clarification is needed
    # Rule: if domain is hardware and metric is cost, time_range must be specified
    if result["domain"] == "hardware" and result["metric"] == "cost":
        if result["time_range"] is None or result["time_range"]["type"] not in (
            "current_month",
            "last_month",
            "specific_month",
            "last_week",
            "current_week",
        ):
            result["needs_clarification"] = True
            result["clarification_question"] = "你看本月、上月，还是指定月份？"

    # Rule: if domain is None and intent is anomaly, need to clarify domain
    if result["domain"] is None and result["intent"] == "anomaly":
        result["needs_clarification"] = True
        result["clarification_question"] = "你看原辅料/包材，还是五金？"

    # Rule: if domain is warehouse_all and metric is None, default to summary
    if result["domain"] == "warehouse_all" and result["metric"] is None:
        result["metric"] = "inventory"
        result["intent"] = "summary"

    return result


def _q_contains(query: WarehouseChatQuery, keywords: list[str]) -> bool:
    """检查解析后的问题文本中是否包含任一关键词。

    关键词匹配范围包括原始问题中的领域/指标/意图关键词，以及
    需要看问题原文的场景（断料预测、关注总结等无法从结构化字段
    还原的意图），因此基于原始问题全文判断。
    """
    # WarehouseChatQuery 不保留原文；这里通过 filters 的兜底字段回传原文
    raw = str(query.get("filters", {}).get("_raw_question", ""))
    return any(kw in raw for kw in keywords)


def build_query_plan(query: WarehouseChatQuery) -> WarehouseQueryPlan:
    """Build query execution plan from parsed question.

    Args:
        query: Parsed question structure.

    Returns:
        WarehouseQueryPlan with data sources, query type, time window, etc.
    """
    # Initialize result
    plan: WarehouseQueryPlan = {
        "query_type": "",
        "data_sources": [],
        "group_by": None,
        "comparison_mode": None,
        "limit": 10,
        "sort_by": None,
        "time_window": None,
        "needs_clarification": query.get("needs_clarification", False),
        "clarification_question": query.get("clarification_question"),
    }

    # If clarification is needed, return early
    if plan["needs_clarification"]:
        return plan

    domain = query.get("domain")
    metric = query.get("metric")
    dimension = query.get("dimension")
    intent = query.get("intent")
    time_range = query.get("time_range")

    # 断料预测意图优先：基于周用量与可支撑天数（不受 domain 判断顺序影响）
    stockout_keywords = [
        "断料",
        "断货",
        "缺料",
        "一周内",
        "可支撑",
        "耗尽",
        "快用完",
        "能撑",
    ]
    if _q_contains(query, stockout_keywords):
        plan["query_type"] = "stockout_risk"
        plan["data_sources"] = [
            "raw-ledger",
            "packaging-ledger",
            "raw_materials",
            "packaging_materials",
        ]
        plan["group_by"] = "material"
        plan["comparison_mode"] = "cover_days"
        plan["limit"] = 20
        return plan

    # Hardware cost queries
    if domain == "hardware" and metric == "cost":
        plan["query_type"] = "hardware_cost_anomaly"
        plan["data_sources"] = ["hardware-outbound-ledger"]
        plan["group_by"] = "workshop"
        plan["comparison_mode"] = "month_vs_3month_avg"
        plan["sort_by"] = "cost"

        if time_range:
            plan["time_window"] = {
                "start": time_range["start"],
                "end": time_range["end"],
                "type": time_range["type"],
            }

        if intent == "topn":
            plan["query_type"] = "hardware_cost_ranking"
            plan["limit"] = 5
        elif intent == "detail":
            plan["limit"] = 20

    # Raw/Packaging inventory queries
    elif domain in ("raw", "packaging") and metric == "inventory":
        plan["query_type"] = "inventory_shortage"
        plan["data_sources"] = [f"{domain}_materials"]
        plan["group_by"] = "material"
        plan["sort_by"] = "inventory"

        if intent == "anomaly":
            plan["comparison_mode"] = "safety_stock"
        elif intent == "topn":
            plan["query_type"] = "inventory_ranking"
            plan["limit"] = 10

    # Raw/Packaging trend queries
    elif domain in ("raw", "packaging") and metric in ("usage", "trend"):
        plan["query_type"] = "trend_anomaly"
        plan["data_sources"] = [f"{domain}-ledger", f"{domain}_materials"]
        plan["group_by"] = "material"
        plan["comparison_mode"] = "week_vs_4week_avg"
        plan["sort_by"] = "usage"

        if time_range:
            plan["time_window"] = {
                "start": time_range["start"],
                "end": time_range["end"],
                "type": time_range["type"],
            }

        if dimension == "product_line":
            plan["group_by"] = "product_line"
            plan["query_type"] = "product_line_trend"

    # Product overview queries
    elif domain == "product":
        plan["query_type"] = "product_overview"
        plan["data_sources"] = ["products"]
        plan["group_by"] = None
        plan["limit"] = 10

        if intent == "topn":
            plan["query_type"] = "product_ranking"
            plan["sort_by"] = "inventory"

    # 仓储最需关注问题总结：聚合库存异常 + 趋势异常 + 五金费用异常
    elif _q_contains(
        query,
        [
            "总结当前",
            "最需要关注",
            "重点关注",
            "核心问题",
            "当前问题",
            "主要问题",
            "风险点",
            "该关注什么",
            "关注什么",
        ],
    ):
        plan["query_type"] = "warehouse_focus"
        plan["data_sources"] = [
            "raw_materials",
            "packaging_materials",
            "products",
            "hardware-outbound-ledger",
        ]
        plan["limit"] = 20

    # Warehouse-wide summary
    elif domain == "warehouse_all":
        plan["query_type"] = "warehouse_summary"
        plan["data_sources"] = [
            "raw_materials",
            "packaging_materials",
            "products",
            "hardware-outbound-ledger",
        ]
        plan["group_by"] = None
        plan["limit"] = 20

    # Default fallback
    else:
        plan["query_type"] = "warehouse_summary"
        plan["data_sources"] = [
            "raw_materials",
            "packaging_materials",
            "products",
        ]

    return plan


class WarehouseAnomalyItem:
    """Single anomaly detection result."""

    def __init__(
        self,
        anomaly_type: str,
        severity: str,  # "high", "medium", "low"
        material_name: str,
        material_type: str,  # "raw", "packaging", "product"
        details: dict[str, Any],
        suggestion: str,
        detected_at: datetime,
    ) -> None:
        self.anomaly_type = anomaly_type
        self.severity = severity
        self.material_name = material_name
        self.material_type = material_type
        self.details = details
        self.suggestion = suggestion
        self.detected_at = detected_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "material_name": self.material_name,
            "material_type": self.material_type,
            "details": self.details,
            "suggestion": self.suggestion,
            "detected_at": self.detected_at.isoformat(),
        }


class WarehouseTrendAnomalyItem:
    """Single material trend anomaly result."""

    def __init__(
        self,
        *,
        material_name: str,
        material_type: str,
        product_line: str,
        current_week_usage: float,
        history_week_avg_usage: float,
        usage_delta_ratio: float | None,
        current_inventory: float,
        safety_inventory: float,
        estimated_cover_days: float | None,
        risk_level: str,
        reason: str,
        suggestion: str,
    ) -> None:
        self.material_name = material_name
        self.material_type = material_type
        self.product_line = product_line
        self.current_week_usage = current_week_usage
        self.history_week_avg_usage = history_week_avg_usage
        self.usage_delta_ratio = usage_delta_ratio
        self.current_inventory = current_inventory
        self.safety_inventory = safety_inventory
        self.estimated_cover_days = estimated_cover_days
        self.risk_level = risk_level
        self.reason = reason
        self.suggestion = suggestion

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_name": self.material_name,
            "material_type": self.material_type,
            "product_line": self.product_line,
            "current_week_usage": self.current_week_usage,
            "history_week_avg_usage": self.history_week_avg_usage,
            "usage_delta_ratio": self.usage_delta_ratio,
            "current_inventory": self.current_inventory,
            "safety_inventory": self.safety_inventory,
            "estimated_cover_days": self.estimated_cover_days,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "suggestion": self.suggestion,
        }


class WarehouseHardwareCostAnomalyItem:
    """Single hardware cost anomaly result."""

    def __init__(
        self,
        *,
        workshop_name: str,
        current_month_cost: float,
        history_month_avg_cost: float,
        cost_delta_ratio: float | None,
        risk_level: str,
        reason: str,
        suggestion: str,
    ) -> None:
        self.workshop_name = workshop_name
        self.current_month_cost = current_month_cost
        self.history_month_avg_cost = history_month_avg_cost
        self.cost_delta_ratio = cost_delta_ratio
        self.risk_level = risk_level
        self.reason = reason
        self.suggestion = suggestion

    def to_dict(self) -> dict[str, Any]:
        return {
            "workshop_name": self.workshop_name,
            "current_month_cost": self.current_month_cost,
            "history_month_avg_cost": self.history_month_avg_cost,
            "cost_delta_ratio": self.cost_delta_ratio,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "suggestion": self.suggestion,
        }


class WarehouseAIService:
    """AI-powered warehouse analysis service."""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = WarehouseRepository(session)
        self.session = session

    @staticmethod
    def _parse_datetime_value(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value.astimezone(CHINA_TIMEZONE)
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 1e12:
                timestamp /= 1000
            try:
                return datetime.fromtimestamp(timestamp, tz=CHINA_TIMEZONE)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            normalized = normalized.replace("/", "-")
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError:
                try:
                    dt = datetime.strptime(normalized, "%Y-%m-%d")
                except ValueError:
                    return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CHINA_TIMEZONE)
            return dt.astimezone(CHINA_TIMEZONE)
        return None

    @staticmethod
    def _parse_float_value(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.replace(",", "").strip()
            if not normalized:
                return None
            try:
                return float(normalized)
            except ValueError:
                return None
        return None

    @classmethod
    def _normalize_safety_inventory(cls: type[WarehouseAIService], value: Any) -> float:
        parsed = cls._parse_float_value(value)
        if parsed is None or parsed <= 0:
            return 0.0
        return parsed

    @classmethod
    def _has_monitored_safety_inventory(
        cls: type[WarehouseAIService], value: Any
    ) -> bool:
        return cls._normalize_safety_inventory(value) > 0

    @staticmethod
    def _normalize_warning_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _is_shortage_warning(cls: Any, value: Any) -> bool:
        warning = cls._normalize_warning_text(value)
        return any(text in warning for text in SHORTAGE_WARNING_TEXTS)

    @staticmethod
    def _is_test_source(value: Any) -> bool:
        return str(value or "").strip().lower() == "test"

    def _build_inventory_shortage_anomaly(
        self,
        *,
        material: Any,
        material_type: str,
        now: datetime,
    ) -> WarehouseAnomalyItem | None:
        if self._is_test_source(getattr(material, "source", None)):
            return None

        safety_inventory = self._normalize_safety_inventory(
            getattr(material, "safety", 0)
        )
        if safety_inventory <= 0:
            return None

        available_inventory = float(getattr(material, "available", 0) or 0)
        warning_text = self._normalize_warning_text(getattr(material, "warning", None))
        has_low_stock = available_inventory < safety_inventory
        has_shortage_warning = self._is_shortage_warning(warning_text)

        if not has_low_stock and not has_shortage_warning:
            return None

        severity = (
            "high"
            if available_inventory <= 0 or "库存严重不足" in warning_text
            else "medium"
        )
        suggestion = (
            f"{'包材' if material_type == 'packaging' else '物料'} {material.name} "
            f"当前可用 {available_inventory}，安全库存 {safety_inventory}"
        )
        if warning_text:
            suggestion += f"，预警状态：{warning_text}"
        suggestion += "，请结合原辅料/包材总表尽快处理。"

        return WarehouseAnomalyItem(
            anomaly_type="stock_low",
            severity=severity,
            material_name=material.name,
            material_type=material_type,
            details={
                "code": getattr(material, "code", ""),
                "available": available_inventory,
                "safety": safety_inventory,
                "gap": round(max(safety_inventory - available_inventory, 0), 2),
                "warning": warning_text,
                "product_line": getattr(material, "product_line", None),
            },
            suggestion=suggestion,
            detected_at=now,
        )

    async def run_anomaly_detection(self) -> list[WarehouseAnomalyItem]:
        """Run all anomaly detection checks and return results."""
        anomalies: list[WarehouseAnomalyItem] = []
        now = datetime.now(CHINA_TIMEZONE)

        # 1. Check raw materials for stock issues
        raw_anomalies = await self._detect_raw_material_anomalies(now)
        anomalies.extend(raw_anomalies)

        # 2. Check packaging materials for stock issues
        packaging_anomalies = await self._detect_packaging_material_anomalies(now)
        anomalies.extend(packaging_anomalies)

        # Sort by severity (high first)
        severity_order = {"high": 0, "medium": 1, "low": 2}
        anomalies.sort(key=lambda x: severity_order.get(x.severity, 3))

        return anomalies

    async def _detect_raw_material_anomalies(
        self, now: datetime
    ) -> list[WarehouseAnomalyItem]:
        """Detect anomalies in raw material inventory."""
        anomalies: list[WarehouseAnomalyItem] = []

        materials = await self.repo.list_raw_materials()

        for material in materials:
            anomaly = self._build_inventory_shortage_anomaly(
                material=material,
                material_type="raw",
                now=now,
            )
            if anomaly is not None:
                anomalies.append(anomaly)

        return anomalies

    async def _detect_packaging_material_anomalies(
        self, now: datetime
    ) -> list[WarehouseAnomalyItem]:
        """Detect anomalies in packaging material inventory."""
        anomalies: list[WarehouseAnomalyItem] = []

        materials = await self.repo.list_packaging_materials()

        for material in materials:
            anomaly = self._build_inventory_shortage_anomaly(
                material=material,
                material_type="packaging",
                now=now,
            )
            if anomaly is not None:
                anomalies.append(anomaly)

        return anomalies

    async def _detect_product_anomalies(
        self, now: datetime
    ) -> list[WarehouseAnomalyItem]:
        """Detect anomalies in product inventory."""
        anomalies: list[WarehouseAnomalyItem] = []

        products = await self.repo.list_products()

        for product in products:
            # Check for backlog (high remaining quantity)
            if product.remaining_quantity > 0:
                # Check if there's recent shipping activity
                shipping_snapshot = await self.repo.get_material_page_snapshot(
                    "product-shipping"
                )
                if shipping_snapshot:
                    rows, _ = await self.repo.list_material_page_rows(
                        shipping_snapshot.id,
                        keyword=product.name,
                        offset=0,
                        limit=10,
                    )
                    if rows:
                        # Check dates of recent shipments
                        recent_dates = []
                        for row in rows:
                            date_val = row.cells.get("日期")
                            if date_val:
                                if isinstance(date_val, (int, float)):
                                    if date_val > 1e12:
                                        date_val /= 1000
                                    try:
                                        recent_dates.append(
                                            datetime.fromtimestamp(
                                                date_val, tz=CHINA_TIMEZONE
                                            )
                                        )
                                    except (OverflowError, OSError, ValueError):
                                        pass

                        if recent_dates:
                            latest_shipment = max(recent_dates)
                            days_since_shipment = (now - latest_shipment).days

                            if days_since_shipment > STOCK_WARNING_THRESHOLD_DAYS:
                                anomalies.append(
                                    WarehouseAnomalyItem(
                                        anomaly_type="product_backlog",
                                        severity="medium",
                                        material_name=product.name,
                                        material_type="product",
                                        details={
                                            "spec": product.spec,
                                            (
                                                "remaining_quantity"
                                            ): product.remaining_quantity,
                                            (
                                                "days_since_last_shipment"
                                            ): days_since_shipment,
                                            (
                                                "last_shipment_date"
                                            ): latest_shipment.isoformat(),
                                        },
                                        suggestion=(
                                            f"成品 {product.name} 剩余库存 "
                                            f"{product.remaining_quantity}，已 "
                                            f"{days_since_shipment} 天未发货，"
                                            "可能存在积压风险。"
                                        ),
                                        detected_at=now,
                                    )
                                )

        return anomalies

    async def _detect_ledger_anomalies(
        self, now: datetime
    ) -> list[WarehouseAnomalyItem]:
        """Detect anomalies in ledger data (unusual patterns)."""
        anomalies: list[WarehouseAnomalyItem] = []
        raw_materials = {
            item.name: item for item in await self.repo.list_raw_materials()
        }

        # Check raw ledger for unusual outbound quantities
        raw_ledger_snapshot = await self.repo.get_material_page_snapshot("raw-ledger")
        if raw_ledger_snapshot:
            rows, _ = await self.repo.list_material_page_rows(
                raw_ledger_snapshot.id,
                keyword=None,
                offset=0,
                limit=1000,
            )

            # Group by material name and calculate average outbound
            material_outbounds: dict[str, list[float]] = {}
            for row in rows:
                name = row.cells.get("物料名称")
                qty = row.cells.get("领用数量（Kg）") or row.cells.get("出库数量")
                if name and qty:
                    try:
                        qty_val = (
                            float(qty) if isinstance(qty, (int, float, str)) else 0
                        )
                        if qty_val > 0:
                            material_name = str(name)
                            if material_name not in material_outbounds:
                                material_outbounds[material_name] = []
                            material_outbounds[material_name].append(qty_val)
                    except (ValueError, TypeError):
                        pass

            # Check for unusually large outbound
            for material_name, quantities in material_outbounds.items():
                material = raw_materials.get(material_name)
                if material is not None and not self._has_monitored_safety_inventory(
                    material.safety
                ):
                    continue

                if len(quantities) >= 3:
                    avg_qty = sum(quantities) / len(quantities)
                    max_qty = max(quantities)
                    if max_qty > avg_qty * LARGE_CHANGE_THRESHOLD_RATIO:
                        anomalies.append(
                            WarehouseAnomalyItem(
                                anomaly_type="unusual_outbound",
                                severity="low",
                                material_name=material_name,
                                material_type="raw",
                                details={
                                    "average_outbound": round(avg_qty, 2),
                                    "max_outbound": max_qty,
                                    "ratio": round(max_qty / avg_qty, 2),
                                },
                                suggestion=(
                                    f"物料 {material_name} 最近有异常大额出库"
                                    f"（最大 {max_qty}，平均 {round(avg_qty, 2)}），"
                                    "请核实是否正常。"
                                ),
                                detected_at=now,
                            )
                        )

        return anomalies

    async def get_inventory_summary(self) -> dict[str, Any]:
        """Get overall inventory summary statistics."""
        raw_materials = await self.repo.list_raw_materials()
        packaging_materials = await self.repo.list_packaging_materials()
        products = await self.repo.list_products()

        # Calculate statistics
        raw_materials = [
            material
            for material in raw_materials
            if not self._is_test_source(material.source)
        ]
        packaging_materials = [
            material
            for material in packaging_materials
            if not self._is_test_source(material.source)
        ]
        products = [
            product for product in products if not self._is_test_source(product.source)
        ]

        raw_total = len(raw_materials)
        raw_monitored = [
            material
            for material in raw_materials
            if self._has_monitored_safety_inventory(material.safety)
        ]
        raw_low_stock = sum(
            1
            for material in raw_monitored
            if material.available < self._normalize_safety_inventory(material.safety)
        )
        raw_zero_stock = sum(1 for material in raw_monitored if material.available <= 0)
        raw_warning = sum(
            1
            for material in raw_monitored
            if self._is_shortage_warning(material.warning)
        )
        raw_anomaly_count = sum(
            1
            for material in raw_monitored
            if material.available < self._normalize_safety_inventory(material.safety)
            or self._is_shortage_warning(material.warning)
        )

        packaging_total = len(packaging_materials)
        packaging_monitored = [
            material
            for material in packaging_materials
            if self._has_monitored_safety_inventory(material.safety)
        ]
        packaging_low_stock = sum(
            1
            for material in packaging_monitored
            if material.available < self._normalize_safety_inventory(material.safety)
        )
        packaging_zero_stock = sum(
            1 for material in packaging_monitored if material.available <= 0
        )
        packaging_warning = sum(
            1
            for material in packaging_monitored
            if self._is_shortage_warning(material.warning)
        )
        packaging_anomaly_count = sum(
            1
            for material in packaging_monitored
            if material.available < self._normalize_safety_inventory(material.safety)
            or self._is_shortage_warning(material.warning)
        )

        product_total = len(products)
        product_with_stock = sum(1 for p in products if p.remaining_quantity > 0)

        return {
            "raw_materials": {
                "total": raw_total,
                "low_stock": raw_low_stock,
                "zero_stock": raw_zero_stock,
                "warning": raw_warning,
            },
            "packaging_materials": {
                "total": packaging_total,
                "low_stock": packaging_low_stock,
                "zero_stock": packaging_zero_stock,
                "warning": packaging_warning,
            },
            "products": {
                "total": product_total,
                "with_stock": product_with_stock,
            },
            "summary": {
                "total_items": raw_total + packaging_total + product_total,
                "anomaly_count": raw_anomaly_count + packaging_anomaly_count,
            },
        }

    async def _collect_ledger_usage_by_period(
        self,
        page_key: str,
        material_type: str,
        quantity_fields: tuple[str, ...],
    ) -> dict[str, dict[str, Any]]:
        snapshot = await self.repo.get_material_page_snapshot(page_key)
        if not snapshot:
            return {}

        rows, _ = await self.repo.list_material_page_rows(
            snapshot.id,
            offset=0,
            limit=20000,
        )
        now = datetime.now(CHINA_TIMEZONE)
        current_window_start = now - timedelta(days=TREND_LOOKBACK_DAYS)
        history_window_start = current_window_start - timedelta(
            days=TREND_LOOKBACK_DAYS * TREND_BASELINE_WEEKS
        )

        usage_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            material_name = str(row.cells.get("物料名称") or "").strip()
            if not material_name:
                continue

            event_time = self._parse_datetime_value(row.cells.get("出库日期"))
            if event_time is None:
                continue
            if event_time < history_window_start or event_time > now:
                continue

            quantity: float | None = None
            for field in quantity_fields:
                parsed = self._parse_float_value(row.cells.get(field))
                if parsed is not None and parsed > 0:
                    quantity = parsed
                    break
            if quantity is None or quantity <= 0:
                continue

            usage_bucket = usage_map.setdefault(
                material_name,
                {
                    "material_name": material_name,
                    "material_type": material_type,
                    "current_week_usage": 0.0,
                    "history_usage": 0.0,
                },
            )
            if event_time >= current_window_start:
                usage_bucket["current_week_usage"] += quantity
            else:
                usage_bucket["history_usage"] += quantity

        for usage_bucket in usage_map.values():
            usage_bucket["history_week_avg_usage"] = (
                usage_bucket["history_usage"] / TREND_BASELINE_WEEKS
            )

        return usage_map

    def _evaluate_trend_risk(
        self,
        *,
        current_week_usage: float,
        history_week_avg_usage: float,
        current_inventory: float,
        safety_inventory: float,
    ) -> tuple[str | None, float | None, float | None, str, str]:
        safety_inventory = max(safety_inventory, 0.0)
        if safety_inventory <= 0:
            return None, None, None, "", ""

        if current_week_usage <= 0 and history_week_avg_usage <= 0:
            return None, None, None, "", ""

        usage_delta_ratio: float | None = None
        if history_week_avg_usage > 0:
            usage_delta_ratio = current_week_usage / history_week_avg_usage - 1

        estimated_cover_days: float | None = None
        if current_week_usage > 0:
            estimated_cover_days = current_inventory / (
                current_week_usage / TREND_LOOKBACK_DAYS
            )

        is_high_risk = (
            (
                usage_delta_ratio is not None
                and usage_delta_ratio >= TREND_HIGH_RISK_RATIO
                and estimated_cover_days is not None
                and estimated_cover_days <= TREND_HIGH_RISK_COVER_DAYS
            )
            or (
                history_week_avg_usage <= 0
                and current_week_usage > 0
                and current_inventory <= safety_inventory
            )
            or (
                usage_delta_ratio is not None
                and usage_delta_ratio > 0
                and current_inventory < safety_inventory
            )
        )
        if is_high_risk:
            return (
                "high",
                usage_delta_ratio,
                estimated_cover_days,
                "本周用量显著高于历史周均，且库存承压。",
                "建议优先补货，并同步排查排产变动或异常领用。",
            )

        is_medium_risk = (
            (
                usage_delta_ratio is not None
                and usage_delta_ratio >= TREND_MEDIUM_RISK_RATIO
            )
            or (
                estimated_cover_days is not None
                and estimated_cover_days <= TREND_MEDIUM_RISK_COVER_DAYS
            )
            or current_inventory < safety_inventory
        )
        if is_medium_risk:
            return (
                "medium",
                usage_delta_ratio,
                estimated_cover_days,
                "本周用量明显偏高，或库存已接近安全线。",
                "建议本周内完成补货确认，并持续跟踪消耗变化。",
            )

        if history_week_avg_usage <= 0 and current_week_usage > 0:
            return (
                "medium",
                None,
                estimated_cover_days,
                "历史基线不足，但本周已出现真实消耗。",
                "建议人工确认是否形成新的稳定消耗节奏。",
            )

        return (
            "low",
            usage_delta_ratio,
            estimated_cover_days,
            "本周用量有波动，但库存仍能覆盖短期需求。",
            "建议继续观察，不必立即升级处理。",
        )

    async def get_material_trend_anomalies(self) -> list[dict[str, Any]]:
        raw_usage = await self._collect_ledger_usage_by_period(
            "raw-ledger",
            "raw",
            ("领用数量（Kg）", "出库数量"),
        )
        packaging_usage = await self._collect_ledger_usage_by_period(
            "packaging-ledger",
            "packaging",
            ("出库数量",),
        )
        raw_materials = {
            item.name: item for item in await self.repo.list_raw_materials()
        }
        packaging_materials = {
            item.name: item for item in await self.repo.list_packaging_materials()
        }

        trend_items: list[WarehouseTrendAnomalyItem] = []
        for usage_map, inventory_map in (
            (raw_usage, raw_materials),
            (packaging_usage, packaging_materials),
        ):
            for material_name, usage in usage_map.items():
                inventory = inventory_map.get(material_name)
                if inventory is None:
                    continue

                safety_inventory = self._normalize_safety_inventory(inventory.safety)
                if safety_inventory <= 0:
                    continue

                (
                    risk_level,
                    usage_delta_ratio,
                    estimated_cover_days,
                    reason,
                    suggestion,
                ) = self._evaluate_trend_risk(
                    current_week_usage=float(usage["current_week_usage"]),
                    history_week_avg_usage=float(usage["history_week_avg_usage"]),
                    current_inventory=float(inventory.available),
                    safety_inventory=safety_inventory,
                )
                if risk_level is None:
                    continue

                trend_items.append(
                    WarehouseTrendAnomalyItem(
                        material_name=material_name,
                        material_type=str(usage["material_type"]),
                        product_line=str(inventory.product_line or ""),
                        current_week_usage=round(float(usage["current_week_usage"]), 2),
                        history_week_avg_usage=round(
                            float(usage["history_week_avg_usage"]), 2
                        ),
                        usage_delta_ratio=(
                            None
                            if usage_delta_ratio is None
                            else round(usage_delta_ratio, 4)
                        ),
                        current_inventory=round(float(inventory.available), 2),
                        safety_inventory=round(safety_inventory, 2),
                        estimated_cover_days=(
                            None
                            if estimated_cover_days is None
                            else round(estimated_cover_days, 2)
                        ),
                        risk_level=risk_level,
                        reason=reason,
                        suggestion=suggestion,
                    )
                )

        risk_order = {"high": 0, "medium": 1, "low": 2}
        trend_items.sort(
            key=lambda item: (
                risk_order.get(item.risk_level, 3),
                item.estimated_cover_days
                if item.estimated_cover_days is not None
                else float("inf"),
                -item.current_week_usage,
            )
        )
        return [item.to_dict() for item in trend_items]

    async def get_product_line_trend_overview(self) -> list[dict[str, Any]]:
        anomalies = await self.get_material_trend_anomalies()
        grouped: dict[str, dict[str, Any]] = {}
        for item in anomalies:
            product_line = str(item.get("product_line") or "未分类")
            bucket = grouped.setdefault(
                product_line,
                {
                    "product_line": product_line,
                    "current_week_usage": 0.0,
                    "history_week_avg_usage": 0.0,
                    "high_risk_count": 0,
                    "medium_risk_count": 0,
                    "material_count": 0,
                },
            )
            bucket["current_week_usage"] += float(item["current_week_usage"])
            bucket["history_week_avg_usage"] += float(item["history_week_avg_usage"])
            bucket["material_count"] += 1
            if item["risk_level"] == "high":
                bucket["high_risk_count"] += 1
            elif item["risk_level"] == "medium":
                bucket["medium_risk_count"] += 1

        overview: list[dict[str, Any]] = []
        for bucket in grouped.values():
            history_week_avg_usage = float(bucket["history_week_avg_usage"])
            usage_delta_ratio = None
            if history_week_avg_usage > 0:
                usage_delta_ratio = (
                    float(bucket["current_week_usage"]) / history_week_avg_usage - 1
                )
            overview.append(
                {
                    "product_line": bucket["product_line"],
                    "current_week_usage": round(float(bucket["current_week_usage"]), 2),
                    "history_week_avg_usage": round(history_week_avg_usage, 2),
                    "usage_delta_ratio": (
                        None
                        if usage_delta_ratio is None
                        else round(usage_delta_ratio, 4)
                    ),
                    "high_risk_count": bucket["high_risk_count"],
                    "medium_risk_count": bucket["medium_risk_count"],
                    "material_count": bucket["material_count"],
                }
            )

        overview.sort(
            key=lambda item: (
                -item["high_risk_count"],
                -item["medium_risk_count"],
                -(
                    item["usage_delta_ratio"]
                    if item["usage_delta_ratio"] is not None
                    else -1
                ),
            )
        )
        return overview

    async def get_trend_anomaly_summary(self) -> dict[str, Any]:
        anomalies = await self.get_material_trend_anomalies()
        return {
            "total": len(anomalies),
            "high_risk": sum(1 for item in anomalies if item["risk_level"] == "high"),
            "medium_risk": sum(
                1 for item in anomalies if item["risk_level"] == "medium"
            ),
            "raw_count": sum(1 for item in anomalies if item["material_type"] == "raw"),
            "packaging_count": sum(
                1 for item in anomalies if item["material_type"] == "packaging"
            ),
        }

    async def get_hardware_cost_anomalies(self) -> list[dict[str, Any]]:
        """Get hardware cost anomalies by workshop."""
        snapshot = await self.repo.get_material_page_snapshot(
            "hardware-outbound-ledger"
        )
        if not snapshot:
            return []

        rows, _ = await self.repo.list_material_page_rows(
            snapshot.id,
            offset=0,
            limit=20000,
        )

        now = datetime.now(CHINA_TIMEZONE)
        current_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        history_month_start = current_month_start - timedelta(days=90)

        workshop_costs: dict[str, dict[str, Any]] = {}
        for row in rows:
            workshop_name = str(row.cells.get("领用车间") or "").strip()
            if not workshop_name:
                continue

            event_time = self._parse_datetime_value(row.cells.get("日期"))
            if event_time is None:
                continue
            if event_time < history_month_start or event_time > now:
                continue

            cost = self._parse_float_value(row.cells.get("金额"))
            if cost is None or cost <= 0:
                continue

            cost_bucket = workshop_costs.setdefault(
                workshop_name,
                {
                    "workshop_name": workshop_name,
                    "current_month_cost": 0.0,
                    "history_month_cost": 0.0,
                },
            )
            if event_time >= current_month_start:
                cost_bucket["current_month_cost"] += cost
            else:
                cost_bucket["history_month_cost"] += cost

        for cost_bucket in workshop_costs.values():
            cost_bucket["history_month_avg_cost"] = (
                cost_bucket["history_month_cost"] / HARDWARE_COST_LOOKBACK_MONTHS
            )

        anomalies: list[WarehouseHardwareCostAnomalyItem] = []
        for cost_bucket in workshop_costs.values():
            current_cost = cost_bucket["current_month_cost"]
            avg_cost = cost_bucket["history_month_avg_cost"]

            if avg_cost <= 0:
                continue

            cost_delta_ratio: float | None = None
            if avg_cost > 0:
                cost_delta_ratio = current_cost / avg_cost - 1

            is_high_risk = (
                cost_delta_ratio is not None
                and cost_delta_ratio >= HARDWARE_COST_HIGH_RISK_RATIO
            )
            is_medium_risk = (
                cost_delta_ratio is not None
                and cost_delta_ratio >= HARDWARE_COST_MEDIUM_RISK_RATIO
            )

            if not is_high_risk and not is_medium_risk:
                continue

            risk_level = "high" if is_high_risk else "medium"
            reason = (
                f"本月五金领用费用 {current_cost:.2f} 元，"
                f"较近3个月月均 {avg_cost:.2f} 元偏高。"
            )
            suggestion = (
                "建议核查本月该车间五金领用明细，确认是否存在异常集中领用或非"
                "计划性消耗。"
            )

            anomalies.append(
                WarehouseHardwareCostAnomalyItem(
                    workshop_name=cost_bucket["workshop_name"],
                    current_month_cost=current_cost,
                    history_month_avg_cost=avg_cost,
                    cost_delta_ratio=cost_delta_ratio,
                    risk_level=risk_level,
                    reason=reason,
                    suggestion=suggestion,
                )
            )

        anomalies.sort(key=lambda x: x.current_month_cost, reverse=True)
        return [anomaly.to_dict() for anomaly in anomalies]

    async def get_hardware_cost_summary(self) -> dict[str, Any]:
        """Get hardware cost summary."""
        anomalies = await self.get_hardware_cost_anomalies()
        high_risk_count = sum(1 for a in anomalies if a["risk_level"] == "high")
        medium_risk_count = sum(1 for a in anomalies if a["risk_level"] == "medium")

        snapshot = await self.repo.get_material_page_snapshot(
            "hardware-outbound-ledger"
        )
        total_workshops = 0
        if snapshot:
            rows, _ = await self.repo.list_material_page_rows(
                snapshot.id,
                offset=0,
                limit=20000,
            )
            workshop_set = set()
            for row in rows:
                workshop_name = str(row.cells.get("领用车间") or "").strip()
                if workshop_name:
                    workshop_set.add(workshop_name)
            total_workshops = len(workshop_set)

        return {
            "total_workshops": total_workshops,
            "anomaly_workshops": len(anomalies),
            "high_risk_count": high_risk_count,
            "medium_risk_count": medium_risk_count,
            "current_month_total_cost": sum(a["current_month_cost"] for a in anomalies),
            "history_month_avg_total_cost": sum(
                a["history_month_avg_cost"] for a in anomalies
            ),
        }

    async def query_hardware_cost_by_time_range(
        self,
        time_window: dict[str, Any] | None,
        group_by: str = "workshop",
        limit: int = 10,
        sort_by: str = "cost",
    ) -> list[dict[str, Any]]:
        """Query hardware cost by dynamic time range.

        Args:
            time_window: Time range dict with start, end, type.
            group_by: Group by dimension (workshop, material, day).
            limit: Max number of results.
            sort_by: Sort field (cost, count).

        Returns:
            List of hardware cost items grouped by specified dimension.
        """
        snapshot = await self.repo.get_material_page_snapshot(
            "hardware-outbound-ledger"
        )
        if not snapshot:
            return []

        rows, _ = await self.repo.list_material_page_rows(
            snapshot.id,
            offset=0,
            limit=20000,
        )

        # Determine time range
        now = datetime.now(CHINA_TIMEZONE)
        start_time: datetime | None = None
        end_time: datetime | None = None
        if time_window:
            start_value = time_window.get("start")
            end_value = time_window.get("end")
            start_time = self._parse_datetime_value(start_value)
            end_time = self._parse_datetime_value(end_value)
        else:
            # Default to current month
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        if start_time is None:
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if end_time is None:
            end_time = now

        # Aggregate costs
        cost_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            # Get group key based on group_by dimension
            if group_by == "workshop":
                group_key = str(row.cells.get("领用车间") or "").strip()
            elif group_by == "material":
                group_key = str(row.cells.get("物料名称") or "").strip()
            elif group_by == "day":
                event_date = self._parse_datetime_value(row.cells.get("日期"))
                if event_date:
                    group_key = event_date.strftime("%Y-%m-%d")
                else:
                    continue
            else:
                group_key = str(row.cells.get("领用车间") or "").strip()

            if not group_key:
                continue

            event_time = self._parse_datetime_value(row.cells.get("日期"))
            if event_time is None:
                continue
            if event_time < start_time or event_time > end_time:
                continue

            cost = self._parse_float_value(row.cells.get("金额"))
            if cost is None or cost <= 0:
                continue

            cost_bucket = cost_map.setdefault(
                group_key,
                {
                    "key": group_key,
                    "total_cost": 0.0,
                    "count": 0,
                },
            )
            cost_bucket["total_cost"] += cost
            cost_bucket["count"] += 1

        # Sort results
        if sort_by == "cost":
            sorted_items = sorted(
                cost_map.values(), key=lambda x: x["total_cost"], reverse=True
            )
        elif sort_by == "count":
            sorted_items = sorted(
                cost_map.values(), key=lambda x: x["count"], reverse=True
            )
        else:
            sorted_items = sorted(
                cost_map.values(), key=lambda x: x["total_cost"], reverse=True
            )

        # Limit results
        return sorted_items[:limit]

    async def query_inventory_shortage_data(
        self,
        domain: str = "raw",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query inventory shortage data for raw or packaging materials.

        Args:
            domain: "raw" or "packaging".
            limit: Max number of results.

        Returns:
            List of materials with inventory shortage.
        """
        if domain == "raw":
            raw_stmt = (
                select(RawMaterialInventory)
                .where(
                    RawMaterialInventory.source != "test",
                )
                .order_by(RawMaterialInventory.available.asc())
            )
            result = await self.session.execute(raw_stmt)
            materials = result.scalars().all()
        elif domain == "packaging":
            packaging_stmt = (
                select(PackagingMaterialInventory)
                .where(
                    PackagingMaterialInventory.source != "test",
                )
                .order_by(PackagingMaterialInventory.available.asc())
            )
            result = await self.session.execute(packaging_stmt)
            materials = result.scalars().all()
        else:
            return []

        shortage_items: list[dict[str, Any]] = []
        for material in materials:
            safety = self._normalize_safety_inventory(material.safety)
            if safety <= 0:
                continue

            available = float(material.available or 0)
            warning = self._normalize_warning_text(material.warning)

            has_low_stock = available < safety
            has_shortage_warning = self._is_shortage_warning(warning)

            if not has_low_stock and not has_shortage_warning:
                continue

            shortage_items.append(
                {
                    "material_name": material.name,
                    "material_type": domain,
                    "code": material.code,
                    "available": available,
                    "safety": safety,
                    "gap": round(max(safety - available, 0), 2),
                    "warning": warning,
                    "product_line": material.product_line,
                    "severity": "high"
                    if available <= 0 or "库存严重不足" in warning
                    else "medium",
                }
            )

        return shortage_items[:limit]

    async def query_product_inventory_overview(
        self,
        limit: int = 10,
        sort_by: str = "inventory",
    ) -> list[dict[str, Any]]:
        """Query product inventory overview.

        Args:
            limit: Max number of results.
            sort_by: Sort field (inventory, name).

        Returns:
            List of products with inventory info.
        """
        stmt = select(ProductInventory).where(
            ProductInventory.source != "test",
        )
        result = await self.session.execute(stmt)
        products = result.scalars().all()

        product_items: list[dict[str, Any]] = []
        for product in products:
            remaining = float(product.remaining_quantity or 0)
            product_items.append(
                {
                    "product_name": product.name,
                    "code": product.spec or "",
                    "inventory": remaining,
                    "unit": product.unit or "",
                    "location": product.spec or "",
                    "qualified": float(product.qualified_quantity or 0),
                    "pending": float(product.pending_quantity or 0),
                    "subtotal": float(product.subtotal_quantity or 0),
                }
            )

        if sort_by == "inventory":
            product_items.sort(key=lambda x: x["inventory"], reverse=True)
        else:
            product_items.sort(key=lambda x: x["product_name"])

        return product_items[:limit]

    def format_chat_answer(
        self,
        *,
        query_type: str,
        details: list[dict[str, Any]] | None,
        time_window: dict[str, Any] | None,
        needs_clarification: bool = False,
        clarification_question: str | None = None,
    ) -> WarehouseChatAnswer:
        """Format structured answer for warehouse AI chat.

        Args:
            query_type: Type of query executed.
            details: Detail data items from query execution.
            time_window: Time range used for the query.
            needs_clarification: Whether clarification is needed.
            clarification_question: Question to ask user.

        Returns:
            WarehouseChatAnswer with structured response.
        """
        if needs_clarification:
            return {
                "status": "need_clarification",
                "summary": None,
                "details": None,
                "basis": None,
                "suggestions": None,
                "clarification_question": clarification_question,
                "answer_text": clarification_question,
            }

        if not details:
            return {
                "status": "no_data",
                "summary": "暂无相关数据。",
                "details": None,
                "basis": None,
                "suggestions": None,
                "clarification_question": None,
                "answer_text": "暂无相关数据。",
            }

        # Build summary based on query type
        summary_parts: list[str] = []
        detail_parts: list[str] = []
        basis_parts: list[str] = []
        suggestions: list[str] = []

        if (
            query_type == "hardware_cost_anomaly"
            or query_type == "hardware_cost_ranking"
        ):
            # Hardware cost query
            anomaly_count = len(details)
            if anomaly_count > 0:
                summary_parts.append(f"共发现 {anomaly_count} 个车间五金费用异常偏高。")

                for item in details[:5]:
                    key = item.get("key", "")
                    total_cost = item.get("total_cost", 0)
                    count = item.get("count", 0)
                    detail_parts.append(
                        f"- {key}：费用 {total_cost:.2f} 元，领用 {count} 次"
                    )

                if time_window:
                    time_type = time_window.get("type", "")
                    if time_type == "last_month":
                        basis_parts.append("本次按上月五金出库记录统计。")
                    elif time_type == "current_month":
                        basis_parts.append("本次按本月五金出库记录统计。")
                    elif time_type == "specific_month":
                        label = time_window.get("label", "")
                        basis_parts.append(f"本次按 {label} 五金出库记录统计。")
                    else:
                        basis_parts.append("本次按指定时间范围的五金出库记录统计。")

                suggestions.append(
                    "建议核查异常车间的五金领用明细，确认是否存在异常集中领用或非计划性消耗。"
                )
            else:
                summary_parts.append("未发现五金费用异常车间。")

        elif query_type == "inventory_shortage":
            # Inventory shortage query
            shortage_count = len(details)
            if shortage_count > 0:
                summary_parts.append(f"共发现 {shortage_count} 个物料库存不足。")

                for item in details[:5]:
                    material_name = item.get("material_name", "")
                    available = item.get("available", 0)
                    safety = item.get("safety", 0)
                    gap = item.get("gap", 0)
                    severity = item.get("severity", "medium")
                    detail_parts.append(
                        f"- {material_name}：可用 {available}，安全库存 {safety}，"
                        f"缺口 {gap}（{severity}风险）"
                    )

                basis_parts.append(
                    "本次按原辅料/包材库存总表统计，安全库存 > 0 且可用库存"
                    "低于安全库存或预警状"
                    "态为库存不足。"
                )
                suggestions.append("建议优先补货缺口较大的物料，并核查预警状态。")
            else:
                summary_parts.append("未发现库存不足物料。")

        elif query_type == "trend_anomaly":
            # Trend anomaly query
            trend_count = len(details)
            if trend_count > 0:
                summary_parts.append(f"共发现 {trend_count} 个物料趋势异常。")

                for item in details[:5]:
                    material_name = item.get("material_name", "")
                    current_usage = item.get("current_week_usage", 0)
                    history_avg = item.get("history_week_avg_usage", 0)
                    ratio = item.get("usage_delta_ratio")
                    ratio_text = "新增消耗" if ratio is None else f"{ratio * 100:.1f}%"
                    detail_parts.append(
                        f"- {material_name}：本周 {current_usage}，"
                        f"历史周均 {history_avg}，偏差 {ratio_text}"
                    )

                basis_parts.append(
                    "本次按最近7天 vs 过去4周周均对比，偏差 >= 30% 判定为异常。"
                )
                suggestions.append(
                    "建议核查异常物料的消耗原因，确认是否存在排产变动或异常领用。"
                )
            else:
                summary_parts.append("未发现趋势异常物料。")

        elif query_type == "stockout_risk":
            # 高消耗物料断料预测
            count = len(details)
            if count > 0:
                summary_parts.append(
                    f"共 {count} 个物料存在一周内断料风险（可支撑天数 ≤ 7 天）。"
                )
                for item in details[:10]:
                    material_name = item.get("material_name", "")
                    cover_days = item.get("estimated_cover_days")
                    current_usage = item.get("current_week_usage", 0)
                    current_inventory = item.get("current_inventory", 0)
                    cover_text = (
                        f"约 {cover_days:.1f} 天" if cover_days is not None else "未知"
                    )
                    detail_parts.append(
                        f"- {material_name}：库存 {current_inventory}，"
                        f"本周用量 {current_usage}，"
                        f"预计可支撑 {cover_text}"
                    )
                basis_parts.append(
                    "本次按最近7天周用量与当前库存计算可支撑天数，"
                    "可支撑天数 ≤ 7 天判定为断料风险。"
                )
                suggestions.append("建议优先补货上述高消耗物料，并同步核查排产计划。")
            else:
                summary_parts.append("当前无一周内断料风险的高消耗物料。")

        elif query_type == "warehouse_focus":
            # 汇总当前最需关注的问题
            count = len(details)
            summary_parts.append(f"当前仓储共识别 {count} 项需关注的问题：")
            for item in details[:10]:
                category = item.get("category", "")
                name = item.get("name", "")
                metric = item.get("metric", "")
                risk = item.get("risk", "")
                detail_parts.append(f"- [{category}] {name}：{metric}（{risk}风险）")
            basis_parts.append("本次综合库存不足、断料风险与五金费用异常三方面汇总。")
            suggestions.append("建议按风险等级优先处理高风险项，并持续跟踪库存消耗。")

        elif query_type == "product_overview" or query_type == "product_ranking":
            # Product overview query
            product_count = len(details)
            if product_count > 0:
                summary_parts.append(f"共 {product_count} 个成品有库存记录。")

                for item in details[:5]:
                    product_name = item.get("product_name", "")
                    inventory = item.get("inventory", 0)
                    unit = item.get("unit", "")
                    detail_parts.append(f"- {product_name}：库存 {inventory} {unit}")

                basis_parts.append("本次按成品库存总表统计。")
            else:
                summary_parts.append("暂无成品库存数据。")

        elif query_type == "warehouse_summary":
            # Warehouse-wide summary
            summary_parts.append("仓储整体数据概览如下：")

            for item in details[:10]:
                key = item.get("key", "")
                total_cost = item.get("total_cost", 0)
                detail_parts.append(f"- {key}：{total_cost:.2f}")

            basis_parts.append("本次按仓储全模块数据汇总。")

        else:
            # Default fallback
            summary_parts.append(f"查询结果共 {len(details)} 条。")
            for item in details[:5]:
                detail_parts.append(f"- {json.dumps(item, ensure_ascii=False)}")

        # Build full answer text
        answer_parts: list[str] = []
        answer_parts.append("## 结论")
        answer_parts.extend(summary_parts)

        if detail_parts:
            answer_parts.append("\n## 明细数据")
            answer_parts.extend(detail_parts)

        if basis_parts:
            answer_parts.append("\n## 计算依据")
            answer_parts.extend(basis_parts)

        if suggestions:
            answer_parts.append("\n## 建议")
            answer_parts.extend(suggestions)

        return {
            "status": "answered",
            "summary": "\n".join(summary_parts),
            "details": details,
            "basis": "\n".join(basis_parts),
            "suggestions": suggestions,
            "clarification_question": None,
            "answer_text": "\n".join(answer_parts),
        }

    async def chat_with_ai(self, question: str) -> str:
        """Answer user question about warehouse using LLM."""
        # Step 1: Parse question
        query = parse_chat_question(question)

        # Step 2: Check if clarification is needed
        if query.get("needs_clarification"):
            clarification = query.get("clarification_question", "请补充更多信息。")
            return str(clarification or "请补充更多信息。")

        # Step 3: Build query plan
        plan = build_query_plan(query)

        # Step 4: Check if clarification is needed in plan
        if plan.get("needs_clarification"):
            clarification = plan.get("clarification_question", "请补充更多信息。")
            return str(clarification or "请补充更多信息。")

        # Step 5: Execute query based on plan
        query_type = plan.get("query_type", "")
        time_window = plan.get("time_window")
        limit = plan.get("limit", 10)
        group_by = plan.get("group_by")
        domain = query.get("domain")

        details: list[dict[str, Any]] | None = None

        if (
            query_type == "hardware_cost_anomaly"
            or query_type == "hardware_cost_ranking"
        ):
            # Hardware cost query with dynamic time range
            details = await self.query_hardware_cost_by_time_range(
                time_window=time_window,
                group_by=group_by or "workshop",
                limit=limit,
                sort_by="cost",
            )

        elif query_type == "inventory_shortage":
            # Inventory shortage query
            details = await self.query_inventory_shortage_data(
                domain=domain or "raw",
                limit=limit,
            )

        elif query_type == "trend_anomaly":
            # Trend anomaly query
            trend_anomalies = await self.get_material_trend_anomalies()
            details = trend_anomalies[:limit]

        elif query_type == "stockout_risk":
            # 高消耗物料断料预测：可支撑天数低 → 高风险
            trend_anomalies = await self.get_material_trend_anomalies()
            risky = [
                item
                for item in trend_anomalies
                if item.get("estimated_cover_days") is not None
                and item.get("estimated_cover_days", 0) <= 7
                and item.get("current_week_usage", 0) > 0
            ]
            risky.sort(key=lambda item: item.get("estimated_cover_days") or 999)
            details = risky[:limit]

        elif query_type == "warehouse_focus":
            # 汇总当前最需关注的问题：库存异常 + 断料风险 + 五金费用异常
            focus_items: list[dict[str, Any]] = []
            shortage = await self.query_inventory_shortage_data(domain="raw", limit=20)
            pkg_shortage = await self.query_inventory_shortage_data(
                domain="packaging", limit=20
            )
            trend_anomalies = await self.get_material_trend_anomalies()
            stockout = [
                item
                for item in trend_anomalies
                if item.get("estimated_cover_days") is not None
                and item.get("estimated_cover_days", 0) <= 7
            ]
            try:
                hw_anomalies = await self.get_hardware_cost_anomalies()
            except Exception:
                hw_anomalies = []

            for item in shortage:
                focus_items.append(
                    {
                        "category": "库存不足",
                        "name": item.get("material_name", ""),
                        "metric": (
                            f"可用 {item.get('available')} / 安全 {item.get('safety')}"
                        ),
                        "risk": item.get("severity", "medium"),
                    }
                )
            for item in pkg_shortage:
                focus_items.append(
                    {
                        "category": "包材库存不足",
                        "name": item.get("material_name", ""),
                        "metric": (
                            f"可用 {item.get('available')} / 安全 {item.get('safety')}"
                        ),
                        "risk": item.get("severity", "medium"),
                    }
                )
            for item in stockout:
                focus_items.append(
                    {
                        "category": "断料风险",
                        "name": item.get("material_name", ""),
                        "metric": f"约 {item.get('estimated_cover_days')} 天耗尽",
                        "risk": item.get("risk_level", "medium"),
                    }
                )
            for item in hw_anomalies:
                focus_items.append(
                    {
                        "category": "五金费用异常",
                        "name": item.get("workshop_name", ""),
                        "metric": f"本月 {item.get('current_month_cost')} 元",
                        "risk": item.get("risk_level", "medium"),
                    }
                )

            risk_order = {"high": 0, "medium": 1, "low": 2}
            focus_items.sort(key=lambda x: risk_order.get(str(x.get("risk") or ""), 3))
            details = focus_items[:limit]

        elif query_type == "product_line_trend":
            # Product line trend query
            product_line_overview = await self.get_product_line_trend_overview()
            details = product_line_overview[:limit]

        elif query_type == "product_overview" or query_type == "product_ranking":
            # Product overview query
            details = await self.query_product_inventory_overview(
                limit=limit,
                sort_by="inventory",
            )

        elif query_type == "warehouse_summary":
            # Warehouse-wide summary - use existing summary functions
            summary = await self.get_inventory_summary()
            anomalies = await self.run_anomaly_detection()
            trend_summary = await self.get_trend_anomaly_summary()
            hardware_cost_summary = await self.get_hardware_cost_summary()

            # Build comprehensive summary
            details = [
                {
                    "key": "原辅料总数",
                    "total_cost": summary["raw_materials"]["total"],
                },
                {
                    "key": "原辅料低库存",
                    "total_cost": summary["raw_materials"]["low_stock"],
                },
                {
                    "key": "包材总数",
                    "total_cost": summary["packaging_materials"]["total"],
                },
                {
                    "key": "包材低库存",
                    "total_cost": summary["packaging_materials"]["low_stock"],
                },
                {
                    "key": "成品总数",
                    "total_cost": summary["products"]["total"],
                },
                {
                    "key": "异常物料数",
                    "total_cost": len(anomalies),
                },
                {
                    "key": "趋势异常数",
                    "total_cost": trend_summary["total"],
                },
                {
                    "key": "五金车间总数",
                    "total_cost": hardware_cost_summary["total_workshops"],
                },
                {
                    "key": "五金费用异常车间",
                    "total_cost": hardware_cost_summary["anomaly_workshops"],
                },
            ]

        else:
            # Default fallback - use existing summary
            summary = await self.get_inventory_summary()
            details = [
                {
                    "key": "原辅料总数",
                    "total_cost": summary["raw_materials"]["total"],
                },
                {
                    "key": "包材总数",
                    "total_cost": summary["packaging_materials"]["total"],
                },
                {
                    "key": "成品总数",
                    "total_cost": summary["products"]["total"],
                },
            ]

        # Step 6: Format answer
        answer = self.format_chat_answer(
            query_type=query_type,
            details=details,
            time_window=time_window,
            needs_clarification=False,
            clarification_question=None,
        )

        # Step 7: Optionally use LLM to polish the answer
        # For now, we return the structured answer directly
        # This can be enhanced later to use LLM for natural language polishing

        return str(answer.get("answer_text") or "暂无相关数据。")

    async def generate_analysis_report(self) -> dict[str, Any]:
        """Generate comprehensive analysis report using LLM."""
        summary = await self.get_inventory_summary()
        anomalies = await self.run_anomaly_detection()
        trend_summary = await self.get_trend_anomaly_summary()
        trend_anomalies = await self.get_material_trend_anomalies()
        product_line_overview = await self.get_product_line_trend_overview()
        hardware_cost_summary = await self.get_hardware_cost_summary()
        hardware_cost_anomalies = await self.get_hardware_cost_anomalies()

        anomaly_data = [a.to_dict() for a in anomalies]

        messages = [
            {
                "role": "system",
                "content": """你是一个仓储管理分析专家，负责生成专业的仓储分析报告。
报告应包含：
1. 总体库存状况评估
2. 异常问题分析
3. 风险等级判断
4. 改进建议

请以JSON格式返回报告，包含以下字段：
- overall_status: 总体状况（正常/需关注/需紧急处理）
- risk_level: 风险等级（低/中/高）
- key_issues: 关键问题列表
- recommendations: 改进建议列表
- summary_text: 简要总结文字""",
            },
            {
                "role": "user",
                "content": f"""请根据以下数据生成仓储分析报告：

库存概览：
{json.dumps(summary, ensure_ascii=False, indent=2)}

检测到的异常：
{json.dumps(anomaly_data[:20], ensure_ascii=False, indent=2)}

周趋势异常概览：
{json.dumps(trend_summary, ensure_ascii=False, indent=2)}

趋势异常明细（前10条）：
{json.dumps(trend_anomalies[:10], ensure_ascii=False, indent=2)}

产品线趋势概览（前5条）：
{json.dumps(product_line_overview[:5], ensure_ascii=False, indent=2)}

五金费用异常概览：
{json.dumps(hardware_cost_summary, ensure_ascii=False, indent=2)}

五金费用异常明细（前10条）：
{json.dumps(hardware_cost_anomalies[:10], ensure_ascii=False, indent=2)}

请生成分析报告。""",
            },
        ]

        try:
            response = await llm_client.chat_json(
                messages,
                expected_keys=[
                    "overall_status",
                    "risk_level",
                    "key_issues",
                    "recommendations",
                    "summary_text",
                ],
                temperature=0.5,
            )
            return response
        except LLMConfigError:
            return {
                "overall_status": "分析失败",
                "risk_level": "未知",
                "key_issues": [],
                "recommendations": [],
                "summary_text": "AI 服务尚未配置，请改用人工分析。",
            }
        except LLMRateLimitError:
            return {
                "overall_status": "分析失败",
                "risk_level": "未知",
                "key_issues": [],
                "recommendations": [],
                "summary_text": "AI 服务繁忙，请稍后重试。",
            }
        except (LLMOutputError, LLMProviderError, TimeoutError):
            return {
                "overall_status": "分析失败",
                "risk_level": "未知",
                "key_issues": [],
                "recommendations": [],
                "summary_text": "AI 报告生成失败，请稍后重试或改用人工分析。",
            }
