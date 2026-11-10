"""Regressions identified while reviewing the four supplied monthly workbooks."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest

from app.modules.energy.ledger_imports import inspect_xlsx
from app.modules.energy.ledger_source_workbook import SourceWorkbook, source_period
from app.modules.energy.ledger_template import extract_template


def workbook_bytes(book: openpyxl.Workbook) -> bytes:
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def test_development_audit_preserves_original_file(tmp_path) -> None:
    from scripts.energy_workbooks import audit

    book = openpyxl.Workbook()
    book.active.title = "日用量"
    book.active.append(["日期", "汇总"])
    book.active.append(["10/1", "=1+2"])
    original = tmp_path / "source.xlsx"
    original.write_bytes(workbook_bytes(book))
    output = tmp_path / "audit"
    summary = audit([original], 2026, output)[0]
    assert summary["report_period"] == "2026-10"
    assert summary["formula_summary"]["workbook_total"] == 1
    assert (output / "source.xlsx").read_bytes() == original.read_bytes()
    assert (output / "analysis.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment,host", [("production", "localhost"), ("development", "shared-db")]
)
async def test_development_loader_rejects_other_databases(
    monkeypatch, environment, host
):
    from types import SimpleNamespace
    from uuid import uuid4

    from scripts import energy_workbooks

    monkeypatch.setattr(
        energy_workbooks,
        "get_settings",
        lambda: SimpleNamespace(
            APP_ENV=environment, DATABASE_URL=f"postgresql+asyncpg://{host}/energy"
        ),
    )
    with pytest.raises(ValueError, match="本地开发库"):
        await energy_workbooks.load_development(
            [], 2026, uuid4(), correct_existing=False
        )


def test_styled_empty_cells_do_not_exhaust_source_snapshot_limit() -> None:
    book = openpyxl.Workbook()
    book.remove(book.active)
    for index in range(21):
        sheet = book.create_sheet(f"表{index}")
        sheet.append(["日期", "输入", "结果"])
        sheet.append(["7/1", 10, "=B2+1"])
        sheet.cell(200, 45).number_format = "0.000"
    payload = inspect_xlsx(workbook_bytes(book), 2026)
    source = SourceWorkbook.from_payload(payload)
    assert source.result("表0", "C2").value == 11
    assert payload["sheets"][0]["source_grid"] == [
        ["日期", "输入", "结果"],
        ["7/1", 10, "=B2+1"],
    ]


def test_import_window_keeps_original_month_and_context_date_index() -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "日用量"
    sheet.append(["日期", "结果"])
    sheet.append(["7/31", "=1+1"])
    sheet.append(["8/1", "=B2+1"])
    sheet.append(["8/2", "=B3+1"])
    payload = inspect_xlsx(
        workbook_bytes(book), 2026, date(2026, 7, 31), date(2026, 7, 31)
    )
    assert payload["report_period"] == "2026-08"
    assert payload["formula_summary"]["workbook_total"] == 3
    assert len(payload["formulas"]) == 1
    assert (
        SourceWorkbook.from_payload(payload)
        .cell_on("日总量", 2, date(2026, 8, 1))
        .value
        == 3
    )


def test_daily_usage_alias_keeps_second_header_and_plant_rules() -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "电量"
    sheet.append(["日期", "设备"])
    sheet.append(["8/1", 10])
    daily = book.create_sheet("日用量")
    daily.append(["日期", "蒸汽日产气量", None, None, None, "电日用量"])
    daily.append([None, "锅炉产气量", "外供用量", "合计", "外供蒸汽占比"])
    daily.append(["8/1", None, None, None, None, "=电量!B2"])
    payload = inspect_xlsx(workbook_bytes(book), 2026)
    assert payload["sheets"][1]["headers"][4] == "外供蒸汽占比"
    draft = extract_template(payload)
    assert (
        next(rule for rule in draft.rules if rule.source_sheet == "日用量").report_scope
        == "plant"
    )
    source = SourceWorkbook.from_payload(payload)
    assert source.resolve_sheet("日总量") == "日用量"
    assert source.cell_on("日总量", 6, date(2026, 8, 1)).value == 10


def test_context_dates_do_not_make_august_replace_july_source() -> None:
    payload = {
        "year": 2026,
        "sheets": [
            {
                "name": "电量",
                "headers": ["日期", "电"],
                "source_grid": [["日期", "电"], ["7/31", 1], ["8/1", 2], ["8/2", 3]],
                "row_dates": [
                    {"row": 2, "date": "2026-07-31"},
                    {"row": 3, "date": "2026-08-01"},
                    {"row": 4, "date": "2026-08-02"},
                ],
            }
        ],
    }
    assert source_period(payload) == (2026, 8)
    source = SourceWorkbook.from_payload(payload)
    assert source.covers(2026, 8)
    assert not source.covers(2026, 7)


def test_duplicate_context_date_does_not_block_the_report_month() -> None:
    payload = {
        "sheets": [
            {
                "name": "蒸汽量",
                "headers": ["日期", "量"],
                "source_grid": [
                    ["日期", "量"],
                    ["8/31", 10],
                    ["9/1", 20],
                    ["8/31", 30],
                ],
                "row_dates": [
                    {"row": 2, "date": "2026-08-31"},
                    {"row": 3, "date": "2026-09-01"},
                    {"row": 4, "date": "2026-08-31"},
                ],
            }
        ],
    }
    source = SourceWorkbook.from_payload(payload, period=(2026, 9))
    assert source.cell_on("蒸汽量", 2, date(2026, 9, 1)).value == 20
    assert source.cell_on("蒸汽量", 2, date(2026, 8, 31)).status == "not_applicable"
    assert source.result("蒸汽量", "B4").value == 30
    with pytest.raises(ValueError, match="重复日期"):
        SourceWorkbook.from_payload(payload, period=(2026, 8))


def test_source_formula_does_not_round_intermediate_values() -> None:
    source = SourceWorkbook.from_payload(
        {
            "sheets": [
                {
                    "name": "电量",
                    "headers": ["日期", "分数", "还原"],
                    "source_grid": [
                        ["日期", "分数", "还原"],
                        ["10/1", "=1/3", "=B2*30000000"],
                    ],
                    "row_dates": [{"row": 2, "date": "2026-10-01"}],
                }
            ]
        }
    )
    assert source.result("电量", "C2").value == Decimal("10000000")


@pytest.mark.parametrize("sheet", ["冰水码", "循环水码"])
def test_detached_copied_fields_are_not_activated_as_meters(sheet: str) -> None:
    from app.modules.energy.ledger_source_policy import input_column_allowed

    assert input_column_allowed(
        sheet, ["日期", "本表读数", "", "", "外表残留"], 2, set()
    )
    assert not input_column_allowed(
        sheet, ["日期", "本表读数", "", "", "外表残留"], 5, set()
    )


def test_review_follows_the_original_cross_date_formula() -> None:
    from app.modules.energy.ledger_schemas import UsageReview, UsageReviewPeriod

    source = SourceWorkbook.from_payload(
        {
            "sheets": [
                {
                    "name": "电量",
                    "headers": ["日期", "来源", "结果"],
                    "source_grid": [
                        ["日期", "来源", "结果"],
                        ["7/1", 10, "=B2"],
                        ["7/2", 20, "=C2*2"],
                    ],
                    "row_dates": [
                        {"row": 2, "date": "2026-07-01"},
                        {"row": 3, "date": "2026-07-02"},
                    ],
                }
            ]
        }
    )
    source.set_reviews(
        [
            UsageReview(
                dataset="电量",
                column=3,
                periods=[
                    UsageReviewPeriod(
                        start_date=date(2026, 7, 1),
                        end_date=date(2026, 7, 1),
                        reason="原表核对",
                        source="日报表",
                    ),
                ],
            )
        ]
    )
    result = source.cell_on("电量", 3, date(2026, 7, 2))
    assert result.value == 20 and result.status == "pending_review"
    assert result.provenance["review"][0]["reason"] == "原表核对"
    source.set_reviews([])
    assert source.cell_on("电量", 3, date(2026, 7, 2)).status == "complete"


@pytest.mark.asyncio
async def test_monthly_reference_stays_archived_while_calculation_uses_business_date(
    db_session,
    monkeypatch,
) -> None:
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from app.modules.energy.ledger_models import EnergyImportBatch, EnergyReading
    from app.modules.energy.ledger_schemas import (
        MeterDefinition,
        MeterWrite,
        RuleDefinition,
        RuleTerm,
        RuleWrite,
    )
    from app.modules.energy.ledger_service import EnergyLedgerService
    from app.modules.energy.ledger_sources import load_monthly_source
    from app.modules.energy.ledger_workbook import EnergyWorkbookService
    from tests.modules.energy.workbook_fixtures import seed_meter, seed_rule

    service = EnergyLedgerService(db_session)
    code = "monthly_" + uuid4().hex
    point = MeterDefinition(
        code=code,
        name="测试电量",
        category="electricity",
        area="测试",
        unit="kWh",
        reading_type="direct",
        quantity_kind="electricity",
        source_sheet="电量",
        source_column=2,
        active_from=date(2026, 7, 1),
        enabled=True,
    )
    meter = await seed_meter(service, MeterWrite(definition=point))
    await seed_rule(
        service,
        RuleWrite(
            definition=RuleDefinition(
                code=code + "_rule",
                name="日报电量",
                category="electricity",
                unit="kWh",
                quantity_kind="electricity",
                source_sheet="日总量",
                source_column=2,
                report_scope="plant",
                active_from=date(2026, 7, 1),
                enabled=True,
                terms=[RuleTerm(metric_key="point:" + code)],
            )
        ),
    )
    now = datetime.now(UTC)
    for month, daily_name, amount in [(7, "日总量", 10), (8, "日用量", 20)]:
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "电量"
        sheet.append(["日期", "测试电量"])
        sheet.append([f"{month - 1}/31", 1])
        sheet.append([f"{month}/1", amount])
        sheet.append([f"{month}/2", amount * 2])
        daily = book.create_sheet(daily_name)
        daily.append(["日期", "日报电量"])
        daily.append([f"{month}/1", "=电量!B3*2"])
        # Deliberate previous-date reference stays in evidence only.
        daily.append([f"{month}/2", "=电量!B3*3"])
        db_session.add(
            EnergyImportBatch(
                id=uuid4(),
                content_hash=uuid4().hex * 2,
                status="imported",
                payload=inspect_xlsx(workbook_bytes(book), 2026),
                created_at=now + timedelta(seconds=month),
            )
        )
    for month, amount in [(7, 10), (8, 20)]:
        for number, value in [(1, amount), (2, amount * 2)]:
            db_session.add(
                EnergyReading(
                    point_id=meter.id,
                    task_id=uuid4(),
                    reading_date=date(2026, month, number),
                    value=Decimal(value),
                    version=1,
                )
            )
    await db_session.flush()
    july = await load_monthly_source(db_session, 2026, 7, await service.meters())
    august = await load_monthly_source(db_session, 2026, 8, await service.meters())
    assert july and august and july.batch_id != august.batch_id
    assert july.workbook.cell_on("日总量", 2, date(2026, 7, 1)).value == 20
    assert august.workbook.cell_on("日总量", 2, date(2026, 8, 2)).value == 60
    outputs = await service.evaluate(date(2026, 8, 2))
    result = next(
        result for key, _, result in outputs if key == "rule:" + code + "_rule"
    )
    assert result.value == 40
    assert result.provenance["reference"]["formula"] == "=电量!B3*3"
    assert result.provenance["calculation_date"] == "2026-08-02"
    report = await EnergyWorkbookService(service).report(2026, 8, "日总量")
    assert report.rows[1].cells["2"].value == 40

    # Importing a later version of July must keep August's copied context intact.
    context = EnergyReading(
        point_id=meter.id,
        task_id=uuid4(),
        reading_date=date(2026, 7, 31),
        value=Decimal(999),
        version=1,
        submitted_at=now + timedelta(minutes=1),
        source="import",
    )
    db_session.add(context)
    await db_session.flush()
    august = await load_monthly_source(db_session, 2026, 8, await service.meters())
    assert august.workbook.cell_on("电量", 2, date(2026, 7, 31)).value == 1
    context.source = "platform"
    await db_session.flush()
    august = await load_monthly_source(db_session, 2026, 8, await service.meters())
    assert august.workbook.cell_on("电量", 2, date(2026, 7, 31)).value == 999

    from unittest.mock import AsyncMock

    from app.modules.energy.ledger_schemas import UsageReview, UsageReviewPeriod

    reviewed = []
    monkeypatch.setattr(
        service, "usage_reviews", AsyncMock(side_effect=lambda: reviewed)
    )
    await service.rebuild({date(2026, 8, 2)})
    for review_day, expected in [
        (2, "pending_review"),
        (1, "complete"),
        (None, "complete"),
    ]:
        reviewed[:] = (
            []
            if review_day is None
            else [
                UsageReview(
                    dataset="电量",
                    column=2,
                    periods=[
                        UsageReviewPeriod(
                            start_date=date(2026, 8, review_day),
                            end_date=date(2026, 8, review_day),
                            reason="核对跨日期公式",
                            source="原始月报",
                        )
                    ],
                )
            ]
        )
        service._monthly_sources.clear()
        report = await service.report(
            date(2026, 8, 2), date(2026, 8, 2), metric_key="rule:" + code + "_rule"
        )
        assert report.rows[0].status == expected
        assert report.rows[0].calculated_value == 40


@pytest.mark.asyncio
async def test_preview_http_reports_formula_errors_and_keeps_invalid_upload_4xx(
    monkeypatch,
) -> None:
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from httpx import ASGITransport, AsyncClient

    from app.core.exceptions import AppException
    from app.modules.energy import ledger_api

    book = openpyxl.Workbook()
    book.active.title = "日用量"
    book.active.append(["日期", "占比"])
    book.active.append(["10/1", "=1/0"])
    service = AsyncMock()
    service.actor_id = None
    service.db.scalar.return_value = None

    async def flush():
        pass

    service.db.flush.side_effect = flush

    def add(batch):
        if getattr(batch, "id", None) is None:
            batch.id = uuid4()

    service.db.add = add
    api = FastAPI()
    api.include_router(ledger_api.router)
    api.dependency_overrides[ledger_api.ledger_service] = lambda: service

    @api.exception_handler(AppException)
    async def error(_request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"message": exc.message}
        )

    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.post(
            "/imports/preview",
            params={"year": 2026},
            files={
                "file": (
                    "report.xlsx",
                    workbook_bytes(book),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["payload"]["report_period"] == "2026-10"
        assert response.json()["data"]["payload"]["formula_summary"]["errors"] == {
            "zero_denominator": 1
        }
        invalid = await client.post(
            "/imports/preview",
            params={"year": 2026},
            files={
                "file": (
                    "report.xlsx",
                    b"invalid",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert invalid.status_code == 422
