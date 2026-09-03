from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.warehouse import api, page_access
from app.modules.warehouse.feishu_material_pages import FEISHU_WAREHOUSE_MATERIAL_PAGES
from app.modules.warehouse.service import HARDWARE_DEPT_PAGE_KEYS, WarehouseService
from app.platform.identity import deps
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    WAREHOUSE_DEPARTMENT_DATA_PAGES,
    WAREHOUSE_MATERIAL_PAGE_ALIASES,
    api_binding_for_route,
    page_api_catalog_gaps,
)
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput

DATA_PAGE = "hardware-101-1-workshop"
PAGE = "warehouse:hardware:hardware-" + DATA_PAGE


@pytest.fixture(autouse=True)
def clean_page_context():
    key = current_page_key.set(None)
    actor = current_page_actor.set(None)
    scope = current_page_data_scope.set(None)
    yield
    current_page_key.reset(key)
    current_page_actor.reset(actor)
    current_page_data_scope.reset(scope)


def _service():
    instance = WarehouseService.__new__(WarehouseService)
    config = SimpleNamespace(
        page_key=DATA_PAGE,
        title="车间物料",
        app_token="test-base",
        table_id="test-table",
    )
    instance.repo = SimpleNamespace(session=None)
    instance._page_cache = {}
    instance._field_meta_cache = {}
    instance._get_material_page_config = AsyncMock(return_value=config)
    instance._get_page_field_meta = AsyncMock(
        return_value=[
            {"field_name": "车间", "type": 1},
            {"field_name": "物料名称", "type": 1},
        ]
    )
    instance._build_page_option_map = AsyncMock(return_value={})
    instance.feishu_client = SimpleNamespace(
        request=AsyncMock(
            return_value={
                "record": {
                    "record_id": "r1",
                    "fields": {"车间": "一车间", "物料名称": "螺栓"},
                }
            }
        )
    )
    instance._get_feishu_client = AsyncMock(return_value=instance.feishu_client)
    external = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                {"record": {"record_id": "r1"}},
                {},
            ]
        ),
    )
    instance._get_material_client = AsyncMock(return_value=external)
    instance._invalidate_page_cache = Mock()
    return instance, config, external


def test_material_page_catalog_matches_real_pages_and_scope_capabilities():
    assert set(WAREHOUSE_MATERIAL_PAGE_ALIASES) <= set(PAGES_BY_KEY)
    assert set(WAREHOUSE_MATERIAL_PAGE_ALIASES.values()) <= set(
        FEISHU_WAREHOUSE_MATERIAL_PAGES
    )
    assert WAREHOUSE_DEPARTMENT_DATA_PAGES == HARDWARE_DEPT_PAGE_KEYS
    for key, alias in WAREHOUSE_MATERIAL_PAGE_ALIASES.items():
        definition = PAGES_BY_KEY[key]
        assert ("department_tree" in definition.supported_scope_types) == (
            alias in HARDWARE_DEPT_PAGE_KEYS
        )
        assert {"delete", "sync_config"} <= {
            action.key for action in definition.sensitive_actions
        }
    binding = api_binding_for_route(
        "DELETE", "/api/v1/warehouse/material-pages/{page_key}/records/{record_id}"
    )
    assert binding.sensitive_action == "delete"
    assert binding.permission == "operate"
    # Partial adaptation must not silently make the whole warehouse publishable.
    assert page_api_catalog_gaps("warehouse")


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["local", "feishu", "fallback"])
async def test_material_list_scopes_rows_count_stats_and_shared_cache(source):
    instance, config, _ = _service()
    rows = [
        {"车间": "一车间", "物料名称": "螺栓", "结存量": 10, "__record_id": "r1"},
        {"车间": "二车间", "物料名称": "螺母", "结存量": 20, "__record_id": "r2"},
    ]
    snapshot = SimpleNamespace(
        id=uuid4(),
        page_key=DATA_PAGE,
        page_title="车间物料",
        table_name="物料",
        columns=[{"key": "车间", "title": "车间", "field_type": 1}],
        last_synced_at=datetime.now(UTC),
    )
    instance.repo.get_material_page_snapshot = AsyncMock(return_value=snapshot)
    instance.repo.list_material_page_rows = AsyncMock(
        return_value=(
            [
                SimpleNamespace(cells=row, source_record_id=row["__record_id"])
                for row in rows
            ],
            2,
        )
    )
    instance._resolve_material_page_source = AsyncMock(
        return_value="local" if source == "local" else "feishu"
    )
    instance.fetch_material_page_from_feishu = AsyncMock(
        return_value=(config, [], rows, {})
    )
    if source == "fallback":
        instance.fetch_material_page_from_feishu.side_effect = RuntimeError(
            "offline test"
        )
    for department, record in (("一车间", "r1"), ("二车间", "r2")):
        result = await instance.get_feishu_material_page(
            DATA_PAGE, scope=DepartmentScope(department_names={department})
        )
        assert result.total == 1
        assert len(result.rows) == 1
        assert result.rows[0]["__record_id"] == record
        assert result.stats["total"] == 1
        assert result.stats["stock_count"] == 1
    assert len(rows) == 2  # Shared unfiltered cache must not be mutated per user.


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("authorized_department", [True, False])
async def test_http_record_scope_denies_outside_department_before_write(
    monkeypatch, method, authorized_department
):
    instance, _, external = _service()
    actor = SimpleNamespace(id=uuid4(), role="user")
    scope = DepartmentScope(
        department_names={"一车间" if authorized_department else "二车间"}
    )
    grant = EffectivePageGrantOut(
        page_key=PAGE,
        module_code="warehouse",
        permissions=["access", "query", "operate"],
        sensitive_actions=["delete"],
        data_scope=PageDataScopeInput(),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionRepository,
        "get_rollout",
        AsyncMock(return_value=SimpleNamespace(status="enforced")),
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    monkeypatch.setattr(
        page_access, "resolve_user_department_scope", AsyncMock(return_value=scope)
    )
    monkeypatch.setattr(
        api, "resolve_user_department_scope", AsyncMock(return_value=scope)
    )
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/warehouse",
        dependencies=[Depends(deps.require_module_view("warehouse"))],
    )
    app.dependency_overrides[deps.get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    app.dependency_overrides[api.get_warehouse_service] = lambda: instance
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            f"/api/v1/warehouse/material-pages/{DATA_PAGE}/records/r1",
            headers={"X-Dazah-Page-Key": PAGE},
            json={"fields": {"物料名称": "新名称"}} if method == "PUT" else None,
        )
        assert response.status_code == (200 if authorized_department else 403)
        if not authorized_department:
            assert "部门范围" in response.json()["detail"]
        # Same interface, different data-page alias: always forbidden.
        forged = await client.request(
            method,
            "/api/v1/warehouse/material-pages/raw-summary/records/r1",
            headers={"X-Dazah-Page-Key": PAGE},
            json={"fields": {"物料名称": "新名称"}} if method == "PUT" else None,
        )
        assert forged.status_code == 403
    assert external.request.await_count == int(
        authorized_department and method in {"PUT", "DELETE"}
    )


