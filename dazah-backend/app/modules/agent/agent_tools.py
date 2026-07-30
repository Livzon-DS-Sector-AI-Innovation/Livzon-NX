from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.modules.agent.automation_schema import AutomationDefinitionV1
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.event_service import AgentDomainEventService
from app.modules.agent.manual_task_service import AgentManualTaskService
from app.modules.agent.operations_service import AgentOperationsService
from app.modules.agent.push_delivery_service import PushDeliveryService
from app.modules.agent.schemas import (
    AgentAutomationDraftCreate,
    AgentAutomationSimulationRequest,
    AgentAutomationTriggerCreate,
    AgentAutomationUpdate,
)
from app.modules.agent.tools import ToolContext, agent_tool
from app.platform.identity.models import User


class AutomationIdInput(BaseModel):
    automation_id: UUID


class AutomationPreviewInput(BaseModel):
    definition: AutomationDefinitionV1


class AutomationUpdateInput(AgentAutomationUpdate):
    automation_id: UUID


class AutomationEnabledInput(BaseModel):
    automation_id: UUID
    enabled: bool


class AutomationListInput(BaseModel):
    scope: str = "mine"
    status_value: str | None = None
    page: int = 1
    page_size: int = 20


class AutomationRunIdInput(BaseModel):
    run_id: UUID


class DirectAutomationActionInput(BaseModel):
    operation: str = Field(
        pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
        description="要执行的已注册业务工具，例如 identity.deliver_feishu_message",
    )
    body: dict[str, Any] = Field(
        default_factory=dict,
        description="直接传给业务工具的参数，由后端编译为自动化步骤",
    )


class DirectAutomationCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    actions: list[DirectAutomationActionInput] = Field(min_length=1, max_length=20)


class DirectScheduledTaskCreateInput(DirectAutomationCreateInput):
    requirement: str = Field(
        min_length=1,
        max_length=4000,
        description="用户提出的完整定时任务需求，不得概括、改写或省略",
    )
    cron: str = Field(
        min_length=9,
        max_length=100,
        description="五段 Cron：分钟 小时 日 月 星期",
    )
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_runtime_query_for_data_delivery(
        self,
    ) -> "DirectScheduledTaskCreateInput":
        query_indexes: list[int] = []
        for index, action in enumerate(self.actions):
            verb = action.operation.partition(".")[2]
            if verb.startswith(("list_", "get_", "search_", "aggregate")):
                query_indexes.append(index)
            if action.operation in _FEISHU_MESSAGE_OPERATIONS:
                requirement_mentions_data = any(
                    word in self.requirement
                    for word in ("数据", "汇总", "统计", "清单", "报表", "记录", "查询")
                )
                if requirement_mentions_data and not any(
                    query_index < index for query_index in query_indexes
                ):
                    raise ValueError(
                        "需要发送数据的定时任务必须先添加查询动作，再添加飞书发送动作"
                    )
        return self


_FEISHU_MESSAGE_OPERATIONS = {
    "identity.deliver_feishu_message",
}


def _scheduled_action_body(
    action: DirectAutomationActionInput,
    *,
    previous_result_keys: list[str],
) -> dict[str, Any]:
    body = dict(action.body)
    if action.operation not in _FEISHU_MESSAGE_OPERATIONS or not previous_result_keys:
        return body

    result_block = "\n\n数据结果：\n" + "\n\n".join(
        f"${{steps.{key}}}" for key in previous_result_keys
    )
    markdown = str(body.get("markdown") or "").strip()
    if "${steps." not in markdown:
        body["markdown"] = f"{markdown}{result_block}".strip()
    return body


class PushDeliveryListInput(BaseModel):
    status_value: str | None = None
    page: int = 1
    page_size: int = 20


class PushDeliveryIdInput(BaseModel):
    delivery_id: UUID


class CorrelationIdInput(BaseModel):
    correlation_id: UUID


class ManualTaskCompleteInput(BaseModel):
    run_id: UUID


def _required_user(context: ToolContext) -> User:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return context.user


def _automation_service(context: ToolContext) -> AgentAutomationService:
    _required_user(context)
    return AgentAutomationService()


