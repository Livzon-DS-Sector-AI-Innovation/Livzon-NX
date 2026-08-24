from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace as _SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergyFeishuPageBinding,
    EnergyMetricFact,
    EnergySheetMapping,
    EnergySheetSnapshot,
    EnergySnapshotRow,
    EnergySyncRun,
    EnergyWikiDocument,
    EnergyWorkbookSheet,
)
from app.modules.energy.schemas import (
    EnergyFeishuSourceRootInput,
    EnergyFeishuSourceRootUpdate,
)
from app.modules.energy.wiki_service import CST, EnergyWikiService

SimpleNamespace: Any = _SimpleNamespace


@pytest.mark.asyncio
async def test_overview_aggregates_published_page_bindings_without_field_mapping(
    db_session: Any,
) -> Any:
    run_id = uuid4()
    daily_sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=uuid4(),
        external_sheet_id="daily-total",
        title="日总量",
        header_row=1,
        headers=["日期", "蒸汽日产气量", "", "", "", "电日用量"],
    )
    electricity_sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=uuid4(),
        external_sheet_id="electricity",
        title="电量",
        header_row=1,
        headers=["日期", "总计", "101车间", "102车间", "分表总和"],
    )
    daily_snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=daily_sheet.id,
        sync_run_id=run_id,
        snapshot_number=1,
        content_hash="d" * 64,
        header_values=daily_sheet.headers,
        row_count=5,
    )
    electricity_snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=electricity_sheet.id,
        sync_run_id=run_id,
        snapshot_number=1,
        content_hash="e" * 64,
        header_values=electricity_sheet.headers,
        row_count=4,
    )
    db_session.add_all(
        [
            daily_sheet,
            electricity_sheet,
            daily_snapshot,
            electricity_snapshot,
            EnergyFeishuPageBinding(
                id=uuid4(),
                page_key="energy.daily_total",
                sheet_id=daily_sheet.id,
                tab_name="日总量",
                is_default=True,
                is_enabled=True,
            ),
            EnergyFeishuPageBinding(
                id=uuid4(),
                page_key="energy.electricity",
                sheet_id=electricity_sheet.id,
                tab_name="电量",
                is_default=True,
                is_enabled=True,
            ),
        ]
    )
    db_session.add_all(
        [
            EnergySnapshotRow(
                id=uuid4(),
                snapshot_id=daily_snapshot.id,
                row_index=index,
                values=values,
                row_hash=str(index) * 64,
            )
            for index, values in [
                (1, ["日期", "蒸汽日产气量", None, None, None, "电日用量"]),
                (2, [None, "锅炉产气量", "外供用量", "合计", "外供蒸汽占比"]),
                (3, ["7/1", 100, 20, 120, 0.1667, 1000]),
                (4, ["7/2", 110, 10, 120, 0.0833, 1200]),
                (5, ["7/3", -999, -1, -1000, 0.001, 0]),
            ]
        ]
        + [
            EnergySnapshotRow(
                id=uuid4(),
                snapshot_id=electricity_snapshot.id,
                row_index=index,
                values=values,
                row_hash=f"{index + 5}" * 64,
            )
            for index, values in [
                (1, ["日期", "总计", "101车间", "102车间", "分表总和"]),
                (2, ["7/1", 1000, 300, 700, 1000]),
                (3, ["7/2", 1200, 400, 800, 1200]),
                (4, ["7/3", -1000, -300, -700, -1000]),
            ]
        ]
    )
    await db_session.flush()

    service = EnergyWikiService(db_session)
    detail = await service.get_overview(
        start=datetime(2026, 7, 1, tzinfo=CST),
        end=datetime(2026, 7, 3, 23, 59, tzinfo=CST),
        energy_type=None,
        group_by="车间",
    )
    assert [(item.metric_key, item.total_value) for item in detail.metrics] == [
        ("电量", 2200.0)
    ]
    assert [(item.key, item.value) for item in detail.distribution] == [
        ("101车间", 700.0),
        ("102车间", 1500.0),
    ]
    assert detail.invalid_count == 1
    assert detail.last_observed_at == datetime(2026, 7, 2, tzinfo=CST)

    daily = await service.get_overview(
        start=datetime(2026, 7, 1, tzinfo=CST),
        end=datetime(2026, 7, 3, 23, 59, tzinfo=CST),
        energy_type=None,
        group_by=None,
        source_scope="daily_summary",
    )
    assert [(item.metric_key, item.total_value) for item in daily.metrics] == [
        ("蒸汽量", 240.0),
        ("电量", 2200.0),
    ]
    assert ("外供蒸汽占比", 8.33) in [
        (item.metric_key, item.value) for item in daily.latest_metrics
    ]
    assert daily.invalid_count == 1


