"""CPV Value ORM model."""

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class CpvValue(BaseModel):
    """持续工艺验证参数值表"""

    __tablename__ = "cpv_values"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "parameter_id",
            name="uq_cpv_values_batch_parameter",
        ),
        {"schema": "quality", "comment": "CPV参数值表"},
    )

    batch_id: Mapped[str] = mapped_column(
        nullable=False, comment="批次ID"
    )
    parameter_id: Mapped[str] = mapped_column(
        nullable=False, comment="参数ID"
    )
    actual_value: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="实测值"
    )
    is_abnormal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否异常"
    )
    remark: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="备注"
    )
