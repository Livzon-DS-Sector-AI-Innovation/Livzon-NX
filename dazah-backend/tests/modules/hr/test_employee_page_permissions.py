import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.hr import api
from app.modules.hr.models import Employee
from app.modules.hr.page_access import (
    EMPLOYEE_PAGE_KEY,
    assert_employee_department,
    employee_page_scope,
)
from app.modules.hr.repository import EmployeeRepository
from app.modules.hr.service import EmployeeService
from app.platform.audit.models import AuditLog
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)
from app.platform.identity.deps import get_current_user, require_module_view
from app.platform.identity.models import Department, User
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    api_binding_for_route,
    page_api_catalog_gaps,
)
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.fixture(autouse=True)
def page_context():
    key = current_page_key.set(None)
    actor = current_page_actor.set(None)
    scope = current_page_data_scope.set(None)
    yield
    current_page_key.reset(key)
    current_page_actor.reset(actor)
    current_page_data_scope.reset(scope)


def _app(db, user, service):
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/hr",
        dependencies=[Depends(require_module_view("hr"))],
    )
    app.dependency_overrides[get_db] = lambda: db
    # These tests isolate page grants; module-level access is covered by the
    # identity permission test suite and must not short-circuit page checks.
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[api.get_employee_service] = lambda: service
    return app


def _grant(department_ids, permissions=None, actions=None):
    return EffectivePageGrantOut(
        page_key=EMPLOYEE_PAGE_KEY,
        module_code="hr",
        permissions=permissions
        if permissions is not None
        else ["access", "query", "operate"],
        sensitive_actions=actions if actions is not None else ["delete", "sync_config"],
        data_scope=PageDataScopeInput(
            scope_type="departments", department_ids=department_ids
        ),
        source="user",
    )


def _publish_fixture(monkeypatch, grant):
    # Simulate grant facts only; real routes, scope resolution and SQL run below.
    monkeypatch.setattr(
        PagePermissionRepository,
        "get_rollout",
        AsyncMock(return_value=SimpleNamespace(status="enforced")),
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )


