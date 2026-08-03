import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

UserRole = Literal["admin", "user"]
UserStatus = Literal["active", "disabled"]
AuthSource = Literal["local", "feishu"]


class ExternalIdentityBindingCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    platform: Literal["feishu"] = "feishu"
    app_fingerprint: str = Field(min_length=1, max_length=255)
    external_user_id: str | None = Field(default=None, max_length=128)
    external_open_id: str | None = Field(default=None, max_length=128)
    external_union_id: str | None = Field(default=None, max_length=128)
    local_user_id: UUID

    @model_validator(mode="after")
    def require_external_identifier(self) -> "ExternalIdentityBindingCreate":
        if not any(
            (self.external_user_id, self.external_open_id, self.external_union_id)
        ):
            raise ValueError("至少需要一个飞书外部用户标识")
        return self


class ExternalIdentityBindingOut(ExternalIdentityBindingCreate):
    id: UUID
    status: Literal["active", "disabled"]
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user: "UserResponse | None" = None


class LocalLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class SSOCallbackResult(BaseModel):
    token: str
    redirect_url: str


class UserResponse(BaseModel):
    id: UUID
    name: str
    username: str | None = None
    role: UserRole = "user"
    status: UserStatus = "active"
    auth_source: AuthSource = "feishu"
    en_name: str | None = None
    email: str | None = None
    enterprise_email: str | None = None
    mobile: str | None = None
    avatar_url: str | None = None
    avatar_thumb: str | None = None
    avatar_middle: str | None = None
    avatar_big: str | None = None
    employee_no: str | None = None
    department: str | None = None
    position: str | None = None
    feishu_user_id: str | None = None
    feishu_open_id: str | None = None
    feishu_union_id: str | None = None
    tenant_key: str | None = None
    grant_version: int = 0
    module_codes: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class UserManagementItem(UserResponse):
    last_login_at: str | None = None

    @field_validator("last_login_at", mode="before")
    @classmethod
    def datetime_to_str(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class UserManagementListResponse(BaseModel):
    items: list[UserManagementItem]
    total: int
    offset: int
    limit: int


class LocalUserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=255)
    name: str = Field(..., min_length=1, max_length=100)
    email: str | None = Field(None, max_length=255)
    mobile: str | None = Field(None, max_length=32)
    employee_no: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=200)
    position: str | None = Field(None, max_length=200)
    role: UserRole = "user"
    status: UserStatus = "active"


class UserManagementUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, max_length=255)
    mobile: str | None = Field(None, max_length=32)
    employee_no: str | None = Field(None, max_length=64)
    department: str | None = Field(None, max_length=200)
    position: str | None = Field(None, max_length=200)
    role: UserRole | None = None
    status: UserStatus | None = None


class PasswordResetRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=255)


ModulePermissionKey = Literal[
    "module.view",
    "module.agent.read",
    "module.agent.execute",
    "module.agent.automate",
    "module.admin",
]


class ModulePermissionGrantInput(BaseModel):
    module_code: str = Field(min_length=1, max_length=64)
    permissions: list[ModulePermissionKey] = Field(default_factory=list)
    data_scope: dict[str, Any] = Field(default_factory=dict)


class UserModulePermissionsUpdate(BaseModel):
    expected_grant_version: int | None = Field(default=None, ge=0)
    grants: list[ModulePermissionGrantInput] = Field(
        default_factory=list, max_length=100
    )
    reason: str = Field(min_length=1, max_length=500)


class ModulePermissionGrantOut(BaseModel):
    module_code: str
    module_name: str
    permissions: list[ModulePermissionKey] = Field(default_factory=list)
    data_scope: dict[str, Any] = Field(default_factory=dict)
    grant_version: int
    granted_by: UUID
    status: str
    updated_at: datetime


class ModulePermissionDefinitionOut(BaseModel):
    module_code: str
    module_name: str
    description: str


class UserModulePermissionsOut(BaseModel):
    user_id: UUID
    grant_version: int
    available_modules: list[ModulePermissionDefinitionOut] = Field(default_factory=list)
    grants: list[ModulePermissionGrantOut] = Field(default_factory=list)
    livzon_sync_status: str | None = None
    livzon_source_grant_version: int | None = None
    livzon_agent_scope_version: int | None = None
    livzon_last_error: str | None = None


class PermissionAuditItem(BaseModel):
    id: UUID
    actor_user_id: UUID | None = None
    action: str
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    reason: str | None = None
    grant_version: int | None = None
    created_at: datetime


class LivzonModuleScopeOut(BaseModel):
    module_code: str
    module_name: str
    permissions: list[str] = Field(default_factory=list)
    data_scope: dict[str, Any] = Field(default_factory=dict)


