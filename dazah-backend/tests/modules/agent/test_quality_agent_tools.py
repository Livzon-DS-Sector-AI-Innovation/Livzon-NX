from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.modules.agent.schemas import AgentToolExecuteRequest, AgentTrustedSubject
from app.modules.agent.service import AgentService
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.modules.quality import agent_tools as quality_agent_tools
from app.modules.quality.schemas.inspection import InspectionRecordOut


class AllowAllAccessScopeService:
    async def require_tool_access(self, *args, **kwargs):
        return None


EXPECTED_QUALITY_OPERATIONS = {
    "quality.add_capa_execution_track",
    "quality.auto_fill_capa_from_deviation",
    "quality.complete_capa_part",
    "quality.create_capa",
    "quality.create_change",
    "quality.create_change_action_plan",
    "quality.create_cpv_parameter",
    "quality.create_cpv_product",
    "quality.create_deviation",
    "quality.create_validation",
    "quality.get_capa",
    "quality.get_capa_statistics",
    "quality.get_change",
    "quality.get_change_statistics",
    "quality.get_cpv_product",
    "quality.get_cpv_statistics",
    "quality.get_cpv_trend",
    "quality.get_deviation",
    "quality.get_deviation_statistics",
    "quality.get_feishu_capa_ledger",
    "quality.get_feishu_capa_plan_track",
    "quality.get_feishu_validation",
    "quality.get_inspection_record",
    "quality.get_next_change_code",
    "quality.get_oos_oot_record",
    "quality.get_related_capas",
    "quality.get_validation",
    "quality.get_validation_statistics",
    "quality.link_capa_deviation",
    "quality.list_capa_departments",
    "quality.list_capas",
    "quality.list_change_action_plans",
    "quality.list_change_action_plans_by_change",
    "quality.list_changes",
    "quality.list_complaints",
    "quality.list_cpv_batches",
    "quality.list_cpv_cpp_batches",
    "quality.list_cpv_cqa_batches",
    "quality.list_cpv_parameters",
    "quality.list_cpv_products",
    "quality.list_deviation_report_records",
    "quality.list_deviations",
    "quality.list_feishu_capa_ledger",
    "quality.list_feishu_capa_plan_tracks",
    "quality.list_feishu_validations",
    "quality.list_inspection_records",
    "quality.list_oos_oot_records",
    "quality.list_product_quality_records",
    "quality.list_quality_sync_conflicts",
    "quality.list_return_recalls",
    "quality.list_suppliers",
    "quality.list_validation_executions",
    "quality.list_validations",
    "quality.pull_feishu_validations",
    "quality.pull_quality_records_from_feishu",
    "quality.resubmit_capa",
    "quality.resubmit_deviation",
    "quality.run_change_action_plan_reminders",
    "quality.send_change_action_plan_reminder",
    "quality.submit_capa",
    "quality.submit_deviation",
    "quality.submit_deviation_investigation",
    "quality.sync_capa_plan_track_to_feishu",
    "quality.sync_capa_to_feishu",
    "quality.sync_change_action_plan",
    "quality.sync_change_action_plans_from_feishu",
    "quality.sync_deviation_report_record_to_feishu",
    "quality.sync_deviation_to_feishu",
    "quality.update_capa",
    "quality.update_change",
    "quality.update_change_action_plan",
    "quality.update_cpv_parameter",
    "quality.update_cpv_product",
    "quality.update_deviation",
    "quality.update_validation",
    "quality.update_validation_execution",
}


class FakeDb:
    pass


