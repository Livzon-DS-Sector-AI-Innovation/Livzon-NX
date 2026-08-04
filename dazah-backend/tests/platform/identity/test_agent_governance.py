from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity import service
from app.platform.identity.models import User
from app.platform.identity.repository import ExternalIdentityBindingRepository
from app.platform.identity.schemas import (
    ExternalIdentityBindingCreate,
    ExternalIdentityBindingStatusUpdate,
    FeishuConfigUpsert,
)


def test_external_identity_lifecycle_contracts() -> None:
    payload = ExternalIdentityBindingCreate(
        tenant_id="tenant-a",
        app_fingerprint="cli_test",
        external_open_id="ou_test",
        local_user_id=uuid4(),
        source="directory_sync",
    )
    assert payload.source == "directory_sync"
    assert ExternalIdentityBindingStatusUpdate(status="suspended").status == "suspended"
    assert ExternalIdentityBindingStatusUpdate(status="revoked").status == "revoked"
    with pytest.raises(ValidationError):
        ExternalIdentityBindingStatusUpdate(status="disabled")


@pytest.mark.anyio
async def test_external_identity_status_transition_records_actor() -> None:
    actor_id = uuid4()
    binding = SimpleNamespace(status="active", updated_by=None)

    class FakeSession:
        flushed = False
        refreshed = None

        async def flush(self) -> None:
            self.flushed = True

        async def refresh(self, value) -> None:
            self.refreshed = value

    session = FakeSession()
    result = await ExternalIdentityBindingRepository().set_status(
        session,
        binding,
        status_value="revoked",
        actor_id=actor_id,
    )
    assert result.status == "revoked"
    assert result.updated_by == actor_id
    assert session.flushed is True
    assert session.refreshed is binding


def test_feishu_admission_config_defaults_fail_closed() -> None:
    config = FeishuConfigUpsert(
        app_id="cli_test",
        app_secret="secret",
        allowed_group_chat_ids=["oc_allowed"],
    )
    assert config.require_group_mention is True
    assert config.allowed_group_chat_ids == ["oc_allowed"]


@pytest.mark.anyio
async def test_directory_reconciliation_creates_binding_once(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = uuid4()
    tenant_id = f"tenant-{uuid4().hex}"
    user = User(
        name="目录同步用户",
        username=f"directory-{uuid4().hex[:12]}",
        status="active",
        tenant_key=tenant_id,
        feishu_user_id=f"u_{uuid4().hex}",
        feishu_open_id=f"ou_{uuid4().hex}",
    )
    db_session.add(user)
    await db_session.flush()
    config = SimpleNamespace(tenant_id=tenant_id, app_id="cli_directory")

    class FakeConfigRepository:
        async def get_active(self, db):
            return config

    monkeypatch.setattr(service, "_feishu_config_repo", FakeConfigRepository())

    first = await service.reconcile_livzon_identity_bindings(
        db_session,
        actor_id=actor_id,
    )
    second = await service.reconcile_livzon_identity_bindings(
        db_session,
        actor_id=actor_id,
    )

    assert first["created"] == 1
    assert first["conflicts"] == []
    assert second["created"] == 0
    assert second["existing"] == 1
    bindings = await ExternalIdentityBindingRepository().list_for_app(
        db_session,
        tenant_id=tenant_id,
        app_fingerprint="cli_directory",
    )
    assert len(bindings) == 1
    assert bindings[0].source == "directory_sync"
    assert bindings[0].local_user_id == user.id
