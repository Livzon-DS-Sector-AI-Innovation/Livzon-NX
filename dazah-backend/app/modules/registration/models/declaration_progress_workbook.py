"""Declaration progress workbook ORM models."""

import uuid

from sqlalchemy import Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class RegistrationDeclarationProgressWorkbookVersion(BaseModel):
    """申报进度工作簿版本记录。"""

    __tablename__ = "declaration_progress_workbook_versions"
    __table_args__ = (
        UniqueConstraint(
            "record_group_id",
            "version_number",
            "is_deleted",
            name="uq_registration_declaration_progress_workbook_group_version",
        ),
        Index(
            "ix_registration_declaration_progress_workbook_sheet_key",
            "sheet_key",
        ),
        Index(
            "ix_registration_declaration_progress_workbook_record_group_id",
            "record_group_id",
        ),
        Index(
            "ix_registration_declaration_progress_workbook_source_sequence",
            "source_sequence",
        ),
        {"schema": "registration"},
    )

    record_group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        comment="主记录分组ID",
    )
    sheet_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="子表键")
    sheet_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="子表名称"
    )
    sheet_title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="子表标题"
    )
    source_sequence: Mapped[int] = mapped_column(nullable=False, comment="主记录序号")
    version_number: Mapped[int] = mapped_column(nullable=False, comment="版本号")
    source_row_number: Mapped[int | None] = mapped_column(
        nullable=True, comment="Excel 原始行号"
    )
    values_data: Mapped[dict[str, str | None]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="字段值快照",
    )
    style_marks: Mapped[dict[str, str | None]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="字段样式标记快照",
    )
    project_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="项目名称快照",
    )
    product_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="产品名称快照",
    )
