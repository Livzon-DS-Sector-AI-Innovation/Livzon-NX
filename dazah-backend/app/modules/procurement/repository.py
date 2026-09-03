"""Procurement database queries live here."""

from datetime import date
from typing import Any
from typing import cast as typing_cast
from uuid import UUID

from sqlalchemy import String, Table, case, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.procurement.models import (
    ContractRecord,
    InvoiceRecognitionRecord,
    MaterialCatalogRecord,
    MaterialSourceConfig,
    PurchaseRequest,
    PurchaseRequestApproval,
    PurchaseRequestItem,
    Supplier,
)
from app.modules.procurement.page_access import (
    assert_request_scope,
    constrain_contract_category,
    constrain_request_category,
    request_department_names,
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

    async def invalidate_catalog(self, source_config_id: UUID) -> None:
        await self.session.execute(
            update(MaterialCatalogRecord)
            .where(
                MaterialCatalogRecord.source_config_id == source_config_id,
                MaterialCatalogRecord.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )


class MaterialCatalogRepository:
    """Persistence operations for the procurement material-code mirror."""

    # 单批写入条数：PostgreSQL 单语句参数数量上限以内，同时保持批次数可控
    WRITE_BATCH_SIZE = 1000

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_feishu_record_ids(self, source_config_id: UUID) -> set[str]:
        """只返回已有记录的飞书 record_id，用于计算本次同步的缺失集合。"""
        result = await self.session.execute(
            select(MaterialCatalogRecord.feishu_record_id).where(
                MaterialCatalogRecord.source_config_id == source_config_id,
            )
        )
        return set(result.scalars().all())

    async def bulk_upsert(self, records: list[dict[str, Any]]) -> int:
        """批量插入或更新物料目录记录（PostgreSQL ON CONFLICT upsert）。

        插入和更新合并为少量批量语句，替代逐条 INSERT/UPDATE；
        DO UPDATE 同时把 is_deleted 重置为 False，实现软删除记录的重新激活。
        asyncpg 对 ON CONFLICT DO UPDATE 不返回可靠 rowcount（通常为 -1），
        因此按批内行数返回，调用方用它累计已落库记录数。
        """
        if not records:
            return 0
        table = typing_cast(Table, MaterialCatalogRecord.__table__)
        statement = postgresql_insert(table)
        statement = statement.on_conflict_do_update(
            index_elements=[
                table.c.source_config_id,
                table.c.feishu_record_id,
            ],
            set_={
                "material_code": statement.excluded.material_code,
                "material_description": statement.excluded.material_description,
                "rule_model": statement.excluded.rule_model,
                "material_unit": statement.excluded.material_unit,
                "material_template": statement.excluded.material_template,
                "material_category": statement.excluded.material_category,
                "material_subcategory": statement.excluded.material_subcategory,
                "material_cost_category": (statement.excluded.material_cost_category),
                "feishu_created_time": statement.excluded.feishu_created_time,
                "feishu_last_modified_time": (
                    statement.excluded.feishu_last_modified_time
                ),
                "last_synced_at": statement.excluded.last_synced_at,
                "is_deleted": statement.excluded.is_deleted,
                "updated_by": statement.excluded.updated_by,
            },
        )
        for start in range(0, len(records), self.WRITE_BATCH_SIZE):
            batch = records[start : start + self.WRITE_BATCH_SIZE]
            await self.session.execute(statement, batch)
        return len(records)

    async def deactivate_missing(
        self,
        source_config_id: UUID,
        missing_record_ids: list[str],
    ) -> int:
        """把本次同步中飞书已不存在的记录标记为软删除。

        missing_record_ids 由调用方在内存中对比得出，通常接近为空，
        避免对全表执行 NOT IN（数万条）巨型更新。
        """
        if not missing_record_ids:
            return 0
        total = 0
        for start in range(0, len(missing_record_ids), self.WRITE_BATCH_SIZE):
            batch = missing_record_ids[start : start + self.WRITE_BATCH_SIZE]
            result = await self.session.execute(
                update(MaterialCatalogRecord)
                .where(
                    MaterialCatalogRecord.source_config_id == source_config_id,
                    MaterialCatalogRecord.feishu_record_id.in_(batch),
                    MaterialCatalogRecord.is_deleted.is_(False),
                )
                .values(is_deleted=True)
            )
            total += int(result.rowcount or 0)  # type: ignore[attr-defined]
        return total

    async def list_records(
        self,
        *,
        source_config_id: UUID,
        keyword: str | None = None,
        material_code: str | None = None,
        material_description: str | None = None,
        rule_model: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MaterialCatalogRecord], int]:
        filters = [
            MaterialCatalogRecord.source_config_id == source_config_id,
            MaterialCatalogRecord.is_deleted.is_(False),
        ]
        if material_code:
            filters.append(
                MaterialCatalogRecord.material_code.ilike(f"%{material_code}%")
            )
        if material_description:
            filters.append(
                MaterialCatalogRecord.material_description.ilike(
                    f"%{material_description}%"
                )
            )
        if rule_model:
            filters.append(MaterialCatalogRecord.rule_model.ilike(f"%{rule_model}%"))
        if keyword:
            keyword_filter = f"%{keyword}%"
            filters.append(
                or_(
                    MaterialCatalogRecord.material_code.ilike(keyword_filter),
                    MaterialCatalogRecord.material_description.ilike(keyword_filter),
                    MaterialCatalogRecord.rule_model.ilike(keyword_filter),
                )
            )

        count = await self.session.scalar(
            select(func.count(MaterialCatalogRecord.id)).where(*filters)
        )
        result = await self.session.execute(
            select(MaterialCatalogRecord)
            .where(*filters)
            .order_by(
                MaterialCatalogRecord.material_code.asc(),
                MaterialCatalogRecord.material_description.asc(),
                MaterialCatalogRecord.feishu_record_id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(count or 0)

    async def list_option_records(
        self,
        *,
        source_config_id: UUID,
        keyword: str,
        limit: int,
    ) -> list[MaterialCatalogRecord]:
        """List active local mirror rows for bounded material autocomplete."""
        contains_pattern = f"%{keyword}%"
        prefix_pattern = f"{keyword}%"
        match_rank = case(
            (MaterialCatalogRecord.material_code.ilike(keyword), 0),
            (MaterialCatalogRecord.material_code.ilike(prefix_pattern), 1),
            else_=2,
        )
        result = await self.session.execute(
            select(MaterialCatalogRecord)
            .where(
                MaterialCatalogRecord.source_config_id == source_config_id,
                MaterialCatalogRecord.is_deleted.is_(False),
                MaterialCatalogRecord.material_code.ilike(contains_pattern),
            )
            .order_by(
                match_rank,
                MaterialCatalogRecord.material_code.asc(),
                MaterialCatalogRecord.material_description.asc(),
                MaterialCatalogRecord.feishu_record_id.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())


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
        return int(getattr(result, "rowcount", 0) or 0) > 0

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
        return int(getattr(result, "rowcount", 0) or 0)


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
        constrain_contract_category(record.category)
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
        record = result.scalar_one_or_none()
        if record is not None:
            constrain_contract_category(record.category)
        return record

    async def list_records(
        self,
        *,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ContractRecord], int]:
        category = constrain_contract_category()
        base_query = select(ContractRecord).where(ContractRecord.is_deleted.is_(False))
        count_query = select(func.count(ContractRecord.id)).where(
            ContractRecord.is_deleted.is_(False)
        )
        if category is not None:
            base_query = base_query.where(ContractRecord.category == category)
            count_query = count_query.where(ContractRecord.category == category)

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
        await assert_request_scope(
            self.session,
            category=request.category,
            department=request.request_department,
        )
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
        request = result.scalar_one_or_none()
        if request is not None:
            await assert_request_scope(
                self.session,
                category=request.category,
                department=request.request_department,
            )
        return request

    async def find_by_import_duplicate_key(
        self,
        duplicate_key: str,
    ) -> PurchaseRequest | None:
        result = await self.session.execute(
            select(PurchaseRequest).where(
                PurchaseRequest.import_duplicate_key == duplicate_key,
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
        request = result.scalar_one_or_none()
        if request is not None:
            await assert_request_scope(
                self.session,
                category=request.category,
                department=request.request_department,
            )
        return request

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
        category = constrain_request_category(category)
        departments = await request_department_names(self.session)
        base_query = select(PurchaseRequest).where(
            PurchaseRequest.is_deleted.is_(False)
        )
        count_query = select(func.count(PurchaseRequest.id)).where(
            PurchaseRequest.is_deleted.is_(False)
        )

        if departments is not None:
            base_query = base_query.where(
                PurchaseRequest.request_department.in_(departments)
            )
            count_query = count_query.where(
                PurchaseRequest.request_department.in_(departments)
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
        category = constrain_request_category(category)
        departments = await request_department_names(self.session)
        request_item_match = PurchaseRequestItem.purchase_request_id == cast(
            PurchaseRequest.id, String
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
        if departments is not None:
            filters.append(PurchaseRequest.request_department.in_(departments))

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
        category = constrain_request_category(category)
        departments = await request_department_names(self.session)
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
        if departments is not None:
            base_query = base_query.where(
                PurchaseRequest.request_department.in_(departments)
            )
            count_query = count_query.where(
                PurchaseRequest.request_department.in_(departments)
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

    async def delete(self, request_id: UUID) -> bool:
        """软删除采购申请及其明细、审批记录。"""
        stmt = (
            update(PurchaseRequest)
            .where(
                PurchaseRequest.id == request_id,
                PurchaseRequest.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        result = await self.session.execute(stmt)
        if int(getattr(result, "rowcount", 0) or 0) == 0:
            return False
        request_id_str = str(request_id)
        await self.session.execute(
            update(PurchaseRequestItem)
            .where(PurchaseRequestItem.purchase_request_id == request_id_str)
            .values(is_deleted=True)
        )
        await self.session.execute(
            update(PurchaseRequestApproval)
            .where(PurchaseRequestApproval.purchase_request_id == request_id_str)
            .values(is_deleted=True)
        )
        return True