@pytest.mark.asyncio
async def test_employee_http_crud_stats_and_sync_share_real_department_scope(
    db_session, monkeypatch
):
    suffix = uuid4().hex[:10]
    own_name, other_name, child_name = (
        f"测试-{name}-{suffix}" for name in ("本部", "其他", "下级")
    )
    own_id = "od-own-" + suffix
    db_session.add_all(
        [
            Department(feishu_department_id=own_id, name=own_name),
            Department(feishu_department_id="od-other-" + suffix, name=other_name),
            Department(
                feishu_department_id="od-child-" + suffix,
                name=child_name,
                parent_feishu_department_id=own_id,
            ),
        ]
    )
    actor = User(
        name="权限经办人",
        username="hr-page-" + suffix,
        role="user",
        status="active",
        auth_source="local",
    )
    own = Employee(
        name="范围内员工",
        employee_number="own-" + suffix,
        department="总部门",
        sub_department=own_name,
        position="操作工",
        status="在职",
        feishu_record_id="test-r1",
    )
    other = Employee(
        name="范围外员工",
        employee_number="other-" + suffix,
        department=own_name,
        sub_department=other_name,
        position="操作工",
        status="在职",
    )
    child = Employee(
        name="下级员工",
        employee_number="child-" + suffix,
        department=own_name,
        sub_department=child_name,
        position="操作工",
        status="在职",
    )
    db_session.add_all([actor, own, other, child])
    for employee in (own, other, child):
        employee.hire_date = date(2026, 1, 1)
    await db_session.flush()
    grant = _grant([own_id])
    _publish_fixture(monkeypatch, grant)
    service = EmployeeService(db_session)
    external = SimpleNamespace(
        create=AsyncMock(return_value="test-created"), delete=AsyncMock()
    )
    monkeypatch.setattr(service, "_get_bitable", AsyncMock(return_value=external))
    monkeypatch.setattr(
        service, "_sync_single_to_feishu", AsyncMock(return_value="test-synced")
    )
    app = _app(db_session, actor, service)
    base = "/api/v1/hr/employees"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Dazah-Page-Key": EMPLOYEE_PAGE_KEY},
    ) as client:
        response = await client.get(base)
        assert response.status_code == 200, response.text
        assert {row["id"] for row in response.json()["data"]} == {
            str(own.id),
            str(child.id),
        }
        assert response.json()["meta"]["total"] == 2
        stats = await client.get(base + "/stats")
        assert stats.status_code == 200
        assert stats.json()["data"]["total"] == 2
        filtered = await client.get(base, params={"department": own_name})
        assert [row["id"] for row in filtered.json()["data"]] == [str(own.id)]
        assert (
            await client.get(base, params={"department": other_name})
        ).status_code == 403
        assert (
            await client.get(f"{base}/by-number/{own.employee_number}")
        ).status_code == 200
        assert (
            await client.get(f"{base}/by-number/{other.employee_number}")
        ).status_code == 403
        for method in ("GET", "PUT", "DELETE"):
            denied = await client.request(
                method,
                f"{base}/{other.id}",
                json={"position": "越权修改"} if method == "PUT" else None,
            )
            assert denied.status_code == 403, denied.text
        assert (
            await client.post(f"{base}/{other.id}/sync-to-feishu")
        ).status_code == 403
        denied_create = await client.post(
            base,
            json={
                "name": "越权新建",
                "department": other_name,
                "position": "岗位",
                "hire_date": "2026-01-01",
            },
        )
        assert denied_create.status_code == 403
        moved = await client.put(
            f"{base}/{own.id}", json={"sub_department": other_name}
        )
        assert moved.status_code == 403
        assert own.sub_department == own_name
        for payload in ({"status": "离职"}, {"contract_opinion": "不续签"}):
            assert (
                await client.put(f"{base}/{own.id}", json=payload)
            ).status_code == 403
        assert own.status == "在职" and own.contract_opinion is None
        external.create.assert_not_awaited()
        service._sync_single_to_feishu.assert_not_awaited()
        external.delete.assert_not_awaited()
        updated = await client.put(
            f"{base}/{own.id}",
            json={"position": "新岗位", "status": "在职", "contract_opinion": None},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["position"] == "新岗位"
        created = await client.post(
            base,
            json={
                "name": "范围内新建",
                "employee_number": "created-" + suffix,
                "department": own_name,
                "position": "岗位",
                "hire_date": "2026-01-01",
            },
        )
        assert created.status_code == 201, created.text
        assert (await client.post(f"{base}/{own.id}/sync-to-feishu")).status_code == 200
        assert (await client.delete(f"{base}/{own.id}")).status_code == 200
        assert own.is_deleted
        assert not other.is_deleted and other.position == "操作工"
        # Incomplete employee routes must not inherit broad CRUD permission.
        assert (await client.get(base + "/max-seq")).status_code == 403
    audits = list(
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.user_id == actor.id)
            )
        ).scalars()
    )
    assert {row.action for row in audits} == {
        "创建员工档案",
        "修改员工档案",
        "删除员工档案",
        "同步员工档案",
    }
    assert all(row.extra["page_key"] == EMPLOYEE_PAGE_KEY for row in audits)
    assert all(
        "范围内员工" not in json.dumps(row.extra, ensure_ascii=False) for row in audits
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "suffix", "permissions", "actions", "expected"),
    [
        ("GET", "", ["access"], [], 403),
        ("PUT", "/00000000-0000-0000-0000-000000000001", ["access", "query"], [], 403),
        (
            "DELETE",
            "/00000000-0000-0000-0000-000000000001",
            ["access", "query", "operate"],
            [],
            403,
        ),
        (
            "POST",
            "/00000000-0000-0000-0000-000000000001/sync-to-feishu",
            ["access", "query", "operate"],
            [],
            403,
        ),
    ],
)
async def test_employee_http_permissions_fail_before_service(
    monkeypatch, method, suffix, permissions, actions, expected
):
    service = SimpleNamespace(
        session=None,
        get_employee=AsyncMock(),
        update_employee=AsyncMock(),
        delete_employee=AsyncMock(),
        sync_to_feishu=AsyncMock(),
    )
    _publish_fixture(monkeypatch, _grant(["test-dept"], permissions, actions))
    app = _app(None, SimpleNamespace(id=uuid4(), role="user"), service)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            "/api/v1/hr/employees" + suffix,
            headers={"X-Dazah-Page-Key": EMPLOYEE_PAGE_KEY},
            json={} if method == "PUT" else None,
        )
    assert response.status_code == expected
    service.get_employee.assert_not_awaited()
    service.update_employee.assert_not_awaited()
    service.delete_employee.assert_not_awaited()
    service.sync_to_feishu.assert_not_awaited()


