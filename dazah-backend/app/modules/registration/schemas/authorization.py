"""Authorization letter schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductInfo(BaseModel):
    """授权书产品汇总条目"""

    product_name: str = Field(..., description="产品名称")
    is_fda: bool = Field(False, description="是否为 FDA 申报产品")
    material_count: int = Field(0, description="资料文件数量")
    market_count: int = Field(0, description="市场数量")
    record_count: int = Field(0, description="授权记录总数")
    fda_record_count: int = Field(0, description="FDA 记录数")


class AuthorizationMaterialSummary(BaseModel):
    """授权书资料汇总"""

    total_products: int = Field(..., description="产品总数")
    total_files: int = Field(..., description="资料文件总数")
    fda_products: int = Field(..., description="FDA 产品数")
    fda_files: int = Field(..., description="FDA 文件数")


class AuthorizationOverview(BaseModel):
    """授权书内容总览"""

    total_products: int = Field(..., description="产品总数")
    total_files: int = Field(..., description="文件总数")
    total_markets: int = Field(..., description="市场总数")
    total_records: int = Field(..., description="授权记录总数")
    fda_products: int = Field(..., description="FDA 产品数")
    fda_records: int = Field(..., description="FDA 授权记录数")
    ledger_records: int = Field(..., description="市场台账记录数")


class AuthorizationLedgerOverview(BaseModel):
    """授权台账总览"""

    total_entries: int = Field(..., description="授权总记录数")
    total_products: int = Field(..., description="产品数")
    total_markets: int = Field(..., description="市场数")
    submitted_entries: int = Field(..., description="已递交记录数")
    pending_entries: int = Field(..., description="未递交记录数")


class AuthorizationMaterialListItem(BaseModel):
    """授权书资料列表项"""

    id: str = Field(..., description="资料唯一标识")
    product_name: str = Field(..., description="产品名称")
    category: str = Field(..., description="资料类别")
    market_name: str | None = Field(None, description="市场/地区")
    is_fda: bool = Field(False, description="是否 FDA 资料")
    file_name: str = Field(..., description="文件名")
    file_ext: str = Field(..., description="文件扩展名")
    relative_path: str = Field(..., description="相对源目录路径")
    size_bytes: int = Field(..., description="文件大小（字节）")
    updated_at: datetime = Field(..., description="最后更新时间")


class AuthorizationSourceFile(BaseModel):
    """授权书来源文件"""

    file_name: str = Field(..., description="文件名")
    relative_path: str = Field(..., description="相对源目录路径")
    category: str = Field(..., description="资料类别")
    market_name: str | None = Field(None, description="市场/地区")
    is_fda: bool = Field(False, description="是否 FDA 文件")
    updated_at: datetime = Field(..., description="最后更新时间")
    record_count: int = Field(0, description="解析出的记录数")
    note: str | None = Field(None, description="文件备注或解析提示")


class AuthorizationFdaRecord(BaseModel):
    """FDA 引用授权记录"""

    id: UUID | None = Field(None, description="记录ID")
    product_name: str | None = Field(None, description="产品名称")
    sequence: int = Field(..., description="记录序号")
    company_name: str = Field(..., description="客户名称")
    address: str | None = Field(None, description="地址")
    reference_number: str | None = Field(None, description="引用编号")
    loa_date: str | None = Field(None, description="授权日期")
    submission_date: str | None = Field(None, description="DMF/VMF 递交日期")
    referenced_sections: str | None = Field(None, description="授权引用章节")


class AuthorizationFdaEntryCreate(BaseModel):
    """创建 FDA 授权记录"""

    product_name: str = Field(..., min_length=1, max_length=128, description="产品名称")
    source_sequence: int | None = Field(None, ge=1, description="来源序号")
    company_name: str = Field(
        ..., min_length=1, max_length=512, description="客户/公司名称"
    )
    address: str | None = Field(None, description="地址")
    reference_number: str | None = Field(None, max_length=128, description="引用编号")
    loa_date: str | None = Field(None, max_length=128, description="LOA日期")
    submission_date: str | None = Field(None, max_length=128, description="递交日期")
    referenced_sections: str | None = Field(
        None, max_length=256, description="引用章节"
    )


class AuthorizationFdaEntryUpdate(BaseModel):
    """更新 FDA 授权记录"""

    product_name: str | None = Field(None, min_length=1, max_length=128)
    source_sequence: int | None = Field(None, ge=1)
    company_name: str | None = Field(None, min_length=1, max_length=512)
    address: str | None = None
    reference_number: str | None = Field(None, max_length=128)
    loa_date: str | None = Field(None, max_length=128)
    submission_date: str | None = Field(None, max_length=128)
    referenced_sections: str | None = Field(None, max_length=256)


class AuthorizationLedgerRecord(BaseModel):
    """市场授权台账记录"""

    id: UUID | None = Field(None, description="记录ID")
    product_name: str | None = Field(None, description="产品名称")
    sequence: str = Field(..., description="记录序号")
    market_name: str | None = Field(None, description="市场/地区")
    authorization_file_name: str = Field(..., description="授权文件名称")
    quality_standard: str | None = Field(None, description="质量标准")
    company_name: str | None = Field(None, description="单位名称")
    country: str | None = Field(None, description="国家")
    customer_code: str | None = Field(None, description="客户编号")
    purpose: str | None = Field(None, description="用途")
    authorization_date: str | None = Field(None, description="授权日期")
    handler: str | None = Field(None, description="经手人")
    status: str | None = Field(None, description="授权状态")
    remarks: str | None = Field(None, description="备注")


class AuthorizationMarketGroup(BaseModel):
    """按市场分组的授权台账"""

    market_name: str = Field(..., description="市场/地区")
    file_name: str = Field(..., description="来源文件名")
    relative_path: str = Field(..., description="相对源目录路径")
    note: str | None = Field(None, description="文件备注")
    records: list[AuthorizationLedgerRecord] = Field(
        default_factory=list, description="授权台账记录"
    )


class AuthorizationProductDetail(BaseModel):
    """单个产品的授权书详情"""

    product_name: str = Field(..., description="产品名称")
    is_fda: bool = Field(False, description="是否 FDA 产品")
    material_count: int = Field(0, description="来源文件数")
    market_count: int = Field(0, description="市场数量")
    record_count: int = Field(0, description="记录总数")
    fda_record_count: int = Field(0, description="FDA 记录数")
    fda_records: list[AuthorizationFdaRecord] = Field(
        default_factory=list, description="FDA 授权记录"
    )
    ledger_records: list[AuthorizationLedgerRecord] = Field(
        default_factory=list, description="市场授权台账记录"
    )


class AuthorizationLedgerEntryCreate(BaseModel):
    """创建授权台账记录"""

    product_name: str = Field(..., min_length=1, max_length=128, description="产品名称")
    market_name: str | None = Field(None, max_length=128, description="市场/地区")
    source_sequence: str | None = Field(None, max_length=64, description="来源序号")
    authorization_file_name: str = Field(
        ..., min_length=1, max_length=512, description="授权文件名称"
    )
    quality_standard: str | None = Field(None, max_length=128, description="质量标准")
    company_name: str | None = Field(None, max_length=512, description="单位名称")
    country: str | None = Field(None, max_length=128, description="国家")
    customer_code: str | None = Field(None, max_length=128, description="客户编号")
    purpose: str | None = Field(None, description="用途")
    authorization_date: str | None = Field(None, max_length=64, description="授权日期")
    handler: str | None = Field(None, max_length=128, description="经手人")
    status: str | None = Field(None, max_length=64, description="授权状态")
    remarks: str | None = Field(None, description="备注")


class AuthorizationLedgerEntryUpdate(BaseModel):
    """更新授权台账记录"""

    product_name: str | None = Field(None, min_length=1, max_length=128)
    market_name: str | None = Field(None, max_length=128)
    source_sequence: str | None = Field(None, max_length=64)
    authorization_file_name: str | None = Field(None, min_length=1, max_length=512)
    quality_standard: str | None = Field(None, max_length=128)
    company_name: str | None = Field(None, max_length=512)
    country: str | None = Field(None, max_length=128)
    customer_code: str | None = Field(None, max_length=128)
    purpose: str | None = None
    authorization_date: str | None = Field(None, max_length=64)
    handler: str | None = Field(None, max_length=128)
    status: str | None = Field(None, max_length=64)
    remarks: str | None = None


class AuthorizationLedgerUpdateCreate(BaseModel):
    """创建市场授权更新子行。"""

    model_config = ConfigDict(extra="forbid")

    authorization_date: str | None = Field(None, max_length=64, description="授权日期")
    handler: str | None = Field(None, max_length=128, description="经手人")
    remarks: str | None = Field(None, description="更新备注")


class AuthorizationLedgerUpdateUpdate(BaseModel):
    """编辑市场授权更新子行。"""

    model_config = ConfigDict(extra="forbid")

    authorization_date: str | None = Field(None, max_length=64, description="授权日期")
    handler: str | None = Field(None, max_length=128, description="经手人")
    remarks: str | None = Field(None, description="更新备注")


class AuthorizationLedgerUpdateRead(BaseModel):
    """市场授权更新子行读取结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ledger_main_id: UUID
    sort_order: int
    authorization_date: str | None = None
    handler: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime


