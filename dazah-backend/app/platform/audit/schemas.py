import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AuditCategory = Literal[
    "permissions",
    "agent_tools",
    "automations",
    "feishu",
    "business",
]


class GeneralAuditLogItem(BaseModel):
    id: uuid.UUID
    category: AuditCategory
    actor_user_id: uuid.UUID | None = None
    actor_name: str | None = None
    actor_username: str | None = None
    action: str
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class GeneralAuditLogDetail(GeneralAuditLogItem):
    request_id: str | None = None
    duration_ms: int | None = None
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    extra: dict[str, Any] | None = None


class GeneralAuditLogPage(BaseModel):
    items: list[GeneralAuditLogItem] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
