"""Dossier Writer database queries."""
from typing import Optional, List
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import ProductDossier, DossierTemplate, DossierChapter, ChapterAsset


class DossierRepository:
    """品种资料数据库操作"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ====== Product Dossier ======

    async def check_duplicate(
        self, product_name: str, manufacturer: str, sterile_type: str
    ) -> Optional[ProductDossier]:
        """检查是否存在相同的品种资料"""
        stmt = (
            select(ProductDossier)
            .where(
                and_(
                    ProductDossier.product_name == product_name,
                    ProductDossier.manufacturer == manufacturer,
                    ProductDossier.sterile_type == sterile_type,
                    ProductDossier.is_deleted == False,
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_product_dossier(self, dossier: ProductDossier) -> ProductDossier:
        """创建品种资料"""
        self.db.add(dossier)
        await self.db.flush()
        return dossier

    async def get_product_dossier(self, dossier_id: UUID) -> Optional[ProductDossier]:
        """获取品种资料详情"""
        stmt = (
            select(ProductDossier)
            .where(and_(ProductDossier.id == dossier_id, ProductDossier.is_deleted == False))
            .options(selectinload(ProductDossier.templates))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_product_dossiers(
        self, skip: int = 0, limit: int = 100
    ) -> tuple[List[ProductDossier], int]:
        """获取品种资料列表"""
        # 查询总数
        count_stmt = select(func.count()).select_from(ProductDossier).where(
            ProductDossier.is_deleted == False
        )
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 查询列表
        stmt = (
            select(ProductDossier)
            .where(ProductDossier.is_deleted == False)
            .order_by(ProductDossier.created_at.desc())
            .offset(skip)
            .limit(limit)
            .options(selectinload(ProductDossier.chapters))
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def update_product_dossier(
        self, dossier_id: UUID, **kwargs
    ) -> Optional[ProductDossier]:
        """更新品种资料"""
        dossier = await self.get_product_dossier(dossier_id)
        if not dossier:
            return None
        for key, value in kwargs.items():
            if hasattr(dossier, key):
                setattr(dossier, key, value)
        await self.db.flush()
        return dossier

    async def delete_product_dossier(self, dossier_id: UUID) -> bool:
        """软删除品种资料"""
        dossier = await self.get_product_dossier(dossier_id)
        if not dossier:
            return False
        dossier.is_deleted = True
        await self.db.flush()
        return True

    # ====== Template ======

    async def create_template(self, template: DossierTemplate) -> DossierTemplate:
        """创建模板记录"""
        self.db.add(template)
        await self.db.flush()
        return template

    async def get_template_by_filename(self, dossier_id: UUID, filename: str) -> Optional[DossierTemplate]:
        """根据文件名查找模板（用于覆盖更新），返回最新的一条"""
        stmt = (
            select(DossierTemplate)
            .where(
                and_(
                    DossierTemplate.product_dossier_id == dossier_id,
                    DossierTemplate.original_filename == filename,
                )
            )
            .order_by(DossierTemplate.uploaded_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_templates(self, dossier_id: UUID) -> List[DossierTemplate]:
        """获取模板列表"""
        stmt = (
            select(DossierTemplate)
            .where(DossierTemplate.product_dossier_id == dossier_id)
            .order_by(DossierTemplate.uploaded_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ====== Chapter ======

    async def create_chapter(self, chapter: DossierChapter) -> DossierChapter:
        """创建章节"""
        self.db.add(chapter)
        await self.db.flush()
        return chapter

    async def bulk_create_chapters(self, chapters: List[DossierChapter]) -> None:
        """批量创建章节"""
        self.db.add_all(chapters)
        await self.db.flush()

    async def delete_chapters_by_dossier(self, dossier_id: UUID) -> int:
        """删除品种的所有章节"""
        stmt = select(DossierChapter).where(
            DossierChapter.product_dossier_id == dossier_id
        )
        result = await self.db.execute(stmt)
        chapters = result.scalars().all()
        count = len(chapters)
        for chapter in chapters:
            await self.db.delete(chapter)
        await self.db.flush()
        return count

    async def get_chapter_tree(self, dossier_id: UUID) -> List[DossierChapter]:
        """获取章节树（扁平列表，前端组装树）"""
        stmt = (
            select(DossierChapter)
            .where(DossierChapter.product_dossier_id == dossier_id)
            .order_by(DossierChapter.sort_order)
            .options(selectinload(DossierChapter.assets))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_chapter(self, chapter_id: UUID) -> Optional[DossierChapter]:
        """获取章节详情"""
        stmt = (
            select(DossierChapter)
            .where(DossierChapter.id == chapter_id)
            .options(selectinload(DossierChapter.assets))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_chapter(self, chapter_id: UUID, **kwargs) -> Optional[DossierChapter]:
        """更新章节"""
        chapter = await self.get_chapter(chapter_id)
        if not chapter:
            return None
        for key, value in kwargs.items():
            if hasattr(chapter, key):
                setattr(chapter, key, value)
        await self.db.flush()
        return chapter

    async def count_chapters(self, dossier_id: UUID) -> int:
        """统计章节数量"""
        stmt = (
            select(func.count())
            .select_from(DossierChapter)
            .where(DossierChapter.product_dossier_id == dossier_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ====== Asset ======

    async def create_asset(self, asset: ChapterAsset) -> ChapterAsset:
        """创建素材记录"""
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def list_assets(self, chapter_id: UUID) -> List[ChapterAsset]:
        """获取章节素材列表"""
        stmt = (
            select(ChapterAsset)
            .where(ChapterAsset.chapter_id == chapter_id)
            .order_by(ChapterAsset.uploaded_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_asset(self, asset_id: UUID) -> Optional[ChapterAsset]:
        """获取素材详情"""
        stmt = select(ChapterAsset).where(ChapterAsset.id == asset_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_asset(self, asset_id: UUID) -> bool:
        """删除素材"""
        asset = await self.get_asset(asset_id)
        if not asset:
            return False
        await self.db.delete(asset)
        await self.db.flush()
        return True

    async def count_assets(self, chapter_id: UUID) -> int:
        """统计章节素材数量"""
        stmt = (
            select(func.count())
            .select_from(ChapterAsset)
            .where(ChapterAsset.chapter_id == chapter_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0