def test_employee_policy_is_reviewed_but_hr_publish_gate_remains_closed():
    assert api_binding_for_route("GET", "/api/v1/hr/employees").page_keys == (
        EMPLOYEE_PAGE_KEY,
    )
    assert (
        api_binding_for_route(
            "DELETE", "/api/v1/hr/employees/{employee_id}"
        ).sensitive_action
        == "delete"
    )
    assert page_api_catalog_gaps("hr")


@pytest.mark.parametrize(
    ("department", "sub_department", "allowed"),
    [
        ("本部门", None, True),
        (" 本部门 ", "  ", True),
        ("其他部门", " 本部门 ", True),
        ("本部门", "其他部门", False),
        (None, None, False),
    ],
)
def test_employee_scope_uses_most_specific_nonblank_department(
    department, sub_department, allowed
):
    scope = DepartmentScope(department_names={"本部门"})
    if allowed:
        assert_employee_department(scope, department, sub_department)
    else:
        with pytest.raises(HTTPException) as exc:
            assert_employee_department(scope, department, sub_department)
        assert exc.value.status_code == 403
    assert_employee_department(None, department, sub_department)
    assert_employee_department(DepartmentScope(is_all=True), department, sub_department)


@pytest.mark.asyncio
async def test_employee_scope_requires_trusted_page_and_actor(monkeypatch):
    assert await employee_page_scope(None) is None
    current_page_key.set("hr:unreviewed")
    with pytest.raises(HTTPException) as exc:
        await employee_page_scope(None)
    assert exc.value.status_code == 403
    current_page_key.set(EMPLOYEE_PAGE_KEY)
    with pytest.raises(HTTPException) as exc:
        await employee_page_scope(None)
    assert exc.value.status_code == 403
    current_page_actor.set(SimpleNamespace(id=uuid4()))
    resolver = AsyncMock(return_value=DepartmentScope())
    monkeypatch.setattr(
        "app.modules.hr.page_access.resolve_user_department_scope", resolver
    )
    with pytest.raises(HTTPException) as exc:
        await employee_page_scope(None)
    assert exc.value.status_code == 403
    resolver.return_value = DepartmentScope(is_all=True)
    assert (await employee_page_scope(None)).is_all


@pytest.mark.asyncio
async def test_employee_write_lookup_locks_and_refreshes_existing_identity():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    await EmployeeRepository(session).get_by_id(uuid4(), for_update=True)
    statement = session.execute.call_args.args[0]
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))
    assert statement.get_execution_options()["populate_existing"] is True


def test_employee_risky_actions_have_concrete_chinese_business_labels():
    labels = {
        action.key: action.name
        for action in PAGES_BY_KEY[EMPLOYEE_PAGE_KEY].sensitive_actions
    }
    assert labels["delete"] == "删除员工档案"
    assert labels["sync_config"] == "同步员工档案至飞书"
