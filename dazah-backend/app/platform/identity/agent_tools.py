from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.agent.tools import ToolContext, agent_tool
from app.platform.identity.models import Department
from app.platform.identity.repository import DepartmentRepository, UserRepository
from app.platform.identity.schemas import DepartmentTreeNode, PersonnelItem
from app.platform.identity.service import (
    diagnose_livzon_feishu_config,
    send_livzon_feishu_card_message,
    send_livzon_feishu_message,
    send_livzon_feishu_text_message,
)

RECIPIENT_ALIASES = (
    "recipient",
    "recipients",
    "recipient_id",
    "recipient_ids",
    "recipient_user_id",
    "recipient_user_ids",
    "to",
    "to_user",
    "to_users",
    "to_user_id",
    "to_user_ids",
    "user_id",
    "feishu_id",
    "feishu_user_id",
    "feishu_user_ids",
    "feishu_open_id",
    "feishu_open_ids",
    "open_id",
    "open_ids",
    "employee_no",
    "employee_nos",
)

RECIPIENT_OBJECT_KEYS = (
    "id",
    "user_id",
    "feishu_id",
    "feishu_user_id",
    "feishu_open_id",
    "open_id",
    "employee_no",
    "name",
)

TEXT_ALIASES = (
    "content",
    "message",
    "message_content",
    "body_text",
)

# These are model placeholders, not stable identifiers.  Rejecting them before
# a write confirmation is created keeps an invalid card from reaching the
# recipient-resolution step after the user has already approved it.
GENERIC_RECIPIENT_PLACEHOLDERS = frozenset(
    {
        "user",
        "users",
        "recipient",
        "recipients",
        "当前用户",
        "当前会话用户",
        "用户",
        "收件人",
        "本人",
        "self",
    }
)


