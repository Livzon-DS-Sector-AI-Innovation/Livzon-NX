"""Project ledger repository."""

from __future__ import annotations

from sqlalchemy import asc, select, update

from app.modules.registration.models import RegistrationProjectLedgerVersion
from app.modules.registration.repository.declaration_progress import (
    RegistrationDeclarationProgressRepository,
)


class RegistrationProjectLedgerRepository(RegistrationDeclarationProgressRepository):
    """Project ledger repository backed by the persisted workbook versions table."""

    async def replace_all_versions(
        self,
        versions: list[RegistrationProjectLedgerVersion],
    ) -> None:
        await self.session.execute(
            update(RegistrationProjectLedgerVersion)
            .values(is_deleted=True)
            .execution_options(synchronize_session=False)
        )
        if versions:
            self.session.add_all(versions)
        await self.session.flush()

    async def list_active_versions_by_sheet(
        self,
        sheet_key: str,
    ) -> list[RegistrationProjectLedgerVersion]:
        stmt = (
            select(RegistrationProjectLedgerVersion)
            .where(
                RegistrationProjectLedgerVersion.is_deleted.is_(False),
                RegistrationProjectLedgerVersion.sheet_key == sheet_key,
            )
            .order_by(
                asc(RegistrationProjectLedgerVersion.source_sequence),
                asc(RegistrationProjectLedgerVersion.version_number),
                asc(RegistrationProjectLedgerVersion.created_at),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
