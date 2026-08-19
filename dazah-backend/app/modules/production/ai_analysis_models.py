"""AI 分析结果存储模型"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, String, Text, Boolean, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel


class AiAnalysis(BaseModel):
    """AI 分析记录表（单次分析 + 多轮对话共用）"""
    __tablename__ = "ai_analysis"
    __table_args__ = (
        Index("ix_aa_batch_stage", "batch_no", "stage"),
        Index("ix_aa_created", "created_at"),
        Index("ix_aa_session", "session_id"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(String(30), nullable=False, comment="目标批号")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, comment="批号类型")
    include_siblings: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否含同级批次")
    trace_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="追溯数据快照")
    dist_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="收率分布快照")
    anomalies: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="后端计算的异常标记")
    llm_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, comment="发给LLM的完整prompt")
    llm_response: Mapped[str | None] = mapped_column(Text, nullable=True, comment="LLM原始返回")
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="一句话摘要")
    causes: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="原因分析")
    suggestions: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="优化建议")
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="严重程度 low/medium/high")
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="LLM模型名")
    reference_cases: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="引用的历史案例ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="操作人")
    # 多轮对话扩展字段（可空，兼容历史数据）
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, comment="会话ID，同会话共享")
    message_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="消息序号，0=首条报告")
    role: Mapped[str] = mapped_column(String(16), default="system", nullable=False, comment="角色 system/user/assistant")
