"""设备模块飞书自建应用 ORM 模型。

应用凭据独立登记（App Secret 加密存储），各车间巡检镜像配置通过
``inspection_feishu_config.feishu_app_id`` 引用；同一应用可被多个车间复用。
"""

from __future__ import annotations

from sqlalchemy import Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class EquipmentFeishuApp(BaseModel):
    """飞书自建应用凭据（登记一次，多车间复用）"""

    __tablename__ = "feishu_apps"
    __table_args__ = (
        # 部分唯一索引：未删除行内 App ID 唯一
        Index(
            "uq_feishu_apps_app_id",
            "app_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "equipment"},
    )

    name: Mapped[str] = mapped_column(
        String(100), comment="应用备注名（下拉展示用）"
    )
    app_id: Mapped[str] = mapped_column(
        String(100), comment="飞书应用 App ID"
    )
    app_secret: Mapped[str] = mapped_column(
        Text, default="", comment="飞书应用 App Secret（加密存储）"
    )
