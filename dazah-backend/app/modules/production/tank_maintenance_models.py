"""发酵罐检修标注模型（看板人工状态）。

同一台罐同一时间只允许一条进行中的检修标注；解除采用软删。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class TankMaintenance(BaseModel):
    """罐检修标注（进行中）"""

    __tablename__ = "tank_maintenance"
    __table_args__ = {"schema": "production"}

    tank_no: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="罐号（如 302A）"
    )
    reason: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="检修原因"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="检修开始时间",
    )
