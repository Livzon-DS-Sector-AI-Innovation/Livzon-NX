"""Dossier Writer request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ====== Product Dossier ======


class ProductDossierBase(BaseModel):
    product_name: str = Field(..., max_length=200, description="品种名称")
    sterile_type: str = Field(..., max_length=50, description="无菌/非无菌")
    manufacturer: str = Field(..., max_length=300, description="生产商")
    template_original_product_name: str | None = Field(
        None, max_length=200, description="模板原品种名称"
    )
    template_original_manufacturer: str | None = Field(
        None, max_length=300, description="模板原生产商"
    )


class ProductDossierCreate(ProductDossierBase):
    """创建品种资料请求"""

    pass


class ProductDossierUpdate(BaseModel):
    """更新品种资料请求"""

    product_name: str | None = Field(None, max_length=200)
    sterile_type: str | None = Field(None, max_length=50)
    manufacturer: str | None = Field(None, max_length=300)
    template_original_product_name: str | None = Field(None, max_length=200)
    template_original_manufacturer: str | None = Field(None, max_length=300)


class ProductDossierResponse(ProductDossierBase):
    """品种资料响应"""

    id: UUID
    status: str
    parse_status: str
    parse_error: str | None = None
    source_templates_path: str | None = None
    working_path: str | None = None
    assets_path: str | None = None
    outputs_path: str | None = None
    created_at: datetime
    updated_at: datetime
    chapter_count: int = 0

    class Config:
        from_attributes = True


class ProductDossierListResponse(BaseModel):
    """品种资料列表响应"""

    id: UUID
    product_name: str
    sterile_type: str
    manufacturer: str
    status: str
    parse_status: str
    chapter_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ====== Template ======


class TemplateResponse(BaseModel):
    """模板文件响应"""

    id: UUID
    original_filename: str
    file_size: int | None = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


# ====== Chapter ======


class ChapterResponse(BaseModel):
    """章节响应"""

    id: UUID
    parent_id: UUID | None = None
    chapter_code: str | None = None
    chapter_title: str
    level: int
    sort_order: int
    has_content: bool
    has_assets: bool
    asset_count: int = 0
    source_file: str | None = None
    working_file: str | None = None
    children: list["ChapterResponse"] = []

    class Config:
        from_attributes = True


class ChapterDetailResponse(BaseModel):
    """章节详情响应"""

    id: UUID
    product_dossier_id: UUID
    chapter_code: str | None = None
    chapter_title: str
    level: int
    has_content: bool
    has_assets: bool
    source_file: str | None = None
    working_file: str | None = None
    assets: list["AssetResponse"] = []

    class Config:
        from_attributes = True


# ====== Asset ======


class AssetResponse(BaseModel):
    """素材响应"""

    id: UUID
    original_filename: str
    file_type: str | None = None
    file_size: int | None = None
    uploaded_at: datetime
    category_id: UUID | None = None

    class Config:
        from_attributes = True


class AssetUploadResponse(BaseModel):
    """素材上传响应"""

    id: UUID
    original_filename: str
    file_path: str
    file_type: str | None = None
    file_size: int | None = None
    uploaded_at: datetime
    category_id: UUID | None = None


# ====== Parse Result ======


class ParseResultResponse(BaseModel):
    """解析结果响应"""

    success: bool
    message: str
    chapter_count: int = 0
    error: str | None = None


# ====== Export ======


class ExportRequest(BaseModel):
    """导出请求"""

    chapter_ids: list[UUID] | None = Field(
        None, description="指定章节ID列表，为空则导出全部"
    )
    format: str = Field("docx", description="导出格式: docx/pdf")


class ExportResponse(BaseModel):
    """导出响应"""

    success: bool
    message: str
    file_path: str | None = None
    filename: str | None = None


# 解决循环引用
ChapterResponse.model_rebuild()
ChapterDetailResponse.model_rebuild()
