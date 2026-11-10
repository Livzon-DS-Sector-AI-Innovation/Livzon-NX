from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.identity import rbac, rbac_api
from app.platform.identity.models import Permission, Role, User
from app.platform.identity.repository import RbacRepository

ROLES_URL = "/api/v1/identity/admin/roles"


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
async def role_client(db: AsyncMock) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[rbac_api.require_identity_admin] = lambda: User(
        id=uuid4(), name="测试管理员", role="admin"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_create_role_trims_before_validating_and_saving(
    role_client: AsyncClient, db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "审" * 98 + "2🧪"
    code = "Qa_.:-" + "1" * 58
    role = Role(id=uuid4(), name=name, code=code, is_system=False, grant_version=0)
    lookup = AsyncMock(return_value=None)
    create = AsyncMock(return_value=role)
    monkeypatch.setattr(RbacRepository, "get_role_by_code", lookup)
    monkeypatch.setattr(RbacRepository, "create_role", create)
    monkeypatch.setattr(rbac_api, "_audit", AsyncMock())

    response = await role_client.post(
        ROLES_URL, json={"name": f"\u3000{name} ", "code": f"\t{code}\u0085"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "id": str(role.id),
        "name": name,
        "code": code,
        "description": None,
        "is_system": False,
        "permissions": [],
        "grant_version": 0,
    }
    lookup.assert_awaited_once_with(db, code)
    create.assert_awaited_once_with(db, name=name, code=code, description=None)
    db.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " \t\u3000"),
        ("name", "质量\u3000审核员"),
        ("name", "审" * 101),
        ("code", " \t"),
        ("code", "qa auditor"),
        ("code", "qa\t_auditor"),
        ("code", "质检"),
        ("code", "a" * 65),
    ],
)
async def test_invalid_role_fields_do_not_reach_repository(
    role_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    lookup = AsyncMock()
    monkeypatch.setattr(RbacRepository, "get_role_by_code", lookup)
    payload = {"name": "质量审核员", "code": "qa_auditor", field: value}

    response = await role_client.post(ROLES_URL, json=payload)

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", field]
    lookup.assert_not_awaited()


@pytest.mark.parametrize("found_before_insert", [True, False])
async def test_duplicate_role_code_conflicts_after_trimming(
    role_client: AsyncClient,
    db: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    found_before_insert: bool,
) -> None:
    role = Role(id=uuid4(), name="质量审核员", code="qa_auditor")
    lookup = AsyncMock(return_value=role if found_before_insert else None)
    create = AsyncMock(side_effect=IntegrityError(None, None, ValueError()))
    monkeypatch.setattr(RbacRepository, "get_role_by_code", lookup)
    monkeypatch.setattr(RbacRepository, "create_role", create)

    response = await role_client.post(
        ROLES_URL, json={"name": role.name, "code": f" {role.code} "}
    )

    assert response.status_code == 409, response.text
    assert "已存在" in response.json()["detail"]
    lookup.assert_awaited_once_with(db, role.code)
    db.commit.assert_not_awaited()
    if found_before_insert:
        create.assert_not_awaited()
        db.rollback.assert_not_awaited()
    else:
        db.rollback.assert_awaited_once()


@pytest.mark.parametrize("code_reused", [False, True])
async def test_quality_seed_leaves_deleted_and_reused_codes_unassigned(
    db: AsyncMock, monkeypatch: pytest.MonkeyPatch, code_reused: bool
) -> None:
    seed = rbac.QUALITY_QA_ROLE_SEEDS[0]
    monkeypatch.setattr(rbac, "QUALITY_QA_ROLE_SEEDS", [seed])
    code = seed["code"]
    roles = [Role(id=uuid4(), code=code, is_system=True, is_deleted=True)]
    if code_reused:
        roles.append(Role(id=uuid4(), code=code, is_system=False, is_deleted=False))
    permission_result = Mock()
    permission_result.scalars.return_value.all.return_value = [
        Permission(id=uuid4(), code=seed["permissions"][0])
    ]
    role_result = Mock()
    role_result.scalars.return_value.all.return_value = roles
    db.execute.side_effect = [permission_result, role_result]

    await rbac._seed_quality_qa_roles(db)

    role_query = db.execute.await_args_list[1].args[0]
    assert "is_deleted" not in str(role_query.whereclause)
    db.add.assert_not_called()
    db.flush.assert_not_awaited()
