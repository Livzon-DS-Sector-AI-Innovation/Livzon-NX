"""Source results stay visible as evidence when native recalculation disagrees."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import openpyxl
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.energy import ledger_api
from app.modules.energy.ledger_calculations import Calculation
from app.modules.energy.ledger_models import EnergyCalculationRule, EnergyMeterPoint
from app.modules.energy.ledger_schemas import MeterDefinition, RuleDefinition
from app.modules.energy.ledger_service import EnergyLedgerService
from app.modules.energy.ledger_source_workbook import SourceWorkbook
from app.modules.energy.ledger_sources import MonthlySource


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "native,status,reported,expected",
    [
        (None, "reading_rollback", 53592, "pending_review"),
        (None, "reading_rollback", 0, "pending_review"),
        (Decimal(50000), "complete", 53592, "pending_review"),
        (Decimal(53592), "complete", 53592, "complete"),
        (None, "missing_reading", 53592, "missing_dependency"),
        (None, "reading_rollback", None, "abnormal_dependency"),
        (None, "reading_rollback", -1, "abnormal_dependency"),
    ],
)
async def test_http_preserves_source_result_without_accepting_it_as_usage(
    monkeypatch, native, status, reported, expected
):
    from datetime import UTC, datetime

    from app.modules.energy.ledger_calculations import Observation
    from app.modules.energy.ledger_service import _EvaluationInputs

    day = date(2026, 10, 1)
    point = MeterDefinition(
        code="counter",
        name="103-1车间",
        source_sheet="循环水码",
        source_column=2,
        category="circulating_water",
        unit="m³",
        area="动力",
        active_from=day,
        enabled=True,
    )
    usage = RuleDefinition(
        code="usage",
        name="103-1车间",
        source_sheet="循环水量",
        source_column=2,
        category="circulating_water",
        unit="m³",
        active_from=day,
        enabled=True,
        terms=[{"metric_key": "point:counter"}],
    )
    total = usage.model_copy(
        update={
            "code": "total",
            "name": "循环水日总量",
            "source_sheet": "日总量",
            "source_column": 10,
            "report_scope": "plant",
            "terms": [usage.terms[0].model_copy(update={"metric_key": "rule:usage"})],
        }
    )
    point_id = uuid4()
    meters = [
        EnergyMeterPoint(
            id=point_id,
            code=point.code,
            version=1,
            definition=point.model_dump(mode="json"),
        )
    ]
    rules = [
        EnergyCalculationRule(
            id=uuid4(),
            code=item.code,
            version=1,
            definition=item.model_dump(mode="json"),
        )
        for item in (usage, total)
    ]
    db = AsyncMock(spec=AsyncSession)

    async def scalars(statement):
        model = statement.column_descriptions[0]["entity"]
        return Mock(
            all=Mock(
                return_value={
                    EnergyMeterPoint: meters,
                    EnergyCalculationRule: rules,
                }.get(model, [])
            )
        )

    db.scalars.side_effect = scalars
    service = EnergyLedgerService(db)
    monkeypatch.setattr(service, "usage_reviews", AsyncMock(return_value=[]))
    source = SourceWorkbook.from_payload(
        {
            "report_period": "2026-10",
            "sheets": [
                {
                    "name": "循环水量",
                    "headers": ["日期", "103-1车间"],
                    "source_grid": [["日期", "103-1车间"], ["10/1", reported]],
                    "row_dates": [{"row": 2, "date": day.isoformat()}],
                },
                {
                    "name": "日总量",
                    "headers": ["日期"] + [""] * 8 + ["循环水日总量"],
                    "source_grid": [
                        ["日期"] + [""] * 8 + ["循环水日总量"],
                        ["10/1"] + [None] * 8
                        + ["=循环水量!B2" if reported is not None else None],
                    ],
                    "row_dates": [{"row": 2, "date": day.isoformat()}],
                },
            ],
        }
    )
    monkeypatch.setattr(
        service,
        "monthly_source",
        AsyncMock(
            return_value=MonthlySource(
                source,
                uuid4(),
                datetime.now(UTC),
            )
        ),
    )
    inputs = _EvaluationInputs(
        points={"point:counter": (point_id, 1, point)},
        rules={"rule:usage": (1, usage), "rule:total": (1, total)},
        observations={point_id: {day: Observation(Decimal(9996405), 1)}},
        order=["rule:usage", "rule:total"],
        labels={"point:counter": point.name},
    )
    monkeypatch.setattr(service, "_evaluation_inputs", AsyncMock(return_value=inputs))
    monkeypatch.setattr(
        "app.modules.energy.ledger_service.calculate_point",
        lambda *args: Calculation(
            native, status, {"reading_values": ["9996405", "49997"]}
        ),
    )
    api = FastAPI()
    api.include_router(ledger_api.router)
    api.dependency_overrides[ledger_api.ledger_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.get(
            "/reporting/workbook",
            params={
                "year": 2026,
                "month": 10,
                "dataset": "日总量",
            },
        )
        assert response.status_code == 200, response.text
        cell = response.json()["data"]["rows"][0]["cells"]["10"]
        assert cell["status"] == expected
        if expected == "pending_review":
            comparison = cell["provenance"]["source_comparison"]
            assert Decimal(comparison["reported_value"]) == reported
            if native is None:
                assert comparison["difference"] is None
            else:
                assert Decimal(comparison["difference"]) == Decimal(reported) - native
            assert cell["value"] is None
            if native is None:
                assert cell["calculated_value"] is None
            else:
                assert Decimal(cell["calculated_value"]) == native
            report = await service.report(day, day, metric_key="rule:total")
            assert report.totals[0].available_count == 0
            assert report.totals[0].value is None
            exported = await client.get(
                "/reporting/workbook/export",
                params={"year": 2026, "month": 10, "dataset": "日总量"},
            )
            assert exported.status_code == 200
            book = openpyxl.load_workbook(BytesIO(exported.content), data_only=True)
            assert book.active["B2"].value == reported
            assert "待核对" in book.active["C2"].value
            assert "差异（原表－系统）" in book.active["C2"].value
            assert book.active["C2"].alignment.wrap_text is True
        else:
            assert "source_comparison" not in cell["provenance"]
    assert source.sheets["循环水量"].grid[1][1] == reported
    db.add.assert_not_called()
