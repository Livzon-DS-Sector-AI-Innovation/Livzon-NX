"""Authorization letter and supplementary reply schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductInfo(BaseModel):
    """品种登记号对照表条目"""
    product_name: str = Field(..., description="品种名称")
    registration_number: str = Field(..., description="登记号")


class AuthorizationLetterCreate(BaseModel):
    """生成授权书请求"""
    product_name: str = Field(..., max_length=128, description="产品名称（对照表标准名）")
    registration_number: str = Field(..., max_length=32, description="产品登记号")
    preparation_unit: str = Field(..., max_length=256, description="制剂单位名称")
    preparation_name: str = Field(..., max_length=256, description="制剂名称")
    administration_route: str = Field(..., max_length=64, description="给药途径")
    remarks: str | None = Field(None, description="备注")


class AuthorizationLetterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_name: str
    registration_number: str
    preparation_unit: str
    preparation_name: str
    administration_route: str
    remarks: str | None = None
    output_file_name: str | None = None
    created_at: datetime
    updated_at: datetime


class AuthorizationLetterListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_name: str
    registration_number: str
    preparation_unit: str
    preparation_name: str
    administration_route: str
    output_file_name: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplementaryReplyCreate(BaseModel):
    """生成发补回复请求"""
    drug_name: str | None = Field(None, max_length=128, description="药品名称")
    registration_number: str | None = Field(None, max_length=64, description="登记号")
    acceptance_number: str | None = Field(None, max_length=64, description="受理号")
    company_name: str | None = Field(None, max_length=256, description="申请人/公司名称")
    remarks: str | None = Field(None, description="备注")


class SupplementaryReplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    drug_name: str | None = None
    registration_number: str | None = None
    acceptance_number: str | None = None
    company_name: str | None = None
    remarks: str | None = None
    output_file_name: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplementaryReplyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    drug_name: str | None = None
    registration_number: str | None = None
    acceptance_number: str | None = None
    company_name: str | None = None
    output_file_name: str | None = None
    created_at: datetime
    updated_at: datetime


# ── 对照物质说明表 ──────────────────────────────────────────


class ReferenceStandardCreate(BaseModel):
    """生成对照物质说明表请求"""
    drug_name: str = Field(..., max_length=128, description="药品名称")
    reference_substance_name: str | None = Field(None, max_length=256, description="对照物质名称")
    batch_number: str | None = Field(None, max_length=64, description="批号")
    manufacturer: str | None = Field(None, max_length=256, description="生产厂家")
    english_name: str | None = Field(None, max_length=256, description="英文名")
    molecular_formula: str | None = Field(None, max_length=128, description="分子式")
    molecular_weight: str | None = Field(None, max_length=64, description="分子量")
    cas_number: str | None = Field(None, max_length=64, description="CAS号")
    content: str | None = Field(None, max_length=64, description="含量")
    moisture: str | None = Field(None, max_length=64, description="水分/干燥失重")
    rsd: str | None = Field(None, max_length=64, description="RSD")
    expiration_date: str | None = Field(None, max_length=64, description="有效期")
    storage_condition: str | None = Field(None, max_length=128, description="贮存条件")
    remarks: str | None = Field(None, description="备注")


class ReferenceStandardResponse(BaseModel):
    """对照物质说明表记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    drug_name: str
    reference_substance_name: str | None = None
    batch_number: str | None = None
    manufacturer: str | None = None
    english_name: str | None = None
    molecular_formula: str | None = None
    molecular_weight: str | None = None
    cas_number: str | None = None
    content: str | None = None
    moisture: str | None = None
    rsd: str | None = None
    expiration_date: str | None = None
    storage_condition: str | None = None
    coa_file_name: str | None = None
    output_file_name: str
    remarks: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReferenceStandardListItem(BaseModel):
    """对照物质说明表列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    drug_name: str
    reference_substance_name: str | None = None
    batch_number: str | None = None
    manufacturer: str | None = None
    output_file_name: str
    created_at: datetime | None = None
