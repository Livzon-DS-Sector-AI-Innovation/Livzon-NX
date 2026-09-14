"""质量检验-物品管理 本地镜像 ORM 模型。

照搬仓储 material_page_snapshots / material_page_rows 模式：物品三张飞书
多维表格（qc_items_inventory / qc_items_inbound / qc_items_outbound）按
page_key 全量回填 + 增量双路单页同步到本地，列表读取改为读本地镜像，
避免每次实时拉飞书全表再内存过滤。

另含 QualityItemsStockAlertNotification：库存不足一键推送的幂等记录表，
按 (page_key, source_record_id, recipient_open_id, period_key) 唯一，防止
同一天/同一周期对同一物料重复推送。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel

# 物品管理三张镜像页的唯一键
ITEMS_MIRROR_PAGE_KEYS: tuple[str, ...] = (
    "qc_items_inventory",
    "qc_items_inbound",
    "qc_items_outbound",
)


class QualityItemsPageSnapshot(BaseModel):
    """物品镜像页快照（一个 page_key 一行，承载列结构与同步水线）。"""

    __tablename__ = "quality_items_page_snapshots"
    __table_args__ = (
        Index(
            "ix_quality_items_page_snapshots_page_key",
            "page_key",
            unique=True,
        ),
        {"schema": "quality"},
    )

    page_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="镜像页唯一键（=飞书实体编码）"
    )
    page_title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="页面标题"
    )
    table_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="飞书来源表名"
    )
    table_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="飞书 table_id"
    )
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="feishu_bitable",
        server_default="feishu_bitable",
        comment="快照来源",
    )
    columns: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="列结构快照（key/title/field_type/ui_type/editable）",
    )
    total_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="同步行数（增量轮次后以本地存量修正）",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次同步错误"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        comment="最近同步时间（增量水线）",
    )


class QualityItemsPageRow(BaseModel):
    """物品镜像行（cells 以飞书中文列名为键，值为前端可渲染结构）。"""

    __tablename__ = "quality_items_page_rows"
    __table_args__ = (
        Index("ix_quality_items_page_rows_page_id", "page_snapshot_id"),
        Index(
            "ix_quality_items_page_rows_source_record_id",
            "source_record_id",
        ),
        Index(
            "ix_quality_items_page_rows_page_record",
            "page_snapshot_id",
            "source_record_id",
            unique=True,
        ),
        {"schema": "quality"},
    )

    page_snapshot_id: Mapped[Any] = mapped_column(
        ForeignKey("quality.quality_items_page_snapshots.id"),
        nullable=False,
        comment="所属页快照 ID",
    )
    source_record_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="飞书记录 ID"
    )
    row_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="行序号",
    )
    cells: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="整行内容快照（中文列名为键，值已归一化）",
    )
    search_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="关键词检索串",
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        comment="最近同步时间",
    )


class QualityItemsStockAlertNotification(BaseModel):
    """库存不足一键推送幂等记录。

    period_key 为推送周期标识（默认当天 YYYY-MM-DD，定时按天幂等；
    手动推送可传本次触发的批次标识），同一 (物料, 接收人, 周期) 只推一次。
    """

    __tablename__ = "quality_items_stock_alert_notifications"
    __table_args__ = (
        Index(
            "ix_quality_items_stock_alert_notify_unique",
            "page_key",
            "source_record_id",
            "recipient_open_id",
            "period_key",
            unique=True,
        ),
        Index(
            "ix_quality_items_stock_alert_notify_period",
            "period_key",
        ),
        {"schema": "quality"},
    )

    page_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="镜像页键（qc_items_inventory）"
    )
    source_record_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="物料飞书记录 ID"
    )
    recipient_open_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="接收人 open_id（或姓名兜底键）"
    )
    recipient_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="接收人姓名快照"
    )
    period_key: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="推送周期标识（默认 YYYY-MM-DD）"
    )
    item_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="物料名称快照"
    )
    feishu_message_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="飞书消息 ID"
    )
    notification_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="sent",
        server_default="sent",
        comment="推送状态：sent/failed",
    )
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        comment="推送时间",
    )
