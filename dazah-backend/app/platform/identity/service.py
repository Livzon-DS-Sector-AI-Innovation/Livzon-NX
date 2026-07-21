"""Authentication service — handles OAuth callback, JWT generation, user upsert."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.platform.audit.models import AuditLog
from app.platform.identity.models import (
    FeishuCardAction,
    FeishuConfig,
    FeishuUserToken,
    User,
)
from app.platform.identity.repository import (
    FeishuCardActionRepository,
    FeishuConfigRepository,
    FeishuUserTokenRepository,
    UserRepository,
)
from app.platform.identity.schemas import (
    FeishuConfigResponse,
    FeishuConfigUpsert,
    FeishuDiagnosticResult,
    FeishuDiagnosticStep,
)
from app.platform.integrations.feishu.im import build_callback_status_card_content
from app.platform.integrations.feishu.oauth import FeishuOAuthClient

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.modules.agent.models import AgentConfirmation

JsonObject = dict[str, Any]

_repo = UserRepository()
_feishu_config_repo = FeishuConfigRepository()
_feishu_card_action_repo = FeishuCardActionRepository()
_feishu_user_token_repo = FeishuUserTokenRepository()
_PASSWORD_ITERATIONS = 260_000
SYSTEM_ADMIN_USERNAME = "system_admin"
SYSTEM_ADMIN_NAME = "系统管理员"
DEFAULT_FEISHU_CONFIG_NAME = "Livzon 助手飞书设置"
ALLOWED_CARD_ACTIONS = {
    "start_processing": "开始处理",
    "mark_done": "标记完成",
    "reject": "驳回",
    "acknowledge": "已知悉",
    "agent_confirmation_execute": "确认执行",
    "agent_confirmation_cancel": "取消",
}


def _secret_runtime_error(exc: RuntimeError) -> HTTPException:
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        (
            "Livzon 助手飞书密钥加解密失败："
            f"{exc}。请检查后端 ENCRYPTION_KEY 配置是否与保存配置时一致。"
        ),
    )


def hash_password(password: str) -> str:
    """Hash a local-account password using PBKDF2-SHA256."""
    salt = secrets.token_bytes(16)
    digest = pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PASSWORD_ITERATIONS
    )
    return (
        f"pbkdf2_sha256${_PASSWORD_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


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
        profile = await get_user_detail(
            lookup_id,
            user_id_type=lookup_type,
            app_id=oauth.app_id,
            app_secret=oauth.app_secret,
        ) or {}
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
        app_secret_configured=False,
        app_secret_masked="",
        card_callback_verification_token_configured=False,
        card_callback_verification_token_masked="",
        card_callback_encrypt_key_configured=False,
        card_callback_encrypt_key_masked="",
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
    encrypt_key = ""
    if config.encrypted_card_callback_encrypt_key:
        try:
            encrypt_key = decrypt_secret(config.encrypted_card_callback_encrypt_key)
        except RuntimeError:
            encrypt_key = ""
    return FeishuConfigResponse(
        id=config.id,
        config_name=config.config_name,
        app_id=config.app_id,
        app_secret_configured=bool(config.encrypted_app_secret),
        app_secret_masked=mask_secret(secret),
        card_callback_verification_token_configured=bool(
            config.card_callback_verification_token
        ),
        card_callback_verification_token_masked=mask_secret(
            config.card_callback_verification_token or ""
        ),
        card_callback_encrypt_key_configured=bool(
            config.encrypted_card_callback_encrypt_key
        ),
        card_callback_encrypt_key_masked=mask_secret(encrypt_key),
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
        encrypted_callback_key = (
            encrypt_secret(payload.card_callback_encrypt_key)
            if payload.card_callback_encrypt_key
            else existing.encrypted_card_callback_encrypt_key
            if existing
            else None
        )
    except RuntimeError as exc:
        raise _secret_runtime_error(exc) from exc
    callback_token = (
        payload.card_callback_verification_token
        if payload.card_callback_verification_token is not None
        else existing.card_callback_verification_token
        if existing
        else None
    )
    if not encrypted_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请输入 App Secret")

    if existing:
        existing.config_name = target_name
        existing.app_id = payload.app_id
        existing.encrypted_app_secret = encrypted_secret
        existing.card_callback_verification_token = callback_token
        existing.encrypted_card_callback_encrypt_key = encrypted_callback_key
        existing.sync_root_department_id = payload.sync_root_department_id
        existing.sync_member_department_id = payload.sync_member_department_id
        existing.is_active = payload.is_active
        existing.is_deleted = False
        await db.flush()
        return _feishu_config_to_response(existing)

    config = FeishuConfig(
        config_name=target_name,
        app_id=payload.app_id,
        encrypted_app_secret=encrypted_secret,
        card_callback_verification_token=callback_token,
        encrypted_card_callback_encrypt_key=encrypted_callback_key,
        sync_root_department_id=payload.sync_root_department_id,
        sync_member_department_id=payload.sync_member_department_id,
        is_active=payload.is_active,
    )
    await _feishu_config_repo.save(db, config)
    return _feishu_config_to_response(config)


async def _effective_feishu_credentials(
    db: AsyncSession,
    payload: FeishuConfigUpsert | None = None,
) -> tuple[str, str, str, str]:
    settings = get_settings()
    stored = await _feishu_config_repo.get_active(db)

    app_id = (payload.app_id if payload else None) or (
        stored.app_id if stored else None
    ) or settings.FEISHU_APP_ID
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


def _diagnostic_status(steps: list[FeishuDiagnosticStep]) -> str:
    if any(step.status == "error" for step in steps):
        return "error"
    if any(step.status == "warning" for step in steps):
        return "warning"
    return "ok"


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

    try:
        departments = await get_all_departments(
            root_department_id=root_id,
            app_id=app_id,
            app_secret=app_secret,
            tenant_access_token=token,
        )
        steps.append(
            FeishuDiagnosticStep(
                name="部门列表",
                status="ok" if departments else "warning",
                message=(
                    f"读取到 {len(departments)} 个部门。"
                    if departments
                    else "部门 API 调用成功，但未读取到部门数据。"
                ),
                suggestion=None
                if departments
                else (
                    "请检查通讯录权限范围是否包含同步根部门；飞书要求使用 "
                    "fetch_child=true 获取子部门，并开通 "
                    "contact:department.base:readonly / "
                    "contact:department.organize:readonly。"
                ),
            )
        )
    except Exception as exc:
        steps.append(
            FeishuDiagnosticStep(
                name="部门列表",
                status="error",
                message=f"读取部门列表失败：{exc}",
                suggestion=(
                    "请开通 contact:department.base:readonly、"
                    "contact:department.organize:readonly，并确认通讯录权限范围。"
                ),
            )
        )

    sample_department_ids = []
    departments_with_members = (
        dept.get("department_id", "")
        for dept in departments
        if dept.get("member_count")
    )
    for dept_id in [
        member_id,
        *departments_with_members,
        *(dept.get("department_id", "") for dept in departments),
        *((scope.get("department_ids") or [])[:3]),
        root_id,
    ]:
        if dept_id and dept_id not in sample_department_ids:
            sample_department_ids.append(dept_id)

    sampled_department_id = ""
    if sample_department_ids:
        last_error: Exception | None = None
        tried_ids: list[str] = []
        try:
            for sample_department_id in sample_department_ids:
                tried_ids.append(sample_department_id)
                users = await find_users_by_department(
                    sample_department_id,
                    app_id=app_id,
                    app_secret=app_secret,
                    tenant_access_token=token,
                )
                if users:
                    sampled_department_id = sample_department_id
                    break
            if not sampled_department_id and tried_ids:
                sampled_department_id = tried_ids[0]
            steps.append(
                FeishuDiagnosticStep(
                    name="部门用户",
                    status="ok" if users else "warning",
                    message=(
                        f"部门 {sampled_department_id} 读取到 {len(users)} 名用户。"
                        if users
                        else (
                            "已尝试部门 "
                            f"{', '.join(tried_ids[:5])}，API 调用成功，"
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
        except Exception as exc:
            last_error = exc
            steps.append(
                FeishuDiagnosticStep(
                    name="部门用户",
                    status="error" if last_error else "warning",
                    message=f"读取部门用户失败：{last_error or exc}",
                    suggestion=(
                        "请开通 contact:user.base:readonly，"
                        "并确认应用通讯录权限范围包含目标部门。"
                    ),
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


async def run_livzon_feishu_sync_all(db: AsyncSession) -> JsonObject:
    from app.platform.integrations.feishu.contact import get_contact_scope
    from app.platform.integrations.feishu.sync import (
        sync_departments,
        sync_members,
        sync_users_by_ids,
    )

    config = await _feishu_config_repo.get_active(db)
    app_id, app_secret, root_id, member_id = await _effective_feishu_credentials(db)

    scope: JsonObject = {}
    scope_department_ids: list[str] = []
    scope_user_ids: list[str] = []
    try:
        scope = await get_contact_scope(app_id=app_id, app_secret=app_secret)
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
            user_id_type="user_id",
            app_id=app_id,
            app_secret=app_secret,
        )

    dept_count = sum(item.get("dept_count", 0) for item in dept_results)
    member_count = sum(item.get("user_count", 0) for item in member_results)
    direct_user_count = direct_user_result.get("user_count", 0)
    total_user_count = member_count + direct_user_count
    nested_member_errors = [
        str(error)
        for result in member_results
        for error in result.get("errors", [])
    ]
    all_errors = dept_errors + member_errors + nested_member_errors

    if not dept_results and not member_results and not direct_user_count:
        message = (
            "同步失败：当前 Livzon 助手飞书应用没有可同步的通讯录数据。"
            "请检查通讯录权限范围是否包含目标部门或用户。"
        )
        if all_errors:
            message = f"{message} 错误：{'; '.join(all_errors)}"
        if config is not None:
            config.last_sync_status = "error"
            config.last_sync_message = message
            config.last_synced_at = datetime.now(UTC)
            await db.flush()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message)

    sync_status = "warning" if all_errors else "ok"
    sync_message = (
        f"同步完成：部门 {dept_count} 个，"
        f"部门用户 {member_count} 名，直接授权用户 {direct_user_count} 名。"
    )
    if sync_status == "warning":
        sync_message = (
            f"{sync_message} 部分部门同步失败："
            f"{'; '.join(all_errors)}"
        )
    if config is not None:
        config.last_sync_status = sync_status
        config.last_sync_message = sync_message
        config.last_synced_at = datetime.now(UTC)
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
        "status": sync_status,
        "message": sync_message,
    }


async def _active_livzon_feishu_credentials(db: AsyncSession) -> tuple[str, str]:
    config = await _feishu_config_repo.get_active(db)
    if config is None or not config.app_id or not config.encrypted_app_secret:
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


def _dedupe_user_ids(user_ids: list[UUID]) -> list[UUID]:
    return list(dict.fromkeys(user_ids))


def _empty_message_result(user_id: UUID, message: str) -> JsonObject:
    return {
        "user_id": str(user_id),
        "name": None,
        "feishu_open_id": None,
        "status": "failed",
        "message_id": None,
        "error_code": None,
        "error_message": message,
    }


def _message_shape(
    *,
    value_level: str,
    structured: bool,
    requires_business_action: bool,
    message_form: str = "auto",
) -> str:
    if message_form != "auto":
        if requires_business_action and message_form != "interactive_card":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "包含业务处理按钮的消息必须使用 interactive_card",
            )
        return message_form
    if requires_business_action:
        return "interactive_card"
    if value_level == "low" and not structured:
        return "text"
    return "card"


def _normalize_card_actions(
    actions: list[JsonObject] | None,
) -> list[dict[str, str]]:
    raw_actions = actions or [
        {"action_key": "start_processing", "label": "开始处理"},
        {"action_key": "mark_done", "label": "标记完成"},
    ]
    normalized: list[dict[str, str]] = []
    for item in raw_actions:
        action_key = str(item.get("action_key") or "").strip()
        if action_key not in ALLOWED_CARD_ACTIONS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"不支持的交互卡片动作：{action_key}",
            )
        label = str(item.get("label") or ALLOWED_CARD_ACTIONS[action_key]).strip()
        normalized.append(
            {
                "action_key": action_key,
                "label": label[:100],
                "button_type": str(item.get("button_type") or "primary"),
            }
        )
    return normalized


def _callback_action_status(action_key: str) -> str:
    if action_key == "reject":
        return "rejected"
    return "processed"


def _write_card_action_audit(
    db: AsyncSession,
    *,
    action: FeishuCardAction,
) -> None:
    if not hasattr(db, "add"):
        return
    db.add(
        AuditLog(
            request_id=str(action.card_id) if action.card_id else None,
            user_id=action.local_user_id,
            method="FEISHU",
            path="/api/v1/identity/feishu/card-callback",
            status_code=200,
            resource_type="feishu_card_action",
            resource_id=action.id,
            action="feishu_card_action_callback",
            new_value={
                "action_key": action.action_key,
                "status": action.status,
                "clicked_open_id": action.clicked_open_id,
            },
            extra={
                "message_id": action.message_id,
                "card_id": action.card_id,
                "recipient_open_id": action.recipient_open_id,
            },
        )
    )


def _write_livzon_message_audit(
    db: AsyncSession,
    *,
    user: User,
    message_id: str,
    outcome: str,
    session_id: UUID | None = None,
) -> None:
    """Record the Feishu entrypoint without persisting message content."""
    if not hasattr(db, "add"):
        return
    db.add(
        AuditLog(
            request_id=message_id[:64],
            user_id=user.id,
            method="FEISHU",
            path="/api/v1/identity/feishu/event-ws",
            status_code=200 if outcome == "processed" else 400,
            resource_type="agent_session",
            resource_id=session_id or user.id,
            action="feishu_agent_message",
            new_value={"outcome": outcome},
            extra={
                "message_id": message_id,
                "source_event": "im.message.receive_v1",
            },
        )
    )


async def _send_livzon_feishu_message(
    db: AsyncSession,
    *,
    user_ids: list[UUID],
    msg_type: str,
    content: str,
) -> JsonObject:
    from app.platform.integrations.feishu.im import send_feishu_message
    from app.platform.integrations.feishu.utils import get_tenant_access_token

    app_id, app_secret = await _active_livzon_feishu_credentials(db)
    token = await get_tenant_access_token(
        app_id,
        app_secret,
        cache_key=f"livzon-assistant:{app_id}",
    )

    results: list[JsonObject] = []
    for user_id in _dedupe_user_ids(user_ids):
        user = await _repo.get_by_id(db, user_id)
        if user is None:
            results.append(_empty_message_result(user_id, "本地用户不存在"))
            continue
        if not user.feishu_open_id:
            results.append(
                {
                    "user_id": str(user.id),
                    "name": user.name,
                    "feishu_open_id": None,
                    "status": "failed",
                    "message_id": None,
                    "error_code": None,
                    "error_message": "用户缺少 feishu_open_id，请先同步通讯录",
                }
            )
            continue

        try:
            sent = await send_feishu_message(
                tenant_access_token=token,
                receive_id=user.feishu_open_id,
                receive_id_type="open_id",
                msg_type=msg_type,
                content=content,
            )
        except Exception as exc:
            logger.exception(
                "Livzon Feishu message send failed: user_id=%s",
                user.id,
            )
            results.append(
                {
                    "user_id": str(user.id),
                    "name": user.name,
                    "feishu_open_id": user.feishu_open_id,
                    "status": "failed",
                    "message_id": None,
                    "error_code": None,
                    "error_message": str(exc),
                }
            )
            continue

        results.append(
            {
                "user_id": str(user.id),
                "name": user.name,
                "feishu_open_id": user.feishu_open_id,
                "status": "sent" if sent.ok else "failed",
                "message_id": sent.message_id,
                "error_code": sent.code if not sent.ok else None,
                "error_message": sent.error_message if not sent.ok else None,
            }
        )

    success_count = sum(1 for item in results if item["status"] == "sent")
    failed_count = len(results) - success_count
    return {
        "total": len(results),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
    }


async def _send_livzon_feishu_text_to_open_id(
    db: AsyncSession,
    *,
    open_id: str,
    text: str,
    markdown: bool = False,
) -> bool:
    """Reply to a private Livzon Feishu conversation without a local user id.

    Agent answers can contain Markdown.  Feishu text messages do not render it,
    so those replies are sent as an interactive card while short service hints
    remain plain text for a compact chat experience.
    """
    from app.platform.integrations.feishu.im import (
        build_markdown_card_content,
        build_text_message_content,
        send_feishu_message,
    )
    from app.platform.integrations.feishu.utils import get_tenant_access_token

    try:
        app_id, app_secret = await _active_livzon_feishu_credentials(db)
        token = await get_tenant_access_token(
            app_id,
            app_secret,
            cache_key=f"livzon-assistant:{app_id}",
        )
        sent = await send_feishu_message(
            tenant_access_token=token,
            receive_id=open_id,
            receive_id_type="open_id",
            msg_type="interactive" if markdown else "text",
            content=(
                build_markdown_card_content(
                    title="Livzon 助手",
                    markdown=text,
                    header_template="blue",
                )
                if markdown
                else build_text_message_content(text)
            ),
        )
    except Exception:
        logger.exception("Livzon 飞书私聊回复请求失败: open_id=%s", open_id)
        return False
    if not sent.ok:
        logger.warning(
            "Livzon 飞书私聊回复失败: open_id=%s code=%s message=%s",
            open_id,
            sent.code,
            sent.error_message,
        )
        return False
    return True


async def _send_livzon_agent_confirmation_cards(
    db: AsyncSession,
    *,
    user: User,
    confirmations: Sequence[AgentConfirmation],
) -> None:
    for confirmation in confirmations:
        try:
            await _send_livzon_feishu_callback_card(
                db,
                user_ids=[user.id],
                title="Livzon 助手操作确认",
                markdown=(
                    f"**{confirmation.summary}**\n\n"
                    f"风险等级：{confirmation.risk_level}\n\n"
                    "请确认是否执行此操作。"
                ),
                header_template="orange",
                actions=[
                    {
                        "action_key": "agent_confirmation_execute",
                        "label": "确认执行",
                        "button_type": "primary",
                    },
                    {
                        "action_key": "agent_confirmation_cancel",
                        "label": "取消",
                        "button_type": "default",
                    },
                ],
                business_ref={
                    "kind": "agent_confirmation",
                    "confirmation_id": str(confirmation.id),
                    "summary": confirmation.summary,
                },
                expires_at=confirmation.expires_at,
            )
        except Exception:
            logger.exception(
                "Livzon 飞书确认卡片发送失败: confirmation_id=%s",
                confirmation.id,
            )


def _parse_livzon_feishu_message_event(
    payload: JsonObject,
) -> JsonObject | None:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    message = event.get("message") if isinstance(event, dict) else None
    sender = event.get("sender") if isinstance(event, dict) else None
    if not isinstance(message, dict) or not isinstance(sender, dict):
        return None
    if sender.get("sender_type") != "user" or message.get("chat_type") != "p2p":
        return None
    sender_id = sender.get("sender_id") or {}
    open_id = sender_id.get("open_id") if isinstance(sender_id, dict) else None
    message_id = message.get("message_id")
    if not isinstance(open_id, str) or not isinstance(message_id, str):
        return None
    if message.get("message_type") != "text":
        return {
            "open_id": open_id,
            "message_id": message_id,
            "unsupported": True,
        }
    try:
        content = json.loads(message.get("content") or "{}")
    except json.JSONDecodeError:
        content = {}
    text = content.get("text") if isinstance(content, dict) else None
    if (
        not isinstance(text, str)
    ):
        return None
    return {"open_id": open_id, "message_id": message_id, "text": text.strip()}


async def handle_livzon_feishu_message_receive_event(
    db: AsyncSession,
    *,
    payload: JsonObject,
) -> JsonObject:
    """Process one authenticated ``im.message.receive_v1`` event."""
    parsed = _parse_livzon_feishu_message_event(payload)
    if parsed is None:
        return {"status": "ignored"}
    open_id = parsed.get("open_id")
    if not isinstance(open_id, str):
        return {"status": "ignored"}
    message_id = parsed.get("message_id")
    if not isinstance(message_id, str):
        return {"status": "ignored"}

    from app.core.redis import acquire_lock, redis_client, release_lock

    try:
        is_new = await redis_client.set(
            f"livzon:feishu:message:{message_id}", "1", ex=86400, nx=True
        )
    except Exception:
        logger.exception(
            "Livzon 飞书消息去重不可用，继续处理: message_id=%s", message_id
        )
        is_new = True
    if not is_new:
        return {"status": "duplicate"}
    if parsed.get("unsupported"):
        await _send_livzon_feishu_text_to_open_id(
            db,
            open_id=open_id,
            text="当前仅支持发送文本消息，请改用文字与 Livzon 助手对话。",
        )
        return {"status": "unsupported"}

    text = str(parsed["text"])
    if not text:
        await _send_livzon_feishu_text_to_open_id(
            db, open_id=open_id, text="请输入需要咨询的内容。"
        )
        return {"status": "empty"}
    if len(text) > 8000:
        await _send_livzon_feishu_text_to_open_id(
            db, open_id=open_id, text="单条消息不能超过 8000 个字符，请拆分后重试。"
        )
        return {"status": "too_long"}

    lock_key = f"livzon:feishu:conversation:{open_id}"
    try:
        acquired = await acquire_lock(lock_key, timeout=150)
    except Exception:
        logger.exception("Livzon 飞书会话锁不可用，继续处理: open_id=%s", open_id)
        acquired = True
    if not acquired:
        await _send_livzon_feishu_text_to_open_id(
            db, open_id=open_id, text="上一条消息正在处理中，请稍后再发送。"
        )
        return {"status": "busy"}

    try:
        user = await _repo.get_by_feishu_open_id(db, open_id)
        if user is None or user.is_deleted or user.status != "active":
            await _send_livzon_feishu_text_to_open_id(
                db,
                open_id=open_id,
                text=(
                    "尚未绑定可用的 Livzon 账户，请联系管理员同步通讯录并授予"
                    "助手权限。"
                ),
            )
            return {"status": "unmapped"}

        from app.modules.agent.public_api import handle_feishu_direct_message

        try:
            result = await handle_feishu_direct_message(
                db,
                user=user,
                sender_open_id=open_id,
                message_id=message_id,
                text=text,
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                reply = "你当前没有 Livzon 助手访问权限，请联系管理员授权后重试。"
            else:
                logger.warning("Livzon 飞书消息处理被拒绝: %s", exc.detail)
                reply = "暂时无法处理该消息，请稍后重试。"
            await _send_livzon_feishu_text_to_open_id(db, open_id=open_id, text=reply)
            _write_livzon_message_audit(
                db,
                user=user,
                message_id=message_id,
                outcome="rejected",
            )
            return {"status": "rejected"}
        except Exception:
            logger.exception("Livzon 飞书消息处理失败: message_id=%s", message_id)
            await _send_livzon_feishu_text_to_open_id(
                db, open_id=open_id, text="Livzon 助手暂时不可用，请稍后重试。"
            )
            _write_livzon_message_audit(
                db,
                user=user,
                message_id=message_id,
                outcome="failed",
            )
            return {"status": "failed"}

        reply = result.text
        if result.pending_confirmations:
            reply = f"{reply}\n\n需要确认的操作已发送为下方卡片。"
        await _send_livzon_feishu_text_to_open_id(
            db,
            open_id=open_id,
            text=reply,
            markdown=True,
        )
        await _send_livzon_agent_confirmation_cards(
            db,
            user=user,
            confirmations=result.pending_confirmations,
        )
        _write_livzon_message_audit(
            db,
            user=user,
            message_id=message_id,
            outcome="processed",
            session_id=result.session_id,
        )
        return {
            "status": "processed",
            "session_id": str(result.session_id) if result.session_id else None,
        }
    finally:
        try:
            await release_lock(lock_key)
        except Exception:
            logger.exception("释放 Livzon 飞书会话锁失败: open_id=%s", open_id)


async def _send_livzon_feishu_callback_card(
    db: AsyncSession,
    *,
    user_ids: list[UUID],
    title: str,
    markdown: str,
    header_template: str,
    actions: list[JsonObject] | None,
    business_ref: JsonObject | None,
    expires_at: datetime | None = None,
) -> JsonObject:
    from app.platform.integrations.feishu.im import (
        build_callback_card_content,
        send_feishu_message,
    )
    from app.platform.integrations.feishu.utils import get_tenant_access_token

    settings = get_settings()
    config = await _feishu_config_repo.get_active(db)
    if config is None or (
        not config.card_callback_verification_token
        and not getattr(settings, "LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED", False)
        and not getattr(settings, "LIVZON_FEISHU_EVENT_WS_ENABLED", False)
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            (
                "Livzon 助手飞书交互卡片回调未配置。HTTP 回调需要 "
                "Verification Token；开发环境可开启长连接 "
                "LIVZON_FEISHU_EVENT_WS_ENABLED=true。"
            ),
        )
    app_id, app_secret = await _active_livzon_feishu_credentials(db)
    token = await get_tenant_access_token(
        app_id,
        app_secret,
        cache_key=f"livzon-assistant:{app_id}",
    )
    normalized_actions = _normalize_card_actions(actions)
    results: list[JsonObject] = []
    action_expires_at = expires_at or (datetime.now(UTC) + timedelta(days=14))

    for user_id in _dedupe_user_ids(user_ids):
        user = await _repo.get_by_id(db, user_id)
        if user is None:
            results.append(_empty_message_result(user_id, "本地用户不存在"))
            continue
        if not user.feishu_open_id:
            results.append(
                {
                    "user_id": str(user.id),
                    "name": user.name,
                    "feishu_open_id": None,
                    "status": "failed",
                    "message_id": None,
                    "error_code": None,
                    "error_message": "用户缺少 feishu_open_id，请先同步通讯录",
                }
            )
            continue

        card_id = f"livzon-{secrets.token_hex(12)}"
        card_actions: list[dict[str, str]] = []
        created_actions: list[FeishuCardAction] = []
        for item in normalized_actions:
            action = await _feishu_card_action_repo.create(
                db,
                message_id=None,
                card_id=card_id,
                local_user_id=user.id,
                recipient_open_id=user.feishu_open_id,
                business_ref=business_ref,
                action_key=item["action_key"],
                action_label=item["label"],
                expires_at=action_expires_at,
            )
            created_actions.append(action)
            card_actions.append(
                {
                    "action_id": str(action.id),
                    "action_key": item["action_key"],
                    "label": item["label"],
                    "button_type": item["button_type"],
                }
            )
        content = build_callback_card_content(
            title=title,
            markdown=markdown,
            actions=card_actions,
            header_template=header_template,
        )
        try:
            sent = await send_feishu_message(
                tenant_access_token=token,
                receive_id=user.feishu_open_id,
                receive_id_type="open_id",
                msg_type="interactive",
                content=content,
            )
        except Exception as exc:
            logger.exception(
                "Livzon Feishu callback card send failed: user_id=%s",
                user.id,
            )
            for action in created_actions:
                action.status = "failed"
                action.callback_summary = {"result": "delivery_failed"}
            await db.flush()
            results.append(
                {
                    "user_id": str(user.id),
                    "name": user.name,
                    "feishu_open_id": user.feishu_open_id,
                    "status": "failed",
                    "message_id": None,
                    "error_code": None,
                    "error_message": str(exc),
                    "message_form": "interactive_card",
                }
            )
            continue
        if not sent.ok:
            for action in created_actions:
                action.status = "failed"
                action.callback_summary = {
                    "result": "delivery_failed",
                    "error_code": sent.code,
                }
            await db.flush()
            results.append(
                {
                    "user_id": str(user.id),
                    "name": user.name,
                    "feishu_open_id": user.feishu_open_id,
                    "status": "failed",
                    "message_id": None,
                    "error_code": sent.code,
                    "error_message": sent.error_message,
                    "message_form": "interactive_card",
                }
            )
            continue
        await _feishu_card_action_repo.set_message_id_for_card(
            db,
            card_id=card_id,
            message_id=sent.message_id,
        )
        results.append(
            {
                "user_id": str(user.id),
                "name": user.name,
                "feishu_open_id": user.feishu_open_id,
                "status": "sent" if sent.ok else "failed",
                "message_id": sent.message_id,
                "error_code": sent.code if not sent.ok else None,
                "error_message": sent.error_message if not sent.ok else None,
                "message_form": "interactive_card",
                "callback_action_count": len(card_actions),
            }
        )

    success_count = sum(1 for item in results if item["status"] == "sent")
    failed_count = len(results) - success_count
    return {
        "message_form": "interactive_card",
        "total": len(results),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
    }


async def send_livzon_feishu_text_message(
    db: AsyncSession,
    *,
    user_ids: list[UUID],
    text: str,
) -> JsonObject:
    from app.platform.integrations.feishu.im import build_text_message_content

    return await _send_livzon_feishu_message(
        db,
        user_ids=user_ids,
        msg_type="text",
        content=build_text_message_content(text),
    )


async def send_livzon_feishu_card_message(
    db: AsyncSession,
    *,
    user_ids: list[UUID],
    title: str,
    markdown: str,
    header_template: str = "blue",
    button_text: str | None = None,
    button_url: str | None = None,
) -> JsonObject:
    from app.platform.integrations.feishu.im import build_simple_card_content

    return await _send_livzon_feishu_message(
        db,
        user_ids=user_ids,
        msg_type="interactive",
        content=build_simple_card_content(
            title=title,
            markdown=markdown,
            header_template=header_template,
            button_text=button_text,
            button_url=button_url,
        ),
    )


async def send_livzon_feishu_message(
    db: AsyncSession,
    *,
    user_ids: list[UUID],
    text: str,
    title: str | None = None,
    markdown: str | None = None,
    value_level: str = "low",
    structured: bool = False,
    requires_business_action: bool = False,
    actions: list[JsonObject] | None = None,
    business_ref: JsonObject | None = None,
    header_template: str = "blue",
    message_form: str = "auto",
) -> JsonObject:
    shape = _message_shape(
        value_level=value_level,
        structured=structured,
        requires_business_action=requires_business_action,
        message_form=message_form,
    )
    if shape == "text":
        result = await send_livzon_feishu_text_message(
            db,
            user_ids=user_ids,
            text=text,
        )
        result["message_form"] = "text"
        return result
    card_title = title or "Livzon 助手通知"
    card_markdown = markdown or text
    if shape == "card":
        result = await send_livzon_feishu_card_message(
            db,
            user_ids=user_ids,
            title=card_title,
            markdown=card_markdown,
            header_template=header_template,
        )
        result["message_form"] = "card"
        return result
    return await _send_livzon_feishu_callback_card(
        db,
        user_ids=user_ids,
        title=card_title,
        markdown=card_markdown,
        header_template=header_template,
        actions=actions,
        business_ref=business_ref,
    )


def _verify_feishu_callback_signature(
    *,
    encrypt_key: str | None,
    raw_body: bytes,
    timestamp: str | None,
    nonce: str | None,
    signature: str | None,
) -> bool:
    if not encrypt_key or not timestamp or not nonce or not signature:
        return True
    raw = f"{timestamp}{nonce}{encrypt_key}".encode() + raw_body
    expected = hashlib.sha256(raw).hexdigest()
    return hmac.compare_digest(expected, signature)


def _callback_payload_token(payload: JsonObject) -> str | None:
    token = payload.get("token")
    if isinstance(token, str):
        return token
    header = payload.get("header")
    if isinstance(header, dict):
        header_token = header.get("token")
        if isinstance(header_token, str):
            return header_token
    return None


def _extract_callback_action(
    payload: JsonObject,
) -> tuple[str | None, str | None, str | None]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    action = event.get("action") if isinstance(event, dict) else None
    value = action.get("value") if isinstance(action, dict) else None
    action_id = value.get("action_id") if isinstance(value, dict) else None
    action_key = value.get("action_key") if isinstance(value, dict) else None
    operator = event.get("operator") if isinstance(event, dict) else None
    open_id = None
    if isinstance(operator, dict):
        open_id = operator.get("open_id") or operator.get("user_id")
    user = event.get("user") if isinstance(event, dict) else None
    if not open_id and isinstance(user, dict):
        open_id = user.get("open_id") or user.get("user_id")
    return (
        action_id if isinstance(action_id, str) else None,
        action_key if isinstance(action_key, str) else None,
        open_id if isinstance(open_id, str) else None,
    )


async def handle_livzon_feishu_card_callback(
    db: AsyncSession,
    *,
    payload: JsonObject,
    raw_body: bytes,
    timestamp: str | None = None,
    nonce: str | None = None,
    signature: str | None = None,
) -> JsonObject:
    config = await _feishu_config_repo.get_active(db)
    if config is None or not config.card_callback_verification_token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Livzon 助手飞书卡片回调未配置",
        )
    encrypt_key = None
    if config.encrypted_card_callback_encrypt_key:
        try:
            encrypt_key = decrypt_secret(config.encrypted_card_callback_encrypt_key)
        except RuntimeError as exc:
            raise _secret_runtime_error(exc) from exc
    if not _verify_feishu_callback_signature(
        encrypt_key=encrypt_key,
        raw_body=raw_body,
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "飞书回调签名校验失败")
    if "encrypt" in payload:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "暂不支持加密后的飞书卡片回调 payload，请关闭加密或使用签名校验",
        )
    token = _callback_payload_token(payload)
    if not token or not hmac.compare_digest(
        token,
        config.card_callback_verification_token,
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "飞书回调 token 校验失败")
    challenge = payload.get("challenge")
    if isinstance(challenge, str):
        return {"challenge": challenge}

    return await handle_livzon_feishu_card_action_event(db, payload=payload)


async def handle_livzon_feishu_card_action_event(
    db: AsyncSession,
    *,
    payload: JsonObject,
) -> JsonObject:
    """Handle authenticated Livzon Feishu card action payloads.

    HTTP callbacks validate verification token/signature before calling this.
    WebSocket callbacks are authenticated by the Feishu long-connection channel.
    """
    action_id, action_key, clicked_open_id = _extract_callback_action(payload)
    if not action_id or not action_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "飞书回调缺少 action_id")
    action = await _feishu_card_action_repo.get_by_id_for_update(db, action_id)
    if action is None:
        return {"toast": {"type": "warning", "content": "操作不存在或已删除"}}
    if action.action_key != action_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "飞书回调动作不匹配")
    if not clicked_open_id or (
        action.recipient_open_id
        and not hmac.compare_digest(clicked_open_id, action.recipient_open_id)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "卡片动作仅限原收件人执行")
    if action.local_user_id:
        recipient = await _repo.get_by_id(db, action.local_user_id)
        if recipient is None or recipient.status != "active" or recipient.is_deleted:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "卡片收件人当前不可用")
    now = datetime.now(UTC)
    if action.expires_at and action.expires_at < now:
        action.status = "expired"
        action.clicked_open_id = clicked_open_id
        action.executed_at = now
        action.callback_summary = {
            "action_id": action_id,
            "action_key": action_key,
            "clicked_open_id": clicked_open_id,
            "result": "expired",
        }
        _write_card_action_audit(db, action=action)
        await db.flush()
        return {"toast": {"type": "warning", "content": "该操作已过期"}}
    if action.status != "pending":
        return {"toast": {"type": "info", "content": "该操作已处理"}}

    raw_business_ref = getattr(action, "business_ref", None)
    business_ref = raw_business_ref if isinstance(raw_business_ref, dict) else {}
    if business_ref.get("kind") == "agent_confirmation":
        if action.local_user_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "确认卡片缺少本地收件人",
            )
        confirmation_id = business_ref.get("confirmation_id")
        try:
            parsed_confirmation_id = UUID(str(confirmation_id))
        except (TypeError, ValueError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "确认卡片缺少有效确认项")
        recipient = await _repo.get_by_id(db, action.local_user_id)
        if recipient is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "卡片收件人当前不可用")

        from app.modules.agent.public_api import (
            cancel_feishu_confirmation,
            execute_feishu_confirmation,
        )

        try:
            if action_key == "agent_confirmation_execute":
                confirmation, _ = await execute_feishu_confirmation(
                    db,
                    confirmation_id=parsed_confirmation_id,
                    user=recipient,
                )
                status_text = f"已执行确认操作：{confirmation.summary}"
            elif action_key == "agent_confirmation_cancel":
                confirmation = await cancel_feishu_confirmation(
                    db,
                    confirmation_id=parsed_confirmation_id,
                    user=recipient,
                )
                status_text = f"已取消确认操作：{confirmation.summary}"
            else:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "不支持的确认卡片动作")
        except HTTPException as exc:
            action.callback_summary = {
                "action_id": action_id,
                "action_key": action_key,
                "result": "rejected",
                "error": str(exc.detail),
            }
            await db.flush()
            return {"toast": {"type": "warning", "content": str(exc.detail)}}

        action.status = "processed"
        action.clicked_open_id = clicked_open_id
        action.executed_at = now
        action.callback_summary = {
            "action_id": action_id,
            "action_key": action_key,
            "confirmation_id": str(confirmation.id),
            "confirmation_status": confirmation.status,
        }
        _write_card_action_audit(db, action=action)
        await db.flush()
        return {
            "toast": {"type": "success", "content": status_text},
            "_callback_message_id": action.message_id,
            "card": json.loads(
                build_callback_status_card_content(
                    title="Livzon 助手操作确认",
                    markdown=str(business_ref.get("summary") or confirmation.summary),
                    status_text=status_text,
                )
            ),
        }

    action.status = _callback_action_status(action_key)
    action.clicked_open_id = clicked_open_id
    action.executed_at = now
    action.callback_summary = {
        "action_id": action_id,
        "action_key": action_key,
        "clicked_open_id": clicked_open_id,
        "status": action.status,
    }
    _write_card_action_audit(db, action=action)
    await db.flush()
    status_text = f"已记录：{action.action_label}"
    return {
        "toast": {
            "type": "success",
            "content": status_text,
        },
        "_callback_message_id": action.message_id,
        "card": json.loads(
            build_callback_status_card_content(
                title="Livzon 卡片操作",
                markdown=f"操作：{action.action_label}",
                status_text=status_text,
            )
        ),
    }


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
        user.feishu_department_ids = (
            feishu_department_ids or user.feishu_department_ids
        )
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
