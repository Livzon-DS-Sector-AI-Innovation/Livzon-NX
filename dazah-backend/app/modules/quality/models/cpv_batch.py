"""CPV Batch ORM model."""

import uuid
from datetime import date

from sqlalchemy import Date, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class CpvBatch(BaseModel):
    """持续工艺验证批次表"""

    __tablename__ = "cpv_batches"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "batch_no",
            "data_type",
            name="uq_cpv_batches_product_batch_type",
        ),
        {"schema": "quality", "comment": "CPV批次表"},
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="产品ID"
    )
    batch_no: Mapped[str] = mapped_column(String(100), nullable=False, comment="批号")
    production_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="生产日期"
    )
    data_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="数据类型: CPP/CQA"
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
        comment="数据来源: excel/feishu/manual",
    )
    import_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, comment="导入任务ID"
    )
