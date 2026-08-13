from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.agent.schemas import AgentTrustedSubject


class InteractionFormField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=120)
    type: Literal["text", "number", "date", "single_select", "multi_select", "boolean"]
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_options(self) -> InteractionFormField:
        if self.type in {"single_select", "multi_select"} and not self.options:
            raise ValueError("选择字段必须提供 options")
        return self


class FeishuResourceTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    resource_type: Literal["bitable", "sheet"] = "bitable"
    resource_url: str = Field(min_length=1, max_length=2000)
    base_token: str = Field(min_length=1, max_length=255)
    table_id: str = Field(min_length=1, max_length=255)
    sheet_range: str | None = Field(default=None, min_length=2, max_length=255)
    view_id: str | None = Field(default=None, max_length=255)
    view_type: Literal["grid", "form"] = "grid"
    field_schema: list[InteractionFormField] = Field(
        default_factory=list, max_length=100
    )
    writable_fields: list[str] = Field(default_factory=list, max_length=100)
    record_mode: Literal["append"] = "append"

    @field_validator("resource_url")
    @classmethod
    def validate_feishu_url(cls, value: str) -> str:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host.endswith(
            (".feishu.cn", ".larksuite.com")
        ):
            raise ValueError("resource_url 必须是可信飞书 HTTPS 地址")
        return value

    @model_validator(mode="after")
    def validate_writable_fields(self) -> FeishuResourceTemplateCreate:
        declared = {field.key for field in self.field_schema}
        unknown = sorted(set(self.writable_fields) - declared)
        if unknown:
            raise ValueError(f"可写字段未在 field_schema 声明: {', '.join(unknown)}")
        if self.resource_type == "sheet" and not self.sheet_range:
            raise ValueError("电子表格模板必须配置 sheet_range")
        if self.resource_type == "sheet" and self.writable_fields:
            raise ValueError("电子表格首版仅支持链接与范围回读，不开放表单写入")
        return self


class FeishuResourceTemplateOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID | None
    name: str
    resource_type: str
    resource_url: str
    view_id: str | None = None
    view_type: str
    field_schema: list[dict[str, Any]] = Field(default_factory=list)
    writable_fields: list[str] = Field(default_factory=list)
    record_mode: str
    status: str
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    validated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InteractionRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: uuid.UUID
    recipient_user_id: uuid.UUID
    mode: Literal["card_form", "table_link"]
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=2000)
    form_schema: list[InteractionFormField] = Field(default_factory=list, max_length=50)
    prefill: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=240)
    automation_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    step_key: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_mode(self) -> InteractionRequestCreate:
        if self.mode == "card_form" and not self.form_schema:
            raise ValueError("card_form 必须提供表单字段")
        if self.mode == "table_link" and not any(
            field.required for field in self.form_schema
        ):
            raise ValueError("table_link 必须配置至少一个回读关键字段")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at 必须包含时区")
        return self


class InteractionArtifact(BaseModel):
    type: Literal["form", "table_link"]
    request_id: uuid.UUID
    version: int
    title: str
    summary: str | None = None
    status: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    form_schema: list[dict[str, Any]] = Field(default_factory=list)
    table_resource: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime
    automation_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None


class InteractionSubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: int = Field(ge=1)
    values: dict[str, Any] = Field(default_factory=dict, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=240)


class InternalFeishuInteractionSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: AgentTrustedSubject
    submission: InteractionSubmissionCreate


class InteractionRequestPage(BaseModel):
    items: list[InteractionArtifact] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