@agent_tool(
    name="agent.get_my_access_scope",
    summary="查询当前用户的 Livzon 有效模块与工具范围",
    method="GET",
    path="/agent/access-scope",
    workflow_allowed=False,
    idempotent=True,
    output_hint="返回当前授权版本、同步状态、可见模块、可调用工具和可编排工具。",
)
async def get_my_access_scope(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    from app.modules.agent.access_scope import AgentAccessScopeService

    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    result = await AgentAccessScopeService().scope_out(
        context.db, user=_required_user(context)
    )
    return result.model_dump(mode="json")


@agent_tool(
    name="agent.create_automation_draft",
    summary="创建 Livzon 自动化草案",
    input_model=AgentAutomationDraftCreate,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="POST",
    path="/agent/automations",
)
async def create_automation_draft(
    context: ToolContext, data: AgentAutomationDraftCreate
) -> dict[str, Any]:
    automation = await _automation_service(context).create_draft(
        context.db, user=_required_user(context), request=data
    )
    return {
        "automation": automation.model_dump(mode="json"),
        "artifact": {
            "type": "automation_detail",
            "automationId": str(automation.id),
            "version": 1,
        },
    }


def _direct_automation_request(
    data: DirectAutomationCreateInput,
    *,
    scheduled: bool,
) -> AgentAutomationDraftCreate:
    timezone = getattr(data, "timezone", "Asia/Shanghai")
    cron = getattr(data, "cron", None)
    previous_result_keys: list[str] = []
    steps: list[dict[str, Any]] = []
    for index, action in enumerate(data.actions, start=1):
        key = f"action_{index}"
        action_body = (
            _scheduled_action_body(
                action,
                previous_result_keys=previous_result_keys,
            )
            if scheduled
            else action.body
        )
        steps.append(
            {
                "key": key,
                "name": f"执行步骤 {index}",
                "type": "tool",
                "operation": action.operation,
                "input": action_body,
            }
        )
        if action.operation not in _FEISHU_MESSAGE_OPERATIONS:
            previous_result_keys.append(key)

    description = data.description
    if scheduled:
        requirement = getattr(data, "requirement", "").strip()
        description = (
            f"{description}\n\n完整需求：{requirement}" if description else requirement
        )
    definition = AutomationDefinitionV1.model_validate(
        {
            "name": data.name,
            "description": description,
            "timezone": timezone,
            "steps": steps,
        }
    )
    triggers = [
        AgentAutomationTriggerCreate(
            trigger_type="schedule" if scheduled else "manual",
            schedule={"cron": cron} if scheduled else {},
            timezone=timezone,
        )
    ]
    return AgentAutomationDraftCreate(
        definition=definition,
        triggers=triggers,
        change_summary=(
            "由 Livzon 助手创建定时任务"
            if scheduled
            else "由 Livzon 助手创建自动化流程"
        ),
    )


async def _create_direct_automation(
    context: ToolContext,
    data: DirectAutomationCreateInput,
    *,
    scheduled: bool,
) -> dict[str, Any]:
    service = _automation_service(context)
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    user = context.user
    automation = await service.create_draft(
        context.db,
        user=user,
        request=_direct_automation_request(data, scheduled=scheduled),
    )
    automation = await service.confirm_automation(
        context.db,
        user=user,
        automation_id=automation.id,
    )
    return {
        "task_type": "scheduled_task" if scheduled else "automation",
        "automation": automation.model_dump(mode="json"),
        "artifact": {
            "type": "automation_detail",
            "automationId": str(automation.id),
            "version": automation.active_version,
        },
    }


@agent_tool(
    name="agent.create_automation",
    summary="直接创建并启用不含时间触发的自动化流程",
    input_model=DirectAutomationCreateInput,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="POST",
    path="/agent/automations/direct",
    output_hint="仅用于不含时间条件的自动化；后端负责生成和校验流程定义。",
)
async def create_automation(
    context: ToolContext, data: DirectAutomationCreateInput
) -> dict[str, Any]:
    return await _create_direct_automation(context, data, scheduled=False)


@agent_tool(
    name="agent.create_scheduled_task",
    summary="直接创建并启用包含 Cron 时间触发的定时任务",
    input_model=DirectScheduledTaskCreateInput,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="POST",
    path="/agent/scheduled-tasks/direct",
    output_hint="只用于包含明确执行时间的任务；后端强制创建 schedule 触发器。",
)
async def create_scheduled_task(
    context: ToolContext, data: DirectScheduledTaskCreateInput
) -> dict[str, Any]:
    return await _create_direct_automation(context, data, scheduled=True)


@agent_tool(
    name="agent.preview_automation",
    summary="预览自动化定义、权限和能力校验结果",
    input_model=AutomationPreviewInput,
    workflow_allowed=False,
    method="POST",
    path="/agent/automations/preview",
)
async def preview_automation(
    context: ToolContext, data: AutomationPreviewInput
) -> dict[str, Any]:
    return await _automation_service(context).preview(
        context.db, user=_required_user(context), definition=data.definition
    )


@agent_tool(
    name="agent.confirm_automation",
    summary="确认并启用 Livzon 自动化",
    input_model=AutomationIdInput,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="POST",
    path="/agent/automations/{automation_id}/confirm",
)
async def confirm_automation(
    context: ToolContext, data: AutomationIdInput
) -> dict[str, Any]:
    automation = await _automation_service(context).confirm_automation(
        context.db,
        user=_required_user(context),
        automation_id=data.automation_id,
    )
    return {
        "automation": automation.model_dump(mode="json"),
        "artifact": {
            "type": "automation_detail",
            "automationId": str(automation.id),
            "version": automation.active_version,
        },
    }


@agent_tool(
    name="agent.list_automations",
    summary="查询 Livzon 自动化",
    input_model=AutomationListInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/automations",
)
async def list_automations(
    context: ToolContext, data: AutomationListInput
) -> dict[str, Any]:
    result = await _automation_service(context).list_automations(
        context.db,
        user=_required_user(context),
        scope=data.scope,
        status_value=data.status_value,
        page=max(1, data.page),
        page_size=min(max(1, data.page_size), 100),
    )
    return {
        **result.model_dump(mode="json"),
        "artifact": {"type": "automation_list", "queryRef": "current"},
    }


@agent_tool(
    name="agent.get_automation",
    summary="查看 Livzon 自动化详情",
    input_model=AutomationIdInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/automations/{automation_id}",
)
async def get_automation(
    context: ToolContext, data: AutomationIdInput
) -> dict[str, Any]:
    automation = await _automation_service(context).get_automation_out(
        context.db,
        user=_required_user(context),
        automation_id=data.automation_id,
    )
    return {
        "automation": automation.model_dump(mode="json"),
        "artifact": {
            "type": "automation_detail",
            "automationId": str(automation.id),
            "version": automation.active_version,
        },
    }


@agent_tool(
    name="agent.run_automation",
    summary="立即运行 Livzon 自动化",
    input_model=AutomationIdInput,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="POST",
    path="/agent/automations/{automation_id}/run",
)
async def run_automation(
    context: ToolContext, data: AutomationIdInput
) -> dict[str, Any]:
    service = _automation_service(context)
    await service._require_owner(
        context.db,
        user=_required_user(context),
        automation_id=data.automation_id,
    )
    from app.modules.agent.automation_runner import AgentAutomationRunner

    run = await AgentAutomationRunner().execute_manual(
        context.db,
        automation_id=data.automation_id,
    )
    result = await service.get_run(
        context.db, user=_required_user(context), run_id=run.id
    )
    return {"run": result}


@agent_tool(
    name="agent.list_automation_audit",
    summary="查看 Livzon 自动化版本与修改审计",
    input_model=AutomationIdInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/automation-audit",
)
async def list_automation_audit(
    context: ToolContext, data: AutomationIdInput
) -> dict[str, Any]:
    versions = await _automation_service(context).list_versions(
        context.db,
        user=_required_user(context),
        automation_id=data.automation_id,
    )
    previous: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    for version in sorted(versions, key=lambda item: item.version):
        changed_fields = sorted(
            key
            for key in set(version.definition) | set(previous)
            if version.definition.get(key) != previous.get(key)
        )
        items.append(
            {
                "id": str(version.id),
                "automation_id": str(version.automation_id),
                "version": version.version,
                "actor_id": str(version.created_by) if version.created_by else None,
                "change_summary": version.change_summary,
                "changed_fields": changed_fields,
                "created_at": version.created_at.isoformat()
                if version.created_at
                else None,
            }
        )
        previous = version.definition
    return {
        "items": list(reversed(items)),
        "artifact": {
            "type": "audit_diff",
            "auditId": str(data.automation_id),
        },
    }


@agent_tool(
    name="agent.update_automation",
    summary="修改 Livzon 自动化定义",
    input_model=AutomationUpdateInput,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="PUT",
    path="/agent/automations/{automation_id}",
)
async def update_automation(
    context: ToolContext, data: AutomationUpdateInput
) -> dict[str, Any]:
    automation = await _automation_service(context).update_automation(
        context.db,
        user=_required_user(context),
        automation_id=data.automation_id,
        request=AgentAutomationUpdate.model_validate(
            data.model_dump(exclude={"automation_id"})
        ),
    )
    return {"automation": automation.model_dump(mode="json")}


@agent_tool(
    name="agent.set_automation_enabled",
    summary="启用或暂停 Livzon 自动化",
    input_model=AutomationEnabledInput,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="POST",
    path="/agent/automations/{automation_id}/enabled",
)
async def set_automation_enabled(
    context: ToolContext, data: AutomationEnabledInput
) -> dict[str, Any]:
    automation = await _automation_service(context).set_enabled(
        context.db,
        user=_required_user(context),
        automation_id=data.automation_id,
        enabled=data.enabled,
    )
    return {"automation": automation.model_dump(mode="json")}


@agent_tool(
    name="agent.archive_automation",
    summary="归档 Livzon 自动化",
    input_model=AutomationIdInput,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="POST",
    path="/agent/automations/{automation_id}/archive",
)
async def archive_automation(
    context: ToolContext, data: AutomationIdInput
) -> dict[str, Any]:
    automation = await _automation_service(context).archive(
        context.db,
        user=_required_user(context),
        automation_id=data.automation_id,
    )
    return {"automation": automation.model_dump(mode="json")}


@agent_tool(
    name="agent.simulate_automation",
    summary="模拟自动化未来执行窗口，不执行任何业务工具",
    input_model=AgentAutomationSimulationRequest,
    workflow_allowed=False,
    method="POST",
    path="/agent/automations/{automation_id}/schedule-preview",
    supports_dry_run=True,
)
async def simulate_automation(
    context: ToolContext, data: AgentAutomationSimulationRequest
) -> dict[str, Any]:
    result = await _automation_service(context).simulate_schedule(
        context.db,
        user=_required_user(context),
        automation_id=data.automation_id,
        count=data.count,
    )
    return {
        **result,
        "artifact": {
            "type": "automation_detail",
            "automationId": str(data.automation_id),
            "version": result["version"],
        },
    }


@agent_tool(
    name="agent.list_scheduled_triggers",
    summary="查询自动化定时触发",
    input_model=AutomationListInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/scheduled-triggers",
)
async def list_scheduled_triggers(
    context: ToolContext, data: AutomationListInput
) -> dict[str, Any]:
    result = await _automation_service(context).list_scheduled_triggers(
        context.db,
        user=_required_user(context),
        scope=data.scope,
        page=max(1, data.page),
        page_size=min(max(1, data.page_size), 100),
    )
    return result.model_dump(mode="json")


@agent_tool(
    name="agent.list_automation_runs",
    summary="查询自动化运行记录",
    input_model=AutomationListInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/automation-runs",
)
async def list_automation_runs(
    context: ToolContext, data: AutomationListInput
) -> dict[str, Any]:
    result = await _automation_service(context).list_runs(
        context.db,
        user=_required_user(context),
        scope=data.scope,
        status_value=data.status_value,
        page=max(1, data.page),
        page_size=min(max(1, data.page_size), 100),
    )
    return {
        **result.model_dump(mode="json"),
        "artifact": {"type": "run_timeline", "runId": None},
    }


@agent_tool(
    name="agent.get_automation_run",
    summary="查看自动化运行与步骤状态",
    input_model=AutomationRunIdInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/automation-runs/{run_id}",
)
async def get_automation_run(
    context: ToolContext, data: AutomationRunIdInput
) -> dict[str, Any]:
    result = await _automation_service(context).get_run(
        context.db, user=_required_user(context), run_id=data.run_id
    )
    return {
        **result,
        "artifact": {"type": "run_timeline", "runId": str(data.run_id)},
    }


@agent_tool(
    name="agent.get_current_time",
    summary="获取当前精确时间",
    method="GET",
    path="/agent/current-time",
    output_hint=(
        "返回当前北京时间、UTC 时间、日期、星期、Unix 时间戳和定时任务建议时区。"
    ),
)
async def get_current_time(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    local_tz_name = "Asia/Shanghai"
    local_tz = ZoneInfo(local_tz_name)
    utc_now = datetime.now(UTC)
    local_now = utc_now.astimezone(local_tz)

    return {
        "timezone": local_tz_name,
        "utc_offset": local_now.strftime("%z")[:3] + ":" + local_now.strftime("%z")[3:],
        "local_iso": local_now.isoformat(),
        "utc_iso": utc_now.isoformat(),
        "date": local_now.date().isoformat(),
        "time": local_now.strftime("%H:%M:%S"),
        "weekday": local_now.isoweekday(),
        "weekday_name": local_now.strftime("%A"),
        "unix_seconds": int(local_now.timestamp()),
        "unix_milliseconds": int(local_now.timestamp() * 1000),
        "cron_timezone": local_tz_name,
        "usage_hint": "设置每天定时任务时，以 cron_timezone 的本地日期和时间为准。",
    }


@agent_tool(
    name="agent.list_push_deliveries",
    summary="查询我的飞书自动化推送记录",
    input_model=PushDeliveryListInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/push-deliveries",
)
async def list_push_deliveries(
    context: ToolContext, data: PushDeliveryListInput
) -> dict[str, Any]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return await PushDeliveryService().list_for_user(
        context.db,
        user=_required_user(context),
        status_value=data.status_value,
        page=max(1, data.page),
        page_size=min(max(1, data.page_size), 100),
    )


@agent_tool(
    name="agent.get_push_delivery",
    summary="查看单条飞书自动化推送记录",
    input_model=PushDeliveryIdInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/push-deliveries/{delivery_id}",
)
async def get_push_delivery(
    context: ToolContext, data: PushDeliveryIdInput
) -> dict[str, Any]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    try:
        return await PushDeliveryService().get_for_user(
            context.db,
            user=_required_user(context),
            delivery_id=data.delivery_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@agent_tool(
    name="agent.list_domain_events",
    summary="按关联 ID 追踪跨模块事件链路",
    input_model=CorrelationIdInput,
    workflow_allowed=False,
    method="GET",
    path="/agent/domain-events/{correlation_id}",
)
async def list_domain_events(
    context: ToolContext, data: CorrelationIdInput
) -> list[dict[str, Any]]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return await AgentDomainEventService().list_for_user(
        context.db,
        user=_required_user(context),
        correlation_id=data.correlation_id,
    )


@agent_tool(
    name="agent.list_automation_capability_impacts",
    summary="扫描受弃用或不兼容能力影响的自动化",
    workflow_allowed=False,
    method="GET",
    path="/agent/automation-capability-impacts",
)
async def list_automation_capability_impacts(
    context: ToolContext, _: BaseModel
) -> list[dict[str, Any]]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return await AgentAutomationService().list_capability_impacts(
        context.db, user=_required_user(context)
    )


@agent_tool(
    name="agent.complete_manual_task",
    summary="完成自动化中的人工待办并恢复运行",
    input_model=ManualTaskCompleteInput,
    write=True,
    risk_level="medium",
    workflow_allowed=False,
    method="POST",
    path="/agent/manual-tasks/{run_id}/complete",
)
async def complete_manual_task(
    context: ToolContext, data: ManualTaskCompleteInput
) -> dict[str, Any]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return await AgentManualTaskService().complete(
        context.db, user=_required_user(context), run_id=data.run_id
    )


@agent_tool(
    name="agent.get_automation_health",
    summary="查看自动化健康评分",
    workflow_allowed=False,
    method="GET",
    path="/agent/operations/health",
)
async def get_automation_health(
    context: ToolContext, _: BaseModel
) -> list[dict[str, Any]]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return await AgentOperationsService().health(
        context.db, user=_required_user(context)
    )


@agent_tool(
    name="agent.get_automation_trends",
    summary="查看自动化失败、积压和推送趋势",
    workflow_allowed=False,
    method="GET",
    path="/agent/operations/trends",
)
async def get_automation_trends(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return await AgentOperationsService().trends(
        context.db, user=_required_user(context)
    )


@agent_tool(
    name="agent.list_automation_templates",
    summary="查看自动化模板与可复用子流程",
    workflow_allowed=False,
    method="GET",
    path="/agent/operations/templates",
)
async def list_automation_templates(
    context: ToolContext, _: BaseModel
) -> list[dict[str, Any]]:
    return AgentOperationsService.templates()


@agent_tool(
    name="agent.list_automation_suggestions",
    summary="查看有运行证据的优化建议",
    workflow_allowed=False,
    method="GET",
    path="/agent/operations/suggestions",
)
async def list_automation_suggestions(
    context: ToolContext, _: BaseModel
) -> list[dict[str, Any]]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return await AgentOperationsService().suggestions(
        context.db, user=_required_user(context)
    )


@agent_tool(
    name="agent.get_operations_report",
    summary="生成管理员运营报告",
    workflow_allowed=False,
    method="GET",
    path="/agent/operations/report",
)
async def get_operations_report(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    if context.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return await AgentOperationsService().admin_report(
        context.db, user=_required_user(context)
    )
