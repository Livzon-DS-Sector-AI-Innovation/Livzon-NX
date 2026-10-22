"""设备模块飞书自建应用凭据库服务。

独立存放自建应用（名称 + App ID + App Secret 加密存储）；巡检镜像
配置通过 feishu_app_id 引用库内应用，凭据在应用库更新后对所有引用
它的车间配置即时生效。Secret 不回显明文，仅返回是否已配置。
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm.encryption import decrypt_api_key, encrypt_api_key
from app.core.llm.exceptions import LLMConfigError
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.schemas.inspection import (
    EquipmentFeishuAppCreateRequest,
    EquipmentFeishuAppItem,
    EquipmentFeishuAppUpdateRequest,
)

logger = logging.getLogger(__name__)


async def _get_app_row(db: AsyncSession, app_id: UUID) -> EquipmentFeishuApp | None:
    result = await db.execute(
        select(EquipmentFeishuApp).where(
            EquipmentFeishuApp.id == app_id,
            EquipmentFeishuApp.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalars().first()


def decrypt_app_secret(encrypted: str | None) -> str:
    """解密应用 Secret；密钥轮换导致解密失败时返回空串并告警。"""
    if not encrypted:
        return ""
    try:
        return decrypt_api_key(encrypted)
    except LLMConfigError:
        logger.warning("飞书自建应用 App Secret 解密失败（加密密钥已轮换），需重新保存")
        return ""


async def _referencing_workshops(db: AsyncSession, app_row_id: UUID) -> list[str]:
    rows = (
        await db.execute(
            select(EquipmentInspectionFeishuConfig.workshop_code).where(
                EquipmentInspectionFeishuConfig.feishu_app_id == app_row_id,
                EquipmentInspectionFeishuConfig.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().all()
    return sorted(set(rows))


async def list_apps(db: AsyncSession) -> list[EquipmentFeishuAppItem]:
    rows = (
        await db.execute(
            select(EquipmentFeishuApp).where(
                EquipmentFeishuApp.is_deleted == False  # noqa: E712
            )
        )
    ).scalars().all()
    items = []
    for row in rows:
        items.append(
            EquipmentFeishuAppItem(
                id=row.id,
                name=row.name,
                app_id=row.app_id,
                app_secret_configured=bool(decrypt_app_secret(row.app_secret)),
                referenced_workshops=await _referencing_workshops(db, row.id),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return items


async def create_app(
    db: AsyncSession, data: EquipmentFeishuAppCreateRequest
) -> EquipmentFeishuAppItem:
    app_id = data.app_id.strip()
    name = data.name.strip()
    if not name or not app_id:
        raise AppException(message="应用名称与 App ID 不能为空")
    duplicate = (
        await db.execute(
            select(EquipmentFeishuApp).where(
                EquipmentFeishuApp.app_id == app_id,
                EquipmentFeishuApp.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if duplicate is not None:
        raise AppException(message=f"App ID {app_id} 已存在于应用库（{duplicate.name}）")
    row = EquipmentFeishuApp(
        name=name,
        app_id=app_id,
        app_secret=encrypt_api_key(data.app_secret.strip()),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return EquipmentFeishuAppItem(
        id=row.id,
        name=row.name,
        app_id=row.app_id,
        app_secret_configured=True,
        referenced_workshops=[],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def update_app(
    db: AsyncSession, app_row_id: UUID, data: EquipmentFeishuAppUpdateRequest
) -> EquipmentFeishuAppItem:
    row = await _get_app_row(db, app_row_id)
    if row is None:
        raise AppException(message="应用不存在或已删除", status_code=404)
    name = data.name.strip()
    app_id = data.app_id.strip()
    if not name or not app_id:
        raise AppException(message="应用名称与 App ID 不能为空")
    duplicate = (
        await db.execute(
            select(EquipmentFeishuApp).where(
                EquipmentFeishuApp.app_id == app_id,
                EquipmentFeishuApp.id != app_row_id,
                EquipmentFeishuApp.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if duplicate is not None:
        raise AppException(message=f"App ID {app_id} 已存在于应用库（{duplicate.name}）")
    row.name = name
    row.app_id = app_id
    submitted_secret = (data.app_secret or "").strip()
    if submitted_secret:
        row.app_secret = encrypt_api_key(submitted_secret)
    await db.commit()
    await db.refresh(row)
    return EquipmentFeishuAppItem(
        id=row.id,
        name=row.name,
        app_id=row.app_id,
        app_secret_configured=bool(decrypt_app_secret(row.app_secret)),
        referenced_workshops=await _referencing_workshops(db, row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def delete_app(db: AsyncSession, app_row_id: UUID) -> None:
    row = await _get_app_row(db, app_row_id)
    if row is None:
        raise AppException(message="应用不存在或已删除", status_code=404)
    referencing = await _referencing_workshops(db, app_row_id)
    if referencing:
        raise AppException(
            message=(
                "该应用仍被以下车间的巡检配置引用："
                f"{'、'.join(referencing)}；请先在这些配置中改用其他凭据"
            )
        )
    row.is_deleted = True
    await db.commit()
