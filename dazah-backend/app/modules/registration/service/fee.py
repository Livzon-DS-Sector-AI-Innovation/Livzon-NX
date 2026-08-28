"""Registration fee service."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.registration.models.fee import InspectionContact, RegistrationFee
from app.modules.registration.repository.fee import RegistrationFeeRepository
from app.modules.registration.schemas.fee import (
    AgencySummary,
    FeeDashboardResponse,
    FeeEntryCreate,
    FeeEntryResponse,
    FeeEntryUpdate,
    FeeOverview,
    FeeTypeSummary,
    InspectionContactCreate,
    InspectionContactResponse,
    InspectionContactUpdate,
    PaymentStatusSummary,
    YearFeeTypeSummary,
    YearSummary,
)

logger = logging.getLogger(__name__)


class RegistrationFeeService:
    """注册费用台账业务服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RegistrationFeeRepository(session)

    async def get_overview(self, *, year_from: int | None = None) -> FeeOverview:
        entries = await self.repository.list_entries(year_from=year_from)
        fee_type_summaries = await self.repository.get_fee_type_summaries(
            year_from=year_from
        )
        payment_status_summaries = await self.repository.get_payment_status_summaries(
            year_from=year_from
        )
        year_summaries = await self.repository.get_year_summaries(year_from=year_from)

        return FeeOverview(
            total_records=len(entries),
            total_amount=await self.repository.get_total_amount(year_from=year_from),
            pending_amount=await self.repository.get_pending_amount(
                year_from=year_from
            ),
            paid_amount=await self.repository.get_paid_amount(year_from=year_from),
            fee_type_summaries=[
                FeeTypeSummary(
                    fee_type=item["fee_type"],
                    total_amount=item["total_amount"],
                    record_count=item["record_count"],
                )
                for item in fee_type_summaries
            ],
            payment_status_summaries=[
                PaymentStatusSummary(
                    payment_status=item["payment_status"],
                    total_amount=item["total_amount"],
                    record_count=item["record_count"],
                )
                for item in payment_status_summaries
            ],
            year_summaries=[
                YearSummary(
                    year=item["year"],
                    total_amount=item["total_amount"],
                    record_count=item["record_count"],
                )
                for item in year_summaries
            ],
        )

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
    ) -> list[FeeEntryResponse]:
        entries = await self.repository.list_entries(
            fee_type=fee_type,
            payment_status=payment_status,
            project_name=project_name,
            product_name=product_name,
            country=country,
            year=year,
            year_from=year_from,
            keyword=keyword,
        )
        return [_build_fee_response(entry) for entry in entries]

    async def get_entry(self, entry_id: UUID) -> FeeEntryResponse:
        entry = await self.repository.get_by_id(entry_id)
        if entry is None:
            raise NotFoundException("费用记录", str(entry_id))
        return _build_fee_response(entry)

    async def create_entry(self, data: FeeEntryCreate) -> FeeEntryResponse:
        entry = RegistrationFee(
            fee_type=data.fee_type,
            amount=data.amount,
            currency=data.currency,
            payment_status=data.payment_status,
            payment_date=data.payment_date,
            project_name=data.project_name,
            product_name=data.product_name,
            country=data.country,
            agency_name=data.agency_name,
            expense_content=data.expense_content,
            handler=data.handler,
            contract_received=data.contract_received,
            invoice_settled=data.invoice_settled,
            contact=data.contact,
            phone=data.phone,
            address=data.address,
            invoice_number=data.invoice_number,
            remarks=data.remarks,
        )
        created = await self.repository.create_entry(entry)
        await self.session.commit()
        return _build_fee_response(created)

    async def update_entry(
        self, entry_id: UUID, data: FeeEntryUpdate
    ) -> FeeEntryResponse:
        entry = await self.repository.get_by_id(entry_id)
        if entry is None:
            raise NotFoundException("费用记录", str(entry_id))

        payload = data.model_dump(exclude_unset=True)
        updated = await self.repository.update_entry(entry, payload)
        await self.session.commit()
        return _build_fee_response(updated)

    async def delete_entry(self, entry_id: UUID) -> None:
        entry = await self.repository.get_by_id(entry_id)
        if entry is None:
            raise NotFoundException("费用记录", str(entry_id))
        await self.repository.soft_delete(entry)
        await self.session.commit()

    async def get_dashboard(
        self, *, year_from: int | None = None
    ) -> FeeDashboardResponse:
        entries = await self.repository.list_entries(year_from=year_from)
        fee_type_summaries = await self.repository.get_fee_type_summaries(
            year_from=year_from
        )
        payment_status_summaries = await self.repository.get_payment_status_summaries(
            year_from=year_from
        )
        year_summaries = await self.repository.get_year_summaries(year_from=year_from)
        year_fee_type_summaries = await self.repository.get_year_fee_type_summaries(
            year_from=year_from
        )
        agency_summaries = await self.repository.get_agency_summaries(
            year_from=year_from
        )
        contact_count = await self.repository.count_inspection_contacts()

        return FeeDashboardResponse(
            total_records=len(entries),
            total_amount=await self.repository.get_total_amount(year_from=year_from),
            pending_amount=await self.repository.get_pending_amount(
                year_from=year_from
            ),
            paid_amount=await self.repository.get_paid_amount(year_from=year_from),
            fee_type_summaries=[
                FeeTypeSummary(
                    fee_type=item["fee_type"],
                    total_amount=item["total_amount"],
                    record_count=item["record_count"],
                )
                for item in fee_type_summaries
            ],
            payment_status_summaries=[
                PaymentStatusSummary(
                    payment_status=item["payment_status"],
                    total_amount=item["total_amount"],
                    record_count=item["record_count"],
                )
                for item in payment_status_summaries
            ],
            year_summaries=[
                YearSummary(
                    year=item["year"],
                    total_amount=item["total_amount"],
                    record_count=item["record_count"],
                )
                for item in year_summaries
            ],
            year_fee_type_summaries=[
                YearFeeTypeSummary(
                    year=item["year"],
                    fee_type=item["fee_type"],
                    total_amount=item["total_amount"],
                    record_count=item["record_count"],
                )
                for item in year_fee_type_summaries
            ],
            agency_summaries=[
                AgencySummary(
                    agency_name=item["agency_name"],
                    total_amount=item["total_amount"],
                    record_count=item["record_count"],
                )
                for item in agency_summaries
            ],
            inspection_contact_count=contact_count,
        )

    # ── Inspection contact operations ─────────────────────────────────

    async def list_inspection_contacts(
        self, *, keyword: str | None = None
    ) -> list[InspectionContactResponse]:
        contacts = await self.repository.list_inspection_contacts(keyword=keyword)
        return [_build_inspection_contact_response(c) for c in contacts]

    async def get_inspection_contact(
        self, contact_id: UUID
    ) -> InspectionContactResponse:
        contact = await self.repository.get_inspection_contact_by_id(contact_id)
        if contact is None:
            raise NotFoundException("外检联系记录", str(contact_id))
        return _build_inspection_contact_response(contact)

    async def create_inspection_contact(
        self, data: InspectionContactCreate
    ) -> InspectionContactResponse:
        contact = InspectionContact(
            test_item=data.test_item,
            agency_name=data.agency_name,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            contact_email=data.contact_email,
            address=data.address,
        )
        created = await self.repository.create_inspection_contact(contact)
        await self.session.commit()
        return _build_inspection_contact_response(created)

    async def update_inspection_contact(
        self, contact_id: UUID, data: InspectionContactUpdate
    ) -> InspectionContactResponse:
        contact = await self.repository.get_inspection_contact_by_id(contact_id)
        if contact is None:
            raise NotFoundException("外检联系记录", str(contact_id))
        payload = data.model_dump(exclude_unset=True)
        updated = await self.repository.update_inspection_contact(contact, payload)
        await self.session.commit()
        return _build_inspection_contact_response(updated)

    async def delete_inspection_contact(self, contact_id: UUID) -> None:
        contact = await self.repository.get_inspection_contact_by_id(contact_id)
        if contact is None:
            raise NotFoundException("外检联系记录", str(contact_id))
        await self.repository.soft_delete_inspection_contact(contact)
        await self.session.commit()


def _build_fee_response(entry: RegistrationFee) -> FeeEntryResponse:
    return FeeEntryResponse(
        id=entry.id,
        fee_type=entry.fee_type,
        amount=entry.amount,
        currency=entry.currency,
        payment_status=entry.payment_status,
        payment_date=entry.payment_date,
        project_name=entry.project_name,
        product_name=entry.product_name,
        country=entry.country,
        agency_name=entry.agency_name,
        expense_content=entry.expense_content,
        handler=entry.handler,
        contract_received=entry.contract_received,
        invoice_settled=entry.invoice_settled,
        contact=entry.contact,
        phone=entry.phone,
        address=entry.address,
        invoice_number=entry.invoice_number,
        remarks=entry.remarks,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _build_inspection_contact_response(
    contact: InspectionContact,
) -> InspectionContactResponse:
    return InspectionContactResponse(
        id=contact.id,
        test_item=contact.test_item,
        agency_name=contact.agency_name,
        contact_name=contact.contact_name,
        contact_phone=contact.contact_phone,
        contact_email=contact.contact_email,
        address=contact.address,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )
