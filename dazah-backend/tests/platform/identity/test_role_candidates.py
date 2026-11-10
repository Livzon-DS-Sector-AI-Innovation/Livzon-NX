from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.identity import rbac_api
from app.platform.identity.models import User
from app.platform.identity.repository import RbacRepository, UserRepository


@pytest.fixture
async def candidate_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    application = FastAPI()
    application.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    application.dependency_overrides[get_db] = lambda: AsyncMock(spec=AsyncSession)
    application.dependency_overrides[rbac_api.require_identity_admin] = lambda: User(
        id=uuid4()
    )
    user = User(
        id=uuid4(),
        name="待补全部门用户",
        department=None,
        role="user",
        status="active",
        auth_source="feishu",
        grant_version=0,
    )
    monkeypatch.setattr(
        UserRepository, "list_role_candidates", AsyncMock(return_value=([user], 1))
    )
    monkeypatch.setattr(RbacRepository, "list_user_roles", AsyncMock(return_value=[]))
    async with AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.parametrize(
    "params",
    [
        {"department_id": "od-1", "user_scope": "department"},
        {"department_name": "质量部", "user_scope": "department"},
        {"user_scope": "missing"},
        {"user_scope": "all", "keyword": "张"},
    ],
)
async def test_candidates_serialize_missing_department(
    candidate_client: AsyncClient, params: dict[str, str]
) -> None:
    response = await candidate_client.get("/api/v1/identity/admin/users", params=params)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["department"] is None
    assert data["items"][0]["roles"] == []
    kwargs = UserRepository.list_role_candidates.call_args.kwargs
    assert kwargs["user_scope"] == params["user_scope"]
    assert kwargs["department_id"] == params.get("department_id")
    assert kwargs["department_name"] == params.get("department_name")


@pytest.mark.parametrize(
    "params",
    [
        {"user_scope": "department"},
        {"user_scope": "department", "department_name": "   "},
        {"user_scope": "invalid"},
        {"user_scope": "all", "limit": "501"},
    ],
)
async def test_candidates_validate_filters(
    candidate_client: AsyncClient, params: dict[str, str]
) -> None:
    response = await candidate_client.get("/api/v1/identity/admin/users", params=params)
    assert response.status_code == 422
    UserRepository.list_role_candidates.assert_not_awaited()


@pytest.mark.parametrize("query", ["", "?user_scope=all"])
async def test_candidates_require_admin(query: str) -> None:
    from fastapi import HTTPException

    application = FastAPI()
    application.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")

    def denied() -> None:
        raise HTTPException(403, "需要 identity:admin 权限")

    application.dependency_overrides[rbac_api.require_identity_admin] = denied
    application.dependency_overrides[get_db] = lambda: AsyncMock(spec=AsyncSession)
    async with AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/identity/admin/users{query}")
    assert response.status_code == 403


async def test_user_roles_search_directory_fields_before_paging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = FastAPI()
    application.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    db = AsyncMock(spec=AsyncSession)
    user = User(
        id=uuid4(),
        name="后页用户",
        username="qa_account",
        role="user",
        status="disabled",
        auth_source="local",
        grant_version=3,
    )
    rows = Mock()
    rows.all.return_value = [user]
    rows.scalars.return_value = rows
    db.execute.return_value = rows
    db.scalar.return_value = 501
    db.scalars.return_value = rows
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[rbac_api.require_identity_admin] = lambda: User(
        id=uuid4()
    )
    monkeypatch.setattr(RbacRepository, "list_user_roles", AsyncMock(return_value=[]))

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/identity/admin/users",
            params={"keyword": "  QA_ACCOUNT  ", "offset": 500, "limit": 20},
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 501
    assert data["items"][0]["id"] == str(user.id)
    assert data["items"][0]["grant_version"] == 3
    assert data["items"][0]["status"] == "disabled"
    assert data["items"][0]["roles"] == []

    count_sql = str(db.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    page = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    conditions = str(page).split("WHERE ")[1].split(" ORDER BY")[0]
    assert count_sql.split("WHERE ")[1] == conditions
    assert "users.is_deleted IS false" in conditions
    for field in ("name", "username", "email", "mobile", "employee_no", "department"):
        assert f"users.{field} ILIKE" in conditions
    assert "users.status" not in conditions
    assert "ORDER BY identity.users.name, identity.users.id" in str(page)
    assert list(page.params.values()) == ["%QA_ACCOUNT%"] * 6 + [20, 500]


@pytest.mark.parametrize("scope", ["department", "missing", "all"])
async def test_candidate_query_matches_full_ids_and_counts_same_filter(
    scope: str,
) -> None:
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = 1
    user = User(id=uuid4(), name="候选人")
    rows = Mock()
    rows.all.return_value = [user]
    departments = Mock()
    departments.all.return_value = ["od-from-directory"]
    db.scalars.side_effect = [departments, rows] if scope == "department" else [rows]
    users, total = await UserRepository().list_role_candidates(
        db,
        department_id="od-1",
        department_name="质量部",
        user_scope=scope,
        keyword="张",
        offset=20,
        limit=20,
    )
    assert users == [user]
    assert total == 1

    def sql(statement: object) -> str:
        return str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )

    count_sql = sql(db.scalar.call_args.args[0])
    page_sql = sql(db.scalars.call_args.args[0])
    assert (
        count_sql.split("WHERE ")[1]
        == page_sql.split("WHERE ")[1].split(" ORDER BY")[0]
    )
    assert "LIMIT 20 OFFSET 20" in page_sql
    if scope == "department":
        assert "'\"od-1\"'" in page_sql
        assert "'\"od-from-directory\"'" in page_sql
        assert "质量部" in page_sql
    elif scope == "missing":
        assert "trim(coalesce(" in page_sql
    else:
        assert "od-1" not in page_sql
