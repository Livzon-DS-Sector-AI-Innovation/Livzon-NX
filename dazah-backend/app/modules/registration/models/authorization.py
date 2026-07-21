"""Authorization letter and supplementary reply ORM models."""

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class AuthorizationLetter(BaseModel):
    """授权书生成记录表"""

    __tablename__ = "authorization_letters"
    __table_args__ = (
        Index("ix_authorization_letters_product_name", "product_name"),
        Index("ix_authorization_letters_registration_number", "registration_number"),
        {"schema": "registration"},
    )

    api_company: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="珠海保税区丽珠合成制药有限公司",
        comment="原料药企业名称",
    )
    product_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="产品名称（对照表标准名）")
    registration_number: Mapped[str] = mapped_column(String(32), nullable=False, comment="产品登记号")
    preparation_unit: Mapped[str] = mapped_column(String(256), nullable=False, comment="制剂单位名称（药品上市许可持有人/申请人）")
    preparation_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="制剂名称")
    administration_route: Mapped[str] = mapped_column(String(64), nullable=False, comment="给药途径")
    template_file_key: Mapped[str] = mapped_column(String(256), nullable=False, comment="模板文件 key")
    template_file_name: Mapped[str] = mapped_column(String(256), nullable=True, comment="模板文件名")
    output_file_key: Mapped[str] = mapped_column(String(256), nullable=False, comment="生成文件 key")
    output_file_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="生成文件名")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class SupplementaryReply(BaseModel):
    """发补回复生成记录表"""

    __tablename__ = "supplementary_replies"
    __table_args__ = (
        Index("ix_supplementary_replies_drug_name", "drug_name"),
        Index("ix_supplementary_replies_registration_number", "registration_number"),
        {"schema": "registration"},
    )

    drug_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="药品名称")
    registration_number: Mapped[str] = mapped_column(String(32), nullable=True, comment="登记号")
    acceptance_number: Mapped[str] = mapped_column(String(64), nullable=True, comment="受理号")
    company_name: Mapped[str] = mapped_column(String(256), nullable=True, comment="申请人/公司名称")
    notice_file_key: Mapped[str] = mapped_column(String(256), nullable=False, comment="CDE通知函文件 key")
    notice_file_name: Mapped[str] = mapped_column(String(256), nullable=True, comment="CDE通知函文件名")
    template_file_key: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="公司模板文件 key")
    template_file_name: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="公司模板文件名")
    output_file_key: Mapped[str] = mapped_column(String(256), nullable=False, comment="生成文件 key")
    output_file_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="生成文件名")
    question_count: Mapped[int] = mapped_column(nullable=False, server_default="0", comment="提取的问题数量")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
