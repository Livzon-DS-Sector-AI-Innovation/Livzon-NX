from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergyMetricFact,
    EnergySheetMapping,
    EnergySheetSnapshot,
    EnergySyncRun,
    EnergyWikiDocument,
    EnergyWorkbookSheet,
)
from app.modules.energy.wiki_service import CST, EnergyWikiService


@pytest.mark.asyncio
async def test_overview_uses_latest_snapshot_and_combines_direct_and_cumulative_values(
    db_session,
):
    config = EnergyFeishuConfig(
        id=uuid4(),
        app_id="cli_energy_test",
        encrypted_app_secret="encrypted",
        root_wiki_url="https://example.feishu.cn/wiki/root",
        root_wiki_token="root",
    )
    document = EnergyWikiDocument(
        id=uuid4(),
        config_id=config.id,
        wiki_node_token="july-node",
        document_token="spreadsheet-token",
        title="2026年7月",
        node_path=[],
        period_month=date(2026, 7, 1),
        classification_status="monthly",
    )
    sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=document.id,
        external_sheet_id="sheet-a",
        title="能源明细",
        headers=["日期", "用量"],
        schema_hash="a" * 64,
    )
    run = EnergySyncRun(
        id=uuid4(),
        config_id=config.id,
        idempotency_key="energy:wiki:test:overview",
        status="success",
    )
    old_snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=sheet.id,
        sync_run_id=run.id,
        snapshot_number=1,
        content_hash="b" * 64,
        header_values=["日期", "用量"],
        row_count=1,
    )
    snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=sheet.id,
        sync_run_id=run.id,
        snapshot_number=2,
        content_hash="a" * 64,
        header_values=["日期", "用量"],
        row_count=6,
    )
    mapping = EnergySheetMapping(
        id=uuid4(),
        sheet_id=sheet.id,
        version=1,
        is_current=True,
        is_enabled=True,
        schema_hash=sheet.schema_hash,
        date_column="日期",
        metrics=[{"metric_key": "usage"}],
    )
    db_session.add_all([config, document, sheet, run, old_snapshot, snapshot, mapping])
    await db_session.flush()
    db_session.add_all(
        [
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=mapping.id,
                mapping_version=1,
                sheet_id=sheet.id,
                snapshot_id=old_snapshot.id,
                metric_key="daily_usage",
                source_row_index=2,
                observed_at=datetime(2026, 7, 2, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                value_semantics="direct",
                value=Decimal("200"),
                dimensions={"车间": "一车间"},
            ),
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=mapping.id,
                mapping_version=1,
                sheet_id=sheet.id,
                snapshot_id=snapshot.id,
                metric_key="daily_usage",
                source_row_index=2,
                observed_at=datetime(2026, 7, 2, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                value_semantics="direct",
                value=Decimal("20"),
                dimensions={"车间": "一车间"},
            ),
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=mapping.id,
                mapping_version=1,
                sheet_id=sheet.id,
                snapshot_id=snapshot.id,
                metric_key="meter_reading",
                source_row_index=3,
                observed_at=datetime(2026, 6, 30, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                meter_key="M-01",
                value_semantics="cumulative",
                value=Decimal("100"),
                dimensions={},
            ),
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=mapping.id,
                mapping_version=1,
                sheet_id=sheet.id,
                snapshot_id=snapshot.id,
                metric_key="meter_reading",
                source_row_index=4,
                observed_at=datetime(2026, 7, 31, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                meter_key="M-01",
                value_semantics="cumulative",
                value=Decimal("130"),
                dimensions={},
            ),
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=mapping.id,
                mapping_version=1,
                sheet_id=sheet.id,
                snapshot_id=snapshot.id,
                metric_key="meter_reading",
                source_row_index=5,
                observed_at=datetime(2026, 6, 30, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                meter_key="M-02",
                value_semantics="cumulative",
                value=Decimal("100"),
                dimensions={},
            ),
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=mapping.id,
                mapping_version=1,
                sheet_id=sheet.id,
                snapshot_id=snapshot.id,
                metric_key="meter_reading",
                source_row_index=6,
                observed_at=datetime(2026, 7, 31, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                meter_key="M-02",
                value_semantics="cumulative",
                value=Decimal("95"),
                dimensions={},
            ),
        ]
    )
    await db_session.flush()

    result = await EnergyWikiService(db_session).get_overview(
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 31, 23, 59, tzinfo=UTC),
        energy_type=None,
        group_by="车间",
    )

    assert [
        (metric.energy_type, metric.unit, metric.total_value)
        for metric in result.metrics
    ] == [("电力", "kWh", 50.0)]
    assert result.invalid_count == 1


