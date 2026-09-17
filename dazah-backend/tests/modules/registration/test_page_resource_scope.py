"""A granted registration page must not unlock a different workbook sheet."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.registration.api import project_ledger
from app.modules.registration.models import (
    RegistrationDeclarationProgressWorkbookVersion,
    RegistrationProjectLedgerVersion,
)
from app.modules.registration.repository.declaration_progress_workbook import (
    RegistrationDeclarationProgressWorkbookRepository,
)
from app.modules.registration.repository.project_ledger import (
    RegistrationProjectLedgerRepository,
)
from app.modules.registration.service.project_ledger import ProjectLedgerWorkbookService
from app.platform.identity import deps, page_policy
from app.platform.identity.data_scope import current_page_actor, current_page_key
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput

KEY = "registration:project:project-ledger:international-associated-review"


@pytest.mark.asyncio
async def test_shared_sheet_route_rejects_foreign_sheet_before_reading(monkeypatch):
    app = FastAPI()
    app.include_router(
        project_ledger.router,
        prefix="/api/v1/registration/project-ledger",
        dependencies=[Depends(deps.require_module_view("registration"))],
    )
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    grant = EffectivePageGrantOut(
        page_key=KEY,
        module_code="registration",
        permissions=["access", "query"],
        sensitive_actions=[],
        data_scope=PageDataScopeInput(scope_type="not_applicable"),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    seed = AsyncMock()
    listing = AsyncMock(return_value=[])
    monkeypatch.setattr(ProjectLedgerWorkbookService, "ensure_seeded", seed)
    monkeypatch.setattr(RegistrationProjectLedgerRepository, "list_versions", listing)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/registration/project-ledger/sheets/domestic-associated-review",
            headers={"X-Dazah-Page-Key": KEY},
        )
    assert response.status_code == 403
    listing.assert_not_awaited()
    seed.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,repository,key,own_sheet,foreign_sheet",
    [
        (
            RegistrationProjectLedgerVersion,
            RegistrationProjectLedgerRepository,
            KEY,
            "international-associated-review",
            "domestic-associated-review",
        ),
        (
            RegistrationDeclarationProgressWorkbookVersion,
            RegistrationDeclarationProgressWorkbookRepository,
            "registration:project:declaration-progress:international-planned-in-progress",
            "international-planned-in-progress",
            "domestic-planned-in-progress",
        ),
    ],
)
async def test_project_sheet_scope_covers_group_history_and_deletion(
    db_session, model, repository, key, own_sheet, foreign_sheet
):
    own = model(
        record_group_id=uuid4(),
        sheet_key=own_sheet,
        sheet_name="国际",
        sheet_title="国际",
        source_sequence=1,
        version_number=1,
        values_data={},
    )
    foreign = model(
        record_group_id=uuid4(),
        sheet_key=foreign_sheet,
        sheet_name="国内",
        sheet_title="国内",
        source_sequence=2,
        version_number=1,
        values_data={},
    )
    db_session.add_all([own, foreign])
    await db_session.flush()
    actor = current_page_actor.set(SimpleNamespace(id=uuid4(), role="user"))
    page = current_page_key.set(key)
    try:
        repo = repository(db_session)
        assert own in await repo.list_versions()
        assert foreign not in await repo.list_versions()
        assert await repo.list_versions_by_group(foreign.record_group_id) == []
        assert await repo.get_latest_version_by_group(foreign.record_group_id) is None
        assert await repo.soft_delete_group(foreign.record_group_id) == 0
        assert not foreign.is_deleted
    finally:
        current_page_key.reset(page)
        current_page_actor.reset(actor)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["bulk_import", "sensitive_export"])
async def test_whole_workbook_requires_all_sheets_and_restores_page_scope(
    monkeypatch, action
):
    from app.core.exceptions import ForbiddenException
    from app.modules.registration.page_scope import (
        PREFIXES,
        authorized_workbook,
        family_sheet_keys,
        visible_sheet_keys,
    )

    family = "project-ledger"
    actor = current_page_actor.set(SimpleNamespace(id=uuid4(), role="user"))
    page = current_page_key.set(KEY)
    grants = AsyncMock(return_value=[])
    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    session = AsyncMock()
    try:
        with pytest.raises(ForbiddenException):
            async with authorized_workbook(session, family, action):
                pytest.fail("Partial authorization entered the workbook operation")
        grants.return_value = [
            SimpleNamespace(
                page_key=PREFIXES[family] + sheet,
                permissions=["operate"],
                sensitive_actions=[action],
            )
            for sheet in family_sheet_keys(family)
        ]
        async with authorized_workbook(session, family, action):
            assert await visible_sheet_keys(session, family) == family_sheet_keys(
                family
            )
        assert await visible_sheet_keys(session, family) == {
            "international-associated-review"
        }
    finally:
        current_page_key.reset(page)
        current_page_actor.reset(actor)
