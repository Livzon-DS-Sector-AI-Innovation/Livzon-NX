import asyncio
import logging
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.response import success_response
from app.platform.identity.deps import AdminUser, CurrentUser
from app.platform.identity.models import Department
from app.platform.identity.repository import (
    DepartmentRepository,
    ExternalIdentityBindingRepository,
    UserRepository,
)
from app.platform.identity.schemas import (
    DepartmentResponse,
    DepartmentTreeNode,
    ExternalIdentityBindingCreate,
    ExternalIdentityBindingOut,
    ExternalIdentityBindingStatusUpdate,
    ExternalIdentityConflictOut,
    FeishuConfigApiResponse,
    FeishuConfigUpsert,
    FeishuDiagnosticApiResponse,
    FeishuGatewayRestartApiResponse,
    LivzonAccessScopeOut,
    LocalLoginRequest,
    LocalUserCreate,
    PasswordResetRequest,
    PermissionAuditItem,
    PersonnelItem,
    PersonnelListResponse,
    TokenResponse,
    UserManagementItem,
    UserManagementListResponse,
    UserManagementUpdate,
    UserModulePermissionsOut,
    UserModulePermissionsUpdate,
    UserResponse,
)
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
OAUTH_STATE_COOKIE = "feishu_oauth_state"
AUTH_TOKEN_COOKIE = "auth_token"

auth_router = APIRouter(prefix="/auth", tags=["认证"])
user_router = APIRouter(tags=["用户信息"])
dept_router = APIRouter(prefix="/departments", tags=["组织架构"])
personnel_router = APIRouter(prefix="/personnel", tags=["人员名单"])
sync_router = APIRouter(prefix="/sync", tags=["飞书同步"])
feishu_config_router = APIRouter(prefix="/feishu-config", tags=["Livzon 助手飞书设置"])
feishu_router = APIRouter(prefix="/feishu", tags=["Livzon 助手飞书"])


# ── Auth (SSO) ──────────────────────────────────────────────────────


def _login_error_redirect(settings: Settings, error: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/login?{urlencode({'error': error})}",
        status_code=302,
    )


@auth_router.get("/login", summary="飞书授权登录入口")
async def login(
    next: str | None = Query(None, description="登录成功后的站内跳转路径"),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect the browser to Feishu's OAuth authorization page."""
    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        return _login_error_redirect(settings, "feishu_not_configured")
    if not settings.FEISHU_REDIRECT_URI:
        return _login_error_redirect(settings, "redirect_uri_missing")

    from app.platform.identity.service import generate_state_token
    from app.platform.integrations.feishu.oauth import FeishuOAuthClient

    state = generate_state_token(next)
    oauth = FeishuOAuthClient(
        app_id=settings.FEISHU_APP_ID,
        app_secret=settings.FEISHU_APP_SECRET,
        redirect_uri=settings.FEISHU_REDIRECT_URI,
        scopes=settings.FEISHU_SCOPES,
    )
    authorize_url = oauth.build_authorize_url(state)
    response = RedirectResponse(url=authorize_url, status_code=302)
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=300,
        path="/api/v1/identity/auth",
    )
    return response


