"""Registration fee repository."""

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Integer, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.registration.models.fee import InspectionContact, RegistrationFee


def _year_from_filter(year_from: int) -> ColumnElement[bool]:
    """Filter entries whose payment_date year >= the given year.
    Rows with non-date payment_date or null are treated as year 9999 (always match)."""
    payment_year = func.cast(
        sa.case(
            (
                RegistrationFee.payment_date.op("~")("^[0-9]{4}"),
                func.left(RegistrationFee.payment_date, 4),
            ),
            else_="9999",
        ),
        Integer,
    )
    return payment_year >= year_from


class RegistrationFeeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _base_where(*, year_from: int | None = None) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [RegistrationFee.is_deleted.is_(False)]
        if year_from:
            conditions.append(_year_from_filter(year_from))
        return conditions

    async def count_entries(self, *, year_from: int | None = None) -> int:
        stmt = select(func.count()).select_from(RegistrationFee)
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_by_id(self, entry_id: UUID) -> RegistrationFee | None:
        result = await self.session.execute(
            select(RegistrationFee).where(
                RegistrationFee.id == entry_id,
                RegistrationFee.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        *,
        fee_type: str | None = None,
        payment_status: str | None = None,
        project_name: str | None = None,
        product_name: str | None = None,
        country: str | None = None,
        year: int | None = None,
        year_from: int | None = None,
        keyword: str | None = None,
    ) -> list[RegistrationFee]:
        stmt = select(RegistrationFee).where(RegistrationFee.is_deleted.is_(False))

        if year_from:
            stmt = stmt.where(_year_from_filter(year_from))
        if fee_type:
            stmt = stmt.where(RegistrationFee.fee_type == fee_type)
        if payment_status:
            stmt = stmt.where(RegistrationFee.payment_status == payment_status)
        if project_name:
            stmt = stmt.where(RegistrationFee.project_name == project_name)
        if product_name:
            stmt = stmt.where(RegistrationFee.product_name == product_name)
        if country:
            stmt = stmt.where(RegistrationFee.country == country)
        if year:
            stmt = stmt.where(func.extract("year", RegistrationFee.created_at) == year)
        if keyword:
            like_keyword = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    RegistrationFee.agency_name.ilike(like_keyword),
                    RegistrationFee.expense_content.ilike(like_keyword),
                    RegistrationFee.handler.ilike(like_keyword),
                    RegistrationFee.remarks.ilike(like_keyword),
                )
            )

        stmt = stmt.order_by(desc(RegistrationFee.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_entry(self, entry: RegistrationFee) -> RegistrationFee:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def update_entry(
        self,
        entry: RegistrationFee,
        data: dict[str, object | None],
    ) -> RegistrationFee:
        for key, value in data.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(RegistrationFee).where(RegistrationFee.id == entry.id)
        )
        return result.scalar_one()

    async def soft_delete(self, entry: RegistrationFee) -> None:
        entry.is_deleted = True
        await self.session.flush()

    async def get_fee_type_summaries(
        self, *, year_from: int | None = None
    ) -> list[dict[str, object]]:
        stmt = select(
            RegistrationFee.fee_type,
            func.sum(RegistrationFee.amount).label("total_amount"),
            func.count().label("record_count"),
        )
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        stmt = stmt.group_by(RegistrationFee.fee_type).order_by(
            func.sum(RegistrationFee.amount).desc()
        )
        result = await self.session.execute(stmt)
        return [
            {
                "fee_type": row.fee_type,
                "total_amount": Decimal(str(row.total_amount or 0)),
                "record_count": row.record_count,
            }
            for row in result.all()
        ]

    async def get_payment_status_summaries(
        self, *, year_from: int | None = None
    ) -> list[dict[str, object]]:
        stmt = select(
            RegistrationFee.payment_status,
            func.sum(RegistrationFee.amount).label("total_amount"),
            func.count().label("record_count"),
        )
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        stmt = stmt.group_by(RegistrationFee.payment_status).order_by(
            func.sum(RegistrationFee.amount).desc()
        )
        result = await self.session.execute(stmt)
        return [
            {
                "payment_status": row.payment_status,
                "total_amount": Decimal(str(row.total_amount or 0)),
                "record_count": row.record_count,
            }
            for row in result.all()
        ]

    async def get_year_summaries(
        self, *, year_from: int | None = None
    ) -> list[dict[str, object]]:
        year_expr = func.cast(func.left(RegistrationFee.payment_date, 4), Integer)
        stmt = select(
            year_expr.label("year"),
            func.sum(RegistrationFee.amount).label("total_amount"),
            func.count().label("record_count"),
        )
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        stmt = stmt.where(RegistrationFee.payment_date.op("~")(r"^\d{4}"))
        stmt = stmt.group_by(year_expr).order_by(desc("year"))
        result = await self.session.execute(stmt)
        return [
            {
                "year": int(row.year),
                "total_amount": Decimal(str(row.total_amount or 0)),
                "record_count": row.record_count,
            }
            for row in result.all()
        ]

    async def get_year_fee_type_summaries(
        self, *, year_from: int | None = None
    ) -> list[dict[str, object]]:
        """Returns cross-tabulation of year × fee_type with total_amount."""
        year_expr = func.cast(func.left(RegistrationFee.payment_date, 4), Integer)
        stmt = select(
            year_expr.label("year"),
            RegistrationFee.fee_type,
            func.sum(RegistrationFee.amount).label("total_amount"),
            func.count().label("record_count"),
        )
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        stmt = stmt.where(RegistrationFee.payment_date.op("~")(r"^\d{4}"))
        stmt = stmt.group_by(year_expr, RegistrationFee.fee_type).order_by(
            desc("year"), desc("total_amount")
        )
        result = await self.session.execute(stmt)
        return [
            {
                "year": int(row.year),
                "fee_type": row.fee_type,
                "total_amount": Decimal(str(row.total_amount or 0)),
                "record_count": row.record_count,
            }
            for row in result.all()
        ]

    async def get_agency_summaries(
        self, *, year_from: int | None = None
    ) -> list[dict[str, object]]:
        stmt = select(
            RegistrationFee.agency_name,
            func.sum(RegistrationFee.amount).label("total_amount"),
            func.count().label("record_count"),
        )
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        stmt = stmt.where(RegistrationFee.agency_name.is_not(None))
        stmt = (
            stmt.group_by(RegistrationFee.agency_name)
            .order_by(func.sum(RegistrationFee.amount).desc())
            .limit(15)
        )
        result = await self.session.execute(stmt)
        return [
            {
                "agency_name": row.agency_name,
                "total_amount": Decimal(str(row.total_amount or 0)),
                "record_count": row.record_count,
            }
            for row in result.all()
        ]

    async def get_total_amount(self, *, year_from: int | None = None) -> Decimal:
        stmt = select(func.sum(RegistrationFee.amount))
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar() or 0))

    async def get_pending_amount(self, *, year_from: int | None = None) -> Decimal:
        stmt = select(func.sum(RegistrationFee.amount)).where(
            RegistrationFee.payment_status == "待支付"
        )
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar() or 0))

    async def get_paid_amount(self, *, year_from: int | None = None) -> Decimal:
        stmt = select(func.sum(RegistrationFee.amount)).where(
            RegistrationFee.payment_status == "已支付"
        )
        for cond in self._base_where(year_from=year_from):
            stmt = stmt.where(cond)
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar() or 0))

    # ── Inspection contact operations ──────────────────────────────────

    async def count_inspection_contacts(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(InspectionContact)
            .where(InspectionContact.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def get_inspection_contact_by_id(
        self, contact_id: UUID
    ) -> InspectionContact | None:
        result = await self.session.execute(
            select(InspectionContact).where(
                InspectionContact.id == contact_id,
                InspectionContact.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_inspection_contacts(
        self, *, keyword: str | None = None
    ) -> list[InspectionContact]:
        stmt = select(InspectionContact).where(InspectionContact.is_deleted.is_(False))
        if keyword:
            like_keyword = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    InspectionContact.test_item.ilike(like_keyword),
                    InspectionContact.agency_name.ilike(like_keyword),
                    InspectionContact.contact_name.ilike(like_keyword),
                )
            )
        stmt = stmt.order_by(asc(InspectionContact.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_inspection_contact(
        self, contact: InspectionContact
    ) -> InspectionContact:
        self.session.add(contact)
        await self.session.flush()
        return contact

    async def create_inspection_contacts(
        self, contacts: list[InspectionContact]
    ) -> list[InspectionContact]:
        self.session.add_all(contacts)
        await self.session.flush()
        return contacts

    async def update_inspection_contact(
        self, contact: InspectionContact, data: dict[str, object | None]
    ) -> InspectionContact:
        for key, value in data.items():
            if hasattr(contact, key):
                setattr(contact, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(InspectionContact).where(InspectionContact.id == contact.id)
        )
        return result.scalar_one()

    async def soft_delete_inspection_contact(self, contact: InspectionContact) -> None:
        contact.is_deleted = True
        await self.session.flush()
