import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class User(BaseModel):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_identity_users_username"),
        UniqueConstraint("employee_no", name="uq_identity_users_employee_no"),
        UniqueConstraint("feishu_user_id", name="uq_identity_users_feishu_user_id"),
        {"schema": "identity"},
    )

    name: Mapped[str] = mapped_column(String(100))
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    auth_source: Mapped[str] = mapped_column(
        String(20), default="feishu", server_default="feishu"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    employee_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    position: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feishu_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feishu_open_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feishu_union_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    en_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="英文名"
    )
    avatar_thumb: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="小头像URL"
    )
    avatar_middle: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="中头像URL"
    )
    avatar_big: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="大头像URL"
    )
    enterprise_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="企业邮箱"
    )
    tenant_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="租户标识"
    )
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    feishu_department_ids: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="飞书部门ID列表，JSON数组"
    )
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    grant_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="用户模块授权单调递增版本",
    )


class UserModuleGrant(BaseModel):
    __tablename__ = "user_module_grants"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "module_code",
            name="uq_identity_user_module_grants_user_module",
        ),
        Index("ix_identity_user_module_grants_user_status", "user_id", "status"),
        Index("ix_identity_user_module_grants_module_status", "module_code", "status"),
        {"schema": "identity", "comment": "用户模块授权事实源"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module_code: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    data_scope: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    grant_version: Mapped[int] = mapped_column(Integer, nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class ExternalIdentityBinding(BaseModel):
    """Trusted mapping from an external application identity to a local user."""

    __tablename__ = "external_identity_bindings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "platform",
            "app_fingerprint",
            "external_user_id",
            name="uq_identity_external_bindings_user_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "platform",
            "app_fingerprint",
            "external_open_id",
            name="uq_identity_external_bindings_open_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "platform",
            "app_fingerprint",
            "external_union_id",
            name="uq_identity_external_bindings_union_id",
        ),
        Index(
            "ix_identity_external_bindings_local_status",
            "local_user_id",
            "status",
        ),
        CheckConstraint(
            "external_user_id IS NOT NULL OR external_open_id IS NOT NULL "
            "OR external_union_id IS NOT NULL",
            name="ck_identity_external_bindings_identifier",
        ),
        {"schema": "identity", "comment": "外部应用身份到本地可信主体的绑定事实"},
    )

    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    app_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    external_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_open_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_union_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    local_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="admin", server_default="admin"
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    binding_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class PermissionOutboxEvent(BaseModel):
    __tablename__ = "permission_outbox_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "grant_version",
            "event_type",
            name="uq_identity_permission_outbox_user_version_type",
        ),
        Index("ix_identity_permission_outbox_status_next", "status", "next_attempt_at"),
        {"schema": "identity", "comment": "身份权限变更事务 Outbox"},
    )

    event_type: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    grant_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class Department(BaseModel):
    """飞书组织架构部门（本地同步副本）"""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint(
            "feishu_department_id",
            name="uq_identity_departments_feishu_id",
        ),
        {"schema": "identity"},
    )

    feishu_department_id: Mapped[str] = mapped_column(
        String(64), unique=True, comment="飞书部门 open_department_id"
    )
    name: Mapped[str] = mapped_column(String(200), comment="部门名称")
    parent_feishu_department_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="父部门 ID"
    )
    leader_user_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="部门主管 user_id"
    )
    member_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="部门成员数"
    )
    status_is_deleted: Mapped[bool | None] = mapped_column(
        comment="飞书侧是否已删除", nullable=True, default=False
    )
    path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="部门路径 JSON，如 [{'name':'公司','id':'xxx'},...]",
    )
    order: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="同级排序"
    )


class Role(BaseModel):
    """RBAC 角色。"""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("code", name="uq_identity_roles_code"),
        {"schema": "identity"},
    )

    name: Mapped[str] = mapped_column(String(100), comment="角色名称")
    code: Mapped[str] = mapped_column(String(64), comment="角色编码")
    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="角色描述"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="系统内置角色（禁删）"
    )


class Permission(BaseModel):
    """RBAC 权限点。"""

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_identity_permissions_code"),
        {"schema": "identity"},
    )

    code: Mapped[str] = mapped_column(String(128), comment="权限编码")
    module: Mapped[str] = mapped_column(String(64), comment="模块名")
    action: Mapped[str] = mapped_column(String(32), comment="操作")
    name: Mapped[str] = mapped_column(String(100), comment="权限名称")
    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="权限描述"
    )


