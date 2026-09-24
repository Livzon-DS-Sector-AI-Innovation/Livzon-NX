import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.modules.agent.automation_service import AgentAutomationService


class PagedRepository:
    def __init__(self, owner_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        self.items = [
            SimpleNamespace(
                id=uuid.uuid4(),
                owner_user_id=owner_id,
                source_session_id=None,
                name=f"自动化 {index}",
                description=None,
                scope_type="mine",
                scope_ref={},
                status="enabled",
                active_version_id=None,
                last_run_id=None,
                last_run_status=None,
                last_run_at=None,
                created_at=now - timedelta(minutes=index),
                updated_at=now - timedelta(minutes=index),
            )
            for index in range(501)
        ]
        self.requested_pages: list[int] = []
        self.run_automation_ids: list[uuid.UUID] = []

    async def list_automations(
        self, _db: Any, *, page: int, page_size: int, **_kwargs: Any
    ) -> tuple[list[Any], int]:
        self.requested_pages.append(page)
        start = (page - 1) * page_size
        return self.items[start : start + page_size], len(self.items)

    async def list_automation_triggers(self, _db: Any, **_kwargs: Any) -> list[Any]:
        return []

    async def list_legacy_workflows(self, _db: Any, **_kwargs: Any) -> list[Any]:
        return []

    async def list_automation_runs(
        self, _db: Any, *, automation_ids: list[uuid.UUID], **_kwargs: Any
    ) -> tuple[list[Any], int]:
        self.run_automation_ids = automation_ids
        return [], 0


class AccessScopeStub:
    async def get_current_scope(self, _db: Any, *, user: Any) -> None:
        assert user.role == "admin"


@pytest.mark.asyncio
async def test_platform_audit_reads_all_definition_pages_and_run_candidates() -> None:
    admin = SimpleNamespace(id=uuid.uuid4(), role="admin")
    repo = PagedRepository(admin.id)
    service = AgentAutomationService(repo=repo, access_scope_service=AccessScopeStub())

    definitions = await service.list_automations(
        None, user=admin, scope="platform", status_value=None, page=26, page_size=20
    )
    assert definitions.total == 501
    assert [item.id for item in definitions.items] == [repo.items[-1].id]
    assert repo.requested_pages == [1, 2]

    runs = await service.list_runs(
        None, user=admin, scope="platform", status_value=None, page=1, page_size=20
    )
    assert runs.total == 0
    assert len(repo.run_automation_ids) == 501
    assert repo.items[-1].id in repo.run_automation_ids
    assert repo.requested_pages == [1, 2, 1, 2]
