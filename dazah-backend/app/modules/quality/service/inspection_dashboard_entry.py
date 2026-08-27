"""Inspection Feishu pages service - dashboard public entry points.

Public dashboard data functions for each product series trend dashboard.
Each function wraps ``_get_finished_dashboard_data`` with the appropriate
configuration constants.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.service.inspection_dashboard_calc import (
    _get_finished_dashboard_data,
)
from app.modules.quality.service.inspection_dashboard_config import (
    BBAS_DASHBOARD_DEFAULT_ENTITY_CODE,
    BBAS_DASHBOARD_ENTITY_CONFIGS,
    DLS_DASHBOARD_DEFAULT_ENTITY_CODE,
    DLS_DASHBOARD_ENTITY_CONFIGS,
    DLS_DASHBOARD_OOT_PRODUCT_CODE,
    FORMULATIONS_DASHBOARD_DEFAULT_ENTITY_CODE,
    FORMULATIONS_DASHBOARD_ENTITY_CONFIGS,
    LFT_DASHBOARD_DEFAULT_ENTITY_CODE,
    LFT_DASHBOARD_ENTITY_CONFIGS,
    LFT_DASHBOARD_OOT_PRODUCT_CODES,
    LKMS_VET_DASHBOARD_ENTITY_CODE,
    LKMS_VET_DASHBOARD_METRIC_CONFIGS,
    LKMS_VET_DASHBOARD_OOT_PRODUCT_CODE,
    LKMS_VET_DASHBOARD_SOURCE_LABEL,
    MPA_DASHBOARD_DEFAULT_ENTITY_CODE,
    MPA_DASHBOARD_ENTITY_CONFIGS,
    MPA_DASHBOARD_OOT_PRODUCT_CODES,
    MVT_DASHBOARD_ENTITY_CODE,
    MVT_DASHBOARD_METRIC_CONFIGS,
    MVT_DASHBOARD_OOT_PRODUCT_CODE,
    MVT_DASHBOARD_SOURCE_LABEL,
    TRYPTOPHAN_DASHBOARD_DEFAULT_ENTITY_CODE,
    TRYPTOPHAN_DASHBOARD_ENTITY_CONFIGS,
    WATER_DASHBOARD_DEFAULT_ENTITY_CODE,
    WATER_DASHBOARD_ENTITY_CONFIGS,
)

logger = logging.getLogger(__name__)


async def get_mpa_dashboard_data(
    db: AsyncSession,
    *,
    source_entity_code: str = MPA_DASHBOARD_DEFAULT_ENTITY_CODE,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    config = MPA_DASHBOARD_ENTITY_CONFIGS.get(source_entity_code)
    if config is None:
        raise AppException(message=f"不支持的霉酚酸仪表盘数据源: {source_entity_code}")

    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=source_entity_code,
        source_label=str(config["source_label"]),
        metric_configs=tuple(config["metric_configs"]),
        oot_product_code=MPA_DASHBOARD_OOT_PRODUCT_CODES.get(source_entity_code),
    )


async def get_mvt_dashboard_data(
    db: AsyncSession,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=MVT_DASHBOARD_ENTITY_CODE,
        source_label=MVT_DASHBOARD_SOURCE_LABEL,
        metric_configs=MVT_DASHBOARD_METRIC_CONFIGS,
        oot_product_code=MVT_DASHBOARD_OOT_PRODUCT_CODE,
    )


async def get_lft_dashboard_data(
    db: AsyncSession,
    *,
    source_entity_code: str = LFT_DASHBOARD_DEFAULT_ENTITY_CODE,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    config = LFT_DASHBOARD_ENTITY_CONFIGS.get(source_entity_code)
    if config is None:
        raise AppException(
            message=f"不支持的洛伐他汀仪表盘数据源: {source_entity_code}"
        )

    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=source_entity_code,
        source_label=str(config["source_label"]),
        metric_configs=tuple(config["metric_configs"]),
        oot_product_code=LFT_DASHBOARD_OOT_PRODUCT_CODES.get(source_entity_code),
    )


async def get_dls_dashboard_data(
    db: AsyncSession,
    *,
    source_entity_code: str = DLS_DASHBOARD_DEFAULT_ENTITY_CODE,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    config = DLS_DASHBOARD_ENTITY_CONFIGS.get(source_entity_code)
    if config is None:
        raise AppException(
            message=f"不支持的多拉菌素仪表盘数据源: {source_entity_code}"
        )

    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=source_entity_code,
        source_label=str(config["source_label"]),
        metric_configs=tuple(config["metric_configs"]),
        oot_product_code=DLS_DASHBOARD_OOT_PRODUCT_CODE,
    )


async def get_lkms_dashboard_data(
    db: AsyncSession,
    *,
    source_entity_code: str = LKMS_VET_DASHBOARD_ENTITY_CODE,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    if source_entity_code != LKMS_VET_DASHBOARD_ENTITY_CODE:
        raise AppException(
            message=f"不支持的林可霉素仪表盘数据源: {source_entity_code}"
        )

    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=source_entity_code,
        source_label=LKMS_VET_DASHBOARD_SOURCE_LABEL,
        metric_configs=LKMS_VET_DASHBOARD_METRIC_CONFIGS,
        oot_product_code=LKMS_VET_DASHBOARD_OOT_PRODUCT_CODE,
    )


async def get_bbas_dashboard_data(
    db: AsyncSession,
    *,
    source_entity_code: str = BBAS_DASHBOARD_DEFAULT_ENTITY_CODE,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    config = BBAS_DASHBOARD_ENTITY_CONFIGS.get(source_entity_code)
    if config is None:
        raise AppException(
            message=f"不支持的苯丙氨酸仪表盘数据源: {source_entity_code}"
        )

    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=source_entity_code,
        source_label=str(config["source_label"]),
        metric_configs=tuple(config["metric_configs"]),
    )


async def get_tryptophan_dashboard_data(
    db: AsyncSession,
    *,
    source_entity_code: str = TRYPTOPHAN_DASHBOARD_DEFAULT_ENTITY_CODE,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    config = TRYPTOPHAN_DASHBOARD_ENTITY_CONFIGS.get(source_entity_code)
    if config is None:
        raise AppException(message=f"不支持的色氨酸仪表盘数据源: {source_entity_code}")

    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=source_entity_code,
        source_label=str(config["source_label"]),
        metric_configs=tuple(config["metric_configs"]),
    )


async def get_formulations_dashboard_data(
    db: AsyncSession,
    *,
    source_entity_code: str = FORMULATIONS_DASHBOARD_DEFAULT_ENTITY_CODE,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    config = FORMULATIONS_DASHBOARD_ENTITY_CONFIGS.get(source_entity_code)
    if config is None:
        raise AppException(message=f"不支持的预混剂仪表盘数据源: {source_entity_code}")

    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=source_entity_code,
        source_label=str(config["source_label"]),
        metric_configs=tuple(config["metric_configs"]),
    )


async def get_water_dashboard_data(
    db: AsyncSession,
    *,
    source_entity_code: str = WATER_DASHBOARD_DEFAULT_ENTITY_CODE,
    sender_user_open_id: str | None = None,
) -> dict[str, Any]:
    config = WATER_DASHBOARD_ENTITY_CONFIGS.get(source_entity_code)
    if config is None:
        raise AppException(message=f"不支持的纯化水仪表盘数据源: {source_entity_code}")

    return await _get_finished_dashboard_data(
        db,
        sender_user_open_id=sender_user_open_id,
        source_entity_code=source_entity_code,
        source_label=str(config["source_label"]),
        metric_configs=tuple(config["metric_configs"]),
    )
