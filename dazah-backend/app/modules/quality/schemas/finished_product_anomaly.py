"""Schemas for finished-product-anomaly AI classification import."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnomalyClassificationImportBody(BaseModel):
    """成品异常 AI 分类结果导入请求（由导出接口产出的 JSON 结构）。"""

    entity_type: str = Field(description="固定 fp_anomaly_classification")
    rows: list[dict[str, Any]] = Field(default_factory=list)