class LivzonAccessScopeOut(BaseModel):
    user_id: UUID
    source_grant_version: int
    agent_scope_version: int
    registry_version: str
    sync_status: str
    synced_at: datetime | None = None
    last_error: str | None = None
    modules: list[LivzonModuleScopeOut] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    workflow_tool_names: list[str] = Field(default_factory=list)


# ── Department ──────────────────────────────────────────────────────


class DepartmentResponse(BaseModel):
    id: UUID
    feishu_department_id: str
    name: str
    parent_feishu_department_id: str | None = None
    leader_user_id: str | None = None
    member_count: int | None = None
    status_is_deleted: bool | None = None
    path: str | None = None
    order: int | None = None

    @field_validator("path", mode="before")
    @classmethod
    def path_to_str(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, list | dict):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    model_config = {"from_attributes": True}


class DepartmentTreeNode(BaseModel):
    """组织架构树节点（含子部门）"""

    id: UUID
    feishu_department_id: str
    name: str
    member_count: int | None = None
    leader_user_id: str | None = None
    order: int | None = None
    children: list["DepartmentTreeNode"] = []

    model_config = {"from_attributes": True}


# ── Personnel ───────────────────────────────────────────────────────


class PersonnelItem(BaseModel):
    """人员列表项"""

    id: UUID
    name: str
    en_name: str | None = None
    employee_no: str | None = None
    email: str | None = None
    enterprise_email: str | None = None
    mobile: str | None = None
    department: str | None = None
    position: str | None = None
    feishu_user_id: str | None = None
    feishu_open_id: str | None = None
    feishu_union_id: str | None = None
    avatar_url: str | None = None
    avatar_thumb: str | None = None
    avatar_middle: str | None = None
    avatar_big: str | None = None
    tenant_key: str | None = None
    feishu_department_ids: list[str] | None = None

    @field_validator("feishu_department_ids", mode="before")
    @classmethod
    def parse_dept_ids(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, list):
            if all(isinstance(item, str) for item in v):
                return v
            raise ValueError("feishu_department_ids 必须是字符串列表")
        if isinstance(v, str):
            try:
                parsed: Any = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
            if isinstance(parsed, list) and all(
                isinstance(item, str) for item in parsed
            ):
                return parsed
            if isinstance(parsed, list):
                raise ValueError("feishu_department_ids 必须是字符串列表")
        return None

    model_config = {"from_attributes": True}


class PersonnelListResponse(BaseModel):
    """人员分页列表"""

    items: list[PersonnelItem]
    total: int
    offset: int
    limit: int


# ── Livzon Assistant Feishu Config ─────────────────────────────────


class FeishuConfigUpsert(BaseModel):
    config_name: str = Field(
        default="Livzon 助手飞书设置",
        min_length=1,
        max_length=128,
        description="配置名称，仅用于 Livzon 助手",
    )
    app_id: str = Field(..., min_length=1, max_length=128)
    app_secret: str | None = Field(default=None, max_length=500)
    tenant_id: str = Field(default="default", min_length=1, max_length=128)
    gateway_enabled: bool = True
    sync_root_department_id: str | None = Field(default=None, max_length=128)
    sync_member_department_id: str | None = Field(default=None, max_length=128)
    is_active: bool = True

    @field_validator(
        "config_name",
        "app_id",
        "app_secret",
        "tenant_id",
        "sync_root_department_id",
        "sync_member_department_id",
        mode="before",
    )
    @classmethod
    def clean_text(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value


class FeishuConfigResponse(BaseModel):
    id: UUID | None = None
    config_name: str = "Livzon 助手飞书设置"
    app_id: str = ""
    tenant_id: str = "default"
    gateway_enabled: bool = True
    config_version: int = 0
    app_secret_configured: bool = False
    app_secret_masked: str = ""
    sync_root_department_id: str | None = None
    sync_member_department_id: str | None = None
    is_active: bool = True
    last_sync_status: str | None = None
    last_sync_message: str | None = None
    last_synced_at: str | None = None
    last_diagnostic_status: str | None = None
    last_diagnostic_message: str | None = None
    last_diagnostic_result: str | None = None
    last_diagnosed_at: str | None = None

    @field_validator("last_synced_at", "last_diagnosed_at", mode="before")
    @classmethod
    def datetime_to_str(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)


class FeishuDiagnosticStep(BaseModel):
    name: str
    status: Literal["ok", "warning", "error"]
    message: str
    suggestion: str | None = None
    code: int | None = None


class FeishuDiagnosticResult(BaseModel):
    status: Literal["ok", "warning", "error"]
    message: str
    steps: list[FeishuDiagnosticStep]
    department_count: int = 0
    sample_user_count: int = 0


class FeishuConfigApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: FeishuConfigResponse


class FeishuDiagnosticApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: FeishuDiagnosticResult
