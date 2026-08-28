"""Lab item / 物品管理 ORM model."""

from datetime import date

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class LabItem(BaseModel):
    """实验室物品：试剂、耗材、标准品等."""

    __tablename__ = "lab_items"
    __table_args__ = {"schema": "quality"}

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="物品名称")
    specification: Mapped[str | None] = mapped_column(String(200), comment="规格/型号")
    category: Mapped[str | None] = mapped_column(
        String(50), comment="类别：试剂/耗材/标准品/其他"
    )
    quantity: Mapped[int | None] = mapped_column(Integer, default=0, comment="数量")
    unit: Mapped[str | None] = mapped_column(String(20), comment="单位")
    location: Mapped[str | None] = mapped_column(String(100), comment="存放位置")
    supplier: Mapped[str | None] = mapped_column(String(200), comment="供应商")
    batch_no: Mapped[str | None] = mapped_column(String(100), comment="批号")
    expiry_date: Mapped[date | None] = mapped_column(Date, comment="有效期至")
    status: Mapped[str] = mapped_column(
        String(20), default="normal", comment="状态：normal/low_stock/expired"
    )
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")
