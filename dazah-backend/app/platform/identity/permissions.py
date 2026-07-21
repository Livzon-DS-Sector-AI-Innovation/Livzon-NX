from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import is_sensitive_key, redact_sensitive
from app.platform.audit.models import AuditLog
from app.platform.identity.models import User
from app.platform.identity.permission_repository import PermissionGrantRepository
from app.platform.identity.schemas import (
    ModulePermissionDefinitionOut,
    ModulePermissionGrantInput,
    ModulePermissionGrantOut,
    PermissionAuditItem,
    UserModulePermissionsOut,
    UserModulePermissionsUpdate,
)
from app.shared.module_registry import MODULES_BY_CODE

MODULE_PERMISSION_KEYS = frozenset(
    {
        "module.view",
        "module.agent.read",
        "module.agent.execute",
        "module.agent.automate",
        "module.admin",
    }
)

ADMIN_DEFAULT_MODULE_PERMISSIONS = MODULE_PERMISSION_KEYS


class IdentityPermissionService:
    def __init__(self, repo: PermissionGrantRepository | None = None) -> None:
        self.repo = repo or PermissionGrantRepository()

    async def get_user_permissions(
        self,
        db: AsyncSession,
        *,
        target_user_id: UUID,
        current_user: User,
    ) -> UserModulePermissionsOut:
        self._require_permission_admin(current_user)
        target = await db.get(User, target_user_id)
        if target is None or target.is_deleted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
        grants = await self.repo.list_grants(db, user_id=target_user_id)
        return self._permissions_out(target, grants)

    async def replace_user_permissions(
        self,
        db: AsyncSession,
        *,
        target_user_id: UUID,
        request: UserModulePermissionsUpdate,
        current_user: User,
        expected_version_from_header: int | None = None,
    ) -> tuple[User, list[Any], Any]:
        self._require_permission_admin(current_user)
        if target_user_id == current_user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "管理员不能修改自己的模块授权",
            )
        expected_version = (
            expected_version_from_header
            if expected_version_from_header is not None
            else request.expected_grant_version
        )
        if expected_version is None:
            raise HTTPException(
                status.HTTP_428_PRECONDITION_REQUIRED,
                "必须提交 expected_grant_version 或 If-Match",
            )
        target = await self.repo.get_user_for_update(db, target_user_id)
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
        if target.grant_version != expected_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"授权版本冲突，当前版本为 {target.grant_version}",
            )
        normalized = self._normalize_grants(request.grants)
        old_grants = await self.repo.list_grants(db, user_id=target_user_id)
        old_value = self._grant_summary(old_grants)
        next_version = target.grant_version + 1
        grants = await self.repo.replace_grants(
            db,
            user_id=target_user_id,
            grants=normalized,
            grant_version=next_version,
            granted_by=current_user.id,
        )
        target.grant_version = next_version
        target.updated_by = current_user.id
        event = await self.repo.create_outbox_event(
            db,
            user_id=target_user_id,
            grant_version=next_version,
            actor_id=current_user.id,
        )
        new_value = self._grant_summary(grants)
        db.add(
            AuditLog(
                user_id=current_user.id,
                method="PUT",
                path=f"/api/v1/identity/users/{target_user_id}/module-permissions",
                status_code=200,
                resource_type="user_module_permissions",
                resource_id=target_user_id,
                action="replace_user_module_permissions",
                old_value=redact_sensitive(old_value),
                new_value=redact_sensitive(new_value),
                extra={
                    "grant_version": next_version,
                    "reason": request.reason,
                    "outbox_event_id": str(event.id),
                },
            )
        )
        await db.flush()
        return target, grants, event

    async def list_permission_audit(
        self,
        db: AsyncSession,
        *,
        target_user_id: UUID,
        current_user: User,
        limit: int,
    ) -> list[PermissionAuditItem]:
        self._require_permission_admin(current_user)
        result = await db.execute(
            select(AuditLog)
            .where(
                AuditLog.resource_type == "user_module_permissions",
                AuditLog.resource_id == target_user_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        logs = list(result.scalars().all())
        db.add(
            AuditLog(
                user_id=current_user.id,
                method="GET",
                path=f"/api/v1/identity/users/{target_user_id}/permission-audit",
                status_code=200,
                resource_type="user_module_permissions",
                resource_id=target_user_id,
                action="view_user_permission_audit",
                extra={"returned": len(logs)},
            )
        )
        return [
            PermissionAuditItem(
                id=log.id,
                actor_user_id=log.user_id,
                action=log.action,
                old_value=redact_sensitive(log.old_value),
                new_value=redact_sensitive(log.new_value),
                reason=str((log.extra or {}).get("reason") or "") or None,
                grant_version=(log.extra or {}).get("grant_version"),
                created_at=log.created_at,
            )
            for log in logs
        ]

    @staticmethod
    def _require_permission_admin(user: User) -> None:
        if user.role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "需要权限管理员资格")

    @classmethod
    def _normalize_grants(
        cls, grants: list[ModulePermissionGrantInput]
    ) -> list[dict[str, Any]]:
        seen_modules: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for grant in grants:
            if grant.module_code in seen_modules:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"模块授权重复: {grant.module_code}",
                )
            seen_modules.add(grant.module_code)
            if grant.module_code not in MODULES_BY_CODE:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"未知模块: {grant.module_code}",
                )
            permissions = sorted(set(grant.permissions))
            unknown = set(permissions) - MODULE_PERMISSION_KEYS
            if unknown:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"未知权限项: {', '.join(sorted(unknown))}",
                )
            if permissions and "module.view" not in permissions:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{grant.module_code} 的任何授权都必须包含 module.view",
                )
            cls._validate_data_scope(grant.data_scope)
            normalized.append(
                {
                    "module_code": grant.module_code,
                    "permissions": permissions,
                    "data_scope": grant.data_scope,
                }
            )
        return sorted(normalized, key=lambda item: item["module_code"])

    @classmethod
    def _validate_data_scope(cls, value: Any, path: str = "data_scope") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if is_sensitive_key(key):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"数据范围不能包含敏感字段: {path}.{key}",
                    )
                cls._validate_data_scope(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                cls._validate_data_scope(item, f"{path}[{index}]")
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"数据范围字段类型不受支持: {path}",
            )

    @staticmethod
    def _grant_summary(grants: list[Any]) -> dict[str, Any]:
        return {
            "grants": [
                {
                    "module_code": grant.module_code,
                    "permissions": list(grant.permissions or []),
                    "data_scope": dict(grant.data_scope or {}),
                    "status": grant.status,
                    "grant_version": grant.grant_version,
                }
                for grant in grants
            ]
        }

    @staticmethod
    def _permissions_out(target: User, grants: list[Any]) -> UserModulePermissionsOut:
        grant_outputs = {
            grant.module_code: ModulePermissionGrantOut(
                module_code=grant.module_code,
                module_name=MODULES_BY_CODE[grant.module_code].name,
                permissions=list(grant.permissions or []),
                data_scope=dict(grant.data_scope or {}),
                grant_version=grant.grant_version,
                granted_by=grant.granted_by,
                status=grant.status,
                updated_at=grant.updated_at,
            )
            for grant in grants
            if grant.module_code in MODULES_BY_CODE
        }
        if target.role == "admin":
            for module_code, module in MODULES_BY_CODE.items():
                grant_outputs[module_code] = ModulePermissionGrantOut(
                    module_code=module_code,
                    module_name=module.name,
                    permissions=sorted(ADMIN_DEFAULT_MODULE_PERMISSIONS),
                    data_scope={},
                    grant_version=target.grant_version,
                    granted_by=target.id,
                    status="active",
                    updated_at=target.updated_at,
                )
        return UserModulePermissionsOut(
            user_id=target.id,
            grant_version=target.grant_version,
            available_modules=[
                ModulePermissionDefinitionOut(
                    module_code=module.code,
                    module_name=module.name,
                    description=module.description,
                )
                for module in MODULES_BY_CODE.values()
            ],
            grants=[grant_outputs[code] for code in sorted(grant_outputs)],
        )
