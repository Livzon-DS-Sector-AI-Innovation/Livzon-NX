"""Production Feishu sync models."""
from typing import Any

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ProductionFeishuConfig(BaseModel):
    __tablename__ = "production_feishu_configs"
    __table_args__ = ({"schema": "production"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="生产飞书配置", comment="配置名称"
    )
    product_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="关联产品（L-苯丙氨酸/洛伐他汀/美伐他汀）"
    )
    app_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书应用 App ID"
    )
    encrypted_app_secret: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="加密后的 App Secret"
    )
    bitable_app_token: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="多维表格 app_token"
    )
    table_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="发酵记录表 table_id"
    )
    sync_target: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="production_plan",
        server_default="production_plan",
        comment="同步目标: production_plan / fermentation_record / batch / production_record / material_balance",  # noqa: E501
    )
    field_mapping: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="自动发现的字段映射 {feishu_field_id: {name, type, db_column}}",
    )
    sync_table_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="动态创建的同步表名"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", comment="是否启用"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
