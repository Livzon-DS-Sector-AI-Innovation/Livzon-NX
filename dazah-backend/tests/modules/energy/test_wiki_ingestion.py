from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.core.secrets import encrypt_secret
from app.modules.energy.feishu_client import (
    EnergyFeishuClient,
    EnergyFeishuRequestError,
)
from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergyMetricFact,
    EnergySheetSnapshot,
    EnergySnapshotRow,
    EnergySyncRun,
    EnergyWikiDocument,
    EnergyWorkbookSheet,
)
from app.modules.energy.schemas import (
    EnergyMappingMetricInput,
    EnergySheetMappingUpsert,
)
from app.modules.energy.wiki_service import EnergyWikiService


def test_parse_wiki_token_from_leaf_url():
    assert (
        EnergyFeishuClient.parse_wiki_token(
            "https://example.feishu.cn/wiki/FYtAwGGFIiyJKNkYZNWcdn1cnfd?sheet=LlAw4G"
        )
        == "FYtAwGGFIiyJKNkYZNWcdn1cnfd"
    )


@pytest.mark.asyncio
async def test_retry_retries_transient_failures_with_exponential_backoff(monkeypatch):
    client = object.__new__(EnergyFeishuClient)
    attempts = 0
    delays: list[int] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary upstream timeout")
        return "ok"

    async def fake_sleep(delay: int) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.modules.energy.feishu_client.asyncio.sleep", fake_sleep)

    assert await client._retry(operation) == "ok"
    assert attempts == 3
    assert delays == [1, 2]


@pytest.mark.asyncio
async def test_sheet_discovery_uses_the_official_sheet_query_endpoint():
    class FakeFeishuClient:
        def __init__(self) -> None:
            self.path = ""

        async def request(self, _method: str, path: str, **_kwargs):
            self.path = path
            return {"sheets": [{"sheet_id": "sheet-a", "title": "日总量"}]}

    client = object.__new__(EnergyFeishuClient)
    client._client = FakeFeishuClient()  # type: ignore[assignment]

    sheets = await client.list_workbook_sheets("spreadsheet-token")

    assert sheets == [{"sheet_id": "sheet-a", "title": "日总量"}]
    assert client._client.path == (
        "/sheets/v3/spreadsheets/spreadsheet-token/sheets/query"
    )


@pytest.mark.asyncio
async def test_sheet_discovery_normalizes_camel_case_grid_size():
    class FakeFeishuClient:
        async def request(self, _method: str, _path: str, **_kwargs):
            return {
                "sheets": [
                    {
                        "sheet_id": "sheet-a",
                        "gridProperties": {"rowCount": 12, "columnCount": 703},
                    }
                ]
            }

    client = object.__new__(EnergyFeishuClient)
    client._client = FakeFeishuClient()  # type: ignore[assignment]

    sheets = await client.list_workbook_sheets("spreadsheet-token")

    assert sheets[0]["grid_properties"] == {
        "row_count": 12,
        "column_count": 703,
    }


@pytest.mark.asyncio
async def test_sheet_values_read_every_declared_row_even_after_empty_chunks():
    class FakeFeishuClient:
        def __init__(self) -> None:
            self.paths: list[str] = []

        async def request(self, _method: str, path: str, **_kwargs):
            self.paths.append(path)
            values = [["tail"]] if "A10001%3AAAA10001" in path else []
            return {"revision": 12, "valueRange": {"values": values}}

    client = object.__new__(EnergyFeishuClient)
    client._client = FakeFeishuClient()  # type: ignore[assignment]

    values, revision = await client.read_sheet_values(
        spreadsheet_token="spreadsheet-token",
        sheet_id="sheet-a",
        row_count=10_001,
        column_count=703,
    )

    assert len(values) == 10_001
    assert values[-1] == ["tail"]
    assert revision == "12"
    assert len(client._client.paths) == 21
    assert client._client.paths[0].endswith("sheet-a!A1%3AAAA500")
    assert client._client.paths[-1].endswith("sheet-a!A10001%3AAAA10001")


@pytest.mark.asyncio
async def test_sheet_values_request_calculated_values_and_formatted_dates():
    class FakeFeishuClient:
        def __init__(self) -> None:
            self.params: list[dict[str, str] | None] = []

        async def request(self, _method: str, _path: str, **kwargs):
            self.params.append(kwargs.get("params"))
            return {"valueRange": {"values": [["2026/06/27", 1052]]}}

    client = object.__new__(EnergyFeishuClient)
    client._client = FakeFeishuClient()  # type: ignore[assignment]

    values, _revision = await client.read_sheet_values(
        spreadsheet_token="spreadsheet-token",
        sheet_id="sheet-a",
        row_count=1,
        column_count=2,
    )

    assert values == [["2026/06/27", 1052]]
    assert client._client.params == [
        {
            "valueRenderOption": "UnformattedValue",
            "dateTimeRenderOption": "FormattedString",
        }
    ]


