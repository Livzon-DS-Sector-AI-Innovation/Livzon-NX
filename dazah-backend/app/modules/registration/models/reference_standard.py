"""对照物质说明表模型"""

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ReferenceStandard(BaseModel):
    """对照物质说明表生成记录表"""

    __tablename__ = "reference_standards"
    __table_args__ = (
        Index("ix_reference_standards_drug_name", "drug_name"),
        Index("ix_reference_standards_batch_number", "batch_number"),
        {"schema": "registration"},
    )

    # 药品信息
    drug_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="药品名称"
    )
    reference_substance_name: Mapped[str] = mapped_column(
        String(256), nullable=True, comment="对照物质名称"
    )
    batch_number: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="批号"
    )
    manufacturer: Mapped[str] = mapped_column(
        String(256), nullable=True, comment="生产厂家/来源"
    )
    english_name: Mapped[str] = mapped_column(
        String(256), nullable=True, comment="英文名"
    )
    molecular_formula: Mapped[str] = mapped_column(
        String(128), nullable=True, comment="分子式"
    )
    molecular_weight: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="分子量"
    )
    cas_number: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="CAS号"
    )
    content: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="含量"
    )
    moisture: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="水分/干燥失重"
    )
    rsd: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="RSD"
    )
    expiration_date: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="有效期"
    )
    storage_condition: Mapped[str] = mapped_column(
        String(128), nullable=True, comment="贮存条件"
    )

    # 文件信息
    coa_file_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="COA文件 key"
    )
    coa_file_name: Mapped[str] = mapped_column(
        String(256), nullable=True, comment="COA文件名"
    )
    output_file_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="生成文件 key"
    )
    output_file_name: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="生成文件名"
    )

    # 备注
    remarks: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )
