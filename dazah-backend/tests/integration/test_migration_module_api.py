"""Real HTTP acceptance checks for the migrated modules."""

from collections.abc import AsyncIterator
from importlib import import_module
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.database import get_db
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

app: FastAPI = cast(FastAPI, getattr(import_module("app.main"), "app"))


def _user(*, role: str) -> User:
    return User(
        id=uuid4(),
        name="迁移接口验收用户",
        username=f"migration-api-{uuid4().hex[:12]}",
        role=role,
        status="active",
        auth_source="local",
    )


@pytest.mark.anyio
async def test_migrated_read_routes_work_through_real_async_client(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """The representative old and new read paths must not be route-only mocks."""
    admin = _user(role="admin")
    db_session.add(admin)
    await db_session.flush()

    original_db_override = app.dependency_overrides.get(get_db)

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    paths = (
        "/api/v1/hr/onboarding-records?page=1&page_size=20",
        "/api/v1/hr/departure-records?page=1&page_size=20",
        "/api/v1/hr/new/employees?page=1&page_size=20",
        "/api/v1/quality/oos-oot/records?page=1&page_size=20&keyword=missing",
        "/api/v1/registration/knowledge/articles?page=1&page_size=20",
        "/api/v1/warehouse/feishu-config",
        "/api/v1/identity/users?page=1&page_size=20",
    )

    try:
        for path in paths:
            response = await client.get(path)
            assert response.status_code == 200, (
                f"{path} returned {response.status_code}: {response.text}"
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if original_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_db_override


@pytest.mark.anyio
async def test_migrated_routes_enforce_auth_for_all_module_boundaries(
    client: AsyncClient,
) -> None:
    paths = (
        "/api/v1/hr/new/employees",
        "/api/v1/quality/oos-oot/records",
        "/api/v1/registration/knowledge/articles",
        "/api/v1/warehouse/feishu-config",
        "/api/v1/identity/users",
    )

    for path in paths:
        response = await client.get(path)
        assert response.status_code == 401, (
            f"{path} unexpectedly returned {response.status_code}"
        )


@pytest.mark.anyio
async def test_system_boundary_forbids_regular_user_and_validates_notice_input(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    regular_user = _user(role="user")
    db_session.add(regular_user)
    await db_session.flush()
    original_db_override = app.dependency_overrides.get(get_db)

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: regular_user

    try:
        forbidden = await client.get("/api/v1/identity/users")
        assert forbidden.status_code == 403

        admin = _user(role="admin")
        db_session.add(admin)
        await db_session.flush()
        app.dependency_overrides[get_current_user] = lambda: admin
        invalid_notice = await client.post(
            f"/api/v1/hr/candidates/{uuid4()}/send-notice",
            json={"scene_code": "unsupported"},
        )
        assert invalid_notice.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if original_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_db_override


@pytest.mark.anyio
async def test_registration_upload_rolls_back_object_when_article_is_missing(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _user(role="admin")
    db_session.add(admin)
    await db_session.flush()

    stored: list[tuple[object, ...]] = []
    deleted: list[tuple[object, ...]] = []
    monkeypatch.setattr(storage, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage,
        "upload_object",
        lambda *args, **kwargs: stored.append(args),
    )
    monkeypatch.setattr(
        storage,
        "delete_object",
        lambda *args, **kwargs: deleted.append(args),
    )

    original_db_override = app.dependency_overrides.get(get_db)

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await client.post(
            f"/api/v1/registration/knowledge/articles/{uuid4()}/attachments",
            files={
                "file": (
                    "missing-article.pdf",
                    b"%PDF-1.7\nrollback-test",
                    "application/pdf",
                )
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if original_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_db_override

    assert response.status_code == 404
    assert len(stored) == 1
    assert len(deleted) == 1
    assert stored[0][1] == deleted[0][1]
