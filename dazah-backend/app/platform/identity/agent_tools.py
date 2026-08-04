from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings
from app.modules.agent.tools import ToolContext, agent_tool
from app.platform.identity.models import Department
from app.platform.identity.repository import DepartmentRepository, UserRepository
from app.platform.identity.schemas import DepartmentTreeNode, PersonnelItem
from app.platform.identity.service import diagnose_livzon_feishu_config


class PersonnelSearchInput(BaseModel):
    keyword: str | None = Field(default=None, max_length=100)
    department_id: str | None = Field(default=None, max_length=128)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class FeishuDeliveryInput(BaseModel):
    recipient_user_ids: list[UUID] = Field(min_length=1, max_length=50)
    message_form: Literal["card", "text"] = "card"
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1, max_length=20_000)
    actions: list[dict[str, Any]] = Field(default_factory=list, max_length=5)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_message_form(self) -> "FeishuDeliveryInput":
        if self.message_form == "text" and self.actions:
            raise ValueError("text delivery does not support actions")
        return self


def _build_tree(
    departments: list[Department],
    parent_id: str | None = None,
) -> list[DepartmentTreeNode]:
    nodes: list[DepartmentTreeNode] = []
    for department in departments:
        if department.parent_feishu_department_id == parent_id or (
            parent_id is None and not department.parent_feishu_department_id
        ):
            nodes.append(
                DepartmentTreeNode(
                    id=department.id,
                    feishu_department_id=department.feishu_department_id,
                    name=department.name,
                    member_count=department.member_count,
                    leader_user_id=department.leader_user_id,
                    order=department.order,
                    children=_build_tree(
                        departments,
                        department.feishu_department_id,
                    ),
                )
            )
    return nodes


@agent_tool(
    name="identity.get_department_tree",
    summary="查询已同步的飞书部门树",
    method="GET",
    path="/identity/departments?tree=true",
)
async def get_department_tree(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    departments = await DepartmentRepository().list_all(context.db)
    return {
        "departments": [
            node.model_dump(mode="json")
            for node in _build_tree(departments, parent_id=None)
        ]
    }


@agent_tool(
    name="identity.search_personnel",
    summary="查询已同步的飞书人员",
    input_model=PersonnelSearchInput,
    method="GET",
    path="/identity/personnel",
)
async def search_personnel(
    context: ToolContext,
    data: PersonnelSearchInput,
) -> dict[str, Any]:
    users, total = await UserRepository().list_all(
        context.db,
        department_id=data.department_id,
        keyword=data.keyword,
        offset=data.offset,
        limit=data.limit,
    )
    return {
        "items": [
            PersonnelItem.model_validate(user).model_dump(mode="json") for user in users
        ],
        "total": total,
        "offset": data.offset,
        "limit": data.limit,
    }


@agent_tool(
    name="identity.check_feishu_permissions",
    summary="诊断飞书应用 Scope 和资源可见性",
    required_roles=("admin",),
    method="POST",
    path="/identity/feishu-config/test",
)
async def check_feishu_permissions(
    context: ToolContext,
    _: BaseModel,
) -> dict[str, Any]:
    result = await diagnose_livzon_feishu_config(context.db)
    return result.model_dump(mode="json")


@agent_tool(
    name="identity.deliver_feishu_message",
    summary="通过 Hermes Delivery API 主动投递飞书消息",
    input_model=FeishuDeliveryInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/internal/feishu/deliveries",
    idempotent=True,
)
async def deliver_feishu_message(
    context: ToolContext,
    data: FeishuDeliveryInput,
) -> dict[str, Any]:
    settings = get_settings()
    base_url = settings.HERMES_INTERNAL_URL.rstrip("/")
    token = settings.HERMES_INTERNAL_TOKEN
    if not base_url or not token:
        raise RuntimeError("Hermes Delivery API is not configured")

    repo = UserRepository()
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for recipient_user_id in data.recipient_user_ids:
            user = await repo.get_by_id(context.db, recipient_user_id)
            if (
                user is None
                or user.is_deleted
                or user.status != "active"
                or not user.feishu_open_id
            ):
                results.append(
                    {
                        "recipient_user_id": str(recipient_user_id),
                        "status": "rejected",
                        "reason": "recipient_unavailable",
                    }
                )
                continue
            delivery_body: dict[str, Any]
            if data.message_form == "text":
                delivery_body = {"content": data.markdown}
            else:
                card: dict[str, Any] = {
                    "schema": "2.0",
                    "header": {
                        "title": {"tag": "plain_text", "content": data.title}
                    },
                    "body": {
                        "elements": [{"tag": "markdown", "content": data.markdown}]
                    },
                }
                if data.actions:
                    card["body"]["elements"].append(
                        {
                            "tag": "action",
                            "actions": [
                                {
                                    "tag": "button",
                                    "text": {
                                        "tag": "plain_text",
                                        "content": str(action.get("label") or "查看"),
                                    },
                                    "value": {
                                        **action,
                                        "resource_domain": "dazah_business",
                                        "trace_id": str(
                                            context.raw_request.trace_id or ""
                                        ),
                                    },
                                }
                                for action in data.actions
                            ],
                        }
                    )
                delivery_body = {"card": card}
            response = await client.post(
                f"{base_url}/internal/feishu/deliveries",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "idempotency_key": (f"{data.idempotency_key}:{recipient_user_id}")[
                        :128
                    ],
                    "chat_id": user.feishu_open_id,
                    **delivery_body,
                    "metadata": {
                        "trace_id": str(context.raw_request.trace_id or ""),
                        "recipient_user_id": str(recipient_user_id),
                        "receive_id_type": "open_id",
                    },
                },
            )
            response.raise_for_status()
            result = response.json()
            results.append(
                {
                    "recipient_user_id": str(recipient_user_id),
                    "status": result.get("status"),
                    "delivery_id": result.get("id"),
                }
            )
    return {"results": results}