class FakeAgentRepository:
    def __init__(self) -> None:
        self.tool_calls = []
        self.confirmations = []

    async def create_tool_call(
        self,
        db,
        *,
        session_id,
        operation,
        request_payload,
    ):
        call = SimpleNamespace(
            session_id=session_id,
            operation=operation,
            request_payload=request_payload,
            status="started",
            response_payload=None,
            error_message=None,
        )
        self.tool_calls.append(call)
        return call

    async def finish_tool_call(
        self,
        db,
        call,
        *,
        status,
        response_payload=None,
        error_message=None,
    ):
        call.status = status
        call.response_payload = response_payload
        call.error_message = error_message
        return call

    async def create_confirmation(
        self,
        db,
        *,
        session_id,
        user_id,
        operation,
        summary,
        risk_level,
        request_payload,
        expires_at,
    ):
        confirmation = SimpleNamespace(
            id=uuid.uuid4(),
            session_id=session_id,
            user_id=user_id,
            operation=operation,
            summary=summary,
            risk_level=risk_level,
            request_payload=request_payload,
            result_payload=None,
            status="pending",
            expires_at=expires_at,
            executed_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.confirmations.append(confirmation)
        return confirmation


def _quality_operation_names() -> set[str]:
    ensure_agent_tools_registered()
    return {
        tool.name for tool in tool_registry.list() if tool.name.startswith("quality.")
    }


def test_quality_agent_tools_are_registered() -> None:
    assert _quality_operation_names() == EXPECTED_QUALITY_OPERATIONS


def test_quality_tools_exclude_deleted_approval_and_config_operations() -> None:
    operations = _quality_operation_names()

    assert not any(".delete" in operation for operation in operations)
    assert "quality.approve_capa" not in operations
    assert "quality.reject_deviation" not in operations
    assert "quality.update_quality_feishu_app_settings" not in operations
    assert "quality.update_quality_feishu_entity_setting" not in operations


@pytest.mark.anyio
async def test_quality_write_tool_returns_confirmation_before_execution() -> None:
    repo = FakeAgentRepository()
    service = AgentService(
        settings=SimpleNamespace(AGENT_WRITE_CONFIRM_TTL_SECONDS=300),
        repo=repo,
        access_scope_service=AllowAllAccessScopeService(),
    )

    response = await service.execute_tool(
        FakeDb(),
        request=AgentToolExecuteRequest(
            operation="quality.create_deviation",
            subject=AgentTrustedSubject(
                tenant_id="test",
                user_id=uuid.uuid4(),
                source="internal",
            ),
            body={
                "description": "洁净区压差异常",
                "affected_items": "产品A/批号B001",
            },
            reason="创建偏差记录",
        ),
    )

    assert response.ok is True
    assert response.requires_confirmation is True
    assert response.confirmation is not None
    assert response.confirmation.operation == "quality.create_deviation"
    assert repo.tool_calls[0].status == "confirmation_required"


def test_quality_tools_are_exposed_to_workflow_capabilities() -> None:
    service = AgentService(settings=SimpleNamespace())

    capabilities = service._workflow_capabilities()["capabilities"]
    by_operation = {item["operation"]: item for item in capabilities}

    assert by_operation["quality.list_deviations"]["workflow_allowed"] is True
    assert by_operation["quality.list_deviations"]["write"] is False
    assert by_operation["quality.create_deviation"]["workflow_allowed"] is True
    assert by_operation["quality.create_deviation"]["write"] is True
    assert by_operation["quality.create_deviation"]["risk_level"] == "medium"
    for operation in {
        "quality.list_inspection_records",
        "quality.get_inspection_record",
        "quality.list_oos_oot_records",
        "quality.get_oos_oot_record",
        "quality.list_suppliers",
        "quality.list_complaints",
        "quality.list_return_recalls",
        "quality.list_product_quality_records",
    }:
        assert by_operation[operation]["workflow_allowed"] is True
        assert by_operation[operation]["write"] is False


@pytest.mark.asyncio
async def test_list_inspection_records_tool_uses_quality_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = InspectionRecordOut.model_construct(
        id=uuid.uuid4(),
        inspection_no="QC-001",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def fake_list_resource_records(*args, **kwargs):
        assert args[1] == "inspection_records"
        assert kwargs["filters"]["conclusion"] == "合格"
        return [record], 1

    monkeypatch.setattr(
        quality_agent_tools.inspection,
        "list_resource_records",
        fake_list_resource_records,
    )

    result = await quality_agent_tools.list_inspection_records(
        SimpleNamespace(db=FakeDb()),
        quality_agent_tools.InspectionRecordListInput(conclusion="合格"),
    )

    assert result["total"] == 1
    assert result["items"][0]["inspection_no"] == "QC-001"


def test_quality_operations_are_available_from_backend_registry() -> None:
    assert _quality_operation_names()
