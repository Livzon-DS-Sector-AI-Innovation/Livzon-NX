"""Dossier Writer request and response schemas."""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


# ====== Product Dossier ======

class ProductDossierBase(BaseModel):
    product_name: str = Field(..., max_length=200, description="品种名称")
    sterile_type: str = Field(..., max_length=50, description="无菌/非无菌")
    manufacturer: str = Field(..., max_length=300, description="生产商")
    template_original_product_name: Optional[str] = Field(None, max_length=200, description="模板原品种名称")
    template_original_manufacturer: Optional[str] = Field(None, max_length=300, description="模板原生产商")


class ProductDossierCreate(ProductDossierBase):
    """创建品种资料请求"""
    pass


class ProductDossierUpdate(BaseModel):
    """更新品种资料请求"""
    product_name: Optional[str] = Field(None, max_length=200)
    sterile_type: Optional[str] = Field(None, max_length=50)
    manufacturer: Optional[str] = Field(None, max_length=300)
    template_original_product_name: Optional[str] = Field(None, max_length=200)
    template_original_manufacturer: Optional[str] = Field(None, max_length=300)


class ProductDossierResponse(ProductDossierBase):
    """品种资料响应"""
    id: UUID
    status: str
    parse_status: str
    parse_error: Optional[str] = None
    source_templates_path: Optional[str] = None
    working_path: Optional[str] = None
    assets_path: Optional[str] = None
    outputs_path: Optional[str] = None
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
    file_size: Optional[int] = None
    uploaded_at: datetime
    
    class Config:
        from_attributes = True


# ====== Chapter ======

class ChapterResponse(BaseModel):
    """章节响应"""
    id: UUID
    parent_id: Optional[UUID] = None
    chapter_code: Optional[str] = None
    chapter_title: str
    level: int
    sort_order: int
    has_content: bool
    has_assets: bool
    asset_count: int = 0
    source_file: Optional[str] = None
    working_file: Optional[str] = None
    children: List["ChapterResponse"] = []
    
    class Config:
        from_attributes = True


class ChapterDetailResponse(BaseModel):
    """章节详情响应"""
    id: UUID
    product_dossier_id: UUID
    chapter_code: Optional[str] = None
    chapter_title: str
    level: int
    has_content: bool
    has_assets: bool
    source_file: Optional[str] = None
    working_file: Optional[str] = None
    assets: List["AssetResponse"] = []
    
    class Config:
        from_attributes = True


# ====== Asset ======

class AssetResponse(BaseModel):
    """素材响应"""
    id: UUID
    original_filename: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: datetime
    category_id: Optional[UUID] = None
    
    class Config:
        from_attributes = True


class AssetUploadResponse(BaseModel):
    """素材上传响应"""
    id: UUID
    original_filename: str
    file_path: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: datetime
    category_id: Optional[UUID] = None


# ====== Parse Result ======

class ParseResultResponse(BaseModel):
    """解析结果响应"""
    success: bool
    message: str
    chapter_count: int = 0
    error: Optional[str] = None


# ====== Export ======

class ExportRequest(BaseModel):
    """导出请求"""
    chapter_ids: Optional[List[UUID]] = Field(None, description="指定章节ID列表，为空则导出全部")
    format: str = Field("docx", description="导出格式: docx/pdf")


class ExportResponse(BaseModel):
    """导出响应"""
    success: bool
    message: str
    file_path: Optional[str] = None
    filename: Optional[str] = None


# 解决循环引用
ChapterResponse.model_rebuild()
ChapterDetailResponse.model_rebuild()
