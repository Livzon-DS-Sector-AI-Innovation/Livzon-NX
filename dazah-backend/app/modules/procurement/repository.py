"""Procurement database queries live here."""

from datetime import date
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.procurement.models import (
    ContractRecord,
    InvoiceRecognitionRecord,
    MaterialSourceConfig,
    PurchaseRequest,
    PurchaseRequestApproval,
    PurchaseRequestItem,
    Supplier,
)


class MaterialSourceConfigRepository:
    """Persistence operations for the single procurement material source."""

    CONFIG_KEY = "material-master"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self) -> MaterialSourceConfig | None:
        result = await self.session.execute(
            select(MaterialSourceConfig).where(
                MaterialSourceConfig.config_key == self.CONFIG_KEY,
                MaterialSourceConfig.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def save(
        self,
        config: MaterialSourceConfig,
    ) -> MaterialSourceConfig:
        existing = await self.get()
        if existing is None:
            self.session.add(config)
        else:
            existing.source_url = config.source_url
            existing.app_token = config.app_token
            existing.table_id = config.table_id
            existing.view_id = config.view_id
            existing.material_code_field = config.material_code_field
            existing.material_code_field_type = config.material_code_field_type
            existing.material_description_field = config.material_description_field
            existing.rule_model_field = config.rule_model_field
            existing.last_test_status = config.last_test_status
            existing.last_test_error = config.last_test_error
            existing.last_tested_at = config.last_tested_at
            existing.updated_by = config.updated_by
            config = existing
        await self.session.flush()
        return config


class InvoiceRecognitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        record: InvoiceRecognitionRecord,
    ) -> InvoiceRecognitionRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def find_duplicate(
        self,
        *,
        duplicate_key: str | None,
        source_file_sha256: str | None,
    ) -> InvoiceRecognitionRecord | None:
        filters = []
        if duplicate_key:
            filters.append(InvoiceRecognitionRecord.duplicate_key == duplicate_key)
        if source_file_sha256:
            filters.append(
                InvoiceRecognitionRecord.source_file_sha256 == source_file_sha256
            )
        if not filters:
            return None

        result = await self.session.execute(
            select(InvoiceRecognitionRecord)
            .where(
                InvoiceRecognitionRecord.is_deleted.is_(False),
                or_(*filters),
            )
            .order_by(InvoiceRecognitionRecord.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_records(
        self,
        *,
        keyword: str | None = None,
        seller_name: str | None = None,
        invoice_number: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[InvoiceRecognitionRecord], int]:
        base_query = select(InvoiceRecognitionRecord).where(
            InvoiceRecognitionRecord.is_deleted.is_(False)
        )
        count_query = select(func.count(InvoiceRecognitionRecord.id)).where(
            InvoiceRecognitionRecord.is_deleted.is_(False)
        )

        if seller_name:
            seller_filter = InvoiceRecognitionRecord.seller_name.ilike(
                f"%{seller_name}%"
            )
            base_query = base_query.where(seller_filter)
            count_query = count_query.where(seller_filter)
        if invoice_number:
            invoice_filter = InvoiceRecognitionRecord.invoice_number == invoice_number
            base_query = base_query.where(invoice_filter)
            count_query = count_query.where(invoice_filter)
        if keyword:
            like_pattern = f"%{keyword}%"
            keyword_filter = or_(
                InvoiceRecognitionRecord.file_name.ilike(like_pattern),
                InvoiceRecognitionRecord.invoice_number.ilike(like_pattern),
                InvoiceRecognitionRecord.seller_name.ilike(like_pattern),
            )
            base_query = base_query.where(keyword_filter)
            count_query = count_query.where(keyword_filter)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.session.execute(
            base_query.order_by(InvoiceRecognitionRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def delete_record(self, record_id: UUID) -> bool:
        stmt = (
            update(InvoiceRecognitionRecord)
            .where(
                InvoiceRecognitionRecord.id == record_id,
                InvoiceRecognitionRecord.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def batch_delete_records(self, record_ids: list[UUID]) -> int:
        if not record_ids:
            return 0

        stmt = (
            update(InvoiceRecognitionRecord)
            .where(
                InvoiceRecognitionRecord.id.in_(record_ids),
                InvoiceRecognitionRecord.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount


class SupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_all(self, suppliers: list[Supplier]) -> int:
        await self.session.execute(
            update(Supplier)
            .where(Supplier.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        if not suppliers:
            await self.session.flush()
            return 0

        self.session.add_all(suppliers)
        await self.session.flush()
        return len(suppliers)

    async def list_suppliers(
        self,
        *,
        keyword: str | None = None,
        supplier_name: str | None = None,
        material_name: str | None = None,
        purchase_category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Supplier], int, list[str]]:
        base_query = select(Supplier).where(Supplier.is_deleted.is_(False))
        count_query = select(func.count(Supplier.id)).where(
            Supplier.is_deleted.is_(False)
        )

        if supplier_name:
            supplier_filter = Supplier.supplier_name.ilike(f"%{supplier_name}%")
            base_query = base_query.where(supplier_filter)
            count_query = count_query.where(supplier_filter)
        if material_name:
            material_filter = Supplier.material_name.ilike(f"%{material_name}%")
            base_query = base_query.where(material_filter)
            count_query = count_query.where(material_filter)
        if purchase_category:
            category_filter = Supplier.purchase_category == purchase_category
            base_query = base_query.where(category_filter)
            count_query = count_query.where(category_filter)
        if keyword:
            like_pattern = f"%{keyword}%"
            keyword_filter = or_(
                Supplier.supplier_code.ilike(like_pattern),
                Supplier.supplier_name.ilike(like_pattern),
                Supplier.material_code.ilike(like_pattern),
                Supplier.material_name.ilike(like_pattern),
                Supplier.manufacturer_code.ilike(like_pattern),
                Supplier.manufacturer_name.ilike(like_pattern),
                Supplier.purchase_category.ilike(like_pattern),
                Supplier.last_updated_by.ilike(like_pattern),
                cast(Supplier.raw_data, String).ilike(like_pattern),
            )
            base_query = base_query.where(keyword_filter)
            count_query = count_query.where(keyword_filter)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.session.execute(
            base_query.order_by(
                Supplier.import_row_number.asc(),
                Supplier.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        suppliers = list(result.scalars().all())
        columns = await self.get_latest_columns()
        return suppliers, total, columns

    async def get_latest_columns(self) -> list[str]:
        result = await self.session.execute(
            select(Supplier.import_columns)
            .where(Supplier.is_deleted.is_(False))
            .order_by(Supplier.created_at.desc(), Supplier.import_row_number.asc())
            .limit(1)
        )
        columns = result.scalar_one_or_none()
        return list(columns or [])


class ContractRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: ContractRecord) -> ContractRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def get(self, record_id: UUID) -> ContractRecord | None:
        result = await self.session.execute(
            select(ContractRecord).where(
                ContractRecord.id == record_id,
                ContractRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_records(
        self,
        *,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ContractRecord], int]:
        base_query = select(ContractRecord).where(
            ContractRecord.is_deleted.is_(False)
        )
        count_query = select(func.count(ContractRecord.id)).where(
            ContractRecord.is_deleted.is_(False)
        )

        if keyword:
            like_pattern = f"%{keyword}%"
            keyword_filter = or_(
                ContractRecord.title.ilike(like_pattern),
                ContractRecord.contract_number.ilike(like_pattern),
                ContractRecord.seller_name.ilike(like_pattern),
            )
            base_query = base_query.where(keyword_filter)
            count_query = count_query.where(keyword_filter)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.session.execute(
            base_query.order_by(ContractRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total


class PurchaseRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        request: PurchaseRequest,
        items: list[PurchaseRequestItem],
    ) -> PurchaseRequest:
        self.session.add(request)
        await self.session.flush()
        request_id = str(request.id)
        for item in items:
            item.purchase_request_id = request_id
        self.session.add_all(items)
        await self.session.flush()
        return request

    async def get(self, request_id: UUID) -> PurchaseRequest | None:
        result = await self.session.execute(
            select(PurchaseRequest).where(
                PurchaseRequest.id == request_id,
                PurchaseRequest.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, request_id: UUID) -> PurchaseRequest | None:
        result = await self.session.execute(
            select(PurchaseRequest)
            .where(
                PurchaseRequest.id == request_id,
                PurchaseRequest.is_deleted.is_(False),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_items(self, request_id: UUID) -> list[PurchaseRequestItem]:
        result = await self.session.execute(
            select(PurchaseRequestItem)
            .where(
                PurchaseRequestItem.purchase_request_id == str(request_id),
                PurchaseRequestItem.is_deleted.is_(False),
            )
            .order_by(PurchaseRequestItem.sequence.asc())
        )
        return list(result.scalars().all())

    async def list_approvals(self, request_id: UUID) -> list[PurchaseRequestApproval]:
        result = await self.session.execute(
            select(PurchaseRequestApproval)
            .where(
                PurchaseRequestApproval.purchase_request_id == str(request_id),
                PurchaseRequestApproval.is_deleted.is_(False),
            )
            .order_by(PurchaseRequestApproval.approval_time.asc())
        )
        return list(result.scalars().all())

    async def list_requests(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PurchaseRequest], int]:
        base_query = select(PurchaseRequest).where(
            PurchaseRequest.is_deleted.is_(False)
        )
        count_query = select(func.count(PurchaseRequest.id)).where(
            PurchaseRequest.is_deleted.is_(False)
        )

        if category:
            base_query = base_query.where(PurchaseRequest.category == category)
            count_query = count_query.where(PurchaseRequest.category == category)
        if status:
            base_query = base_query.where(PurchaseRequest.status == status)
            count_query = count_query.where(PurchaseRequest.status == status)
        if keyword:
            like_pattern = f"%{keyword}%"
            keyword_filter = PurchaseRequest.request_department.ilike(like_pattern)
            base_query = base_query.where(keyword_filter)
            count_query = count_query.where(keyword_filter)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.session.execute(
            base_query.order_by(PurchaseRequest.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def list_purchase_order_lines(
        self,
        *,
        start_date: date,
        end_date: date,
        status: str,
        category: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> tuple[list[tuple[PurchaseRequest, PurchaseRequestItem]], int]:
        request_item_match = (
            PurchaseRequestItem.purchase_request_id == cast(PurchaseRequest.id, String)
        )
        filters = [
            PurchaseRequest.is_deleted.is_(False),
            PurchaseRequestItem.is_deleted.is_(False),
            PurchaseRequest.status == status,
            PurchaseRequest.request_date >= start_date,
            PurchaseRequest.request_date < end_date,
        ]
        if category:
            filters.append(PurchaseRequest.category == category)

        base_query = (
            select(PurchaseRequest, PurchaseRequestItem)
            .select_from(PurchaseRequest)
            .join(PurchaseRequestItem, request_item_match)
            .where(*filters)
        )
        count_query = (
            select(func.count(PurchaseRequestItem.id))
            .select_from(PurchaseRequest)
            .join(PurchaseRequestItem, request_item_match)
            .where(*filters)
        )

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        base_query = base_query.order_by(
            PurchaseRequest.request_date.asc(),
            PurchaseRequest.category.asc(),
            PurchaseRequest.request_department.asc(),
            PurchaseRequestItem.sequence.asc(),
        )
        if page is not None and page_size is not None:
            base_query = base_query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(base_query)
        return [(row[0], row[1]) for row in result.all()], total

    async def list_requests_by_approval(
        self,
        *,
        approval_role: str,
        result: str,
        category: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PurchaseRequest], int]:
        approval_subquery = (
            select(
                PurchaseRequestApproval.purchase_request_id,
                func.max(PurchaseRequestApproval.approval_time).label(
                    "latest_approval_time"
                ),
            )
            .where(
                PurchaseRequestApproval.is_deleted.is_(False),
                PurchaseRequestApproval.approval_role == approval_role,
                PurchaseRequestApproval.result == result,
            )
            .group_by(PurchaseRequestApproval.purchase_request_id)
            .subquery()
        )
        request_id_match = (
            cast(PurchaseRequest.id, String(36))
            == approval_subquery.c.purchase_request_id
        )
        base_query = (
            select(PurchaseRequest)
            .join(approval_subquery, request_id_match)
            .where(PurchaseRequest.is_deleted.is_(False))
        )
        count_query = (
            select(func.count(PurchaseRequest.id))
            .join(approval_subquery, request_id_match)
            .where(PurchaseRequest.is_deleted.is_(False))
        )

        if category:
            base_query = base_query.where(PurchaseRequest.category == category)
            count_query = count_query.where(PurchaseRequest.category == category)
        if keyword:
            like_pattern = f"%{keyword}%"
            keyword_filter = PurchaseRequest.request_department.ilike(like_pattern)
            base_query = base_query.where(keyword_filter)
            count_query = count_query.where(keyword_filter)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        result_set = await self.session.execute(
            base_query.order_by(approval_subquery.c.latest_approval_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result_set.scalars().all()), total

    async def replace_items(
        self,
        request_id: UUID,
        items: list[PurchaseRequestItem],
    ) -> None:
        await self.session.execute(
            update(PurchaseRequestItem)
            .where(
                PurchaseRequestItem.purchase_request_id == str(request_id),
                PurchaseRequestItem.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        for item in items:
            item.purchase_request_id = str(request_id)
        self.session.add_all(items)
        await self.session.flush()

    async def add_approval(
        self,
        approval: PurchaseRequestApproval,
    ) -> PurchaseRequestApproval:
        self.session.add(approval)
        await self.session.flush()
        return approval
