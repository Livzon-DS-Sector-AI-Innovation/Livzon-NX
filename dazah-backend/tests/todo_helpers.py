from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.identity import deps, page_policy, todo_access
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.models import User
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


async def make_todo_user(db: AsyncSession) -> User:
    actor = User(
        id=uuid4(), name=f"待办测试{uuid4().hex[:10]}", role="user", status="active"
    )
    db.add(actor)
    await db.flush()
    return actor


@asynccontextmanager
async def scoped_todo_client(
    db: AsyncSession,
    user: User,
    router: APIRouter,
    module: str,
    key: str,
    scope: DepartmentScope,
    monkeypatch: pytest.MonkeyPatch,
    *,
    operate: bool = True,
    approve: bool = False,
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(
        router,
        prefix=f"/api/v1/{module}",
        dependencies=[Depends(deps.require_module_view(module))],
    )

    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[deps.get_settings] = lambda: type(
        "Settings", (), {"effective_module_access_mode": "all"}
    )()
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    grant = EffectivePageGrantOut(
        page_key=key,
        module_code=module,
        source="user",
        permissions=["access", "query", "operate"] if operate else ["access", "query"],
        sensitive_actions=["approve"] if approve else [],
        data_scope=PageDataScopeInput(scope_type="all"),
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    monkeypatch.setattr(
        todo_access, "resolve_user_department_scope", AsyncMock(return_value=scope)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Dazah-Page-Key": key},
    ) as client:
        yield client
