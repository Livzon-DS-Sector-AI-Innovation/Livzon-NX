"""Administration database queries."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administration.models import (
    AdministrationFeishuConfig,
    AdministrationFeishuReadField,
    AdministrationFeishuReadPageBinding,
    AdministrationFeishuReadRecord,
    AdministrationFeishuReadResource,
)


@dataclass(frozen=True)
class MirroredTable:
    """一个页面绑定的数据表在当前激活镜像版本下的字段与记录快照。"""

    resource: AdministrationFeishuReadResource
    fields: list[AdministrationFeishuReadField]
    records: list[AdministrationFeishuReadRecord]


class AdministrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest_config(self) -> AdministrationFeishuConfig | None:
        """最近更新的一行配置（含停用行，供设置页回显）。"""
        return (await self.session.execute(
            select(AdministrationFeishuConfig)
            .where(AdministrationFeishuConfig.is_deleted.is_(False))
            .order_by(AdministrationFeishuConfig.updated_at.desc())
            .limit(1)
        )).scalars().first()

    async def get_active_config(self) -> AdministrationFeishuConfig | None:
        """最近更新的激活配置（同步与读取镜像使用）。"""
        return (await self.session.execute(
            select(AdministrationFeishuConfig)
            .where(
                AdministrationFeishuConfig.is_active.is_(True),
                AdministrationFeishuConfig.is_deleted.is_(False),
            )
            .order_by(AdministrationFeishuConfig.updated_at.desc())
            .limit(1)
        )).scalars().first()

    async def get_config(
        self, config_id: uuid.UUID
    ) -> AdministrationFeishuConfig | None:
        return (await self.session.execute(
            select(AdministrationFeishuConfig).where(
                AdministrationFeishuConfig.id == config_id,
                AdministrationFeishuConfig.is_deleted.is_(False),
            )
        )).scalars().first()

    def add_config(self, config: AdministrationFeishuConfig) -> None:
        self.session.add(config)

    async def get_resource(
        self, resource_id: uuid.UUID
    ) -> AdministrationFeishuReadResource | None:
        return (await self.session.execute(
            select(AdministrationFeishuReadResource).where(
                AdministrationFeishuReadResource.id == resource_id,
                AdministrationFeishuReadResource.is_deleted.is_(False),
            )
        )).scalars().first()

    async def list_syncable_resources(self) -> list[AdministrationFeishuReadResource]:
        result = await self.session.execute(
            select(AdministrationFeishuReadResource)
            .where(AdministrationFeishuReadResource.is_deleted.is_(False))
            .order_by(AdministrationFeishuReadResource.title.asc())
        )
        return list(result.scalars().all())

    async def get_default_bound_table(self, page_key: str) -> MirroredTable | None:
        """取页面默认（否则排序第一）启用绑定的数据表及其激活版本记录。"""
        row = (
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
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        resource = row[1]
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
