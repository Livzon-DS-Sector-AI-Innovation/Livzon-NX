"""Procurement request and response schemas live here."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLineItem(BaseModel):
    project_name: str | None = Field(None, description="项目名称")
    unit: str | None = Field(None, description="单位")
    quantity: Decimal | None = Field(None, description="数量")


class InvoiceRecognitionResult(BaseModel):
    invoice_number: str | None = Field(None, description="发票号码")
    invoice_date: str | None = Field(None, description="开票日期")
    seller_name: str | None = Field(None, description="销售方名称")
    total_tax_amount: Decimal | None = Field(None, description="税额合计")
    total_amount_with_tax_small: Decimal | None = Field(
        None,
        description="价税合计（小写）",
    )
    line_items: list[InvoiceLineItem] = Field(
        default_factory=list,
        description="发票明细",
    )
    raw_text: str = Field("", description="PDF 文本层原文")


class InvoiceRecognitionRecordResponse(InvoiceRecognitionResult):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="识别记录 ID")
    file_name: str = Field(..., description="上传文件名")
    include_details: bool = Field(False, description="是否开启明细识别")
    created_at: datetime | None = Field(None, description="识别时间")


class InvoiceRecognitionResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: InvoiceRecognitionRecordResponse
    meta: dict[str, Any] | None = None


class InvoiceRecognitionRecordListResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: list[InvoiceRecognitionRecordResponse]
    meta: dict[str, Any] | None = None


class InvoiceRecognitionRecordDeleteRequest(BaseModel):
    ids: list[UUID] = Field(default_factory=list, description="识别记录 ID 列表")


class InvoiceRecognitionRecordDeleteResult(BaseModel):
    success_count: int = Field(0, description="成功删除数量")
    fail_count: int = Field(0, description="删除失败数量")


class InvoiceRecognitionRecordDeleteResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: InvoiceRecognitionRecordDeleteResult | None = None
    meta: dict[str, Any] | None = None


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="供应商清单记录 ID")
    supplier_code: str = Field("", description="供应商代码")
    supplier_name: str = Field("", description="供应商名称")
    material_code: str = Field("", description="物料编码")
    material_name: str = Field("", description="物料名称")
    manufacturer_code: str = Field("", description="生产厂家编码")
    manufacturer_name: str = Field("", description="生产厂家名称")
    purchase_category: str = Field("", description="采购品类名称")
    last_updated_by: str = Field("", description="最后更新人")
    last_updated_date: date | None = Field(None, description="最后更新日期")
    import_file_name: str = Field("", description="导入文件名")
    import_sheet_name: str = Field("", description="导入工作表")
    import_row_number: int = Field(..., description="导入文件行号")
    import_columns: list[str] = Field(default_factory=list, description="导入字段")
    raw_data: dict[str, Any] = Field(default_factory=dict, description="原始行数据")
    created_at: datetime | None = Field(None, description="导入时间")
    updated_at: datetime | None = Field(None, description="更新时间")


class SupplierListResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: list[SupplierResponse]
    meta: dict[str, Any] | None = None


class SupplierImportResult(BaseModel):
    imported_count: int = Field(0, description="导入记录数")
    columns: list[str] = Field(default_factory=list, description="导入字段")
    file_name: str = Field("", description="导入文件名")
    sheet_name: str = Field("", description="导入工作表")


class SupplierImportResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: SupplierImportResult
    meta: dict[str, Any] | None = None


class PurchaseRequestCategory(StrEnum):
    hardware = "hardware"
    computer = "computer"
    office = "office"
    raw_auxiliary = "raw-auxiliary"
    chemical_glass = "chemical-glass"
    electrical = "electrical"
    advertising_printing = "advertising-printing"
    fire = "fire"
    packaging = "packaging"
    labor_special = "labor-special"
    labor_miscellaneous = "labor-miscellaneous"
    urgent = "urgent"


MATERIAL_FIELD_PURCHASE_CATEGORIES = frozenset(
    {
        PurchaseRequestCategory.hardware,
        PurchaseRequestCategory.electrical,
        PurchaseRequestCategory.chemical_glass,
        PurchaseRequestCategory.raw_auxiliary,
        PurchaseRequestCategory.packaging,
        PurchaseRequestCategory.labor_special,
        PurchaseRequestCategory.labor_miscellaneous,
        PurchaseRequestCategory.fire,
    }
)

NORMAL_PURCHASE_CATEGORIES = frozenset(
    category
    for category in PurchaseRequestCategory
    if category is not PurchaseRequestCategory.urgent
)


class PurchaseRequestImportSummary(BaseModel):
    request_id: UUID = Field(..., description="生成的采购申请草稿 ID")
    sheet_name: str = Field("", description="来源工作表")
    category: PurchaseRequestCategory = Field(..., description="采购分类")
    category_label: str = Field("", description="采购分类名称")
    category_source: str = Field(
        "sheet_name",
        description="采购类型来源：column=表内采购类型列，sheet_name=工作表名称，inferred=按明细字段自动推断",
    )
    request_department: str = Field("", description="申购部门")
    request_date: date = Field(..., description="申请日期")
    items_count: int = Field(..., description="导入明细条数")


class PurchaseRequestImportError(BaseModel):
    sheet_name: str = Field("", description="来源工作表")
    row: int | None = Field(None, description="文件行号；None 表示整个工作表级错误")
    message: str = Field(..., description="错误说明")


class PurchaseRequestImportResult(BaseModel):
    file_name: str = Field("", description="导入文件名")
    total_sheets: int = Field(0, description="文件工作表数（CSV 为 1）")
    imported_requests: list[PurchaseRequestImportSummary] = Field(
        default_factory=list,
        description="成功生成的采购申请草稿",
    )
    failed_rows: list[PurchaseRequestImportError] = Field(
        default_factory=list,
        description="失败的行或工作表",
    )


class PurchaseRequestImportResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: PurchaseRequestImportResult
    meta: dict[str, Any] | None = None


class PurchaseRequestStatus(StrEnum):
    draft = "draft"
    pending_hardware_warehouse = "pending_hardware_warehouse"
    pending_equipment_power = "pending_equipment_power"
    pending_safety_officer = "pending_safety_officer"
    pending_department_head = "pending_department_head"
    pending_responsible_leader = "pending_responsible_leader"
    pending_supervising_leader = "pending_supervising_leader"
    pending_finance_director = "pending_finance_director"
    pending_general_manager = "pending_general_manager"
    approved = "approved"
    rejected = "rejected"


class PurchaseApprovalRole(StrEnum):
    hardware_warehouse = "hardware_warehouse"
    equipment_power = "equipment_power"
    safety_officer = "safety_officer"
    department_head = "department_head"
    responsible_leader = "responsible_leader"
    supervising_leader = "supervising_leader"
    finance_director = "finance_director"
    general_manager = "general_manager"


class PurchaseApprovalResult(StrEnum):
    approved = "approved"
    rejected = "rejected"


class PurchaseApprovalView(StrEnum):
    pending = "pending"
    completed = "completed"
    rejected = "rejected"


class PurchaseRequestItemInput(BaseModel):
    item_category: PurchaseRequestCategory | None = Field(
        None,
        description="明细采购类型，加急单必填",
    )
    product_name: str = Field("", max_length=255, description="商品名称")
    specification: str = Field("", max_length=255, description="规格")
    material_code: str = Field("", max_length=64, description="物料编码")
    material_description: str = Field(
        "",
        max_length=255,
        description="物料说明",
    )
    rule_model: str = Field("", max_length=255, description="规格型号")
    purpose: str = Field("", max_length=255, description="用途")
    material: str = Field("", max_length=255, description="材质")
    brand: str = Field("", max_length=255, description="品牌")
    quantity: Decimal = Field(..., ge=0, description="数量")
    unit: str = Field("", max_length=64, description="单位")
    unit_price: Decimal = Field(..., ge=0, description="单价（元）")
    remarks: str = Field("", description="备注")


class PurchaseRequestItemResponse(PurchaseRequestItemInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="明细 ID")
    sequence: int = Field(..., description="序号")
    total_amount: Decimal = Field(..., description="总额（元）")


class PurchaseApprovalRequest(BaseModel):
    approval_role: PurchaseApprovalRole = Field(..., description="审批角色")
    approver_name: str = Field("", max_length=100, description="审批人姓名")
    opinion: str = Field("", description="审批意见")
    result: PurchaseApprovalResult = Field(..., description="审批结果")


class PurchaseRequestCreate(BaseModel):
    category: PurchaseRequestCategory = Field(..., description="采购分类")
    request_department: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="申购部门",
    )
    request_date: date = Field(..., description="申请日期")
    attachment_note: str = Field("", description="附件说明")
    import_duplicate_key: str | None = Field(
        None,
        max_length=64,
        description="导入幂等键（内部使用，防止同一表格重复导入）",
    )
    items: list[PurchaseRequestItemInput] = Field(
        ...,
        min_length=1,
        description="申请明细",
    )


class PurchaseRequestUpdate(BaseModel):
    request_department: str | None = Field(
        None,
        min_length=1,
        max_length=200,
        description="申购部门",
    )
    request_date: date | None = Field(None, description="申请日期")
    attachment_note: str | None = Field(None, description="附件说明")
    items: list[PurchaseRequestItemInput] | None = Field(
        None,
        min_length=1,
        description="申请明细",
    )


class PurchaseApprovalRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="审批记录 ID")
    approval_role: PurchaseApprovalRole = Field(..., description="审批角色")
    result: PurchaseApprovalResult = Field(..., description="审批结果")
    opinion: str = Field("", description="审批意见")
    approver_name: str = Field("", description="审批人姓名")
    approval_time: datetime = Field(..., description="审批时间")


class PurchaseRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="采购申请 ID")
    category: PurchaseRequestCategory = Field(..., description="采购分类")
    request_department: str = Field(..., description="申购部门")
    request_date: date = Field(..., description="申请日期")
    attachment_note: str = Field("", description="附件说明")
    status: PurchaseRequestStatus = Field(..., description="流程状态")
    total_amount: Decimal = Field(..., description="合计金额")
    rejected_step: PurchaseApprovalRole | None = Field(None, description="驳回步骤")
    status_updated_at: datetime | None = Field(None, description="状态更新时间")
    created_at: datetime | None = Field(None, description="创建时间")
    updated_at: datetime | None = Field(None, description="更新时间")
    items: list[PurchaseRequestItemResponse] = Field(
        default_factory=list,
        description="申请明细",
    )
    approvals: list[PurchaseApprovalRecordResponse] = Field(
        default_factory=list,
        description="审批记录",
    )


class PurchaseRequestApiResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: PurchaseRequestResponse
    meta: dict[str, Any] | None = None


class PurchaseRequestListResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: list[PurchaseRequestResponse]
    meta: dict[str, Any] | None = None


class PurchaseRequestDeleteResult(BaseModel):
    success_count: int = Field(0, description="成功删除数量")
    fail_count: int = Field(0, description="删除失败数量")


class PurchaseRequestDeleteResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: PurchaseRequestDeleteResult | None = None
    meta: dict[str, Any] | None = None


class PurchaseOrderLineResponse(BaseModel):
    request_id: UUID = Field(..., description="采购申请 ID")
    category: PurchaseRequestCategory = Field(..., description="采购分类")
    category_label: str = Field(..., description="采购分类名称")
    request_department: str = Field(..., description="申购部门")
    request_date: date = Field(..., description="申请日期")
    item_id: UUID = Field(..., description="申请明细 ID")
    item_sequence: int = Field(..., description="明细序号")
    item_category: PurchaseRequestCategory | None = Field(
        None,
        description="明细实际采购类型",
    )
    product_name: str = Field("", description="商品名称")
    specification: str = Field("", description="规格")
    material_code: str = Field("", description="物料编码")
    material_description: str = Field("", description="物料说明")
    rule_model: str = Field("", description="规格型号")
    purpose: str = Field("", description="用途")
    material: str = Field("", description="材质")
    brand: str = Field("", description="品牌")
    quantity: Decimal = Field(..., description="数量")
    unit: str = Field("", description="单位")
    unit_price: Decimal = Field(..., description="单价（元）")
    total_amount: Decimal = Field(..., description="金额（元）")
    remarks: str = Field("", description="备注")


class PurchaseOrderListResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: list[PurchaseOrderLineResponse]
    meta: dict[str, Any] | None = None


class ContractCategory(StrEnum):
    fixed_assets = "fixed-assets"
    consumables = "consumables"
    hardware = "hardware"
    raw_materials = "raw-materials"


class ContractPartyInfo(BaseModel):
    name: str = Field("", description="单位名称")
    representative: str = Field("", description="法定代表人或签约代表")
    address: str = Field("", description="地址")
    postal_code: str = Field("", description="邮编")
    contact_person: str = Field("", description="联系人")
    contact_address: str = Field("", description="联系人地址")
    contact_phone: str = Field("", description="联系人电话")
    mobile: str = Field("", description="联系人手机")
    phone: str = Field("", description="电话")
    bank_name: str = Field("", description="开户行")
    bank_account: str = Field("", description="银行账号")
    tax_id: str = Field("", description="统一社会信用代码或纳税人识别号")
    bank_line_number: str = Field("", description="银行行号")
    email: str = Field("", description="邮箱")


class ContractItemInput(BaseModel):
    item_code: str = Field("", description="物料或物品编码")
    name: str = Field(..., description="商品或产品名称")
    specification: str = Field("", description="规格")
    quality_standard: str = Field("", description="质量标准或第二规格列")
    manufacturer: str = Field("", description="生产厂家或生产单位")
    department: str = Field("", description="申请部门或备注部门")
    quantity: Decimal = Field(..., gt=0, description="数量")
    unit: str = Field("", description="单位")
    unit_price: Decimal = Field(..., ge=0, description="单价")
    amount: Decimal | None = Field(
        None,
        ge=0,
        description="含税金额，不填则按数量*单价计算",
    )
    remarks: str = Field("", description="备注")


class ContractGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="合同标题")
    category: ContractCategory = Field(..., description="合同分类")
    contract_number: str = Field(..., description="合同编号")
    contract_date: date = Field(..., description="签订日期")
    delivery_date: date | None = Field(None, description="最迟交货日期")
    delivery_terms: str = Field("", description="交货日期或交货说明")
    payment_terms: str = Field("", description="付款期限/付款方式完整描述")
    tax_rate: Decimal = Field(Decimal("13"), ge=0, description="增值税税率")
    seller: ContractPartyInfo = Field(
        default_factory=ContractPartyInfo,
        description="卖方信息",
    )
    items: list[ContractItemInput] = Field(..., min_length=1, description="合同明细")

    buyer_invoice_recipient: str = Field("", description="发票接收人")
    buyer_invoice_recipient_mobile: str = Field("", description="发票接收人手机")
    buyer_receiver: str = Field("", description="收货人")
    buyer_receiver_mobile: str = Field("", description="收货人手机")
    buyer_receiver_phone: str = Field("", description="收货人电话")

    attached_documents: str = Field("", description="固定资产随货资料")
    installation_days: int | None = Field(None, ge=0, description="安装调试工作日")
    warranty_months: int | None = Field(None, ge=0, description="质保期（月）")
    response_hours: int | None = Field(None, ge=0, description="质保期响应小时")
    onsite_hours: int | None = Field(None, ge=0, description="质保期到场处理小时")
    maintenance_response_hours: int | None = Field(
        None,
        ge=0,
        description="质保期满维修响应小时",
    )
    overdue_days: int | None = Field(None, ge=0, description="逾期多少天可解除合同")
    jurisdiction: str = Field("", description="争议管辖地")
    attachment_note: str = Field("", description="附件说明")
    copies: int | None = Field(None, ge=1, description="合同总份数")
    buyer_copies: int | None = Field(None, ge=1, description="买方执份数")
    arrival_payment_condition: str = Field("", description="固定资产到货款支付条件")
    arrival_payment_method: str = Field("", description="固定资产到货款支付方式")
    arrival_payment_ratio: Decimal | None = Field(
        None,
        ge=0,
        le=100,
        description="到货款比例",
    )
    warranty_payment_ratio: Decimal | None = Field(
        None,
        ge=0,
        le=100,
        description="质保金比例",
    )
    warranty_payment_method: str = Field("", description="质保金支付方式")


class ContractTemplateField(BaseModel):
    name: str = Field(..., description="字段名")
    label: str = Field(..., description="显示名称")
    input_type: str = Field("text", description="输入控件类型")
    required: bool = Field(False, description="是否必填")
    default_value: str | None = Field(None, description="默认值")


class ContractTemplateMetadata(BaseModel):
    category: ContractCategory
    label: str
    fields: list[ContractTemplateField]


class ContractRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="合同记录 ID")
    title: str = Field(..., description="合同标题")
    category: ContractCategory = Field(..., description="合同分类")
    contract_number: str = Field(..., description="合同编号")
    contract_date: date = Field(..., description="签订日期")
    seller_name: str = Field("", description="卖方名称")
    filename: str = Field(..., description="合同文件名")
    content_type: str = Field(..., description="文件 MIME 类型")
    file_size: int = Field(..., description="文件大小（字节）")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="合同生成请求快照",
    )
    created_at: datetime | None = Field(None, description="生成时间")
    updated_at: datetime | None = Field(None, description="更新时间")


class ContractRecordListResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: list[ContractRecordResponse]
    meta: dict[str, Any] | None = None


class MaterialSourceConfigUpsert(BaseModel):
    source_url: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="飞书多维表格链接",
    )
    material_code_field: str | None = Field(
        None,
        max_length=128,
        description="物料编码实际字段名，不填则自动识别",
    )
    material_description_field: str | None = Field(
        None,
        max_length=128,
        description="物料说明实际字段名，不填则自动识别",
    )
    rule_model_field: str | None = Field(
        None,
        max_length=128,
        description="规格型号实际字段名，不填则自动识别",
    )
    material_unit_field: str | None = Field(
        None,
        max_length=128,
        description="主要单位实际字段名，不填则自动识别，识别不到留空",
    )
    material_template_field: str | None = Field(
        None,
        max_length=128,
        description="物料模板实际字段名，不填则自动识别，识别不到留空",
    )
    material_category_field: str | None = Field(
        None,
        max_length=128,
        description="物料大类实际字段名，不填则自动识别，识别不到留空",
    )
    material_subcategory_field: str | None = Field(
        None,
        max_length=128,
        description="物料小类实际字段名，不填则自动识别，识别不到留空",
    )
    material_cost_category_field: str | None = Field(
        None,
        max_length=128,
        description="物料成本大类实际字段名，不填则自动识别，识别不到留空",
    )


class MaterialSourceConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="物料数据源配置 ID")
    source_url: str = Field(..., description="飞书多维表格链接")
    app_token: str = Field(..., description="多维表格 app_token")
    table_id: str = Field(..., description="多维表格 table_id")
    view_id: str | None = Field(None, description="多维表格 view_id")
    material_code_field: str = Field(..., description="物料编码字段")
    material_description_field: str = Field(..., description="物料说明字段")
    rule_model_field: str = Field(..., description="规格型号字段")
    material_unit_field: str | None = Field(None, description="主要单位字段")
    material_template_field: str | None = Field(None, description="物料模板字段")
    material_category_field: str | None = Field(None, description="物料大类字段")
    material_subcategory_field: str | None = Field(
        None,
        description="物料小类字段",
    )
    material_cost_category_field: str | None = Field(
        None,
        description="物料成本大类字段",
    )
    last_test_status: str = Field(..., description="最近测试状态")
    last_test_error: str | None = Field(None, description="最近测试错误")
    last_tested_at: datetime | None = Field(None, description="最近测试时间")
    sync_status: str = Field("not_synced", description="最近同步状态")
    sync_error: str | None = Field(None, description="最近同步错误")
    last_synced_at: datetime | None = Field(None, description="最近成功同步时间")
    last_sync_record_count: int = Field(0, description="最近成功同步记录数")
    sync_total_records: int | None = Field(
        None,
        description="本次同步飞书侧预计记录数（同步进行中）",
    )
    sync_fetched_count: int | None = Field(
        None,
        description="本次同步已拉取记录数（同步进行中）",
    )
    sync_phase: str = Field("idle", description="同步阶段")
    sync_persisted_count: int = Field(0, description="本次同步已持久化记录数")
    sync_heartbeat_at: datetime | None = Field(None, description="同步最近心跳时间")
    last_successful_modified_time: int | None = Field(
        None,
        description="最近成功同步观察到的飞书最大修改时间",
    )
    sync_phase: str = Field("idle", description="同步阶段")
    sync_persisted_count: int = Field(0, description="本次同步已持久化记录数")
    sync_heartbeat_at: datetime | None = Field(None, description="同步最近心跳时间")
    last_successful_modified_time: int | None = Field(
        None,
        description="最近成功同步观察到的飞书最大修改时间",
    )
    updated_at: datetime | None = Field(None, description="配置更新时间")


class MaterialSourceConfigApiResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: MaterialSourceConfigResponse | None = None
    meta: dict[str, Any] | None = None


class MaterialSourceProbeResponse(BaseModel):
    source_url: str = Field(..., description="飞书多维表格链接")
    app_token: str = Field(..., description="解析后的多维表格 app_token")
    table_id: str = Field(..., description="解析后的多维表格 table_id")
    view_id: str | None = Field(None, description="解析后的多维表格 view_id")
    material_code_field: str = Field(..., description="识别到的物料编码字段")
    material_description_field: str = Field(..., description="识别到的物料说明字段")
    rule_model_field: str = Field(..., description="识别到的规格型号字段")
    material_unit_field: str | None = Field(
        None,
        description="识别到的主要单位字段，识别不到为 null",
    )
    material_template_field: str | None = Field(
        None,
        description="识别到的物料模板字段，识别不到为 null",
    )
    material_category_field: str | None = Field(
        None,
        description="识别到的物料大类字段，识别不到为 null",
    )
    material_subcategory_field: str | None = Field(
        None,
        description="识别到的物料小类字段，识别不到为 null",
    )
    material_cost_category_field: str | None = Field(
        None,
        description="识别到的物料成本大类字段，识别不到为 null",
    )
    available_fields: list[str] = Field(
        default_factory=list,
        description="多维表格字段名",
    )
    status: str = Field(..., description="测试状态")
    error_message: str | None = Field(None, description="测试错误")
    tested_at: datetime = Field(..., description="测试时间")


class MaterialSourceProbeApiResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: MaterialSourceProbeResponse
    meta: dict[str, Any] | None = None


class MaterialOptionResponse(BaseModel):
    record_id: str = Field(..., description="飞书记录 ID")
    material_code: str = Field(..., description="物料编码")
    material_description: str = Field(..., description="物料说明")
    rule_model: str = Field(..., description="规格型号")
    material_unit: str = Field("", description="主要单位")
    material_template: str = Field("", description="物料模板")
    material_category: str = Field("", description="物料大类")
    material_subcategory: str = Field("", description="物料小类")
    material_cost_category: str = Field("", description="物料成本大类")


class MaterialOptionListResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: list[MaterialOptionResponse]
    meta: dict[str, Any] | None = None


class MaterialCatalogRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="物料编码库记录 ID")
    feishu_record_id: str = Field(..., description="飞书记录 ID")
    material_code: str = Field("", description="物料编码")
    material_description: str = Field("", description="物料说明")
    rule_model: str = Field("", description="规格型号")
    material_unit: str = Field("", description="主要单位")
    material_template: str = Field("", description="物料模板")
    material_category: str = Field("", description="物料大类")
    material_subcategory: str = Field("", description="物料小类")
    material_cost_category: str = Field("", description="物料成本大类")
    feishu_created_time: int | None = Field(None, description="飞书创建时间")
    feishu_last_modified_time: int | None = Field(
        None,
        description="飞书最近修改时间",
    )
    last_synced_at: datetime | None = Field(None, description="最近同步时间")


class MaterialCatalogListMeta(BaseModel):
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    total: int = Field(..., description="符合条件的记录总数")
    sync_status: str = Field("not_synced", description="最近同步状态")
    sync_error: str | None = Field(None, description="最近同步错误")
    last_synced_at: datetime | None = Field(None, description="最近成功同步时间")
    last_sync_record_count: int = Field(0, description="最近成功同步记录数")
    sync_total_records: int | None = Field(
        None,
        description="本次同步飞书侧预计记录数（同步进行中）",
    )
    sync_fetched_count: int | None = Field(
        None,
        description="本次同步已拉取记录数（同步进行中）",
    )
    sync_phase: str = Field("idle", description="同步阶段")
    sync_persisted_count: int = Field(0, description="本次同步已持久化记录数")
    sync_heartbeat_at: datetime | None = Field(None, description="同步最近心跳时间")
    last_successful_modified_time: int | None = Field(
        None,
        description="最近成功同步观察到的飞书最大修改时间",
    )


class MaterialCatalogListResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: list[MaterialCatalogRecordResponse]
    meta: MaterialCatalogListMeta


class MaterialSourceSyncResult(BaseModel):
    config: MaterialSourceConfigResponse = Field(..., description="同步后的数据源配置")
    synced_count: int = Field(..., description="本次同步记录数")
    deactivated_count: int = Field(..., description="本次停用的旧记录数")


class MaterialSourceSyncApiResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: MaterialSourceSyncResult
    meta: dict[str, Any] | None = None


class ContractRecordApiResponse(BaseModel):
    code: int = Field(200, description="响应状态码")
    message: str = Field("success", description="响应消息")
    data: ContractRecordResponse
    meta: dict[str, Any] | None = None