class RolePermission(BaseModel):
    """角色-权限绑定。"""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_id", name="uq_identity_role_permissions"
        ),
        {"schema": "identity"},
    )

    role_id = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    permission_id = mapped_column(UUID(as_uuid=True), index=True, nullable=False)


class UserRole(BaseModel):
    """用户-角色绑定，来源为手动或部门映射。"""

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "source", name="uq_identity_user_roles"),
        {"schema": "identity"},
    )

    user_id = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    role_id = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), default="manual", server_default="manual", comment="来源"
    )


class Menu(BaseModel):
    """系统菜单、目录和按钮。"""

    __tablename__ = "menus"
    __table_args__ = (
        UniqueConstraint("key", name="uq_identity_menus_key"),
        {"schema": "identity"},
    )

    key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_id = mapped_column(UUID(as_uuid=True), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(100), comment="菜单名称")
    type: Mapped[str] = mapped_column(String(16), comment="directory/menu/button")
    permission_code: Mapped[str | None] = mapped_column(
        String(128), index=True, nullable=True
    )
    route_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    component_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )


class RoleMenu(BaseModel):
    """角色-菜单绑定。"""

    __tablename__ = "role_menus"
    __table_args__ = (
        UniqueConstraint("role_id", "menu_id", name="uq_identity_role_menus"),
        {"schema": "identity"},
    )

    role_id = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    menu_id = mapped_column(UUID(as_uuid=True), index=True, nullable=False)


class DataScopeRule(BaseModel):
    """角色或用户的部门数据范围配置。"""

    __tablename__ = "data_scope_rules"
    __table_args__ = (
        UniqueConstraint("role_id", "user_id", name="uq_identity_data_scope_rules"),
        {"schema": "identity"},
    )

    role_id = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id = mapped_column(UUID(as_uuid=True), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(16), comment="all/departments")
    department_names: Mapped[str | None] = mapped_column(Text, nullable=True)


class DepartmentRoleRule(BaseModel):
    """按飞书部门 ID 或部门名称映射角色。"""

    __tablename__ = "department_role_rules"
    __table_args__ = (
        UniqueConstraint(
            "feishu_department_id",
            "department_name",
            "role_id",
            name="uq_identity_department_role_rules",
        ),
        {"schema": "identity"},
    )

    feishu_department_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role_id = mapped_column(UUID(as_uuid=True), nullable=False)


class FeishuConfig(BaseModel):
    """Livzon 助手专用飞书通讯录配置。"""

    __tablename__ = "feishu_configs"
    __table_args__ = {"schema": "identity"}

    config_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="Livzon 助手飞书设置",
        comment="配置名称，仅用于 Livzon 助手",
    )
    app_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书自建应用 App ID"
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="default",
        server_default="default",
        comment="Gateway 可信租户标识",
    )
    gateway_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否启用 Hermes Feishu Gateway",
    )
    allowed_group_chat_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    require_group_mention: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    config_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Gateway 配置单调递增版本",
    )
    encrypted_app_secret: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="加密后的飞书自建应用 App Secret"
    )
    sync_root_department_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="组织架构同步根部门 ID"
    )
    sync_member_department_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="成员同步部门 ID"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否启用",
    )
    last_sync_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="最近同步状态"
    )
    last_sync_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近同步信息"
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近同步时间"
    )
    last_diagnostic_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="最近诊断状态"
    )
    last_diagnostic_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近诊断信息"
    )
    last_diagnostic_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近诊断结果 JSON"
    )
    last_diagnosed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近诊断时间"
    )


class FeishuUserToken(BaseModel):
    """Encrypted Feishu user OAuth credentials for delegated OpenAPI calls."""

    __tablename__ = "feishu_user_tokens"
    __table_args__ = (
        UniqueConstraint(
            "local_user_id",
            "app_id",
            name="uq_identity_feishu_user_tokens_user_app",
        ),
        {"schema": "identity"},
    )

    local_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="本地平台用户 ID"
    )
    app_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="飞书自建应用 App ID"
    )
    feishu_open_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="飞书 open_id"
    )
    feishu_user_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="飞书 user_id"
    )
    feishu_union_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="飞书 union_id"
    )
    tenant_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="飞书租户标识"
    )
    encrypted_user_access_token: Mapped[str] = mapped_column(
        Text, nullable=False, comment="加密后的 user_access_token"
    )
    encrypted_refresh_token: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="加密后的 refresh_token"
    )
    token_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="Token 类型"
    )
    scope: Mapped[str | None] = mapped_column(Text, nullable=True, comment="授权范围")
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="user_access_token 过期时间"
    )
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="refresh_token 过期时间"
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近刷新时间"
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近刷新错误"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
        comment="active/revoked/error",
    )
