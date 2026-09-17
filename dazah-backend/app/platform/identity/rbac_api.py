"""Administrative RBAC APIs used by the migrated system permission pages.

The current identity API remains the source of authentication and legacy module
grants.  This router only manages the additive role/menu/data-scope tables and
never turns an old ``module.view`` grant into a write or Agent permission.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.response import success_response
from app.platform.audit.service import record_audit_log
from app.platform.identity.access_check import check_access
from app.platform.identity.authorization_guard import lock_authorization_actor
from app.platform.identity.data_scope import (
    publish_data_scope_changed,
    resolve_user_department_scope,
)
from app.platform.identity.deps import CurrentUser, require_current_user
from app.platform.identity.models import (
    Permission,
    Role,
    RolePageGrant,
    User,
    UserPageGrant,
)
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import (
    PAGES_BY_MODULE,
    canonical_page_key,
    get_page_definition,
)
from app.platform.identity.permission_cache import (
    publish_permissions_changed,
    publish_permissions_changed_all,
)
from app.platform.identity.permission_repository import PermissionGrantRepository
from app.platform.identity.rbac import (
    active_system_admin_count,
    lock_admin_changes,
    resolve_user_menu_ids,
    resolve_user_permissions,
    resolve_user_roles,
)
from app.platform.identity.repository import (
    MenuRepository,
    RbacRepository,
    UserRepository,
)
from app.platform.identity.schemas import (
    AssignUserRoleRequest,
    DataScopeRuleCreateRequest,
    DataScopeRuleResponse,
    DataScopeRuleUpdateRequest,
    DeptRuleCreateRequest,
    DeptRuleResponse,
    MenuCreateRequest,
    MenuResponse,
    MenuUpdateRequest,
    PageDataScopeInput,
    PageGrantInput,
    PagePermissionHealthOut,
    PagePermissionHealthRemediationOut,
    PagePermissionHealthRemediationRequest,
    PagePermissionHistoryItemOut,
    PagePermissionHistoryPageOut,
    PagePermissionRollbackPreviewOut,
    PagePermissionRollbackPreviewRequest,
    PagePermissionRollbackRequest,
    PagePermissionSimulationOut,
    PagePermissionSimulationRequest,
    PermissionModuleIntegrationOut,
    PermissionModuleRolloutPreviewOut,
    PermissionResponse,
    PermissionSimulateRequest,
    RoleCreateRequest,
    RoleMenusRequest,
    RolePagePermissionAffectedUserOut,
    RolePagePermissionsOut,
    RolePagePermissionsPreviewOut,
    RolePagePermissionsUpdate,
    RolePermissionsRequest,
    RoleResponse,
    RoleUpdateRequest,
    UserPagePermissionsOut,
    UserPagePermissionsUpdate,
    UserResponse,
)
from app.shared.module_registry import MODULES_BY_CODE

rbac_router = APIRouter(prefix="/admin", tags=["权限管理"])


async def require_identity_admin(
    current_user: CurrentUser,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require platform administration, even when module access is ``all``."""

    user = await require_current_user(current_user)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        user = await lock_authorization_actor(db, user)
    if user.role == "admin":
        return user
    permissions = await resolve_user_permissions(db, user.id)
    if "*" not in permissions and "identity:admin" not in permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要 identity:admin 权限")
    return user


IdentityAdminUser = Annotated[User, Depends(require_identity_admin)]


async def _audit(
    db: AsyncSession,
    actor: User,
    *,
    action: str,
    resource_type: str,
    resource_id: UUID | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    await record_audit_log(
        db,
        action=action,
        user_id=actor.id,
        resource_type=resource_type,
        resource_id=resource_id,
        old_value=old_value,
        new_value=new_value,
    )


def _role_payload(role: Role, permissions: list[str] | None = None) -> dict[str, Any]:
    payload = RoleResponse.model_validate(role).model_dump(mode="json")
    if role.code == "super_admin":
        payload["name"] = "系统管理员"
    if permissions is not None:
        payload["permissions"] = permissions
    return payload


async def _get_role_or_404(db: AsyncSession, role_id: UUID) -> Role:
    role = await RbacRepository().get_role_by_id(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在")
    return role


async def _get_target_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    user = await UserRepository().get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    return user


async def _active_super_admin_count(db: AsyncSession) -> int:
    return await active_system_admin_count(db)


async def _assert_not_own_role(db: AsyncSession, actor: User, role_id: UUID) -> None:
    if actor.role != "admin" and any(
        role.id == role_id for role in await resolve_user_roles(db, actor.id)
    ):
        raise HTTPException(403, "不能通过本人所属角色修改自身授权")


async def _bump_all_user_grant_versions(db: AsyncSession, *, actor_id: UUID) -> None:
    """Invalidate effective page/Agent snapshots after a role or rollout change."""

    page_repo = PagePermissionRepository()
    permission_repo = PermissionGrantRepository()
    for user in await page_repo.bump_active_user_versions(db, actor_id=actor_id):
        await permission_repo.create_outbox_event(
            db,
            user_id=user.id,
            grant_version=user.grant_version,
            actor_id=actor_id,
            event_type="identity.user_page_grants.changed.v1",
        )


async def _assert_not_own_department_rule(
    db: AsyncSession,
    actor: User,
    *,
    department_id: str | None,
    department_name: str | None,
) -> None:
    matches_self = bool(
        department_id in PagePermissionService._user_department_ids(actor)
        or (department_name and department_name == getattr(actor, "department", None))
    )
    if matches_self and not await PagePermissionService().is_super_admin(
        db, user_id=actor.id
    ):
        raise HTTPException(403, "不能通过本人部门的角色映射调整自身授权")


def _grant_payload(grants: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "page_key": grant.page_key,
            "permissions": list(grant.permissions or []),
            "sensitive_actions": list(grant.sensitive_actions or []),
            "sensitive_actions_expires_at": (
                grant.sensitive_actions_expires_at.isoformat()
                if getattr(grant, "sensitive_actions_expires_at", None)
                else None
            ),
            "scope_type": grant.scope_type,
            "department_ids": list(grant.department_ids or []),
        }
        for grant in grants
    ]


def _snapshot_inputs(grants: list[dict[str, Any]]) -> list[PageGrantInput]:
    return [
        PageGrantInput(
            page_key=str(grant["page_key"]),
            permissions=list(grant.get("permissions") or []),
            sensitive_actions=list(grant.get("sensitive_actions") or []),
            sensitive_actions_expires_at=grant.get("sensitive_actions_expires_at"),
            data_scope=PageDataScopeInput(
                scope_type=grant.get("scope_type", "department_tree"),
                department_ids=list(grant.get("department_ids") or []),
            ),
        )
        for grant in grants
    ]


def _page_permission_request_fingerprint(
    *,
    reason: str,
    grants: list[PageGrantInput] | None = None,
    audit_id: UUID | None = None,
) -> str:
    payload = {
        "reason": reason,
        "grants": [grant.model_dump(mode="json") for grant in grants or []],
        "audit_id": str(audit_id) if audit_id else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _assert_matching_idempotency(existing: Any, request_fingerprint: str) -> None:
    if (existing.new_value or {}).get("request_fingerprint") != request_fingerprint:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "该幂等键已用于另一项授权请求，请重新发起操作",
        )


async def _raise_page_grant_conflict(
    db: AsyncSession,
    *,
    resource_type: str,
    resource_id: UUID,
    submitted_version: int,
    current_version: int,
) -> None:
    latest = await PagePermissionService().permission_history(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=1,
    )
    detail = (
        f"授权版本冲突：你基于 v{submitted_version} 编辑，当前已是 v{current_version}"
    )
    if latest:
        item = latest[0]
        actor = item.actor_name or "其他管理员"
        changed_at = item.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
        reason = f"，原因：{item.reason}" if item.reason else ""
        detail += f"；最近由 {actor} 于 {changed_at} 变更{reason}"
    raise HTTPException(status.HTTP_409_CONFLICT, detail)


def _page_permission_history_csv(
    items: list[PagePermissionHistoryItemOut], *, target_name: str
) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["时间", "对象", "版本", "来源", "操作人", "原因", "页面", "变化", "变化说明"]
    )
    source_labels = {
        "manual": "手工调整",
        "rollback": "历史回滚",
        "health_remediation": "健康修复",
    }
    for item in items:
        changes: list[Any] = list(item.changes) or [None]
        for change in changes:
            writer.writerow(
                [
                    item.created_at.isoformat(),
                    target_name,
                    item.grant_version or "",
                    source_labels[item.source],
                    item.actor_name or "系统",
                    item.reason or "",
                    change.page_name if change else "",
                    change.kind if change else "",
                    change.summary if change else "",
                ]
            )
    filename = f"page-permission-history-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@rbac_router.get("/permissions", summary="权限目录列表")
