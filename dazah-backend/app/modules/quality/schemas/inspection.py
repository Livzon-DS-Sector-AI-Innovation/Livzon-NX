"""Pydantic contracts for the quality inspection foundation."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InspectionEntityOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InspectionRecordBase(BaseModel):
    inspection_no: str = Field(min_length=1, max_length=50, description="检验编号")
    product_name: str | None = Field(
        default=None, max_length=200, description="产品名称"
    )
    batch_no: str | None = Field(default=None, max_length=100, description="批号")
    inspection_type: str | None = Field(
        default=None, max_length=50, description="检验类型"
    )
    inspection_item: str | None = Field(
        default=None, max_length=500, description="检验项目"
    )
    specification: str | None = Field(default=None, description="标准规定")
    test_result: str | None = Field(default=None, description="检验结果")
    conclusion: str | None = Field(default=None, max_length=20, description="检验结论")
    inspector: str | None = Field(default=None, max_length=100, description="检验人")
    inspection_date: date | None = Field(default=None, description="检验日期")
    department: str | None = Field(default=None, max_length=100, description="检验部门")
    remark: str | None = Field(default=None, description="备注")


class CreateInspectionRecordRequest(InspectionRecordBase):
    pass


class UpdateInspectionRecordRequest(BaseModel):
    inspection_no: str | None = Field(default=None, min_length=1, max_length=50)
    product_name: str | None = Field(default=None, max_length=200)
    batch_no: str | None = Field(default=None, max_length=100)
    inspection_type: str | None = Field(default=None, max_length=50)
    inspection_item: str | None = Field(default=None, max_length=500)
    specification: str | None = None
    test_result: str | None = None
    conclusion: str | None = Field(default=None, max_length=20)
    inspector: str | None = Field(default=None, max_length=100)
    inspection_date: date | None = None
    department: str | None = Field(default=None, max_length=100)
    remark: str | None = None


class InspectionRecordOut(InspectionRecordBase, InspectionEntityOut):
    pass


class LabItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="物品名称")
    specification: str | None = Field(
        default=None, max_length=200, description="规格/型号"
    )
    category: str | None = Field(default=None, max_length=50, description="类别")
    quantity: int = Field(default=0, ge=0, description="数量")
    unit: str | None = Field(default=None, max_length=20, description="单位")
    location: str | None = Field(default=None, max_length=100, description="存放位置")
    supplier: str | None = Field(default=None, max_length=200, description="供应商")
    batch_no: str | None = Field(default=None, max_length=100, description="批号")
    expiry_date: date | None = Field(default=None, description="有效期至")
    status: str = Field(
        default="normal", min_length=1, max_length=20, description="状态"
    )
    remark: str | None = Field(default=None, description="备注")


class CreateLabItemRequest(LabItemBase):
    pass


class UpdateLabItemRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    specification: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    quantity: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=100)
    supplier: str | None = Field(default=None, max_length=200)
    batch_no: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None
    status: str | None = Field(default=None, min_length=1, max_length=20)
    remark: str | None = None


class LabItemOut(LabItemBase, InspectionEntityOut):
    pass


class LabInstrumentBase(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="仪器名称")
    model: str | None = Field(default=None, max_length=100, description="型号")
    serial_no: str | None = Field(default=None, max_length=100, description="序列号")
    manufacturer: str | None = Field(
        default=None, max_length=200, description="生产厂家"
    )
    department: str | None = Field(default=None, max_length=100, description="所属部门")
    location: str | None = Field(default=None, max_length=100, description="放置位置")
    calibration_date: date | None = Field(default=None, description="最近校准日期")
    next_calibration_date: date | None = Field(default=None, description="下次校准日期")
    status: str = Field(
        default="normal", min_length=1, max_length=20, description="状态"
    )
    remark: str | None = Field(default=None, description="备注")


class CreateLabInstrumentRequest(LabInstrumentBase):
    pass


class UpdateLabInstrumentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=100)
    serial_no: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    calibration_date: date | None = None
    next_calibration_date: date | None = None
    status: str | None = Field(default=None, min_length=1, max_length=20)
    remark: str | None = None


class LabInstrumentOut(LabInstrumentBase, InspectionEntityOut):
    pass


class MaterialInspectionBase(BaseModel):
    inspection_no: str = Field(min_length=1, max_length=50, description="检验编号")
    inspection_item: str | None = Field(
        default=None, max_length=500, description="检验项目"
    )
    specification: str | None = Field(default=None, description="标准规定")
    test_result: str | None = Field(default=None, description="检验结果")
    conclusion: str | None = Field(default=None, max_length=20, description="检验结论")
    inspector: str | None = Field(default=None, max_length=100, description="检验人")
    inspection_date: date | None = Field(default=None, description="检验日期")
    remark: str | None = Field(default=None, description="备注")


class FinishedProductInspectionBase(MaterialInspectionBase):
    product_name: str | None = Field(
        default=None, max_length=200, description="产品名称"
    )
    batch_no: str | None = Field(default=None, max_length=100, description="批号")


class CreateFinishedProductInspectionRequest(FinishedProductInspectionBase):
    pass


class UpdateFinishedProductInspectionRequest(BaseModel):
    inspection_no: str | None = Field(default=None, min_length=1, max_length=50)
    product_name: str | None = Field(default=None, max_length=200)
    batch_no: str | None = Field(default=None, max_length=100)
    inspection_item: str | None = Field(default=None, max_length=500)
    specification: str | None = None
    test_result: str | None = None
    conclusion: str | None = Field(default=None, max_length=20)
    inspector: str | None = Field(default=None, max_length=100)
    inspection_date: date | None = None
    remark: str | None = None


class FinishedProductInspectionOut(FinishedProductInspectionBase, InspectionEntityOut):
    pass


class MaterialInspectionUpdateRequest(BaseModel):
    inspection_no: str | None = Field(default=None, min_length=1, max_length=50)
    material_name: str | None = Field(default=None, max_length=200)
    material_batch: str | None = Field(default=None, max_length=100)
    supplier: str | None = Field(default=None, max_length=200)
    inspection_item: str | None = Field(default=None, max_length=500)
    specification: str | None = None
    test_result: str | None = None
    conclusion: str | None = Field(default=None, max_length=20)
    inspector: str | None = Field(default=None, max_length=100)
    inspection_date: date | None = None
    remark: str | None = None


class SolidMaterialInspectionBase(MaterialInspectionBase):
    material_name: str | None = Field(
        default=None, max_length=200, description="物料名称"
    )
    material_batch: str | None = Field(
        default=None, max_length=100, description="物料批号"
    )
    supplier: str | None = Field(default=None, max_length=200, description="供应商")


class CreateSolidMaterialInspectionRequest(SolidMaterialInspectionBase):
    pass


class UpdateSolidMaterialInspectionRequest(MaterialInspectionUpdateRequest):
    pass


class SolidMaterialInspectionOut(SolidMaterialInspectionBase, InspectionEntityOut):
    pass


class LiquidMaterialInspectionBase(MaterialInspectionBase):
    material_name: str | None = Field(
        default=None, max_length=200, description="物料名称"
    )
    material_batch: str | None = Field(
        default=None, max_length=100, description="物料批号"
    )
    supplier: str | None = Field(default=None, max_length=200, description="供应商")


class CreateLiquidMaterialInspectionRequest(LiquidMaterialInspectionBase):
    pass


class UpdateLiquidMaterialInspectionRequest(MaterialInspectionUpdateRequest):
    pass


class LiquidMaterialInspectionOut(LiquidMaterialInspectionBase, InspectionEntityOut):
    pass
