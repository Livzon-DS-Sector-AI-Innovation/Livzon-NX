"""Authentication service — handles OAuth callback, JWT generation, user upsert."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.platform.identity.models import (
    FeishuConfig,
    FeishuUserToken,
    User,
)
from app.platform.identity.repository import (
    ExternalIdentityBindingRepository,
    FeishuConfigRepository,
    FeishuUserTokenRepository,
    UserRepository,
)
from app.platform.identity.schemas import (
    ExternalIdentityConflictOut,
    FeishuConfigResponse,
    FeishuConfigUpsert,
    FeishuDiagnosticResult,
    FeishuDiagnosticStep,
    FeishuGatewayRestartResult,
)
from app.platform.integrations.feishu.oauth import FeishuOAuthClient

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass

JsonObject = dict[str, Any]

_repo = UserRepository()
_feishu_config_repo = FeishuConfigRepository()
_feishu_user_token_repo = FeishuUserTokenRepository()
_PASSWORD_ITERATIONS = 260_000
SYSTEM_ADMIN_USERNAME = "system_admin"
SYSTEM_ADMIN_NAME = "系统管理员"
DEFAULT_FEISHU_CONFIG_NAME = "Livzon 助手飞书设置"


def _secret_runtime_error(exc: RuntimeError) -> HTTPException:
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        (
            "Livzon 助手飞书密钥加解密失败："
            f"{exc}。请检查后端 ENCRYPTION_KEY 配置是否与保存配置时一致。"
        ),
    )


async def _push_livzon_credentials_to_hermes(
    *,
    app_id: str,
    app_secret: str,
    tenant_id: str,
    gateway_enabled: bool,
    version: int,
) -> bool:
    """Rotate Hermes credentials or raise a stable API error."""
    settings = get_settings()
    base_url = settings.HERMES_INTERNAL_URL.rstrip("/")
    token = settings.HERMES_INTERNAL_TOKEN
    if not base_url or not token:
        logger.warning("Hermes internal Feishu credential delivery is not configured")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Hermes 内部接口未配置，飞书接入配置未保存",
        )
    signed = (
        f"{app_id}\n{tenant_id}\n{str(gateway_enabled).lower()}\n"
        f"{version}\n{app_secret}"
    ).encode()
    signature = hmac.new(token.encode(), signed, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.put(
                f"{base_url}/internal/feishu/config",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "app_id": app_id,
                    "app_secret": app_secret,
                    "tenant_id": tenant_id,
                    "gateway_enabled": gateway_enabled,
                    "version": version,
                    "signature": signature,
                },
            )
        if response.is_success:
            return True
        logger.error(
            "Hermes rejected Feishu credential version %s with status %s",
            version,
            response.status_code,
        )
        if response.status_code == status.HTTP_409_CONFLICT:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Hermes 拒绝了重复或过期的飞书配置版本，请刷新后重试",
            )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Hermes 未接受飞书接入配置，当前可用版本保持不变",
        )
    except httpx.HTTPError as exc:
        logger.error(
            "Hermes Feishu credential delivery failed for version %s: %s",
            version,
            type(exc).__name__,
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Hermes 暂时不可达，飞书接入配置未保存",
        ) from exc


async def restart_livzon_feishu_gateway() -> FeishuGatewayRestartResult:
    """Restart only the managed Feishu Gateway child and wait for readiness."""
    settings = get_settings()
    base_url = settings.HERMES_INTERNAL_URL.rstrip("/")
    token = settings.HERMES_INTERNAL_TOKEN
    if not base_url or not token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Hermes 内部接口未配置，无法重启飞书 Gateway",
        )
    try:
        async with httpx.AsyncClient(timeout=70) as client:
            response = await client.post(
                f"{base_url}/internal/feishu/gateway/restart",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "Hermes 飞书 Gateway 重启超时，请刷新运行状态并查看诊断信息",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Hermes 暂时不可达，未能发起飞书 Gateway 重启",
        ) from exc

    if response.status_code == status.HTTP_409_CONFLICT:
        detail = "飞书 Gateway 当前状态不允许重启"
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                detail = payload["detail"]
        except ValueError:
            pass
        raise HTTPException(status.HTTP_409_CONFLICT, detail)
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "当前运行的 Hermes 版本不支持管理面板重启，请先重新部署 Hermes 后再试",
        )
    if response.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Hermes 内部鉴权失败，请管理员核对后端与 Hermes 的内部服务 Token",
        )
    if response.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "Hermes 飞书 Gateway 未在限定时间内恢复连接，请查看运行状态和诊断信息",
        )
    if not response.is_success:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Hermes 拒绝了飞书 Gateway 重启请求",
        )
    try:
        return FeishuGatewayRestartResult.model_validate(response.json())
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Hermes 返回了无效的飞书 Gateway 重启结果",
        ) from exc


def hash_password(password: str) -> str:
    """Hash a local-account password using PBKDF2-SHA256."""
    salt = secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${_PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        ).hex()
    except (ValueError, TypeError):
        return False
    return compare_digest(expected, digest_hex)


def _split_identifiers(raw: str) -> set[str]:
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _matches_admin_whitelist(user: User, raw_identifiers: str) -> bool:
    identifiers = _split_identifiers(raw_identifiers)
    if not identifiers:
        return False
    candidates = {
        user.username,
        user.feishu_open_id,
        user.feishu_user_id,
        user.email,
        user.enterprise_email,
        user.mobile,
        user.employee_no,
    }
    return any(value and value.lower() in identifiers for value in candidates)


def _directory_department_name(profile: JsonObject) -> str | None:
    department_path = profile.get("department_path") or []
    positions = profile.get("positions") or []
    primary_position = next(
        (item for item in positions if item.get("is_major")),
        positions[0] if positions else {},
    )
    primary_department_id = str(primary_position.get("department_id") or "")
    if primary_department_id:
        for item in department_path:
            if str(item.get("department_id") or "") == primary_department_id:
                return str(item.get("department_name") or "").strip() or None
    for item in reversed(department_path):
        name = str(item.get("department_name") or "").strip()
        if name:
            return name
    return None


def _directory_position_name(profile: JsonObject) -> str | None:
    job_title = str(profile.get("job_title") or "").strip()
    if job_title:
        return job_title
    positions = profile.get("positions") or []
    primary_position = next(
        (item for item in positions if item.get("is_major")),
        positions[0] if positions else {},
    )
    return str(primary_position.get("position_name") or "").strip() or None


async def _get_oauth_directory_profile(
    oauth: FeishuOAuthClient,
    *,
    user_id: str | None,
    open_id: str,
) -> JsonObject:
    """Best-effort contact lookup for fields omitted by OAuth user_info."""
    from app.platform.integrations.feishu.contact import (
        get_department_detail,
        get_user_detail,
    )

    lookup_id = user_id or open_id
    lookup_type = "user_id" if user_id else "open_id"
    try:
        profile = (
            await get_user_detail(
                lookup_id,
                user_id_type=lookup_type,
                app_id=oauth.app_id,
                app_secret=oauth.app_secret,
            )
            or {}
        )
        if not profile.get("department_path"):
            department_path = []
            for department_id in profile.get("department_ids") or []:
                department = await get_department_detail(
                    department_id,
                    app_id=oauth.app_id,
                    app_secret=oauth.app_secret,
                )
                if department:
                    department_path.append(department)
            profile["department_path"] = department_path
        return profile
    except Exception:
        logger.warning(
            "Unable to enrich OAuth user from Feishu contacts: %s=%s",
            lookup_type,
            lookup_id,
            exc_info=True,
        )
        return {}


def _empty_feishu_config_response() -> FeishuConfigResponse:
    return FeishuConfigResponse(
        config_name=DEFAULT_FEISHU_CONFIG_NAME,
        app_id="",
        tenant_id="default",
        gateway_enabled=True,
        config_version=0,
        app_secret_configured=False,
        app_secret_masked="",
        is_active=True,
    )


def _feishu_config_to_response(config: FeishuConfig | None) -> FeishuConfigResponse:
    if config is None:
        return _empty_feishu_config_response()
    secret = ""
    if config.encrypted_app_secret:
        try:
            secret = decrypt_secret(config.encrypted_app_secret)
        except RuntimeError:
            secret = ""
    return FeishuConfigResponse(
        id=config.id,
        config_name=config.config_name,
        app_id=config.app_id,
        tenant_id=config.tenant_id,
        gateway_enabled=config.gateway_enabled,
        allowed_group_chat_ids=config.allowed_group_chat_ids or [],
        require_group_mention=config.require_group_mention,
        config_version=config.config_version,
        app_secret_configured=bool(config.encrypted_app_secret),
        app_secret_masked=mask_secret(secret),
        sync_root_department_id=config.sync_root_department_id,
        sync_member_department_id=config.sync_member_department_id,
        is_active=config.is_active,
        last_sync_status=config.last_sync_status,
        last_sync_message=config.last_sync_message,
        last_synced_at=config.last_synced_at,
        last_diagnostic_status=config.last_diagnostic_status,
        last_diagnostic_message=config.last_diagnostic_message,
        last_diagnostic_result=config.last_diagnostic_result,
        last_diagnosed_at=config.last_diagnosed_at,
        updated_at=config.updated_at,
        updated_by=config.updated_by,
    )


async def get_livzon_feishu_config_response(db: AsyncSession) -> FeishuConfigResponse:
    config = await _feishu_config_repo.get_latest(db)
    return _feishu_config_to_response(config)


async def save_livzon_feishu_config(
    db: AsyncSession, payload: FeishuConfigUpsert
) -> FeishuConfigResponse:
    existing = await _feishu_config_repo.get_latest(db)
    target_name = payload.config_name or DEFAULT_FEISHU_CONFIG_NAME
    if existing is None:
        existing = await _feishu_config_repo.get_by_name_including_deleted(
            db,
            target_name,
        )
    try:
        encrypted_secret = (
            encrypt_secret(payload.app_secret)
            if payload.app_secret
            else existing.encrypted_app_secret
            if existing
            else ""
        )
    except RuntimeError as exc:
        raise _secret_runtime_error(exc) from exc
    if not encrypted_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请输入 App Secret")

    if existing:
        existing.config_name = target_name
        existing.app_id = payload.app_id
        existing.tenant_id = payload.tenant_id
        existing.gateway_enabled = payload.gateway_enabled
        existing.allowed_group_chat_ids = payload.allowed_group_chat_ids
        existing.require_group_mention = payload.require_group_mention
        existing.config_version = (existing.config_version or 0) + 1
        existing.encrypted_app_secret = encrypted_secret
        existing.sync_root_department_id = payload.sync_root_department_id
        existing.sync_member_department_id = payload.sync_member_department_id
        existing.is_active = payload.is_active
        existing.is_deleted = False
        await db.flush()
        await db.refresh(existing)
        effective_secret = payload.app_secret
        if not effective_secret:
            try:
                effective_secret = decrypt_secret(existing.encrypted_app_secret)
            except RuntimeError as exc:
                raise _secret_runtime_error(exc) from exc
        response = _feishu_config_to_response(existing)
        await _push_livzon_credentials_to_hermes(
            app_id=existing.app_id,
            app_secret=effective_secret,
            tenant_id=existing.tenant_id,
            gateway_enabled=existing.gateway_enabled and existing.is_active,
            version=existing.config_version,
        )
        return response

    config = FeishuConfig(
        config_name=target_name,
        app_id=payload.app_id,
        tenant_id=payload.tenant_id,
        gateway_enabled=payload.gateway_enabled,
        allowed_group_chat_ids=payload.allowed_group_chat_ids,
        require_group_mention=payload.require_group_mention,
        config_version=1,
        encrypted_app_secret=encrypted_secret,
        sync_root_department_id=payload.sync_root_department_id,
        sync_member_department_id=payload.sync_member_department_id,
        is_active=payload.is_active,
    )
    await _feishu_config_repo.save(db, config)
    await db.refresh(config)
    response = _feishu_config_to_response(config)
    await _push_livzon_credentials_to_hermes(
        app_id=config.app_id,
        app_secret=payload.app_secret or "",
        tenant_id=config.tenant_id,
        gateway_enabled=config.gateway_enabled and config.is_active,
        version=config.config_version,
    )
    return response


async def _effective_feishu_credentials(
    db: AsyncSession,
    payload: FeishuConfigUpsert | None = None,
) -> tuple[str, str, str, str]:
    settings = get_settings()
    stored = await _feishu_config_repo.get_active(db)

    app_id = (
        (payload.app_id if payload else None)
        or (stored.app_id if stored else None)
        or settings.FEISHU_APP_ID
    )
    encrypted_secret = stored.encrypted_app_secret if stored else ""
    try:
        app_secret = (
            payload.app_secret
            if payload and payload.app_secret
            else decrypt_secret(encrypted_secret)
            if encrypted_secret
            else settings.FEISHU_APP_SECRET
        )
    except RuntimeError as exc:
        raise _secret_runtime_error(exc) from exc
    root_id = (
        (payload.sync_root_department_id if payload else None)
        or (stored.sync_root_department_id if stored else None)
        or settings.FEISHU_SYNC_ROOT_DEPT_ID
        or "0"
    )
    member_id = (
        (payload.sync_member_department_id if payload else None)
        or (stored.sync_member_department_id if stored else None)
        or settings.FEISHU_SYNC_MEMBER_DEPT_ID
        or root_id
    )
    if not app_id or not app_secret:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Livzon 助手飞书 App ID 或 App Secret 未配置",
        )
    return app_id, app_secret, root_id, member_id


def _environment_directory_credentials() -> tuple[str, str, str, str]:
    """Resolve the platform directory app strictly from root environment settings."""
    settings = get_settings()
    app_id = settings.FEISHU_APP_ID.strip()
    app_secret = settings.FEISHU_APP_SECRET.strip()
    root_id = settings.FEISHU_SYNC_ROOT_DEPT_ID.strip() or "0"
    member_id = settings.FEISHU_SYNC_MEMBER_DEPT_ID.strip() or root_id
    if not app_id or not app_secret:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "飞书登录与通讯录 App ID 或 App Secret 未配置",
        )
    return app_id, app_secret, root_id, member_id


def _diagnostic_status(steps: list[FeishuDiagnosticStep]) -> str:
    if any(step.status == "error" for step in steps):
        return "error"
    if any(step.status == "warning" for step in steps):
        return "warning"
    return "ok"


def _feishu_error_code(exc: Exception) -> int | None:
    matched = re.search(r"\bcode=(-?\d+)\b", str(exc))
    return int(matched.group(1)) if matched else None


def _contact_api_suggestion(exc: Exception, *, resource: str) -> str:
    error_text = str(exc).lower()
    if _feishu_error_code(exc) == 40004 or "no dept authority" in error_text:
        return (
            "Scope 已开通；飞书错误 40004 表示目标部门不在应用的通讯录权限范围内。"
            f"请将{resource}对应部门加入通讯录权限范围，或把同步部门配置为已授权部门。"
        )
    if resource == "部门列表":
        return (
            "请核对 contact:department.base:readonly、"
            "contact:department.organize:readonly 的发布状态和目标部门可见范围。"
        )
    return (
        "请核对 contact:user.base:readonly 的发布状态，并确认应用通讯录权限范围"
        "包含目标部门及其成员。"
    )


async def diagnose_livzon_feishu_config(
    db: AsyncSession,
    payload: FeishuConfigUpsert | None = None,
) -> FeishuDiagnosticResult:
    from app.platform.integrations.feishu.contact import (
        find_users_by_department,
        get_all_departments,
        get_contact_scope,
    )
    from app.platform.integrations.feishu.utils import get_tenant_access_token

    steps: list[FeishuDiagnosticStep] = []
    departments: list[JsonObject] = []
    users: list[JsonObject] = []
    scope: JsonObject = {}
    authorized_department_ids: list[str] = []
    stored = await _feishu_config_repo.get_active(db)

    try:
        app_id, app_secret, root_id, member_id = await _effective_feishu_credentials(
            db, payload
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_400_BAD_REQUEST:
            raise
        steps.append(
            FeishuDiagnosticStep(
                name="应用凭证",
                status="error",
                message="Livzon 助手飞书 App ID 或 App Secret 未配置",
                suggestion="请在系统设置的 Livzon 助手飞书设置中填写自建应用凭证。",
            )
        )
        return FeishuDiagnosticResult(
            status="error",
            message="Livzon 助手飞书配置不完整",
            steps=steps,
        )

    try:
        token = await get_tenant_access_token(
            app_id,
            app_secret,
            cache_key=f"livzon-assistant:{app_id}",
        )
        steps.append(
            FeishuDiagnosticStep(
                name="tenant_access_token",
                status="ok",
                message="已成功获取 tenant_access_token。",
            )
        )
    except Exception as exc:
        steps.append(
            FeishuDiagnosticStep(
                name="tenant_access_token",
                status="error",
                message=f"获取 tenant_access_token 失败：{exc}",
                suggestion=(
                    "请确认 App ID / App Secret 正确，且应用已发布或处于可调用状态。"
                ),
            )
        )
        result = FeishuDiagnosticResult(
            status="error",
            message="Livzon 助手飞书认证失败",
            steps=steps,
        )
        await _save_diagnostic_result(db, stored, result)
        return result

    try:
        scope = await get_contact_scope(
            app_id=app_id,
            app_secret=app_secret,
            tenant_access_token=token,
        )
        scope_department_count = len(scope.get("department_ids") or [])
        authorized_department_ids = [
            str(item) for item in scope.get("department_ids") or [] if str(item).strip()
        ]
        scope_user_count = len(scope.get("user_ids") or [])
        scope_group_count = len(scope.get("group_ids") or [])
        steps.append(
            FeishuDiagnosticStep(
                name="通讯录授权范围",
                status="ok"
                if scope_department_count or scope_user_count or scope_group_count
                else "warning",
                message=(
                    "当前应用通讯录授权范围："
                    f"部门 {scope_department_count} 个，"
                    f"用户 {scope_user_count} 名，"
                    f"用户组 {scope_group_count} 个。"
                ),
                suggestion=None
                if scope_department_count or scope_user_count or scope_group_count
                else (
                    "飞书开放平台的权限开通后，还需要在“通讯录权限范围”"
                    "中授权可访问的部门或成员。"
                ),
            )
        )
    except Exception as exc:
        steps.append(
            FeishuDiagnosticStep(
                name="通讯录授权范围",
                status="warning",
                message=f"读取通讯录授权范围失败：{exc}",
                suggestion=(
                    "请确认已开通 contact:scope:readonly，或在飞书开放平台检查"
                    "通讯录权限范围是否已发布生效。"
                ),
            )
        )

    diagnostic_root_id = root_id
    if authorized_department_ids and (
        root_id == "0" or root_id not in authorized_department_ids
    ):
        diagnostic_root_id = authorized_department_ids[0]
        steps.append(
            FeishuDiagnosticStep(
                name="诊断目标部门",
                status="warning",
                message=(
                    f"配置的同步根部门 {root_id} 不在当前通讯录权限范围内；"
                    "本次改用一个已授权部门进行连通性探测。"
                ),
                suggestion=(
                    "若需要从该根部门同步，请在飞书开放平台扩大通讯录权限范围；"
                    "否则请将同步根部门和成员同步部门改为已授权部门。"
                ),
                code=40004,
            )
        )

    try:
        departments = await get_all_departments(
            root_department_id=diagnostic_root_id,
            app_id=app_id,
            app_secret=app_secret,
            tenant_access_token=token,
        )
        steps.append(
            FeishuDiagnosticStep(
                name="部门列表",
                status="ok",
                message=(
                    f"读取到 {len(departments)} 个部门。"
                    if departments
                    else (
                        f"部门 API 调用成功；已授权部门 {diagnostic_root_id} "
                        "下没有可返回的子部门。"
                    )
                ),
                suggestion=None,
            )
        )
    except Exception as exc:
        steps.append(
            FeishuDiagnosticStep(
                name="部门列表",
                status="error",
                message=f"读取部门列表失败：{exc}",
                suggestion=_contact_api_suggestion(exc, resource="部门列表"),
                code=_feishu_error_code(exc),
            )
        )

    sample_department_ids = []
    departments_with_members = (
        dept.get("department_id", "")
        for dept in departments
        if dept.get("member_count")
    )
    for dept_id in [
        *(authorized_department_ids[:3]),
        diagnostic_root_id,
        member_id,
        *departments_with_members,
        *(dept.get("department_id", "") for dept in departments),
        root_id,
    ]:
        if dept_id and dept_id not in sample_department_ids:
            sample_department_ids.append(dept_id)

    sampled_department_id = ""
    if sample_department_ids:
        errors: list[Exception] = []
        tried_ids: list[str] = []
        successful_ids: list[str] = []
        for sample_department_id in sample_department_ids:
            tried_ids.append(sample_department_id)
            try:
                users = await find_users_by_department(
                    sample_department_id,
                    app_id=app_id,
                    app_secret=app_secret,
                    tenant_access_token=token,
                )
            except Exception as exc:
                errors.append(exc)
                continue
            successful_ids.append(sample_department_id)
            sampled_department_id = sample_department_id
            if users:
                break
        if successful_ids:
            steps.append(
                FeishuDiagnosticStep(
                    name="部门用户",
                    status="ok" if users else "warning",
                    message=(
                        f"部门 {sampled_department_id} 读取到 {len(users)} 名用户。"
                        if users
                        else (
                            "已尝试部门 "
                            f"{', '.join(successful_ids[:5])}，API 调用成功，"
                            "但未读取到用户。"
                        )
                    ),
                    suggestion=None
                    if users
                    else (
                        "请确认这些部门下存在直属成员；若成员在子部门，请配置成员同步部门"
                        "为有人的部门，或检查通讯录权限范围是否包含该部门成员，并开通 "
                        "contact:user.base:readonly。"
                    ),
                )
            )
        else:
            last_error = errors[-1]
            steps.append(
                FeishuDiagnosticStep(
                    name="部门用户",
                    status="error",
                    message=f"读取部门用户失败：{last_error}",
                    suggestion=_contact_api_suggestion(
                        last_error,
                        resource="部门用户",
                    ),
                    code=_feishu_error_code(last_error),
                )
            )
    else:
        steps.append(
            FeishuDiagnosticStep(
                name="部门用户",
                status="warning",
                message="没有可用于抽样的部门 ID。",
                suggestion="请配置成员同步部门 ID，或扩大通讯录权限范围后重试。",
            )
        )

    if users:
        has_department_ids = any(user.get("department_ids") for user in users)
        has_mobile = any(user.get("mobile") for user in users)
        has_email = any(user.get("email") for user in users)
        steps.extend(
            [
                FeishuDiagnosticStep(
                    name="用户部门关系",
                    status="ok" if has_department_ids else "warning",
                    message="已返回用户 department_ids 字段。"
                    if has_department_ids
                    else "用户可读取，但未返回 department_ids。",
                    suggestion=None
                    if has_department_ids
                    else "请开通 contact:user.department:readonly。",
                ),
                FeishuDiagnosticStep(
                    name="用户手机号",
                    status="ok" if has_mobile else "warning",
                    message="已返回至少一名用户手机号。"
                    if has_mobile
                    else "用户可读取，但未返回手机号。",
                    suggestion=None
                    if has_mobile
                    else (
                        "请开通 contact:user.phone:readonly，"
                        "并确认通讯录权限范围包含手机号字段。"
                    ),
                ),
                FeishuDiagnosticStep(
                    name="用户邮箱",
                    status="ok" if has_email else "warning",
                    message="已返回至少一名用户邮箱。"
                    if has_email
                    else "用户可读取，但未返回邮箱。",
                    suggestion=None
                    if has_email
                    else (
                        "请开通 contact:user.email:readonly，"
                        "并确认通讯录权限范围包含邮箱字段。"
                    ),
                ),
            ]
        )

    status_value = _diagnostic_status(steps)
    result = FeishuDiagnosticResult(
        status=status_value,
        message={
            "ok": "Livzon 助手飞书配置可用。",
            "warning": "Livzon 助手飞书配置可连接，但部分通讯录数据不可见。",
            "error": "Livzon 助手飞书配置存在错误。",
        }[status_value],
        steps=steps,
        department_count=len(departments),
        sample_user_count=len(users),
    )
    await _save_diagnostic_result(db, stored, result)
    return result


async def _save_diagnostic_result(
    db: AsyncSession,
    config: FeishuConfig | None,
    result: FeishuDiagnosticResult,
) -> None:
    if config is None:
        return
    config.last_diagnostic_status = result.status
    config.last_diagnostic_message = result.message
    config.last_diagnostic_result = json.dumps(result.model_dump(), ensure_ascii=False)
    config.last_diagnosed_at = datetime.now(UTC)
    await db.flush()


async def _run_feishu_directory_sync_all(
    db: AsyncSession,
    *,
    app_id: str,
    app_secret: str,
    root_id: str,
    member_id: str,
    user_id_type: str,
    status_config: FeishuConfig | None,
    actor_id: UUID | None = None,
) -> JsonObject:
    from app.platform.integrations.feishu.contact import get_contact_scope
    from app.platform.integrations.feishu.sync import (
        sync_departments,
        sync_members,
        sync_users_by_ids,
    )

    scope: JsonObject = {}
    scope_department_ids: list[str] = []
    scope_user_ids: list[str] = []
    try:
        scope = await get_contact_scope(
            user_id_type=user_id_type,
            app_id=app_id,
            app_secret=app_secret,
        )
        scope_department_ids = scope.get("department_ids") or []
        scope_user_ids = scope.get("user_ids") or []
    except Exception:
        logger.exception("Failed to read Livzon Feishu contact scope before sync")

    department_targets = [root_id]
    member_targets = [member_id]
    if root_id == "0" and scope_department_ids:
        department_targets = scope_department_ids
    if member_id == "0" and scope_department_ids:
        member_targets = scope_department_ids

    dept_results: list[JsonObject] = []
    dept_errors: list[str] = []
    for department_id in dict.fromkeys(department_targets):
        try:
            dept_results.append(
                await sync_departments(
                    department_id,
                    user_id_type=user_id_type,
                    app_id=app_id,
                    app_secret=app_secret,
                )
            )
        except Exception as exc:
            logger.exception("Livzon Feishu department sync failed: %s", department_id)
            dept_errors.append(f"{department_id}: {exc}")

    member_results: list[JsonObject] = []
    member_errors: list[str] = []
    for department_id in dict.fromkeys(member_targets):
        try:
            member_results.append(
                await sync_members(
                    department_id,
                    user_id_type=user_id_type,
                    app_id=app_id,
                    app_secret=app_secret,
                )
            )
        except Exception as exc:
            logger.exception("Livzon Feishu member sync failed: %s", department_id)
            member_errors.append(f"{department_id}: {exc}")

    direct_user_result = {"user_count": 0, "elapsed": 0}
    if scope_user_ids:
        direct_user_result = await sync_users_by_ids(
            scope_user_ids,
            user_id_type=user_id_type,
            app_id=app_id,
            app_secret=app_secret,
        )

    dept_count = sum(item.get("dept_count", 0) for item in dept_results)
    member_count = sum(item.get("user_count", 0) for item in member_results)
    direct_user_count = direct_user_result.get("user_count", 0)
    total_user_count = member_count + direct_user_count
    nested_member_errors = [
        str(error) for result in member_results for error in result.get("errors", [])
    ]
    all_errors = dept_errors + member_errors + nested_member_errors

    if not dept_results and not member_results and not direct_user_count:
        message = (
            "同步失败：当前 Livzon 助手飞书应用没有可同步的通讯录数据。"
            "请检查通讯录权限范围是否包含目标部门或用户。"
        )
        if all_errors:
            message = f"{message} 错误：{'; '.join(all_errors)}"
        if status_config is not None:
            status_config.last_sync_status = "error"
            status_config.last_sync_message = message
            status_config.last_synced_at = datetime.now(UTC)
            await db.flush()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message)

    sync_status = "warning" if all_errors else "ok"
    sync_message = (
        f"同步完成：部门 {dept_count} 个，"
        f"部门用户 {member_count} 名，直接授权用户 {direct_user_count} 名。"
    )
    if sync_status == "warning":
        sync_message = f"{sync_message} 部分部门同步失败：{'; '.join(all_errors)}"
    binding_result = await reconcile_livzon_identity_bindings(
        db,
        actor_id=actor_id,
    )
    conflict_count = len(binding_result["conflicts"])
    if conflict_count:
        sync_status = "warning"
        sync_message = (
            f"{sync_message} 发现 {conflict_count} 个身份绑定冲突，请处理后重试。"
        )
    if status_config is not None:
        status_config.last_sync_status = sync_status
        status_config.last_sync_message = sync_message
        status_config.last_synced_at = datetime.now(UTC)
        await db.flush()
    return {
        "scope": {
            "department_count": len(scope_department_ids),
            "user_count": len(scope_user_ids),
            "group_count": len(scope.get("group_ids") or []),
        },
        "department_targets": department_targets,
        "member_targets": member_targets,
        "departments": {
            "dept_count": dept_count,
            "results": dept_results,
            "errors": dept_errors,
        },
        "members": {
            "user_count": total_user_count,
            "department_user_count": member_count,
            "direct_user_count": direct_user_count,
            "results": member_results,
            "direct_user_result": direct_user_result,
            "errors": member_errors + nested_member_errors,
        },
        "bindings": binding_result,
        "status": sync_status,
        "message": sync_message,
    }


async def run_livzon_feishu_sync_all(
    db: AsyncSession,
    *,
    actor_id: UUID | None = None,
) -> JsonObject:
    """Sync the Livzon integration using its persisted configuration."""
    config = await _feishu_config_repo.get_active(db)
    app_id, app_secret, root_id, member_id = await _effective_feishu_credentials(db)
    return await _run_feishu_directory_sync_all(
        db,
        app_id=app_id,
        app_secret=app_secret,
        root_id=root_id,
        member_id=member_id,
        user_id_type="user_id",
        status_config=config,
        actor_id=actor_id,
    )


async def run_environment_feishu_user_sync(
    db: AsyncSession,
    *,
    actor_id: UUID | None = None,
) -> JsonObject:
    """Sync user management strictly with root environment credentials."""
    app_id, app_secret, root_id, member_id = _environment_directory_credentials()
    return await _run_feishu_directory_sync_all(
        db,
        app_id=app_id,
        app_secret=app_secret,
        root_id=root_id,
        member_id=member_id,
        user_id_type="open_id",
        status_config=None,
        actor_id=actor_id,
    )


async def list_livzon_identity_conflicts(
    db: AsyncSession,
) -> list[ExternalIdentityConflictOut]:
    config = await _feishu_config_repo.get_active(db)
    if config is None:
        return []
    users = list(
        (
            await db.execute(
                select(User).where(
                    User.is_deleted.is_(False),
                    User.tenant_key == config.tenant_id,
                    or_(
                        User.feishu_user_id.is_not(None),
                        User.feishu_open_id.is_not(None),
                        User.feishu_union_id.is_not(None),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    bindings = await ExternalIdentityBindingRepository().list_for_app(
        db,
        tenant_id=config.tenant_id,
        app_fingerprint=config.app_id,
    )
    conflicts: list[ExternalIdentityConflictOut] = []
    for user in users:
        identifiers = {
            value
            for value in (
                user.feishu_user_id,
                user.feishu_open_id,
                user.feishu_union_id,
            )
            if value
        }
        externally_matched = next(
            (
                binding
                for binding in bindings
                if identifiers
                & {
                    value
                    for value in (
                        binding.external_user_id,
                        binding.external_open_id,
                        binding.external_union_id,
                    )
                    if value
                }
            ),
            None,
        )
        local_binding = next(
            (binding for binding in bindings if binding.local_user_id == user.id),
            None,
        )
        if externally_matched and externally_matched.local_user_id != user.id:
            conflicts.append(
                ExternalIdentityConflictOut(
                    local_user_id=user.id,
                    local_user_name=user.name,
                    department=user.department,
                    external_identifier=sorted(identifiers)[0],
                    conflict_type="external_owned_by_other",
                    conflicting_binding_id=externally_matched.id,
                )
            )
        elif local_binding and not externally_matched:
            conflicts.append(
                ExternalIdentityConflictOut(
                    local_user_id=user.id,
                    local_user_name=user.name,
                    department=user.department,
                    external_identifier=sorted(identifiers)[0],
                    conflict_type="local_binding_mismatch",
                    conflicting_binding_id=local_binding.id,
                )
            )
    return conflicts


async def reconcile_livzon_identity_bindings(
    db: AsyncSession,
    *,
    actor_id: UUID | None,
) -> JsonObject:
    config = await _feishu_config_repo.get_active(db)
    if config is None:
        return {"created": 0, "existing": 0, "conflicts": []}
    users = list(
        (
            await db.execute(
                select(User).where(
                    User.is_deleted.is_(False),
                    User.status == "active",
                    User.tenant_key == config.tenant_id,
                    or_(
                        User.feishu_user_id.is_not(None),
                        User.feishu_open_id.is_not(None),
                        User.feishu_union_id.is_not(None),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    repo = ExternalIdentityBindingRepository()
    existing_bindings = await repo.list_for_app(
        db,
        tenant_id=config.tenant_id,
        app_fingerprint=config.app_id,
    )
    created = 0
    existing = 0
    for user in users:
        identifiers = {
            value
            for value in (
                user.feishu_user_id,
                user.feishu_open_id,
                user.feishu_union_id,
            )
            if value
        }
        matched = any(
            binding.local_user_id == user.id
            or bool(
                identifiers
                & {
                    value
                    for value in (
                        binding.external_user_id,
                        binding.external_open_id,
                        binding.external_union_id,
                    )
                    if value
                }
            )
            for binding in existing_bindings
        )
        if matched:
            existing += 1
            continue
        binding = await repo.create(
            db,
            tenant_id=config.tenant_id,
            platform="feishu",
            app_fingerprint=config.app_id,
            external_user_id=user.feishu_user_id,
            external_open_id=user.feishu_open_id,
            external_union_id=user.feishu_union_id,
            local_user_id=user.id,
            source="directory_sync",
            actor_id=actor_id or user.id,
        )
        existing_bindings.append(binding)
        created += 1
    conflicts = await list_livzon_identity_conflicts(db)
    return {
        "created": created,
        "existing": existing,
        "conflicts": [item.model_dump(mode="json") for item in conflicts],
    }


async def _active_livzon_feishu_credentials(db: AsyncSession) -> tuple[str, str]:
    config = await _feishu_config_repo.get_active(db)
    if config is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Livzon 助手飞书 App ID 或 App Secret 未配置",
        )
    if not config.app_id or not config.encrypted_app_secret:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Livzon 助手飞书 App ID 或 App Secret 未配置",
        )
    try:
        app_secret = decrypt_secret(config.encrypted_app_secret)
    except RuntimeError as exc:
        raise _secret_runtime_error(exc) from exc
    if not app_secret:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Livzon 助手飞书 App Secret 未配置",
        )
    return config.app_id, app_secret


_livzon_bot_open_id_cache: dict[str, str] = {}


def _token_value(token_data: JsonObject, *keys: str) -> str | None:
    for key in keys:
        value = token_data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _token_seconds(token_data: JsonObject, *keys: str) -> int | None:
    for key in keys:
        value = token_data.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str | int | float):
            continue
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            return seconds
    return None


def _expires_at(seconds: int | None, now: datetime) -> datetime | None:
    if seconds is None:
        return None
    return now + timedelta(seconds=seconds)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _save_feishu_user_token(
    db: AsyncSession,
    *,
    user: User,
    token_data: JsonObject,
    user_info: JsonObject | None,
    app_id: str,
    last_refreshed_at: datetime | None = None,
) -> FeishuUserToken:
    user_access_token = _token_value(token_data, "access_token", "user_access_token")
    if not user_access_token:
        raise ValueError("Feishu token response missing user_access_token")
    refresh_token = _token_value(token_data, "refresh_token")
    now = datetime.now(UTC)
    access_expires_at = _expires_at(
        _token_seconds(token_data, "expires_in", "expire", "expires"),
        now,
    )
    refresh_expires_at = _expires_at(
        _token_seconds(
            token_data,
            "refresh_expires_in",
            "refresh_token_expires_in",
            "refresh_token_expire",
        ),
        now,
    )
    info = user_info or {}
    token = await _feishu_user_token_repo.get_by_user_and_app(
        db,
        local_user_id=user.id,
        app_id=app_id,
    )
    if token is None:
        token = FeishuUserToken(
            local_user_id=user.id,
            app_id=app_id,
            encrypted_user_access_token=encrypt_secret(user_access_token),
            encrypted_refresh_token=encrypt_secret(refresh_token)
            if refresh_token
            else None,
        )
        await _feishu_user_token_repo.save(db, token)
    else:
        token.encrypted_user_access_token = encrypt_secret(user_access_token)
        if refresh_token:
            token.encrypted_refresh_token = encrypt_secret(refresh_token)

    token.feishu_open_id = (
        _token_value(info, "open_id") or user.feishu_open_id or token.feishu_open_id
    )
    token.feishu_user_id = (
        _token_value(info, "user_id") or user.feishu_user_id or token.feishu_user_id
    )
    token.feishu_union_id = (
        _token_value(info, "union_id") or user.feishu_union_id or token.feishu_union_id
    )
    token.tenant_key = (
        _token_value(info, "tenant_key") or user.tenant_key or token.tenant_key
    )
    token.token_type = _token_value(token_data, "token_type") or token.token_type
    token.scope = _token_value(token_data, "scope") or token.scope
    token.access_token_expires_at = access_expires_at or token.access_token_expires_at
    token.refresh_token_expires_at = (
        refresh_expires_at or token.refresh_token_expires_at
    )
    token.last_refreshed_at = last_refreshed_at or token.last_refreshed_at
    token.last_error = None
    token.status = "active"
    await db.flush()
    return token


async def handle_oauth_callback(
    db: AsyncSession,
    code: str,
) -> tuple[User, str]:
    """Complete the OAuth flow: exchange code → get user info → upsert → JWT.

    Returns (user, jwt_token).
    """
    oauth = FeishuOAuthClient.from_settings()

    # 1. Exchange authorization code for tokens (v2 endpoint)
    token_data = await oauth.exchange_code(code)
    user_access_token = _token_value(token_data, "access_token", "user_access_token")
    if not user_access_token:
        raise ValueError("Feishu token response missing user_access_token")

    # 2. Fetch user profile from Feishu (v1 user_info endpoint)
    #    Response fields: name, en_name, avatar_url, avatar_thumb,
    #    avatar_middle, avatar_big, open_id, union_id, email,
    #    enterprise_email, user_id, mobile, tenant_key
    info = await oauth.get_user_info(user_access_token)

    open_id = info.get("open_id", "")
    user_id = info.get("user_id") or None  # Convert empty to None
    union_id = info.get("union_id") or None  # Convert empty to None
    name = info.get("name", "")
    en_name = info.get("en_name")
    avatar_url = info.get("avatar_url") or info.get("avatar_middle")
    avatar_thumb = info.get("avatar_thumb")
    avatar_middle = info.get("avatar_middle")
    avatar_big = info.get("avatar_big")
    email = info.get("email") or info.get("enterprise_email")
    enterprise_email = info.get("enterprise_email")
    mobile = info.get("mobile")
    tenant_key = info.get("tenant_key")

    if not open_id:
        raise ValueError("Feishu user info missing open_id")

    directory_profile = await _get_oauth_directory_profile(
        oauth,
        user_id=user_id,
        open_id=open_id,
    )
    name = directory_profile.get("name") or name
    en_name = directory_profile.get("en_name") or en_name
    email = directory_profile.get("email") or email
    mobile = directory_profile.get("mobile") or mobile
    employee_no = directory_profile.get("employee_no") or None
    department = _directory_department_name(directory_profile)
    position = _directory_position_name(directory_profile)
    department_ids = directory_profile.get("department_ids") or []
    feishu_department_ids = json.dumps(department_ids) if department_ids else None

    # 3. Upsert user in local DB
    user = await _repo.get_by_feishu_open_id(db, open_id)
    if user is None:
        # Also try matching by feishu_user_id in case user was synced earlier
        user = await _repo.get_by_feishu_user_id(db, user_id) if user_id else None

    if user is None:
        user = await _repo.create(
            db,
            name=name,
            feishu_user_id=user_id,
            feishu_open_id=open_id,
            feishu_union_id=union_id,
            en_name=en_name,
            email=email,
            enterprise_email=enterprise_email,
            mobile=mobile,
            employee_no=employee_no,
            department=department,
            position=position,
            feishu_department_ids=feishu_department_ids,
            avatar_url=avatar_url,
            avatar_thumb=avatar_thumb,
            avatar_middle=avatar_middle,
            avatar_big=avatar_big,
            tenant_key=tenant_key,
            role="admin"
            if _matches_admin_whitelist(
                User(
                    name=name,
                    feishu_user_id=user_id,
                    feishu_open_id=open_id,
                    email=email,
                    enterprise_email=enterprise_email,
                    mobile=mobile,
                ),
                get_settings().SSO_ADMIN_IDENTIFIERS,
            )
            else "user",
            status="active",
            auth_source="feishu",
        )
        logger.info("Created new user: %s (open_id=%s)", name, open_id)
    else:
        # Update profile info on each login
        user.name = name or user.name
        user.feishu_user_id = user_id or user.feishu_user_id
        user.feishu_union_id = union_id or user.feishu_union_id
        user.en_name = en_name or user.en_name
        user.email = email or user.email
        user.enterprise_email = enterprise_email or user.enterprise_email
        user.mobile = mobile or user.mobile
        user.employee_no = employee_no or user.employee_no
        user.department = department or user.department
        user.position = position or user.position
        user.feishu_department_ids = feishu_department_ids or user.feishu_department_ids
        user.avatar_url = avatar_url or user.avatar_url
        user.avatar_thumb = avatar_thumb or user.avatar_thumb
        user.avatar_middle = avatar_middle or user.avatar_middle
        user.avatar_big = avatar_big or user.avatar_big
        user.tenant_key = tenant_key or user.tenant_key
        user.auth_source = user.auth_source or "feishu"
        user.role = (
            "admin"
            if _matches_admin_whitelist(
                user,
                get_settings().SSO_ADMIN_IDENTIFIERS,
            )
            else "user"
        )
        logger.info("Updated user: %s (open_id=%s)", user.name, open_id)

    if user.status == "disabled":
        raise PermissionError("User account is disabled")
    await _save_feishu_user_token(
        db,
        user=user,
        token_data=token_data,
        user_info=info,
        app_id=oauth.app_id,
    )
    user.last_login_at = datetime.now(UTC)
    await db.commit()

    # 4. Generate JWT
    token = generate_jwt(user)
    return user, token


async def get_valid_feishu_user_access_token(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    app_id: str | None = None,
    min_ttl_seconds: int = 300,
) -> str:
    """Return a valid Feishu user_access_token, refreshing it when needed."""
    settings = get_settings()
    target_app_id = app_id or settings.FEISHU_APP_ID
    if not target_app_id:
        raise ValueError("Feishu App ID is not configured")

    user = await _repo.get_by_id(db, user_id)
    if user is None or user.status == "disabled":
        raise PermissionError("User is not available")
    token = await _feishu_user_token_repo.get_by_user_and_app(
        db,
        local_user_id=user.id,
        app_id=target_app_id,
    )
    if token is None or token.status == "revoked":
        raise ValueError("Feishu user token is not available")

    now = datetime.now(UTC)
    expires_at = _as_utc(token.access_token_expires_at)
    if expires_at and expires_at > now + timedelta(seconds=min_ttl_seconds):
        return decrypt_secret(token.encrypted_user_access_token)

    if not token.encrypted_refresh_token:
        raise ValueError("Feishu refresh token is not available")
    refresh_expires_at = _as_utc(token.refresh_token_expires_at)
    if refresh_expires_at and refresh_expires_at <= now:
        token.status = "revoked"
        token.last_error = "Feishu refresh token expired"
        await db.flush()
        raise ValueError("Feishu refresh token expired")

    oauth = FeishuOAuthClient.from_settings()
    refresh_token = decrypt_secret(token.encrypted_refresh_token)
    try:
        token_data = await oauth.refresh_access_token(refresh_token)
        updated = await _save_feishu_user_token(
            db,
            user=user,
            token_data=token_data,
            user_info=None,
            app_id=target_app_id,
            last_refreshed_at=now,
        )
    except Exception as exc:
        token.status = "error"
        token.last_error = str(exc)[:1000]
        await db.flush()
        raise
    return decrypt_secret(updated.encrypted_user_access_token)


def generate_jwt(user: User) -> str:
    """Generate a JWT token for the given user."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "open_id": user.feishu_open_id,
        "name": user.name,
        "role": user.role,
        "auth_source": user.auth_source,
        "iat": now,
        "exp": now + timedelta(seconds=settings.JWT_EXPIRE_SECONDS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def authenticate_local_user(
    db: AsyncSession, *, username: str, password: str
) -> tuple[User, str]:
    user = await _repo.get_by_login_identifier(db, username)
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if user.status == "disabled":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已禁用")
    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user, generate_jwt(user)


async def bootstrap_local_users() -> None:
    settings = get_settings()
    entries = [
        (
            settings.BOOTSTRAP_ADMIN_USERNAME,
            settings.BOOTSTRAP_ADMIN_PASSWORD,
            settings.BOOTSTRAP_ADMIN_NAME,
            settings.BOOTSTRAP_ADMIN_EMAIL,
            "admin",
        ),
        (
            settings.BOOTSTRAP_USER_USERNAME,
            settings.BOOTSTRAP_USER_PASSWORD,
            settings.BOOTSTRAP_USER_NAME,
            settings.BOOTSTRAP_USER_EMAIL,
            "user",
        ),
    ]

    async with async_session_factory() as session:
        for username, password, name, email, role in entries:
            if not username or not password:
                continue
            existing = await _repo.get_by_username(session, username)
            if existing is None:
                await _repo.create(
                    session,
                    username=username,
                    password_hash=hash_password(password),
                    name=name or username,
                    email=email or None,
                    role=role,
                    status="active",
                    auth_source="local",
                )
                logger.info("Bootstrapped %s local user: %s", role, username)
                continue

            existing.password_hash = hash_password(password)
            existing.name = name or existing.name
            existing.email = email or existing.email
            existing.role = role
            existing.status = "active"
            existing.auth_source = existing.auth_source or "local"

        await get_or_create_system_admin(session)
        await session.commit()


async def get_or_create_system_admin(db: AsyncSession) -> User:
    """Return the platform default administrator used when login is disabled."""
    user = await _repo.get_by_username_including_deleted(db, SYSTEM_ADMIN_USERNAME)
    if user is None:
        user = await _repo.create(
            db,
            username=SYSTEM_ADMIN_USERNAME,
            name=SYSTEM_ADMIN_NAME,
            role="admin",
            status="active",
            auth_source="local",
        )
        logger.info("Created default platform administrator: %s", SYSTEM_ADMIN_USERNAME)
        return user

    changed = False
    if user.name != SYSTEM_ADMIN_NAME:
        user.name = SYSTEM_ADMIN_NAME
        changed = True
    if user.role != "admin":
        user.role = "admin"
        changed = True
    if user.status != "active":
        user.status = "active"
        changed = True
    if user.auth_source != "local":
        user.auth_source = "local"
        changed = True
    if user.is_deleted:
        user.is_deleted = False
        changed = True

    if changed:
        await db.flush()
    return user


def sanitize_oauth_next_path(next_path: str | None) -> str:
    """Return a safe internal redirect target for OAuth completion."""
    if not next_path:
        return "/production"
    candidate = next_path.strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/production"
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return "/production"
    if candidate.startswith("/api/") or candidate.startswith("/auth/"):
        return "/production"
    return candidate


def generate_state_token(next_path: str | None = None) -> str:
    """Generate a short-lived state token for CSRF protection."""
    settings = get_settings()
    nonce = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    payload = {
        "nonce": nonce,
        "next": sanitize_oauth_next_path(next_path),
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def validate_state_token(
    state: str,
    expected_state: str | None = None,
) -> JsonObject | None:
    """Validate an OAuth state token and return its payload if valid."""
    settings = get_settings()
    if not expected_state or not hmac.compare_digest(state, expected_state):
        return None
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
        if not isinstance(payload, dict):
            return None
        return payload
    except jwt.InvalidTokenError:
        return None