async def list_permissions(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    permissions = await RbacRepository().list_permissions(db)
    return success_response(
        data=[
            PermissionResponse.model_validate(item).model_dump(mode="json")
            for item in permissions
        ]
    )


@rbac_router.get("/roles", summary="角色列表")
async def list_roles(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = RbacRepository()
    items = []
    for role in await repo.list_roles(db):
        items.append(
            _role_payload(role, await repo.list_role_permission_codes(db, role.id))
        )
    return success_response(data=items)


@rbac_router.post("/roles", summary="新建角色")
async def create_role(
    body: RoleCreateRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = RbacRepository()
    if await repo.get_role_by_code(db, body.code):
        raise HTTPException(status.HTTP_409_CONFLICT, f"角色编码 {body.code} 已存在")
    try:
        role = await repo.create_role(
            db, name=body.name, code=body.code, description=body.description
        )
        await _audit(
            db,
            current_user,
            action="rbac_role_created",
            resource_type="identity.role",
            resource_id=role.id,
            new_value={"name": role.name, "code": role.code},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "角色编码已存在") from exc
    return success_response(data=_role_payload(role, []))


@rbac_router.put("/roles/{role_id}", summary="更新角色")
async def update_role(
    role_id: UUID,
    body: RoleUpdateRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    role = await _get_role_or_404(db, role_id)
    if role.code == "super_admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统管理员角色不允许修改")
    old = {"name": role.name, "description": role.description}
    role = await RbacRepository().update_role(
        db, role, name=body.name, description=body.description
    )
    await _audit(
        db,
        current_user,
        action="rbac_role_updated",
        resource_type="identity.role",
        resource_id=role.id,
        old_value=old,
        new_value={"name": role.name, "description": role.description},
    )
    await db.commit()
    await publish_permissions_changed_all()
    return success_response(
        data=_role_payload(
            role, await RbacRepository().list_role_permission_codes(db, role.id)
        )
    )


@rbac_router.delete("/roles/{role_id}", summary="删除角色")
async def delete_role(
    role_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    role = await _get_role_or_404(db, role_id)
    await _assert_not_own_role(db, current_user, role_id)
    if role.code == "super_admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统管理员角色不允许删除")
    await RbacRepository().soft_delete_role(db, role)
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rbac_role_deleted",
        resource_type="identity.role",
        resource_id=role.id,
        old_value={"name": role.name, "code": role.code},
    )
    await db.commit()
    await publish_permissions_changed_all()
    return success_response(data={"message": "角色已删除"})


@rbac_router.post("/roles/{role_id}/permissions", summary="设置角色权限")
async def set_role_permissions(
    role_id: UUID,
    body: RolePermissionsRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    role = await _get_role_or_404(db, role_id)
    await _assert_not_own_role(db, current_user, role_id)
    if role.is_system and role.code == "super_admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统管理员权限不可修改")
    permission_ids = list(dict.fromkeys(body.permission_ids))
    permission_stmt = select(Permission.id).where(Permission.is_deleted.is_(False))
    if permission_ids:
        permission_stmt = permission_stmt.where(Permission.id.in_(permission_ids))
    result = await db.execute(permission_stmt)
    existing_ids = set(result.scalars().all())
    missing = [item for item in permission_ids if item not in existing_ids]
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"权限点不存在: {missing[0]}")
    repo = RbacRepository()
    old_permissions = await repo.list_role_permission_codes(db, role.id)
    await repo.set_role_permissions(db, role.id, permission_ids)
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rbac_role_permissions_updated",
        resource_type="identity.role_permissions",
        resource_id=role.id,
        old_value={"permissions": old_permissions},
        new_value={"permission_ids": [str(item) for item in permission_ids]},
    )
    await db.commit()
    await publish_permissions_changed_all()
    return success_response(data={"message": "角色权限已更新"})


@rbac_router.get("/users", summary="用户列表（含角色）")
async def list_admin_users(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
    keyword: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    department_id: Annotated[str | None, Query(max_length=255)] = None,
    department_name: Annotated[str | None, Query(max_length=255)] = None,
    user_scope: Annotated[
        Literal["department", "missing", "all"] | None, Query()
    ] = None,
) -> JSONResponse:
    if user_scope is not None:
        department_id = (department_id or "").strip() or None
        department_name = (department_name or "").strip() or None
        if user_scope == "department" and not (department_id or department_name):
            raise HTTPException(422, "飞书部门 ID 与部门名称至少填写一个")
        users, total = await UserRepository().list_role_candidates(
            db,
            department_id=department_id,
            department_name=department_name,
            user_scope=user_scope,
            keyword=(keyword or "").strip() or None,
            offset=offset,
            limit=limit,
        )
    else:
        users, total = await UserRepository().list_all(
            db, keyword=keyword, offset=offset, limit=limit
        )
    repo = RbacRepository()
    items = []
    for user in users:
        item = UserResponse.model_validate(user).model_dump(mode="json")
        item["roles"] = [
            _role_payload(role) for role in await repo.list_user_roles(db, user.id)
        ]
        if user.role == "admin" and not any(
            role["code"] == "super_admin" for role in item["roles"]
        ):
            system_role = await db.scalar(
                select(Role).where(
                    Role.code == "super_admin", Role.is_deleted.is_(False)
                )
            )
            if system_role is not None:
                item["roles"].append(_role_payload(system_role))
        items.append(item)
    return success_response(data={"items": items, "total": total})


