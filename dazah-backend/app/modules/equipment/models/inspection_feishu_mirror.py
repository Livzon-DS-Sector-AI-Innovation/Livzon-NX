"""设备巡检飞书多维表格镜像 ORM 模型。

平台自持数据副本：岗位人员在飞书多维表格录入巡检记录，
后台按表镜像同步到本地（增量水位 + 每日全量对账），
页面只读展示，不回写飞书。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel

# 巡检检查项（7 项 × 上午/下午），镜像列与飞书列按关键字匹配
INSPECTION_ITEMS = ("清洁", "润滑", "紧固", "密封", "震动", "异声", "外表")


class EquipmentInspectionFeishuRecord(BaseModel):
    """巡检记录镜像（今日巡检 + 设备历史巡检记录）"""

    __tablename__ = "inspection_feishu_records"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "record_id",
            "is_deleted",
            name="uq_inspection_feishu_records_source_record",
        ),
        {"schema": "equipment"},
    )

    source: Mapped[str] = mapped_column(
        String(20), comment="来源表：today=今日巡检 / history=设备历史巡检记录"
    )
    record_id: Mapped[str] = mapped_column(String(64), comment="飞书记录ID")
    record_date: Mapped[date | None] = mapped_column(Date, comment="巡检日期")
    equipment_name: Mapped[str | None] = mapped_column(
        String(200), comment="设备名称"
    )
    equipment_no: Mapped[str | None] = mapped_column(
        String(100), comment="设备编号"
    )
    # 上午 7 项（√ / × / NULL=未填）
    am_clean: Mapped[str | None] = mapped_column(String(8))
    am_lubrication: Mapped[str | None] = mapped_column(String(8))
    am_fastening: Mapped[str | None] = mapped_column(String(8))
    am_sealing: Mapped[str | None] = mapped_column(String(8))
    am_vibration: Mapped[str | None] = mapped_column(String(8))
    am_sound: Mapped[str | None] = mapped_column(String(8))
    am_surface: Mapped[str | None] = mapped_column(String(8))
    # 下午 7 项
    pm_clean: Mapped[str | None] = mapped_column(String(8))
    pm_lubrication: Mapped[str | None] = mapped_column(String(8))
    pm_fastening: Mapped[str | None] = mapped_column(String(8))
    pm_sealing: Mapped[str | None] = mapped_column(String(8))
    pm_vibration: Mapped[str | None] = mapped_column(String(8))
    pm_sound: Mapped[str | None] = mapped_column(String(8))
    pm_surface: Mapped[str | None] = mapped_column(String(8))
    anomaly_note: Mapped[str | None] = mapped_column(
        Text, comment="其他异常情况描述"
    )
    process_status: Mapped[str | None] = mapped_column(
        String(20), comment="处理状态（历史表）：已拆分/有效记录"
    )
    has_abnormal: Mapped[bool] = mapped_column(
        default=False, comment="任一检查项为 ×"
    )
    raw_fields: Mapped[dict | None] = mapped_column(
        JSONB, comment="飞书原始字段（未识别列也保留）"
    )
    last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="飞书最后修改时间"
    )


class EquipmentInspectionFeishuDevice(BaseModel):
    """巡检设备清单镜像（设备档案表）"""

    __tablename__ = "inspection_feishu_devices"
    __table_args__ = (
        UniqueConstraint(
            "record_id", "is_deleted", name="uq_inspection_feishu_devices_record"
        ),
        {"schema": "equipment"},
    )

    record_id: Mapped[str] = mapped_column(String(64), comment="飞书记录ID")
    equipment_name: Mapped[str | None] = mapped_column(
        String(200), comment="设备名称"
    )
    equipment_no: Mapped[str | None] = mapped_column(
        String(100), comment="设备编号"
    )
    last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="飞书最后修改时间"
    )


class EquipmentInspectionFeishuSyncState(BaseModel):
    """镜像同步状态（每张源表一行）"""

    __tablename__ = "inspection_feishu_sync_state"
    __table_args__ = (
        UniqueConstraint(
            "table_key", "is_deleted", name="uq_inspection_feishu_sync_state_key"
        ),
        {"schema": "equipment"},
    )

    table_key: Mapped[str] = mapped_column(
        String(20), comment="today / history / devices"
    )
    total_rows: Mapped[int] = mapped_column(default=0, comment="镜像行数")
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="同步水位（飞书侧最后覆盖的修改时间）"
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最近一次同步执行时间"
    )
    last_status: Mapped[str | None] = mapped_column(
        String(20), comment="最近一次结果：success / failed"
    )
    last_message: Mapped[str | None] = mapped_column(
        Text, comment="最近一次结果说明（失败原因）"
    )