@pytest.mark.asyncio
async def test_overview_excludes_daily_and_energy_summary_sources(db_session):
    run_id = uuid4()
    detail_sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=uuid4(),
        external_sheet_id="101-workshop",
        title="101车间",
    )
    summary_sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=uuid4(),
        external_sheet_id="electricity-summary",
        title="电量",
    )
    daily_sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=uuid4(),
        external_sheet_id="daily-summary",
        title="日总量",
    )
    detail_snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=detail_sheet.id,
        sync_run_id=run_id,
        snapshot_number=1,
        content_hash="d" * 64,
    )
    summary_snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=summary_sheet.id,
        sync_run_id=run_id,
        snapshot_number=1,
        content_hash="s" * 64,
    )
    daily_snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=daily_sheet.id,
        sync_run_id=run_id,
        snapshot_number=1,
        content_hash="t" * 64,
    )
    detail_mapping = EnergySheetMapping(
        id=uuid4(),
        sheet_id=detail_sheet.id,
        version=1,
        is_current=True,
        is_enabled=True,
        source_role="workshop_detail",
        metrics=[],
    )
    summary_mapping = EnergySheetMapping(
        id=uuid4(),
        sheet_id=summary_sheet.id,
        version=1,
        is_current=True,
        is_enabled=True,
        source_role="energy_summary",
        metrics=[],
    )
    daily_mapping = EnergySheetMapping(
        id=uuid4(),
        sheet_id=daily_sheet.id,
        version=1,
        is_current=True,
        is_enabled=True,
        source_role="daily_summary",
        metrics=[],
    )
    db_session.add_all(
        [
            detail_sheet,
            summary_sheet,
            daily_sheet,
            detail_snapshot,
            summary_snapshot,
            daily_snapshot,
            detail_mapping,
            summary_mapping,
            daily_mapping,
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=detail_mapping.id,
                mapping_version=1,
                sheet_id=detail_sheet.id,
                snapshot_id=detail_snapshot.id,
                metric_key="electricity",
                source_row_index=2,
                observed_at=datetime(2026, 7, 1, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                value_semantics="direct",
                value=Decimal("25"),
                dimensions={"车间": "101车间"},
            ),
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=summary_mapping.id,
                mapping_version=1,
                sheet_id=summary_sheet.id,
                snapshot_id=summary_snapshot.id,
                metric_key="electricity",
                source_row_index=2,
                observed_at=datetime(2026, 7, 1, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                value_semantics="direct",
                value=Decimal("100"),
                dimensions={"车间": "101车间"},
            ),
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=daily_mapping.id,
                mapping_version=1,
                sheet_id=daily_sheet.id,
                snapshot_id=daily_snapshot.id,
                metric_key="外供蒸汽占比",
                source_row_index=2,
                observed_at=datetime(2026, 7, 1, tzinfo=UTC),
                energy_type="蒸汽",
                unit="%",
                value_semantics="direct",
                value=Decimal("12.5"),
                dimensions={},
            ),
            EnergyMetricFact(
                id=uuid4(),
                mapping_id=daily_mapping.id,
                mapping_version=1,
                sheet_id=daily_sheet.id,
                snapshot_id=daily_snapshot.id,
                metric_key="电日用量",
                source_row_index=3,
                observed_at=datetime(2026, 7, 1, tzinfo=UTC),
                energy_type="电力",
                unit="kWh",
                value_semantics="direct",
                value=Decimal("888"),
                dimensions={},
            ),
        ]
    )
    await db_session.flush()

    result = await EnergyWikiService(db_session).get_overview(
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 1, 23, 59, tzinfo=UTC),
        energy_type=None,
        group_by="车间",
    )

    assert [(item.energy_type, item.total_value) for item in result.metrics] == [
        ("电力", 25.0)
    ]

    daily = await EnergyWikiService(db_session).get_overview(
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 1, 23, 59, tzinfo=UTC),
        energy_type=None,
        group_by="车间",
        source_scope="daily_summary",
    )
    assert daily.source_scope == "daily_summary"
    assert [
        (item.metric_key, item.total_value, item.unit)
        for item in daily.metrics
    ] == [("电日用量", 888.0, "kWh")]
    assert ("外供蒸汽占比", 12.5, "%") in [
        (item.metric_key, item.value, item.unit)
        for item in daily.latest_metrics
    ]
    assert daily.last_observed_at == datetime(2026, 7, 1, tzinfo=UTC)

    energy_summary = await EnergyWikiService(db_session).get_overview(
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 1, 23, 59, tzinfo=UTC),
        energy_type=None,
        group_by="车间",
        source_scope="energy_summary",
        source_sheet_title="电量",
    )
    assert [(item.metric_key, item.total_value) for item in energy_summary.metrics] == [
        ("electricity", 100.0)
    ]

    workshop = await EnergyWikiService(db_session).get_overview(
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 1, 23, 59, tzinfo=UTC),
        energy_type=None,
        group_by="车间",
        workshop="101车间",
    )
    assert [(item.total_value, item.unit) for item in workshop.metrics] == [
        (25.0, "kWh")
    ]


