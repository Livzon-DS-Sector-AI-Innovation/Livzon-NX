from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.modules.procurement.analytics_service import (
    AnalyticsAggregateInput,
    AnalyticsFilterInput,
    AnalyticsMetricInput,
    AnalyticsOrderInput,
    aggregate_analytics,
)
from app.platform.identity.data_scope import (
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,key,scope,expected",
    [
        (None, None, None, 403),
        ("user", None, None, 403),
        ("user", "purchasing:order", {"scope_type": "all"}, 403),
        ("user", "purchasing:supplier", {"scope_type": "departments"}, 403),
        ("user", "purchasing:supplier", {"scope_type": "all"}, 200),
        ("admin", None, None, 200),
    ],
)
async def test_supplier_aggregation_requires_trusted_supported_scope(
    role, key, scope, expected
):
    actor = (
        SimpleNamespace(role=role, is_deleted=False, status="active") if role else None
    )
    tokens = (
        current_page_actor.set(actor),
        current_page_key.set(key),
        current_page_data_scope.set(scope),
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [SimpleNamespace(_mapping={"count": 2})]
            )
        )
    )
    try:
        if expected == 403:
            with pytest.raises(HTTPException) as error:
                await aggregate_analytics(
                    db, AnalyticsAggregateInput(dataset="procurement.suppliers")
                )
            assert error.value.status_code == 403
            db.execute.assert_not_awaited()
        else:
            result = await aggregate_analytics(
                db, AnalyticsAggregateInput(dataset="procurement.suppliers")
            )
            assert result["rows"] == [{"count": 2}]
            query = str(db.execute.await_args.args[0])
            assert "is_deleted IS false" in query
            assert "LIMIT" in query
    finally:
        current_page_actor.reset(tokens[0])
        current_page_key.reset(tokens[1])
        current_page_data_scope.reset(tokens[2])


@pytest.mark.asyncio
async def test_supplier_aggregation_keeps_filters_grouping_order_and_limit():
    from sqlalchemy.dialects import postgresql

    token = current_page_actor.set(
        SimpleNamespace(role="admin", is_deleted=False, status="active")
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    )
    try:
        result = await aggregate_analytics(
            db,
            AnalyticsAggregateInput(
                dataset="procurement.suppliers",
                metrics=[
                    AnalyticsMetricInput(
                        type="count_distinct",
                        field="supplier_code",
                        alias="supplier_count",
                    )
                ],
                group_by=["manufacturer_name"],
                filters=[
                    AnalyticsFilterInput(
                        field="purchase_category", op="eq", value="原料"
                    )
                ],
                order_by=[
                    AnalyticsOrderInput(metric="supplier_count", direction="desc")
                ],
                limit=7,
            ),
        )
        query = db.execute.await_args.args[0].compile(dialect=postgresql.dialect())
        sql = str(query)
        assert "count(distinct(procurement.suppliers.supplier_code))" in sql
        assert "GROUP BY procurement.suppliers.manufacturer_name" in sql
        assert "ORDER BY supplier_count DESC" in sql
        assert "is_deleted IS false" in sql
        assert "原料" in query.params.values()
        assert 7 in query.params.values()
        assert result["rows"] == []
        assert result["meta"]["metrics"] == ["supplier_count"]
    finally:
        current_page_actor.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,detail",
    [
        ({"dataset": "hr.employees"}, "Unsupported analytics dataset"),
        (
            {"dataset": "procurement.suppliers", "metrics": [{"field": "password"}]},
            "Unsupported field",
        ),
    ],
)
async def test_supplier_aggregation_rejects_unknown_dataset_or_field(payload, detail):
    token = current_page_actor.set(
        SimpleNamespace(role="admin", is_deleted=False, status="active")
    )
    db = SimpleNamespace(execute=AsyncMock())
    try:
        with pytest.raises(HTTPException) as error:
            await aggregate_analytics(
                db, AnalyticsAggregateInput.model_validate(payload)
            )
        assert error.value.status_code == 400
        assert detail in error.value.detail
        db.execute.assert_not_awaited()
    finally:
        current_page_actor.reset(token)
