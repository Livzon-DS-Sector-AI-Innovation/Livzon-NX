"""Reference substance ORM models."""

import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ReferenceSubstance(BaseModel):
    """对照品标准物质表"""

    __tablename__ = "reference_substances"
    __table_args__ = {"schema": "registration"}

    drug_name: Mapped[str] = mapped_column(
        String(255), comment="药品名称"
    )
    substance_name: Mapped[str] = mapped_column(
        String(255), comment="对照物质名称"
    )
    lot_number: Mapped[str] = mapped_column(
        String(100), comment="批号"
    )
    manufacturer: Mapped[str] = mapped_column(
        String(500), comment="生产厂家/来源"
    )
    english_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="英文名"
    )
    expiration_date: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="有效期"
    )
    cas_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="CAS号"
    )
    molecular_formula: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="分子式"
    )
    molecular_weight: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="分子量"
    )
    assay: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="含量"
    )
    storage_condition: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="贮存条件"
    )
    usage_scope: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default="含量测定", comment="使用范围"
    )
    usage_method: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default="直接折算", comment="使用方法"
    )
    coa_file_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="COA文件URL"
    )
    provider: Mapped[str] = mapped_column(
        String(255),
        default="珠海保税区丽珠合成制药有限公司",
        comment="提供单位",
    )
    handler: Mapped[str] = mapped_column(
        String(50), default="魏永红", comment="经办人"
    )
    contact: Mapped[str] = mapped_column(
        String(50), default="13570680132", comment="联系方式"
    )
