"""Quality request and response schemas live here."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ─── LabelVerification Schemas ───


class LabelVerificationBase(BaseModel):
    """标签复核记录基础字段"""

    batch_number: str = Field(..., max_length=32, description="批号")
    product_name: str = Field(..., max_length=128, description="产品名称")
    production_date: date = Field(..., description="生产日期")
    expiry_date: date = Field(..., description="有效期至")

    total_barrels: int = Field(..., ge=1, description="总桶数")
    standard_barrels: int = Field(..., ge=0, description="整桶数")
    remainder_barrel: int = Field(..., ge=0, le=1, description="零头桶数（0或1）")
    standard_weight: float = Field(..., ge=0, description="整桶重量（kg）")
    remainder_weight: float = Field(..., ge=0, description="零头重量（kg）")
    total_weight: float = Field(..., ge=0, description="总重量（kg）")

    check_batch_number: bool = Field(..., description="批号对比结果")
    check_production_date: bool = Field(..., description="生产日期对比结果")
    check_expiry_date: bool = Field(..., description="有效期至对比结果")
    check_standard_barrels: bool = Field(..., description="整桶信息对比结果")
    check_remainder_barrel: bool = Field(..., description="零头信息对比结果")
    check_total_weight: bool = Field(..., description="总重量对比结果")
    check_all_barrels_identified: bool = Field(..., description="是否识别到每一桶")
    check_exception_handled: bool = Field(..., description="异常处理结果")

    result_status: str = Field(
        "全部一致", max_length=16, description="总体结论：全部一致/存在差异"
    )
    result_summary: str = Field(..., description="结论摘要")

    video_file_key: str = Field(..., max_length=256, description="视频文件 key")
    video_file_name: str | None = Field(None, max_length=256, description="视频文件名")
    video_frame_count: int | None = Field(None, ge=0, description="提取帧数")
    video_fps: float | None = Field(None, description="帧率")

    verification_date: date = Field(..., description="复核日期")
    verification_time: datetime = Field(..., description="复核时间")

    remarks: str | None = Field(None, description="备注")


class LabelVerificationCreate(LabelVerificationBase):
    """创建标签复核记录"""

    pass


class LabelVerificationUpdate(BaseModel):
    """更新标签复核记录"""

    product_name: str | None = Field(None, max_length=128)
    production_date: date | None = Field(None)
    expiry_date: date | None = Field(None)

    total_barrels: int | None = Field(None, ge=1)
    standard_barrels: int | None = Field(None, ge=0)
    remainder_barrel: int | None = Field(None, ge=0, le=1)
    standard_weight: float | None = Field(None, ge=0)
    remainder_weight: float | None = Field(None, ge=0)
    total_weight: float | None = Field(None, ge=0)

    check_batch_number: bool | None = Field(None)
    check_production_date: bool | None = Field(None)
    check_expiry_date: bool | None = Field(None)
    check_standard_barrels: bool | None = Field(None)
    check_remainder_barrel: bool | None = Field(None)
    check_total_weight: bool | None = Field(None)
    check_all_barrels_identified: bool | None = Field(None)
    check_exception_handled: bool | None = Field(None)

    result_status: str | None = Field(None, max_length=16)
    result_summary: str | None = Field(None)

    video_file_name: str | None = Field(None, max_length=256)
    video_frame_count: int | None = Field(None, ge=0)
    video_fps: float | None = Field(None)

    remarks: str | None = Field(None)


class LabelVerificationResponse(LabelVerificationBase):
    """标签复核记录响应"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LabelVerificationStatistics(BaseModel):
    """标签复核统计"""

    total: int = Field(..., description="总复核次数")
    all_match: int = Field(..., description="全部一致次数")
    has_difference: int = Field(..., description="存在差异次数")
    match_rate: float = Field(..., description="一致率（%）")
    today_count: int = Field(..., description="今日复核次数")
    this_week_count: int = Field(..., description="本周复核次数")
    this_month_count: int = Field(..., description="本月复核次数")
    by_batch: dict[str, int] = Field(
        default_factory=dict, description="按批号统计"
    )
