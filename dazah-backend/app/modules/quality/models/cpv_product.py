"""CPV Product ORM model."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class CpvProduct(BaseModel):
    """持续工艺验证产品表"""

    __tablename__ = "cpv_products"
    __table_args__ = {"schema": "quality", "comment": "CPV产品表"}

    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="产品名称"
    )
    specification: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="规格"
    )
    process_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="工艺版本"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", comment="状态: active/inactive"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注描述"
    )
