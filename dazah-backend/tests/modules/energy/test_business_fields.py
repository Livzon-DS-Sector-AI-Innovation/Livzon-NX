"""Business identities survive monthly worksheet layout and formula changes."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import openpyxl
import pytest
from sqlalchemy import select

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
from app.modules.energy.ledger_source_workbook import SourceWorkbook
from tests.modules.energy.workbook_fixtures import seed_meter, seed_rule


def monthly_book(month: int) -> dict:
    book = openpyxl.Workbook()
    source = book.active
    source.title = "电量"
    source.append(["日期", "压缩机"])
    source.append([f"{month}/1", 10])
    source.append([f"{month}/2", 20])
    workshop = book.create_sheet("102-1车间")
    workshop.append(
        ["日期", "饮用水", "电", "蒸汽", "压缩空气"]
        if month == 9
        else ["日期", "饮用水", "电", "蒸汽", "大罐数量", "压缩空气", "循环水"]
    )
    for day in [1, 2]:
        formula = f"=电量!B{day + 1}*{month}"
        workshop.append(
            [f"{month}/{day}", None, None, None, formula]
            if month == 9
            else [f"{month}/{day}", None, None, None, 99, formula, None]
        )
    output = BytesIO()
    book.save(output)
    return inspect_xlsx(output.getvalue(), 2026)


def test_preview_persists_business_fields_and_per_cell_formula_mapping():
    july, september = monthly_book(7), monthly_book(9)
    first = next(
        item for item in july["field_mappings"] if item["business_name"] == "压缩空气"
    )
    second = next(
        item
        for item in september["field_mappings"]
        if item["business_name"] == "压缩空气"
    )
    assert first["business_key"] == second["business_key"]
    assert first["source_column"] == 6 and second["source_column"] == 5
    assert first["formula_cells"] == ["F2", "F3"]
    assert second["formula_cells"] == ["E2", "E3"]
    book = SourceWorkbook.from_payload(september)
    assert (
        book.result("102-1车间", second["formula_cells"][0]).provenance["formula"]
        == "=电量!B2*9"
    )


def test_cosmetic_labels_and_daily_sheet_alias_share_business_identity():
    from app.modules.energy.ledger_fields import business_key

    assert business_key("日用量", "锅  炉 产气量") == business_key(
        "日总量", "锅炉产气量"
    )
    assert business_key("电量", "（-5℃）冰水用电量") == business_key(
        "电量", "-5℃ 冰水 用电量"
    )
    assert business_key("101车间", "压缩空气") != business_key("102-1车间", "压缩空气")


def test_missing_month_field_and_duplicate_meter_names_are_not_silently_merged():
    book = SourceWorkbook.from_payload(monthly_book(9))
    missing = RuleDefinition(
        code="circulation",
        name="102-1车间·循环水",
        category="circulating_water",
        unit="m³",
        source_sheet="102-1车间",
        source_column=7,
        active_from=date(2026, 7, 1),
        terms=[RuleTerm(metric_key="point:input")],
    )
    assert (
        book.business_cell(missing, date(2026, 9, 1)).status == "source_field_missing"
    )
    from app.modules.energy.ledger_fields import build_field_mappings, find_field

    mappings = build_field_mappings(
        {
            "sheets": [
                {
                    "name": "饮用水码",
                    "headers": ["日期", "同名水表", "同名水表"],
                    "source_grid": [],
                }
            ]
        }
    )
    assert mappings[0]["business_key"] != mappings[1]["business_key"]
    definition = MeterDefinition(
        code="water",
        name="同名水表〔C列〕",
        category="drinking_water",
        area="测试",
        unit="m³",
        source_sheet="饮用水码",
        source_column=3,
        active_from=date(2026, 7, 1),
    )
    assert find_field(mappings, definition)["source_column"] == 3
    assert (
        find_field(mappings, definition.model_copy(update={"source_column": 4})) is None
    )


def test_unnamed_calculated_column_retains_explicit_source_binding():
    payload = monthly_book(9)
    sheet = next(item for item in payload["sheets"] if item["name"] == "102-1车间")
    sheet["headers"][4] = ""
    book = SourceWorkbook.from_payload(payload)
    definition = RuleDefinition(
        code="unnamed",
        name="102-1车间·来源表计（原表E列无表头）",
        category="air",
        unit="m³",
        source_sheet="102-1车间",
        source_column=5,
        active_from=date(2026, 7, 1),
        terms=[RuleTerm(metric_key="point:input")],
    )
    field = book.field_for(definition)
    assert field["source_label"] == "" and field["status"] == "missing_label"
    assert field["formula_cells"] == ["E2", "E3"]
    result = book.business_cell(definition, date(2026, 9, 1))
    assert result.value == 90
    assert result.provenance["formula"] == "=电量!B2*9"
    # A genuinely named, absent business field must never take this column.
    assert (
        book.business_cell(
            definition.model_copy(update={"name": "102-1车间·压缩空气"}),
            date(2026, 9, 1),
        ).status
        == "source_field_missing"
    )


@pytest.mark.asyncio
async def test_september_shift_keeps_one_metric_and_does_not_read_tank_count(
    db_session,
):
    service = EnergyLedgerService(db_session)
    token = uuid4().hex
    meter = await seed_meter(
        service,
        MeterWrite(
            definition=MeterDefinition(
                code="input_" + token,
                name="压缩机",
                category="electricity",
                unit="kWh",
                area="测试",
                reading_type="direct",
                quantity_kind="electricity",
                source_sheet="电量",
                source_column=2,
                active_from=date(2026, 7, 1),
                enabled=True,
            )
        ),
    )

    def definition(column, code):
        return RuleDefinition(
            code=code,
            name="102-1车间·压缩空气",
            category="air",
            unit="m³",
            source_sheet="102-1车间",
            source_column=column,
            workshop="102-1车间",
            report_scope="detail",
            active_from=date(2026, 7, 1),
            enabled=True,
            terms=[RuleTerm(metric_key="point:" + meter.definition.code)],
        )

    canonical = await seed_rule(
        service, RuleWrite(definition=definition(6, "air_" + token))
    )
    from app.modules.energy.ledger_models import EnergyCalculationRule

    canonical_record = await db_session.get(EnergyCalculationRule, canonical.id)
    canonical_record.created_at = datetime.now(UTC) - timedelta(days=1)
    await seed_rule(service, RuleWrite(definition=definition(5, "shifted_" + token)))
    for month in [7, 8, 9, 10]:
        db_session.add(
            EnergyImportBatch(
                id=uuid4(),
                content_hash=uuid4().hex * 2,
                status="imported",
                payload=monthly_book(month),
            )
        )
        # Native readings drive the invariant rule; sample multipliers are evidence.
        db_session.add(
            EnergyReading(
                point_id=meter.id,
                task_id=uuid4(),
                reading_date=date(2026, month, 1),
                value=Decimal(10 * month),
                version=1,
            )
        )
    await db_session.flush()
    for month, column in [(7, 6), (8, 6), (9, 5), (10, 6)]:
        day = date(2026, month, 1)
        await service.rebuild({day})
        report = await service.report(
            day, day, workshop="102-1车间", include_all=True, include_basis=True
        )
        assert len(report.rows) == 1
        row = report.rows[0]
        assert row.metric_key == "rule:" + canonical.definition.code
        assert row.calculated_value == Decimal(10 * month)
        assert row.provenance["source_column"] == column
        assert row.provenance["business_key"]
        assert row.provenance["reference"]["formula"] == f"=电量!B2*{month}"
    facts = (
        await db_session.scalars(
            select(EnergyUsageFact).where(
                EnergyUsageFact.usage_date == date(2026, 9, 1),
                EnergyUsageFact.is_deleted.is_(False),
                EnergyUsageFact.metric_key.startswith("rule:"),
            )
        )
    ).all()
    assert len(facts) == 1


@pytest.mark.asyncio
async def test_prepare_and_confirm_store_monthly_bindings_without_creating_shifted_rule(
    db_session,
):
    from app.modules.energy.ledger_imports import confirm_import, prepare_import
    from app.modules.energy.ledger_models import EnergyCalculationRule, EnergyMeterPoint
    from app.modules.energy.ledger_schemas import ImportConfirm, ImportMapping
    from app.platform.identity.models import User

    actor = User(
        id=uuid4(),
        username="fields-" + uuid4().hex,
        name="字段映射测试",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(actor)
    await db_session.flush()
    service = EnergyLedgerService(db_session, actor)
    original_meter = await seed_meter(
        service,
        MeterWrite(
            definition=MeterDefinition(
                code="confirmed_" + uuid4().hex,
                name="开发验证·压缩机（已确认别名）",
                category="electricity",
                unit="kWh",
                area="测试",
                reading_type="direct",
                source_sheet="电量",
                source_column=2,
                active_from=date(2026, 7, 1),
                enabled=True,
            )
        ),
    )
    keys = []
    for month in [7, 8, 9, 10]:
        payload = monthly_book(month)
        for sheet in payload["sheets"]:
            if sheet["name"] == "102-1车间":
                for row in sheet["source_grid"]:
                    for column, value in enumerate(row):
                        if isinstance(value, str) and value.startswith("="):
                            row[column] = value.split("*")[0]
        for formula in payload["formulas"]:
            formula["formula"] = formula["formula"].split("*")[0]
        batch = EnergyImportBatch(
            id=uuid4(), content_hash=uuid4().hex * 2, status="preview", payload=payload
        )
        db_session.add(batch)
        await db_session.flush()
        await prepare_import(service, batch.id)
        meter = (await service.meters())[0]
        assert meter.id == original_meter.id
        await confirm_import(
            service,
            batch.id,
            ImportConfirm(
                mappings=[ImportMapping(sheet="电量", column=2, point_id=meter.id)],
                reason="核对月份字段与公式",
            ),
        )
        mapping = next(
            item
            for item in batch.payload["field_mappings"]
            if item["business_name"] == "压缩空气"
        )
        assert mapping["source_column"] == (5 if month == 9 else 6)
        assert mapping["formula_cells"] == (
            ["E2", "E3"] if month == 9 else ["F2", "F3"]
        )
        keys.append((mapping["business_key"], mapping["metric_key"]))
        source_mapping = next(
            item
            for item in batch.payload["field_mappings"]
            if item["source_sheet"] == "电量"
        )
        assert source_mapping["metric_key"] == "point:" + original_meter.definition.code
    assert len(set(keys)) == 1 and keys[0][1].startswith("rule:")
    records = (await db_session.scalars(select(EnergyCalculationRule))).all()
    assert len(records) == 1
    assert len((await db_session.scalars(select(EnergyMeterPoint))).all()) == 1

    # Previously imported September facts may still contain July's F address.
    stale = await db_session.scalar(
        select(EnergyUsageFact).where(
            EnergyUsageFact.metric_key == keys[0][1],
            EnergyUsageFact.usage_date == date(2026, 9, 1),
        )
    )
    stale.provenance = {**stale.provenance, "source_cell": "F2", "source_column": 6}
    await db_session.flush()

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.modules.energy import ledger_api

    api = FastAPI()
    api.include_router(ledger_api.router)
    api.dependency_overrides[ledger_api.ledger_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.get(
            "/reporting",
            params={
                "start_date": "2026-09-01",
                "end_date": "2026-09-01",
                "workshop": "102-1车间",
            },
        )
        assert response.status_code == 200
        rows = response.json()["data"]["rows"]
        assert len(rows) == 1 and rows[0]["metric_key"] == keys[0][1]
        assert Decimal(rows[0]["calculated_value"]) == 10
        assert rows[0]["provenance"]["source_column"] == 5
        assert rows[0]["provenance"]["reference"]["formula"] == "=电量!B2"
        workbook = await client.get(
            "/reporting/workbook",
            params={"year": 2026, "month": 9, "dataset": "102-1车间"},
        )
        assert workbook.status_code == 200
        assert (
            workbook.json()["data"]["rows"][0]["cells"]["5"]["provenance"][
                "business_name"
            ]
            == "压缩空气"
        )