@pytest.mark.asyncio
async def test_create_source_root_accepts_direct_spreadsheet_link() -> Any:
    class FakeSession:
        async def commit(self: Any) -> Any:
            return None

    async def save_root(root: Any) -> Any:
        root.id = uuid4()
        return root

    service = EnergyWikiService(cast(Any, FakeSession)())
    service.repo.get_config = AsyncMock(return_value=SimpleNamespace(id=uuid4()))  # type: ignore[method-assign]
    service.repo.list_source_roots = AsyncMock(return_value=[])  # type: ignore[method-assign]
    service.repo.save_source_root = AsyncMock(side_effect=save_root)  # type: ignore[method-assign]

    root = await service.create_source_root(
        EnergyFeishuSourceRootInput(
            name="能源副本",
            source_type="wiki",
            source_url="https://example.feishu.cn/sheets/shtcnExample",
        )
    )

    assert root.root_token == "shtcnExample"
    assert root.source_type == "wiki"


@pytest.mark.asyncio
async def test_connectivity_lists_direct_spreadsheet_sheets_without_wiki_lookup() -> (
    Any
):
    class FakeSheetClient:
        async def list_workbook_sheets(self: Any, spreadsheet_token: Any) -> Any:
            assert spreadsheet_token == "shtcnExample"
            return [
                {"sheet_id": "sheet-a", "title": "电力"},
                {"sheet_id": "sheet-b", "title": "蒸汽"},
            ]

        async def get_wiki_node(self: Any, _root_token: Any) -> Any:
            raise AssertionError("直连电子表格不应调用 Wiki 节点接口")

    root: Any = SimpleNamespace(
        is_active=True,
        source_type="wiki",
        source_url="https://example.feishu.cn/sheets/shtcnExample",
        root_token="shtcnExample",
    )
    service = EnergyWikiService(object())  # type: ignore[arg-type]
    service.repo.get_config = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id=uuid4())
    )
    service.repo.list_source_roots = AsyncMock(return_value=[root])  # type: ignore[method-assign]
    service._client_for = lambda _config: FakeSheetClient()  # type: ignore[method-assign, assignment, return-value]

    result = await service.test_connectivity()

    assert result.ok
    assert result.steps[0].name == "应用凭据与电子表格"
    assert result.steps[0].message == "可读取 2 个工作表"


