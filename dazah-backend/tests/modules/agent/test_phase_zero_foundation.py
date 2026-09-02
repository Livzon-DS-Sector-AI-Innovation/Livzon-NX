from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import normalize_correlation_id
from app.core.redaction import REDACTED_VALUE, redact_sensitive
from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.automation_schema import (
    AutomationDefinitionV1,
    AutomationErrorCode,
    compile_automation_definition,
)
from app.modules.agent.tools import ToolContext, ToolRegistry, agent_tool
from app.platform.identity.models import User
from app.platform.identity.permissions import IdentityPermissionService
from app.platform.identity.schemas import (
    ModulePermissionGrantInput,
    UserModulePermissionsUpdate,
)


class SampleInput(BaseModel):
    batch_id: uuid.UUID


def test_recursive_redaction_masks_nested_secrets_and_preserves_business_data() -> None:
    value = {
        "batch_id": "B-2026-001",
        "credentials": {
            "access_token": "sensitive",
            "nested": [{"app_secret": "hidden", "status": "active"}],
        },
    }

    result = redact_sensitive(value)

    assert result["batch_id"] == "B-2026-001"
    assert result["credentials"]["access_token"] == REDACTED_VALUE
    assert result["credentials"]["nested"][0]["app_secret"] == REDACTED_VALUE
    assert result["credentials"]["nested"][0]["status"] == "active"


def test_correlation_id_accepts_uuid_and_replaces_untrusted_values() -> None:
    existing = uuid.uuid4()

    assert normalize_correlation_id(str(existing)) == existing
    assert normalize_correlation_id(existing) == existing
    assert normalize_correlation_id("not-a-uuid") != existing


def test_tool_metadata_infers_business_module_and_permission_key() -> None:
    registry = ToolRegistry()

    @agent_tool(
        name="quality.get_batch",
        summary="查询批次",
        input_model=SampleInput,
        registry=registry,
        workflow_allowed=True,
        idempotent=True,
        output_schema={"type": "object"},
    )
    async def get_batch(context: ToolContext, data: SampleInput) -> dict[str, Any]:
        return {"batch_id": str(data.batch_id)}

    spec = registry.require("quality.get_batch")
    public = spec.public_dict()

    assert spec.module == "quality"
    assert spec.permission_key == "module.agent.read"
    assert public["capability_version"] == "1.0"
    assert public["idempotent"] is True
    assert public["output_schema"] == {"type": "object"}


def test_automation_schema_compiles_registered_authorized_workflow() -> None:
    definition = {
        "schema_version": "1.0",
        "name": "采购到货未入库提醒",
        "steps": [
            {
                "key": "get_arrivals",
                "type": "tool",
                "operation": "procurement.list_arrivals",
                "input": {"status": "arrived"},
            },
            {
                "key": "has_delay",
                "type": "condition",
                "expression": {
                    "field": "steps.get_arrivals.output.overdue_count",
                    "op": "gt",
                    "value": 0,
                },
            },
            {
                "key": "finish",
                "type": "end",
                "status": "succeeded",
            },
        ],
    }
    capabilities = {
        "procurement.list_arrivals": {
            "module": "procurement",
            "workflow_allowed": True,
            "human_decision_required": False,
        }
    }

    report = compile_automation_definition(
        definition,
        capabilities=capabilities,
        allowed_tool_names={"procurement.list_arrivals"},
    )

    assert report.valid is True
    assert report.required_operations == ["procurement.list_arrivals"]
    assert report.required_modules == ["procurement"]
    assert report.issues == []


def test_automation_schema_rejects_urls_and_executable_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AutomationDefinitionV1.model_validate(
            {
                "name": "危险定义",
                "steps": [
                    {
                        "key": "unsafe",
                        "type": "tool",
                        "operation": "quality.get_batch",
                        "input": {"callback_url": "https://attacker.invalid/run"},
                    }
                ],
            }
        )

    assert AutomationErrorCode.UNSAFE_EXPRESSION.value in str(exc_info.value)


def test_automation_compiler_rejects_human_decision_and_missing_scope() -> None:
    report = compile_automation_definition(
        {
            "name": "自动批准",
            "steps": [
                {
                    "key": "approve",
                    "type": "tool",
                    "operation": "procurement.approve_request",
                    "input": {"request_id": "REQ-1"},
                }
            ],
        },
        capabilities={
            "procurement.approve_request": {
                "module": "procurement",
                "workflow_allowed": False,
                "human_decision_required": True,
            }
        },
        allowed_tool_names=set(),
    )

    codes = {issue.code for issue in report.issues}
    assert report.valid is False
    assert AutomationErrorCode.HUMAN_DECISION_REQUIRED in codes
    assert AutomationErrorCode.PERMISSION_DENIED in codes


