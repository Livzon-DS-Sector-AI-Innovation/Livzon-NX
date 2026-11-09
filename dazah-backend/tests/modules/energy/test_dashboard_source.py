"""Reference structure and live-input calculation regressions (no sample hash lock)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import openpyxl
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import AppException
from app.main import app_exception_handler
from app.modules.energy import ledger_api, ledger_notifications
from app.modules.energy.ledger_entry import source_fields
from app.modules.energy.ledger_imports import inspect_xlsx
from app.modules.energy.ledger_models import EnergyImportBatch
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    MeterWrite,
    RuleDefinition,
    RuleTerm,
    RuleWrite,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.modules.energy.ledger_source_policy import SOURCE_CATEGORIES
from app.modules.energy.ledger_source_workbook import SourceWorkbook
from app.platform.identity.models import User
from tests.modules.energy.workbook_fixtures import seed_meter, seed_rule


def source_book(electricity=False):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "电量" if electricity else "饮用水码"
    if electricity:
        sheet.append(["日期", "总计", "西动力总", "东动力总"])
        sheet.append([date(2028, 2, 27), "=SUM(C2:D2)", 1, 2])
        sheet.append([date(2028, 2, 28), "=SUM(C3:D3)", None, None])
    else:
        sheet.append(["日期", "主表"])
        sheet.append([date(2028, 2, 27), 90])
        sheet.append([date(2028, 2, 28), 100])
        usage = book.create_sheet("饮用水量")
        usage.append(["日期", "用量"])
        usage.append([date(2028, 2, 27), "=饮用水码!B3-饮用水码!B2"])
        usage.append([date(2028, 2, 28), "=饮用水码!B4-饮用水码!B3"])
    daily = book.create_sheet("日用量")
    daily.append(["日期", "合计"])
    daily.append(
        [date(2028, 2, 27), "=SUM(电量!C2:D2)" if electricity else "=饮用水量!B2"]
    )
    output = BytesIO()
    book.save(output)
    return SourceWorkbook.from_payload(inspect_xlsx(output.getvalue(), 2028))


def test_next_day_input_drives_usage_and_keeps_missing_distinct_from_zero():
    book = source_book()
    book.require_inputs({("饮用水码", 2)})
    assert book.cell_on("饮用水量", 2, date(2028, 2, 28)).status == "missing_reading"
    book.set_reading("饮用水码", 2, date(2028, 2, 29), Decimal(130), version=1)
    assert book.cell_on("饮用水量", 2, date(2028, 2, 28)).value == 30
    book.set_reading("饮用水码", 2, date(2028, 2, 29), Decimal(140), version=2)
    assert book.cell_on("饮用水量", 2, date(2028, 2, 28)).value == 40
    assert book.cell_on("饮用水码", 2, date(2028, 2, 29)).provenance["version"] == 2


def test_required_non_numeric_input_cannot_be_ignored_by_sum():
    book = source_book(True)
    book.sheets["电量"].grid[2].extend(["待核对", 5])
    book.require_inputs({("电量", 3), ("电量", 4)})
    assert book.cell_on("电量", 2, date(2028, 2, 28)).status == "pending_review"


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=电量!C2:C3", 8),
        ("=@电量!C2:C3", 8),
        ("=电量!B2:D2", 3),
        ("=电量!C2:C2", 1),
        ("=SUM(电量!C2:C3)", 9),
        ("=电量!C4:C5", None),
        ("=电量!C2:D3", None),
    ],
)
def test_scalar_ranges_keep_excel_implicit_intersection(formula, expected):
    book = source_book(True)
    book.sheets["电量"].grid[2] = [None, formula, 8, 5]
    result = book.result("电量", "B3")
    assert result.value == expected
    assert result.status == (
        "complete" if expected is not None else "source_formula_error"
    )


def test_electricity_formula_is_read_only_and_new_day_copies_formula_not_values():
    book = source_book(True)
    book.require_inputs({("电量", 3), ("电量", 4)})
    assert book.cell_on("日总量", 2, date(2028, 2, 27)).value == 3
    assert book.cell_on("电量", 2, date(2028, 2, 28)).status == "missing_reading"
    book.set_reading("电量", 3, date(2028, 2, 29), Decimal(0), version=1)
    assert book.cell_on("电量", 2, date(2028, 2, 29)).status == "missing_reading"
    book.set_reading("电量", 4, date(2028, 2, 29), Decimal(5), version=1)
    assert book.cell_on("电量", 2, date(2028, 2, 29)).value == 5
    assert (
        book.cell_on("电量", 2, date(2028, 2, 29)).provenance["formula"]
        == "=SUM(C4:D4)"
    )
    with pytest.raises(ValueError, match="公式列"):
        book.set_reading("电量", 2, date(2028, 2, 29), Decimal(99), version=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("with_snapshot", [False, True])
async def test_six_input_tables_and_live_updates_drive_derived_tables(
    db_session, monkeypatch, with_snapshot
):
    actor = User(
        id=uuid4(),
        username="schema-" + uuid4().hex,
        name="字段回归",
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
    meters = {}
    for sheet, category in SOURCE_CATEGORIES.items():
        definition = MeterDefinition(
            code="field_" + uuid4().hex,
            name="原始字段",
            category=category,
            unit="测试单位",
            area="测试",
            source_sheet=sheet,
            source_column=2,
            reading_type="direct" if sheet == "电量" else "counter",
            active_from=date(2028, 1, 1),
            enabled=True,
        )
        meters[sheet] = await seed_meter(service, MeterWrite(definition=definition))
        assert [item.id for item in await source_fields(service, sheet)] == [
            meters[sheet].id
        ]
    computed = await seed_meter(
        service,
        MeterWrite.model_construct(
            definition=meters["电量"].definition.model_copy(
                update={
                    "code": "computed_" + uuid4().hex,
                    "name": "总计",
                    "source_column": 3,
                }
            )
        ),
    )
    assert computed.id not in [item.id for item in await source_fields(service, "电量")]
    usage = await seed_rule(
        service,
        RuleWrite(
            definition=RuleDefinition(
                code="usage_" + uuid4().hex,
                name="饮用水量·用量",
                category="drinking_water",
                unit="测试单位",
                department="测试",
                active_from=date(2028, 1, 1),
                enabled=True,
                source_sheet="饮用水量",
                source_column=2,
                terms=[
                    RuleTerm(metric_key="point:" + meters["饮用水码"].definition.code)
                ],
            )
        ),
    )
    await seed_rule(
        service,
        RuleWrite(
            definition=RuleDefinition(
                code="daily_" + uuid4().hex,
                name="日总量·饮用水日总量",
                category="drinking_water",
                unit="测试单位",
                department="测试",
                active_from=date(2028, 1, 1),
                enabled=True,
                source_sheet="日总量",
                source_column=7,
                terms=[RuleTerm(metric_key="rule:" + usage.definition.code)],
            )
        ),
    )
    if with_snapshot:
        template = openpyxl.Workbook()
        raw = template.active
        raw.title = "饮用水码"
        raw.append(["日期", "原始字段"])
        raw.append([date(2028, 2, 27), 90])
        raw.append([date(2028, 2, 28), 100])
        derived = template.create_sheet("饮用水量")
        derived.append(["日期", "用量"])
        derived.append([date(2028, 2, 27), "=饮用水码!B3-饮用水码!B2"])
        derived.append([date(2028, 2, 28), None])
        daily = template.create_sheet("日用量")
        daily.append(["日期", None, None, None, None, None, "饮用水日总量"])
        daily.append([date(2028, 2, 27)])
        daily.append([date(2028, 2, 28)])
        data = BytesIO()
        template.save(data)
        db_session.add(
            EnergyImportBatch(
                id=uuid4(),
                content_hash=uuid4().hex * 2,
                status="imported",
                payload=inspect_xlsx(data.getvalue(), 2028),
                created_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await db_session.flush()
    api = FastAPI()
    api.include_router(ledger_api.router)
    api.add_exception_handler(AppException, app_exception_handler)
    api.dependency_overrides[ledger_api.ledger_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        for day, value, version, draft in [
            ("2028-02-28", "100", 0, False),
            ("2028-03-01", "150", 0, False),
            ("2028-02-29", "130", 0, False),
            ("2028-02-29", "140", 1, True),
        ]:
            response = await client.put(
                "/input-readings",
                json={
                    "dataset": "饮用水码",
                    "reading_date": day,
                    "values": [
                        {
                            "point_id": str(meters["饮用水码"].id),
                            "value": value,
                            "version": version,
                        }
                    ],
                    "draft": draft,
                    "reason": "字段回归",
                },
            )
            assert response.status_code == 200, response.text
        report = await client.get(
            "/reporting/workbook",
            params={"year": 2028, "month": 2, "dataset": "日总量"},
        )
        assert report.status_code == 200
        assert Decimal(report.json()["data"]["rows"][27]["cells"]["7"]["value"]) == 30
        response = await client.put(
            "/input-readings",
            json={
                "dataset": "饮用水码",
                "reading_date": "2028-02-29",
                "values": [
                    {
                        "point_id": str(meters["饮用水码"].id),
                        "value": "140",
                        "version": 2,
                    }
                ],
                "draft": False,
                "reason": "字段更正",
            },
        )
        assert response.status_code == 200
        report = await client.get(
            "/reporting/workbook",
            params={"year": 2028, "month": 2, "dataset": "日总量"},
        )
        assert Decimal(report.json()["data"]["rows"][27]["cells"]["7"]["value"]) == 40
        assert Decimal(report.json()["data"]["rows"][28]["cells"]["7"]["value"]) == 10
        for dataset, field, status in [
            ("饮用水量", meters["饮用水码"], 422),
            ("电量", computed, 403),
        ]:
            response = await client.put(
                "/input-readings",
                json={
                    "dataset": dataset,
                    "reading_date": "2028-02-29",
                    "values": [
                        {"point_id": str(field.id), "value": "999", "version": 0}
                    ],
                    "draft": False,
                },
            )
            assert response.status_code == status
    assert "baseline" not in {
        item["name"]
        for item in api.openapi()["paths"]["/reporting/workbook"]["get"]["parameters"]
    }
