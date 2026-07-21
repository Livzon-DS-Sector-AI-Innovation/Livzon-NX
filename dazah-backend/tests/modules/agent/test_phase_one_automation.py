from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import REDACTED_VALUE
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.models import AgentWorkflow
from app.modules.agent.schemas import AgentAutomationDraftCreate
from app.platform.identity.models import User
from app.platform.identity.permissions import IdentityPermissionService
from app.platform.identity.schemas import (
    ModulePermissionGrantInput,
    UserModulePermissionsUpdate,
)


def _user(*, role: str = "user") -> User:
    return User(
        name=f"Phase 1 {role}",
        username=f"phase-one-{role}-{uuid.uuid4().hex[:12]}",
        role=role,
        status="active",
        auth_source="local",
    )


def _definition(name: str) -> dict:
    return {
        "name": name,
        "description": "查询质量偏差并保留受控摘要",
        "steps": [
            {
                "key": "list_deviations",
                "type": "tool",
                "operation": "quality.list_deviations",
                "input": {"api_token": "must-not-leak"},
            },
            {
                "key": "finish",
                "type": "end",
                "status": "succeeded",
            },
        ],
    }


async def _grant_quality_automation(
    db_session: AsyncSession,
    *,
    admin: User,
    user: User,
) -> None:
    await IdentityPermissionService().replace_user_permissions(
        db_session,
        target_user_id=user.id,
        request=UserModulePermissionsUpdate(
            expected_grant_version=user.grant_version,
            reason="Phase 1 自动化集成测试授权",
            grants=[
                ModulePermissionGrantInput(
                    module_code="quality",
                    permissions=[
                        "module.view",
                        "module.agent.read",
                        "module.agent.automate",
                    ],
                    data_scope={"factory_ids": ["F-1"]},
                )
            ],
        ),
        current_user=admin,
    )


@pytest.mark.anyio
async def test_owner_can_create_and_confirm_automation(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_quality_automation(db_session, admin=admin, user=owner)

    service = AgentAutomationService()
    draft = await service.create_draft(
        db_session,
        user=owner,
        request=AgentAutomationDraftCreate.model_validate(
            {"definition": _definition("质量偏差摘要")}
        ),
    )

    assert draft.status == "draft"
    assert draft.owner_user_id == owner.id
    assert draft.payload_redacted is False
    assert draft.active_version_id is not None

    confirmed = await service.confirm_automation(
        db_session, user=owner, automation_id=draft.id
    )
    versions = await service.list_versions(
        db_session, user=owner, automation_id=draft.id
    )

    assert confirmed.status == "enabled"
    assert len(versions) == 1
    assert versions[0].definition["steps"][0]["input"]["api_token"] == REDACTED_VALUE


@pytest.mark.anyio
async def test_shared_and_platform_views_are_server_filtered_and_redacted(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    participant = _user()
    db_session.add_all([admin, owner, participant])
    await db_session.flush()
    await _grant_quality_automation(db_session, admin=admin, user=owner)

    service = AgentAutomationService()
    draft = await service.create_draft(
        db_session,
        user=owner,
        request=AgentAutomationDraftCreate.model_validate(
            {
                "definition": _definition("共享质量偏差摘要"),
                "scope_type": "shared",
                "scope_ref": {"user_ids": [str(participant.id)]},
            }
        ),
    )

    shared = await service.list_automations(
        db_session,
        user=participant,
        scope="shared",
        status_value=None,
        page=1,
        page_size=20,
    )
    platform = await service.list_automations(
        db_session,
        user=admin,
        scope="platform",
        status_value=None,
        page=1,
        page_size=20,
    )
    shared_versions = await service.list_versions(
        db_session, user=participant, automation_id=draft.id
    )

    assert [item.id for item in shared.items] == [draft.id]
    assert shared.items[0].payload_redacted is True
    assert [item.id for item in platform.items] == [draft.id]
    assert platform.items[0].payload_redacted is True
    assert shared_versions[0].definition == {}
    assert shared_versions[0].policy_snapshot == {}


@pytest.mark.anyio
async def test_revoked_automation_permission_suspends_enable_attempt(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_quality_automation(db_session, admin=admin, user=owner)

    service = AgentAutomationService()
    draft = await service.create_draft(
        db_session,
        user=owner,
        request=AgentAutomationDraftCreate.model_validate(
            {"definition": _definition("撤权暂停测试")}
        ),
    )
    await service.confirm_automation(db_session, user=owner, automation_id=draft.id)

    await IdentityPermissionService().replace_user_permissions(
        db_session,
        target_user_id=owner.id,
        request=UserModulePermissionsUpdate(
            expected_grant_version=owner.grant_version,
            reason="撤销 Phase 1 自动化权限",
            grants=[],
        ),
        current_user=admin,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.set_enabled(
            db_session, user=owner, automation_id=draft.id, enabled=True
        )

    current = await service.repo.get_automation(db_session, draft.id)
    assert exc_info.value.status_code == 403
    assert current is not None
    assert current.status == "suspended_policy"


@pytest.mark.anyio
async def test_legacy_workflow_is_exposed_as_read_only_automation(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_quality_automation(db_session, admin=admin, user=owner)
    legacy = AgentWorkflow(
        user_id=owner.id,
        name="旧工作流兼容项",
        description="在新自动化查询中保持可见",
        status="enabled",
        steps=[{"operation": "quality.list_deviations", "api_token": "legacy-secret"}],
    )
    legacy.created_by = owner.id
    legacy.updated_by = owner.id
    db_session.add(legacy)
    await db_session.flush()

    service = AgentAutomationService()
    mine = await service.list_automations(
        db_session,
        user=owner,
        scope="mine",
        status_value=None,
        page=1,
        page_size=20,
    )
    versions = await service.list_versions(
        db_session, user=owner, automation_id=legacy.id
    )
    platform = await service.list_automations(
        db_session,
        user=admin,
        scope="platform",
        status_value=None,
        page=1,
        page_size=20,
    )

    legacy_item = next(item for item in mine.items if item.id == legacy.id)
    platform_item = next(item for item in platform.items if item.id == legacy.id)
    assert legacy_item.legacy_source_workflow_id == legacy.id
    assert versions[0].schema_version == "legacy-agent-workflow-v1"
    assert versions[0].definition["steps"][0]["api_token"] == REDACTED_VALUE
    assert platform_item.payload_redacted is True