class AuthorizationLedgerMainCreate(BaseModel):
    """创建市场授权主记录。"""

    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(..., min_length=1, max_length=128, description="产品名称")
    market_name: str | None = Field(None, max_length=128, description="市场/地区")
    source_sequence: str | None = Field(None, max_length=64, description="来源序号")
    authorization_file_name: str = Field(
        ..., min_length=1, max_length=512, description="授权文件名称"
    )
    quality_standard: str | None = Field(None, max_length=128, description="质量标准")
    company_name: str | None = Field(None, max_length=512, description="单位名称")
    country: str | None = Field(None, max_length=128, description="国家")
    customer_code: str | None = Field(None, max_length=128, description="客户编号")
    purpose: str | None = Field(None, description="用途")
    status: str | None = Field(None, max_length=64, description="授权状态")
    initial_update: AuthorizationLedgerUpdateCreate = Field(
        ..., description="首次录入的首行更新信息"
    )


class AuthorizationLedgerMainUpdate(BaseModel):
    """编辑市场授权主记录。"""

    model_config = ConfigDict(extra="forbid")

    product_name: str | None = Field(
        None, min_length=1, max_length=128, description="产品名称"
    )
    market_name: str | None = Field(None, max_length=128, description="市场/地区")
    source_sequence: str | None = Field(None, max_length=64, description="来源序号")
    authorization_file_name: str | None = Field(
        None, min_length=1, max_length=512, description="授权文件名称"
    )
    quality_standard: str | None = Field(None, max_length=128, description="质量标准")
    company_name: str | None = Field(None, max_length=512, description="单位名称")
    country: str | None = Field(None, max_length=128, description="国家")
    customer_code: str | None = Field(None, max_length=128, description="客户编号")
    purpose: str | None = Field(None, description="用途")
    status: str | None = Field(None, max_length=64, description="授权状态")