@pytest.mark.asyncio
async def test_create_source_root_rejects_duplicate_with_conflict() -> Any:
    config_id = uuid4()
    service = EnergyWikiService(object())  # type: ignore[arg-type]
    service.repo.get_config = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id=config_id)
    )
    service.repo.list_source_roots = AsyncMock(  # type: ignore[method-assign]
        return_value=[SimpleNamespace(source_type="wiki", root_token="wikcnExample")]
    )

    with pytest.raises(AppException) as exc_info:
        await service.create_source_root(
            EnergyFeishuSourceRootInput(
                name="重复入口",
                source_type="wiki",
                source_url="wikcnExample",
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "该飞书数据入口已存在"


@pytest.mark.asyncio
async def test_delete_source_root_rolls_back_integrity_conflict() -> Any:
    root: Any = SimpleNamespace(is_deleted=False, is_active=True)
    integrity_error = IntegrityError(
        "UPDATE energy.feishu_source_roots",
        {},
        Exception("duplicate"),
    )
    session: Any = SimpleNamespace(
        commit=AsyncMock(side_effect=integrity_error),
        rollback=AsyncMock(),
    )
    service = EnergyWikiService(session)
    service.repo.get_source_root = AsyncMock(return_value=root)  # type: ignore[method-assign]

    with pytest.raises(AppException) as exc_info:
        await service.delete_source_root(uuid4())

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == (
        "停用飞书数据入口时发生数据状态冲突，请刷新后重试"
    )
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_source_root_reparses_source_and_resets_discovery() -> Any:
    config_id = uuid4()
    root_id = uuid4()
    root: Any = SimpleNamespace(
        id=root_id,
        config_id=config_id,
        name="旧入口",
        source_type="wiki",
        source_url="https://example.feishu.cn/wiki/wikcnOld",
        root_token="wikcnOld",
        is_active=True,
        discovery_status="success",
        discovery_error="旧错误",
        last_discovered_at=datetime.now(UTC),
    )
    session: Any = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    service = EnergyWikiService(session)
    service.repo.get_config = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id=config_id)
    )
    service.repo.get_source_root = AsyncMock(return_value=root)  # type: ignore[method-assign]
    service.repo.list_source_roots = AsyncMock(return_value=[root])  # type: ignore[method-assign]
    service.repo.save_source_root = AsyncMock(side_effect=lambda item: item)  # type: ignore[method-assign]

    result = await service.update_source_root(
        root_id,
        EnergyFeishuSourceRootUpdate(
            name="7 月能源 Base",
            source_type="base",
            source_url="https://example.feishu.cn/base/bascnNew",
        ),
    )

    assert result.name == "7 月能源 Base"
    assert result.source_type == "base"
    assert result.root_token == "bascnNew"
    assert result.discovery_status == "pending"
    assert result.discovery_error is None
    assert result.last_discovered_at is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_source_root_rejects_duplicate_target() -> Any:
    config_id = uuid4()
    root_id = uuid4()
    root: Any = SimpleNamespace(
        id=root_id,
        config_id=config_id,
        name="旧入口",
        source_type="wiki",
        source_url="wikcnOld",
        root_token="wikcnOld",
        is_active=True,
    )
    duplicate: Any = SimpleNamespace(
        id=uuid4(),
        source_type="base",
        root_token="bascnDuplicate",
    )
    service = EnergyWikiService(object())  # type: ignore[arg-type]
    service.repo.get_config = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id=config_id)
    )
    service.repo.get_source_root = AsyncMock(return_value=root)  # type: ignore[method-assign]
    service.repo.list_source_roots = AsyncMock(  # type: ignore[method-assign]
        return_value=[root, duplicate]
    )

    with pytest.raises(AppException) as exc_info:
        await service.update_source_root(
            root_id,
            EnergyFeishuSourceRootUpdate(
                source_type="base",
                source_url="bascnDuplicate",
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "该飞书数据入口已存在"


@pytest.mark.asyncio
async def test_overview_uses_latest_snapshot_and_combines_direct_and_cumulative_values(
    db_session: Any,
) -> Any:
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
async def test_overview_excludes_daily_and_energy_summary_sources(
    db_session: Any,
) -> Any:
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
        (item.metric_key, item.total_value, item.unit) for item in daily.metrics
    ] == [("电日用量", 888.0, "kWh")]
    assert ("外供蒸汽占比", 12.5, "%") in [
        (item.metric_key, item.value, item.unit) for item in daily.latest_metrics
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
    db_session: Any,
) -> Any:
    """A same-schema monthly sheet inherits its mapping but archives only changes."""

    class FakeSheetClient:
        def __init__(self: Any, values: list[list[str]]) -> None:
            self.values = values

        async def list_workbook_sheets(self: Any, _document_token: str) -> Any:
            return [{"sheet_id": "month-sheet", "title": "电力明细", "index": 0}]

        async def read_sheet_values(self: Any, **_kwargs: Any) -> Any:
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

    client: Any = FakeSheetClient([["日期", "用量"], ["2026-07-01", "10"]])
    first = await service._sync_document(
        client=client,
        document=document,
        run=run,
    )
    second = await service._sync_document(
        client=client,
        document=document,
        run=run,
    )
    client.values = [["日期", "用量"], ["2026-07-01", "11"]]
    third = await service._sync_document(
        client=client,
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
async def test_scheduled_sync_skips_a_completed_run_for_the_same_day(
    db_session: Any,
) -> Any:
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
