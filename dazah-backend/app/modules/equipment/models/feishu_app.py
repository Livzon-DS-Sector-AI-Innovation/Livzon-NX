"""设备模块飞书自建应用凭据库 ORM 模型。

独立存放飞书自建应用（名称 + App ID + App Secret 加密存储），
巡检镜像配置可引用库内应用，避免每个车间重复录入同一套凭据；
应用凭据更新后所有引用它的车间配置同步生效。
"""

from __future__ import annotations

from sqlalchemy import Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class EquipmentFeishuApp(BaseModel):
    """飞书自建应用凭据（每个应用一条记录）"""

    __tablename__ = "feishu_apps"
    __table_args__ = (
        # 部分唯一索引：未删除行内 App ID 唯一，删除后可重建
        Index(
            "uq_feishu_apps_app_id",
            "app_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "equipment"},
    )

    name: Mapped[str] = mapped_column(
        String(100), comment="应用名称（便于辨认，如：设备巡检同步应用）"
    )
    app_id: Mapped[str] = mapped_column(String(100), comment="飞书应用 App ID")
    app_secret: Mapped[str] = mapped_column(
        Text, comment="飞书应用 App Secret（加密存储）"
    )
