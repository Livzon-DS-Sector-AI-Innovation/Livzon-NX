"""设备车间注册表 ORM 模型。

车间清单的数据源：统一工作台车间块、各功能视图车间切换与飞书配置页
清单均由此派生。新增车间在「车间管理」页登记后全模块生效；停用仅
隐藏入口，业务数据按 workshop_code 保留。
"""

from __future__ import annotations

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class EquipmentWorkshop(BaseModel):
    """设备模块车间注册表（代码创建后不可改，名称可改，停用可逆）"""

    __tablename__ = "workshops"
    __table_args__ = (
        # 部分唯一索引：未删除行内车间代码唯一
        Index(
            "uq_equipment_workshops_code",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "equipment"},
    )

    code: Mapped[str] = mapped_column(
        String(10), comment="车间代码（如 101-1 / 201-1，全系统数据标识）"
    )
    name: Mapped[str] = mapped_column(
        String(50), comment="车间显示名（如 101一车间）"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        comment="启用；停用后各处隐藏，数据保留可再启用",
    )
