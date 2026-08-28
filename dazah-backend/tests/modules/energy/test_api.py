from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.main import app, database_integrity_exception_handler
from app.modules.energy.api import (
    _render_energy_cell,
    get_energy_page_data,
    get_energy_page_records,
    list_source_sheets,
)
from app.modules.energy.models import EnergyWikiDocument, EnergyWorkbookSheet
from app.modules.energy.schemas import EnergyOverviewMetric, EnergyOverviewResponse
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

SimpleNamespace: Any = _SimpleNamespace


def test_energy_page_renders_spreadsheet_date_serial_without_changing_numbers() -> Any:
    assert _render_energy_cell("日期", 46200) == "2026-06-27"
    assert _render_energy_cell("日期时间", 46200.5) == "2026-06-27 12:00:00"
    assert _render_energy_cell("锅炉产气量", 1052) == 1052


@pytest.mark.asyncio
async def test_energy_overview_returns_mapped_table_statistics_through_http(
    client: Any, monkeypatch: Any
) -> Any:
    user = User(
        id=uuid4(),
        name="能源统计用户",
        username=f"energy-overview-{uuid4().hex[:10]}",
        role="admin",
        status="active",
        auth_source="local",
    )

    class FakeService:
        async def get_overview(self: Any, **_kwargs: Any) -> Any:
            return EnergyOverviewResponse(
                source_scope="detail",
                metrics=[
                    EnergyOverviewMetric(
                        metric_key="电量",
                        energy_type="电量",
                        unit="kWh",
                        total_value=2200,
                        record_count=2,
                    )
                ],
                trend=[],
                distribution=[],
                latest_metrics=[],
                last_observed_at=datetime(2026, 7, 2, tzinfo=UTC),
                invalid_count=0,
            )

    async def override_current_user() -> User:
        return user

    monkeypatch.setattr("app.modules.energy.api._service", lambda _db: FakeService())
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.get(
            "/api/v1/energy/overview",
            params={
                "start_time": "2026-07-01T00:00:00+08:00",
                "end_time": "2026-07-03T23:59:59+08:00",
                "source_scope": "detail",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["data"]["metrics"] == [
        {
            "metric_key": "电量",
            "energy_type": "电量",
            "unit": "kWh",
            "total_value": 2200.0,
            "record_count": 2,
        }
    ]


@pytest.mark.asyncio
async def test_database_integrity_error_is_returned_as_conflict() -> Any:
    request: Any = SimpleNamespace(
        method="DELETE",
        url=SimpleNamespace(path="/api/v1/energy/feishu/roots/root-id"),
    )
    response = await database_integrity_exception_handler(
        request,
        IntegrityError("UPDATE", {}, Exception("duplicate")),
    )

    assert response.status_code == 409
    assert json.loads(response.body) == {  # type: ignore[arg-type]
        "code": 409,
        "message": "数据状态冲突，请刷新后重试",
    }


@pytest.mark.asyncio
async def test_admin_can_read_empty_energy_config_without_exposing_a_secret(
    client: Any,
) -> Any:
    unauthenticated = await client.get("/api/v1/energy/feishu-config")
    assert unauthenticated.status_code == 401

    admin = User(
        id=uuid4(),
        name="能源管理员",
        username=f"energy-admin-{uuid4().hex[:12]}",
        role="admin",
        status="active",
        auth_source="local",
    )

    async def override_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.get("/api/v1/energy/feishu-config")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["app_secret_configured"] is False
    assert data["daily_sync_time"] == "02:00"


@pytest.mark.asyncio
async def test_admin_can_update_energy_source_root_through_http(
    client: Any, monkeypatch: Any
) -> Any:
    admin = User(
        id=uuid4(),
        name="能源管理员",
        username=f"energy-root-update-{uuid4().hex[:10]}",
        role="admin",
        status="active",
        auth_source="local",
    )
    root_id = uuid4()
    received: list[Any] = []

    class FakeService:
        async def update_source_root(
            self: Any, requested_root_id: Any, payload: Any
        ) -> Any:
            received.append((requested_root_id, payload))
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(root_id),
                    "config_id": str(uuid4()),
                    "name": payload.name,
                    "source_type": "base",
                    "source_url": payload.source_url,
                    "root_token": "bascnUpdated",
                    "is_active": True,
                    "discovery_status": "pending",
                    "last_discovered_at": None,
                    "discovery_error": None,
                }
            )

    async def override_current_user() -> User:
        return admin

    monkeypatch.setattr("app.modules.energy.api._service", lambda _db: FakeService())
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.put(
            f"/api/v1/energy/feishu/roots/{root_id}",
            json={
                "name": "更新后的能源表",
                "source_type": "base",
                "source_url": "https://example.feishu.cn/base/bascnUpdated",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert received[0][0] == root_id
    assert received[0][1].name == "更新后的能源表"
    assert response.json()["data"]["discovery_status"] == "pending"


@pytest.mark.asyncio
async def test_legacy_device_api_is_not_exposed(client: Any) -> Any:
    response = await client.get("/api/v1/energy/devices")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_source_sheet_response_adds_document_fields_once(monkeypatch: Any) -> Any:
    document = EnergyWikiDocument(
        id=uuid4(),
        config_id=uuid4(),
        wiki_node_token="wiki-node",
        document_token="spreadsheet-token",
        title="7月份能源日报表",
        node_path=[],
        period_month=date(2026, 7, 1),
    )
    sheet = EnergyWorkbookSheet(
        id=uuid4(),
        document_id=document.id,
        external_sheet_id="sheet-a",
        title="电力",
        sheet_index=0,
        header_row=1,
        headers=["日期", "用量"],
        mapping_status="unmapped",
    )

    class FakeService:
        async def list_sources(self: Any, **_kwargs: Any) -> Any:
            return [(sheet, document)]

        async def get_mapping(self: Any, _sheet_id: Any) -> Any:
            return None

    monkeypatch.setattr("app.modules.energy.api._service", lambda _db: FakeService())

    response = await list_source_sheets(
        period_month=None,
        mapping_status=None,
        db=object(),  # type: ignore[arg-type]
    )
    payload = json.loads(response.body)  # type: ignore[arg-type]

    assert payload["data"][0]["document_title"] == "7月份能源日报表"
    assert payload["data"][0]["period_month"] == "2026-07-01"


@pytest.mark.asyncio
async def test_admin_can_batch_delete_energy_sources_through_http(
    client: Any, monkeypatch: Any
) -> Any:
    admin = User(
        id=uuid4(),
        name="能源管理员",
        username=f"energy-delete-{uuid4().hex[:12]}",
        role="admin",
        status="active",
        auth_source="local",
    )
    first_id = uuid4()
    second_id = uuid4()
    requested_ids: list[list[Any]] = []

    class FakeService:
        async def delete_sources(self: Any, sheet_ids: Any) -> Any:
            requested_ids.append(sheet_ids)
            return {
                "deleted_count": 2,
                "snapshot_count": 3,
                "snapshot_row_count": 120,
                "mapping_count": 2,
                "fact_count": 44,
                "binding_count": 1,
                "document_count": 1,
            }

    async def override_current_user() -> User:
        return admin

    monkeypatch.setattr("app.modules.energy.api._service", lambda _db: FakeService())
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.request(
            "DELETE",
            "/api/v1/energy/sources/batch",
            json={"sheet_ids": [str(first_id), str(second_id)]},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert requested_ids == [[first_id, second_id]]
    assert response.json()["data"]["snapshot_row_count"] == 120


@pytest.mark.asyncio
async def test_admin_can_batch_sync_selected_energy_sources_through_http(
    client: Any, monkeypatch: Any
) -> Any:
    admin = User(
        id=uuid4(),
        name="能源管理员",
        username=f"energy-sync-{uuid4().hex[:12]}",
        role="admin",
        status="active",
        auth_source="local",
    )
    first_id = uuid4()
    second_id = uuid4()
    run_id = uuid4()
    config_id = uuid4()
    requested_ids: list[list[Any]] = []

    class FakeService:
        async def sync_sources(self: Any, sheet_ids: Any) -> Any:
            requested_ids.append(sheet_ids)
            return SimpleNamespace(
                id=run_id,
                config_id=config_id,
                trigger_type="manual_batch",
                scheduled_for=None,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                status="success",
                document_count=1,
                sheet_count=2,
                snapshot_count=2,
                fact_count=0,
                error_count=0,
                error_message=None,
            )

    async def override_current_user() -> User:
        return admin

    monkeypatch.setattr("app.modules.energy.api._service", lambda _db: FakeService())
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.post(
            "/api/v1/energy/sources/batch-sync",
            json={"sheet_ids": [str(first_id), str(second_id)]},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert requested_ids == [[first_id, second_id]]
    assert response.json()["data"]["sheet_count"] == 2
    assert response.json()["data"]["trigger_type"] == "manual_batch"


@pytest.mark.asyncio
async def test_batch_delete_rejects_an_empty_selection_through_http(client: Any) -> Any:
    admin = User(
        id=uuid4(),
        name="能源管理员",
        username=f"energy-empty-delete-{uuid4().hex[:10]}",
        role="admin",
        status="active",
        auth_source="local",
    )

    async def override_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.request(
            "DELETE",
            "/api/v1/energy/sources/batch",
            json={"sheet_ids": []},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_page_data_lists_all_sources_without_optional_filters(
    monkeypatch: Any,
) -> Any:
    calls: list[tuple[str | None, str | None]] = []

    class FakeRepository:
        async def list_page_bindings(self: Any, _page_key: Any) -> Any:
            return []

    class FakeService:
        repo: Any = FakeRepository()

        async def list_sources(
            self: Any, *, period_month: Any, mapping_status: Any
        ) -> Any:
            calls.append((period_month, mapping_status))
            return []

    monkeypatch.setattr("app.modules.energy.api._service", lambda _db: FakeService())

    response = await get_energy_page_data(
        page_key="energy.overview",
        db=object(),  # type: ignore[arg-type]
    )
    payload = json.loads(response.body)  # type: ignore[arg-type]

    assert response.status_code == 200
    assert payload["data"] == {"page_key": "energy.overview", "bindings": []}
    assert calls == [(None, None)]


@pytest.mark.asyncio
async def test_page_records_resolves_the_published_binding_to_its_sheet(
    monkeypatch: Any,
) -> Any:
    binding_id = uuid4()
    sheet_id = uuid4()
    requested_sheet_ids: list[Any] = []

    class FakeRepository:
        async def get_page_binding(
            self: Any, page_key: Any, requested_binding_id: Any
        ) -> Any:
            assert page_key == "energy.overview"
            assert requested_binding_id == binding_id
            return SimpleNamespace(sheet_id=sheet_id)

        async def get_latest_snapshot(self: Any, requested_sheet_id: Any) -> Any:
            assert requested_sheet_id == sheet_id
            return None

    class FakeService:
        repo: Any = FakeRepository()

        async def get_sheet_or_raise(self: Any, requested_sheet_id: Any) -> Any:
            requested_sheet_ids.append(requested_sheet_id)
            return SimpleNamespace(id=sheet_id)

    monkeypatch.setattr("app.modules.energy.api._service", lambda _db: FakeService())

    response = await get_energy_page_records(
        page_key="energy.overview",
        binding_id=binding_id,
        keyword=None,
        page=1,
        page_size=50,
        db=object(),  # type: ignore[arg-type]
    )
    payload = json.loads(response.body)  # type: ignore[arg-type]

    assert response.status_code == 200
    assert payload["data"]["records"] == []
    assert requested_sheet_ids == [sheet_id]


@pytest.mark.asyncio
async def test_page_records_use_formatted_values_but_keep_raw_normalized_values(
    monkeypatch: Any,
) -> Any:
    binding_id = uuid4()
    sheet_id = uuid4()
    snapshot_id = uuid4()
    sheet: Any = SimpleNamespace(
        id=sheet_id,
        document_id=uuid4(),
        headers=["日期", "外供蒸汽占比"],
        title="日总量",
        sheet_index=0,
        external_sheet_id="sheet-a",
        last_synced_at=None,
    )
    snapshot: Any = SimpleNamespace(
        id=snapshot_id,
        header_values=["日期", "外供蒸汽占比"],
    )
    row: Any = SimpleNamespace(
        row_index=3,
        values=[46200, 0.0812227074235808],
        display_values=["2026/06/27", "8%"],
    )

    class FakeRepository:
        async def get_page_binding(self: Any, _page_key: Any, _binding_id: Any) -> Any:
            return SimpleNamespace(sheet_id=sheet_id)

        async def get_latest_snapshot(self: Any, _sheet_id: Any) -> Any:
            return snapshot

        async def list_snapshot_rows(self: Any, **_kwargs: Any) -> Any:
            return [row], 1

        async def get_document_by_id(self: Any, _document_id: Any) -> Any:
            return SimpleNamespace(document_token="book", node_path=[])

    class FakeService:
        repo: Any = FakeRepository()

        async def get_sheet_or_raise(self: Any, _sheet_id: Any) -> Any:
            return sheet

    monkeypatch.setattr("app.modules.energy.api._service", lambda _db: FakeService())

    response = await get_energy_page_records(
        page_key="energy.overview",
        binding_id=binding_id,
        keyword=None,
        page=1,
        page_size=50,
        db=object(),  # type: ignore[arg-type]
    )
    record = json.loads(response.body)["data"]["records"][0]  # type: ignore[arg-type]

    assert record["fields"] == {"日期": "2026/06/27", "外供蒸汽占比": "8%"}
    assert record["normalized_fields"] == {
        "日期": 46200,
        "外供蒸汽占比": 0.0812227074235808,
    }
