"""Document catalog ORM models (各部门文件目录管理)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class DocumentDepartment(BaseModel):
    """部门分类（对应汇总表中的每个 Sheet）。"""

    __tablename__ = "document_departments"
    __table_args__ = {"schema": "quality"}

    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class DocumentEntry(BaseModel):
    """文件目录条目。"""

    __tablename__ = "document_entries"
    __table_args__ = {"schema": "quality"}

    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date_text: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachments: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
