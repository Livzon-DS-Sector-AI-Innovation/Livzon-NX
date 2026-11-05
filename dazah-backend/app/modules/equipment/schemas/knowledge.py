"""维修知识案例 schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

KnowledgeCaseStatus = Literal["draft", "verified", "dismissed"]

# ORM → Pydantic（model_validate(ORM 对象)）
MODEL_CONFIG_FROM_ATTRIBUTES = ConfigDict(from_attributes=True)


class KnowledgeCaseResponse(BaseModel):
    """维修知识案例"""

    model_config = MODEL_CONFIG_FROM_ATTRIBUTES

    id: uuid.UUID = Field(..., description="案例ID")
    source_work_order_id: uuid.UUID | None = Field(
        default=None, description="来源工单ID"
    )
    equipment_id: uuid.UUID | None = Field(default=None, description="设备ID")
    equipment_name: str | None = Field(default=None, description="设备名称")
    equipment_no: str | None = Field(default=None, description="设备编号")
    workshop_code: str | None = Field(default=None, description="车间代码")
    symptom_code: str | None = Field(default=None, description="故障现象代码")
    symptom_name: str | None = Field(default=None, description="故障现象名称")
    cause_code: str | None = Field(default=None, description="故障原因代码")
    cause_name: str | None = Field(default=None, description="故障原因名称")
    action_code: str | None = Field(default=None, description="维修措施代码")
    action_name: str | None = Field(default=None, description="维修措施名称")
    fault_description: str | None = Field(default=None, description="故障描述")
    repair_summary: str | None = Field(default=None, description="维修过程描述")
    key_steps: list[str] | None = Field(
        default=None, description="关键维修步骤（LLM 抽取，人工确认）"
    )
    parts_used: list[dict[str, Any]] | None = Field(
        default=None, description="使用备件清单"
    )
    status: KnowledgeCaseStatus = Field(..., description="状态")
    verified_by: uuid.UUID | None = Field(default=None, description="确认人ID")
    verified_at: datetime | None = Field(default=None, description="确认时间")
    use_count: int = Field(default=0, description="被推荐采纳次数")
    created_at: datetime | None = Field(default=None, description="创建时间")


class KnowledgeSearchHit(BaseModel):
    """相似案例检索结果条目"""

    id: uuid.UUID = Field(..., description="案例ID")
    equipment_name: str | None = Field(default=None, description="设备名称")
    equipment_no: str | None = Field(default=None, description="设备编号")
    symptom_name: str | None = Field(default=None, description="故障现象")
    cause_name: str | None = Field(default=None, description="故障原因")
    action_name: str | None = Field(default=None, description="维修措施")
    fault_description: str | None = Field(default=None, description="故障描述")
    repair_summary: str | None = Field(default=None, description="维修过程")
    key_steps: list[str] = Field(default_factory=list, description="关键步骤")
    use_count: int = Field(default=0, description="被采纳次数")
    score: float = Field(..., description="匹配分")


class KnowledgeSearchResponse(BaseModel):
    """相似案例检索结果"""

    items: list[KnowledgeSearchHit] = Field(default_factory=list)
