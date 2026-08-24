"""Registration knowledge schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeCategoryCreate(BaseModel):
    """新增知识分类。"""

    name: str = Field(..., min_length=1, max_length=128, description="分类名称")
    description: str | None = Field(None, description="分类描述")
    sort_order: int = Field(default=0, ge=0, description="排序序号")


class KnowledgeCategoryUpdate(BaseModel):
    """更新知识分类。"""

    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None
    sort_order: int | None = Field(None, ge=0)


class KnowledgeCategoryResponse(BaseModel):
    """知识分类响应。"""

    id: UUID = Field(..., description="分类ID")
    name: str = Field(..., description="分类名称")
    description: str | None = Field(None, description="分类描述")
    sort_order: int = Field(..., description="排序序号")
    article_count: int = Field(default=0, description="文章数量")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class KnowledgeArticleCreate(BaseModel):
    """新增知识文章。"""

    title: str = Field(..., min_length=1, max_length=255, description="文章标题")
    category_id: UUID = Field(..., description="分类ID")
    content: str = Field(..., description="文章内容")
    tags: str | None = Field(None, max_length=512, description="标签（逗号分隔）")
    country: str | None = Field(None, max_length=128, description="适用国家")
    product: str | None = Field(None, max_length=255, description="关联产品")
    is_published: bool = Field(default=False, description="是否发布")
    author: str | None = Field(None, max_length=128, description="作者")
    source_url: str | None = Field(None, max_length=1024, description="信息来源链接")


class KnowledgeArticleUpdate(BaseModel):
    """更新知识文章。"""

    title: str | None = Field(None, min_length=1, max_length=255)
    category_id: UUID | None = None
    content: str | None = None
    tags: str | None = Field(None, max_length=512)
    country: str | None = Field(None, max_length=128)
    product: str | None = Field(None, max_length=255)
    is_published: bool | None = None
    author: str | None = Field(None, max_length=128)
    source_url: str | None = Field(None, max_length=1024)


class KnowledgeArticleResponse(BaseModel):
    """知识文章响应。"""

    id: UUID = Field(..., description="文章ID")
    title: str = Field(..., description="文章标题")
    category_id: UUID = Field(..., description="分类ID")
    category_name: str | None = Field(None, description="分类名称")
    content: str = Field(..., description="文章内容")
    tags: str | None = Field(None, description="标签")
    country: str | None = Field(None, description="适用国家")
    product: str | None = Field(None, description="关联产品")
    is_published: bool = Field(..., description="是否发布")
    published_at: datetime | None = Field(None, description="发布时间")
    author: str | None = Field(None, description="作者")
    view_count: int = Field(..., description="浏览次数")
    source_url: str | None = Field(None, description="信息来源链接")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class KnowledgeArticleListItem(BaseModel):
    """知识文章列表项。"""

    id: UUID = Field(..., description="文章ID")
    title: str = Field(..., description="文章标题")
    category_id: UUID = Field(..., description="分类ID")
    category_name: str | None = Field(None, description="分类名称")
    tags: str | None = Field(None, description="标签")
    country: str | None = Field(None, description="适用国家")
    product: str | None = Field(None, description="关联产品")
    is_published: bool = Field(..., description="是否发布")
    published_at: datetime | None = Field(None, description="发布时间")
    author: str | None = Field(None, description="作者")
    view_count: int = Field(..., description="浏览次数")
    source_url: str | None = Field(None, description="信息来源链接")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class KnowledgeOverview(BaseModel):
    """知识库概览。"""

    total_categories: int = Field(..., description="分类总数")
    total_articles: int = Field(..., description="文章总数")
    published_articles: int = Field(..., description="已发布文章数")
    draft_articles: int = Field(..., description="草稿文章数")
    categories: list[KnowledgeCategoryResponse] = Field(
        default_factory=list, description="分类列表"
    )


# ── Attachment schemas ───────────────────────────────────────────────


class KnowledgeAttachmentResponse(BaseModel):
    """附件响应。"""

    id: UUID = Field(..., description="附件ID")
    article_id: UUID = Field(..., description="文章ID")
    file_name: str = Field(..., description="原始文件名")
    file_path: str = Field(..., description="存储路径")
    file_size: int = Field(..., description="文件大小（字节）")
    content_type: str = Field(..., description="MIME类型")
    ai_summary: str | None = Field(None, description="AI生成的结构化摘要")
    created_at: datetime = Field(..., description="创建时间")


# ── Comment schemas ──────────────────────────────────────────────────


class KnowledgeCommentCreate(BaseModel):
    """新增评论。"""

    content: str = Field(..., min_length=1, description="评论内容")


class KnowledgeCommentUpdate(BaseModel):
    """更新评论。"""

    content: str = Field(..., min_length=1, description="评论内容")


class KnowledgeCommentResponse(BaseModel):
    """评论响应。"""

    id: UUID = Field(..., description="评论ID")
    article_id: UUID = Field(..., description="文章ID")
    content: str = Field(..., description="评论内容")
    author: str | None = Field(None, description="作者")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


# ── Extended article response with attachments and comments ──────────


class KnowledgeArticleDetail(KnowledgeArticleResponse):
    """文章详情（含附件和评论）。"""

    attachments: list[KnowledgeAttachmentResponse] = Field(
        default_factory=list, description="附件列表"
    )
    comments: list[KnowledgeCommentResponse] = Field(
        default_factory=list, description="评论列表"
    )