@pytest.mark.asyncio
async def test_sheet_values_can_request_feishu_formatted_display_values():
    class FakeFeishuClient:
        def __init__(self) -> None:
            self.params: list[dict[str, str] | None] = []

        async def request(self, _method: str, _path: str, **kwargs):
            self.params.append(kwargs.get("params"))
            return {"valueRange": {"values": [["8%"]]}}

    client = object.__new__(EnergyFeishuClient)
    client._client = FakeFeishuClient()  # type: ignore[assignment]

    values, _revision = await client.read_sheet_values(
        spreadsheet_token="spreadsheet-token",
        sheet_id="sheet-a",
        row_count=1,
        column_count=1,
        value_render_option="FormattedValue",
    )

    assert values == [["8%"]]
    assert client._client.params == [
        {
            "valueRenderOption": "FormattedValue",
            "dateTimeRenderOption": "FormattedString",
        }
    ]


@pytest.mark.asyncio
async def test_sheet_values_reduce_chunk_after_feishu_response_too_large():
    class FakeFeishuClient:
        def __init__(self) -> None:
            self.paths: list[str] = []

        async def request(self, _method: str, path: str, **_kwargs):
            self.paths.append(path)
            if len(self.paths) == 1:
                raise RuntimeError(
                    "Feishu API error: code=90221, msg=data exceeded 10485760 bytes"
                )
            value = 1 if "A1%3AB1" in path else 2
            return {"valueRange": {"values": [[value]]}}

    client = object.__new__(EnergyFeishuClient)
    client._client = FakeFeishuClient()  # type: ignore[assignment]

    values, _revision = await client.read_sheet_values(
        spreadsheet_token="spreadsheet-token",
        sheet_id="sheet-a",
        row_count=2,
        column_count=2,
    )

    assert values == [[1], [2]]
    assert client._client.paths == [
        "/sheets/v2/spreadsheets/spreadsheet-token/values/sheet-a!A1%3AB2",
        "/sheets/v2/spreadsheets/spreadsheet-token/values/sheet-a!A1%3AB1",
        "/sheets/v2/spreadsheets/spreadsheet-token/values/sheet-a!A2%3AB2",
    ]


@pytest.mark.asyncio
async def test_sheet_values_split_columns_and_preserve_cell_offsets():
    class FakeFeishuClient:
        async def request(self, _method: str, path: str, **_kwargs):
            if "A1%3AD1" in path:
                raise RuntimeError("Feishu API error: code=90221")
            if "A1%3AB1" in path:
                return {"valueRange": {"values": [["left"]]}}
            return {"valueRange": {"values": [["right"]]}}

    client = object.__new__(EnergyFeishuClient)
    client._client = FakeFeishuClient()  # type: ignore[assignment]

    values, _revision = await client.read_sheet_values(
        spreadsheet_token="spreadsheet-token",
        sheet_id="sheet-a",
        row_count=1,
        column_count=4,
    )

    assert values == [["left", None, "right"]]


@pytest.mark.asyncio
async def test_sheet_values_refuse_to_guess_missing_grid_size():
    client = object.__new__(EnergyFeishuClient)

    with pytest.raises(RuntimeError, match="无法保证完整读取"):
        await client.read_sheet_values(
            spreadsheet_token="spreadsheet-token",
            sheet_id="sheet-a",
            row_count=None,
            column_count=2,
        )


def test_parse_direct_spreadsheet_link():
    url = "https://example.feishu.cn/sheets/shtcnExample?sheet=sheet-a"

    assert EnergyFeishuClient.is_spreadsheet_url(url)
    assert EnergyFeishuClient.parse_spreadsheet_token(url) == "shtcnExample"


@pytest.mark.asyncio
async def test_sync_document_continues_after_one_sheet_fails(monkeypatch):
    class NestedTransaction:
        async def __aenter__(self):
            return None

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    class FakeSession:
        def begin_nested(self):
            return NestedTransaction()

        async def flush(self):
            return None

    class FakeSheetClient:
        async def list_workbook_sheets(self, _document_token: str):
            return [
                {"sheet_id": "too-large", "title": "大表"},
                {"sheet_id": "normal", "title": "正常表"},
            ]

    service = EnergyWikiService(FakeSession())  # type: ignore[arg-type]

    async def fake_sync_workbook_sheet(**kwargs):
        if kwargs["raw_sheet"]["sheet_id"] == "too-large":
            raise RuntimeError("Feishu API error: code=90221")
        return 1, 1, 2

    monkeypatch.setattr(service, "_sync_workbook_sheet", fake_sync_workbook_sheet)
    document = EnergyWikiDocument(
        id=uuid4(),
        config_id=uuid4(),
        wiki_node_token="node",
        document_token="spreadsheet-token",
        title="7月份能源日报表",
        node_path=[],
    )
    run = EnergySyncRun(
        id=uuid4(),
        config_id=document.config_id,
        idempotency_key="energy:wiki:test:sheet-isolation",
    )

    counts = await service._sync_document(
        client=FakeSheetClient(),  # type: ignore[arg-type]
        document=document,
        run=run,
    )

    assert counts == (1, 1, 2)
    assert run.error_count == 1
    assert "大表" in (run.error_message or "")
    assert "90221" in (run.error_message or "")


