"""CPV Parameter ORM model."""

import uuid

from sqlalchemy import Boolean, Float, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class CpvParameter(BaseModel):
    """持续工艺验证参数定义表"""

    __tablename__ = "cpv_parameters"
    __table_args__ = {"schema": "quality", "comment": "CPV参数定义表"}

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="产品ID"
    )
    parameter_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="参数类型: CPP/CQA"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="参数名称")
    code: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="参数代码(Excel表头匹配键)"
    )
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="单位")
    lower_limit: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="标准下限"
    )
    upper_limit: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="标准上限"
    )
    control_lower: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="控制下限(内控限)"
    )
    control_upper: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="控制上限(内控限)"
    )
    target_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="目标值"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="排序"
    )
