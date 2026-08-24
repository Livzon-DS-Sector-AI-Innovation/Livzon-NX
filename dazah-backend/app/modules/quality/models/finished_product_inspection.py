"""Finished product inspection / 成品检验 ORM model."""

from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class FinishedProductInspection(BaseModel):
    """成品检验记录."""

    __tablename__ = "finished_product_inspections"
    __table_args__ = {"schema": "quality"}

    inspection_no: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="检验编号"
    )
    product_name: Mapped[str | None] = mapped_column(String(200), comment="产品名称")
    batch_no: Mapped[str | None] = mapped_column(String(100), comment="批号")
    inspection_item: Mapped[str | None] = mapped_column(String(500), comment="检验项目")
    specification: Mapped[str | None] = mapped_column(Text, comment="标准规定")
    test_result: Mapped[str | None] = mapped_column(Text, comment="检验结果")
    conclusion: Mapped[str | None] = mapped_column(
        String(20), comment="检验结论：合格/不合格"
    )
    inspector: Mapped[str | None] = mapped_column(String(100), comment="检验人")
    inspection_date: Mapped[date | None] = mapped_column(Date, comment="检验日期")
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")