@pytest.mark.asyncio
async def test_wiki_http_error_keeps_feishu_code_without_leaking_request_token():
    class FailingFeishuClient:
        def __init__(self) -> None:
            self.calls = 0

        async def request(self, _method: str, _path: str, **_kwargs):
            self.calls += 1
            request = httpx.Request(
                "GET",
                "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token=private-token",
            )
            response = httpx.Response(
                400,
                request=request,
                headers={"x-tt-logid": "log-123"},
                json={"code": 131006, "msg": "permission denied"},
            )
            raise httpx.HTTPStatusError(
                "bad request", request=request, response=response
            )

    client = object.__new__(EnergyFeishuClient)
    client._client = FailingFeishuClient()  # type: ignore[assignment]

    with pytest.raises(EnergyFeishuRequestError) as raised:
        await client.get_wiki_node("private-token")

    assert raised.value.feishu_code == 131006
    assert raised.value.request_log_id == "log-123"
    assert "private-token" not in str(raised.value)
    assert client._client.calls == 1


def test_config_response_never_exposes_plaintext_app_secret():
    secret = "energy-secret-for-test"
    config = EnergyFeishuConfig(
        id=uuid4(),
        config_name="能源 Wiki 数据源",
        app_id="cli_energy_secret_test",
        encrypted_app_secret=encrypt_secret(secret),
        root_wiki_url="https://example.feishu.cn/wiki/root",
        root_wiki_token="root",
        timezone="Asia/Shanghai",
        daily_sync_time="02:00",
        is_active=False,
        sync_status="pending",
    )

    response = EnergyWikiService(None)._config_response(config)  # type: ignore[arg-type]

    assert response.app_secret_configured is True
    assert response.app_secret_masked != secret
    assert secret not in response.model_dump_json()


def test_period_is_inherited_from_nearest_monthly_ancestor():
    period = EnergyWikiService._period_from_path(
        [
            {"token": "root", "title": "能源台账"},
            {"token": "month", "title": "2026年7月"},
            {"token": "child", "title": "水电明细"},
        ]
    )
    assert period == date(2026, 7, 1)


def test_cumulative_mapping_requires_meter_key():
    with pytest.raises(ValueError, match="计量点"):
        EnergyMappingMetricInput(
            metric_key="electricity_reading",
            value_column="表底",
            energy_type="电力",
            unit="kWh",
            value_semantics="cumulative",
        )


def test_enabled_mapping_requires_date_and_metric():
    with pytest.raises(ValueError, match="日期列"):
        EnergySheetMappingUpsert(is_enabled=True)


@pytest.mark.asyncio
async def test_discover_tree_recurses_and_keeps_monthly_ancestor_path():
    client = object.__new__(EnergyFeishuClient)
    children = {
        "root": [
            {
                "node_token": "july",
                "title": "2026-07",
                "has_child": True,
                "obj_type": "doc",
            }
        ],
        "july": [
            {
                "node_token": "sheet-node",
                "title": "水电分表",
                "has_child": False,
                "obj_type": "sheet",
                "obj_token": "spreadsheet-token",
            }
        ],
    }

    async def get_node(_token: str):
        return {
            "node_token": "root",
            "title": "能源台账",
            "space_id": "space",
            "has_child": True,
        }

    async def list_children(*, space_id: str, parent_node_token: str):
        assert space_id == "space"
        return children[parent_node_token]

    client.get_wiki_node = get_node  # type: ignore[method-assign]
    client.list_child_nodes = list_children  # type: ignore[method-assign]

    nodes = await client.discover_tree("root")

    assert [node["node_token"] for node in nodes] == ["root", "july", "sheet-node"]
    assert nodes[-1]["node_path"][-2]["title"] == "2026-07"


