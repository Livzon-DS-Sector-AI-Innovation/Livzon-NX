"""Generic Feishu record write schemas for quality inspection sub-modules."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InspectionFeishuRecordBody(BaseModel):
    """通用飞书记录写操作请求体（字段名 = 飞书表真实字段名）。"""

    fields: dict[str, Any] = Field(default_factory=dict)
