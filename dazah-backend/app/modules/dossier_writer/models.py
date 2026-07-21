"""Dossier Writer ORM models."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Integer, Text, DateTime, ForeignKey, text
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.base_model import BaseModel
from .field_models import (  # noqa: F401
    AssetCategory,
    FieldMapping,
    FieldFillResult,
    AssetPageSplit,
)


class ProductDossier(BaseModel):
    """品种资料主表"""
    __tablename__ = "product_dossiers"
    __table_args__ = {"schema": "dossier_writer"}

    product_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="品种名称"
    )
    sterile_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="无菌/非无菌"
    )
    manufacturer: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="生产商"
    )
    template_original_product_name: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="模板原品种名称"
    )
    template_original_manufacturer: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True, comment="模板原生产商"
    )
    
    # 文件路径
    source_templates_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="原始模板目录路径"
    )
    working_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="工作副本目录路径"
    )
    assets_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="素材目录路径"
    )
    outputs_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="导出目录路径"
    )
    
    # 状态
    status: Mapped[str] = mapped_column(
        String(50), default="draft", server_default="draft", comment="状态: draft/active"
    )
    parse_status: Mapped[str] = mapped_column(
        String(50), default="pending", server_default="pending", comment="解析状态: pending/parsing/completed/failed"
    )
    parse_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="解析错误信息"
    )
    
    # 关系
    templates = relationship("DossierTemplate", back_populates="product_dossier", cascade="all, delete-orphan")
    chapters = relationship("DossierChapter", back_populates="product_dossier", cascade="all, delete-orphan")


class DossierTemplate(BaseModel):
    """模板文件记录"""
    __tablename__ = "dossier_templates"
    __table_args__ = {"schema": "dossier_writer"}

    product_dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.product_dossiers.id", ondelete="CASCADE"),
        nullable=False,
        comment="品种资料ID",
    )
    original_filename: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="原始文件名"
    )
    file_path: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="文件存储路径"
    )
    file_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="文件大小(字节)"
    )
    uploaded_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="上传时间"
    )
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="上传人"
    )
    
    # 关系
    product_dossier = relationship("ProductDossier", back_populates="templates")


class DossierChapter(BaseModel):
    """章节树"""
    __tablename__ = "dossier_chapters"
    __table_args__ = {"schema": "dossier_writer"}

    product_dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.product_dossiers.id", ondelete="CASCADE"),
        nullable=False,
        comment="品种资料ID",
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.dossier_chapters.id", ondelete="CASCADE"),
        nullable=True,
        comment="父章节ID",
    )
    
    # 章节信息
    chapter_code: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="章节编号，如 3.2.S.1.1"
    )
    chapter_title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="章节标题"
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="层级深度"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="排序序号"
    )
    
    # Word 文档信息
    source_file: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="源模板文件名"
    )
    working_file: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="工作副本文件名"
    )
    paragraph_start: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="起始段落索引"
    )
    paragraph_end: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="结束段落索引"
    )
    
    # 状态
    has_content: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="是否有内容"
    )
    has_assets: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="是否有素材"
    )
    
    # 关系
    product_dossier = relationship("ProductDossier", back_populates="chapters")
    parent = relationship("DossierChapter", remote_side="DossierChapter.id", backref="children_rel")
    assets = relationship("ChapterAsset", back_populates="chapter", cascade="all, delete-orphan")


class ChapterAsset(BaseModel):
    """章节素材"""
    __tablename__ = "chapter_assets"
    __table_args__ = {"schema": "dossier_writer"}

    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.dossier_chapters.id", ondelete="CASCADE"),
        nullable=False,
        comment="章节ID",
    )
    
    # 文件信息
    original_filename: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="原始文件名"
    )
    file_path: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="文件存储路径"
    )
    file_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="文件类型: pdf/docx/xlsx/txt"
    )
    file_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="文件大小(字节)"
    )
    uploaded_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="上传时间"
    )
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="上传人"
    )
    
    # 素材分类
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.asset_categories.id", ondelete="SET NULL"),
        nullable=True,
        comment="素材分类ID",
    )
    
    # 关系
    chapter = relationship("DossierChapter", back_populates="assets")
    category = relationship("AssetCategory", foreign_keys=[category_id])
