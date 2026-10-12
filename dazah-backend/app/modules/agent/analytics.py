"""Supplier analytics adapter; authorization uses the procurement page contract."""

from typing import Any

from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.procurement.public_api import (
    AnalyticsAggregateInput as AnalyticsAggregateInput,
)
from app.modules.procurement.public_api import (
    AnalyticsFilterInput as AnalyticsFilterInput,
)
from app.modules.procurement.public_api import (
    AnalyticsMetricInput as AnalyticsMetricInput,
)
from app.modules.procurement.public_api import (
    AnalyticsOrderInput as AnalyticsOrderInput,
)
from app.modules.procurement.public_api import (
    aggregate_supplier_analytics,
)


async def aggregate_analytics(
    context: ToolContext, data: AnalyticsAggregateInput
) -> dict[str, Any]:
    return await aggregate_supplier_analytics(context.db, data)


@agent_tool(
    name="analytics.aggregate",
    result_kind="statistics",
    module="procurement",
    page_keys=("purchasing:supplier",),
    data_scope_type="all",
    summary="通用业务数据聚合统计",
    input_model=AnalyticsAggregateInput,
    method="TOOL",
    path="/agent/analytics/aggregate",
    input_schema={
        **AnalyticsAggregateInput.model_json_schema(),
        "body": {
            "dataset": "数据集名称；当前支持 procurement.suppliers",
            "metrics": "聚合指标列表，支持 count/count_distinct/sum/avg/min/max",
            "group_by": "分组字段列表，最多 3 个；例如 manufacturer_name",
            "filters": "过滤条件列表，支持 eq/ne/contains/not_empty/is_empty/gte/lte",
            "order_by": "按 metric 或 group_by 字段排序",
            "limit": "返回分组数量，默认 20，最大 200",
        },
        "examples": [
            {
                "dataset": "procurement.suppliers",
                "metrics": [
                    {
                        "type": "count",
                        "field": "manufacturer_name",
                        "alias": "record_count",
                    }
                ],
                "group_by": ["manufacturer_name"],
                "filters": [{"field": "manufacturer_name", "op": "not_empty"}],
                "order_by": [{"metric": "record_count", "direction": "desc"}],
                "limit": 10,
            }
        ],
    },
    output_hint=(
        "用于全量计数、去重计数、TopN、分布统计等场景；返回数据库聚合后的 rows，"
        "避免逐页读取全量明细。"
    ),
)
async def aggregate_analytics_tool(
    context: ToolContext, data: AnalyticsAggregateInput
) -> dict[str, Any]:
    return await aggregate_analytics(context, data)
