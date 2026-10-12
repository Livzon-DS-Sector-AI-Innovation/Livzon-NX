"""设备巡检飞书镜像配置 ORM 模型。

单行配置：飞书应用凭据（App Secret 加密存储）与三张多维表格
引用。数据库行优先于 EQUIPMENT_FEISHU_* 环境变量回退。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class EquipmentInspectionFeishuConfig(BaseModel):
    """设备巡检飞书镜像配置（全模块仅一行）"""

    __tablename__ = "inspection_feishu_config"
    __table_args__ = {"schema": "equipment"}

    app_id: Mapped[str] = mapped_column(
        String(100), default="", comment="飞书应用 App ID"
    )
    app_secret: Mapped[str] = mapped_column(
        Text, default="", comment="飞书应用 App Secret（加密存储）"
    )
    app_token: Mapped[str] = mapped_column(
        String(200), default="", comment="多维表格 App Token（wiki 链接保存时已解析）"
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
