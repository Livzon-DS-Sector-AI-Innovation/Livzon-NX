import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

UserRole = Literal["admin", "user"]
UserStatus = Literal["active", "disabled"]
AuthSource = Literal["local", "feishu"]
PagePermissionLevel = Literal["access", "query", "operate"]
PageGrantMode = Literal["inherit", "custom"]
PageScopeType = Literal[
    "not_applicable", "department_tree", "departments", "all", "self"
]


class PageDataScopeInput(BaseModel):
    scope_type: PageScopeType = "department_tree"
    department_ids: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("department_ids", mode="after")
    @classmethod
    def clean_department_ids(cls: Any, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @model_validator(mode="after")
    def validate_selected_departments(self) -> "PageDataScopeInput":
        if self.scope_type == "departments" and not self.department_ids:
            raise ValueError("指定部门范围至少选择一个部门")
        if self.scope_type != "departments" and self.department_ids:
            raise ValueError("仅指定部门范围可以提交 department_ids")
        return self


class EffectivePageGrantOut(BaseModel):
    page_key: str
    module_code: str
    permissions: list[PagePermissionLevel] = Field(default_factory=list)
    sensitive_actions: list[str] = Field(default_factory=list)
    data_scope: PageDataScopeInput
    source: Literal["super_admin", "user", "role", "none"]
    source_role_names: list[str] = Field(default_factory=list)


class ExternalIdentityBindingCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    platform: Literal["feishu"] = "feishu"
    app_fingerprint: str = Field(min_length=1, max_length=255)
    external_user_id: str | None = Field(default=None, max_length=128)
    external_open_id: str | None = Field(default=None, max_length=128)
    external_union_id: str | None = Field(default=None, max_length=128)
    local_user_id: UUID
    source: Literal["admin", "directory_sync", "oauth"] = "admin"

    @model_validator(mode="after")
    def require_external_identifier(self) -> "ExternalIdentityBindingCreate":
        if not any(
            (self.external_user_id, self.external_open_id, self.external_union_id)
        ):
            raise ValueError("至少需要一个飞书外部用户标识")
        return self


class ExternalIdentityBindingOut(ExternalIdentityBindingCreate):
    id: UUID
    status: Literal["active", "suspended", "revoked"]
    last_seen_at: datetime | None = None
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    local_user_name: str | None = None
    local_user_department: str | None = None
    local_user_status: str | None = None

    @field_validator("source", mode="before")
    @classmethod
    def normalize_legacy_source(cls: Any, value: object) -> object:
        if value == "identity.users":
            return "directory_sync"
        return value

    model_config = {"from_attributes": True}


class ExternalIdentityBindingStatusUpdate(BaseModel):
    status: Literal["active", "suspended", "revoked"]


class ExternalIdentityConflictOut(BaseModel):
    local_user_id: UUID
    local_user_name: str
    department: str | None = None
    external_identifier: str
    conflict_type: Literal["external_owned_by_other", "local_binding_mismatch"]
    conflicting_binding_id: UUID


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
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    page_permissions: list[EffectivePageGrantOut] = Field(default_factory=list)
    page_permission_rollouts: dict[str, str] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class UserManagementItem(UserResponse):
    last_login_at: str | None = None

    @field_validator("last_login_at", mode="before")
    @classmethod
    def datetime_to_str(cls: Any, v: object) -> str | None:
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


class PageGrantInput(BaseModel):
    page_key: str = Field(min_length=1, max_length=255)
    mode: PageGrantMode = "custom"
    permissions: list[PagePermissionLevel] = Field(default_factory=list, max_length=3)
    sensitive_actions: list[str] = Field(default_factory=list, max_length=100)
    data_scope: PageDataScopeInput = Field(default_factory=PageDataScopeInput)


class UserPagePermissionsUpdate(BaseModel):
    expected_grant_version: int | None = Field(default=None, ge=0)
    grants: list[PageGrantInput] = Field(default_factory=list, max_length=1000)
    reason: str = Field(min_length=1, max_length=500)


class RolePagePermissionsUpdate(BaseModel):
    expected_grant_version: int = Field(ge=0)
    grants: list[PageGrantInput] = Field(default_factory=list, max_length=1000)
    reason: str = Field(min_length=1, max_length=500)


class SensitiveActionDefinitionOut(BaseModel):
    key: str
    name: str
    category: Literal[
        "decision",
        "destructive",
        "bulk_change",
        "sensitive_export",
        "integration_admin",
        "permission_admin",
    ]
    description: str


class PagePermissionDefinitionOut(BaseModel):
    page_key: str
    module_code: str
    page_name: str
    route_path: str
    supported_scope_types: list[PageScopeType] = Field(default_factory=list)
    sensitive_actions: list[SensitiveActionDefinitionOut] = Field(default_factory=list)


class UserPagePermissionsOut(BaseModel):
    user_id: UUID
    grant_version: int
    definitions: list[PagePermissionDefinitionOut] = Field(default_factory=list)
    grants: list[EffectivePageGrantOut] = Field(default_factory=list)
    role_grants: list[EffectivePageGrantOut] = Field(default_factory=list)
    custom_page_keys: list[str] = Field(default_factory=list)
    module_rollouts: dict[str, str] = Field(default_factory=dict)


class RolePagePermissionsOut(BaseModel):
    role_id: UUID
    grant_version: int
    definitions: list[PagePermissionDefinitionOut] = Field(default_factory=list)
    grants: list[EffectivePageGrantOut] = Field(default_factory=list)


class PagePermissionSimulationRequest(BaseModel):
    user_id: UUID
    page_key: str = Field(min_length=1, max_length=255)
    permission: PagePermissionLevel
    sensitive_action: str | None = Field(default=None, max_length=128)


class PagePermissionSimulationOut(BaseModel):
    allowed: bool
    reason: str
    effective: EffectivePageGrantOut | None = None


class PermissionModuleRolloutOut(BaseModel):
    module_code: str
    status: Literal["legacy", "draft", "enforced"]
    version: int
    published_at: datetime | None = None
    published_by: UUID | None = None
    last_reason: str | None = None


class PermissionModuleRolloutPreviewOut(BaseModel):
    module_code: str
    current_status: Literal["legacy", "draft", "enforced"]
    current_version: int
    preview_hash: str
    page_count: int
    user_count: int
    users_without_access: int
    catalog_gaps: list[str] = Field(default_factory=list)


class PermissionModulePublishRequest(BaseModel):
    expected_version: int = Field(ge=0)
    preview_hash: str = Field(min_length=16, max_length=128)
    reason: str = Field(min_length=1, max_length=500)
    confirmed: Literal[True]


class PermissionModuleRollbackRequest(BaseModel):
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    confirmed: Literal[True]


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
    def path_to_str(cls: Any, v: object) -> str | None:
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
    def parse_dept_ids(cls: Any, v: object) -> list[str] | None:
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
    allowed_group_chat_ids: list[str] = Field(default_factory=list, max_length=200)
    require_group_mention: bool = True
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
    def clean_text(cls: Any, value: object) -> object:
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
    allowed_group_chat_ids: list[str] = Field(default_factory=list)
    require_group_mention: bool = True
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
    updated_at: str | None = None
    updated_by: UUID | None = None

    @field_validator(
        "last_synced_at",
        "last_diagnosed_at",
        "updated_at",
        mode="before",
    )
    @classmethod
    def datetime_to_str(cls: Any, value: object) -> str | None:
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


class FeishuGatewayRestartResult(BaseModel):
    status: Literal["connected"]
    message: str
    previous_reconnects: int = Field(ge=0)
    gateway_reconnects: int = Field(ge=1)
    credential_version: int | None = None
    config_version: int = Field(ge=0)


class FeishuConfigApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: FeishuConfigResponse


class FeishuDiagnosticApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: FeishuDiagnosticResult


class FeishuGatewayRestartApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: FeishuGatewayRestartResult


# ── RBAC / system permission management ────────────────────────────


class RoleResponse(BaseModel):
    id: UUID
    name: str
    code: str
    description: str | None = None
    is_system: bool = False
    permissions: list[str] = Field(default_factory=list)
    grant_version: int = 0

    model_config = {"from_attributes": True}


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    description: str | None = Field(default=None, max_length=255)


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class RolePermissionsRequest(BaseModel):
    permission_ids: list[UUID] = Field(default_factory=list, max_length=500)


class PermissionResponse(BaseModel):
    id: UUID
    code: str
    module: str
    action: str
    name: str
    description: str | None = None

    model_config = {"from_attributes": True}


class UserRolesResponse(BaseModel):
    user: UserResponse
    roles: list[RoleResponse] = Field(default_factory=list)


class AssignUserRoleRequest(BaseModel):
    role_ids: list[UUID] = Field(default_factory=list, max_length=200)


class DeptRuleCreateRequest(BaseModel):
    role_id: UUID
    feishu_department_id: str | None = Field(default=None, max_length=64)
    department_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_department_selector(self) -> "DeptRuleCreateRequest":
        if not self.feishu_department_id and not self.department_name:
            raise ValueError("feishu_department_id 与 department_name 至少提供一个")
        return self


class DeptRuleResponse(BaseModel):
    id: UUID
    role_id: UUID
    role_name: str | None = None
    role_code: str | None = None
    feishu_department_id: str | None = None
    department_name: str | None = None

    model_config = {"from_attributes": True}


class MenuCreateRequest(BaseModel):
    key: str | None = Field(default=None, max_length=128)
    parent_id: UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    type: Literal["directory", "menu", "button"]
    permission_code: str | None = Field(default=None, max_length=128)
    route_path: str | None = Field(default=None, max_length=255)
    component_path: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    status: Literal["active", "disabled"] = "active"


class MenuUpdateRequest(BaseModel):
    key: str | None = Field(default=None, max_length=128)
    parent_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: Literal["directory", "menu", "button"] | None = None
    permission_code: str | None = Field(default=None, max_length=128)
    route_path: str | None = Field(default=None, max_length=255)
    component_path: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int | None = Field(default=None, ge=0, le=1_000_000)
    status: Literal["active", "disabled"] | None = None


class MenuResponse(BaseModel):
    id: UUID
    key: str | None = None
    parent_id: UUID | None = None
    name: str
    type: str
    permission_code: str | None = None
    route_path: str | None = None
    component_path: str | None = None
    icon: str | None = None
    sort_order: int = 0
    status: str = "active"

    model_config = {"from_attributes": True}


class RoleMenusRequest(BaseModel):
    menu_ids: list[UUID] = Field(default_factory=list, max_length=500)


class RoleMenusResponse(BaseModel):
    role_id: UUID
    menu_ids: list[UUID] = Field(default_factory=list)


class DataScopeRuleCreateRequest(BaseModel):
    role_id: UUID | None = None
    user_id: UUID | None = None
    scope_type: Literal["all", "departments"]
    department_names: list[str] | None = None

    @field_validator("department_names", mode="after")
    @classmethod
    def clean_department_names(cls: Any, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        names = [item.strip() for item in value if item and item.strip()]
        return names or None

    @model_validator(mode="after")
    def validate_scope_target(self) -> "DataScopeRuleCreateRequest":
        if (self.role_id is None) == (self.user_id is None):
            raise ValueError("role_id 与 user_id 必须二选一")
        if self.scope_type == "departments" and not self.department_names:
            raise ValueError("scope_type=departments 时必须提供 department_names")
        return self


class DataScopeRuleUpdateRequest(BaseModel):
    scope_type: Literal["all", "departments"] | None = None
    department_names: list[str] | None = None

    @field_validator("department_names", mode="after")
    @classmethod
    def clean_department_names(cls: Any, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        names = [item.strip() for item in value if item and item.strip()]
        return names or None


class DataScopeRuleResponse(BaseModel):
    id: UUID
    role_id: UUID | None = None
    user_id: UUID | None = None
    scope_type: str
    department_names: list[str] = Field(default_factory=list)

    @field_validator("department_names", mode="before")
    @classmethod
    def parse_department_names(cls: Any, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return []
            return [str(item) for item in parsed] if isinstance(parsed, list) else []
        return []


class PermissionSimulateRequest(BaseModel):
    user_id: UUID
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    path: str = Field(min_length=1, max_length=500)
    department: str | None = Field(default=None, max_length=200)

    @field_validator("path")
    @classmethod
    def require_absolute_path(cls: Any, value: str) -> str:
        if not value.strip().startswith("/"):
            raise ValueError("path 必须以 / 开头")
        return value.strip()