@pytest.mark.asyncio
async def test_overview_uses_latest_facts_and_excludes_negative_cumulative_delta():
    sheet_id = uuid4()
    snapshot_id = uuid4()
    mapping_id = uuid4()
    facts = [
        EnergyMetricFact(
            id=uuid4(),
            mapping_id=mapping_id,
            mapping_version=1,
            sheet_id=sheet_id,
            snapshot_id=snapshot_id,
            metric_key="daily",
            source_row_index=1,
            observed_at=datetime(2026, 7, 2, tzinfo=UTC),
            energy_type="电力",
            unit="kWh",
            value_semantics="direct",
            value=Decimal("20"),
            dimensions={"车间": "一车间"},
        ),
        EnergyMetricFact(
            id=uuid4(),
            mapping_id=mapping_id,
            mapping_version=1,
            sheet_id=sheet_id,
            snapshot_id=snapshot_id,
            metric_key="meter",
            source_row_index=2,
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
            mapping_id=mapping_id,
            mapping_version=1,
            sheet_id=sheet_id,
            snapshot_id=snapshot_id,
            metric_key="meter",
            source_row_index=3,
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
            mapping_id=mapping_id,
            mapping_version=1,
            sheet_id=sheet_id,
            snapshot_id=snapshot_id,
            metric_key="meter",
            source_row_index=4,
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
            mapping_id=mapping_id,
            mapping_version=1,
            sheet_id=sheet_id,
            snapshot_id=snapshot_id,
            metric_key="meter",
            source_row_index=5,
            observed_at=datetime(2026, 7, 31, tzinfo=UTC),
            energy_type="电力",
            unit="kWh",
            meter_key="M-02",
            value_semantics="cumulative",
            value=Decimal("95"),
            dimensions={},
        ),
    ]

    class FactRepository:
        async def list_current_facts(self, **_kwargs):
            return facts

    service = EnergyWikiService(None)  # type: ignore[arg-type]
    service.repo = FactRepository()  # type: ignore[assignment]
    result = await service.get_overview(
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


def test_mapping_parses_sparse_rows_by_actual_header_row_number():
    sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=uuid4(),
        external_sheet_id="sheet-a",
        title="电力明细",
    )
    snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=sheet.id,
        sync_run_id=uuid4(),
        snapshot_number=1,
        content_hash="a" * 64,
    )
    rows = [
        EnergySnapshotRow(
            id=uuid4(),
            snapshot_id=snapshot.id,
            row_index=2,
            values=["日期", "用量"],
            row_hash="b" * 64,
        ),
        EnergySnapshotRow(
            id=uuid4(),
            snapshot_id=snapshot.id,
            row_index=3,
            values=["2026-07-01", "12.5"],
            row_hash="c" * 64,
        ),
    ]
    mapping = EnergySheetMappingUpsert(
        is_enabled=True,
        header_row=2,
        date_column="日期",
        metrics=[
            EnergyMappingMetricInput(
                metric_key="daily_usage",
                value_column="用量",
                energy_type="电力",
                unit="kWh",
            )
        ],
    )

    parsed, errors = EnergyWikiService(None)._parse_rows(  # type: ignore[arg-type]
        snapshot_rows=rows,
        mapping=mapping,
        sheet=sheet,
        mapping_id=uuid4(),
        snapshot_id=snapshot.id,
        mapping_version=1,
        preview=False,
    )

    assert errors == []
    assert parsed[0]["fact"].observed_at.date() == date(2026, 7, 1)
    assert float(parsed[0]["fact"].value) == 12.5


def test_workshop_mapping_can_use_sheet_title_as_a_fixed_dimension():
    sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=uuid4(),
        external_sheet_id="workshop-101",
        title="101车间",
    )
    snapshot_id = uuid4()
    rows = [
        EnergySnapshotRow(
            id=uuid4(),
            snapshot_id=snapshot_id,
            row_index=1,
            values=["日期", "电"],
            row_hash="a" * 64,
        ),
        EnergySnapshotRow(
            id=uuid4(),
            snapshot_id=snapshot_id,
            row_index=2,
            values=["2026-07-01", "12.5"],
            row_hash="b" * 64,
        ),
    ]
    mapping = EnergySheetMappingUpsert(
        is_enabled=True,
        source_role="workshop_detail",
        date_column="日期",
        dimensions={"车间": "$sheet_title"},
        metrics=[
            EnergyMappingMetricInput(
                metric_key="electricity",
                value_column="电",
                energy_type="电力",
                unit="kWh",
            )
        ],
    )

    parsed, errors = EnergyWikiService(None)._parse_rows(  # type: ignore[arg-type]
        snapshot_rows=rows,
        mapping=mapping,
        sheet=sheet,
        mapping_id=uuid4(),
        snapshot_id=snapshot_id,
        mapping_version=1,
        preview=False,
    )

    assert errors == []
    assert parsed[0]["fact"].dimensions == {"车间": "101车间"}
