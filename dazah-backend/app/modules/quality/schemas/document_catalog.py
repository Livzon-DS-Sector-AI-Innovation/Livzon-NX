"""Document catalog schemas (各部门文件目录管理)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentDepartmentBase(BaseModel):
    """Shared document department fields."""

    name: str = Field(..., min_length=1, max_length=255, description="部门名称")
    sort_order: int = Field(default=0, description="排序序号")


class CreateDocumentDepartmentRequest(DocumentDepartmentBase):
    """Create document department request."""


class UpdateDocumentDepartmentRequest(BaseModel):
    """Update document department request."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = None


class DocumentDepartmentOut(DocumentDepartmentBase):
    """Document department output."""

    id: UUID
    document_count: int = Field(default=0, description="文件条目数量")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentEntryBase(BaseModel):
    """Shared document entry fields."""

    department_id: UUID = Field(..., description="所属部门ID")
    seq_no: int | None = Field(default=None, description="序号")
    name: str = Field(..., min_length=1, max_length=500, description="文件名称")
    code: str | None = Field(default=None, max_length=255, description="文件编码")
    effective_date: date | None = Field(default=None, description="生效日期")
    effective_date_text: str | None = Field(
        default=None, max_length=32, description="生效日期原始文本"
    )


class CreateDocumentEntryRequest(DocumentEntryBase):
    """Create document entry request."""


class UpdateDocumentEntryRequest(BaseModel):
    """Update document entry request."""

    department_id: UUID | None = None
    seq_no: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=500)
    code: str | None = Field(default=None, max_length=255)
    effective_date: date | None = None
    effective_date_text: str | None = Field(default=None, max_length=32)


class DocumentEntryAttachmentOut(BaseModel):
    """Document entry attachment item."""

    file_name: str = Field(..., description="附件文件名")
    storage_key: str = Field(..., description="原始文件存储 key")
    converted_md_key: str | None = Field(
        default=None, description="转换后标准 MD 存储 key（仅 word 附件）"
    )
    content_type: str | None = Field(default=None, description="文件 MIME 类型")
    file_size: int | None = Field(default=None, description="文件大小（字节）")
    converted: bool = Field(default=True, description="是否已转换（图片/PDF 为 false）")
    uploaded_at: datetime | None = Field(default=None, description="上传时间")
    uploaded_by: str | None = Field(default=None, description="上传人")

    model_config = ConfigDict(from_attributes=True)


class DocumentEntryOut(DocumentEntryBase):
    """Document entry output."""

    id: UUID
    source_file: str | None = None
    attachments: list[DocumentEntryAttachmentOut] | None = Field(
        default_factory=list, description="附件列表"
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UploadDocumentEntryAttachmentResult(BaseModel):
    """Attachment upload/bind result."""

    entry_id: UUID | None = Field(
        default=None, description="绑定条目 ID（未匹配时为空）"
    )
    entry_name: str | None = Field(default=None, description="绑定条目名称")
    matched: bool = Field(default=True, description="是否自动匹配到唯一条目")
    attachment: DocumentEntryAttachmentOut
    message: str | None = Field(default=None, description="提示信息（如未匹配明细）")


class DocumentEntryLookupOut(BaseModel):
    """按名称查询最新版文件编号的输出。"""

    name: str
    code: str | None = None
    effective_date: date | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentEntryResolveQuery(BaseModel):
    """单个待解析文件的查询项（培训勾选时锁定的条目）。"""

    name: str = Field(
        ..., description="文件名称（展示与 entry_id 未提供时的名称匹配兜底）"
    )
    entry_id: UUID | None = Field(
        default=None,
        description="勾选时锁定的条目 ID；提供时严格按 ID 读取，未命中不回退名称匹配",
    )


class DocumentEntryResolveRequest(BaseModel):
    """批量解析文件条目并读取附件内容请求（供培训 AI 出题使用）。"""

    # 不限数量：培训勾选教材份数不设上限（2026-08-12
    # 业务确认），请求体大小由网关/框架默认限制兜底
    entries: list[DocumentEntryResolveQuery] = Field(
        default_factory=list,
        description="按勾选条目解析（优先；entry_id 精确读取，杜绝名称误匹配）",
    )
    names: list[str] = Field(
        default_factory=list, description="按文件名称解析（旧客户端兜底，取名称最新版）"
    )

    @model_validator(mode="after")
    def _require_entries_or_names(self) -> DocumentEntryResolveRequest:
        if not self.entries and not self.names:
            raise ValueError("entries 与 names 至少提供一个")
        return self


class ResolveAttachmentContent(BaseModel):
    """解析出的单个附件标准 MD 文本内容。"""

    file_name: str = Field(..., description="附件文件名")
    md_text: str = Field(..., description="标准 MD 文本内容")


class DocumentEntryResolveItem(BaseModel):
    """单个文件名称的解析结果。"""

    name: str = Field(..., description="请求的文件名称")
    code: str | None = Field(default=None, description="匹配到的文件编码")
    entry_id: UUID | None = Field(
        default=None, description="匹配到的条目 ID（未匹配为空）"
    )
    matched: bool = Field(default=False, description="是否匹配到条目")
    attachments: list[ResolveAttachmentContent] = Field(
        default_factory=list, description="附件标准 MD 内容列表"
    )


class DocumentEntryResolveResult(BaseModel):
    """resolve-content 批量解析响应。"""

    results: list[DocumentEntryResolveItem] = Field(default_factory=list)


class DocumentCatalogImportSheetResult(BaseModel):
    """单个 Sheet（部门）的导入结果。"""

    sheet_name: str
    department_id: UUID
    imported_count: int


class DocumentCatalogImportResult(BaseModel):
    """Excel 导入结果汇总。"""

    source_file: str
    department_count: int
    entry_count: int
    sheets: list[DocumentCatalogImportSheetResult] = Field(default_factory=list)


class BatchImportAttachmentResultItem(BaseModel):
    """单个附件文件的导入结果。"""

    file_name: str = Field(..., description="附件文件名")
    matched: bool = Field(default=False, description="是否匹配到条目")
    match_type: str = Field(
        default="none", description="匹配方式：name/code/content/llm/none"
    )
    entry_id: UUID | None = Field(default=None, description="绑定条目 ID")
    entry_name: str | None = Field(default=None, description="绑定条目名称")
    entry_code: str | None = Field(default=None, description="绑定条目文件编码")
    version_updated: bool = Field(
        default=False, description="是否自动升级了条目文件编码版本"
    )
    old_code: str | None = Field(
        default=None, description="版本升级前的文件编码（未升级为空）"
    )
    new_code: str | None = Field(
        default=None, description="版本升级后的文件编码（未升级为空）"
    )


class BatchImportDocumentAttachmentsResult(BaseModel):
    """统一导入附件结果汇总。"""

    bound: int = Field(default=0, description="成功绑定附件数")
    failed: int = Field(default=0, description="未匹配文件数")
    version_updated_count: int = Field(
        default=0, description="文件编码版本自动升级数"
    )
    results: list[BatchImportAttachmentResultItem] = Field(default_factory=list)
