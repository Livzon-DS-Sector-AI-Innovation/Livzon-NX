"""Supplier qualification schemas (Feishu Bitable)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SupplierExpiryBucket = Literal["expired", "due_30", "due_60", "due_90"]
"""按截止日期划分的到期分桶（与 get_supplier_statistics 计数口径一致）。"""


class SupplierQualificationBase(BaseModel):
    """Shared supplier qualification fields."""

    supplier_name: str = Field(..., description="供应商名称")
    material_name: str | None = Field(default=None, description="物料名称")
    material_type: str | None = Field(default=None, description="物料类型")
    qualification_name: str = Field(..., description="资质名称")
    qualification_file: str | None = Field(default=None, description="资质文件")
    is_completed: bool = Field(default=False, description="是否完成")
    deadline: str | None = Field(default=None, description="截止日期")
    responsible_person: str | None = Field(default=None, description="负责人")
    responsible_users: list[dict[str, str]] | None = Field(
        default=None,
        description="负责人飞书成员对象 [{id: ou_…, name}]，写回成员字段用",
    )
    remark: str | None = Field(default=None, description="备注")


class CreateSupplierQualificationRequest(SupplierQualificationBase):
    """Create supplier qualification request."""

    pass


class UpdateSupplierQualificationRequest(BaseModel):
    """Update supplier qualification request."""

    supplier_name: str | None = None
    material_name: str | None = None
    material_type: str | None = None
    qualification_name: str | None = None
    qualification_file: str | None = None
    is_completed: bool | None = None
    deadline: str | None = None
    responsible_person: str | None = None
    responsible_users: list[dict[str, str]] | None = None
    remark: str | None = None


class SupplierQualificationOut(BaseModel):
    """Supplier qualification output (Feishu record)."""

    record_id: str
    supplier_name: str | None = None
    material_name: str | None = None
    material_type: str | None = None
    qualification_name: str | None = None
    qualification_file: str | None = None
    is_completed: bool = False
    deadline: str | None = None
    responsible_person: str | None = None
    responsible_users: list[dict[str, str]] | None = None
    groups: list[dict[str, str]] | None = None
    remark: str | None = None
    expiry_status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SupplierDashboardStatsOut(BaseModel):
    """Supplier dashboard statistics output."""

    total: int = 0
    completed: int = 0
    pending: int = 0
    completion_rate: float = 0
    expired_count: int = 0
    due_30_count: int = 0
    due_60_count: int = 0
    due_90_count: int = 0
    normal_count: int = 0
    supplier_count: int = 0
    material_type_compliance: list[dict[str, Any]] = Field(default_factory=list)
    qualification_compliance: list[dict[str, Any]] = Field(default_factory=list)
    supplier_risk_ranking: list[dict[str, Any]] = Field(default_factory=list)
    expiry_timeline: list[dict[str, Any]] = Field(default_factory=list)


class SupplierPullResult(BaseModel):
    """Supplier qualification mirror pull result."""

    synced: int = 0
    failed: int = 0
    removed: int = 0
    total: int = 0
