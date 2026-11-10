"""System formulas use business dates; reference values never replace results."""

from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import openpyxl
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.exceptions import AppException
from app.main import app_exception_handler
from app.modules.energy import ledger_api, ledger_notifications
from app.modules.energy.ledger_calculations import Calculation, calculate_rule
from app.modules.energy.ledger_imports import inspect_xlsx
from app.modules.energy.ledger_models import (
    EnergyImportBatch,
    EnergyReading,
    EnergyUsageFact,
)
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    MeterWrite,
    RuleDefinition,
    RuleTerm,
    RuleWrite,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.platform.identity.models import User
from tests.modules.energy.workbook_fixtures import seed_meter, seed_rule


@pytest.mark.parametrize(
    "numerator, denominator, expected",
    [
        (
            Calculation(Decimal(0), "complete", {}),
            Calculation(Decimal(0), "complete", {}),
            "not_applicable",
        ),
        (
            Calculation(None, "missing_reading", {}),
            Calculation(Decimal(0), "complete", {}),
            "missing_dependency",
        ),
        (
            Calculation(Decimal(0), "complete", {}),
            Calculation(None, "missing_reading", {}),
            "missing_dependency",
        ),
        (
            Calculation(Decimal(0), "abnormal_usage", {}),
            Calculation(Decimal(0), "complete", {}),
            "abnormal_dependency",
        ),
        (
            Calculation(None, "reading_rollback", {}),
            Calculation(Decimal(0), "complete", {}),
            "abnormal_dependency",
        ),
    ],
)
def test_ratio_checks_input_completeness_before_zero(numerator, denominator, expected):
    rule = RuleDefinition(
        code="ratio",
        name="占比",
        category="electricity",
        unit="比例",
        active_from=date(2028, 2, 1),
        operation="ratio",
        quantity_kind="ratio",
        terms=[RuleTerm(metric_key="point:n"), RuleTerm(metric_key="point:d")],
    )
    result = calculate_rule(rule, {"point:n": numerator, "point:d": denominator})
    assert result.value is None
    assert result.status == expected


