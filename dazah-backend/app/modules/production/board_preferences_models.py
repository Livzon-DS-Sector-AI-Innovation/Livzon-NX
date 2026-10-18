"""生产看板用户偏好（按登录账户持久化，跨设备一致）。

当前承载发酵看板单批产量图的平均单产口径（含/不含中试）与标签后缀；
用户 ID 为 identity.users 的稳定标识，跨模块不建外键。
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ProductionUserBoardPreference(BaseModel):
    __tablename__ = "user_board_preferences"
    __table_args__ = (
        Index(
            "uq_user_board_preferences_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "production"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        comment="用户 ID（identity.users 稳定标识，跨模块不建外键）",
    )
    avg_pilot_incl: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "平均单产口径：true=含中试（总产量÷大罐批数）"
            "false=不含中试（大罐批均值）"
        ),
    )
    avg_note: Mapped[str] = mapped_column(
        String(length=64),
        nullable=False,
        default="含中试",
        server_default="含中试",
        comment="含中试模式下的平均线标签后缀（默认「含中试」，可改可清空）",
    )