@rbac_router.post("/users/{user_id}/roles", summary="手动分配角色")
async def assign_user_roles(
    user_id: UUID,
    body: AssignUserRoleRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "管理员不能修改自己的角色")
    await lock_admin_changes(db)
    user = await _get_target_user_or_404(db, user_id)
    if (
        body.expected_grant_version is not None
        and user.grant_version != body.expected_grant_version
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "授权版本冲突："
            f"你基于 v{body.expected_grant_version} 编辑，"
            f"当前已是 v{user.grant_version}",
        )
    repo = RbacRepository()
    current_roles = await repo.list_user_roles(db, user.id)
    current_by_id = {role.id: role for role in current_roles}
    selected_roles: list[Role] = []
    for role_id in dict.fromkeys(body.role_ids):
        role = await _get_role_or_404(db, role_id)
        if (
            role.code == "super_admin"
            and not await PagePermissionService().is_super_admin(
                db, user_id=current_user.id
            )
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "仅系统管理员可以分配系统管理员角色"
            )
        selected_roles.append(role)
    requested_by_id = {role.id: role for role in selected_roles}
    selected_by_id = (
        {**current_by_id, **requested_by_id} if body.mode == "add" else requested_by_id
    )
    removed_super_admin = any(
        role.code == "super_admin" and role_id not in selected_by_id
        for role_id, role in current_by_id.items()
    )
    if removed_super_admin:
        if not await PagePermissionService().is_super_admin(
            db, user_id=current_user.id
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "仅系统管理员可以移除系统管理员角色"
            )
        if user.status == "active" and await _active_super_admin_count(db) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "不能移除最后一个可用的系统管理员"
            )
    current_ids = set(current_by_id)
    selected_ids = set(selected_by_id)
    added_ids = selected_ids - current_ids
    removed_ids = current_ids - selected_ids
    if not added_ids and not removed_ids:
        return success_response(
            data={"message": "角色未变化", "grant_version": user.grant_version}
        )
    await repo.replace_user_roles(db, user.id, list(selected_ids))
    user.role = (
        "admin"
        if any(role.code == "super_admin" for role in selected_by_id.values())
        else "user"
    )
    user.grant_version += 1
    user.updated_by = current_user.id
    await PermissionGrantRepository().create_outbox_event(
        db,
        user_id=user.id,
        grant_version=user.grant_version,
        actor_id=current_user.id,
        event_type="identity.user_page_grants.changed.v1",
    )
    await _audit(
        db,
        current_user,
        action="rbac_user_roles_updated",
        resource_type="identity.user_roles",
        resource_id=user.id,
        old_value={"role_ids": [str(item) for item in sorted(current_ids, key=str)]},
        new_value={
            "role_ids": [str(item) for item in sorted(selected_ids, key=str)],
            "added_role_ids": [str(item) for item in sorted(added_ids, key=str)],
            "removed_role_ids": [str(item) for item in sorted(removed_ids, key=str)],
            "reason": (body.reason or "").strip() or None,
        },
    )
    await db.commit()
    await publish_permissions_changed(user.id)
    await publish_data_scope_changed("user", user.id)
    return success_response(
        data={
            "message": "角色分配已更新",
            "grant_version": user.grant_version,
            "added_count": len(added_ids),
            "removed_count": len(removed_ids),
        }
    )


@rbac_router.delete("/users/{user_id}/roles/{role_id}", summary="移除手动角色")
async def remove_user_role(
    user_id: UUID,
    role_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "管理员不能修改自己的角色")
    await lock_admin_changes(db)
    user = await _get_target_user_or_404(db, user_id)
    role = await _get_role_or_404(db, role_id)
    if role.code == "super_admin":
        if not await PagePermissionService().is_super_admin(
            db, user_id=current_user.id
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "仅系统管理员可以移除系统管理员角色"
            )
        if user.status == "active" and await _active_super_admin_count(db) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "不能移除最后一个可用的系统管理员"
            )
    removed = await RbacRepository().remove_user_role(db, user.id, role_id)
    if role.code == "super_admin" and user.role == "admin":
        user.role = "user"
        removed = True
    if removed:
        user.grant_version += 1
        user.updated_by = current_user.id
        await PermissionGrantRepository().create_outbox_event(
            db,
            user_id=user.id,
            grant_version=user.grant_version,
            actor_id=current_user.id,
            event_type="identity.user_page_grants.changed.v1",
        )
    await _audit(
        db,
        current_user,
        action="rbac_user_role_removed",
        resource_type="identity.user_roles",
        resource_id=user.id,
        old_value={"role_id": str(role_id), "removed": removed},
    )
    await db.commit()
    await publish_permissions_changed(user.id)
    await publish_data_scope_changed("user", user.id)
    return success_response(data={"message": "角色已移除" if removed else "绑定不存在"})


@rbac_router.get("/dept-rules", summary="部门-角色映射规则列表")
async def list_dept_rules(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = RbacRepository()
    items = []
    for rule in await repo.list_dept_rules(db):
        payload = DeptRuleResponse.model_validate(rule).model_dump(mode="json")
        role = await repo.get_role_by_id(db, rule.role_id)
        if role:
            payload["role_name"] = role.name
            payload["role_code"] = role.code
        items.append(payload)
    return success_response(data=items)


@rbac_router.post("/dept-rules", summary="新建部门-角色映射规则")
async def create_dept_rule(
    body: DeptRuleCreateRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await _assert_not_own_department_rule(
        db,
        current_user,
        department_id=body.feishu_department_id,
        department_name=body.department_name,
    )
    role = await _get_role_or_404(db, body.role_id)
    if role.code == "super_admin":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "系统管理员角色只能逐个用户明确分配，不能通过部门映射授予",
        )
    rule = await RbacRepository().create_dept_rule(
        db,
        role_id=role.id,
        feishu_department_id=body.feishu_department_id,
        department_name=body.department_name,
    )
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rbac_department_role_rule_created",
        resource_type="identity.department_role_rule",
        resource_id=rule.id,
        new_value={
            "role_id": str(role.id),
            "feishu_department_id": rule.feishu_department_id,
            "department_name": rule.department_name,
        },
    )
    await db.commit()
    await publish_permissions_changed_all()
    payload = DeptRuleResponse.model_validate(rule).model_dump(mode="json")
    payload.update(role_name=role.name, role_code=role.code)
    return success_response(data=payload)


@rbac_router.delete("/dept-rules/{rule_id}", summary="删除部门-角色映射规则")
async def delete_dept_rule(
    rule_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = RbacRepository()
    rule = await repo.get_dept_rule_by_id(db, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    await _assert_not_own_department_rule(
        db,
        current_user,
        department_id=rule.feishu_department_id,
        department_name=rule.department_name,
    )
    await repo.soft_delete_dept_rule(db, rule)
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rbac_department_role_rule_deleted",
        resource_type="identity.department_role_rule",
        resource_id=rule.id,
        old_value={"role_id": str(rule.role_id)},
    )
    await db.commit()
    await publish_permissions_changed_all()
    return success_response(data={"message": "规则已删除"})


@rbac_router.get("/menus", summary="菜单树列表（扁平，含禁用）")
async def list_menus(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    menus = await MenuRepository().list_all(db)
    return success_response(
        data=[
            MenuResponse.model_validate(item).model_dump(mode="json") for item in menus
        ]
    )


@rbac_router.post("/menus", summary="新建菜单/目录/按钮")
async def create_menu(
    body: MenuCreateRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = MenuRepository()
    if body.key and await repo.get_by_key(db, body.key, include_deleted=True):
        raise HTTPException(409, "菜单标识已使用或已退役，新功能必须使用新的标识")
    if body.parent_id is not None:
        parent = await repo.get_by_id(db, body.parent_id)
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "父菜单不存在")
        if parent.type == "button":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "按钮下不允许再建子节点")
    fields = body.model_dump()
    menu = await repo.create(db, **fields)
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rbac_menu_created",
        resource_type="identity.menu",
        resource_id=menu.id,
        new_value={"name": menu.name, "key": menu.key, "type": menu.type},
    )
    await db.commit()
    await publish_permissions_changed_all()
    return success_response(
        data=MenuResponse.model_validate(menu).model_dump(mode="json")
    )