def _append_recipient_identifier(result: list[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _append_recipient_identifier(result, item)
        return
    if isinstance(value, dict):
        for key in RECIPIENT_OBJECT_KEYS:
            nested = value.get(key)
            if nested:
                _append_recipient_identifier(result, nested)
                return
        return
    text = str(value).strip()
    if text:
        result.append(text)


def _normalize_recipient_aliases(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    data = dict(value)
    existing_user_ids = data.get("user_ids")
    if existing_user_ids:
        return data

    recipient_ids: list[str] = []
    for key in RECIPIENT_ALIASES:
        if key in data:
            _append_recipient_identifier(recipient_ids, data.get(key))
    if recipient_ids:
        data["user_ids"] = recipient_ids
    return data


def _normalize_text_aliases(value: Any, *, target: str) -> Any:
    if not isinstance(value, dict):
        return value

    data = dict(value)
    if data.get(target):
        return data
    for key in TEXT_ALIASES:
        alias_value = data.get(key)
        if isinstance(alias_value, str) and alias_value.strip():
            data[target] = alias_value.strip()
            break
    return data


class PersonnelSearchInput(BaseModel):
    keyword: str | None = Field(default=None, max_length=100)
    department_id: str | None = Field(default=None, max_length=128)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class FeishuMessageRecipientsInput(BaseModel):
    user_ids: list[str] = Field(
        min_length=1,
        max_length=50,
        description=(
            "收件人标识。可填本地用户 UUID、飞书 user_id、飞书 open_id、工号、"
            "手机号、邮箱或姓名。不得填写 user、当前用户、收件人等占位词；"
            "不确定时先调用 identity.search_personnel 查询并使用返回的明确标识。"
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_recipient_aliases(cls, value: Any) -> Any:
        return _normalize_recipient_aliases(value)

    @field_validator("user_ids", mode="before")
    @classmethod
    def normalize_user_ids(cls, value: Any) -> Any:
        if value is None:
            return value
        if not isinstance(value, list):
            value = [value]
        normalized = [
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        ]
        placeholders = [
            identifier
            for identifier in normalized
            if identifier.casefold() in GENERIC_RECIPIENT_PLACEHOLDERS
        ]
        if placeholders:
            raise ValueError(
                "user_ids 必须使用已同步人员的明确标识，不能使用占位词："
                + "、".join(placeholders)
            )
        return normalized


class FeishuTextMessageInput(FeishuMessageRecipientsInput):
    text: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="before")
    @classmethod
    def normalize_text_aliases(cls, value: Any) -> Any:
        return _normalize_text_aliases(value, target="text")


class FeishuCardMessageInput(FeishuMessageRecipientsInput):
    title: str = Field(min_length=1, max_length=100)
    markdown: str = Field(min_length=1, max_length=4000)
    header_template: Literal["blue", "green", "orange", "red", "purple"] = "blue"
    button_text: str | None = Field(default=None, max_length=80)
    button_url: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def normalize_markdown_aliases(cls, value: Any) -> Any:
        return _normalize_text_aliases(value, target="markdown")

    @model_validator(mode="after")
    def validate_button(self) -> "FeishuCardMessageInput":
        if bool(self.button_text) != bool(self.button_url):
            raise ValueError("button_text 和 button_url 必须同时提供")
        if self.button_url and not self.button_url.startswith(("http://", "https://")):
            raise ValueError("button_url 必须是 http 或 https 链接")
        return self


class FeishuBusinessActionInput(BaseModel):
    action_key: Literal[
        "start_processing",
        "mark_done",
        "reject",
        "acknowledge",
    ]
    label: str | None = Field(default=None, max_length=100)
    button_type: Literal["primary", "default", "danger"] = "primary"


class FeishuUnifiedMessageInput(FeishuMessageRecipientsInput):
    text: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default=None, max_length=100)
    markdown: str | None = Field(default=None, max_length=4000)
    value_level: Literal["low", "medium", "high"] = "low"
    structured: bool = False
    requires_business_action: bool = False
    message_form: Literal["auto", "text", "card", "interactive_card"] = "auto"
    header_template: Literal["blue", "green", "orange", "red", "purple"] = "blue"
    actions: list[FeishuBusinessActionInput] | None = Field(
        default=None,
        max_length=4,
    )
    business_ref: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_text_aliases(cls, value: Any) -> Any:
        return _normalize_text_aliases(value, target="text")


async def _resolve_livzon_message_user_ids(
    context: ToolContext,
    recipient_ids: list[str],
) -> list[UUID]:
    repo = UserRepository()
    resolved: list[UUID] = []
    seen: set[UUID] = set()
    errors: list[str] = []

    for recipient_id in recipient_ids:
        matches = await repo.find_by_livzon_recipient_identifier(
            context.db,
            recipient_id,
        )
        if not matches:
            errors.append(f"{recipient_id} 未匹配到已同步用户")
            continue
        if len(matches) > 1:
            names = "、".join(user.name for user in matches[:5])
            errors.append(f"{recipient_id} 匹配到多个用户：{names}")
            continue
        user_id = matches[0].id
        if user_id not in seen:
            resolved.append(user_id)
            seen.add(user_id)

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "无法解析飞书消息收件人。user_ids 可填写本地用户 UUID、"
                "飞书 user_id、飞书 open_id、工号、手机号、邮箱或姓名；"
                + "；".join(errors)
            ),
        )
    return resolved


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
    summary="查询 Livzon 助手可用的飞书部门树",
    method="GET",
    path="/identity/departments?tree=true",
    output_hint="返回已同步到本地的部门层级树，仅来自 Livzon 助手飞书通讯录同步副本。",
)
async def get_department_tree(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    departments = await DepartmentRepository().list_all(context.db)
    nodes: list[DepartmentTreeNode] = _build_tree(
        departments,
        parent_id=None,
    )
    return {"departments": [node.model_dump(mode="json") for node in nodes]}


@agent_tool(
    name="identity.search_personnel",
    summary="查询 Livzon 助手已同步的飞书人员",
    input_model=PersonnelSearchInput,
    method="GET",
    path="/identity/personnel",
    output_hint="返回姓名、部门、手机号、邮箱和飞书 ID 等本地同步副本字段。",
)
async def search_personnel(
    context: ToolContext, data: PersonnelSearchInput
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
            PersonnelItem.model_validate(user).model_dump(mode="json")
            for user in users
        ],
        "total": total,
        "offset": data.offset,
        "limit": data.limit,
    }


