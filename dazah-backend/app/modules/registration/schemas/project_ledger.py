"""Project ledger schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectLedgerColumn(BaseModel):
    """Single workbook column definition."""

    key: str = Field(..., description="字段键")
    label: str = Field(..., description="字段标题")


class ProjectLedgerHistoryRecord(BaseModel):
    """Single historical snapshot inside one project ledger group."""

    entry_id: uuid.UUID = Field(..., description="版本记录ID")
    version: int = Field(..., description="版本序号")
    source_row_number: int | None = Field(None, description="Excel 原始行号")
    values: dict[str, str | None] = Field(
        default_factory=dict, description="当前版本字段值"
    )


class ProjectLedgerRecord(BaseModel):
    """Collapsed project ledger row."""

    record_id: uuid.UUID = Field(..., description="主记录ID")
    record_key: str = Field(..., description="记录唯一键")
    sequence: int = Field(..., description="主记录序号")
    latest_values: dict[str, str | None] = Field(
        default_factory=dict, description="最新版本字段值"
    )
    history_count: int = Field(..., description="历史版本数量")
    history_records: list[ProjectLedgerHistoryRecord] = Field(
        default_factory=list,
        description="完整历史版本列表",
    )


class ProjectLedgerRecordHistory(BaseModel):
    """Single project ledger record history payload."""

    record_id: uuid.UUID = Field(..., description="主记录ID")
    sheet_key: str = Field(..., description="子表键")
    sequence: int = Field(..., description="主记录序号")
    history_count: int = Field(..., description="历史版本数量")
    history_records: list[ProjectLedgerHistoryRecord] = Field(
        default_factory=list,
        description="完整历史版本列表",
    )


class ProjectLedgerSheetSummary(BaseModel):
    """Sheet-level summary."""

    sheet_key: str = Field(..., description="子表键")
    sheet_name: str = Field(..., description="子表名称")
    title: str = Field(..., description="子表标题")
    total_records: int = Field(..., description="主表记录数")
    records_with_history: int = Field(..., description="存在历史版本的记录数")
    total_history_versions: int = Field(..., description="历史版本总数")


class ProjectLedgerSheetDetail(BaseModel):
    """Single project ledger sheet detail."""

    sheet_key: str = Field(..., description="子表键")
    sheet_name: str = Field(..., description="子表名称")
    title: str = Field(..., description="子表标题")
    columns: list[ProjectLedgerColumn] = Field(
        default_factory=list, description="字段定义"
    )
    records: list[ProjectLedgerRecord] = Field(
        default_factory=list, description="主表记录"
    )
    summary: ProjectLedgerSheetSummary = Field(..., description="子表汇总")


class ProjectLedgerWorkbookOverview(BaseModel):
    """Workbook-level project ledger overview."""

    workbook_name: str = Field(..., description="工作簿名称")
    updated_at: datetime | None = Field(None, description="工作簿更新时间")
    total_records: int = Field(..., description="主表记录总数")
    records_with_history: int = Field(..., description="存在历史版本的记录总数")
    total_history_versions: int = Field(..., description="历史版本总数")
    sheets: list[ProjectLedgerSheetDetail] = Field(
        default_factory=list, description="四个子表明细"
    )


class ProjectLedgerWorkbookDetail(BaseModel):
    """Workbook-level detail for import/export flows."""

    workbook_name: str = Field(..., description="工作簿名称")
    updated_at: datetime | None = Field(None, description="模板更新时间")
    total_records: int = Field(..., description="主表记录总数")
    sheets: list[ProjectLedgerSheetDetail] = Field(
        default_factory=list, description="四个子表详情"
    )


class ProjectLedgerWorkbookImportResult(BaseModel):
    """Workbook import result."""

    workbook_name: str = Field(..., description="导入工作簿名称")
    imported_records: int = Field(..., description="成功导入的主记录数")
    sheet_record_counts: dict[str, int] = Field(
        default_factory=dict, description="各子表导入记录数"
    )


class ProjectLedgerWorkbookExportArtifact(BaseModel):
    """Workbook export artifact metadata."""

    file_path: str = Field(..., description="导出文件绝对路径")
    download_name: str = Field(..., description="下载文件名")


class ProjectLedgerEntryInput(BaseModel):
    """Create/update payload."""

    sheet_key: str = Field(..., description="子表键")
    values: dict[str, str | None] = Field(default_factory=dict, description="字段值")


class ProjectLedgerEntryResponse(BaseModel):
    """Write operation response."""

    record_id: uuid.UUID = Field(..., description="主记录ID")
    sheet_key: str = Field(..., description="子表键")
    version_number: int = Field(..., description="当前版本号")
    sequence: int = Field(..., description="主记录序号")
    values: dict[str, str | None] = Field(
        default_factory=dict, description="当前字段值"
    )
