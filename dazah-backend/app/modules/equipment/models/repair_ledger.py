"""设备检修台账（飞书多维表格镜像）ORM 模型。

车间在飞书多维表格登记维修记录，后台按表镜像同步到本地
（增量水位 + 每日全量对账），页面只读展示与频次分析，
不回写飞书，也不与设备台账（equipments）做关联——
检修记录按表内「设备名称/型号」原文独立聚合。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel


class RepairFeishuConfig(BaseModel):
    """设备检修飞书镜像配置（每个车间一行）"""

    __tablename__ = "repair_feishu_config"
    __table_args__ = (
        # 部分唯一索引：未删除行内每个车间仅一行配置
        Index(
            "uq_repair_feishu_config_workshop",
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
    feishu_app_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.feishu_apps.id"),
        nullable=True,
        comment="关联的飞书自建应用（凭据存于 feishu_apps，与巡检共用应用登记）",
    )
    app_token: Mapped[str] = mapped_column(
        String(200), default="", comment="多维表格 App Token（保存链接时已解析）"
    )
    table_id: Mapped[str] = mapped_column(
        String(100), default="", comment="维修记录表 ID"
    )
    base_url: Mapped[str] = mapped_column(
        String(500),
        default="",
        server_default="",
        comment="多维表格完整链接（含租户域名，用于配置页直达）",
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

    feishu_app: Mapped[Any | None] = relationship(
        "EquipmentFeishuApp", foreign_keys=[feishu_app_id], lazy="selectin"
    )


class RepairRecord(BaseModel):
    """检修记录镜像（不关联设备台账，按原文展示与聚合）"""

    __tablename__ = "repair_records"
    __table_args__ = (
        # 部分唯一索引：未删除行内同车间的飞书记录唯一
        Index(
            "uq_repair_records_source_record",
            "workshop_code",
            "record_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_repair_records_workshop_date",
            "workshop_code",
            "repaired_at",
        ),
        {"schema": "equipment"},
    )

    workshop_code: Mapped[str] = mapped_column(
        String(10),
        default="201-1",
        server_default="201-1",
        comment="车间代码（如 101-1 / 201-1）",
    )
    record_id: Mapped[str] = mapped_column(String(64), comment="飞书记录ID")
    workshop_text: Mapped[str | None] = mapped_column(
        String(200), comment="车间及地点（飞书原文）"
    )
    equipment_text: Mapped[str | None] = mapped_column(
        String(200), comment="设备名称/型号（飞书原文，频次聚合键）"
    )
    repaired_at: Mapped[date | None] = mapped_column(Date, comment="维修日期")
    person_text: Mapped[str | None] = mapped_column(
        String(500), comment="维修人员（人员/文本字段的原文）"
    )
    persons: Mapped[list[Any] | None] = mapped_column(
        JSONB,
        comment=(
            "维修人员结构化（[{name, open_id, avatar_url}]）；"
            "通讯录无权限或未匹配到时为空，展示回退 person_text"
        ),
    )
    fault_desc: Mapped[str | None] = mapped_column(Text, comment="故障描述/原因")
    spare_parts: Mapped[str | None] = mapped_column(Text, comment="更换备件")
    result: Mapped[str | None] = mapped_column(
        String(100), comment="维修后状态（原文）"
    )
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")
    raw_fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, comment="飞书原始字段（未识别列也保留）"
    )
    last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="飞书最后修改时间"
    )


class RepairSyncState(BaseModel):
    """检修镜像同步状态（每车间一行）"""

    __tablename__ = "repair_sync_state"
    __table_args__ = (
        # 部分唯一索引：未删除行内每个车间仅一行状态
        Index(
            "uq_repair_sync_state_workshop",
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
