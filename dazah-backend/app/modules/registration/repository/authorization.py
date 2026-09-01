"""Registration database queries live here."""

from uuid import UUID

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria
from sqlalchemy.sql.base import ExecutableOption

from app.modules.registration.models import (
    AuthorizationFdaEntry,
    AuthorizationLedgerEntry,
    AuthorizationLedgerMain,
    AuthorizationLedgerUpdate,
    AuthorizationLetter,
    ReferenceStandard,
    SupplementaryReply,
)


class AuthorizationLetterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, letter_id: UUID) -> AuthorizationLetter | None:
        result = await self.session.execute(
            select(AuthorizationLetter).where(
                AuthorizationLetter.id == letter_id,
                AuthorizationLetter.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_letters(
        self,
        *,
        product_name: str | None = None,
        preparation_unit: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[AuthorizationLetter], int]:
        stmt = select(AuthorizationLetter).where(
            AuthorizationLetter.is_deleted.is_(False)
        )

        if product_name:
            stmt = stmt.where(
                AuthorizationLetter.product_name.ilike(f"%{product_name}%")
            )
        if preparation_unit:
            stmt = stmt.where(
                AuthorizationLetter.preparation_unit.ilike(f"%{preparation_unit}%")
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        default_sort = AuthorizationLetter.created_at
        sort_column = getattr(AuthorizationLetter, sort_by, default_sort)
        order_func = desc if sort_order == "desc" else asc
        stmt = stmt.order_by(order_func(sort_column))
        stmt = stmt.offset(max(page - 1, 0) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, letter: AuthorizationLetter) -> AuthorizationLetter:
        self.session.add(letter)
        await self.session.flush()
        return letter

    async def soft_delete(self, letter: AuthorizationLetter) -> None:
        letter.is_deleted = True
        await self.session.flush()


class AuthorizationLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _main_load_options() -> tuple[ExecutableOption, ...]:
        return (
            selectinload(AuthorizationLedgerMain.updates),
            with_loader_criteria(
                AuthorizationLedgerUpdate,
                AuthorizationLedgerUpdate.is_deleted.is_(False),
                include_aliases=True,
            ),
        )

    async def count_entries(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(AuthorizationLedgerEntry)
            .where(AuthorizationLedgerEntry.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def get_by_id(self, entry_id: UUID) -> AuthorizationLedgerEntry | None:
        result = await self.session.execute(
            select(AuthorizationLedgerEntry).where(
                AuthorizationLedgerEntry.id == entry_id,
                AuthorizationLedgerEntry.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        *,
        product_name: str | None = None,
        market_name: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> list[AuthorizationLedgerEntry]:
        stmt = select(AuthorizationLedgerEntry).where(
            AuthorizationLedgerEntry.is_deleted.is_(False)
        )

        if product_name:
            stmt = stmt.where(AuthorizationLedgerEntry.product_name == product_name)
        if market_name:
            stmt = stmt.where(AuthorizationLedgerEntry.market_name == market_name)
        if status:
            stmt = stmt.where(AuthorizationLedgerEntry.status == status)
        if keyword:
            like_keyword = f"%{keyword}%"
            stmt = stmt.where(
                AuthorizationLedgerEntry.authorization_file_name.ilike(like_keyword)
                | AuthorizationLedgerEntry.company_name.ilike(like_keyword)
                | AuthorizationLedgerEntry.purpose.ilike(like_keyword)
                | AuthorizationLedgerEntry.remarks.ilike(like_keyword)
            )

        stmt = stmt.order_by(
            asc(AuthorizationLedgerEntry.product_name),
            asc(AuthorizationLedgerEntry.market_name),
            asc(AuthorizationLedgerEntry.authorization_date),
            asc(AuthorizationLedgerEntry.created_at),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_entry(
        self, entry: AuthorizationLedgerEntry
    ) -> AuthorizationLedgerEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def create_entries(
        self, entries: list[AuthorizationLedgerEntry]
    ) -> list[AuthorizationLedgerEntry]:
        self.session.add_all(entries)
        await self.session.flush()
        return entries

    async def get_main_by_id(self, main_id: UUID) -> AuthorizationLedgerMain | None:
        result = await self.session.execute(
            select(AuthorizationLedgerMain)
            .options(*self._main_load_options())
            .where(
                AuthorizationLedgerMain.id == main_id,
                AuthorizationLedgerMain.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_main_entries(
        self,
        *,
        product_name: str | None = None,
        market_name: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> list[AuthorizationLedgerMain]:
        stmt = (
            select(AuthorizationLedgerMain)
            .options(*self._main_load_options())
            .where(AuthorizationLedgerMain.is_deleted.is_(False))
        )

        if product_name:
            stmt = stmt.where(AuthorizationLedgerMain.product_name == product_name)
        if market_name:
            stmt = stmt.where(AuthorizationLedgerMain.market_name == market_name)
        if status:
            stmt = stmt.where(AuthorizationLedgerMain.status == status)
        if keyword:
            like_keyword = f"%{keyword}%"
            update_keyword_exists = (
                select(AuthorizationLedgerUpdate.id)
                .where(
                    AuthorizationLedgerUpdate.ledger_main_id
                    == AuthorizationLedgerMain.id,
                    AuthorizationLedgerUpdate.is_deleted.is_(False),
                    or_(
                        AuthorizationLedgerUpdate.authorization_date.ilike(
                            like_keyword
                        ),
                        AuthorizationLedgerUpdate.handler.ilike(like_keyword),
                        AuthorizationLedgerUpdate.remarks.ilike(like_keyword),
                    ),
                )
                .exists()
            )
            stmt = stmt.where(
                or_(
                    AuthorizationLedgerMain.product_name.ilike(like_keyword),
                    AuthorizationLedgerMain.market_name.ilike(like_keyword),
                    AuthorizationLedgerMain.source_sequence.ilike(like_keyword),
                    AuthorizationLedgerMain.authorization_file_name.ilike(like_keyword),
                    AuthorizationLedgerMain.quality_standard.ilike(like_keyword),
                    AuthorizationLedgerMain.company_name.ilike(like_keyword),
                    AuthorizationLedgerMain.country.ilike(like_keyword),
                    AuthorizationLedgerMain.customer_code.ilike(like_keyword),
                    AuthorizationLedgerMain.purpose.ilike(like_keyword),
                    AuthorizationLedgerMain.status.ilike(like_keyword),
                    update_keyword_exists,
                )
            )

        stmt = stmt.order_by(
            asc(AuthorizationLedgerMain.product_name),
            asc(AuthorizationLedgerMain.market_name),
            asc(AuthorizationLedgerMain.source_sequence),
            asc(AuthorizationLedgerMain.created_at),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def create_main_entry(
        self,
        entry: AuthorizationLedgerMain,
    ) -> AuthorizationLedgerMain:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def update_main_entry(
        self,
        entry: AuthorizationLedgerMain,
        data: dict[str, str | None],
    ) -> AuthorizationLedgerMain:
        for key, value in data.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        await self.session.flush()
        reloaded = await self.get_main_by_id(entry.id)
        return reloaded or entry

    async def soft_delete_main_entry(self, entry: AuthorizationLedgerMain) -> None:
        entry.is_deleted = True
        for update in entry.updates:
            update.is_deleted = True
        await self.session.flush()

    async def get_update_by_id(
        self, update_id: UUID
    ) -> AuthorizationLedgerUpdate | None:
        result = await self.session.execute(
            select(AuthorizationLedgerUpdate).where(
                AuthorizationLedgerUpdate.id == update_id,
                AuthorizationLedgerUpdate.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_update_entry(
        self,
        entry: AuthorizationLedgerUpdate,
    ) -> AuthorizationLedgerUpdate:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def update_update_entry(
        self,
        entry: AuthorizationLedgerUpdate,
        data: dict[str, str | None],
    ) -> AuthorizationLedgerUpdate:
        for key, value in data.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(AuthorizationLedgerUpdate).where(
                AuthorizationLedgerUpdate.id == entry.id
            )
        )
        return result.scalar_one()

    async def count_active_updates(self, main_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(AuthorizationLedgerUpdate)
            .where(
                AuthorizationLedgerUpdate.ledger_main_id == main_id,
                AuthorizationLedgerUpdate.is_deleted.is_(False),
            )
        )
        return int(result.scalar() or 0)

    async def get_next_update_sort_order(self, main_id: UUID) -> int:
        result = await self.session.execute(
            select(
                func.coalesce(func.max(AuthorizationLedgerUpdate.sort_order), 0) + 1
            ).where(
                AuthorizationLedgerUpdate.ledger_main_id == main_id,
                AuthorizationLedgerUpdate.is_deleted.is_(False),
            )
        )
        return int(result.scalar() or 1)

    async def soft_delete_update_entry(self, entry: AuthorizationLedgerUpdate) -> None:
        entry.is_deleted = True
        await self.session.flush()

    async def update_entry(
        self,
        entry: AuthorizationLedgerEntry,
        data: dict[str, str | None],
    ) -> AuthorizationLedgerEntry:
        for key, value in data.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(AuthorizationLedgerEntry).where(
                AuthorizationLedgerEntry.id == entry.id
            )
        )
        return result.scalar_one()

    async def soft_delete(self, entry: AuthorizationLedgerEntry) -> None:
        entry.is_deleted = True
        await self.session.flush()


class AuthorizationFdaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_entries(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(AuthorizationFdaEntry)
            .where(AuthorizationFdaEntry.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def get_by_id(self, entry_id: UUID) -> AuthorizationFdaEntry | None:
        result = await self.session.execute(
            select(AuthorizationFdaEntry).where(
                AuthorizationFdaEntry.id == entry_id,
                AuthorizationFdaEntry.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        *,
        product_name: str | None = None,
        keyword: str | None = None,
    ) -> list[AuthorizationFdaEntry]:
        stmt = select(AuthorizationFdaEntry).where(
            AuthorizationFdaEntry.is_deleted.is_(False)
        )

        if product_name:
            stmt = stmt.where(AuthorizationFdaEntry.product_name == product_name)
        if keyword:
            like_keyword = f"%{keyword}%"
            stmt = stmt.where(
                AuthorizationFdaEntry.company_name.ilike(like_keyword)
                | AuthorizationFdaEntry.address.ilike(like_keyword)
                | AuthorizationFdaEntry.reference_number.ilike(like_keyword)
                | AuthorizationFdaEntry.referenced_sections.ilike(like_keyword)
            )

        stmt = stmt.order_by(
            asc(AuthorizationFdaEntry.product_name),
            asc(AuthorizationFdaEntry.source_sequence),
            asc(AuthorizationFdaEntry.created_at),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_entry(self, entry: AuthorizationFdaEntry) -> AuthorizationFdaEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def create_entries(
        self, entries: list[AuthorizationFdaEntry]
    ) -> list[AuthorizationFdaEntry]:
        self.session.add_all(entries)
        await self.session.flush()
        return entries

    async def update_entry(
        self,
        entry: AuthorizationFdaEntry,
        data: dict[str, str | int | None],
    ) -> AuthorizationFdaEntry:
        for key, value in data.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(AuthorizationFdaEntry).where(AuthorizationFdaEntry.id == entry.id)
        )
        return result.scalar_one()

    async def soft_delete(self, entry: AuthorizationFdaEntry) -> None:
        entry.is_deleted = True
        await self.session.flush()


class SupplementaryReplyRepository:
    """Repository retained for the legacy supplementary-reply API."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, reply_id: UUID) -> SupplementaryReply | None:
        result = await self.session.execute(
            select(SupplementaryReply).where(
                SupplementaryReply.id == reply_id,
                SupplementaryReply.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_replies(
        self,
        *,
        drug_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[SupplementaryReply], int]:
        stmt = select(SupplementaryReply).where(
            SupplementaryReply.is_deleted.is_(False)
        )
        if drug_name:
            stmt = stmt.where(SupplementaryReply.drug_name.ilike(f"%{drug_name}%"))
        total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(stmt.subquery())
                )
            ).scalar()
            or 0
        )
        sort_column = getattr(
            SupplementaryReply, sort_by, SupplementaryReply.created_at
        )
        stmt = stmt.order_by((desc if sort_order == "desc" else asc)(sort_column))
        stmt = stmt.offset(max(page - 1, 0) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, reply: SupplementaryReply) -> SupplementaryReply:
        self.session.add(reply)
        await self.session.flush()
        await self.session.refresh(reply)
        return reply

    async def soft_delete(self, reply: SupplementaryReply) -> None:
        reply.is_deleted = True
        await self.session.flush()


class ReferenceStandardRepository:
    """Repository retained for the legacy reference-standard API."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, record_id: UUID) -> ReferenceStandard | None:
        result = await self.session.execute(
            select(ReferenceStandard).where(
                ReferenceStandard.id == record_id,
                ReferenceStandard.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_records(
        self,
        *,
        drug_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[ReferenceStandard], int]:
        stmt = select(ReferenceStandard).where(ReferenceStandard.is_deleted.is_(False))
        if drug_name:
            stmt = stmt.where(ReferenceStandard.drug_name.ilike(f"%{drug_name}%"))
        total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(stmt.subquery())
                )
            ).scalar()
            or 0
        )
        sort_column = getattr(ReferenceStandard, sort_by, ReferenceStandard.created_at)
        stmt = stmt.order_by((desc if sort_order == "desc" else asc)(sort_column))
        stmt = stmt.offset(max(page - 1, 0) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, record: ReferenceStandard) -> ReferenceStandard:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def soft_delete(self, record: ReferenceStandard) -> None:
        record.is_deleted = True
        await self.session.flush()
