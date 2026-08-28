"""Declaration progress repository."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.models import RegistrationDeclarationProgressVersion


class RegistrationDeclarationProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_versions(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(RegistrationDeclarationProgressVersion)
            .where(RegistrationDeclarationProgressVersion.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def list_versions(
        self,
        *,
        sheet_key: str | None = None,
    ) -> list[RegistrationDeclarationProgressVersion]:
        stmt = select(RegistrationDeclarationProgressVersion).where(
            RegistrationDeclarationProgressVersion.is_deleted.is_(False)
        )
        if sheet_key:
            stmt = stmt.where(
                RegistrationDeclarationProgressVersion.sheet_key == sheet_key
            )
        stmt = stmt.order_by(
            asc(RegistrationDeclarationProgressVersion.sheet_key),
            asc(RegistrationDeclarationProgressVersion.source_sequence),
            asc(RegistrationDeclarationProgressVersion.version_number),
            asc(RegistrationDeclarationProgressVersion.created_at),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_versions_by_group(
        self,
        record_group_id: UUID,
    ) -> list[RegistrationDeclarationProgressVersion]:
        result = await self.session.execute(
            select(RegistrationDeclarationProgressVersion)
            .where(
                RegistrationDeclarationProgressVersion.record_group_id
                == record_group_id,
                RegistrationDeclarationProgressVersion.is_deleted.is_(False),
            )
            .order_by(
                asc(RegistrationDeclarationProgressVersion.version_number),
                asc(RegistrationDeclarationProgressVersion.created_at),
            )
        )
        return list(result.scalars().all())

    async def get_latest_version_by_group(
        self,
        record_group_id: UUID,
    ) -> RegistrationDeclarationProgressVersion | None:
        result = await self.session.execute(
            select(RegistrationDeclarationProgressVersion)
            .where(
                RegistrationDeclarationProgressVersion.record_group_id
                == record_group_id,
                RegistrationDeclarationProgressVersion.is_deleted.is_(False),
            )
            .order_by(
                desc(RegistrationDeclarationProgressVersion.version_number),
                desc(RegistrationDeclarationProgressVersion.created_at),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_max_source_sequence(self, sheet_key: str) -> int:
        result = await self.session.execute(
            select(
                func.max(RegistrationDeclarationProgressVersion.source_sequence)
            ).where(
                RegistrationDeclarationProgressVersion.sheet_key == sheet_key,
                RegistrationDeclarationProgressVersion.is_deleted.is_(False),
            )
        )
        return int(result.scalar() or 0)

    async def get_next_version_number(self, record_group_id: UUID) -> int:
        result = await self.session.execute(
            select(
                func.max(RegistrationDeclarationProgressVersion.version_number)
            ).where(
                RegistrationDeclarationProgressVersion.record_group_id
                == record_group_id,
                RegistrationDeclarationProgressVersion.is_deleted.is_(False),
            )
        )
        return int(result.scalar() or 0) + 1

    async def create_version(
        self,
        version: RegistrationDeclarationProgressVersion,
    ) -> RegistrationDeclarationProgressVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def create_versions(
        self,
        versions: list[RegistrationDeclarationProgressVersion],
    ) -> list[RegistrationDeclarationProgressVersion]:
        if not versions:
            return []
        self.session.add_all(versions)
        await self.session.flush()
        return versions

    async def soft_delete_group(self, record_group_id: UUID) -> int:
        versions = await self.list_versions_by_group(record_group_id)
        deleted_count = 0
        for version in versions:
            if not version.is_deleted:
                version.is_deleted = True
                deleted_count += 1
        await self.session.flush()
        return deleted_count

    @staticmethod
    def generate_group_id() -> uuid.UUID:
        return uuid.uuid4()
