import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.analytics import (
    AnalyticsAggregateInput,
    AnalyticsFilterInput,
    AnalyticsMetricInput,
    AnalyticsOrderInput,
    aggregate_analytics,
)
from app.modules.agent.schemas import AgentToolExecuteRequest
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import ToolContext, tool_registry
from app.modules.procurement.models import Supplier


def _context(db: AsyncSession) -> ToolContext:
    return ToolContext(
        db=db,
        session_id=None,
        user_id=None,
        user=None,
        reason=None,
        raw_request=AgentToolExecuteRequest(operation="analytics.aggregate"),
        agent_service=None,
    )


def test_analytics_tool_is_registered() -> None:
    ensure_agent_tools_registered()
    spec = tool_registry.get("analytics.aggregate")

    assert spec is not None
    assert spec.write is False
    assert spec.workflow_allowed is True


@pytest.mark.anyio
async def test_aggregate_suppliers_groups_by_manufacturer(
    db_session: AsyncSession,
) -> None:
    category = f"analytics-test-{uuid.uuid4()}"
    db_session.add_all(
        [
            Supplier(
                supplier_code="S001",
                supplier_name="供应商A",
                material_code="M001",
                material_name="物料A",
                manufacturer_code="F001",
                manufacturer_name="厂家一",
                purchase_category=category,
                import_row_number=1,
            ),
            Supplier(
                supplier_code="S002",
                supplier_name="供应商B",
                material_code="M002",
                material_name="物料B",
                manufacturer_code="F001",
                manufacturer_name="厂家一",
                purchase_category=category,
                import_row_number=2,
            ),
            Supplier(
                supplier_code="S003",
                supplier_name="供应商C",
                material_code="M003",
                material_name="物料C",
                manufacturer_code="F002",
                manufacturer_name="厂家二",
                purchase_category=category,
                import_row_number=3,
            ),
            Supplier(
                supplier_code="S004",
                supplier_name="供应商D",
                material_code="M004",
                material_name="物料D",
                manufacturer_code="F003",
                manufacturer_name="",
                purchase_category=category,
                import_row_number=4,
            ),
            Supplier(
                supplier_code="S005",
                supplier_name="供应商E",
                material_code="M005",
                material_name="物料E",
                manufacturer_code="F001",
                manufacturer_name="厂家一",
                purchase_category=category,
                import_row_number=5,
                is_deleted=True,
            ),
        ]
    )
    await db_session.flush()

    result = await aggregate_analytics(
        _context(db_session),
        AnalyticsAggregateInput(
            dataset="procurement.suppliers",
            metrics=[
                AnalyticsMetricInput(
                    type="count",
                    field="manufacturer_name",
                    alias="record_count",
                )
            ],
            group_by=["manufacturer_name"],
            filters=[
                AnalyticsFilterInput(
                    field="purchase_category", op="eq", value=category
                ),
                AnalyticsFilterInput(field="manufacturer_name", op="not_empty"),
            ],
            order_by=[AnalyticsOrderInput(metric="record_count", direction="desc")],
            limit=10,
        ),
    )

    assert result["dataset"]["name"] == "procurement.suppliers"
    assert result["rows"] == [
        {"manufacturer_name": "厂家一", "record_count": 2},
        {"manufacturer_name": "厂家二", "record_count": 1},
    ]
    assert result["meta"]["row_count"] == 2


@pytest.mark.anyio
async def test_aggregate_rejects_unregistered_field(db_session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await aggregate_analytics(
            _context(db_session),
            AnalyticsAggregateInput(
                dataset="procurement.suppliers",
                metrics=[AnalyticsMetricInput(type="count", field="password")],
            ),
        )

    assert exc_info.value.status_code == 400
    assert "Unsupported field" in str(exc_info.value.detail)
