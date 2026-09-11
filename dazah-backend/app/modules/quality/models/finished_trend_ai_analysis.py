"""Finished product trend AI analysis persistence model.

Stores deterministic trend-rule anomalies (continuous move / slope break /
mean shift / month-over-month) and their optional AI interpretation, with the
chart payload needed to re-render and re-analyze asynchronously. Doubles as the
dedup ledger so re-opening the dashboard does not re-push or re-bill the same
trend anomaly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class FinishedTrendAIAnalysis(BaseModel):
    """A deduplicated trend anomaly + AI analysis record for one metric."""

    __tablename__ = "quality_finished_trend_ai_analyses"
    __table_args__ = (
        # 软删除语义：仅未删除行唯一（重分析=软删旧行再建新行）
        Index(
            "uq_quality_finished_trend_ai_analysis_key",
            "entity_code",
            "metric_key",
            "rule_type",
            "trend_end_batch",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_quality_finished_trend_ai_analysis_entity_metric",
            "entity_code",
            "metric_key",
        ),
        {"schema": "quality"},
    )

    entity_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 前端趋势页深链片段（如 mpa/mvt/...），推送卡片按钮跳转用
    frontend_group: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metric_key: Mapped[str] = mapped_column(String(256), nullable=False)
    metric_label: Mapped[str] = mapped_column(String(256), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    trend_start_batch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trend_end_batch: Mapped[str] = mapped_column(String(128), nullable=False)
    # 规则命中的受影响批次列表（前端高亮 + 卡片图标注）
    affected_batches: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    # 确定性规则产出的事实描述与证据
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # 重渲染/重分析所需序列快照：points + spec_lines + mean/std/control_limit
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # LLM 结构化结论（经白名单校验后）；无配置/失败时为空
    ai_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feishu_image_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    feishu_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
