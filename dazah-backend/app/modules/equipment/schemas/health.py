"""设备健康档案与月度报告 schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

HealthGrade = Literal["G", "Y", "R"]

# ORM → Pydantic（model_validate(ORM 对象)）
MODEL_CONFIG_FROM_ATTRIBUTES = ConfigDict(from_attributes=True)


class HealthSnapshotResponse(BaseModel):
    """健康快照"""

    model_config = MODEL_CONFIG_FROM_ATTRIBUTES

    id: uuid.UUID = Field(..., description="快照ID")
    equipment_id: uuid.UUID = Field(..., description="设备ID")
    snapshot_date: date = Field(..., description="快照日期")
    score: float = Field(..., description="健康度评分 0-100")
    grade: HealthGrade = Field(..., description="分档：G绿/Y黄/R红")
    metrics: dict[str, Any] | None = Field(default=None, description="分项指标")


class HealthTrendResponse(BaseModel):
    """健康趋势（近 N 日）"""

    equipment_id: uuid.UUID = Field(..., description="设备ID")
    snapshots: list[HealthSnapshotResponse] = Field(
        default_factory=list, description="按日期升序的快照列表"
    )


class HealthBoardItem(BaseModel):
    """健康度榜单条目"""

    equipment_id: uuid.UUID = Field(..., description="设备ID")
    equipment_no: str | None = Field(default=None, description="设备编号")
    equipment_name: str | None = Field(default=None, description="设备名称")
    workshop_code: str | None = Field(default=None, description="车间代码")
    score: float = Field(..., description="健康度评分")
    grade: HealthGrade = Field(..., description="分档")
    metrics: dict[str, Any] | None = Field(default=None, description="分项指标")
    snapshot_date: str | None = Field(default=None, description="快照日期")


class HealthBoardResponse(BaseModel):
    """健康度榜单"""

    items: list[HealthBoardItem] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict, description="分档汇总 {G,Y,R,total}"
    )


class RepairProfileResponse(BaseModel):
    """维修病历"""

    model_config = MODEL_CONFIG_FROM_ATTRIBUTES

    # 无落库记录时接口返回只读计算的瞬态档案，此时无持久化 id
    id: uuid.UUID | None = Field(default=None, description="病历ID")
    equipment_id: uuid.UUID = Field(..., description="设备ID")
    total_orders: int = Field(..., description="累计工单数")
    total_faults: int = Field(..., description="累计故障维修数")
    total_downtime_min: int = Field(..., description="累计维修用时（分钟）")
    total_spare_cost: float = Field(..., description="累计备件费用")
    mtbf_days: float | None = Field(default=None, description="平均故障间隔（天）")
    last_3_faults: list[dict[str, Any]] | None = Field(
        default=None, description="最近 3 次故障摘要"
    )
    updated_at: datetime | None = Field(default=None, description="更新时间")


class MonthlyReportResponse(BaseModel):
    """月度健康报告"""

    model_config = MODEL_CONFIG_FROM_ATTRIBUTES

    id: uuid.UUID = Field(..., description="报告ID")
    report_month: str = Field(..., description="报告月份 YYYY-MM")
    metrics: dict[str, Any] | None = Field(default=None, description="聚合指标")
    content_md: str | None = Field(default=None, description="报告正文 Markdown")
    generated_at: datetime | None = Field(default=None, description="生成时间")


class MonthlyReportGenerateRequest(BaseModel):
    """生成月报请求"""

    report_month: str = Field(
        ...,
        pattern=r"^[0-9]{4}-[0-9]{2}$",
        description="报告月份 YYYY-MM",
    )
