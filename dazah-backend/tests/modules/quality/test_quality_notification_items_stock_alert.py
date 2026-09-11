"""通知设置新增类型 items_stock_alert：播种、读写往返与配置加载。"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.schemas.notification_settings import (
    QualityNotificationRecipientItem,
    UpdateQualityNotificationSettingRequest,
)
from app.modules.quality.service import quality_notification_settings as ns

pytestmark = pytest.mark.anyio

_SETTINGS_DDL = """
    CREATE TABLE IF NOT EXISTS quality.quality_notification_settings (
        notification_type VARCHAR(50) NOT NULL,
        notification_label VARCHAR(100) NOT NULL,
        is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        lead_days INTEGER NOT NULL DEFAULT 3,
        repeat_interval_days INTEGER NOT NULL DEFAULT 1,
        send_time VARCHAR(5) NOT NULL DEFAULT '09:00',
        recipients JSON NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        id UUID PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by UUID NULL,
        updated_by UUID NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
        CONSTRAINT uq_quality_notification_settings_notification_type
            UNIQUE (notification_type)
    )
"""


@pytest.fixture(autouse=True)
async def _prepare(db_session: AsyncSession) -> Any:
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(text(_SETTINGS_DDL))
    # 仅清理本类型行，避免与其它通知设置测试文件全局 DELETE 同一张表造成串扰
    await db_session.execute(
        text(
            "DELETE FROM quality.quality_notification_settings "
            "WHERE notification_type = 'items_stock_alert'"
        )
    )
    await db_session.commit()
    yield
    await db_session.execute(
        text(
            "DELETE FROM quality.quality_notification_settings "
            "WHERE notification_type = 'items_stock_alert'"
        )
    )
    await db_session.commit()


async def test_items_stock_alert_roundtrip(db_session: AsyncSession) -> None:
    # 类型已注册标签 + 有效集合
    assert "items_stock_alert" in ns.QUALITY_NOTIFICATION_LABELS
    assert "items_stock_alert" in ns._VALID_NOTIFICATION_TYPES

    await ns.update_quality_notification_setting(
        db_session,
        "items_stock_alert",
        UpdateQualityNotificationSettingRequest(
            is_enabled=True,
            send_time="08:30",
            stock_recipients=[
                QualityNotificationRecipientItem(open_id="ou_1", name="张三")
            ],
            stock_warning_source="local_threshold",
            stock_header_template="库存告警 {count}",
            stock_footer_template="请到系统查看",
        ),
    )

    config = await ns.load_items_stock_alert_config(db_session)
    assert config.is_enabled is True
    assert config.send_time == "08:30"
    assert config.warning_source == "local_threshold"
    assert config.recipients[0]["name"] == "张三"
    assert config.header_template == "库存告警 {count}"

    # 读模型摊平
    items = await ns.list_quality_notification_settings(db_session)
    stock = next(
        i for i in items if i.notification_type == "items_stock_alert"
    )
    assert stock.stock_warning_source == "local_threshold"
    assert stock.stock_recipients[0].name == "张三"


async def test_items_stock_alert_default_when_missing(
    db_session: AsyncSession,
) -> None:
    await ns.ensure_quality_notification_settings(db_session)
    # 播种行默认关闭、默认口径 feishu
    config = await ns.load_items_stock_alert_config(db_session)
    assert config.is_enabled is False
    assert config.warning_source == "feishu"
    assert "{count}" in config.footer_template
