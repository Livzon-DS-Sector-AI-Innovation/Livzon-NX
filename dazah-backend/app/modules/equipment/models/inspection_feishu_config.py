"""设备巡检飞书镜像配置 ORM 模型。

按车间一行配置：引用的飞书自建应用（feishu_apps，App Secret 加密存储于
应用行）与三张多维表格引用。数据库行优先于 EQUIPMENT_FEISHU_* 环境变量
回退（环境变量仅作用于默认车间）。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel

if TYPE_CHECKING:
    from app.modules.equipment.models.feishu_app import EquipmentFeishuApp


class EquipmentInspectionFeishuConfig(BaseModel):
    """设备巡检飞书镜像配置（每个车间一行）"""

    __tablename__ = "inspection_feishu_config"
    __table_args__ = (
        # 部分唯一索引：未删除行内每个车间仅一行配置
        Index(
            "uq_inspection_feishu_config_workshop",
            "workshop_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "equipment"},
    )

    workshop_code: Mapped[str] = mapped_column(
        String(10),
        default="201-1",
        server_default="201-1",
        comment="车间代码（如 101-1 / 201-1）",
    )
    feishu_app_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("equipment.feishu_apps.id"),
        nullable=True,
        comment="关联的飞书自建应用（凭据存于 feishu_apps）",
    )
    app_token: Mapped[str] = mapped_column(
        String(200), default="", comment="多维表格 App Token（wiki 链接保存时已解析）"
    )
    base_url: Mapped[str] = mapped_column(
        String(500),
        default="",
        server_default="",
        comment="多维表格完整链接（含租户域名，用于飞书配置页直达）",
    )
    today_table_id: Mapped[str] = mapped_column(
        String(100), default="", comment="今日巡检表 ID"
    )
    history_table_id: Mapped[str] = mapped_column(
        String(100), default="", comment="设备历史巡检记录表 ID"
    )
    device_table_id: Mapped[str] = mapped_column(
        String(100), default="", comment="设备档案表 ID"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="启用镜像同步"
    )
    last_test_status: Mapped[str | None] = mapped_column(
        String(20), comment="最近连接测试：success / failed"
    )
    last_test_error: Mapped[str | None] = mapped_column(
        Text, comment="最近连接测试失败原因（脱敏）"
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最近连接测试时间"
    )

    feishu_app: Mapped[EquipmentFeishuApp | None] = relationship(
        "EquipmentFeishuApp", lazy="raise"
    )