class AuthorizationLedgerMainRead(BaseModel):
    """市场授权主记录读取结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_name: str
    market_name: str | None = None
    source_sequence: str | None = None
    authorization_file_name: str
    quality_standard: str | None = None
    company_name: str | None = None
    country: str | None = None
    customer_code: str | None = None
    purpose: str | None = None
    status: str | None = None
    created_at: datetime
    updated_at: datetime
    updates: list[AuthorizationLedgerUpdateRead] = Field(
        default_factory=list, description="更新子行"
    )


class AuthorizationLedgerGroupedOverview(BaseModel):
    """市场授权分层列表概览。"""

    total_main_records: int = Field(..., description="主记录数")
    total_update_records: int = Field(..., description="更新子行数")
    total_products: int = Field(..., description="产品数")
    total_markets: int = Field(..., description="市场数")
    submitted_main_records: int = Field(..., description="已递交主记录数")
    pending_main_records: int = Field(..., description="未递交主记录数")


class AuthorizationLetterCreate(BaseModel):
    """生成授权书请求"""

    product_name: str = Field(
        ..., max_length=128, description="产品名称（对照表标准名）"
    )
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
    """生成发补回复请求。"""

    drug_name: str | None = Field(None, max_length=128, description="药品名称")
    registration_number: str | None = Field(None, max_length=64, description="登记号")
    acceptance_number: str | None = Field(None, max_length=64, description="受理号")
    company_name: str | None = Field(
        None, max_length=256, description="申请人/公司名称"
    )
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


class ReferenceStandardCreate(BaseModel):
    """生成对照物质说明表请求。"""

    drug_name: str = Field(..., max_length=128, description="药品名称")
    reference_substance_name: str | None = Field(
        None, max_length=256, description="对照物质名称"
    )
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
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    drug_name: str
    reference_substance_name: str | None = None
    batch_number: str | None = None
    manufacturer: str | None = None
    output_file_name: str
    created_at: datetime | None = None