@pytest.mark.asyncio
async def test_sync_document_deduplicates_snapshots_and_inherits_matching_mapping(
    db_session,
):
    """A same-schema monthly sheet inherits its mapping but archives only changes."""

    class FakeSheetClient:
        def __init__(self, values: list[list[str]]) -> None:
            self.values = values

        async def list_workbook_sheets(self, _document_token: str):
            return [{"sheet_id": "month-sheet", "title": "电力明细", "index": 0}]

        async def read_sheet_values(self, **_kwargs):
            return self.values, "revision-1"

    service = EnergyWikiService(db_session)
    config = EnergyFeishuConfig(
        id=uuid4(),
        app_id="cli_energy_sync_test",
        encrypted_app_secret="encrypted",
        root_wiki_url="https://example.feishu.cn/wiki/root",
        root_wiki_token="root",
    )
    template_document = EnergyWikiDocument(
        id=uuid4(),
        config_id=config.id,
        wiki_node_token="template-node",
        document_token="template-book",
        title="2026年6月",
        node_path=[],
        period_month=date(2026, 6, 1),
        classification_status="monthly",
    )
    headers = ["日期", "用量"]
    schema_hash = service._hash(headers)
    template_sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=template_document.id,
        external_sheet_id="template-sheet",
        title="电力明细",
        headers=headers,
        schema_hash=schema_hash,
    )
    template_mapping = EnergySheetMapping(
        id=uuid4(),
        sheet_id=template_sheet.id,
        version=1,
        is_current=True,
        is_enabled=True,
        source_role="energy_summary",
        schema_hash=schema_hash,
        date_column="日期",
        metrics=[
            {
                "metric_key": "daily_usage",
                "value_column": "用量",
                "energy_type": "电力",
                "unit": "kWh",
                "value_semantics": "direct",
            }
        ],
    )
    document = EnergyWikiDocument(
        id=uuid4(),
        config_id=config.id,
        wiki_node_token="july-node",
        document_token="july-book",
        title="2026年7月",
        node_path=[],
        period_month=date(2026, 7, 1),
        classification_status="monthly",
    )
    run = EnergySyncRun(
        id=uuid4(),
        config_id=config.id,
        idempotency_key="energy:wiki:test:dedupe",
        status="running",
    )
    db_session.add_all(
        [
            config,
            template_document,
            template_sheet,
            template_mapping,
            document,
            run,
        ]
    )
    await db_session.flush()

    client = FakeSheetClient([["日期", "用量"], ["2026-07-01", "10"]])
    first = await service._sync_document(
        client=client,  # type: ignore[arg-type]
        document=document,
        run=run,
    )
    second = await service._sync_document(
        client=client,  # type: ignore[arg-type]
        document=document,
        run=run,
    )
    client.values = [["日期", "用量"], ["2026-07-01", "11"]]
    third = await service._sync_document(
        client=client,  # type: ignore[arg-type]
        document=document,
        run=run,
    )

    current_sheet = await service.repo.get_sheet(
        document_id=document.id,
        external_sheet_id="month-sheet",
    )
    assert current_sheet is not None
    inherited_mapping = await service.repo.get_current_mapping(current_sheet.id)
    snapshots = await service.repo.list_snapshots(current_sheet.id)

    assert first == (1, 1, 1)
    assert second == (1, 0, 0)
    assert third == (1, 1, 1)
    assert inherited_mapping is not None
    assert inherited_mapping.source_role == "energy_summary"
    assert inherited_mapping.date_column == "日期"
    assert inherited_mapping.metrics == template_mapping.metrics
    assert [snapshot.snapshot_number for snapshot in snapshots] == [2, 1]


@pytest.mark.asyncio
async def test_scheduled_sync_skips_a_completed_run_for_the_same_day(db_session):
    """The idempotency key prevents a recovered scheduler from executing twice."""

    config = EnergyFeishuConfig(
        id=uuid4(),
        app_id="cli_energy_schedule_test",
        encrypted_app_secret="encrypted",
        root_wiki_url="https://example.feishu.cn/wiki/root",
        root_wiki_token="root",
        daily_sync_time="00:00",
        is_active=True,
    )
    today = datetime.now(CST).date()
    completed_run = EnergySyncRun(
        id=uuid4(),
        config_id=config.id,
        idempotency_key=f"energy:wiki:scheduled:{today.isoformat()}",
        trigger_type="scheduled",
        status="success",
    )
    db_session.add_all([config, completed_run])
    await db_session.flush()

    service = EnergyWikiService(db_session)
    await service.run_scheduled_sync_if_due()
    runs, total = await service.repo.list_sync_runs(
        config_id=config.id,
        page=1,
        page_size=10,
    )

    assert total == 1
    assert runs[0].id == completed_run.id