@pytest.mark.asyncio
async def test_restricted_writer_cannot_move_record_to_another_department():
    instance, _, external = _service()
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await instance.update_material_page_record(
            DATA_PAGE,
            "r1",
            {"车间": "二车间"},
            scope=DepartmentScope(department_names={"一车间"}),
        )
    assert error.value.status_code == 403
    external.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_restricted_writer_can_submit_unchanged_department():
    instance, _, external = _service()
    result = await instance.update_material_page_record(
        DATA_PAGE,
        "r1",
        {"车间": "一车间", "物料名称": "新名称"},
        scope=DepartmentScope(department_names={"一车间"}),
    )
    assert result["record_id"] == "r1"
    external.request.assert_awaited_once_with(
        "PUT",
        "/bitable/v1/apps/test-base/tables/test-table/records/r1",
        json_body={"fields": {"车间": "一车间", "物料名称": "新名称"}},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("anonymous", 401),
        ("no_context", 400),
        ("access_only", 403),
        ("read_only_write", 403),
        ("delete_without_action", 403),
        ("refresh_without_action", 403),
        ("foreign_list", 403),
        ("empty_scope", 403),
        ("foreign_filter", 403),
    ],
)
async def test_http_access_and_sensitive_gates_prevent_business_reads(
    monkeypatch, case, expected
):
    instance, _, external = _service()
    actor = SimpleNamespace(id=uuid4(), role="user")
    grant = EffectivePageGrantOut(
        page_key=PAGE,
        module_code="warehouse",
        permissions=["access"]
        if case == "access_only"
        else (
            ["access", "query"]
            if case == "read_only_write"
            else ["access", "query", "operate"]
        ),
        sensitive_actions=[],
        data_scope=PageDataScopeInput(),
        source="user",
    )
    scope = DepartmentScope(
        department_names=set() if case == "empty_scope" else {"一车间"}
    )
    monkeypatch.setattr(
        PagePermissionRepository,
        "get_rollout",
        AsyncMock(return_value=SimpleNamespace(status="enforced")),
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    monkeypatch.setattr(
        page_access, "resolve_user_department_scope", AsyncMock(return_value=scope)
    )
    monkeypatch.setattr(
        api, "resolve_user_department_scope", AsyncMock(return_value=scope)
    )
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/warehouse",
        dependencies=[Depends(deps.require_module_view("warehouse"))],
    )
    app.dependency_overrides[deps.get_current_user] = lambda: (
        None if case == "anonymous" else actor
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    app.dependency_overrides[api.get_warehouse_service] = lambda: instance
    method = (
        "DELETE"
        if case == "delete_without_action"
        else "PUT"
        if case == "read_only_write"
        else "GET"
    )
    path = "/api/v1/warehouse/material-pages/" + (
        "raw-summary" if case == "foreign_list" else DATA_PAGE
    )
    if method != "GET":
        path += "/records/r1"
    if case == "refresh_without_action":
        path += "?force=true"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            path,
            params={"filters": '[{"field":"车间","operator":"eq","value":"二车间"}]'}
            if case == "foreign_filter"
            else None,
            headers={} if case == "no_context" else {"X-Dazah-Page-Key": PAGE},
            json={"fields": {"物料名称": "修改"}} if method == "PUT" else None,
        )
    assert response.status_code == expected, response.text
    instance.feishu_client.request.assert_not_awaited()
    instance._get_material_page_config.assert_not_awaited()
    external.request.assert_not_awaited()
