"""设备巡检飞书镜像配置服务。

配置来源优先级：数据库单行配置（App Secret 加密存储）→
EQUIPMENT_FEISHU_* 环境变量回退。数据库行一旦保存即视为权威，
环境变量仅在没有数据库行时生效。知识库（/wiki/）链接在保存时
解析为真实多维表格 App Token，镜像同步运行时不再解析。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.llm.encryption import decrypt_api_key, encrypt_api_key, mask_api_key
from app.core.llm.exceptions import LLMConfigError
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.schemas.inspection import (
    EquipmentInspectionFeishuConfigDetail,
    EquipmentInspectionFeishuConfigTestResult,
    EquipmentInspectionFeishuConfigUpdateRequest,
)
from app.platform.integrations.feishu.bitable import BitableClient
from app.platform.integrations.feishu.utils import (
    extract_wiki_node_token,
    normalize_app_token,
    normalize_table_id,
    resolve_wiki_bitable_app_token,
)

logger = logging.getLogger(__name__)

settings = get_settings()

CONFIG_SOURCE_DATABASE = "database"
CONFIG_SOURCE_ENVIRONMENT = "environment"

_FEISHU_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:bascn?|tbl|cli_)[A-Za-z0-9_-]{4,}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InspectionFeishuEffectiveConfig:
    """镜像同步实际使用的配置（Secret 已解密）"""

    app_id: str
    app_secret: str
    app_token: str
    today_table_id: str
    history_table_id: str
    device_table_id: str
    is_enabled: bool
    source: str

    @property
    def enabled(self) -> bool:
        return bool(
            self.is_enabled and self.app_id and self.app_secret and self.app_token
        )


def _mask_feishu_identifier(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def _sanitize_feishu_error_message(message: str | None) -> str | None:
    """失败信息中掩码 app_token / table_id / 应用凭据等标识符。"""
    if not message:
        return message
    return _FEISHU_IDENTIFIER_PATTERN.sub(
        lambda match: _mask_feishu_identifier(match.group()),
        message,
    )


def _decrypt_stored_secret(encrypted: str | None) -> str:
    """解密存量 App Secret；密钥轮换导致解密失败时返回空串。

    返回空串而非抛错，保证配置读取和镜像展示可用，用户重新
    保存 Secret 即可覆盖损坏的存量密文。
    """
    if not encrypted:
        return ""
    try:
        return decrypt_api_key(encrypted)
    except LLMConfigError:
        logger.warning("设备巡检飞书 App Secret 解密失败（加密密钥已轮换），需重新保存")
        return ""


async def _get_config_row(db: AsyncSession) -> EquipmentInspectionFeishuConfig | None:
    result = await db.execute(select(EquipmentInspectionFeishuConfig).limit(1))
    return result.scalars().first()


def _env_config() -> InspectionFeishuEffectiveConfig:
    return InspectionFeishuEffectiveConfig(
        app_id=settings.EQUIPMENT_FEISHU_APP_ID.strip(),
        app_secret=settings.EQUIPMENT_FEISHU_APP_SECRET.strip(),
        app_token=settings.EQUIPMENT_FEISHU_BITABLE_APP_TOKEN.strip(),
        today_table_id=settings.EQUIPMENT_FEISHU_BITABLE_TODAY_TABLE_ID.strip(),
        history_table_id=settings.EQUIPMENT_FEISHU_BITABLE_HISTORY_TABLE_ID.strip(),
        device_table_id=settings.EQUIPMENT_FEISHU_BITABLE_DEVICE_TABLE_ID.strip(),
        is_enabled=True,
        source=CONFIG_SOURCE_ENVIRONMENT,
    )


def _row_config(
    row: EquipmentInspectionFeishuConfig,
) -> InspectionFeishuEffectiveConfig:
    return InspectionFeishuEffectiveConfig(
        app_id=(row.app_id or "").strip(),
        app_secret=_decrypt_stored_secret(row.app_secret),
        app_token=(row.app_token or "").strip(),
        today_table_id=(row.today_table_id or "").strip(),
        history_table_id=(row.history_table_id or "").strip(),
        device_table_id=(row.device_table_id or "").strip(),
        is_enabled=row.is_enabled,
        source=CONFIG_SOURCE_DATABASE,
    )


async def get_effective_config(db: AsyncSession) -> InspectionFeishuEffectiveConfig:
    """数据库行优先，无行时回退环境变量。"""
    row = await _get_config_row(db)
    if row is None:
        return _env_config()
    return _row_config(row)


async def is_mirror_enabled(db: AsyncSession) -> bool:
    return (await get_effective_config(db)).enabled


async def get_config_detail(db: AsyncSession) -> EquipmentInspectionFeishuConfigDetail:
    row = await _get_config_row(db)
    config = _row_config(row) if row else _env_config()
    return EquipmentInspectionFeishuConfigDetail(
        app_id=config.app_id,
        app_secret_masked=mask_api_key(config.app_secret) if config.app_secret else "",
        app_secret_configured=bool(config.app_secret),
        app_token=config.app_token,
        today_table_id=config.today_table_id,
        history_table_id=config.history_table_id,
        device_table_id=config.device_table_id,
        is_enabled=config.is_enabled,
        source=config.source,
        enabled=config.enabled,
        last_test_status=row.last_test_status if row else None,
        last_test_error=(
            _sanitize_feishu_error_message(row.last_test_error) if row else None
        ),
        last_tested_at=row.last_tested_at if row else None,
    )


def _normalized_table_id(value: str) -> str:
    """兼容直接粘贴子表链接 / 带 table 参数的 URL / 裸 table ID。"""
    return normalize_table_id(value) or ""


async def _resolve_app_token(
    *, app_id: str, app_secret: str, raw_app_token: str
) -> str:
    """知识库（/wiki/）链接解析为真实 App Token；其余按 URL/裸 Token 归一。"""
    node_token = extract_wiki_node_token(raw_app_token)
    if node_token:
        if not app_id or not app_secret:
            raise AppException(message="解析知识库链接需先填写 App ID 与 App Secret")
        try:
            return await resolve_wiki_bitable_app_token(
                app_id=app_id,
                app_secret=app_secret,
                node_token=node_token,
            )
        except AppException:
            raise
        except Exception as exc:
            raise AppException(
                message=f"解析知识库多维表格失败：{_sanitize_feishu_error_message(str(exc))}"
            ) from exc
    return normalize_app_token(raw_app_token) or ""


async def update_config(
    db: AsyncSession, data: EquipmentInspectionFeishuConfigUpdateRequest
) -> EquipmentInspectionFeishuConfigDetail:
    row = await _get_config_row(db)
    app_id = data.app_id.strip()
    submitted_secret = (data.app_secret or "").strip()

    if row is None:
        current_secret = ""
        if not app_id or not submitted_secret:
            raise AppException(
                message=(
                    "首次保存需填写 App ID 与 App Secret"
                    "（保存后数据库配置优先于环境变量）"
                )
            )
    else:
        current_secret = _decrypt_stored_secret(row.app_secret)

    # 掩码回传不当作新密钥加密（前端未修改 Secret 时可能原样带回掩码）
    secret_changed = bool(
        submitted_secret and submitted_secret != mask_api_key(current_secret)
    )
    if secret_changed:
        current_secret = submitted_secret

    app_token = await _resolve_app_token(
        app_id=app_id,
        app_secret=current_secret,
        raw_app_token=data.app_token.strip(),
    )
    if data.is_enabled and (not app_id or not current_secret or not app_token):
        raise AppException(
            message="启用同步需完整填写 App ID、App Secret 与多维表格 App Token"
        )

    if row is None:
        row = EquipmentInspectionFeishuConfig(
            app_secret=encrypt_api_key(current_secret)
        )
        db.add(row)
    elif secret_changed:
        row.app_secret = encrypt_api_key(current_secret)

    row.app_id = app_id
    row.is_enabled = data.is_enabled
    row.app_token = app_token
    row.today_table_id = _normalized_table_id(data.today_table_id)
    row.history_table_id = _normalized_table_id(data.history_table_id)
    row.device_table_id = _normalized_table_id(data.device_table_id)

    await db.commit()
    return await get_config_detail(db)


async def test_config(db: AsyncSession) -> EquipmentInspectionFeishuConfigTestResult:
    config = await get_effective_config(db)
    row = await _get_config_row(db)
    checked_at = datetime.now(UTC)

    if not config.app_id or not config.app_secret or not config.app_token:
        raise AppException(
            message="请先完整配置 App ID、App Secret 与多维表格 App Token"
        )
    if row is not None and row.app_secret and not config.app_secret:
        raise AppException(
            message=(
                "已保存的 App Secret 无法解密（加密密钥已轮换），"
                "请重新输入 App Secret 并保存后再测试连接"
            ),
            status_code=400,
        )

    try:
        client = BitableClient(
            app_token=config.app_token,
            app_id=config.app_id,
            app_secret=config.app_secret,
        )
        tables = await client.list_tables()
        if row is not None:
            row.last_test_status = "success"
            row.last_test_error = None
            row.last_tested_at = checked_at
            await db.commit()
        return EquipmentInspectionFeishuConfigTestResult(
            success=True,
            table_count=len(tables),
            message=f"连接成功，读取到 {len(tables)} 张子表",
        )
    except Exception as exc:
        # 连接测试失败按业务结果记录并返回，不上升为接口错误
        detail = _sanitize_feishu_error_message(str(exc))
        logger.warning("设备巡检飞书连接测试失败：%s", detail)
        if row is not None:
            row.last_test_status = "failed"
            row.last_test_error = detail
            row.last_tested_at = checked_at
            await db.commit()
        return EquipmentInspectionFeishuConfigTestResult(
            success=False, table_count=0, message=detail
        )
