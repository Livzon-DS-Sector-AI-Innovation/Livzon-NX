import uuid
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.catalog import ToolCatalogService
from app.modules.agent.models import AgentToolCatalog
from app.modules.agent.schemas import AgentToolExecuteRequest, AgentToolSearchRequest
from app.modules.agent.tools import ToolExecutor, tool_registry
from app.platform.identity.models import User

SimpleNamespace: Any = _SimpleNamespace


def _user(*, status_value: str = "active") -> User:
    return User(
        name="Catalog User",
        username=f"catalog-{uuid.uuid4().hex}",
        role="user",
        status=status_value,
        auth_source="local",
        tenant_key="local",
    )


def _request(
    user_id: uuid.UUID,
    *,
    query: str = "",
    module: str | None = None,
    limit: int = 12,
) -> AgentToolSearchRequest:
    return AgentToolSearchRequest.model_validate(
        {
            "query": query,
            "module": module,
            "limit": limit,
            "subject": {
                "tenant_id": "local",
                "user_id": user_id,
                "source": "internal",
            },
        }
    )


class ConfigurableAccessScope:
    def __init__(
        self: Any,
        *,
        denied: set[str] | None = None,
        error_status: int | None = None,
    ) -> None:
        self.denied = denied or set()
        self.error_status = error_status

    async def require_tool_access(
        self: Any, db: Any, *, tool_name: str, **kwargs: Any
    ) -> Any:
        if self.error_status is not None:
            raise HTTPException(self.error_status, "scope unavailable")
        if tool_name in self.denied:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "denied")
        return None


@pytest.mark.anyio
async def test_access_scope_selects_workflow_tool_allowlist() -> None:
    service = AgentAccessScopeService()

    async def current_scope(db: Any, *, user: Any) -> Any:
        return SimpleNamespace(
            tool_names=[],
            workflow_tool_names=["quality.list_deviations"],
        )

    service.get_current_scope = current_scope  # type: ignore[assignment, method-assign]
    snapshot = await service.require_tool_access(
        None,  # type: ignore[arg-type]
        user=SimpleNamespace(),
        tool_name="quality.list_deviations",
        module="quality",
        for_workflow=True,
    )

    assert snapshot.workflow_tool_names == ["quality.list_deviations"]  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_synchronize_creates_updates_and_disables_stale_rows(
    db_session: AsyncSession,
) -> None:
    stale = AgentToolCatalog(
        operation="removed.tool",
        module="removed",
        capability_version="0",
        summary="removed",
        status="active",
        risk_level="low",
        write=False,
        confirmation_required=False,
        input_schema={},
        output_schema={},
        timeout_seconds=1,
        idempotent=True,
        metadata_hash="stale",
    )
    db_session.add(stale)
    await db_session.flush()
    service = ToolCatalogService()

    await service.synchronize(db_session)
    await service.synchronize(db_session)
    entries = await service.list_all(db_session)

    assert stale.status == "disabled"
    assert len(entries) >= len(tool_registry.list())
    assert any(entry.operation == "removed.tool" for entry in entries)
    assert all(entry.version for entry in entries)
    assert all(
        entry.output_schema for entry in entries if entry.operation != "removed.tool"
    )


