"""OOS/OOT management ORM model."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.quality.models.oot_limit import (
    OotLimitItem as OotLimitItem,
)
from app.modules.quality.models.oot_limit import (
    OotLimitProduct as OotLimitProduct,
)
from app.shared.base_model import BaseModel


class OosOotRecord(BaseModel):
    """OOS/OOT record (OOS = Out of Specification, OOT = Out of Trend)."""

    __tablename__ = "oos_oot_records"
    __table_args__ = {"schema": "quality"}

    record_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="记录编号"
    )
    record_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="OOS", comment="记录类型：OOS / OOT"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="标题")
    department: Mapped[str | None] = mapped_column(String(100), comment="责任部门")
    product_name: Mapped[str | None] = mapped_column(String(200), comment="产品名称")
    batch_number: Mapped[str | None] = mapped_column(String(100), comment="批号")
    test_item: Mapped[str | None] = mapped_column(String(200), comment="检验项目")
    specification: Mapped[str | None] = mapped_column(String(200), comment="标准规定")
    test_result: Mapped[str | None] = mapped_column(String(200), comment="检验结果")
    discovery_date: Mapped[date | None] = mapped_column(Date, comment="发现日期")
    description: Mapped[str | None] = mapped_column(Text, comment="描述")
    investigation_result: Mapped[str | None] = mapped_column(Text, comment="调查结论")
    corrective_actions: Mapped[str | None] = mapped_column(Text, comment="纠正措施")
    status: Mapped[str] = mapped_column(
        String(30), default="open", comment="状态：open / investigating / closed"
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="关闭时间"
    )


# Compatibility re-exports for the current OOS/OOT service and repository;
# the migrated code stores these resources in their dedicated model module.
