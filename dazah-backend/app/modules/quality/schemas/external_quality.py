"""Pydantic contracts for supplier and external-quality management."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SupplierStatus = Literal["active", "suspended", "blacklisted"]
SupplierQualificationStatus = Literal[
    "pending", "valid", "expiring", "expired", "invalid"
]
ComplaintStatus = Literal["pending", "investigating", "responded", "closed"]
ReturnRecallType = Literal["return", "recall"]
ReturnRecallStatus = Literal["pending", "assessing", "processing", "completed"]
ProductQualityRecordType = Literal["annual_review", "customer_standard"]
ProductQualityStatus = Literal["draft", "completed", "approved"]


class ExternalQualityEntityOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplierBase(BaseModel):
    supplier_code: str = Field(min_length=1, max_length=50, description="供应商编号")
    name: str = Field(min_length=1, max_length=200, description="供应商名称")
    category: str | None = Field(default=None, max_length=50, description="供应商类别")
    contact_person: str | None = Field(
        default=None, max_length=100, description="联系人"
    )
    contact_phone: str | None = Field(
        default=None, max_length=30, description="联系电话"
    )
    address: str | None = Field(default=None, max_length=300, description="地址")
    qualification_status: SupplierQualificationStatus = Field(
        default="pending", description="资质状态"
    )
    audit_date: date | None = Field(default=None, description="最近审计日期")
    audit_result: str | None = Field(default=None, description="审计结论")
    next_audit_date: date | None = Field(default=None, description="下次审计日期")
    scope_of_supply: str | None = Field(default=None, description="供应范围")
    remark: str | None = Field(default=None, description="备注")
    status: SupplierStatus = Field(default="active", description="供应商状态")


class CreateSupplierRequest(SupplierBase):
    pass


class UpdateSupplierRequest(BaseModel):
    supplier_code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    contact_person: str | None = Field(default=None, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=300)
    qualification_status: SupplierQualificationStatus | None = None
    audit_date: date | None = None
    audit_result: str | None = None
    next_audit_date: date | None = None
    scope_of_supply: str | None = None
    remark: str | None = None
    status: SupplierStatus | None = None


class SupplierOut(SupplierBase, ExternalQualityEntityOut):
    pass


class SupplierQualificationBase(BaseModel):
    qualification_code: str = Field(min_length=1, max_length=50, description="资质编号")
    qualification_name: str = Field(
        min_length=1, max_length=200, description="资质名称"
    )
    document_no: str | None = Field(
        default=None, max_length=100, description="文件编号"
    )
    obtained_date: date | None = Field(default=None, description="取得日期")
    expiry_date: date | None = Field(default=None, description="到期日期")
    status: SupplierQualificationStatus = Field(
        default="pending", description="资质状态"
    )
    responsible_person: str | None = Field(
        default=None, max_length=100, description="责任人"
    )
    remark: str | None = Field(default=None, description="备注")


class CreateSupplierQualificationRequest(SupplierQualificationBase):
    pass


class UpdateSupplierQualificationRequest(BaseModel):
    qualification_code: str | None = Field(default=None, min_length=1, max_length=50)
    qualification_name: str | None = Field(default=None, min_length=1, max_length=200)
    document_no: str | None = Field(default=None, max_length=100)
    obtained_date: date | None = None
    expiry_date: date | None = None
    status: SupplierQualificationStatus | None = None
    responsible_person: str | None = Field(default=None, max_length=100)
    remark: str | None = None


class SupplierQualificationOut(SupplierQualificationBase, ExternalQualityEntityOut):
    supplier_id: UUID


class ComplaintBase(BaseModel):
    complaint_code: str = Field(min_length=1, max_length=50, description="投诉编号")
    title: str = Field(min_length=1, max_length=200, description="投诉标题")
    complaint_source: str | None = Field(
        default=None, max_length=100, description="投诉来源"
    )
    customer_name: str | None = Field(
        default=None, max_length=200, description="客户名称"
    )
    product_name: str | None = Field(
        default=None, max_length=200, description="涉及产品"
    )
    batch_number: str | None = Field(default=None, max_length=100, description="批号")
    complaint_date: date | None = Field(default=None, description="投诉日期")
    complaint_category: str | None = Field(
        default=None, max_length=50, description="投诉类别"
    )
    description: str | None = Field(default=None, description="投诉描述")
    handler: str | None = Field(default=None, max_length=100, description="处理人")
    capa_code: str | None = Field(
        default=None, max_length=50, description="关联CAPA编号"
    )


class CreateComplaintRequest(ComplaintBase):
    pass


class UpdateComplaintRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    complaint_source: str | None = Field(default=None, max_length=100)
    customer_name: str | None = Field(default=None, max_length=200)
    product_name: str | None = Field(default=None, max_length=200)
    batch_number: str | None = Field(default=None, max_length=100)
    complaint_date: date | None = None
    complaint_category: str | None = Field(default=None, max_length=50)
    description: str | None = None
    handler: str | None = Field(default=None, max_length=100)
    capa_code: str | None = Field(default=None, max_length=50)


class RespondComplaintRequest(BaseModel):
    investigation_result: str = Field(min_length=1, description="调查结论")
    response_content: str = Field(min_length=1, description="回复内容")
    response_date: date = Field(default_factory=date.today, description="回复日期")


class ComplaintOut(ComplaintBase, ExternalQualityEntityOut):
    investigation_result: str | None
    response_content: str | None
    response_date: date | None
    status: ComplaintStatus
    closed_at: datetime | None


class ReturnRecallBase(BaseModel):
    record_code: str = Field(min_length=1, max_length=50, description="记录编号")
    record_type: ReturnRecallType = Field(description="记录类型")
    title: str = Field(min_length=1, max_length=200, description="标题")
    product_name: str | None = Field(
        default=None, max_length=200, description="产品名称"
    )
    batch_number: str | None = Field(default=None, max_length=100, description="批号")
    quantity: Decimal | None = Field(default=None, ge=0, description="数量")
    unit: str | None = Field(default=None, max_length=20, description="单位")
    customer_name: str | None = Field(
        default=None, max_length=200, description="客户或退货方"
    )
    reason: str | None = Field(default=None, description="退货或召回原因")
    occurrence_date: date | None = Field(default=None, description="发生日期")
    handler: str | None = Field(default=None, max_length=100, description="处理人")


class CreateReturnRecallRequest(ReturnRecallBase):
    pass


class UpdateReturnRecallRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    product_name: str | None = Field(default=None, max_length=200)
    batch_number: str | None = Field(default=None, max_length=100)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)
    customer_name: str | None = Field(default=None, max_length=200)
    reason: str | None = None
    occurrence_date: date | None = None
    handler: str | None = Field(default=None, max_length=100)


class StartReturnRecallProcessingRequest(BaseModel):
    assessment_date: date = Field(default_factory=date.today, description="评估日期")


class CompleteReturnRecallRequest(BaseModel):
    disposition: str = Field(min_length=1, max_length=50, description="处置方式")
    completion_date: date = Field(default_factory=date.today, description="完成日期")


class ReturnRecallOut(ReturnRecallBase, ExternalQualityEntityOut):
    assessment_date: date | None
    disposition: str | None
    completion_date: date | None
    status: ReturnRecallStatus


class ProductQualityRecordBase(BaseModel):
    record_code: str = Field(min_length=1, max_length=50, description="质量记录编号")
    record_type: ProductQualityRecordType = Field(description="记录类型")
    title: str = Field(min_length=1, max_length=200, description="标题")
    product_name: str = Field(min_length=1, max_length=200, description="产品名称")
    customer_name: str | None = Field(
        default=None, max_length=200, description="客户名称"
    )
    batch_number: str | None = Field(default=None, max_length=100, description="批号")
    document_no: str | None = Field(
        default=None, max_length=100, description="标准文件编号"
    )
    document_version: str | None = Field(
        default=None, max_length=50, description="标准文件版本"
    )
    review_type: str | None = Field(default=None, max_length=50, description="评审类型")
    review_period_start: date | None = Field(default=None, description="回顾周期开始")
    review_period_end: date | None = Field(default=None, description="回顾周期结束")
    batch_count: int | None = Field(default=None, ge=0, description="批次数量")
    qualified_count: int | None = Field(default=None, ge=0, description="合格批次")
    unqualified_count: int | None = Field(default=None, ge=0, description="不合格批次")
    oos_count: int | None = Field(default=None, ge=0, description="OOS次数")
    deviation_count: int | None = Field(default=None, ge=0, description="偏差次数")
    change_count: int | None = Field(default=None, ge=0, description="变更次数")
    quality_trend: str | None = Field(
        default=None, max_length=30, description="质量趋势"
    )
    quality_standard: str | None = Field(default=None, description="质量标准")
    special_requirements: str | None = Field(default=None, description="特殊要求")
    packaging_requirements: str | None = Field(default=None, description="包装要求")
    label_requirements: str | None = Field(default=None, description="标签要求")
    pallet_requirements: str | None = Field(default=None, description="打托要求")
    target_market: str | None = Field(
        default=None, max_length=100, description="目标市场"
    )
    registration_status: str | None = Field(
        default=None, max_length=100, description="注册情况"
    )
    suggestions: str | None = Field(default=None, description="改进建议")


class CreateProductQualityRecordRequest(ProductQualityRecordBase):
    pass


class UpdateProductQualityRecordRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    customer_name: str | None = Field(default=None, max_length=200)
    batch_number: str | None = Field(default=None, max_length=100)
    document_no: str | None = Field(default=None, max_length=100)
    document_version: str | None = Field(default=None, max_length=50)
    review_type: str | None = Field(default=None, max_length=50)
    review_period_start: date | None = None
    review_period_end: date | None = None
    batch_count: int | None = Field(default=None, ge=0)
    qualified_count: int | None = Field(default=None, ge=0)
    unqualified_count: int | None = Field(default=None, ge=0)
    oos_count: int | None = Field(default=None, ge=0)
    deviation_count: int | None = Field(default=None, ge=0)
    change_count: int | None = Field(default=None, ge=0)
    quality_trend: str | None = Field(default=None, max_length=30)
    quality_standard: str | None = None
    special_requirements: str | None = None
    packaging_requirements: str | None = None
    label_requirements: str | None = None
    pallet_requirements: str | None = None
    target_market: str | None = Field(default=None, max_length=100)
    registration_status: str | None = Field(default=None, max_length=100)
    suggestions: str | None = None


class CompleteProductQualityRecordRequest(BaseModel):
    conclusion: str = Field(min_length=1, description="评审结论")
    reviewer: str = Field(min_length=1, max_length=100, description="评审人")
    review_date: date = Field(default_factory=date.today, description="评审日期")


class ProductQualityRecordOut(ProductQualityRecordBase, ExternalQualityEntityOut):
    conclusion: str | None
    reviewer: str | None
    review_date: date | None
    status: ProductQualityStatus
    approved_at: datetime | None


class ProductQualityStandardItemBase(BaseModel):
    display_order: int = Field(default=1, ge=1, description="显示顺序")
    category: str | None = Field(default=None, max_length=100, description="要求分类")
    item_name: str = Field(min_length=1, max_length=500, description="要求项目")
    requirement: str = Field(min_length=1, description="要求内容")
    is_critical: bool = Field(default=False, description="是否关键要求")
    remark: str | None = Field(default=None, description="备注")


class CreateProductQualityStandardItemRequest(ProductQualityStandardItemBase):
    pass


class UpdateProductQualityStandardItemRequest(BaseModel):
    display_order: int | None = Field(default=None, ge=1)
    category: str | None = Field(default=None, max_length=100)
    item_name: str | None = Field(default=None, min_length=1, max_length=500)
    requirement: str | None = Field(default=None, min_length=1)
    is_critical: bool | None = None
    remark: str | None = None


class ProductQualityStandardItemOut(
    ProductQualityStandardItemBase, ExternalQualityEntityOut
):
    product_quality_id: UUID


class ExternalQualityPageMeta(BaseModel):
    page: int
    page_size: int
    total: int


class SupplierResponse(BaseModel):
    code: int
    message: str
    data: SupplierOut


class SupplierListResponse(BaseModel):
    code: int
    message: str
    data: list[SupplierOut]
    meta: ExternalQualityPageMeta


class SupplierQualificationResponse(BaseModel):
    code: int
    message: str
    data: SupplierQualificationOut


class SupplierQualificationListResponse(BaseModel):
    code: int
    message: str
    data: list[SupplierQualificationOut]


class ComplaintResponse(BaseModel):
    code: int
    message: str
    data: ComplaintOut


class ComplaintListResponse(BaseModel):
    code: int
    message: str
    data: list[ComplaintOut]
    meta: ExternalQualityPageMeta


class ReturnRecallResponse(BaseModel):
    code: int
    message: str
    data: ReturnRecallOut


class ReturnRecallListResponse(BaseModel):
    code: int
    message: str
    data: list[ReturnRecallOut]
    meta: ExternalQualityPageMeta


class ProductQualityRecordResponse(BaseModel):
    code: int
    message: str
    data: ProductQualityRecordOut


class ProductQualityRecordListResponse(BaseModel):
    code: int
    message: str
    data: list[ProductQualityRecordOut]
    meta: ExternalQualityPageMeta


class ProductQualityStandardItemResponse(BaseModel):
    code: int
    message: str
    data: ProductQualityStandardItemOut


class ProductQualityStandardItemListResponse(BaseModel):
    code: int
    message: str
    data: list[ProductQualityStandardItemOut]


class ExternalQualityFeishuSyncOut(BaseModel):
    resource_code: str
    entity_code: str
    record_id: str
    table_id: str
    synced_at: datetime


class ExternalQualityFeishuSyncResponse(BaseModel):
    code: int
    message: str
    data: ExternalQualityFeishuSyncOut
