"""Safety request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.safety.schemas.enums import (
    RevisionType,
)


class OperationRegulationBase(BaseModel):
    """安全操作规程基础模式"""

    regulation_no: str | None = Field(
        None, max_length=64, description="操规编号（可选，由文控/车间编号时填写）"
    )
    regulation_name: str = Field(..., max_length=255, description="操规名称")
    document_path: str | None = Field(None, max_length=500, description="操规文档路径")
    document_original_name: str | None = Field(
        None, max_length=255, description="文档原始文件名"
    )
    position: str | None = Field(
        None, max_length=100, description="岗位（达托/达巴，逗号分隔）"
    )
    workshop: str | None = Field(
        None, max_length=60, description="车间/部门（如 103车间、201二车间、动力部）"
    )
    notes: str | None = Field(None, description="备注")


class OperationRegulationCreate(OperationRegulationBase):
    """创建安全操作规程"""

    pass


class OperationRegulationUpdate(BaseModel):
    """更新安全操作规程"""

    regulation_no: str | None = Field(None, max_length=64, description="操规编号")
    regulation_name: str | None = Field(None, max_length=255, description="操规名称")
    document_path: str | None = Field(None, max_length=500, description="操规文档路径")
    document_original_name: str | None = Field(
        None, max_length=255, description="文档原始文件名"
    )
    position: str | None = Field(None, max_length=100, description="岗位")
    workshop: str | None = Field(None, max_length=60, description="车间/部门")
    notes: str | None = Field(None, description="备注")
    content: str | None = Field(None, description="标准化 Markdown 内容")
    status: str | None = Field(None, max_length=20, description="操规状态")


class OperationRegulationResponse(OperationRegulationBase):
    """安全操作规程响应"""

    id: uuid.UUID
    content: str | None = Field(None, description="标准化 Markdown 内容")
    status: str = Field("draft", description="操规状态")
    source_document_path: str | None = Field(
        None, max_length=500, description="原始上传文件路径"
    )
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== 操规修订记录 Schemas ====================


class RegulationRevisionBase(BaseModel):
    """修订记录基础模式"""

    revision_no: str = Field(..., max_length=64, description="修订编号")
    regulation_id: uuid.UUID = Field(..., description="关联操规ID")
    regulation_name: str = Field(..., max_length=255, description="安全操规名称")
    old_document_path: str | None = Field(
        None, max_length=500, description="旧文档路径"
    )
    reviser: uuid.UUID | None = Field(None, description="修订人")
    reviser_name: str | None = Field(None, max_length=100, description="修订人姓名")
    revision_time: datetime = Field(..., description="修订时间")
    revision_type: RevisionType = Field(RevisionType.MANUAL, description="修订类型")
    revision_opinion: str | None = Field(None, description="修订意见/内容")
    revision_scope: str | None = Field(None, max_length=100, description="修订范围")
    new_document_path: str | None = Field(
        None, max_length=500, description="新文档路径"
    )
    notes: str | None = Field(None, description="备注")


class RegulationRevisionCreate(BaseModel):
    """创建修订记录"""

    revision_no: str = Field(..., max_length=64, description="修订编号")
    regulation_id: uuid.UUID = Field(..., description="关联操规ID")
    revision_type: RevisionType = Field(RevisionType.MANUAL, description="修订类型")
    revision_opinion: str | None = Field(None, description="修订意见/内容")
    reviser: uuid.UUID | None = Field(None, description="修订人")
    reviser_name: str | None = Field(None, max_length=100, description="修订人姓名")
    notes: str | None = Field(None, description="备注")


class RegulationRevisionUpdate(BaseModel):
    """更新修订记录"""

    revision_opinion: str | None = Field(None, description="修订意见/内容")
    revision_scope: str | None = Field(None, max_length=100, description="修订范围")
    review_opinion: str | None = Field(None, max_length=32, description="审核意见")
    new_document_path: str | None = Field(
        None, max_length=500, description="新文档路径"
    )
    notes: str | None = Field(None, description="备注")


class RegulationRevisionAIDiff(BaseModel):
    """AI 差异识别请求"""

    old_content: str | None = Field(None, description="旧文档内容")
    new_content: str = Field(..., description="新文档内容（修订人发送的）")


class RegulationRevisionAIGenerate(BaseModel):
    """AI 生成修订版本请求"""

    regulation_name: str = Field(..., description="操规名称")
    current_content: str = Field(..., description="当前操规内容")
    revision_opinion: str = Field(..., description="修订意见")


class RegulationRevisionResponse(RegulationRevisionBase):
    """修订记录响应"""

    id: uuid.UUID
    review_opinion: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== 修订范围 AI 识别 Schemas ====================


class RevisionScopeIdentifyRequest(BaseModel):
    """AI 识别修订范围请求"""

    revision_opinion: str = Field(..., description="修订意见内容")
    revision_type: RevisionType = Field(..., description="修订类型")


class RevisionScopeIdentifyResponse(BaseModel):
    """AI 识别修订范围响应"""

    scope: str = Field(
        ..., description="识别的修订范围（逗号分隔: process/safety_requirement）"
    )
    reasoning: str = Field(..., description="识别依据说明")


# ==================== SOP 标准化生成 Schemas ====================


class SopMeta(BaseModel):
    """SOP 元信息（从文档提取）"""

    product_name: str = Field("", description="产品名称")
    post_name: str = Field("", description="岗位名称")
    department: str = Field("", description="所属部门")
    doc_number: str = Field("", description="文件编号")
    effective_date: str = Field("", description="生效日期")
    company_name: str = Field("", description="公司名称")


class SopGenerateResponse(BaseModel):
    """SOP 标准化生成响应"""

    regulation_id: uuid.UUID = Field(..., description="操规记录 ID")
    meta: SopMeta = Field(..., description="提取的元信息")
    content: str = Field(..., description="生成的标准化 Markdown 内容（9 章）")
    status: str = Field("generated", description="生成状态")


class SopContentUpdate(BaseModel):
    """更新 SOP 标准化内容"""

    content: str = Field(..., description="编辑后的标准化 Markdown 内容")
    status: str | None = Field(None, max_length=20, description="新状态（可选）")


# ==================== 操规批量上传（自动识别） Schemas ====================


class RegulationRecognizedInfo(BaseModel):
    """从文件名/内容自动识别出的操规归属信息"""

    workshop: str = Field("", max_length=60, description="识别的车间/部门")
    position: str = Field("", max_length=100, description="识别的岗位")
    title: str = Field("", max_length=255, description="识别的操规名称")
    recognized_by: str = Field(
        "heuristic", description="识别方式: heuristic(文件名规则)/ai(大模型)"
    )


class RegulationBatchUploadItem(BaseModel):
    """批量上传单文件处理结果"""

    file_name: str = Field(..., description="上传文件名")
    ok: bool = Field(..., description="是否导入成功")
    regulation_id: uuid.UUID | None = Field(None, description="创建的操规ID")
    regulation_no: str = Field("", description="生成的操规编号")
    regulation_name: str = Field("", description="操规名称")
    workshop: str = Field("", description="车间/部门")
    position: str = Field("", description="岗位")
    recognized_by: str = Field("", description="识别方式")
    message: str = Field("", description="失败原因或补充说明")


class RegulationBatchUploadResponse(BaseModel):
    """批量上传汇总结果"""

    items: list[RegulationBatchUploadItem] = Field(default_factory=list)
    success_count: int = Field(0, ge=0)
    fail_count: int = Field(0, ge=0)


# ==================== 操规合规审核 Schemas ====================


class RegulationReviewItem(BaseModel):
    """审核问题项（缺失项/不合规项）"""

    item: str = Field("", description="问题项名称")
    requirement: str = Field("", description="法规/规范要求")
    basis: str = Field("", description="依据（法规名称与条款）")
    severity: str = Field("建议", description="严重程度: 严重/一般/建议")
    suggestion: str = Field("", description="整改建议")


class RegulationReviewResponse(BaseModel):
    """操规合规审核记录响应"""

    id: uuid.UUID
    regulation_id: uuid.UUID
    regulation_name: str
    result: str = Field(..., description="审核结论: pass/conditional_pass/fail")
    score: int = Field(..., ge=0, le=100, description="合规评分")
    summary: str = Field("", description="总体评价")
    missing_items: list[RegulationReviewItem] = Field(default_factory=list)
    non_compliant_items: list[RegulationReviewItem] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    reviewed_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RegulationReviewListResponse(BaseModel):
    """操规审核记录列表"""

    items: list[RegulationReviewResponse] = Field(default_factory=list)
    total: int = Field(0, ge=0)


class RegulationLatestReviewEntry(BaseModel):
    """操规最新审核状态（用于台账列表列展示）"""

    regulation_id: uuid.UUID
    result: str
    score: int
    reviewed_at: datetime
