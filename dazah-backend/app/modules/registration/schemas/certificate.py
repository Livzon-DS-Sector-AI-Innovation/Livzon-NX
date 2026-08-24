"""Certificate dashboard schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CertificateColumn(BaseModel):
    """Single sheet column definition."""

    key: str = Field(..., description="字段键")
    label: str = Field(..., description="列标题")


class CertificateRecordSummary(BaseModel):
    """Compact certificate record for dashboard lists."""

    id: str = Field(..., description="记录唯一标识")
    sheet_key: str = Field(..., description="子表键")
    sheet_name: str = Field(..., description="子表名称")
    certificate_name: str = Field(..., description="证照名称")
    certificate_number: str | None = Field(None, description="证书编号/编号")
    authority: str | None = Field(None, description="发证机关")
    issue_date: str | None = Field(None, description="发证日期")
    expiry_date: str | None = Field(None, description="到期日期")
    expiry_status: str = Field(..., description="到期状态")
    product_scope: str | None = Field(None, description="产品范围")
    remarks: str | None = Field(None, description="备注")


class CertificateSheetSummary(BaseModel):
    """Sheet-level metrics for dashboard cards."""

    sheet_key: str = Field(..., description="子表键")
    sheet_name: str = Field(..., description="子表名称")
    title: str = Field(..., description="子表标题")
    total_records: int = Field(..., description="记录总数")
    issuer_count: int = Field(..., description="发证机关数量")
    product_count: int = Field(..., description="产品范围数量")
    expired_count: int = Field(..., description="已过期数量")
    due_90_count: int = Field(..., description="90天内到期数量")
    total_pages: int = Field(..., description="累计页数")


class CertificateSheetRow(BaseModel):
    """Single certificate row in a sheet."""

    id: str = Field(..., description="记录唯一标识")
    sequence: int = Field(..., description="显示序号")
    values: dict[str, str | None] = Field(
        default_factory=dict, description="字段值映射"
    )
    issue_date: str | None = Field(None, description="发证日期")
    expiry_date: str | None = Field(None, description="到期日期")
    expiry_status: str = Field(..., description="到期状态")


class CertificateEntryInput(BaseModel):
    """可编辑的证书台账字段。"""

    sheet_key: str = Field(..., description="子表键")
    certificate_name: str = Field(
        ..., min_length=1, max_length=512, description="证照名称"
    )
    acceptance_number: str | None = Field(None, max_length=255, description="受理号")
    approval_number: str | None = Field(None, max_length=255, description="批件号")
    certificate_number: str | None = Field(
        None, max_length=255, description="证书编号/编号"
    )
    issuing_authority: str | None = Field(None, description="发证机关")
    issue_date: str | None = Field(None, max_length=64, description="发证日期")
    validity_period: str | None = Field(None, description="有效期/复验期")
    product_scope: str | None = Field(None, description="产品范围")
    quality_standard: str | None = Field(None, description="质量标准")
    page_count: int | None = Field(None, ge=0, description="页数")
    remarks: str | None = Field(None, description="备注")


class CertificateEntryCreate(CertificateEntryInput):
    """创建证书台账记录。"""

    source_sequence: int | None = Field(None, ge=1, description="来源序号")


class CertificateEntryUpdate(BaseModel):
    """更新证书台账记录。"""

    certificate_name: str | None = Field(None, min_length=1, max_length=512)
    acceptance_number: str | None = Field(None, max_length=255)
    approval_number: str | None = Field(None, max_length=255)
    certificate_number: str | None = Field(None, max_length=255)
    issuing_authority: str | None = None
    issue_date: str | None = Field(None, max_length=64)
    validity_period: str | None = None
    product_scope: str | None = None
    quality_standard: str | None = None
    page_count: int | None = Field(None, ge=0)
    remarks: str | None = None


class CertificateEntryResponse(CertificateEntryInput):
    """证书台账记录响应。"""

    id: UUID = Field(..., description="记录ID")
    sheet_name: str = Field(..., description="子表名称")
    sheet_title: str = Field(..., description="子表标题")
    source_sequence: int | None = Field(None, description="来源序号")
    expiry_date: str | None = Field(None, description="到期日期")
    expiry_status: str = Field(..., description="到期状态")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class CertificateSheetDetail(BaseModel):
    """Full sheet data for a detail page."""

    sheet_key: str = Field(..., description="子表键")
    sheet_name: str = Field(..., description="子表名称")
    title: str = Field(..., description="子表标题")
    source_file_name: str = Field(..., description="来源文件名")
    updated_at: datetime | None = Field(None, description="来源文件更新时间")
    columns: list[CertificateColumn] = Field(default_factory=list, description="列定义")
    rows: list[CertificateSheetRow] = Field(
        default_factory=list, description="子表记录"
    )
    summary: CertificateSheetSummary = Field(..., description="子表汇总")


class CertificateWorkbookSheet(BaseModel):
    """Sheet payload inside workbook detail."""

    sheet_key: str = Field(..., description="子表键")
    sheet_name: str = Field(..., description="子表名称")
    title: str = Field(..., description="子表标题")
    columns: list[CertificateColumn] = Field(default_factory=list, description="列定义")
    rows: list[CertificateSheetRow] = Field(
        default_factory=list, description="子表完整记录"
    )
    summary: CertificateSheetSummary = Field(..., description="子表汇总")


class CertificateWorkbookDetail(BaseModel):
    """Workbook detail containing all named sheets."""

    workbook_name: str = Field(..., description="工作簿名称")
    updated_at: datetime | None = Field(None, description="工作簿更新时间")
    sheets: list[CertificateWorkbookSheet] = Field(
        default_factory=list, description="整本子表列表"
    )


class CertificateWorkbookOverview(BaseModel):
    """Workbook-level dashboard overview."""

    workbook_name: str = Field(..., description="工作簿名称")
    updated_at: datetime | None = Field(None, description="工作簿更新时间")
    total_records: int = Field(..., description="证书总数")
    sheet_count: int = Field(..., description="子表数量")
    issuer_count: int = Field(..., description="发证机关总数")
    product_count: int = Field(..., description="产品范围总数")
    expired_count: int = Field(..., description="已过期数量")
    due_90_count: int = Field(..., description="90天内到期数量")
    total_pages: int = Field(..., description="累计页数")
    sheet_summaries: list[CertificateSheetSummary] = Field(
        default_factory=list, description="各子表汇总"
    )
    upcoming_expirations: list[CertificateRecordSummary] = Field(
        default_factory=list, description="近期到期清单"
    )
    recent_issued: list[CertificateRecordSummary] = Field(
        default_factory=list, description="最新发证清单"
    )


class CertificateWorkbookImportResult(BaseModel):
    """Whole workbook import result."""

    workbook_name: str = Field(..., description="导入工作簿名称")
    imported_sheet_count: int = Field(..., description="导入子表数量")
    imported_record_count: int = Field(..., description="导入记录数量")
    replaced_record_count: int = Field(..., description="被覆盖的旧记录数量")


class CertificateReminderRecipientOption(BaseModel):
    """证书提醒接收人选项。"""

    open_id: str = Field(..., description="飞书 open_id")
    name: str = Field(..., description="联系人姓名")
    department: str | None = Field(None, description="所属部门")
    enterprise_email: str | None = Field(None, description="企业邮箱")


class CertificateReminderSettingUpdate(BaseModel):
    """证书到期提醒配置入参。"""

    is_enabled: bool = Field(..., description="是否启用自动提醒")
    reminder_days: int = Field(..., ge=1, le=365, description="提前提醒天数")
    recipient_open_id: str | None = Field(None, description="接收人飞书 open_id")


class CertificateReminderSettingResponse(BaseModel):
    """证书到期提醒配置响应。"""

    is_enabled: bool = Field(..., description="是否启用自动提醒")
    reminder_days: int = Field(..., description="提前提醒天数")
    recipient_open_id: str | None = Field(None, description="接收人飞书 open_id")
    recipient_name: str | None = Field(None, description="接收人姓名")
    recipient_department: str | None = Field(None, description="接收人所属部门")
    pending_count: int = Field(..., description="当前规则命中的待提醒证书数")
