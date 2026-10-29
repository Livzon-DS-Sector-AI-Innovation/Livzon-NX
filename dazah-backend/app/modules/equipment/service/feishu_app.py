"""设备模块飞书自建应用服务。

应用凭据登记一次、多车间复用（App Secret 加密存储、永不回显明文）。
车间巡检镜像配置通过 ``feishu_app_id`` 引用；仍被引用的应用删除时阻断。
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm.encryption import decrypt_api_key, encrypt_api_key, mask_api_key
from app.core.llm.exceptions import LLMConfigError
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.schemas.inspection import (
    FeishuAppCreateRequest,
    FeishuAppSummary,
    FeishuAppUpdateRequest,
)

logger = logging.getLogger(__name__)


def decrypt_app_secret(encrypted: str | None) -> str:
    """解密应用 Secret；密钥轮换导致解密失败时返回空串。

    返回空串而非抛错，保证配置读取可用；用户在应用管理中重新保存
    Secret 即可覆盖损坏的存量密文。
    """
    if not encrypted:
        return ""
    try:
        return decrypt_api_key(encrypted)
    except LLMConfigError:
        logger.warning("飞书应用 App Secret 解密失败（加密密钥已轮换），需重新保存")
        return ""


async def get_app_by_id(
    db: AsyncSession, app_uuid: UUID
) -> EquipmentFeishuApp | None:
    result = await db.execute(
        select(EquipmentFeishuApp).where(
            EquipmentFeishuApp.id == app_uuid,
            EquipmentFeishuApp.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalars().first()


async def get_app_by_app_id(
    db: AsyncSession, app_id: str
) -> EquipmentFeishuApp | None:
    result = await db.execute(
        select(EquipmentFeishuApp).where(
            EquipmentFeishuApp.app_id == app_id,
            EquipmentFeishuApp.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalars().first()


async def _usage_workshops(db: AsyncSession) -> dict[UUID, list[str]]:
    """引用各应用的未删除车间配置（应用管理区与删除阻断共用）。"""
    rows = (
        await db.execute(
            select(
                EquipmentInspectionFeishuConfig.feishu_app_id,
                EquipmentInspectionFeishuConfig.workshop_code,
            ).where(
                EquipmentInspectionFeishuConfig.is_deleted == False,  # noqa: E712
                EquipmentInspectionFeishuConfig.feishu_app_id.is_not(None),
            )
        )
    ).all()
    usage: dict[UUID, list[str]] = {}
    for app_uuid, workshop_code in rows:
        usage.setdefault(app_uuid, []).append(workshop_code)
    return usage


def _summary(
    app: EquipmentFeishuApp, in_use_workshops: list[str]
) -> FeishuAppSummary:
    secret = decrypt_app_secret(app.app_secret)
    return FeishuAppSummary(
        id=app.id,
        name=app.name,
        app_id=app.app_id,
        app_secret_masked=mask_api_key(secret) if secret else "",
        app_secret_configured=bool(secret),
        in_use_workshops=sorted(in_use_workshops),
        created_at=app.created_at,
    )


async def list_apps(db: AsyncSession) -> list[FeishuAppSummary]:
    """应用清单（下拉数据源与应用管理区共用）。"""
    apps = (
        await db.execute(
            select(EquipmentFeishuApp)
            .where(EquipmentFeishuApp.is_deleted == False)  # noqa: E712
            .order_by(EquipmentFeishuApp.created_at, EquipmentFeishuApp.id)
        )
    ).scalars().all()
    usage = await _usage_workshops(db)
    return [_summary(app, usage.get(app.id, [])) for app in apps]


async def create_app(
    db: AsyncSession, data: FeishuAppCreateRequest
) -> FeishuAppSummary:
    name = data.name.strip()
    app_id = data.app_id.strip()
    secret = data.app_secret.strip()
    if not name or not app_id or not secret:
        raise AppException(message="请完整填写应用名称、App ID 与 App Secret")
    existing = await get_app_by_app_id(db, app_id)
    if existing is not None:
        raise AppException(
            message=f"App ID 已登记（{existing.name}），请直接选择或修改原应用"
        )
    row = EquipmentFeishuApp(
        name=name, app_id=app_id, app_secret=encrypt_api_key(secret)
    )
    db.add(row)
    await db.commit()
    return _summary(row, [])


async def update_app(
    db: AsyncSession, app_uuid: UUID, data: FeishuAppUpdateRequest
) -> FeishuAppSummary:
    row = await get_app_by_id(db, app_uuid)
    if row is None:
        raise AppException(message="应用不存在或已删除", status_code=404)

    submitted_secret = (data.app_secret or "").strip()
    current_secret = decrypt_app_secret(row.app_secret)
    # 掩码回传不当作新密钥（前端未修改 Secret 时可能原样带回掩码）
    if submitted_secret and submitted_secret != mask_api_key(current_secret):
        row.app_secret = encrypt_api_key(submitted_secret)

    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise AppException(message="应用名称不能为空")
        row.name = name

    await db.commit()
    usage = await _usage_workshops(db)
    return _summary(row, usage.get(row.id, []))


async def delete_app(db: AsyncSession, app_uuid: UUID) -> None:
    row = await get_app_by_id(db, app_uuid)
    if row is None:
        raise AppException(message="应用不存在或已删除", status_code=404)
    usage = await _usage_workshops(db)
    in_use = usage.get(row.id, [])
    if in_use:
        raise AppException(
            message=(
                f"应用仍被车间配置引用（{'、'.join(in_use)}），"
                "请先在这些车间改用其他应用或清空配置"
            )
        )
    row.is_deleted = True
    await db.commit()
