"""Monthly dashboard loading must not repeat metadata queries for every day."""

from collections import Counter
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.main import app_exception_handler
from app.modules.energy import ledger_api
from app.modules.energy.ledger_models import (
    EnergyCalculationRule,
    EnergyMeterPoint,
    EnergyReading,
    EnergyUsageFact,
)
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    RuleDefinition,
    RuleTerm,
    WorkbookReport,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.modules.energy.ledger_template import stable_code
from app.modules.energy.ledger_workbook import EnergyWorkbookService


@pytest.fixture
def report_source():
    electric = MeterDefinition(
        code="electric",
        name="设备电量",
        category="electricity",
        area="动力",
        unit="kWh",
        quantity_kind="electricity",
        reading_type="direct",
        source_sheet="电量",
        source_column=2,
        active_from=date(2026, 1, 1),
    )
    water = MeterDefinition(
        code="water",
        name="水表",
        category="drinking_water",
        area="动力",
        unit="m³",
        source_sheet="饮用水码",
        source_column=2,
        active_from=date(2026, 1, 1),
    )
    meters = [
        EnergyMeterPoint(
            id=uuid4(),
            version=1,
            code=definition.code,
            definition=definition.model_dump(mode="json"),
        )
        for definition in (electric, water)
    ]
    rules = [
        EnergyCalculationRule(
            id=uuid4(),
            version=1,
            code=definition.code,
            definition=definition.model_dump(mode="json"),
        )
        for definition in (
            RuleDefinition(
                code="electric_total",
                name="电日用量",
                category="electricity",
                unit="kWh",
                quantity_kind="electricity",
                report_scope="plant",
                source_sheet="日总量",
                source_column=6,
                terms=[RuleTerm(metric_key="point:electric")],
                active_from=date(2026, 1, 1),
            ),
            RuleDefinition(
                code="water_total",
                name="饮用水量",
                category="drinking_water",
                unit="m³",
                report_scope="plant",
                source_sheet="日总量",
                source_column=7,
                terms=[RuleTerm(metric_key="point:water")],
                active_from=date(2026, 1, 1),
            ),
        )
    ]
    readings = [
        EnergyReading(
            id=uuid4(),
            point_id=meters[index].id,
            task_id=uuid4(),
            reading_date=day,
            value=Decimal(value),
            version=1,
            exception={},
            source="platform",
        )
        for index, day, value in (
            (0, date(2026, 10, 1), "7"),
            (0, date(2026, 10, 31), "0"),
            (1, date(2026, 10, 31), "100"),
            (1, date(2026, 11, 1), "130"),
            (1, date(2026, 11, 2), "170"),
        )
    ]
    counts = Counter()
    windows = []

    async def scalars(statement):
        model = statement.column_descriptions[0]["entity"]
        counts[model.__name__] += 1
        records = {EnergyMeterPoint: meters, EnergyCalculationRule: rules}.get(
            model, []
        )
        if model is EnergyReading:
            params = statement.compile().params
            start, end = params["reading_date_1"], params["reading_date_2"]
            windows.append((start, end))
            records = [row for row in readings if start <= row.reading_date <= end]
        return Mock(all=Mock(return_value=records))

    db = AsyncMock(spec=AsyncSession)
    db.scalars.side_effect = scalars
    service = EnergyLedgerService(db)
    api = FastAPI()
    api.include_router(ledger_api.router, prefix="/api/v1/energy")
    api.add_exception_handler(AppException, app_exception_handler)
    api.dependency_overrides[ledger_api.ledger_service] = lambda: service
    return api, service, counts, windows, readings, rules


