"""设备巡检飞书镜像配置服务。

配置按车间一行，凭据引用 ``feishu_apps`` 应用实体（登记一次、多车间复用，
App Secret 加密存储于应用行）。来源优先级：数据库该车间行 →
EQUIPMENT_FEISHU_* 环境变量回退（仅作用于默认车间 201-1，兼容存量
单套配置）。车间行一旦保存即视为权威；未配置的非默认车间视为未启用。
知识库（/wiki/）链接在保存时解析为真实多维表格 App Token，镜像同步
运行时不再解析。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.llm.encryption import encrypt_api_key, mask_api_key
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.schemas.inspection import (
    EquipmentInspectionFeishuConfigDetail,
    EquipmentInspectionFeishuConfigTestResult,
    EquipmentInspectionFeishuConfigUpdateRequest,
)
from app.modules.equipment.service import feishu_app as feishu_app_service
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

# 环境变量回退仅作用于默认车间：存量单套 EQUIPMENT_FEISHU_* 配置
# 属于 201一车间，不能让其他未配置车间复用同一套表格
DEFAULT_WORKSHOP_CODE = "201-1"

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
    base_url: str
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


async def _get_config_row(
    db: AsyncSession, workshop_code: str
) -> EquipmentInspectionFeishuConfig | None:
    result = await db.execute(
        select(EquipmentInspectionFeishuConfig)
        .options(selectinload(EquipmentInspectionFeishuConfig.feishu_app))
        .where(
            EquipmentInspectionFeishuConfig.workshop_code == workshop_code,
            EquipmentInspectionFeishuConfig.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalars().first()


def _empty_config() -> InspectionFeishuEffectiveConfig:
    """未配置的非默认车间：视为未启用，页面展示空态。"""
    return InspectionFeishuEffectiveConfig(
        app_id="",
        app_secret="",
        app_token="",
        base_url="",
        today_table_id="",
        history_table_id="",
        device_table_id="",
        is_enabled=False,
        source=CONFIG_SOURCE_ENVIRONMENT,
    )


def _env_config() -> InspectionFeishuEffectiveConfig:
    return InspectionFeishuEffectiveConfig(
        app_id=settings.EQUIPMENT_FEISHU_APP_ID.strip(),
        app_secret=settings.EQUIPMENT_FEISHU_APP_SECRET.strip(),
        app_token=settings.EQUIPMENT_FEISHU_BITABLE_APP_TOKEN.strip(),
        base_url="",
        today_table_id=settings.EQUIPMENT_FEISHU_BITABLE_TODAY_TABLE_ID.strip(),
        history_table_id=settings.EQUIPMENT_FEISHU_BITABLE_HISTORY_TABLE_ID.strip(),
        device_table_id=settings.EQUIPMENT_FEISHU_BITABLE_DEVICE_TABLE_ID.strip(),
        is_enabled=True,
        source=CONFIG_SOURCE_ENVIRONMENT,
    )


def _row_config(
    row: EquipmentInspectionFeishuConfig,
) -> InspectionFeishuEffectiveConfig:
    app = row.feishu_app
    return InspectionFeishuEffectiveConfig(
        app_id=(app.app_id if app is not None else "").strip(),
        app_secret=(
            feishu_app_service.decrypt_app_secret(app.app_secret)
            if app is not None
            else ""
        ),
        app_token=(row.app_token or "").strip(),
        base_url=(row.base_url or "").strip(),
        today_table_id=(row.today_table_id or "").strip(),
        history_table_id=(row.history_table_id or "").strip(),
        device_table_id=(row.device_table_id or "").strip(),
        is_enabled=row.is_enabled,
        source=CONFIG_SOURCE_DATABASE,
    )


async def get_effective_config(
    db: AsyncSession, workshop_code: str
) -> InspectionFeishuEffectiveConfig:
    """该车间数据库行优先；默认车间无行时回退环境变量，其余车间视为未配置。"""
    row = await _get_config_row(db, workshop_code)
    if row is not None:
        return _row_config(row)
    if workshop_code == DEFAULT_WORKSHOP_CODE:
        return _env_config()
    return _empty_config()


async def is_mirror_enabled(db: AsyncSession, workshop_code: str) -> bool:
    return (await get_effective_config(db, workshop_code)).enabled


async def list_enabled_workshops(db: AsyncSession) -> list[str]:
    """已启用镜像同步的车间代码（调度器按此生成同步任务）。"""
    rows = (
        await db.execute(
            select(EquipmentInspectionFeishuConfig.workshop_code).where(
                EquipmentInspectionFeishuConfig.is_deleted == False  # noqa: E712
            )
        )
    ).scalars().all()
    workshops = set(rows)
    # 默认车间无行时仍检查环境变量回退
    workshops.add(DEFAULT_WORKSHOP_CODE)
    enabled = [code for code in sorted(workshops)
               if await is_mirror_enabled(db, code)]
    return enabled


async def get_config_detail(
    db: AsyncSession, workshop_code: str
) -> EquipmentInspectionFeishuConfigDetail:
    row = await _get_config_row(db, workshop_code)
    config = _row_config(row) if row else (
        _env_config() if workshop_code == DEFAULT_WORKSHOP_CODE else _empty_config()
    )
    return EquipmentInspectionFeishuConfigDetail(
        workshop_code=workshop_code,
        feishu_app_id=row.feishu_app_id if row is not None else None,
        app_name=(row.feishu_app.name if row is not None and row.feishu_app else ""),
        app_id=config.app_id,
        app_secret_masked=mask_api_key(config.app_secret) if config.app_secret else "",
        app_secret_configured=bool(config.app_secret),
        app_token=config.app_token,
        base_url=config.base_url,
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


def _normalized_base_url(value: str) -> str:
    """完整链接仅接受 https 直链；粘贴 base/wiki 链接以外的内容时报错。"""
    stripped = value.strip()
    if not stripped:
        return ""
    if not stripped.startswith("https://"):
        raise AppException(message="多维表格完整链接需以 https:// 开头")
    return stripped[:500]


async def list_config_details(
    db: AsyncSession,
) -> list[EquipmentInspectionFeishuConfigDetail]:
    """飞书配置页清单：全部已配置车间 + 默认车间（环境变量回退）。

    前端结合车间常量表补齐未配置车间的空态行。
    """
    rows = (
        await db.execute(
            select(EquipmentInspectionFeishuConfig).where(
                EquipmentInspectionFeishuConfig.is_deleted.is_(False)
            )
        )
    ).scalars().all()
    workshops = [row.workshop_code for row in rows]
    if DEFAULT_WORKSHOP_CODE not in workshops:
        workshops.append(DEFAULT_WORKSHOP_CODE)
    return [
        await get_config_detail(db, workshop_code)
        for workshop_code in sorted(set(workshops))
    ]


def _normalized_table_id(value: str) -> str:
    """兼容直接粘贴子表链接 / 带 table 参数的 URL / 裸 table ID。"""
    return normalize_table_id(value) or ""


def _is_view_id(value: str) -> bool:
    """飞书视图 ID 以 vew 开头；数据表 ID 以 tbl 开头。"""
    return value.startswith("vew")


async def _resolve_view_table_ids(
    client: BitableClient, table_ids: dict[str, str]
) -> dict[str, str]:
    """把误填的视图 ID（vew…）解析为所属数据表 ID（tbl…）。

    遍历多维表格的数据表及其视图定位视图所属表；解析不到的保持原值，
    由调用方决定如何提示。
    """
    pending = {value for value in table_ids.values() if _is_view_id(value)}
    if not pending:
        return table_ids
    resolved: dict[str, str] = {}
    for table in await client.list_tables():
        table_id = table.get("table_id")
        if not table_id:
            continue
        page_token: str | None = None
        while True:
            params: dict[str, object] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = await client.client.request(
                "GET",
                f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/views",
                params=params,
            )
            for view in data.get("items") or []:
                view_id = view.get("view_id") if isinstance(view, dict) else None
                if view_id in pending:
                    resolved[view_id] = table_id
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        if not pending - set(resolved):
            break
    return {key: resolved.get(value, value) for key, value in table_ids.items()}


async def _resolve_view_ids_or_raise(
    table_ids: dict[str, str], *, app_id: str, app_secret: str, app_token: str
) -> dict[str, str]:
    """保存时自动纠正视图 ID（vew…）为数据表 ID（tbl…）。

    误填视图 ID 会导致同步报 WrongTableId；用已配置的应用凭据查询
    视图所属数据表并替换，无法解析时给出可操作的错误。
    """
    if not any(_is_view_id(value) for value in table_ids.values()):
        return table_ids
    if not (app_id and app_secret and app_token):
        raise AppException(
            message=(
                "Table ID 以 vew 开头是视图 ID，"
                "自动解析需完整填写 App ID、App Secret 与 App Token"
            )
        )
    client = BitableClient(app_token=app_token, app_id=app_id, app_secret=app_secret)
    try:
        resolved = await _resolve_view_table_ids(client, table_ids)
    except AppException:
        raise
    except Exception as exc:
        raise AppException(
            message=f"视图 ID 自动解析失败：{_sanitize_feishu_error_message(str(exc))}"
        ) from exc
    if any(_is_view_id(value) for value in resolved.values()):
        raise AppException(
            message=(
                "Table ID 以 vew 开头是视图 ID，且未能在该多维表格中解析到所属数据表；"
                "请改用数据表 ID（多维表格链接中 table= 参数，以 tbl 开头）"
            )
        )
    return resolved


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


async def _resolve_target_app(
    db: AsyncSession, data: EquipmentInspectionFeishuConfigUpdateRequest
) -> EquipmentFeishuApp:
    """解析本次配置指向的应用：下拉选择优先，其次手输。

    手输的 App ID 已登记则直接关联（掩码回传不当作新密钥，附带的
    Secret 与已登记值不同时引导走应用管理）；未登记则连同 Secret
    登记为可复用的新应用。
    """
    if data.feishu_app_id is not None:
        app = await feishu_app_service.get_app_by_id(db, data.feishu_app_id)
        if app is None:
            raise AppException(message="所选应用不存在或已删除", status_code=404)
        return app

    manual_app_id = data.app_id.strip()
    submitted_secret = (data.app_secret or "").strip()
    if not manual_app_id:
        raise AppException(
            message="请选择已登记应用，或填写新应用的 App ID 与 App Secret"
        )
    app = await feishu_app_service.get_app_by_app_id(db, manual_app_id)
    if app is not None:
        stored_secret = feishu_app_service.decrypt_app_secret(app.app_secret)
        if submitted_secret and submitted_secret != mask_api_key(stored_secret):
            raise AppException(
                message=(
                    f"该 App ID 已登记（{app.name}），请直接下拉选择；"
                    "如需更换密钥请在应用管理中修改"
                )
            )
        return app

    if not submitted_secret:
        raise AppException(
            message="新 App ID 需同时填写 App Secret（保存后登记为可复用应用）"
        )
    app = EquipmentFeishuApp(
        name=(data.app_name.strip() or manual_app_id),
        app_id=manual_app_id,
        app_secret=encrypt_api_key(submitted_secret),
    )
    db.add(app)
    await db.flush()
    return app


async def update_config(
    db: AsyncSession,
    workshop_code: str,
    data: EquipmentInspectionFeishuConfigUpdateRequest,
) -> EquipmentInspectionFeishuConfigDetail:
    row = await _get_config_row(db, workshop_code)
    app = await _resolve_target_app(db, data)
    current_secret = feishu_app_service.decrypt_app_secret(app.app_secret)

    app_token = await _resolve_app_token(
        app_id=app.app_id,
        app_secret=current_secret,
        raw_app_token=data.app_token.strip(),
    )
    if data.is_enabled and (not current_secret or not app_token):
        raise AppException(
            message="启用同步需选择已配置 Secret 的应用并填写多维表格 App Token"
        )

    if row is None:
        row = EquipmentInspectionFeishuConfig(workshop_code=workshop_code)
        db.add(row)
    row.feishu_app_id = app.id
    row.is_enabled = data.is_enabled
    row.app_token = app_token
    row.base_url = _normalized_base_url(data.base_url)
    table_ids = await _resolve_view_ids_or_raise(
        {
            "today_table_id": _normalized_table_id(data.today_table_id),
            "history_table_id": _normalized_table_id(data.history_table_id),
            "device_table_id": _normalized_table_id(data.device_table_id),
        },
        app_id=app.app_id,
        app_secret=current_secret,
        app_token=app_token,
    )
    row.today_table_id = table_ids["today_table_id"]
    row.history_table_id = table_ids["history_table_id"]
    row.device_table_id = table_ids["device_table_id"]

    await db.commit()
    return await get_config_detail(db, workshop_code)


async def test_config(
    db: AsyncSession, workshop_code: str
) -> EquipmentInspectionFeishuConfigTestResult:
    config = await get_effective_config(db, workshop_code)
    row = await _get_config_row(db, workshop_code)
    checked_at = datetime.now(UTC)

    if not config.app_id or not config.app_secret or not config.app_token:
        raise AppException(
            message="请先完整配置应用凭据与多维表格 App Token"
        )
    if (
        row is not None
        and row.feishu_app is not None
        and row.feishu_app.app_secret
        and not config.app_secret
    ):
        raise AppException(
            message=(
                "已保存的 App Secret 无法解密（加密密钥已轮换），"
                "请在飞书配置页应用管理中重新保存该应用的 Secret 后再测试连接"
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
