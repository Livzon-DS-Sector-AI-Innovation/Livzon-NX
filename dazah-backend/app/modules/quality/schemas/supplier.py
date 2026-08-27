"""Supplier schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SupplierBase(BaseModel):
    """Shared supplier fields."""

    supplier_code: str = Field(..., description="供应商编号")
    name: str = Field(..., description="供应商名称")
    category: str | None = Field(default=None, description="类别")
    contact_person: str | None = Field(default=None, description="联系人")
    contact_phone: str | None = Field(default=None, description="联系电话")
    address: str | None = Field(default=None, description="地址")
    qualification_status: str | None = Field(default=None, description="资质状态")
    audit_date: date | None = Field(default=None, description="最近审计日期")
    audit_result: str | None = Field(default=None, description="审计结论")
    next_audit_date: date | None = Field(default=None, description="下次审计日期")
    scope_of_supply: str | None = Field(default=None, description="供应范围")
    remarks: str | None = Field(default=None, description="备注")
    status: str = Field(default="active", description="状态")


class CreateSupplierRequest(SupplierBase):
    """Create supplier request."""

    pass


class UpdateSupplierRequest(BaseModel):
    """Update supplier request."""

    name: str | None = None
    category: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    qualification_status: str | None = None
    audit_date: date | None = None
    audit_result: str | None = None
    next_audit_date: date | None = None
    scope_of_supply: str | None = None
    remarks: str | None = None
    status: str | None = None


class SupplierOut(SupplierBase):
    """Supplier output."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
