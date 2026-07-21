"""DataSource ORM model."""

import uuid
from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.base_model import BaseModel


class DataSource(BaseModel):
    """数据源表 - 监管机构"""

    __tablename__ = "data_sources"
    __table_args__ = {"schema": "regulatory_tracker"}

    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="数据源编码，如 CDE, NMPA"
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="数据源名称"
    )
    base_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="基础URL"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="是否启用"
    )

    # Relationships
    channels = relationship("DataChannel", back_populates="source", cascade="all, delete-orphan")
    documents = relationship("RegulatoryDocument", back_populates="source")
    sync_jobs = relationship("SyncJob", back_populates="source")
