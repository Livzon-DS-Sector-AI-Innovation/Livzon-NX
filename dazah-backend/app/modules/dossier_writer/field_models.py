"""通用字段映射模型 + AI 填充相关模型"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.base_model import Base


class FieldMapping(Base):
    """字段映射配置表 - 定义每个章节需要填充哪些字段"""
    __tablename__ = "field_mappings"
    __table_args__ = {"schema": "dossier_writer"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    chapter_code: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="章节编号，如 3.2.S.6"
    )
    field_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="字段名，如 包材类型"
    )
    field_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="text",
        comment="字段类型: text/table/image_appendix"
    )
    location_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="paragraph",
        comment="模板中的位置类型: paragraph/table/appendix/inline_image"
    )
    location_hint: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="位置语义提示：描述在模板中的位置，如'包装形式字段在包装材料类型章节的段落中'"
    )
    extraction_prompt: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="AI 提取提示：告诉 LLM 如何从素材中识别此字段的值"
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="asset_extract",
        comment="值来源类型: asset_extract(AI从素材提取)/asset_image(素材转图片)/fixed(固定值)/manual(手动)"
    )
    source_category: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="素材分类名：指向 AssetCategory.category_name，限定 AI 只在对应分类的素材中查找"
    )
    fixed_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="固定值：当 source_type=fixed 时使用"
    )
    appendix_slot: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="附录编号：当 field_type=image_appendix 时，对应模板中的附录位置"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="字段在章节内的排序"
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="是否必填"
    )


class FieldFillResult(Base):
    """字段填充结果表 - 记录每个字段的填充情况"""
    __tablename__ = "field_fill_results"
    __table_args__ = {"schema": "dossier_writer"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.product_dossiers.id", ondelete="CASCADE"),
        nullable=False,
        comment="品种资料ID"
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.dossier_chapters.id", ondelete="CASCADE"),
        nullable=False,
        comment="章节ID"
    )
    field_mapping_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.field_mappings.id", ondelete="CASCADE"),
        nullable=False,
        comment="字段映射ID"
    )
    field_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="字段名（冗余存储便于查询）"
    )
    filled_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="填充的值"
    )
    source_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.chapter_assets.id", ondelete="SET NULL"),
        nullable=True,
        comment="值来自哪个素材文件"
    )
    source_location: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="在素材中的位置，如 paragraph[5] 或 table[0].row[3].cell[2]"
    )
    fill_method: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ai",
        comment="填充方式: ai/rule/manual"
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="置信度（AI填充时用，0-1）"
    )
    ai_reasoning: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="AI 的推理过程，用于用户审核"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",
        comment="状态: pending/extracted/filled/reviewed/rejected"
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="审核时间"
    )


class AssetCategory(Base):
    """素材分类定义表 - 每个章节需要哪些类型的素材"""
    __tablename__ = "asset_categories"
    __table_args__ = {"schema": "dossier_writer"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    chapter_code: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="章节编号，如 3.2.S.6"
    )
    category_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="分类名称，如 授权书"
    )
    category_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="document",
        comment="分类类型: document(文字提取)/image_appendix(图片插入)/both(两者皆可)"
    )
    appendix_slot: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="对应模板中的附录编号，如 附录1"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="分类说明，帮助用户理解这个分类包含什么内容"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="排序序号"
    )


class AssetPageSplit(Base):
    """素材页拆分结果表 - 记录 AI 对多页文档的拆分识别"""
    __tablename__ = "asset_page_splits"
    __table_args__ = {"schema": "dossier_writer"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossier_writer.chapter_assets.id", ondelete="CASCADE"),
        nullable=False,
        comment="素材ID"
    )
    page_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="页码（从1开始）"
    )
    page_type: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="AI 识别的页面类型"
    )
    content_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="页面内容摘要"
    )
    ocr_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="OCR 提取的页面文本"
    )
    appendix_slot: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="用户确认的附录编号"
    )
    image_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="转换后的图片路径"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",
        comment="状态: pending/confirmed/inserted/skipped"
    )
