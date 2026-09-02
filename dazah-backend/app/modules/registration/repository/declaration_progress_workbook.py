"""Declaration progress workbook repository."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import asc, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.models import (
    RegistrationDeclarationProgressWorkbookVersion,
)


class RegistrationDeclarationProgressWorkbookRepository:
    """Repository for declaration progress workbook versions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_versions(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(RegistrationDeclarationProgressWorkbookVersion)
            .where(RegistrationDeclarationProgressWorkbookVersion.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def list_versions(
        self,
        *,
        sheet_key: str | None = None,
    ) -> list[RegistrationDeclarationProgressWorkbookVersion]:
        stmt = select(RegistrationDeclarationProgressWorkbookVersion).where(
            RegistrationDeclarationProgressWorkbookVersion.is_deleted.is_(False)
        )
        if sheet_key:
            stmt = stmt.where(
                RegistrationDeclarationProgressWorkbookVersion.sheet_key == sheet_key
            )
        stmt = stmt.order_by(
            asc(RegistrationDeclarationProgressWorkbookVersion.sheet_key),
            asc(RegistrationDeclarationProgressWorkbookVersion.source_sequence),
            asc(RegistrationDeclarationProgressWorkbookVersion.version_number),
            asc(RegistrationDeclarationProgressWorkbookVersion.created_at),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_versions_by_group(
        self,
        record_group_id: UUID,
    ) -> list[RegistrationDeclarationProgressWorkbookVersion]:
        result = await self.session.execute(
            select(RegistrationDeclarationProgressWorkbookVersion)
            .where(
                RegistrationDeclarationProgressWorkbookVersion.record_group_id
                == record_group_id,
                RegistrationDeclarationProgressWorkbookVersion.is_deleted.is_(False),
            )
            .order_by(
                asc(RegistrationDeclarationProgressWorkbookVersion.version_number),
                asc(RegistrationDeclarationProgressWorkbookVersion.created_at),
            )
        )
        return list(result.scalars().all())

    async def list_active_versions_by_sheet(
        self,
        sheet_key: str,
    ) -> list[RegistrationDeclarationProgressWorkbookVersion]:
        result = await self.session.execute(
            select(RegistrationDeclarationProgressWorkbookVersion)
            .where(
                RegistrationDeclarationProgressWorkbookVersion.is_deleted.is_(False),
                RegistrationDeclarationProgressWorkbookVersion.sheet_key == sheet_key,
            )
            .order_by(
                asc(RegistrationDeclarationProgressWorkbookVersion.source_sequence),
                asc(RegistrationDeclarationProgressWorkbookVersion.version_number),
                asc(RegistrationDeclarationProgressWorkbookVersion.created_at),
            )
        )
        return list(result.scalars().all())

    async def get_latest_version_by_group(
        self,
        record_group_id: UUID,
    ) -> RegistrationDeclarationProgressWorkbookVersion | None:
        result = await self.session.execute(
            select(RegistrationDeclarationProgressWorkbookVersion)
            .where(
                RegistrationDeclarationProgressWorkbookVersion.record_group_id
                == record_group_id,
                RegistrationDeclarationProgressWorkbookVersion.is_deleted.is_(False),
            )
            .order_by(
                desc(RegistrationDeclarationProgressWorkbookVersion.version_number),
                desc(RegistrationDeclarationProgressWorkbookVersion.created_at),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_max_source_sequence(self, sheet_key: str) -> int:
        result = await self.session.execute(
            select(
                func.max(RegistrationDeclarationProgressWorkbookVersion.source_sequence)
            ).where(
                RegistrationDeclarationProgressWorkbookVersion.sheet_key == sheet_key,
                RegistrationDeclarationProgressWorkbookVersion.is_deleted.is_(False),
            )
        )
        return int(result.scalar() or 0)

    async def get_next_version_number(self, record_group_id: UUID) -> int:
        result = await self.session.execute(
            select(
                func.max(RegistrationDeclarationProgressWorkbookVersion.version_number)
            ).where(
                RegistrationDeclarationProgressWorkbookVersion.record_group_id
                == record_group_id,
                RegistrationDeclarationProgressWorkbookVersion.is_deleted.is_(False),
            )
        )
        return int(result.scalar() or 0) + 1

    async def create_version(
        self,
        version: RegistrationDeclarationProgressWorkbookVersion,
    ) -> RegistrationDeclarationProgressWorkbookVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def create_versions(
        self,
        versions: list[RegistrationDeclarationProgressWorkbookVersion],
    ) -> list[RegistrationDeclarationProgressWorkbookVersion]:
        if not versions:
            return []
        self.session.add_all(versions)
        await self.session.flush()
        return versions

    async def replace_all_versions(
        self,
        versions: list[RegistrationDeclarationProgressWorkbookVersion],
    ) -> None:
        await self.session.execute(
            update(RegistrationDeclarationProgressWorkbookVersion)
            .values(is_deleted=True)
            .execution_options(synchronize_session=False)
        )
        if versions:
            self.session.add_all(versions)
        await self.session.flush()

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
