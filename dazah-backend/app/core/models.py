"""core schema ORM 模型（供 alembic autogenerate / alembic check 感知）。

config_reader 以原始 SQL 读写 core.module_settings，此前该表不在
Base.metadata 中，导致 alembic check 把这张应用自有表当作"库中多余表"
持续报告漂移。此处声明与 e4f5a6b7c8d9 / e5f6a7b8c9d0 / e6f7a8b9c0d1
迁移完全一致的结构与索引（部分唯一索引匹配 set_module_setting 的
ON CONFLICT 谓词）。

注意：不继承 BaseModel——该表的审计列（created_by/updated_by）是
varchar(64) 而非 identity.users 外键，结构与 BaseModel 不同。
"""

import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import Base


class ModuleSetting(Base):
    """模块级运行时配置（module/key 维度，软删除）。"""

    __tablename__ = "module_settings"
    __table_args__ = (
        Index(
            "uq_core_module_settings_module_key",
            "module",
            "key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_core_module_settings_module_key", "module", "key"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