@agent_tool(
    name="identity.check_feishu_permissions",
    summary="诊断 Livzon 助手飞书通讯录权限",
    required_roles=("admin",),
    method="POST",
    path="/identity/feishu-config/test",
    output_hint="通过实际 API 探测当前 Livzon 助手飞书应用的通讯录权限和字段可见性。",
)
async def check_feishu_permissions(
    context: ToolContext, _: BaseModel
) -> dict[str, Any]:
    result = await diagnose_livzon_feishu_config(context.db)
    return result.model_dump(mode="json")


@agent_tool(
    name="identity.send_feishu_message",
    summary="按 Livzon 助手规则向已同步飞书用户发送消息",
    input_model=FeishuUnifiedMessageInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/identity/feishu/messages",
    output_hint=(
        "后端按规则自动选择消息形态：低价值短消息发文本；中高价值或结构化消息发卡片；"
        "user_ids 可填写本地用户 UUID、飞书 user_id、飞书 open_id、"
        "工号、手机号、邮箱或姓名；"
        "需要处理的业务消息发带回传按钮的交互卡片。发送前必须让用户核对收件人、消息形态、"
        "标题/正文摘要和是否包含处理按钮。"
    ),
)
async def send_feishu_message(
    context: ToolContext, data: FeishuUnifiedMessageInput
) -> dict[str, Any]:
    user_ids = await _resolve_livzon_message_user_ids(context, data.user_ids)
    return await send_livzon_feishu_message(
        context.db,
        user_ids=user_ids,
        text=data.text,
        title=data.title,
        markdown=data.markdown,
        value_level=data.value_level,
        structured=data.structured,
        requires_business_action=data.requires_business_action,
        message_form=data.message_form,
        header_template=data.header_template,
        actions=[
            item.model_dump(mode="json", exclude_none=True)
            for item in data.actions or []
        ] or None,
        business_ref=data.business_ref,
    )


@agent_tool(
    name="identity.send_feishu_text_message",
    summary="向已同步飞书用户发送文本消息",
    input_model=FeishuTextMessageInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/identity/feishu/messages/text",
    output_hint=(
        "user_ids 可填写本地用户 UUID、飞书 user_id、飞书 open_id、"
        "工号、手机号、邮箱或姓名；"
        "发送前必须先通过确认项让用户核对收件人和正文；确认后返回每个收件人的"
        "发送状态、message_id 和错误信息。"
    ),
)
async def send_feishu_text_message(
    context: ToolContext, data: FeishuTextMessageInput
) -> dict[str, Any]:
    user_ids = await _resolve_livzon_message_user_ids(context, data.user_ids)
    return await send_livzon_feishu_text_message(
        context.db,
        user_ids=user_ids,
        text=data.text,
    )


@agent_tool(
    name="identity.send_feishu_card_message",
    summary="向已同步飞书用户发送卡片消息",
    input_model=FeishuCardMessageInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/identity/feishu/messages/card",
    output_hint=(
        "user_ids 可填写本地用户 UUID、飞书 user_id、飞书 open_id、"
        "工号、手机号、邮箱或姓名；"
        "发送前必须先通过确认项让用户核对收件人、标题、正文摘要和按钮链接；"
        "确认后返回每个收件人的发送状态、message_id 和错误信息。"
    ),
)
async def send_feishu_card_message(
    context: ToolContext, data: FeishuCardMessageInput
) -> dict[str, Any]:
    user_ids = await _resolve_livzon_message_user_ids(context, data.user_ids)
    return await send_livzon_feishu_card_message(
        context.db,
        user_ids=user_ids,
        title=data.title,
        markdown=data.markdown,
        header_template=data.header_template,
        button_text=data.button_text,
        button_url=data.button_url,
    )