@rbac_router.put("/menus/{menu_id}", summary="更新菜单")
async def update_menu(
    menu_id: UUID,
    body: MenuUpdateRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = MenuRepository()
    menu = await repo.get_by_id(db, menu_id)
    if menu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "菜单不存在")
    fields = body.model_dump(exclude_unset=True)
    if menu.key and "key" in fields and fields["key"] != menu.key:
        raise HTTPException(409, "已有菜单的授权标识不可修改，功能重做请新建菜单")
    if fields.get("parent_id") == menu.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能将菜单设为自己的父节点")
    if fields.get("parent_id") is not None:
        parent = await repo.get_by_id(db, fields["parent_id"])
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "父菜单不存在")
        if parent.type == "button":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "按钮下不允许再建子节点")
    old = MenuResponse.model_validate(menu).model_dump(mode="json")
    if fields:
        menu = await repo.update(db, menu, **fields)
        await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rbac_menu_updated",
        resource_type="identity.menu",
        resource_id=menu.id,
        old_value=old,
        new_value=MenuResponse.model_validate(menu).model_dump(mode="json"),
    )
    await db.commit()
    await publish_permissions_changed_all()
    return success_response(
        data=MenuResponse.model_validate(menu).model_dump(mode="json")
    )


@rbac_router.delete("/menus/{menu_id}", summary="删除菜单")
async def delete_menu(
    menu_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = MenuRepository()
    menu = await repo.get_by_id(db, menu_id)
    if menu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "菜单不存在")
    if await repo.list_children(db, menu.id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "菜单存在子节点，请先删除或禁用子节点"
        )
    await repo.soft_delete(db, menu)
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rbac_menu_deleted",
        resource_type="identity.menu",
        resource_id=menu.id,
        old_value={"name": menu.name, "key": menu.key},
    )
    await db.commit()
    await publish_permissions_changed_all()
    return success_response(data={"message": "菜单已删除"})


@rbac_router.get("/roles/{role_id}/menus", summary="角色菜单绑定")
async def get_role_menus(
    role_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    role = await _get_role_or_404(db, role_id)
    menu_ids = await MenuRepository().list_role_menu_ids(db, role.id)
    return success_response(
        data={"role_id": str(role.id), "menu_ids": [str(item) for item in menu_ids]}
    )


@rbac_router.put("/roles/{role_id}/menus", summary="设置角色菜单绑定")
async def set_role_menus(
    role_id: UUID,
    body: RoleMenusRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    role = await _get_role_or_404(db, role_id)
    await _assert_not_own_role(db, current_user, role_id)
    if role.code == "super_admin":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "系统管理员角色不允许修改菜单绑定"
        )
    menu_repo = MenuRepository()
    for menu_id in dict.fromkeys(body.menu_ids):
        if await menu_repo.get_by_id(db, menu_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"菜单 {menu_id} 不存在")
    await menu_repo.set_role_menus(db, role.id, body.menu_ids)
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rbac_role_menus_updated",
        resource_type="identity.role_menus",
        resource_id=role.id,
        new_value={"menu_ids": [str(item) for item in body.menu_ids]},
    )
    await db.commit()
    await publish_permissions_changed_all()
    return success_response(
        data={
            "role_id": str(role.id),
            "menu_ids": [str(item) for item in body.menu_ids],
        }
    )