@auth_router.post("/local/login", summary="本地账号登录", response_model=TokenResponse)
async def local_login(
    payload: LocalLoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Login with local username/password and return the same JWT used by SSO."""
    from app.platform.identity.service import authenticate_local_user

    local_login_mode = getattr(
        settings,
        "effective_local_login_mode",
        "disabled" if settings.is_production else "enabled",
    )
    if local_login_mode == "disabled":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "本地账号登录已禁用，请使用飞书授权登录",
        )

    user, token = await authenticate_local_user(
        db, username=payload.username, password=payload.password
    )
    if local_login_mode == "admin_only" and user.role != "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "应急登录仅允许管理员账号",
        )
    response = TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )
    json_response = success_response(data=response.model_dump(mode="json"))
    json_response.set_cookie(
        AUTH_TOKEN_COOKIE,
        token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=getattr(settings, "JWT_EXPIRE_SECONDS", 86400),
        path="/",
    )
    return json_response


@auth_router.get("/callback", summary="飞书 SSO 回调")
async def auth_callback(
    code: str | None = Query(None),
    state: str = Query(""),
    error: str | None = Query(None),
    feishu_oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle the OAuth callback from Feishu.

    Exchanges code for tokens, upserts user, generates JWT, then redirects
    to the frontend with the token as a query parameter.
    """
    from app.platform.identity.service import (
        handle_oauth_callback,
        validate_state_token,
    )

    response: RedirectResponse
    if error:
        response = _login_error_redirect(settings, "access_denied")
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/identity/auth")
        return response

    payload = validate_state_token(state, feishu_oauth_state)
    if not payload:
        response = _login_error_redirect(settings, "invalid_state")
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/identity/auth")
        return response

    if not code:
        response = _login_error_redirect(settings, "missing_code")
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/identity/auth")
        return response

    try:
        _, token = await handle_oauth_callback(db, code)
    except PermissionError:
        logger.warning("OAuth callback rejected disabled user")
        response = _login_error_redirect(settings, "account_disabled")
    except Exception:
        logger.exception("OAuth callback failed")
        response = _login_error_redirect(settings, "callback_failed")
    else:
        next_path = payload.get("next") if isinstance(payload, dict) else None
        response = RedirectResponse(
            url=f"{settings.FRONTEND_URL}{next_path or '/production'}",
            status_code=302,
        )
        response.set_cookie(
            AUTH_TOKEN_COOKIE,
            token,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
            max_age=getattr(settings, "JWT_EXPIRE_SECONDS", 86400),
            path="/",
        )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/identity/auth")
    return response


@auth_router.get("/logout", summary="兼容登出入口")
async def logout(
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect to the frontend logout route where browser cookies are cleared."""
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/auth/logout",
        status_code=302,
    )


# ── Current User ────────────────────────────────────────────────────


@user_router.get("/me", summary="获取当前平台用户信息")
async def get_me(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Return the current platform user."""
    if current_user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    from app.platform.identity.permission_repository import PermissionGrantRepository

    response = UserResponse.model_validate(current_user)
    if settings.effective_module_access_mode == "all":
        response.module_codes = sorted(MODULES_BY_CODE)
    elif current_user.role == "admin":
        response.module_codes = sorted(MODULES_BY_CODE)
    else:
        grants = await PermissionGrantRepository().list_grants(
            db, user_id=current_user.id
        )
        response.module_codes = sorted(
            grant.module_code
            for grant in grants
            if "module.view" in set(grant.permissions or [])
        )
    return success_response(data=response.model_dump())


# ── User Management ────────────────────────────────────────────────


@user_router.get(
    "/users", summary="管理员查询用户列表", response_model=UserManagementListResponse
)
async def list_users(
    keyword: str | None = Query(None, description="按姓名/账号/邮箱/手机号/工号搜索"),
    role: str | None = Query(None, pattern="^(admin|user)$"),
    status_filter: str | None = Query(
        None, alias="status", pattern="^(active|disabled)$"
    ),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    repo = UserRepository()
    users, total = await repo.list_users(
        db,
        keyword=keyword,
        role=role,
        status=status_filter,
        offset=offset,
        limit=limit,
    )
    response = UserManagementListResponse(
        items=[UserManagementItem.model_validate(user) for user in users],
        total=total,
        offset=offset,
        limit=limit,
    )
    return success_response(data=response.model_dump(mode="json"))


@user_router.post(
    "/users", summary="管理员创建本地用户", response_model=UserManagementItem
)
async def create_local_user(
    payload: LocalUserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.platform.identity.service import hash_password

    repo = UserRepository()
    existing = await repo.get_by_username(db, payload.username)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")

    user = await repo.create(
        db,
        username=payload.username,
        password_hash=hash_password(payload.password),
        name=payload.name,
        email=payload.email,
        mobile=payload.mobile,
        employee_no=payload.employee_no,
        department=payload.department,
        position=payload.position,
        role=payload.role,
        status=payload.status,
        auth_source="local",
    )
    user.created_by = current_user.id
    user.updated_by = current_user.id
    await db.flush()
    return success_response(
        data=UserManagementItem.model_validate(user).model_dump(mode="json")
    )


@user_router.put(
    "/users/{user_id}", summary="管理员更新用户", response_model=UserManagementItem
)
async def update_user(
    user_id: UUID,
    payload: UserManagementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    repo = UserRepository()
    user = await repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")

    updates = payload.model_dump(exclude_unset=True)
    role_changed = "role" in updates and updates["role"] != user.role
    for field, value in updates.items():
        setattr(user, field, value)
    if role_changed:
        user.grant_version += 1
    user.updated_by = current_user.id
    await db.flush()
    return success_response(
        data=UserManagementItem.model_validate(user).model_dump(mode="json")
    )


@user_router.post("/users/{user_id}/reset-password", summary="管理员重置用户密码")
async def reset_user_password(
    user_id: UUID,
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.platform.identity.service import hash_password

    repo = UserRepository()
    user = await repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    user.password_hash = hash_password(payload.password)
    user.auth_source = user.auth_source or "local"
    user.updated_by = current_user.id
    await db.flush()
    return success_response(data={"message": "密码已重置"})


@user_router.get(
    "/external-identity-bindings",
    summary="管理员查询外部身份绑定",
)
async def list_external_identity_bindings(
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    tenant_id: str | None = None,
    status_value: str | None = None,
    department: str | None = None,
    active_since: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    items, total = await ExternalIdentityBindingRepository().list_page(
        db,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
        keyword=keyword,
        tenant_id=tenant_id,
        status_value=status_value,
        department=department,
        active_since=active_since,
    )
    return success_response(
        data={
            "items": [
                {
                    **ExternalIdentityBindingOut.model_validate(binding).model_dump(
                        mode="json"
                    ),
                    "local_user_name": user.name,
                    "local_user_department": user.department,
                    "local_user_status": user.status,
                }
                for binding, user in items
            ],
            "page": max(1, page),
            "page_size": min(max(1, page_size), 100),
            "total": total,
        }
    )


@user_router.get(
    "/external-identity-bindings/conflicts",
    summary="管理员查询飞书身份绑定冲突",
    response_model=list[ExternalIdentityConflictOut],
)
async def list_external_identity_binding_conflicts(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> list[ExternalIdentityConflictOut]:
    from app.platform.identity.service import list_livzon_identity_conflicts

    return await list_livzon_identity_conflicts(db)


@user_router.post(
    "/external-identity-bindings",
    summary="管理员创建外部身份绑定",
    status_code=status.HTTP_201_CREATED,
)
async def create_external_identity_binding(
    payload: ExternalIdentityBindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.platform.audit.models import AuditLog

    local_user = await UserRepository().get_by_id(db, payload.local_user_id)
    if local_user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "本地用户不存在")
    try:
        binding = await ExternalIdentityBindingRepository().create(
            db,
            **payload.model_dump(),
            actor_id=current_user.id,
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "该飞书身份已经绑定",
        ) from exc
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="POST",
            path="/api/v1/identity/external-identity-bindings",
            status_code=201,
            resource_type="external_identity_binding",
            resource_id=binding.id,
            action="create_external_identity_binding",
            extra={"tenant_id": binding.tenant_id, "source": binding.source},
        )
    )
    return success_response(
        data=ExternalIdentityBindingOut.model_validate(binding).model_dump(mode="json")
    )


@user_router.post(
    "/external-identity-bindings/{binding_id}/status",
    summary="管理员更新外部身份绑定状态",
)
async def update_external_identity_binding_status(
    binding_id: UUID,
    payload: ExternalIdentityBindingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.platform.audit.models import AuditLog

    repo = ExternalIdentityBindingRepository()
    binding = await repo.get(db, binding_id)
    if binding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "外部身份绑定不存在")
    binding = await repo.set_status(
        db,
        binding,
        status_value=payload.status,
        actor_id=current_user.id,
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="POST",
            path=f"/api/v1/identity/external-identity-bindings/{binding_id}/status",
            status_code=200,
            resource_type="external_identity_binding",
            resource_id=binding.id,
            action="update_external_identity_binding_status",
            extra={"status": payload.status},
        )
    )
    return success_response(
        data=ExternalIdentityBindingOut.model_validate(binding).model_dump(mode="json")
    )


def _parse_if_match(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "If-Match 必须是授权版本整数",
        ) from exc
    if parsed < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "授权版本不能小于 0")
    return parsed


@user_router.get(
    "/users/{user_id}/module-permissions",
    summary="管理员查询用户模块授权",
    response_model=UserModulePermissionsOut,
)
async def get_user_module_permissions(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.modules.agent.access_scope import AgentAccessScopeService
    from app.platform.audit.models import AuditLog
    from app.platform.identity.permissions import IdentityPermissionService

    service = IdentityPermissionService()
    result = await service.get_user_permissions(
        db, target_user_id=user_id, current_user=current_user
    )
    snapshot = await AgentAccessScopeService().get_snapshot(db, user_id=user_id)
    if snapshot is not None:
        result.livzon_sync_status = snapshot.sync_status
        result.livzon_source_grant_version = snapshot.source_grant_version
        result.livzon_agent_scope_version = snapshot.agent_scope_version
        result.livzon_last_error = snapshot.last_error
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="GET",
            path=f"/api/v1/identity/users/{user_id}/module-permissions",
            status_code=200,
            resource_type="user_module_permissions",
            resource_id=user_id,
            action="view_user_module_permissions",
            extra={"grant_version": result.grant_version},
        )
    )
    return success_response(data=result.model_dump(mode="json"))


@user_router.put(
    "/users/{user_id}/module-permissions",
    summary="管理员替换用户模块授权",
    response_model=UserModulePermissionsOut,
)
async def replace_user_module_permissions(
    user_id: UUID,
    payload: UserModulePermissionsUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.modules.agent.access_scope import AgentAccessScopeService
    from app.platform.identity.permissions import IdentityPermissionService

    permission_service = IdentityPermissionService()
    target, grants, event = await permission_service.replace_user_permissions(
        db,
        target_user_id=user_id,
        request=payload,
        current_user=current_user,
        expected_version_from_header=_parse_if_match(if_match),
    )
    scope_service = AgentAccessScopeService()
    snapshot = None
    try:
        snapshot = await scope_service.synchronize(
            db, user_id=user_id, actor_id=current_user.id
        )
        await permission_service.repo.mark_outbox_processed(
            db, event, actor_id=current_user.id
        )
    except Exception as exc:
        await permission_service.repo.mark_outbox_failed(
            db, event, error=str(exc), actor_id=current_user.id
        )
        snapshot = await scope_service.get_snapshot(db, user_id=user_id)
    result = permission_service._permissions_out(target, grants)
    if snapshot is not None:
        result.livzon_sync_status = snapshot.sync_status
        result.livzon_source_grant_version = snapshot.source_grant_version
        result.livzon_agent_scope_version = snapshot.agent_scope_version
        result.livzon_last_error = snapshot.last_error
    else:
        result.livzon_sync_status = "failed"
        result.livzon_last_error = event.last_error
    return success_response(data=result.model_dump(mode="json"))


@user_router.get(
    "/users/{user_id}/livzon-access-scope",
    summary="管理员查询用户 Livzon 有效范围",
    response_model=LivzonAccessScopeOut,
)
async def get_user_livzon_access_scope(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.modules.agent.access_scope import AgentAccessScopeService
    from app.platform.audit.models import AuditLog
    from app.platform.identity.permissions import IdentityPermissionService

    await IdentityPermissionService().get_user_permissions(
        db, target_user_id=user_id, current_user=current_user
    )
    scope_service = AgentAccessScopeService()
    snapshot = await scope_service.get_snapshot(db, user_id=user_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Livzon 范围尚未同步")
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="GET",
            path=f"/api/v1/identity/users/{user_id}/livzon-access-scope",
            status_code=200,
            resource_type="agent_access_scope",
            resource_id=user_id,
            action="view_user_livzon_access_scope",
            extra={"source_grant_version": snapshot.source_grant_version},
        )
    )
    result = scope_service.snapshot_out(snapshot)
    return success_response(data=result.model_dump(mode="json"))


@user_router.post(
    "/users/{user_id}/livzon-access-scope/sync",
    summary="管理员重新同步用户 Livzon 有效范围",
    response_model=LivzonAccessScopeOut,
)
async def sync_user_livzon_access_scope(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.modules.agent.access_scope import AgentAccessScopeService
    from app.platform.audit.models import AuditLog
    from app.platform.identity.permissions import IdentityPermissionService

    await IdentityPermissionService().get_user_permissions(
        db, target_user_id=user_id, current_user=current_user
    )
    scope_service = AgentAccessScopeService()
    snapshot = await scope_service.synchronize(
        db, user_id=user_id, actor_id=current_user.id
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="POST",
            path=f"/api/v1/identity/users/{user_id}/livzon-access-scope/sync",
            status_code=200,
            resource_type="agent_access_scope",
            resource_id=user_id,
            action="sync_user_livzon_access_scope",
            new_value={
                "source_grant_version": snapshot.source_grant_version,
                "agent_scope_version": snapshot.agent_scope_version,
                "sync_status": snapshot.sync_status,
            },
        )
    )
    result = scope_service.snapshot_out(snapshot)
    return success_response(data=result.model_dump(mode="json"))


@user_router.get(
    "/users/{user_id}/permission-audit",
    summary="管理员查询用户授权审计",
    response_model=list[PermissionAuditItem],
)
async def get_user_permission_audit(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    from app.platform.identity.permissions import IdentityPermissionService

    items = await IdentityPermissionService().list_permission_audit(
        db,
        target_user_id=user_id,
        current_user=current_user,
        limit=limit,
    )
    return success_response(data=[item.model_dump(mode="json") for item in items])


# ── Departments ─────────────────────────────────────────────────────


def _build_department_tree(
    depts: list[Department],
    parent_id: str | None = None,
) -> list[DepartmentTreeNode]:
    """递归构建部门树。"""
    result: list[DepartmentTreeNode] = []
    for d in depts:
        if d.parent_feishu_department_id == parent_id or (
            parent_id is None and not d.parent_feishu_department_id
        ):
            node = DepartmentTreeNode(
                id=d.id,
                feishu_department_id=d.feishu_department_id,
                name=d.name,
                member_count=d.member_count,
                leader_user_id=d.leader_user_id,
                order=d.order,
                children=_build_department_tree(
                    depts,
                    d.feishu_department_id,
                ),
            )
            result.append(node)
    return result


@dept_router.get("", summary="获取部门列表 / 组织架构树")
async def list_departments(
    tree: bool = Query(False, description="是否返回树形结构"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取所有部门。传 ?tree=true 返回层级组织架构树。"""
    repo = DepartmentRepository()
    depts = await repo.list_all(db)

    if tree:
        nodes = _build_department_tree(depts, parent_id=None)
        return success_response(data=[n.model_dump() for n in nodes])

    return success_response(
        data=[DepartmentResponse.model_validate(d).model_dump() for d in depts],
    )


@dept_router.get("/{dept_id}", summary="获取部门详情")
async def get_department(
    dept_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """按 open_department_id 获取单个部门详情。"""
    repo = DepartmentRepository()
    dept = await repo.get_by_feishu_id(db, dept_id)
    if dept is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="部门不存在")
    return success_response(data=DepartmentResponse.model_validate(dept).model_dump())


# ── Personnel ───────────────────────────────────────────────────────


@personnel_router.get("", summary="获取人员名单")
async def list_personnel(
    department_id: str | None = Query(None, description="按部门 ID 筛选"),
    keyword: str | None = Query(None, description="按姓名搜索"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """分页获取所有人员名单，支持按部门和姓名筛选。"""
    repo = UserRepository()
    users, total = await repo.list_all(
        db,
        department_id=department_id,
        keyword=keyword,
        offset=offset,
        limit=limit,
    )

    items = [PersonnelItem.model_validate(u).model_dump() for u in users]
    resp = PersonnelListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )
    return success_response(data=resp.model_dump())


# ── Sync ────────────────────────────────────────────────────────────


@feishu_config_router.get(
    "",
    summary="获取 Livzon 助手飞书设置",
    response_model=FeishuConfigApiResponse,
)
async def get_livzon_feishu_config(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    """获取仅用于 Livzon 助手的飞书通讯录配置。"""
    from app.platform.identity.service import get_livzon_feishu_config_response

    data = await get_livzon_feishu_config_response(db)
    return success_response(data=data.model_dump(mode="json"))


@feishu_config_router.get(
    "/gateway-status",
    summary="查询 Hermes Feishu Gateway 状态",
)
async def get_livzon_feishu_gateway_status(
    settings: Settings = Depends(get_settings),
    current_user: AdminUser = None,
) -> JSONResponse:
    if not settings.HERMES_INTERNAL_URL or not settings.HERMES_INTERNAL_TOKEN:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Hermes 内部接口未配置"
        )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.HERMES_INTERNAL_URL.rstrip('/')}/internal/feishu/status",
                headers={"Authorization": f"Bearer {settings.HERMES_INTERNAL_TOKEN}"},
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Hermes Gateway 状态查询失败",
        ) from exc
    return success_response(data=response.json())


@feishu_config_router.post(
    "/gateway/restart",
    summary="重启 Hermes Feishu Gateway",
    response_model=FeishuGatewayRestartApiResponse,
)
async def restart_livzon_feishu_gateway(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    """重建飞书 Gateway 子进程连接，不重启 Hermes 服务或部署镜像。"""
    from app.platform.audit.models import AuditLog
    from app.platform.identity.service import restart_livzon_feishu_gateway as restart

    data = await restart()
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="POST",
            path="/api/v1/identity/feishu-config/gateway/restart",
            status_code=200,
            resource_type="feishu_gateway",
            action="restart_livzon_feishu_gateway",
            extra={
                "status": data.status,
                "previous_reconnects": data.previous_reconnects,
                "gateway_reconnects": data.gateway_reconnects,
                "config_version": data.config_version,
            },
        )
    )
    return success_response(data=data.model_dump(mode="json"))


@feishu_config_router.put(
    "",
    summary="保存 Livzon 助手飞书设置",
    response_model=FeishuConfigApiResponse,
)
async def save_livzon_feishu_config(
    payload: FeishuConfigUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    """保存仅用于 Livzon 助手的飞书自建应用凭证。"""
    from app.platform.identity.service import (
        save_livzon_feishu_config as save_config,
    )

    data = await save_config(db, payload)
    return success_response(data=data.model_dump(mode="json"))


@feishu_config_router.get(
    "/authorizations",
    summary="查看 Hermes 飞书记忆授权",
)
async def list_livzon_feishu_authorizations(
    user_id: str,
    settings: Settings = Depends(get_settings),
    current_user: AdminUser = None,
) -> JSONResponse:
    if not settings.HERMES_INTERNAL_URL or not settings.HERMES_INTERNAL_TOKEN:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Hermes 内部接口未配置"
        )
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{settings.HERMES_INTERNAL_URL.rstrip('/')}/internal/feishu/grants",
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {settings.HERMES_INTERNAL_TOKEN}"},
        )
    if not response.is_success:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Hermes 授权查询失败")
    return success_response(data=response.json())


@feishu_config_router.delete(
    "/authorizations/{grant_id}",
    summary="撤销 Hermes 飞书记忆授权",
)
async def revoke_livzon_feishu_authorization(
    grant_id: str,
    user_id: str,
    settings: Settings = Depends(get_settings),
    current_user: AdminUser = None,
) -> JSONResponse:
    if not settings.HERMES_INTERNAL_URL or not settings.HERMES_INTERNAL_TOKEN:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Hermes 内部接口未配置"
        )
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.delete(
            f"{settings.HERMES_INTERNAL_URL.rstrip('/')}/internal/feishu/grants/{grant_id}",
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {settings.HERMES_INTERNAL_TOKEN}"},
        )
    if response.status_code == 404:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "授权不存在或已撤销")
    if not response.is_success:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Hermes 授权撤销失败")
    return success_response(data=response.json())


@feishu_config_router.post(
    "/test",
    summary="诊断 Livzon 助手飞书权限",
    response_model=FeishuDiagnosticApiResponse,
)
async def test_livzon_feishu_config(
    payload: FeishuConfigUpsert | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    """通过实际飞书 API 调用诊断 Livzon 助手通讯录权限。"""
    from app.platform.identity.service import diagnose_livzon_feishu_config

    data = await diagnose_livzon_feishu_config(db, payload)
    return success_response(data=data.model_dump(mode="json"))


@sync_router.post("/departments", summary="触发飞书组织架构同步（异步）")
async def trigger_sync_departments(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """POST 触发一次飞书组织架构同步，后台执行不阻塞，立即返回。"""
    from app.core.secrets import decrypt_secret
    from app.platform.identity.repository import FeishuConfigRepository

    config = await FeishuConfigRepository().get_active(db)
    root_id = (
        config.sync_root_department_id
        if config and config.sync_root_department_id
        else settings.FEISHU_SYNC_ROOT_DEPT_ID
    )
    if not root_id:
        return JSONResponse(status_code=400, content={"message": "未配置同步根部门 ID"})

    from app.platform.integrations.feishu.sync import sync_departments

    app_id = config.app_id if config else None
    app_secret = decrypt_secret(config.encrypted_app_secret) if config else None
    asyncio.create_task(sync_departments(root_id, app_id=app_id, app_secret=app_secret))
    logger.info("Department sync triggered for root=%s", root_id)
    return success_response(
        data={"message": "组织架构同步已触发", "root_dept_id": root_id},
    )


@sync_router.post("/members", summary="触发飞书成员同步（异步）")
async def trigger_sync_members(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """POST 触发一次飞书成员同步，后台执行不阻塞，立即返回。"""
    from app.core.secrets import decrypt_secret
    from app.platform.identity.repository import FeishuConfigRepository

    config = await FeishuConfigRepository().get_active(db)
    target_id = (
        config.sync_member_department_id
        if config and config.sync_member_department_id
        else settings.FEISHU_SYNC_MEMBER_DEPT_ID
    )
    if not target_id:
        return JSONResponse(
            status_code=400,
            content={"message": "未配置成员同步部门 ID"},
        )

    from app.platform.integrations.feishu.sync import sync_members

    app_id = config.app_id if config else None
    app_secret = decrypt_secret(config.encrypted_app_secret) if config else None
    asyncio.create_task(sync_members(target_id, app_id=app_id, app_secret=app_secret))
    logger.info("Member sync triggered for target=%s", target_id)
    return success_response(
        data={"message": "成员同步已触发", "target_dept_id": target_id},
    )


@sync_router.post("/all", summary="同步 Livzon 助手飞书通讯录")
async def trigger_sync_all(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> JSONResponse:
    """同步 Livzon 助手使用的部门、用户、手机号、邮箱和部门关系。"""
    from app.platform.identity.service import run_livzon_feishu_sync_all

    data = await run_livzon_feishu_sync_all(db, actor_id=current_user.id)
    from app.platform.audit.models import AuditLog

    db.add(
        AuditLog(
            user_id=current_user.id,
            method="POST",
            path="/api/v1/identity/sync/all",
            status_code=200,
            resource_type="external_identity_binding",
            action="sync_livzon_feishu_directory",
            extra={
                "status": data.get("status"),
                "created_bindings": data.get("bindings", {}).get("created", 0),
                "conflict_count": len(
                    data.get("bindings", {}).get("conflicts", [])
                ),
            },
        )
    )
    return success_response(data=data)