def test_permission_normalization_requires_view_and_rejects_secret_scope() -> None:
    with pytest.raises(HTTPException) as missing_view:
        IdentityPermissionService._normalize_grants(
            [
                ModulePermissionGrantInput(
                    module_code="quality",
                    permissions=["module.agent.read"],
                )
            ]
        )
    assert missing_view.value.status_code == 400

    with pytest.raises(HTTPException) as secret_scope:
        IdentityPermissionService._normalize_grants(
            [
                ModulePermissionGrantInput(
                    module_code="quality",
                    permissions=["module.view", "module.agent.read"],
                    data_scope={"api_token": "forbidden"},
                )
            ]
        )
    assert secret_scope.value.status_code == 400


def test_permission_normalization_is_deterministic() -> None:
    result = IdentityPermissionService._normalize_grants(
        [
            ModulePermissionGrantInput(
                module_code="warehouse",
                permissions=[
                    "module.agent.read",
                    "module.view",
                    "module.agent.read",
                ],
                data_scope={"factory_ids": ["F-1"]},
            )
        ]
    )

    assert result == [
        {
            "module_code": "warehouse",
            "permissions": ["module.agent.read", "module.view"],
            "data_scope": {"factory_ids": ["F-1"]},
        }
    ]


@pytest.mark.anyio
async def test_business_tool_scope_rejects_anonymous_actor_fail_closed() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await AgentAccessScopeService().require_tool_access(
            object(),  # type: ignore[arg-type]
            user=None,
            tool_name="quality.list_deviations",
            module="quality",
        )

    assert exc_info.value.status_code == 403
    assert "已登录责任主体" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_admin_grant_change_syncs_livzon_scope_with_versioned_outbox(
    db_session: AsyncSession,
) -> None:
    admin = User(
        name="权限管理员",
        username=f"permission-admin-{uuid.uuid4().hex[:8]}",
        role="admin",
        status="active",
        auth_source="local",
    )
    target = User(
        name="质量用户",
        username=f"quality-user-{uuid.uuid4().hex[:8]}",
        role="user",
        status="active",
        auth_source="local",
    )
    db_session.add_all([admin, target])
    await db_session.flush()

    permission_service = IdentityPermissionService()
    updated_user, grants, event = await permission_service.replace_user_permissions(
        db_session,
        target_user_id=target.id,
        request=UserModulePermissionsUpdate(
            expected_grant_version=0,
            reason="允许质量异常查询与自动化",
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

    snapshot = await AgentAccessScopeService().synchronize(
        db_session,
        user_id=target.id,
        actor_id=admin.id,
    )
    await permission_service.repo.mark_outbox_processed(
        db_session, event, actor_id=admin.id
    )

    assert updated_user.grant_version == 1
    assert grants[0].grant_version == 1
    assert event.status == "processed"
    assert event.event_type == "identity.user_module_grants.changed.v1"
    assert snapshot.source_grant_version == 1
    assert snapshot.sync_status == "synced"
    # 旧模块授权仅保留页面兼容展示；草稿/未发布页面不能派生工具能力。
    assert "quality.list_deviations" not in snapshot.tool_names
    assert "quality.list_deviations" not in snapshot.workflow_tool_names
    assert snapshot.modules == [
        {
            "module_code": "quality",
            "module_name": "质量管理",
            "permissions": [
                "module.agent.automate",
                "module.agent.read",
                "module.view",
            ],
            "data_scope": {"factory_ids": ["F-1"]},
        }
    ]


@pytest.mark.anyio
async def test_admin_cannot_modify_own_grants(db_session: AsyncSession) -> None:
    admin = User(
        name="自助提权测试管理员",
        username=f"self-grant-admin-{uuid.uuid4().hex[:8]}",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(admin)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await IdentityPermissionService().replace_user_permissions(
            db_session,
            target_user_id=admin.id,
            request=UserModulePermissionsUpdate(
                expected_grant_version=0,
                reason="尝试修改本人权限",
                grants=[],
            ),
            current_user=admin,
        )

    assert exc_info.value.status_code == 403
    assert "不能修改自己的模块授权" in str(exc_info.value.detail)