@rbac_router.get("/data-scopes", summary="数据范围配置列表")
async def list_data_scope_rules(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    rules = await RbacRepository().list_data_scope_rules(db)
    return success_response(
        data=[
            DataScopeRuleResponse.model_validate(item).model_dump(mode="json")
            for item in rules
        ]
    )


@rbac_router.post("/data-scopes", summary="新建或覆盖数据范围配置")
async def create_data_scope_rule(
    body: DataScopeRuleCreateRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = RbacRepository()
    existing = await repo.get_data_scope_rule_by_target(
        db, role_id=body.role_id, user_id=body.user_id
    )
    names = (
        json.dumps(body.department_names or [], ensure_ascii=False)
        if body.scope_type == "departments"
        else None
    )
    if existing:
        old = DataScopeRuleResponse.model_validate(existing).model_dump(mode="json")
        rule = await repo.update_data_scope_rule(
            db, existing, scope_type=body.scope_type, department_names=names
        )
        action = "rbac_data_scope_updated"
    else:
        rule = await repo.create_data_scope_rule(
            db,
            role_id=body.role_id,
            user_id=body.user_id,
            scope_type=body.scope_type,
            department_names=names,
        )
        old = None
        action = "rbac_data_scope_created"
    await _audit(
        db,
        current_user,
        action=action,
        resource_type="identity.data_scope_rule",
        resource_id=rule.id,
        old_value=old,
        new_value=DataScopeRuleResponse.model_validate(rule).model_dump(mode="json"),
    )
    await db.commit()
    target_type = "user" if rule.user_id else "role"
    await publish_data_scope_changed(target_type, rule.user_id or rule.role_id)
    return success_response(
        data=DataScopeRuleResponse.model_validate(rule).model_dump(mode="json")
    )


@rbac_router.put("/data-scopes/{rule_id}", summary="更新数据范围配置")
async def update_data_scope_rule(
    rule_id: UUID,
    body: DataScopeRuleUpdateRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = RbacRepository()
    rule = await repo.get_data_scope_rule_by_id(db, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "数据范围配置不存在")
    next_scope = body.scope_type or rule.scope_type
    if (
        next_scope == "departments"
        and body.scope_type == "departments"
        and not body.department_names
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "departments 范围必须提供部门列表"
        )
    old = DataScopeRuleResponse.model_validate(rule).model_dump(mode="json")
    fields: dict[str, Any] = {"scope_type": next_scope}
    if next_scope == "all":
        fields["department_names"] = None
    elif body.department_names is not None:
        fields["department_names"] = json.dumps(
            body.department_names, ensure_ascii=False
        )
    await repo.update_data_scope_rule(db, rule, **fields)
    await _audit(
        db,
        current_user,
        action="rbac_data_scope_updated",
        resource_type="identity.data_scope_rule",
        resource_id=rule.id,
        old_value=old,
        new_value=DataScopeRuleResponse.model_validate(rule).model_dump(mode="json"),
    )
    await db.commit()
    target_type = "user" if rule.user_id else "role"
    await publish_data_scope_changed(target_type, rule.user_id or rule.role_id)
    return success_response(
        data=DataScopeRuleResponse.model_validate(rule).model_dump(mode="json")
    )


@rbac_router.delete("/data-scopes/{rule_id}", summary="删除数据范围配置")
async def delete_data_scope_rule(
    rule_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = RbacRepository()
    rule = await repo.get_data_scope_rule_by_id(db, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "数据范围配置不存在")
    target_type = "user" if rule.user_id else "role"
    target_id = rule.user_id or rule.role_id
    old = DataScopeRuleResponse.model_validate(rule).model_dump(mode="json")
    await repo.soft_delete_data_scope_rule(db, rule)
    await _audit(
        db,
        current_user,
        action="rbac_data_scope_deleted",
        resource_type="identity.data_scope_rule",
        resource_id=rule.id,
        old_value=old,
    )
    await db.commit()
    await publish_data_scope_changed(target_type, target_id)
    return success_response(data={"message": "数据范围配置已删除，恢复默认"})


@rbac_router.get("/users/{user_id}/permission-preview", summary="账号权限预览")
async def get_user_permission_preview(
    user_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    user = await _get_target_user_or_404(db, user_id)
    roles = await resolve_user_roles(db, user.id)
    permissions = await resolve_user_permissions(db, user.id)
    menu_ids = await resolve_user_menu_ids(db, user.id, roles)
    scope = await resolve_user_department_scope(db, user)
    return success_response(
        data={
            "user_id": str(user.id),
            "name": user.name,
            "roles": [_role_payload(role) for role in roles],
            "permissions": permissions,
            "menu_ids": [str(item) for item in menu_ids],
            "data_scope": {
                "is_all": scope.is_all,
                "department_names": sorted(scope.department_names),
            },
        }
    )


@rbac_router.post("/permission-simulate", summary="接口准入模拟")
async def simulate_permission(
    body: PermissionSimulateRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    user = await _get_target_user_or_404(db, body.user_id)
    permissions = await resolve_user_permissions(db, user.id)
    decision = check_access(body.path, body.method, permissions)
    data = {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "required": decision.required,
        "note": decision.note,
    }
    if body.department and body.path.startswith("/api/v1/hr/"):
        scope = await resolve_user_department_scope(db, user)
        data["dept_scope_hint"] = (
            f"该账号可见部门含「{body.department}」"
            if scope.is_all or body.department in scope.department_names
            else f"该账号可见部门不含「{body.department}」"
        )
    return success_response(data=data)


# ─── 页面权限矩阵 ────────────────────────────────────────────────────


@rbac_router.get(
    "/users/{user_id}/page-permissions",
    summary="查看用户页面权限",
    response_model=UserPagePermissionsOut,
)
async def get_user_page_permissions(
    user_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    user = await _get_target_user_or_404(db, user_id)
    result = await PagePermissionService().user_permissions_out(db, user=user)
    await _audit(
        db,
        current_user,
        action="view_user_page_permissions",
        resource_type="identity.user_page_permissions",
        resource_id=user.id,
    )
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.put(
    "/users/{user_id}/page-permissions",
    summary="替换用户页面权限覆盖",
    response_model=UserPagePermissionsOut,
)
async def replace_user_page_permissions(
    user_id: UUID,
    body: UserPagePermissionsUpdate,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "管理员不能修改自己的页面权限")
    permission_repo = PermissionGrantRepository()
    user = await permission_repo.get_user_for_update(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if user.role == "admin":
        raise HTTPException(400, "系统管理员拥有全部权限，无需配置页面覆盖")
    if body.expected_grant_version is None:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "必须提交授权版本")
    page_repo = PagePermissionRepository()
    service = PagePermissionService()
    request_fingerprint = _page_permission_request_fingerprint(
        reason=body.reason, grants=body.grants
    )
    if body.idempotency_key:
        existing = await page_repo.find_page_permission_idempotency(
            db,
            resource_type="identity.user_page_permissions",
            resource_id=user.id,
            idempotency_key=body.idempotency_key,
        )
        if existing:
            _assert_matching_idempotency(existing, request_fingerprint)
            result = await service.user_permissions_out(db, user=user)
            return success_response(data=result.model_dump(mode="json"))
    if user.grant_version != body.expected_grant_version:
        await _raise_page_grant_conflict(
            db,
            resource_type="identity.user_page_permissions",
            resource_id=user.id,
            submitted_version=body.expected_grant_version,
            current_version=user.grant_version,
        )
    normalized = service.normalize_inputs(body.grants, allow_inherit=True)
    await service.validate_department_ids(db, grants=normalized)
    old = await page_repo.list_user_grants(db, user_id=user.id)
    created = await page_repo.replace_user_grants(
        db,
        user_id=user.id,
        grants=normalized,
        actor_id=current_user.id,
    )
    user.grant_version += 1
    user.updated_by = current_user.id
    await permission_repo.create_outbox_event(
        db,
        user_id=user.id,
        grant_version=user.grant_version,
        actor_id=current_user.id,
        event_type="identity.user_page_grants.changed.v1",
    )
    await _audit(
        db,
        current_user,
        action="replace_user_page_permissions",
        resource_type="identity.user_page_permissions",
        resource_id=user.id,
        old_value={"grants": _grant_payload(old)},
        new_value={
            "grants": _grant_payload(created),
            "reason": body.reason,
            "grant_version": user.grant_version,
            "idempotency_key": str(body.idempotency_key)
            if body.idempotency_key
            else None,
            "request_fingerprint": request_fingerprint,
        },
    )
    await db.commit()
    await publish_permissions_changed(user.id)
    result = await service.user_permissions_out(db, user=user)
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.get(
    "/roles/{role_id}/page-permissions",
    summary="查看角色页面权限",
    response_model=RolePagePermissionsOut,
)
async def get_role_page_permissions(
    role_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    role = await _get_role_or_404(db, role_id)
    result = await PagePermissionService().role_permissions_out(db, role=role)
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.put(
    "/roles/{role_id}/page-permissions",
    summary="替换角色页面权限",
    response_model=RolePagePermissionsOut,
)
async def replace_role_page_permissions(
    role_id: UUID,
    body: RolePagePermissionsUpdate,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    page_repo = PagePermissionRepository()
    role = await page_repo.get_role_for_update(db, role_id=role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在")
    if role.code == "super_admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统管理员页面权限不可修改")
    actor_roles = await resolve_user_roles(db, current_user.id)
    if (
        current_user.role != "admin"
        and not any(item.code == "super_admin" for item in actor_roles)
        and any(item.id == role.id for item in actor_roles)
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "不能通过修改本人所属角色调整自身页面授权"
        )
    service = PagePermissionService()
    request_fingerprint = _page_permission_request_fingerprint(
        reason=body.reason, grants=body.grants
    )
    if body.idempotency_key:
        existing = await page_repo.find_page_permission_idempotency(
            db,
            resource_type="identity.role_page_permissions",
            resource_id=role.id,
            idempotency_key=body.idempotency_key,
        )
        if existing:
            _assert_matching_idempotency(existing, request_fingerprint)
            result = await service.role_permissions_out(db, role=role)
            return success_response(data=result.model_dump(mode="json"))
    if role.grant_version != body.expected_grant_version:
        await _raise_page_grant_conflict(
            db,
            resource_type="identity.role_page_permissions",
            resource_id=role.id,
            submitted_version=body.expected_grant_version,
            current_version=role.grant_version,
        )
    normalized = service.normalize_inputs(body.grants, allow_inherit=False)
    await service.validate_department_ids(db, grants=normalized)
    old = await page_repo.list_role_grants(db, role_ids=[role.id])
    created = await page_repo.replace_role_grants(
        db,
        role_id=role.id,
        grants=normalized,
        actor_id=current_user.id,
    )
    role.grant_version += 1
    role.updated_by = current_user.id
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="replace_role_page_permissions",
        resource_type="identity.role_page_permissions",
        resource_id=role.id,
        old_value={"grants": _grant_payload(old)},
        new_value={
            "grants": _grant_payload(created),
            "reason": body.reason,
            "grant_version": role.grant_version,
            "idempotency_key": str(body.idempotency_key)
            if body.idempotency_key
            else None,
            "request_fingerprint": request_fingerprint,
        },
    )
    await db.commit()
    await publish_permissions_changed_all()
    result = await service.role_permissions_out(db, role=role)
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.post(
    "/roles/{role_id}/page-permissions/preview",
    summary="预演角色页面权限用户影响",
    response_model=RolePagePermissionsPreviewOut,
)
async def preview_role_page_permissions(
    role_id: UUID,
    body: RolePagePermissionsUpdate,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    role = await _get_role_or_404(db, role_id)
    if role.code == "super_admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统管理员页面权限不可修改")
    service = PagePermissionService()
    if role.grant_version != body.expected_grant_version:
        await _raise_page_grant_conflict(
            db,
            resource_type="identity.role_page_permissions",
            resource_id=role.id,
            submitted_version=body.expected_grant_version,
            current_version=role.grant_version,
        )
    normalized = service.normalize_inputs(body.grants, allow_inherit=False)
    await service.validate_department_ids(db, grants=normalized)
    result = await service.role_permissions_preview(
        db,
        role=role,
        proposed_grants=normalized,
        module_access_mode=settings.effective_module_access_mode,
    )
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.get(
    "/users/{user_id}/page-permissions/history",
    summary="查看用户页面权限历史",
    response_model=PagePermissionHistoryPageOut,
)
async def get_user_page_permission_history(
    user_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor_user_id: UUID | None = Query(default=None),
    source: Literal["manual", "rollback", "health_remediation"] | None = Query(
        default=None
    ),
    page_key: str | None = Query(default=None, max_length=255),
    change_kind: Literal["grant", "expand", "restrict", "revoke", "mixed"]
    | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> JSONResponse:
    await _get_target_user_or_404(db, user_id)
    result = await PagePermissionService().permission_history_page(
        db,
        resource_type="identity.user_page_permissions",
        resource_id=user_id,
        page=page,
        page_size=page_size,
        actor_user_id=actor_user_id,
        source=source,
        page_key=page_key,
        change_kind=change_kind,
        date_from=date_from,
        date_to=date_to,
    )
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.get(
    "/roles/{role_id}/page-permissions/history",
    summary="查看角色页面权限历史",
    response_model=PagePermissionHistoryPageOut,
)
async def get_role_page_permission_history(
    role_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor_user_id: UUID | None = Query(default=None),
    source: Literal["manual", "rollback", "health_remediation"] | None = Query(
        default=None
    ),
    page_key: str | None = Query(default=None, max_length=255),
    change_kind: Literal["grant", "expand", "restrict", "revoke", "mixed"]
    | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> JSONResponse:
    await _get_role_or_404(db, role_id)
    result = await PagePermissionService().permission_history_page(
        db,
        resource_type="identity.role_page_permissions",
        resource_id=role_id,
        page=page,
        page_size=page_size,
        actor_user_id=actor_user_id,
        source=source,
        page_key=page_key,
        change_kind=change_kind,
        date_from=date_from,
        date_to=date_to,
    )
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.get(
    "/users/{user_id}/page-permissions/history/export",
    summary="导出用户页面权限历史",
)
async def export_user_page_permission_history(
    user_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_target_user_or_404(db, user_id)
    items = await PagePermissionService().permission_history(
        db,
        resource_type="identity.user_page_permissions",
        resource_id=user_id,
        limit=5000,
    )
    return _page_permission_history_csv(items, target_name=user.name)


@rbac_router.get(
    "/roles/{role_id}/page-permissions/history/export",
    summary="导出角色页面权限历史",
)
async def export_role_page_permission_history(
    role_id: UUID,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    role = await _get_role_or_404(db, role_id)
    items = await PagePermissionService().permission_history(
        db,
        resource_type="identity.role_page_permissions",
        resource_id=role_id,
        limit=5000,
    )
    return _page_permission_history_csv(items, target_name=role.name)


@rbac_router.post(
    "/users/{user_id}/page-permissions/rollback/preview",
    summary="预演用户页面权限回滚",
    response_model=PagePermissionRollbackPreviewOut,
)
async def preview_user_page_permission_rollback(
    user_id: UUID,
    body: PagePermissionRollbackPreviewRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    user = await _get_target_user_or_404(db, user_id)
    if user.grant_version != body.expected_grant_version:
        await _raise_page_grant_conflict(
            db,
            resource_type="identity.user_page_permissions",
            resource_id=user.id,
            submitted_version=body.expected_grant_version,
            current_version=user.grant_version,
        )
    repo = PagePermissionRepository()
    history = await repo.get_page_permission_history(
        db,
        audit_id=body.audit_id,
        resource_type="identity.user_page_permissions",
        resource_id=user.id,
    )
    if history is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "授权历史不存在")
    service = PagePermissionService()
    current = _grant_payload(await repo.list_user_grants(db, user_id=user.id))
    target = service.normalize_inputs(
        _snapshot_inputs(list((history.new_value or {}).get("grants") or [])),
        allow_inherit=True,
    )
    await service.validate_department_ids(db, grants=target)
    changes = service.history_changes(current, target)
    kinds = {item.kind for item in changes}
    impact = (
        "expanded"
        if kinds and kinds <= {"grant", "expand"}
        else "restricted"
        if kinds and kinds <= {"revoke", "restrict"}
        else "mixed"
    )
    result = PagePermissionRollbackPreviewOut(
        target_type="user",
        target_id=user.id,
        current_grant_version=user.grant_version,
        history_grant_version=(history.new_value or {}).get("grant_version"),
        changes=changes,
        affected_user_count=1 if changes else 0,
        expanded_user_count=1 if changes and impact == "expanded" else 0,
        restricted_user_count=1 if changes and impact == "restricted" else 0,
        mixed_user_count=1 if changes and impact == "mixed" else 0,
        users_with_overrides=1 if target else 0,
        affected_user_samples=(
            [
                RolePagePermissionAffectedUserOut(
                    user_id=user.id, user_name=user.name, impact=impact
                )
            ]
            if changes
            else []
        ),
    )
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.post(
    "/roles/{role_id}/page-permissions/rollback/preview",
    summary="预演角色页面权限回滚",
    response_model=PagePermissionRollbackPreviewOut,
)
async def preview_role_page_permission_rollback(
    role_id: UUID,
    body: PagePermissionRollbackPreviewRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    role = await _get_role_or_404(db, role_id)
    if role.grant_version != body.expected_grant_version:
        await _raise_page_grant_conflict(
            db,
            resource_type="identity.role_page_permissions",
            resource_id=role.id,
            submitted_version=body.expected_grant_version,
            current_version=role.grant_version,
        )
    repo = PagePermissionRepository()
    history = await repo.get_page_permission_history(
        db,
        audit_id=body.audit_id,
        resource_type="identity.role_page_permissions",
        resource_id=role.id,
    )
    if history is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "授权历史不存在")
    service = PagePermissionService()
    current = _grant_payload(await repo.list_role_grants(db, role_ids=[role.id]))
    target = service.normalize_inputs(
        _snapshot_inputs(list((history.new_value or {}).get("grants") or [])),
        allow_inherit=False,
    )
    await service.validate_department_ids(db, grants=target)
    impact = await service.role_permissions_preview(
        db,
        role=role,
        proposed_grants=target,
        module_access_mode=settings.effective_module_access_mode,
    )
    result = PagePermissionRollbackPreviewOut(
        target_type="role",
        target_id=role.id,
        current_grant_version=role.grant_version,
        history_grant_version=(history.new_value or {}).get("grant_version"),
        changes=service.history_changes(current, target),
        affected_user_count=impact.affected_user_count,
        expanded_user_count=impact.expanded_user_count,
        restricted_user_count=impact.restricted_user_count,
        mixed_user_count=impact.mixed_user_count,
        users_with_overrides=impact.users_with_overrides,
        affected_user_samples=impact.affected_user_samples,
    )
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.post(
    "/users/{user_id}/page-permissions/rollback",
    summary="回滚用户页面权限",
    response_model=UserPagePermissionsOut,
)
async def rollback_user_page_permissions(
    user_id: UUID,
    body: PagePermissionRollbackRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "管理员不能回滚自己的页面权限")
    permission_repo = PermissionGrantRepository()
    user = await permission_repo.get_user_for_update(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if user.role == "admin":
        raise HTTPException(400, "系统管理员拥有全部权限，无需回滚页面覆盖")
    page_repo = PagePermissionRepository()
    service = PagePermissionService()
    request_fingerprint = _page_permission_request_fingerprint(
        reason=body.reason, audit_id=body.audit_id
    )
    if body.idempotency_key:
        existing = await page_repo.find_page_permission_idempotency(
            db,
            resource_type="identity.user_page_permissions",
            resource_id=user.id,
            idempotency_key=body.idempotency_key,
        )
        if existing:
            _assert_matching_idempotency(existing, request_fingerprint)
            result = await service.user_permissions_out(db, user=user)
            return success_response(data=result.model_dump(mode="json"))
    if user.grant_version != body.expected_grant_version:
        await _raise_page_grant_conflict(
            db,
            resource_type="identity.user_page_permissions",
            resource_id=user.id,
            submitted_version=body.expected_grant_version,
            current_version=user.grant_version,
        )
    history = await page_repo.get_page_permission_history(
        db,
        audit_id=body.audit_id,
        resource_type="identity.user_page_permissions",
        resource_id=user.id,
    )
    if history is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "授权历史不存在")
    normalized = service.normalize_inputs(
        _snapshot_inputs(list((history.new_value or {}).get("grants") or [])),
        allow_inherit=True,
    )
    await service.validate_department_ids(db, grants=normalized)
    old = await page_repo.list_user_grants(db, user_id=user.id)
    created = await page_repo.replace_user_grants(
        db, user_id=user.id, grants=normalized, actor_id=current_user.id
    )
    user.grant_version += 1
    user.updated_by = current_user.id
    await permission_repo.create_outbox_event(
        db,
        user_id=user.id,
        grant_version=user.grant_version,
        actor_id=current_user.id,
        event_type="identity.user_page_grants.changed.v1",
    )
    await _audit(
        db,
        current_user,
        action="rollback_user_page_permissions",
        resource_type="identity.user_page_permissions",
        resource_id=user.id,
        old_value={"grants": _grant_payload(old)},
        new_value={
            "grants": _grant_payload(created),
            "reason": body.reason,
            "grant_version": user.grant_version,
            "rollback_of": str(history.id),
            "idempotency_key": str(body.idempotency_key)
            if body.idempotency_key
            else None,
            "request_fingerprint": request_fingerprint,
        },
    )
    await db.commit()
    await publish_permissions_changed(user.id)
    result = await service.user_permissions_out(db, user=user)
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.post(
    "/roles/{role_id}/page-permissions/rollback",
    summary="回滚角色页面权限",
    response_model=RolePagePermissionsOut,
)
async def rollback_role_page_permissions(
    role_id: UUID,
    body: PagePermissionRollbackRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    page_repo = PagePermissionRepository()
    role = await page_repo.get_role_for_update(db, role_id=role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在")
    if role.code == "super_admin":
        raise HTTPException(400, "系统管理员页面权限不可回滚")
    actor_roles = await resolve_user_roles(db, current_user.id)
    if (
        current_user.role != "admin"
        and not any(item.code == "super_admin" for item in actor_roles)
        and any(item.id == role.id for item in actor_roles)
    ):
        raise HTTPException(403, "不能通过回滚本人所属角色调整自身页面授权")
    service = PagePermissionService()
    request_fingerprint = _page_permission_request_fingerprint(
        reason=body.reason, audit_id=body.audit_id
    )
    if body.idempotency_key:
        existing = await page_repo.find_page_permission_idempotency(
            db,
            resource_type="identity.role_page_permissions",
            resource_id=role.id,
            idempotency_key=body.idempotency_key,
        )
        if existing:
            _assert_matching_idempotency(existing, request_fingerprint)
            result = await service.role_permissions_out(db, role=role)
            return success_response(data=result.model_dump(mode="json"))
    if role.grant_version != body.expected_grant_version:
        await _raise_page_grant_conflict(
            db,
            resource_type="identity.role_page_permissions",
            resource_id=role.id,
            submitted_version=body.expected_grant_version,
            current_version=role.grant_version,
        )
    history = await page_repo.get_page_permission_history(
        db,
        audit_id=body.audit_id,
        resource_type="identity.role_page_permissions",
        resource_id=role.id,
    )
    if history is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "授权历史不存在")
    normalized = service.normalize_inputs(
        _snapshot_inputs(list((history.new_value or {}).get("grants") or [])),
        allow_inherit=False,
    )
    await service.validate_department_ids(db, grants=normalized)
    old = await page_repo.list_role_grants(db, role_ids=[role.id])
    created = await page_repo.replace_role_grants(
        db, role_id=role.id, grants=normalized, actor_id=current_user.id
    )
    role.grant_version += 1
    role.updated_by = current_user.id
    await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    await _audit(
        db,
        current_user,
        action="rollback_role_page_permissions",
        resource_type="identity.role_page_permissions",
        resource_id=role.id,
        old_value={"grants": _grant_payload(old)},
        new_value={
            "grants": _grant_payload(created),
            "reason": body.reason,
            "grant_version": role.grant_version,
            "rollback_of": str(history.id),
            "idempotency_key": str(body.idempotency_key)
            if body.idempotency_key
            else None,
            "request_fingerprint": request_fingerprint,
        },
    )
    await db.commit()
    await publish_permissions_changed_all()
    result = await service.role_permissions_out(db, role=role)
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.get(
    "/page-permissions/health",
    summary="检查页面权限健康状态",
    response_model=PagePermissionHealthOut,
)
async def get_page_permission_health(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await PagePermissionService().permission_health(db)
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.post(
    "/page-permissions/health/remediate",
    summary="修复页面权限健康问题",
    response_model=PagePermissionHealthRemediationOut,
)
async def remediate_page_permission_health_issue(
    body: PagePermissionHealthRemediationRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    page_repo = PagePermissionRepository()
    permission_repo = PermissionGrantRepository()
    service = PagePermissionService()
    target: Role | User
    grant: RolePageGrant | UserPageGrant | None
    if body.target_type == "role":
        role = await page_repo.get_role_for_update(db, role_id=body.target_id)
        if role is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在")
        if role.code == "super_admin":
            raise HTTPException(400, "系统管理员页面权限不可自动修复")
        await _assert_not_own_role(db, current_user, role.id)
        target = role
        grant = await page_repo.get_role_grant_for_update(
            db, role_id=role.id, page_key=body.page_key
        )
        resource_type = "identity.role_page_permissions"
    else:
        user = await permission_repo.get_user_for_update(db, body.target_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
        if user.id == current_user.id:
            raise HTTPException(403, "管理员不能自动修复自己的页面权限")
        if user.role == "admin":
            raise HTTPException(400, "系统管理员无需页面权限修复")
        target = user
        grant = await page_repo.get_user_grant_for_update(
            db, user_id=user.id, page_key=body.page_key
        )
        resource_type = "identity.user_page_permissions"
    if target.grant_version != body.expected_grant_version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"授权版本冲突，当前版本为 {target.grant_version}",
        )
    if grant is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该健康问题已被处理，请重新检查")
    health = await service.permission_health(db)
    issue = next(
        (
            item
            for item in health.issues
            if item.code == body.code
            and item.target_type == body.target_type
            and item.target_id == body.target_id
            and item.page_key == body.page_key
        ),
        None,
    )
    if issue is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该健康问题已变化，请重新检查")

    old = (
        await page_repo.list_role_grants(db, role_ids=[target.id])
        if body.target_type == "role"
        else await page_repo.list_user_grants(db, user_id=target.id)
    )
    message = "问题已修复"
    if body.code in {"retired_page", "redundant_user_override"}:
        await page_repo.remove_grant(db, grant)
        message = (
            "已恢复角色基线"
            if body.code == "redundant_user_override"
            else "已移除停用页面授权"
        )
    else:
        valid_ids = await page_repo.existing_department_ids(
            db, department_ids=set(grant.department_ids or [])
        )
        if not valid_ids and grant.scope_type == "departments":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "指定部门已全部失效，请进入授权编辑器选择新的数据范围",
            )
        grant.department_ids = sorted(valid_ids)
        grant.updated_by = current_user.id
        await db.flush()
        message = "已清除失效部门引用"

    target.grant_version += 1
    target.updated_by = current_user.id
    current = (
        await page_repo.list_role_grants(db, role_ids=[target.id])
        if body.target_type == "role"
        else await page_repo.list_user_grants(db, user_id=target.id)
    )
    await _audit(
        db,
        current_user,
        action=f"remediate_{body.target_type}_page_permissions",
        resource_type=resource_type,
        resource_id=target.id,
        old_value={"grants": _grant_payload(old)},
        new_value={
            "grants": _grant_payload(current),
            "reason": body.reason,
            "grant_version": target.grant_version,
            "health_issue": body.code,
        },
    )
    if body.target_type == "role":
        await _bump_all_user_grant_versions(db, actor_id=current_user.id)
    else:
        await permission_repo.create_outbox_event(
            db,
            user_id=target.id,
            grant_version=target.grant_version,
            actor_id=current_user.id,
            event_type="identity.user_page_grants.changed.v1",
        )
    await db.commit()
    if body.target_type == "role":
        await publish_permissions_changed_all()
    else:
        await publish_permissions_changed(target.id)
    result = PagePermissionHealthRemediationOut(
        grant_version=target.grant_version, message=message
    )
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.post(
    "/page-permissions/simulate",
    summary="按页面和业务动作验证权限",
    response_model=PagePermissionSimulationOut,
)
async def simulate_page_permission(
    body: PagePermissionSimulationRequest,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    user = await _get_target_user_or_404(db, body.user_id)
    page_service = PagePermissionService()
    grants = await page_service.effective_grants(db, user=user)
    page_key = canonical_page_key(body.page_key)
    effective = next((item for item in grants if item.page_key == page_key), None)
    definition = get_page_definition(page_key)
    module_allowed = bool(
        definition
        and (
            settings.effective_module_access_mode == "all"
            or await page_service.is_super_admin(db, user_id=user.id)
            or await PermissionGrantRepository().has_module_view(
                db,
                user_id=user.id,
                module_code=definition.module_code,
            )
        )
    )
    allowed = bool(
        module_allowed
        and effective is not None
        and body.permission in effective.permissions
    )
    if module_allowed and body.sensitive_action:
        allowed = bool(
            allowed
            and effective is not None
            and body.sensitive_action in effective.sensitive_actions
        )
    if definition is None:
        reason = "所选页面未登记或已失效"
    elif not module_allowed:
        reason = "当前账号未获得所属模块访问权限"
    elif allowed:
        reason = (
            "当前账号满足模块入口及所选页面授权条件；"
            "实际接口还需核对页面绑定、数据范围和业务规则"
        )
    else:
        reason = "当前账号已获模块访问，但未获得所选页面业务权限"
    result = PagePermissionSimulationOut(
        allowed=allowed, reason=reason, effective=effective
    )
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.get(
    "/page-permissions/modules",
    summary="自动检查模块页面权限接入完整性",
    response_model=list[PermissionModuleIntegrationOut],
)
async def list_page_permission_rollouts(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    service = PagePermissionService()
    modules = sorted(set(MODULES_BY_CODE) | set(PAGES_BY_MODULE))
    items = []
    for code in modules:
        gaps = await service.integration_gaps(db, module_code=code)
        items.append(PermissionModuleIntegrationOut(
            module_code=code, passed=not gaps, catalog_gaps=gaps
        ))
    return success_response(data=[item.model_dump(mode="json") for item in items])


@rbac_router.get(
    "/page-permissions/modules/{module_code}/preview",
    summary="预览模块页面权限发布影响",
    response_model=PermissionModuleRolloutPreviewOut,
)
async def preview_page_permission_rollout(
    module_code: str,
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if module_code not in MODULES_BY_CODE and module_code not in PAGES_BY_MODULE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "模块不存在")
    result = await PagePermissionService().rollout_preview(db, module_code=module_code)
    return success_response(data=result.model_dump(mode="json"))


@rbac_router.get("/permissions/export", summary="权限清单导出")
async def export_permissions(
    current_user: IdentityAdminUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        select(User).where(User.is_deleted.is_(False)).order_by(User.name)
    )
    users = list(result.scalars().all())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "姓名",
            "部门",
            "菜单页面",
            "模块",
            "访问",
            "查询",
            "操作",
            "高风险业务动作",
            "数据范围",
            "授权来源",
            "角色来源",
            "当前接入检查",
        ]
    )
    service = PagePermissionService()
    repo = PagePermissionRepository()
    department_labels = await repo.department_labels(db)
    integration_checks = {
        code: not await service.integration_gaps(db, module_code=code)
        for code in sorted(set(MODULES_BY_CODE) | set(PAGES_BY_MODULE))
    }
    scope_names = {
        "all": "全部部门",
        "department_tree": "本部门及下级",
        "departments": "指定部门及下级",
        "self": "仅本人",
        "not_applicable": "不适用",
    }
    source_names = {
        "role": "角色基线",
        "user": "用户覆盖",
        "none": "未授权",
        "super_admin": "系统管理员",
    }
    for user in users:
        grants = await service.effective_grants(db, user=user)
        rows = []
        for grant in grants:
            page = get_page_definition(grant.page_key)
            if page is None:
                continue
            module = MODULES_BY_CODE.get(page.module_code)
            scope_text = scope_names.get(grant.data_scope.scope_type, "未知范围")
            if grant.data_scope.department_ids:
                scope_text += "：" + "；".join(
                    department_labels.get(key, "已失效部门")
                    for key in grant.data_scope.department_ids
                )
            rows.append(
                [
                    user.name,
                    user.department or "",
                    page.page_name,
                    module.name if module else "系统管理",
                    *[
                        "是" if level in grant.permissions else "否"
                        for level in ("access", "query", "operate")
                    ],
                    "；".join(
                        action.name
                        for action in page.sensitive_actions
                        if action.key in grant.sensitive_actions
                    ),
                    scope_text,
                    source_names[grant.source],
                    "；".join(grant.source_role_names),
                    (
                        "自动检查通过"
                        if integration_checks.get(grant.module_code)
                        else "接入有缺口"
                    ),
                ]
            )
        if not rows:
            rows.append(
                [
                    user.name,
                    user.department or "",
                    "无页面授权",
                    "",
                    "否",
                    "否",
                    "否",
                    "",
                    "",
                    "未授权",
                    "",
                    "",
                ]
            )
        # User-controlled names must not become spreadsheet formulas on open.
        writer.writerows(
            [
                [
                    "'" + cell
                    if cell.lstrip().startswith(("=", "+", "-", "@"))
                    else cell
                    for cell in row
                ]
                for row in rows
            ]
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="permissions.csv"'},
    )
