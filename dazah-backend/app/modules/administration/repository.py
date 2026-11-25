"""Administration database queries."""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administration.models import (
    AdministrationFeishuConfig,
    AdministrationFeishuReadField,
    AdministrationFeishuReadPageBinding,
    AdministrationFeishuReadRecord,
    AdministrationFeishuReadResource,
    AdministrationNotice,
)


@dataclass(frozen=True)
class MirroredTable:
    """一个页面绑定的数据表在当前激活镜像版本下的字段与记录快照。"""

    resource: AdministrationFeishuReadResource
    fields: list[AdministrationFeishuReadField]
    records: list[AdministrationFeishuReadRecord]


@dataclass(frozen=True)
class NoticePage:
    """公告台账分页查询结果。"""

    items: list[AdministrationNotice]
    total: int


class AdministrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest_config(self) -> AdministrationFeishuConfig | None:
        """最近更新的一行配置（含停用行，供设置页回显）。"""
        return (
            (
                await self.session.execute(
                    select(AdministrationFeishuConfig)
                    .where(AdministrationFeishuConfig.is_deleted.is_(False))
                    .order_by(AdministrationFeishuConfig.updated_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def get_active_config(self) -> AdministrationFeishuConfig | None:
        """最近更新的激活配置（同步与读取镜像使用）。"""
        return (
            (
                await self.session.execute(
                    select(AdministrationFeishuConfig)
                    .where(
                        AdministrationFeishuConfig.is_active.is_(True),
                        AdministrationFeishuConfig.is_deleted.is_(False),
                    )
                    .order_by(AdministrationFeishuConfig.updated_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def get_config(
        self, config_id: uuid.UUID
    ) -> AdministrationFeishuConfig | None:
        return (
            (
                await self.session.execute(
                    select(AdministrationFeishuConfig).where(
                        AdministrationFeishuConfig.id == config_id,
                        AdministrationFeishuConfig.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .first()
        )

    def add_config(self, config: AdministrationFeishuConfig) -> None:
        self.session.add(config)

    async def get_resource(
        self, resource_id: uuid.UUID
    ) -> AdministrationFeishuReadResource | None:
        return (
            (
                await self.session.execute(
                    select(AdministrationFeishuReadResource).where(
                        AdministrationFeishuReadResource.id == resource_id,
                        AdministrationFeishuReadResource.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .first()
        )

    async def list_syncable_resources(self) -> list[AdministrationFeishuReadResource]:
        result = await self.session.execute(
            select(AdministrationFeishuReadResource)
            .where(AdministrationFeishuReadResource.is_deleted.is_(False))
            .order_by(AdministrationFeishuReadResource.title.asc())
        )
        return list(result.scalars().all())

    async def get_default_bound_table(self, page_key: str) -> MirroredTable | None:
        """取页面默认（否则排序第一）启用绑定的数据表及其激活版本记录。"""
        tables = await self.list_bound_tables(page_key)
        return tables[0] if tables else None

    async def list_bound_tables(self, page_key: str) -> list[MirroredTable]:
        """页面全部启用绑定的数据表快照（默认绑定优先，其余按 sort_order）。"""
        rows = (
            await self.session.execute(
                select(
                    AdministrationFeishuReadPageBinding,
                    AdministrationFeishuReadResource,
                )
                .join(
                    AdministrationFeishuReadResource,
                    AdministrationFeishuReadResource.id
                    == AdministrationFeishuReadPageBinding.resource_id,
                )
                .where(
                    AdministrationFeishuReadPageBinding.page_key == page_key,
                    AdministrationFeishuReadPageBinding.is_enabled.is_(True),
                    AdministrationFeishuReadPageBinding.is_deleted.is_(False),
                    AdministrationFeishuReadResource.is_deleted.is_(False),
                )
                .order_by(
                    AdministrationFeishuReadPageBinding.is_default.desc(),
                    AdministrationFeishuReadPageBinding.sort_order.asc(),
                )
            )
        ).all()
        return [await self._load_table_snapshot(resource) for _, resource in rows]

    async def _load_table_snapshot(
        self, resource: AdministrationFeishuReadResource
    ) -> MirroredTable:
        fields_result = await self.session.execute(
            select(AdministrationFeishuReadField)
            .where(
                AdministrationFeishuReadField.resource_id == resource.id,
                AdministrationFeishuReadField.is_deleted.is_(False),
            )
            .order_by(AdministrationFeishuReadField.sort_order.asc())
        )
        records: list[AdministrationFeishuReadRecord] = []
        if resource.active_mirror_version is not None:
            records_result = await self.session.execute(
                select(AdministrationFeishuReadRecord)
                .where(
                    AdministrationFeishuReadRecord.resource_id == resource.id,
                    AdministrationFeishuReadRecord.mirror_version
                    == resource.active_mirror_version,
                    AdministrationFeishuReadRecord.is_deleted.is_(False),
                )
                .order_by(AdministrationFeishuReadRecord.record_id.asc())
            )
            records = list(records_result.scalars().all())
        return MirroredTable(
            resource=resource,
            fields=list(fields_result.scalars().all()),
            records=records,
        )

    # ── 公告通知台账 ─────────────────────────────────────────────

    async def get_notice(self, notice_id: uuid.UUID) -> AdministrationNotice | None:
        return (
            (
                await self.session.execute(
                    select(AdministrationNotice).where(
                        AdministrationNotice.id == notice_id,
                        AdministrationNotice.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .first()
        )

    async def list_notices(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        category: str | None = None,
    ) -> NoticePage:
        """台账分页（keyword 走 search_text 元数据，不含公告内容）。"""
        conditions: list[ColumnElement[bool]] = [
            AdministrationNotice.is_deleted.is_(False)
        ]
        if keyword:
            # LIKE 通配符按字面匹配，避免 %/_ 被解释成模式
            escaped = (
                keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            conditions.append(
                AdministrationNotice.search_text.ilike(f"%{escaped}%", escape="\\")
            )
        if category:
            conditions.append(AdministrationNotice.category == category)
        total = (
            await self.session.execute(
                select(func.count())
                .select_from(AdministrationNotice)
                .where(*conditions)
            )
        ).scalar() or 0
        result = await self.session.execute(
            select(AdministrationNotice)
            .where(*conditions)
            .order_by(
                AdministrationNotice.published_at.desc().nulls_last(),
                AdministrationNotice.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        return NoticePage(items=items, total=total)

    async def list_notice_categories(self) -> list[str]:
        """现存非空类别（供筛选下拉），按名称排序。"""
        result = await self.session.execute(
            select(AdministrationNotice.category)
            .where(
                AdministrationNotice.is_deleted.is_(False),
                AdministrationNotice.category != "",
            )
            .distinct()
            .order_by(AdministrationNotice.category.asc())
        )
        return list(result.scalars().all())

    def add_notice(self, notice: AdministrationNotice) -> None:
        self.session.add(notice)
