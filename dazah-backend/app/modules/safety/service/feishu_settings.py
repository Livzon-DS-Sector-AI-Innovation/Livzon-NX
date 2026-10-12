"""安全模块飞书设置服务。

配置存 safety.feishu_app_settings（单行），App Secret 加密存储；
对齐质量模块 quality_feishu_settings 的行为：脱敏回显、掩码回传保持原值、
连接测试写回 last_test_* 字段、错误信息中的飞书标识符脱敏。
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm.encryption import encrypt_api_key, mask_api_key
from app.modules.safety.feishu.runtime_config import (
    SafetyFeishuConfigError,
    decrypt_stored_secret,
)
from app.modules.safety.models import SafetyFeishuAppSettings
from app.modules.safety.schemas.feishu_settings import (
    SafetyFeishuAppSettingsDetail,
    SafetyFeishuSettingsTestResult,
    UpdateSafetyFeishuAppSettingsRequest,
)
from app.platform.integrations.feishu.auth import FeishuAuth

logger = logging.getLogger(__name__)

_FEISHU_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:bascn?|tbl|cli_)[A-Za-z0-9_-]{4,}\b",
    re.IGNORECASE,
)


def _mask_feishu_identifier(value: str) -> str:
    normalized = (value or "").strip()
    if len(normalized) <= 8:
        return "****"
    return f"{normalized[:4]}****{normalized[-4:]}"


def _sanitize_feishu_error_message(message: str) -> str:
    """错误信息中的飞书 App ID / 多维表格标识符脱敏后再存储或返回前端。"""
    return _FEISHU_IDENTIFIER_PATTERN.sub(
        lambda match: _mask_feishu_identifier(match.group()),
        message,
    )


def _is_settings_table_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "feishu_app_settings" in text
        or "does not exist" in text
        or "undefinedtable" in text
        or "no such table" in text
    )


def _clean_optional(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _decrypt_for_settings_page(encrypted: str | None) -> str:
    """设置页专用解密：密钥轮换导致解密失败时返回空串。

    返回空串而非抛错，保证设置页可加载、可重新保存覆盖损坏的存量密文。
    """
    if not encrypted:
        return ""
    try:
        return decrypt_stored_secret(encrypted)
    except SafetyFeishuConfigError:
        logger.warning("安全模块飞书 App Secret 解密失败（加密密钥已轮换），需重新保存")
        return ""


async def _get_settings_model(db: AsyncSession) -> SafetyFeishuAppSettings | None:
    result = await db.execute(
        select(SafetyFeishuAppSettings)
        .where(SafetyFeishuAppSettings.is_deleted.is_(False))
        .order_by(SafetyFeishuAppSettings.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _build_detail(
    model: SafetyFeishuAppSettings | None,
) -> SafetyFeishuAppSettingsDetail:
    if not model:
        return SafetyFeishuAppSettingsDetail()
    decrypted_secret = _decrypt_for_settings_page(model.app_secret)
    return SafetyFeishuAppSettingsDetail(
        app_id=model.app_id or "",
        app_secret_masked=mask_api_key(decrypted_secret),
        bitable_app_token=model.bitable_app_token,
        bitable_hazard_table_id=model.bitable_hazard_table_id,
        knowledge_app_token=model.knowledge_app_token,
        knowledge_table_id=model.knowledge_table_id,
        radar_scan_enabled=model.radar_scan_enabled,
        radar_notify_enabled=model.radar_notify_enabled,
        radar_notify_chat_ids=list(model.radar_notify_chat_ids or []),
        radar_notify_user_ids=list(model.radar_notify_user_ids or []),
        is_enabled=model.is_enabled,
        knowledge_last_sync_status=model.knowledge_last_sync_status,
        knowledge_last_sync_error=model.knowledge_last_sync_error,
        knowledge_last_synced_at=model.knowledge_last_synced_at,
        last_test_status=model.last_test_status,
        last_test_error=model.last_test_error,
        last_tested_at=model.last_tested_at,
    )


async def get_safety_feishu_app_settings(
    db: AsyncSession,
) -> SafetyFeishuAppSettingsDetail:
    try:
        model = await _get_settings_model(db)
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            return SafetyFeishuAppSettingsDetail()
        raise
    return _build_detail(model)


async def update_safety_feishu_app_settings(
    db: AsyncSession,
    data: UpdateSafetyFeishuAppSettingsRequest,
) -> SafetyFeishuAppSettingsDetail:
    try:
        model = await _get_settings_model(db)
        app_secret = data.app_secret.strip()
        if model is None:
            if not app_secret:
                raise AppException(message="App Secret 不能为空")
            model = SafetyFeishuAppSettings(
                app_id=data.app_id.strip(),
                app_secret=encrypt_api_key(app_secret),
                bitable_app_token=_clean_optional(data.bitable_app_token),
                bitable_hazard_table_id=_clean_optional(data.bitable_hazard_table_id),
                knowledge_app_token=_clean_optional(data.knowledge_app_token),
                knowledge_table_id=_clean_optional(data.knowledge_table_id),
                radar_scan_enabled=data.radar_scan_enabled,
                radar_notify_enabled=data.radar_notify_enabled,
                radar_notify_chat_ids=list(data.radar_notify_chat_ids or []),
                radar_notify_user_ids=list(data.radar_notify_user_ids or []),
                is_enabled=data.is_enabled,
            )
            db.add(model)
        else:
            model.app_id = data.app_id.strip()
            model.is_enabled = data.is_enabled
            current_secret = _decrypt_for_settings_page(model.app_secret)
            # 掩码值回传表示未修改；仅当输入为新明文时覆盖密文，
            # 存量密文解密失败时 current_secret 抛错提示重新保存。
            if app_secret and app_secret != mask_api_key(current_secret):
                model.app_secret = encrypt_api_key(app_secret)
            if "bitable_app_token" in data.model_fields_set:
                model.bitable_app_token = _clean_optional(data.bitable_app_token)
            if "bitable_hazard_table_id" in data.model_fields_set:
                model.bitable_hazard_table_id = _clean_optional(
                    data.bitable_hazard_table_id
                )
            if "knowledge_app_token" in data.model_fields_set:
                model.knowledge_app_token = _clean_optional(data.knowledge_app_token)
            if "knowledge_table_id" in data.model_fields_set:
                model.knowledge_table_id = _clean_optional(data.knowledge_table_id)
            if "radar_scan_enabled" in data.model_fields_set:
                model.radar_scan_enabled = data.radar_scan_enabled
            if "radar_notify_enabled" in data.model_fields_set:
                model.radar_notify_enabled = data.radar_notify_enabled
            if "radar_notify_chat_ids" in data.model_fields_set:
                model.radar_notify_chat_ids = list(data.radar_notify_chat_ids or [])
            if "radar_notify_user_ids" in data.model_fields_set:
                model.radar_notify_user_ids = list(data.radar_notify_user_ids or [])
        await db.commit()
        return _build_detail(model)
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            raise AppException(
                message="飞书设置数据表未创建，请先执行安全模块数据库迁移"
            )
        raise


async def test_safety_feishu_app_settings(
    db: AsyncSession,
) -> SafetyFeishuSettingsTestResult:
    try:
        model = await _get_settings_model(db)
    except (OperationalError, ProgrammingError) as exc:
        if _is_settings_table_missing(exc):
            raise AppException(
                message="飞书设置数据表未创建，请先执行安全模块数据库迁移"
            )
        raise
    if not model:
        raise AppException(message="请先保存飞书应用信息")
    checked_at = datetime.now(UTC)
    stored_secret = _decrypt_for_settings_page(model.app_secret)
    if model.app_secret and not stored_secret:
        raise AppException(
            message=(
                "已保存的 App Secret 无法解密（加密密钥已轮换），"
                "请重新输入 App Secret 并保存后再测试连接"
            ),
            status_code=400,
        )
    try:
        await FeishuAuth.get_tenant_access_token(
            app_id=model.app_id,
            app_secret=stored_secret,
        )
        model.last_test_status = "success"
        model.last_test_error = None
        model.last_tested_at = checked_at
        await db.commit()
        return SafetyFeishuSettingsTestResult(
            success=True,
            message="飞书应用连接成功",
            checked_at=checked_at,
        )
    except Exception as exc:
        safe_error = _sanitize_feishu_error_message(str(exc))
        model.last_test_status = "failed"
        model.last_test_error = safe_error
        model.last_tested_at = checked_at
        await db.commit()
        return SafetyFeishuSettingsTestResult(
            success=False,
            message=safe_error,
            checked_at=checked_at,
        )
