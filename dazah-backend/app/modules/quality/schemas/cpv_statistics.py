"""CPV Statistics schemas."""

from pydantic import BaseModel, Field


class CpvStatisticsRequest(BaseModel):
    """统计请求参数"""

    data_type: str = Field(default="CPP", description="数据类型: CPP/CQA")
    parameter_id: str | None = Field(default=None, description="参数ID")
    batch_no: str | None = Field(default=None, description="批号")
    start_date: str | None = Field(default=None, description="开始日期")
    end_date: str | None = Field(default=None, description="结束日期")


class CpvStatisticsResponse(BaseModel):
    """统计响应"""

    total_batches: int = Field(..., description="批次总数")
    min_value: float = Field(..., description="最小值")
    max_value: float = Field(..., description="最大值")
    avg_value: float = Field(..., description="平均值")
    std_dev: float = Field(..., description="标准差")
    cpk_value: float = Field(..., description="CPK值")
    abnormal_count: int = Field(..., description="异常批次数")
    lower_limit: float = Field(..., description="控制下限")
    upper_limit: float = Field(..., description="控制上限")


class CpvTrendItem(BaseModel):
    """趋势数据项"""

    batch_no: str
    production_date: str
    value: float
    lower_limit: float
    upper_limit: float
    is_abnormal: bool


class CpvTrendResponse(BaseModel):
    """趋势响应"""

    parameter_name: str
    parameter_unit: str | None
    items: list[CpvTrendItem]
