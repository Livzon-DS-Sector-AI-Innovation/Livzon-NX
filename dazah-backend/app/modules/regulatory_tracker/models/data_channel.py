"""DataChannel ORM model."""

import uuid
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.base_model import BaseModel


class DataChannel(BaseModel):
    """栏目表 - 数据源下的具体栏目"""

    __tablename__ = "data_channels"
    __table_args__ = {"schema": "regulatory_tracker"}

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_tracker.data_sources.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属数据源ID",
    )
    code: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="栏目编码，如 cde_domestic_guideline"
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="栏目名称"
    )
    list_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="列表页URL"
    )
    adapter_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="适配器名称"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="是否启用"
    )

    # Relationships
    source = relationship("DataSource", back_populates="channels")
    documents = relationship("RegulatoryDocument", back_populates="channel")
    sync_jobs = relationship("SyncJob", back_populates="channel")
