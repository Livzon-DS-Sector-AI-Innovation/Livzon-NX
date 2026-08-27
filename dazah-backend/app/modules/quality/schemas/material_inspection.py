"""Material inspection shared schemas (solid/liquid/finished)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MaterialInspectionBase(BaseModel):
    inspection_no: str = Field(..., description="检验编号")
    inspection_item: str | None = Field(default=None, description="检验项目")
    specification: str | None = Field(default=None, description="标准规定")
    test_result: str | None = Field(default=None, description="检验结果")
    conclusion: str | None = Field(default=None, description="检验结论")
    inspector: str | None = Field(default=None, description="检验人")
    inspection_date: date | None = Field(default=None, description="检验日期")
    remark: str | None = Field(default=None, description="备注")


# ── Finished Product ──


class FinishedProductInspectionBase(MaterialInspectionBase):
    product_name: str | None = Field(default=None, description="产品名称")
    batch_no: str | None = Field(default=None, description="批号")


class CreateFinishedProductInspectionRequest(FinishedProductInspectionBase):
    pass


class UpdateFinishedProductInspectionRequest(BaseModel):
    inspection_no: str | None = None
    product_name: str | None = None
    batch_no: str | None = None
    inspection_item: str | None = None
    specification: str | None = None
    test_result: str | None = None
    conclusion: str | None = None
    inspector: str | None = None
    inspection_date: date | None = None
    remark: str | None = None


class FinishedProductInspectionOut(FinishedProductInspectionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Solid Material ──


class SolidMaterialInspectionBase(MaterialInspectionBase):
    material_name: str | None = Field(default=None, description="物料名称")
    material_batch: str | None = Field(default=None, description="物料批号")
    supplier: str | None = Field(default=None, description="供应商")


class CreateSolidMaterialInspectionRequest(SolidMaterialInspectionBase):
    pass


class UpdateSolidMaterialInspectionRequest(BaseModel):
    inspection_no: str | None = None
    material_name: str | None = None
    material_batch: str | None = None
    supplier: str | None = None
    inspection_item: str | None = None
    specification: str | None = None
    test_result: str | None = None
    conclusion: str | None = None
    inspector: str | None = None
    inspection_date: date | None = None
    remark: str | None = None


class SolidMaterialInspectionOut(SolidMaterialInspectionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Liquid Material ──


class LiquidMaterialInspectionBase(MaterialInspectionBase):
    material_name: str | None = Field(default=None, description="物料名称")
    material_batch: str | None = Field(default=None, description="物料批号")
    supplier: str | None = Field(default=None, description="供应商")


class CreateLiquidMaterialInspectionRequest(LiquidMaterialInspectionBase):
    pass


class UpdateLiquidMaterialInspectionRequest(BaseModel):
    inspection_no: str | None = None
    material_name: str | None = None
    material_batch: str | None = None
    supplier: str | None = None
    inspection_item: str | None = None
    specification: str | None = None
    test_result: str | None = None
    conclusion: str | None = None
    inspector: str | None = None
    inspection_date: date | None = None
    remark: str | None = None


class LiquidMaterialInspectionOut(LiquidMaterialInspectionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
