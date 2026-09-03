"""Department rule routes must serialize ORM records, including after creation."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.identity import rbac_api
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import DepartmentRoleRule, Role, User
from app.platform.identity.repository import RbacRepository


@pytest.fixture
def rule() -> DepartmentRoleRule:
    return DepartmentRoleRule(
        id=uuid4(),
        role_id=uuid4(),
        feishu_department_id="od-test-quality",
        department_name="质量管理部",
    )


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def route_app(db: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    application.dependency_overrides[get_db] = lambda: db
    actor = User(
        id=uuid4(), name="测试管理员", role="admin", status="active", is_deleted=False
    )
    db.scalar.return_value = actor
    application.dependency_overrides[get_current_user] = lambda: actor
    return application


@pytest.fixture
async def rule_client(route_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=route_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.parametrize("role_exists", [True, False])
async def test_list_serializes_orm_rule(
    rule_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    rule: DepartmentRoleRule,
    role_exists: bool,
) -> None:
    monkeypatch.setattr(
        RbacRepository, "list_dept_rules", AsyncMock(return_value=[rule])
    )
    role = Role(id=rule.role_id, name="质量审核员", code="quality_reviewer")
    monkeypatch.setattr(
        RbacRepository,
        "get_role_by_id",
        AsyncMock(return_value=role if role_exists else None),
    )

    response = await rule_client.get("/api/v1/identity/admin/dept-rules")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == [
        {
            "id": str(rule.id),
            "role_id": str(rule.role_id),
            "feishu_department_id": "od-test-quality",
            "department_name": "质量管理部",
            "role_name": "质量审核员" if role_exists else None,
            "role_code": "quality_reviewer" if role_exists else None,
        }
    ]


async def test_list_empty_rules(
    rule_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(RbacRepository, "list_dept_rules", AsyncMock(return_value=[]))
    response = await rule_client.get("/api/v1/identity/admin/dept-rules")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize("selector", ["feishu_department_id", "department_name"])
async def test_create_serializes_orm_rule_after_commit(
    rule_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    db: AsyncMock,
    rule: DepartmentRoleRule,
    selector: str,
) -> None:
    role = Role(id=rule.role_id, name="质量审核员", code="quality_reviewer")
    monkeypatch.setattr(RbacRepository, "get_role_by_id", AsyncMock(return_value=role))
    if selector == "feishu_department_id":
        rule.department_name = None
    else:
        rule.feishu_department_id = None
    create = AsyncMock(return_value=rule)
    monkeypatch.setattr(RbacRepository, "create_dept_rule", create)
    monkeypatch.setattr(rbac_api, "_bump_all_user_grant_versions", AsyncMock())
    monkeypatch.setattr(rbac_api, "_audit", AsyncMock())
    publish = AsyncMock()
    monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", publish)

    response = await rule_client.post(
        "/api/v1/identity/admin/dept-rules",
        json={"role_id": str(rule.role_id), selector: getattr(rule, selector)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "id": str(rule.id),
        "role_id": str(rule.role_id),
        "feishu_department_id": rule.feishu_department_id,
        "department_name": rule.department_name,
        "role_name": role.name,
        "role_code": role.code,
    }
    create.assert_awaited_once_with(
        db,
        role_id=rule.role_id,
        feishu_department_id=rule.feishu_department_id,
        department_name=rule.department_name,
    )
    db.commit.assert_awaited_once()
    publish.assert_awaited_once()


async def test_create_requires_department_selector(
    rule_client: AsyncClient, db: AsyncMock
) -> None:
    response = await rule_client.post(
        "/api/v1/identity/admin/dept-rules", json={"role_id": str(uuid4())}
    )
    assert response.status_code == 422
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("user_role, expected_status", [(None, 401), ("user", 403)])
async def test_rules_require_admin(
    rule_client: AsyncClient,
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    user_role: str | None,
    expected_status: int,
) -> None:
    route_app.dependency_overrides[get_current_user] = lambda: (
        User(id=uuid4(), name="测试用户", role=user_role) if user_role else None
    )
    monkeypatch.setattr(
        rbac_api, "resolve_user_permissions", AsyncMock(return_value=set())
    )
    list_rules = AsyncMock()
    monkeypatch.setattr(RbacRepository, "list_dept_rules", list_rules)
    response = await rule_client.get("/api/v1/identity/admin/dept-rules")
    assert response.status_code == expected_status
    list_rules.assert_not_awaited()
