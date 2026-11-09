"""备件采购建议与维修成本 schemas（方案C）."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG_FROM_ATTRIBUTES = ConfigDict(from_attributes=True)

SuggestionStatus = Literal[
    "suggested", "submitted", "partial", "done", "cancelled"
]


class PurchaseSuggestionItem(BaseModel):
    """采购建议条目（联备件信息）"""

    id: uuid.UUID = Field(..., description="建议ID")
    spare_part_id: uuid.UUID = Field(..., description="备件ID")
    spare_part_code: str | None = Field(default=None, description="备件编码")
    spare_part_name: str | None = Field(default=None, description="备件名称")
    specification: str | None = Field(default=None, description="规格型号")
    unit: str | None = Field(default=None, description="单位")
    workshop_code: str | None = Field(default=None, description="车间代码")
    default_supplier: str | None = Field(default=None, description="默认供应商")
    current_qty: int = Field(..., description="生成时库存")
    safety_qty: int = Field(..., description="安全线")
    suggest_qty: int = Field(..., description="建议采购数量")
    arrived_qty: int = Field(..., description="已到货数量")
    status: SuggestionStatus = Field(..., description="状态")
    source: str = Field(..., description="来源")
    purchase_request_id: str | None = Field(default=None, description="采购申请单ID")
    purchase_ref: str | None = Field(default=None, description="采购回执摘要")
    unit_price: float | None = Field(default=None, description="参考单价")
    submitted_at: str | None = Field(default=None, description="提交时间")
    created_at: str | None = Field(default=None, description="创建时间")


class PurchaseSuggestionQtyUpdate(BaseModel):
    """调整建议数量"""

    suggest_qty: int = Field(..., ge=1, le=99999, description="建议采购数量")


class PurchaseSuggestionSubmitRequest(BaseModel):
    """批量提交采购"""

    suggestion_ids: list[uuid.UUID] = Field(
        ..., min_length=1, max_length=50, description="建议ID列表"
    )


class PurchaseSuggestionSubmitResult(BaseModel):
    """提交结果"""

    submitted: int = Field(..., description="成功提交条数")
    purchase_request_id: str | None = Field(
        default=None, description="采购申请单ID"
    )
    failed: list[dict[str, str]] = Field(
        default_factory=list, description="失败明细"
    )


class PurchaseSuggestionArrivalRequest(BaseModel):
    """登记到货"""

    arrived_qty: int = Field(..., ge=1, le=99999, description="到货数量")


class LaborRateCreate(BaseModel):
    """新增费率"""

    scope: Literal["role", "person"] = Field(..., description="范围")
    role_id: uuid.UUID | None = Field(default=None, description="设备角色ID")
    person_id: uuid.UUID | None = Field(default=None, description="人员用户ID")
    hourly_rate: float = Field(..., ge=0, le=100000, description="时薪（元/小时）")
    effective_from: dt.date | None = Field(default=None, description="生效日期")
    remark: str | None = Field(default=None, max_length=200, description="备注")


class LaborRateUpdate(BaseModel):
    """编辑费率"""

    hourly_rate: float | None = Field(default=None, ge=0, le=100000)
    effective_from: dt.date | None = Field(default=None)
    remark: str | None = Field(default=None, max_length=200)


class LaborRateItem(BaseModel):
    """费率条目"""

    id: uuid.UUID
    scope: str
    role_id: uuid.UUID | None
    person_id: uuid.UUID | None
    hourly_rate: float
    effective_from: str
    remark: str | None


class WorkOrderExternalCostUpdate(BaseModel):
    """补录外委费用"""

    external_cost: float | None = Field(default=None, ge=0, le=99999999)
    external_vendor: str | None = Field(default=None, max_length=100)


class CostReportItem(BaseModel):
    """成本报表条目"""

    label: str = Field(..., description="分组标签")
    orders: int = Field(..., description="工单数")
    spare_cost: float = Field(..., description="备件成本")
    labor_cost: float = Field(..., description="工时成本")
    external_cost: float = Field(..., description="外委成本")
    total_cost: float = Field(..., description="合计")


class CostReportResponse(BaseModel):
    """成本报表"""

    month: str = Field(..., description="统计月份")
    workshop: str | None = Field(default=None, description="车间")
    group_by: str = Field(..., description="分组维度")
    totals: dict[str, float] = Field(..., description="汇总")
    top: list[dict[str, Any]] = Field(default_factory=list, description="TOP10")