@pytest.mark.anyio
async def test_enable_disable_and_missing_catalog_entry(
    db_session: AsyncSession,
) -> None:
    service = ToolCatalogService()
    await service.synchronize(db_session)
    operation = tool_registry.list()[0].name

    disabled = await service.set_enabled(
        db_session,
        operation=operation,
        enabled=False,
    )
    enabled = await service.set_enabled(
        db_session,
        operation=operation,
        enabled=True,
    )

    assert disabled.status == "disabled"
    assert enabled.status == "active"
    with pytest.raises(HTTPException) as exc:
        await service.set_enabled(
            db_session,
            operation="missing.operation",
            enabled=True,
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_disabled_catalog_blocks_direct_execution(
    db_session: AsyncSession,
) -> None:
    user = _user()
    user.role = "admin"
    db_session.add(user)
    await db_session.flush()
    catalog = ToolCatalogService()
    operation = "quality.list_deviations"
    await catalog.set_enabled(db_session, operation=operation, enabled=False)

    try:
        with pytest.raises(HTTPException) as exc:
            await ToolExecutor().execute(
                db_session,
                request=AgentToolExecuteRequest.model_validate(
                    {
                        "operation": operation,
                        "subject": {
                            "tenant_id": "local",
                            "user_id": user.id,
                            "source": "internal",
                        },
                    }
                ),
            )
    finally:
        await catalog.set_enabled(db_session, operation=operation, enabled=True)

    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert exc.value.detail == "该能力已被管理员停用，当前无法执行"


@pytest.mark.anyio
async def test_list_page_filters_catalog_and_reports_total(
    db_session: AsyncSession,
) -> None:
    service = ToolCatalogService()
    await service.synchronize(db_session)
    first = tool_registry.list()[0]

    entries, total = await service.list_page(
        db_session,
        page=1,
        page_size=5,
        keyword=first.name,
        module=first.module,
        risk_level=first.risk_level,
        write=first.write,
    )

    assert total >= 1
    assert entries
    assert all(first.name in entry.operation for entry in entries)

    platform_entries, platform_total = await service.list_page(
        db_session,
        page=1,
        page_size=100,
        module="platform",
    )
    assert platform_total >= 1
    assert platform_entries
    assert all(entry.module is None for entry in platform_entries)


@pytest.mark.anyio
async def test_search_filters_module_query_scope_and_limit(
    db_session: AsyncSession,
) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    service = ToolCatalogService()
    await service.synchronize(db_session)
    specs = tool_registry.list()
    searchable = next(spec for spec in specs if spec.module is None)

    service.access_scope = ConfigurableAccessScope()  # type: ignore[assignment]
    limited = await service.search(
        db_session,
        _request(user.id, query=searchable.name, limit=1),
    )
    assert [entry.operation for entry in limited] == [searchable.name]

    assert (
        await service.search(
            db_session,
            _request(user.id, module="does-not-exist"),
        )
        == []
    )
    assert (
        await service.search(
            db_session,
            _request(user.id, query="does-not-match-any-tool"),
        )
        == []
    )

    service.access_scope = ConfigurableAccessScope(denied={searchable.name})  # type: ignore[assignment]
    assert (
        await service.search(
            db_session,
            _request(user.id, query=searchable.name),
        )
        == []
    )

    service.access_scope = ConfigurableAccessScope(  # type: ignore[assignment]
        error_status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    with pytest.raises(HTTPException) as exc:
        await service.search(db_session, _request(user.id))
    assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.anyio
async def test_describe_validates_status_user_and_access(
    db_session: AsyncSession,
) -> None:
    active = _user()
    inactive = _user(status_value="disabled")
    db_session.add_all([active, inactive])
    await db_session.flush()
    service = ToolCatalogService()
    service.access_scope = ConfigurableAccessScope()  # type: ignore[assignment]
    await service.synchronize(db_session)
    operation = tool_registry.list()[0].name

    entry = await service.describe(
        db_session,
        operation=operation,
        user_id=active.id,
        tenant_id="local",
    )
    assert entry.operation == operation

    with pytest.raises(HTTPException) as exc:
        await service.describe(
            db_session,
            operation="missing.operation",
            user_id=active.id,
            tenant_id="local",
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    with pytest.raises(HTTPException) as exc:
        await service.describe(
            db_session,
            operation=operation,
            user_id=inactive.id,
            tenant_id="local",
        )
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    with pytest.raises(HTTPException) as exc:
        await service.describe(
            db_session,
            operation=operation,
            user_id=uuid.uuid4(),
            tenant_id="local",
        )
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    with pytest.raises(HTTPException) as exc:
        await service.describe(
            db_session,
            operation=operation,
            user_id=active.id,
            tenant_id="other-tenant",
        )
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