@pytest.mark.asyncio
async def test_dashboard_month_batches_inputs_and_refreshes_live_values(report_source):
    api, service, counts, _, readings, rules = report_source
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/energy/reporting/workbook",
            params={"year": 2026, "month": 10, "dataset": "日总量"},
        )
        assert response.status_code == 200
        report = WorkbookReport.model_validate(response.json()["data"])
        assert len(report.rows) == 31
        assert report.rows[0].cells["6"].value == 7
        assert report.rows[30].cells["6"].value == 0
        assert report.rows[1].cells["6"].status == "missing_dependency"
        assert report.rows[30].cells["7"].value == 30
        # A monthly request has a bounded number of reads, independent of days.
        assert counts["EnergyMeterPoint"] <= 8
        assert counts["EnergyCalculationRule"] <= 3
        assert counts["EnergyReading"] <= 5
        fact_queries = [
            call.args[0].compile().params
            for call in service.db.scalars.call_args_list
            if call.args[0].column_descriptions[0]["entity"] is EnergyUsageFact
        ]
        assert len(fact_queries) == 1
        assert any(
            isinstance(value, list)
            and set(value) == {"rule:electric_total", "rule:water_total"}
            for value in fact_queries[0].values()
        )

        readings[3].value = Decimal(160)
        rules[1].definition = {
            **rules[1].definition,
            "terms": [{"metric_key": "point:water", "coefficient": "2"}],
        }
        refreshed = await client.get(
            "/api/v1/energy/reporting/workbook",
            params={"year": 2026, "month": 10, "dataset": "日总量"},
        )
        assert refreshed.status_code == 200
        updated = WorkbookReport.model_validate(refreshed.json()["data"])
        assert updated.rows[30].cells["7"].value == 120


@pytest.mark.asyncio
async def test_report_batches_cross_month_counter_context(report_source):
    _, service, counts, windows, _, _ = report_source
    report = await service.report(
        date(2026, 10, 31), date(2026, 11, 1), metric_key="rule:water_total"
    )
    assert {row.usage_date: row.effective_value for row in report.rows} == {
        date(2026, 10, 31): Decimal(30),
        date(2026, 11, 1): Decimal(40),
    }
    assert counts["EnergyCalculationRule"] == 1
    assert (date(2026, 10, 1), date(2026, 12, 1)) in windows


@pytest.mark.asyncio
async def test_dashboard_invalid_graph_stays_a_business_conflict(report_source):
    api, _, _, _, _, rules = report_source
    original = rules[0].definition
    rules[0].definition = {
        **original,
        "terms": [{"metric_key": "rule:electric_total"}],
    }
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/energy/reporting/workbook",
            params={"year": 2026, "month": 10, "dataset": "日总量"},
        )
        assert response.status_code == 409
        assert "历史计算配置无效" in response.json()["message"]
        rules[0].definition = original
        retried = await client.get(
            "/api/v1/energy/reporting/workbook",
            params={"year": 2026, "month": 10, "dataset": "日总量"},
        )
        assert retried.status_code == 200
        assert Decimal(retried.json()["data"]["rows"][0]["cells"]["6"]["value"]) == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_only", [False, True])
async def test_explicit_mapping_precedes_legacy_suffix_without_false_conflicts(
    report_source, legacy_only
):
    _, service, _, _, _, _ = report_source
    workbook = EnergyWorkbookService(service)
    workbook.loaded = (2026, 10)
    definition = RuleDefinition(
        code=stable_code("日总量", 6),
        name="日总量·电日用量",
        category="electricity",
        unit="kWh",
        quantity_kind="electricity",
        active_from=date(2026, 1, 1),
        enabled=True,
        source_sheet="日总量",
        source_column=6,
        terms=[RuleTerm(metric_key="point:electric")],
    )
    legacy = definition.model_copy(
        update={
            "code": "verify_" + definition.code,
            "source_sheet": "",
            "source_column": None,
            "name": "开发验证·日总量·电日用量",
        }
    )
    if not legacy_only:
        workbook.definitions["rule:" + definition.code] = definition
    workbook.definitions["rule:" + legacy.code] = legacy
    for item, value in [(definition, "7"), (legacy, "999")]:
        workbook.facts["rule:" + item.code, date(2026, 10, 1)] = (
            await service.calculated_rows(date(2026, 10, 1))
        )["rule:electric_total"].model_copy(update={"effective_value": Decimal(value)})
    report = await workbook.report(2026, 10, "日总量")
    assert report.rows[0].cells["6"].status == "complete"
    assert report.rows[0].cells["6"].value == (999 if legacy_only else 7)


@pytest.mark.asyncio
async def test_raw_workbook_does_not_query_usage_facts_and_export_loads_new_sheets(
    report_source,
):
    _, service, counts, _, _, _ = report_source
    workbook = EnergyWorkbookService(service)
    raw = await workbook.report(2026, 10, "电量")
    assert raw.rows[0].cells["2"].value == 7
    assert counts["EnergyUsageFact"] == 0
    overview = await workbook.report(2026, 10, "日总量")
    assert overview.rows[30].cells["7"].value == 30
    assert counts["EnergyUsageFact"] == 1