@pytest.mark.asyncio
async def test_http_date_alignment_formula_only_history_and_stale_facts(
    db_session, monkeypatch
):
    actor = User(
        id=uuid4(),
        username="dated-" + uuid4().hex,
        name="日期回归",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(actor)
    await db_session.flush()
    service = EnergyLedgerService(db_session, actor)
    monkeypatch.setattr(
        ledger_notifications, "enqueue_reading_notification", AsyncMock()
    )
    meter = await seed_meter(
        service,
        MeterWrite(
            definition=MeterDefinition(
                code="dated_" + uuid4().hex,
                name="设备",
                category="electricity",
                unit="kWh",
                area="测试",
                reading_type="direct",
                quantity_kind="electricity",
                source_sheet="电量",
                source_column=2,
                active_from=date(2028, 1, 1),
                enabled=True,
            )
        ),
    )
    rule = await seed_rule(
        service,
        RuleWrite(
            definition=RuleDefinition(
                code="dated_rule_" + uuid4().hex,
                name="101车间·电",
                category="electricity",
                unit="kWh",
                quantity_kind="electricity",
                source_sheet="101车间",
                source_column=3,
                workshop="101车间",
                active_from=date(2028, 1, 1),
                enabled=True,
                terms=[RuleTerm(metric_key="point:" + meter.definition.code)],
            )
        ),
    )
    book = openpyxl.Workbook()
    raw = book.active
    raw.title = "电量"
    raw.append(["日期", "设备"])
    raw.append([date(2028, 2, 28), 10])
    raw.append([date(2028, 2, 29), 20])
    raw.append([date(2028, 3, 1), 30])
    derived = book.create_sheet("101车间")
    derived.append(["日期", None, "电"])
    derived.append([date(2028, 2, 28), None, "=电量!B3"])
    derived.append([date(2028, 2, 29), None, 999])
    derived.append([date(2028, 3, 1), None, 0])
    output = BytesIO()
    book.save(output)
    source_bytes = output.getvalue()
    batch = EnergyImportBatch(
        id=uuid4(),
        content_hash=uuid4().hex * 2,
        status="imported",
        payload=inspect_xlsx(source_bytes, 2028),
    )
    source_snapshot = deepcopy(batch.payload)
    db_session.add(batch)
    for day, value in [
        (date(2028, 2, 28), 10),
        (date(2028, 2, 29), 20),
        (date(2028, 3, 1), 30),
    ]:
        db_session.add(
            EnergyReading(
                id=uuid4(),
                point_id=meter.id,
                task_id=uuid4(),
                reading_date=day,
                value=Decimal(value),
                version=1,
                source="import",
                submitted_at=datetime.now(UTC),
            )
        )
    stale = EnergyUsageFact(
        id=uuid4(),
        metric_key="rule:" + rule.definition.code,
        usage_date=date(2028, 2, 28),
        definition=rule.definition.model_dump(mode="json"),
        calculated_value=Decimal(999),
        effective_value=Decimal(999),
        status="complete",
        provenance={
            "source_sheet": "101车间",
            "source_cell": "C2",
            "formula": "=电量!B3",
        },
    )
    db_session.add(stale)
    await db_session.flush()
    api = FastAPI()
    api.include_router(ledger_api.router)
    api.add_exception_handler(AppException, app_exception_handler)
    api.dependency_overrides[ledger_api.ledger_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.get(
            "/reporting/workbook",
            params={"year": 2028, "month": 2, "dataset": "101车间"},
        )
        assert response.status_code == 200, response.text
        cells = [row["cells"]["3"] for row in response.json()["data"]["rows"]]
        assert cells[27]["value"] == "10.00000000"
        assert cells[28]["value"] is None
        assert cells[28]["calculated_value"] == "20.00000000"
        assert cells[28]["status"] == "pending_review"
        comparison = cells[28]["provenance"]["source_comparison"]
        assert Decimal(comparison["reported_value"]) == 999
        assert Decimal(comparison["difference"]) == 979
        assert cells[28]["provenance"]["reference"]["reported_value"] == "999"
        trace = await client.get(f"/reporting/trace/{stale.id}")
        assert trace.status_code == 200
        assert Decimal(trace.json()["data"]["effective_value"]) == 10
        retired_key = "rule:retired_" + uuid4().hex
        db_session.add(
            EnergyUsageFact(
                id=uuid4(),
                metric_key=retired_key,
                usage_date=date(2028, 2, 29),
                definition=rule.definition.model_dump(mode="json"),
                calculated_value=Decimal(999),
                effective_value=Decimal(999),
                status="complete",
                provenance={"source_cell": "C3"},
            )
        )
        await db_session.flush()
        response = await client.get(
            "/reporting",
            params={
                "start_date": "2028-02-29",
                "end_date": "2028-02-29",
                "metric_key": retired_key,
            },
        )
        assert response.status_code == 200
        retired = response.json()["data"]["rows"][0]
        assert (
            retired["effective_value"] is None and retired["status"] == "unconfigured"
        )
        response = await client.put(
            "/input-readings",
            json={
                "dataset": "电量",
                "reading_date": "2028-02-29",
                "values": [{"point_id": str(meter.id), "value": "25", "version": 1}],
                "reason": "核实电表更正",
            },
        )
        assert response.status_code == 200, response.text
        response = await client.get(
            "/reporting/workbook",
            params={"year": 2028, "month": 2, "dataset": "101车间"},
        )
        updated = response.json()["data"]["rows"][28]["cells"]["3"]
        assert updated["value"] is None
        assert Decimal(updated["calculated_value"]) == 25
        assert updated["status"] == "pending_review"
        assert Decimal(updated["provenance"]["source_comparison"]["difference"]) == 974
        reading = await db_session.scalar(
            select(EnergyReading).where(
                EnergyReading.point_id == meter.id,
                EnergyReading.reading_date == date(2028, 2, 29),
            )
        )
        response = await client.get(f"/ledger-history/reading/{reading.id}")
        assert response.status_code == 200
        revision = response.json()["data"][0]
        assert Decimal(revision["payload"]["before"]) == 20
        assert Decimal(revision["payload"]["value"]) == 25
        assert revision["reason"] == "核实电表更正"
        assert revision["created_by"] == str(actor.id)
    assert batch.payload["sheets"][1]["source_grid"][2][2] == 999
    assert batch.payload == source_snapshot


@pytest.mark.asyncio
async def test_http_ratio_missing_zero_and_period_totals_are_distinct(db_session):
    service = EnergyLedgerService(db_session)
    meters = []
    for column, label in [(2, "分子"), (3, "分母")]:
        meters.append(
            await seed_meter(
                service,
                MeterWrite(
                    definition=MeterDefinition(
                        code="ratio_input_" + uuid4().hex,
                        name=label,
                        category="electricity",
                        area="测试",
                        unit="kWh",
                        reading_type="direct",
                        quantity_kind="electricity",
                        source_sheet="电量",
                        source_column=column,
                        active_from=date(2028, 1, 1),
                        enabled=True,
                    )
                ),
            )
        )
    rule = await seed_rule(
        service,
        RuleWrite(
            definition=RuleDefinition(
                code="ratio_result_" + uuid4().hex,
                name="日总量·占比",
                category="electricity",
                unit="比例",
                source_sheet="日总量",
                source_column=5,
                operation="ratio",
                quantity_kind="ratio",
                active_from=date(2028, 1, 1),
                enabled=True,
                terms=[
                    RuleTerm(metric_key="point:" + meter.definition.code)
                    for meter in meters
                ],
            )
        ),
    )
    for number, values in [
        (1, [0, None]),
        (2, [0, 10]),
        (3, [10, 20]),
        (4, [0, 0]),
        (5, [0, 0]),
    ]:
        for meter, value in zip(meters, values, strict=True):
            if value is not None:
                db_session.add(
                    EnergyReading(
                        point_id=meter.id,
                        task_id=uuid4(),
                        reading_date=date(2028, 1, number),
                        value=Decimal(value),
                        version=1,
                    )
                )
    await db_session.flush()
    api = FastAPI()
    api.include_router(ledger_api.router)
    api.dependency_overrides[ledger_api.ledger_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.get(
            "/reporting/workbook",
            params={"year": 2028, "month": 1, "dataset": "日总量"},
        )
        assert response.status_code == 200, response.text
        cells = [row["cells"]["5"] for row in response.json()["data"]["rows"]]
        assert [cell["status"] for cell in cells[:5]] == [
            "missing_dependency",
            "complete",
            "complete",
            "not_applicable",
            "not_applicable",
        ]
        assert cells[0]["value"] is None
        assert Decimal(cells[1]["value"]) == 0
        assert Decimal(cells[2]["value"]) == Decimal(".5")
        for start, end, status, value in [
            (2, 4, "complete", Decimal(1) / 3),
            (4, 5, "not_applicable", None),
            (1, 2, "missing_dependency", None),
        ]:
            response = await client.get(
                "/reporting",
                params={
                    "start_date": f"2028-01-{start:02}",
                    "end_date": f"2028-01-{end:02}",
                    "metric_key": "rule:" + rule.definition.code,
                },
            )
            assert response.status_code == 200, response.text
            report = response.json()["data"]
            metric = report["period_metrics"][0]
            assert metric["status"] == status
            if value is None:
                assert metric["value"] is None
            else:
                assert abs(Decimal(metric["value"]) - value) < Decimal("1e-8")
            if status == "not_applicable":
                assert report["status"] == "complete"
                assert not report["quality_counts"]
        exported = await client.get(
            "/reporting/workbook/export",
            params={"year": 2028, "month": 1, "dataset": "日总量"},
        )
        assert exported.status_code == 200
        sheet = openpyxl.load_workbook(BytesIO(exported.content), data_only=True).active
        assert sheet["C2"].value == "待补数"
        assert sheet["B3"].value == 0
        assert sheet["C5"].value == "不适用"
