"""Safety request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AIWorkflowConfigBase(BaseModel):
    """AI 工作流配置基础模式"""

    module_code: str = Field(..., max_length=64, description="模块代码")
    workflow_name: str = Field(..., max_length=128, description="工作流名称")
    workflow_description: str | None = Field(None, description="工作流描述")
    trigger_event: str | None = Field(None, max_length=64, description="触发事件")
    is_enabled: bool = Field(True, description="是否启用")
    script_configs: list[dict] | dict | None = Field(None, description="脚本配置 JSON")
    sort_order: int = Field(0, description="排序顺序")
    notes: str | None = Field(None, description="备注")


class AIWorkflowConfigCreate(BaseModel):
    """创建 AI 工作流配置"""
    module_code: str = Field(..., max_length=64, description="模块代码")
    workflow_name: str = Field(..., max_length=128, description="工作流名称")
    workflow_description: str | None = Field(None, description="工作流描述")
    trigger_event: str | None = Field(None, max_length=64, description="触发事件")
    is_enabled: bool = Field(True, description="是否启用")
    script_configs: list[dict] | dict | None = Field(None, description="脚本配置 JSON")
    sort_order: int = Field(0, description="排序顺序")
    notes: str | None = Field(None, description="备注")


class AIWorkflowConfigUpdate(BaseModel):
    """更新 AI 工作流配置"""
    module_code: str | None = Field(None, max_length=64, description="模块代码")
    workflow_name: str | None = Field(None, max_length=128, description="工作流名称")
    workflow_description: str | None = Field(None, description="工作流描述")
    trigger_event: str | None = Field(None, max_length=64, description="触发事件")
    is_enabled: bool | None = Field(None, description="是否启用")
    script_configs: list[dict] | dict | None = Field(None, description="脚本配置 JSON")
    sort_order: int | None = Field(None, description="排序顺序")
    notes: str | None = Field(None, description="备注")


class AIWorkflowConfigResponse(AIWorkflowConfigBase):
    """AI 工作流配置响应"""
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== AI 工作流附件 Schemas ====================


class ReferenceAttachmentResponse(BaseModel):
    """调用文档附件响应"""

    id: str = Field(..., description="附件唯一标识 (UUID)")
    type: str = Field(..., description="附件类型: file / knowledge")
    name: str = Field(..., description="显示名称")
    url: str = Field(..., description="预览 URL")
    original_name: str | None = Field(None, description="原始文件名")
    file_type: str | None = Field(None, description="文件类型: pdf / docx / xlsx / txt / md")
    file_size: int | None = Field(None, description="文件大小（字节）")
    markdown_path: str | None = Field(None, description="Markdown 转换文件路径（AI 读取用）")
    knowledge_id: str | None = Field(None, description="知识库文章 ID（type=knowledge 时）")
    created_at: str = Field(..., description="创建时间 ISO 字符串")


class KnowledgeAttachmentRequest(BaseModel):
    """从知识库创建附件请求"""

    knowledge_ids: list[str] = Field(..., description="知识库文章 ID 列表")


