"""Certificate management repository."""

from uuid import UUID

from sqlalchemy import asc, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.public_api import (
    DepartmentContact,
    get_department_contact_by_open_id,
    list_department_contacts,
)
from app.modules.registration.models import (
    RegistrationCertificateEntry,
    RegistrationCertificateReminderNotification,
    RegistrationCertificateReminderSetting,
)


class RegistrationCertificateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_entries(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(RegistrationCertificateEntry)
            .where(RegistrationCertificateEntry.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def get_by_id(self, entry_id: UUID) -> RegistrationCertificateEntry | None:
        result = await self.session.execute(
            select(RegistrationCertificateEntry).where(
                RegistrationCertificateEntry.id == entry_id,
                RegistrationCertificateEntry.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        *,
        sheet_key: str | None = None,
        keyword: str | None = None,
        expiry_status: str | None = None,
    ) -> list[RegistrationCertificateEntry]:
        stmt = select(RegistrationCertificateEntry).where(
            RegistrationCertificateEntry.is_deleted.is_(False)
        )

        if sheet_key:
            stmt = stmt.where(RegistrationCertificateEntry.sheet_key == sheet_key)

        if keyword:
            like_keyword = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    RegistrationCertificateEntry.certificate_name.ilike(like_keyword),
                    RegistrationCertificateEntry.certificate_number.ilike(like_keyword),
                    RegistrationCertificateEntry.issuing_authority.ilike(like_keyword),
                    RegistrationCertificateEntry.product_scope.ilike(like_keyword),
                    RegistrationCertificateEntry.remarks.ilike(like_keyword),
                )
            )

        if expiry_status:
            if expiry_status == "已过期":
                stmt = stmt.where(RegistrationCertificateEntry.expiry_date.is_not(None))
            elif expiry_status == "90天内到期":
                stmt = stmt.where(RegistrationCertificateEntry.expiry_date.is_not(None))

        stmt = stmt.order_by(
            asc(RegistrationCertificateEntry.sheet_key),
            asc(RegistrationCertificateEntry.source_sequence),
            asc(RegistrationCertificateEntry.created_at),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_entry(
        self,
        entry: RegistrationCertificateEntry,
    ) -> RegistrationCertificateEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_next_source_sequence(self, sheet_key: str) -> int:
        result = await self.session.execute(
            select(func.max(RegistrationCertificateEntry.source_sequence)).where(
                RegistrationCertificateEntry.is_deleted.is_(False),
                RegistrationCertificateEntry.sheet_key == sheet_key,
            )
        )
        current_max = result.scalar()
        if current_max is None:
            return 1
        return int(current_max) + 1

    async def create_entries(
        self,
        entries: list[RegistrationCertificateEntry],
    ) -> list[RegistrationCertificateEntry]:
        self.session.add_all(entries)
        await self.session.flush()
        return entries

    async def get_reminder_setting(
        self,
    ) -> RegistrationCertificateReminderSetting | None:
        result = await self.session.execute(
            select(RegistrationCertificateReminderSetting)
            .where(RegistrationCertificateReminderSetting.is_deleted.is_(False))
            .order_by(asc(RegistrationCertificateReminderSetting.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_reminder_setting(
        self,
        *,
        setting: RegistrationCertificateReminderSetting | None,
        is_enabled: bool,
        reminder_days: int,
        recipient_open_id: str | None,
        recipient_name: str | None,
        recipient_department: str | None,
    ) -> RegistrationCertificateReminderSetting:
        if setting is None:
            setting = RegistrationCertificateReminderSetting(
                is_enabled=is_enabled,
                reminder_days=reminder_days,
                recipient_open_id=recipient_open_id,
                recipient_name=recipient_name,
                recipient_department=recipient_department,
            )
            self.session.add(setting)
        else:
            setting.is_enabled = is_enabled
            setting.reminder_days = reminder_days
            setting.recipient_open_id = recipient_open_id
            setting.recipient_name = recipient_name
            setting.recipient_department = recipient_department

        await self.session.flush()
        result = await self.session.execute(
            select(RegistrationCertificateReminderSetting).where(
                RegistrationCertificateReminderSetting.id == setting.id
            )
        )
        return result.scalar_one()

    async def list_reminder_recipient_contacts(self) -> list[DepartmentContact]:
        return await list_department_contacts(self.session)

    async def get_contact_by_open_id(self, open_id: str) -> DepartmentContact | None:
        return await get_department_contact_by_open_id(self.session, open_id)

    async def reminder_notification_exists(
        self,
        entry_id: UUID,
        recipient_open_id: str,
        reminder_days: int,
    ) -> bool:
        result = await self.session.execute(
            select(
                exists().where(
                    RegistrationCertificateReminderNotification.is_deleted.is_(False),
                    RegistrationCertificateReminderNotification.entry_id == entry_id,
                    RegistrationCertificateReminderNotification.recipient_open_id
                    == recipient_open_id,
                    RegistrationCertificateReminderNotification.reminder_days
                    == reminder_days,
                )
            )
        )
        return bool(result.scalar())

    async def create_reminder_notifications(
        self,
        notifications: list[RegistrationCertificateReminderNotification],
    ) -> list[RegistrationCertificateReminderNotification]:
        if not notifications:
            return []
        self.session.add_all(notifications)
        await self.session.flush()
        return notifications

    async def update_entry(
        self,
        entry: RegistrationCertificateEntry,
        data: dict[str, object | None],
    ) -> RegistrationCertificateEntry:
        for key, value in data.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(RegistrationCertificateEntry).where(
                RegistrationCertificateEntry.id == entry.id
            )
        )
        return result.scalar_one()

    async def soft_delete(self, entry: RegistrationCertificateEntry) -> None:
        entry.is_deleted = True
        await self.session.flush()

    async def soft_delete_many(
        self,
        entries: list[RegistrationCertificateEntry],
    ) -> int:
        deleted_count = 0
        for entry in entries:
            if not entry.is_deleted:
                entry.is_deleted = True
                deleted_count += 1
        await self.session.flush()
        return deleted_count
