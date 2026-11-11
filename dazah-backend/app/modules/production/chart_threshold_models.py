"""仪表盘图表警戒线配置模型（按页面范围 + 图表键，全平台共享）。"""

from sqlalchemy import Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ChartThreshold(BaseModel):
    """图表警戒线：按页面范围（scope_key）+ 图表键（chart_key）存一条数值。

    前端各车间收率趋势图/收率卡片读取该值渲染警戒线与红绿判断；
    由管理员在页面上调整，全平台共享。更新人复用 BaseModel.updated_by。
    """

    __tablename__ = "chart_thresholds"
    __table_args__ = (
        UniqueConstraint(
            "scope_key", "chart_key", name="uq_chart_threshold_scope_chart"
        ),
        {"schema": "production"},
    )

    scope_key: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="页面范围键，如 workshop-201-2/crude-extraction",
    )
    chart_key: Mapped[str] = mapped_column(
        String(60), nullable=False, comment="图表键，如 yield / pass_rate"
    )
    threshold: Mapped[float] = mapped_column(
        Float, nullable=False, comment="警戒线数值"
    )
