"""Warehouse database queries live here."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Float, asc, case, cast, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.models import (
    PackagingMaterialInventory,
    ProductInventory,
    RawMaterialInventory,
    WarehouseFeishuAnalysisProfile,
    WarehouseFeishuAnalysisResult,
    WarehouseFeishuAnalysisRun,
    WarehouseFeishuConfig,
    WarehouseFeishuField,
    WarehouseFeishuPageBinding,
    WarehouseFeishuPromptVersion,
    WarehouseFeishuRecord,
    WarehouseFeishuRecordSnapshot,
    WarehouseFeishuSourceRoot,
    WarehouseFeishuSyncRun,
    WarehouseFeishuTable,
)


class WarehouseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _json_scalar_text(json_value):
        json_type = func.jsonb_typeof(json_value)
        return case(
            (json_type.in_(("string", "number", "boolean")), json_value.astext),
            else_=None,
        )

    @classmethod
    def _feishu_field_display_text(cls, field: str):
        field_value = WarehouseFeishuRecord.fields[field]
        first_item = field_value[0]
        nested_value = field_value["value"]
        nested_value_first_item = nested_value[0]

        return func.coalesce(
            cls._json_scalar_text(field_value),
            field_value["text"].astext,
            field_value["name"].astext,
            field_value["title"].astext,
            field_value["display_name"].astext,
            field_value["number"].astext,
            field_value["amount"].astext,
            cls._json_scalar_text(nested_value),
            nested_value["text"].astext,
            nested_value["name"].astext,
            nested_value["number"].astext,
            nested_value["amount"].astext,
            cls._json_scalar_text(first_item),
            first_item["text"].astext,
            first_item["name"].astext,
            first_item["number"].astext,
            first_item["amount"].astext,
            cls._json_scalar_text(nested_value_first_item),
            nested_value_first_item["text"].astext,
            nested_value_first_item["name"].astext,
            nested_value_first_item["number"].astext,
            nested_value_first_item["amount"].astext,
            field_value.astext,
        )

    async def list_raw_materials(self) -> list[RawMaterialInventory]:
        result = await self.session.execute(
            select(RawMaterialInventory)
            .where(RawMaterialInventory.is_deleted.is_(False))
            .order_by(
                asc(RawMaterialInventory.product_line),
                asc(RawMaterialInventory.code),
                asc(RawMaterialInventory.name),
            )
        )
        return list(result.scalars().all())

    async def list_packaging_materials(self) -> list[PackagingMaterialInventory]:
        result = await self.session.execute(
            select(PackagingMaterialInventory)
            .where(PackagingMaterialInventory.is_deleted.is_(False))
            .order_by(
                asc(PackagingMaterialInventory.product_line),
                asc(PackagingMaterialInventory.code),
                asc(PackagingMaterialInventory.name),
            )
        )
        return list(result.scalars().all())

    async def list_products(self) -> list[ProductInventory]:
        result = await self.session.execute(
            select(ProductInventory)
            .where(ProductInventory.is_deleted.is_(False))
            .order_by(
                asc(ProductInventory.name),
                asc(ProductInventory.spec),
            )
        )
        return list(result.scalars().all())

    async def get_raw_material_by_import_key(
        self, import_key: str
    ) -> RawMaterialInventory | None:
        result = await self.session.execute(
            select(RawMaterialInventory).where(
                RawMaterialInventory.import_key == import_key
            )
        )
        return result.scalar_one_or_none()

    async def get_packaging_material_by_import_key(
        self, import_key: str
    ) -> PackagingMaterialInventory | None:
        result = await self.session.execute(
            select(PackagingMaterialInventory).where(
                PackagingMaterialInventory.import_key == import_key
            )
        )
        return result.scalar_one_or_none()

    async def get_product_by_import_key(
        self, import_key: str
    ) -> ProductInventory | None:
        result = await self.session.execute(
            select(ProductInventory).where(ProductInventory.import_key == import_key)
        )
        return result.scalar_one_or_none()

    async def create_raw_material(
        self, item: RawMaterialInventory
    ) -> RawMaterialInventory:
        self.session.add(item)
        await self.session.flush()
        return item

    async def create_packaging_material(
        self, item: PackagingMaterialInventory
    ) -> PackagingMaterialInventory:
        self.session.add(item)
        await self.session.flush()
        return item

    async def create_product(self, item: ProductInventory) -> ProductInventory:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_active_feishu_config(self) -> WarehouseFeishuConfig | None:
        result = await self.session.execute(
            select(WarehouseFeishuConfig)
            .where(
                WarehouseFeishuConfig.is_deleted.is_(False),
                WarehouseFeishuConfig.is_active.is_(True),
            )
            .order_by(WarehouseFeishuConfig.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_any_feishu_config(self) -> WarehouseFeishuConfig | None:
        result = await self.session.execute(
            select(WarehouseFeishuConfig)
            .where(WarehouseFeishuConfig.is_deleted.is_(False))
            .order_by(WarehouseFeishuConfig.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_feishu_config(
        self, config: WarehouseFeishuConfig
    ) -> WarehouseFeishuConfig:
        self.session.add(config)
        await self.session.flush()
        return config

    async def list_feishu_tables(
        self,
        *,
        config_id: UUID,
        keyword: str | None = None,
    ) -> list[WarehouseFeishuTable]:
        conditions = [
            WarehouseFeishuTable.is_deleted.is_(False),
            WarehouseFeishuSourceRoot.config_id == config_id,
            WarehouseFeishuSourceRoot.is_deleted.is_(False),
            WarehouseFeishuSourceRoot.is_active.is_(True),
        ]
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    WarehouseFeishuTable.name.ilike(pattern),
                    WarehouseFeishuTable.table_id.ilike(pattern),
                    WarehouseFeishuTable.app_token.ilike(pattern),
                )
            )
        result = await self.session.execute(
            select(WarehouseFeishuTable)
            .join(
                WarehouseFeishuSourceRoot,
                WarehouseFeishuSourceRoot.id == WarehouseFeishuTable.source_root_id,
            )
            .where(*conditions)
            .order_by(
                asc(WarehouseFeishuTable.name),
                asc(WarehouseFeishuTable.table_id),
            )
        )
        return list(result.scalars().all())

    async def get_feishu_table(
        self, source_root_id: UUID, app_token: str, table_id: str
    ) -> WarehouseFeishuTable | None:
        result = await self.session.execute(
            select(WarehouseFeishuTable).where(
                WarehouseFeishuTable.is_deleted.is_(False),
                WarehouseFeishuTable.source_root_id == source_root_id,
                WarehouseFeishuTable.app_token == app_token,
                WarehouseFeishuTable.table_id == table_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_feishu_table_by_id(
        self, table_pk: UUID, config_id: UUID
    ) -> WarehouseFeishuTable | None:
        result = await self.session.execute(
            select(WarehouseFeishuTable)
            .join(
                WarehouseFeishuSourceRoot,
                WarehouseFeishuSourceRoot.id == WarehouseFeishuTable.source_root_id,
            )
            .where(
                WarehouseFeishuTable.is_deleted.is_(False),
                WarehouseFeishuTable.id == table_pk,
                WarehouseFeishuSourceRoot.config_id == config_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_feishu_table_for_event(
        self, config_id: UUID, app_token: str, table_id: str
    ) -> WarehouseFeishuTable | None:
        result = await self.session.execute(
            select(WarehouseFeishuTable)
            .join(
                WarehouseFeishuSourceRoot,
                WarehouseFeishuSourceRoot.id == WarehouseFeishuTable.source_root_id,
            )
            .where(
                WarehouseFeishuTable.is_deleted.is_(False),
                WarehouseFeishuTable.app_token == app_token,
                WarehouseFeishuTable.table_id == table_id,
                WarehouseFeishuSourceRoot.config_id == config_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.is_active.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_feishu_app_tokens(self, config_id: UUID) -> list[str]:
        result = await self.session.execute(
            select(WarehouseFeishuTable.app_token)
            .join(
                WarehouseFeishuSourceRoot,
                WarehouseFeishuSourceRoot.id == WarehouseFeishuTable.source_root_id,
            )
            .where(
                WarehouseFeishuTable.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.config_id == config_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.is_active.is_(True),
            )
            .distinct()
            .order_by(WarehouseFeishuTable.app_token)
        )
        return list(result.scalars().all())

    async def save_feishu_table(
        self, table: WarehouseFeishuTable
    ) -> WarehouseFeishuTable:
        self.session.add(table)
        await self.session.flush()
        return table

    async def get_feishu_field(
        self, business_domain: str, app_token: str, table_id: str, field_id: str
    ) -> WarehouseFeishuField | None:
        result = await self.session.execute(
            select(WarehouseFeishuField).where(
                WarehouseFeishuField.is_deleted.is_(False),
                WarehouseFeishuField.business_domain == business_domain,
                WarehouseFeishuField.app_token == app_token,
                WarehouseFeishuField.table_id == table_id,
                WarehouseFeishuField.field_id == field_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_feishu_fields(
        self, business_domain: str, app_token: str, table_id: str
    ) -> list[WarehouseFeishuField]:
        result = await self.session.execute(
            select(WarehouseFeishuField)
            .where(
                WarehouseFeishuField.is_deleted.is_(False),
                WarehouseFeishuField.business_domain == business_domain,
                WarehouseFeishuField.app_token == app_token,
                WarehouseFeishuField.table_id == table_id,
            )
            .order_by(
                asc(WarehouseFeishuField.created_at),
                asc(WarehouseFeishuField.field_name),
            )
        )
        return list(result.scalars().all())

    async def save_feishu_field(
        self, field: WarehouseFeishuField
    ) -> WarehouseFeishuField:
        self.session.add(field)
        await self.session.flush()
        return field

    async def get_feishu_record(
        self, business_domain: str, app_token: str, table_id: str, record_id: str
    ) -> WarehouseFeishuRecord | None:
        result = await self.session.execute(
            select(WarehouseFeishuRecord).where(
                WarehouseFeishuRecord.business_domain == business_domain,
                WarehouseFeishuRecord.app_token == app_token,
                WarehouseFeishuRecord.table_id == table_id,
                WarehouseFeishuRecord.record_id == record_id,
            )
        )
        return result.scalar_one_or_none()

    async def save_feishu_record(
        self, record: WarehouseFeishuRecord
    ) -> WarehouseFeishuRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def mark_missing_feishu_records_deleted(
        self,
        *,
        business_domain: str,
        app_token: str,
        table_id: str,
        active_record_ids: set[str],
    ) -> None:
        stmt = (
            update(WarehouseFeishuRecord)
            .where(
                WarehouseFeishuRecord.business_domain == business_domain,
                WarehouseFeishuRecord.app_token == app_token,
                WarehouseFeishuRecord.table_id == table_id,
                WarehouseFeishuRecord.is_deleted.is_(False),
                WarehouseFeishuRecord.record_id.not_in(active_record_ids),
            )
            .values(is_deleted=True, is_source_deleted=True)
        )
        await self.session.execute(stmt)

    async def list_feishu_records(
        self,
        *,
        business_domain: str,
        app_token: str,
        table_id: str,
        keyword: str | None,
        field: str | None,
        field_operator: str | None,
        field_value: str | None,
        page: int,
        page_size: int,
        filters: list[tuple[str, str, str]] | None = None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
    ) -> tuple[list[WarehouseFeishuRecord], int]:
        conditions = [
            WarehouseFeishuRecord.is_deleted.is_(False),
            WarehouseFeishuRecord.business_domain == business_domain,
            WarehouseFeishuRecord.app_token == app_token,
            WarehouseFeishuRecord.table_id == table_id,
        ]
        if keyword:
            pattern = f"%{keyword.strip()}%"
            if field:
                conditions.append(self._feishu_field_display_text(field).ilike(pattern))
            else:
                conditions.append(WarehouseFeishuRecord.search_text.ilike(pattern))
        if field and field_operator and field_value is not None:
            field_text = self._feishu_field_display_text(field)
            normalized_value = field_value.strip()

            if field_operator == "contains":
                conditions.append(field_text.ilike(f"%{normalized_value}%"))
            elif field_operator == "eq":
                conditions.append(field_text == normalized_value)
            elif field_operator == "ne":
                conditions.append(field_text != normalized_value)
            elif field_operator in {"gt", "gte", "lt", "lte"}:
                numeric_pattern = r"^\s*-?\d+(\.\d+)?\s*$"
                field_number = case(
                    (field_text.op("~")(numeric_pattern), cast(field_text, Float)),
                    else_=None,
                )
                compare_value = float(normalized_value)
                if field_operator == "gt":
                    conditions.append(field_number > compare_value)
                elif field_operator == "gte":
                    conditions.append(field_number >= compare_value)
                elif field_operator == "lt":
                    conditions.append(field_number < compare_value)
                else:
                    conditions.append(field_number <= compare_value)

        for filter_field, operator, value in filters or []:
            field_text = self._feishu_field_display_text(filter_field)
            normalized_value = value.strip()
            if operator == "contains":
                conditions.append(field_text.ilike(f"%{normalized_value}%"))
            elif operator == "eq":
                conditions.append(field_text == normalized_value)
            elif operator == "ne":
                conditions.append(field_text != normalized_value)
            elif operator in {"gt", "gte", "lt", "lte"}:
                numeric = case(
                    (
                        field_text.op("~")(r"^\s*-?\d+(\.\d+)?\s*$"),
                        cast(field_text, Float),
                    ),
                    else_=None,
                )
                number = float(normalized_value)
                conditions.append(
                    {
                        "gt": numeric > number,
                        "gte": numeric >= number,
                        "lt": numeric < number,
                        "lte": numeric <= number,
                    }[operator]
                )

        total_result = await self.session.execute(
            select(func.count()).select_from(WarehouseFeishuRecord).where(*conditions)
        )
        total = int(total_result.scalar_one() or 0)

        ordering = (
            self._feishu_field_display_text(sort_field)
            if sort_field
            else WarehouseFeishuRecord.feishu_last_modified_time
        )
        order_clause = ordering.asc().nullslast() if sort_direction == "asc" else ordering.desc().nullslast()
        result = await self.session.execute(
            select(WarehouseFeishuRecord)
            .where(*conditions)
            .order_by(
                order_clause,
                WarehouseFeishuRecord.updated_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def list_feishu_field_values(
        self,
        *,
        table: WarehouseFeishuTable,
        field_name: str,
        keyword: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        value = self._feishu_field_display_text(field_name).label("value")
        conditions = [
            WarehouseFeishuRecord.is_deleted.is_(False),
            WarehouseFeishuRecord.business_domain == table.business_domain,
            WarehouseFeishuRecord.app_token == table.app_token,
            WarehouseFeishuRecord.table_id == table.table_id,
            value.is_not(None),
        ]
        if keyword:
            conditions.append(value.ilike(f"%{keyword.strip()}%"))
        count = func.count(WarehouseFeishuRecord.id).label("count")
        result = await self.session.execute(
            select(value, count)
            .where(*conditions)
            .group_by(value)
            .order_by(count.desc(), value.asc())
            .limit(limit)
        )
        return [dict(row._mapping) for row in result.all()]

    async def list_feishu_source_roots(
        self, config_id: UUID
    ) -> list[WarehouseFeishuSourceRoot]:
        result = await self.session.execute(
            select(WarehouseFeishuSourceRoot)
            .where(
                WarehouseFeishuSourceRoot.config_id == config_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
            )
            .order_by(asc(WarehouseFeishuSourceRoot.created_at))
        )
        return list(result.scalars().all())

    async def get_feishu_source_root(
        self, root_id: UUID
    ) -> WarehouseFeishuSourceRoot | None:
        result = await self.session.execute(
            select(WarehouseFeishuSourceRoot).where(
                WarehouseFeishuSourceRoot.id == root_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def save_feishu_source_root(
        self, root: WarehouseFeishuSourceRoot
    ) -> WarehouseFeishuSourceRoot:
        self.session.add(root)
        await self.session.flush()
        return root

    async def list_page_bindings(
        self, config_id: UUID, page_key: str
    ) -> list[WarehouseFeishuPageBinding]:
        result = await self.session.execute(
            select(WarehouseFeishuPageBinding)
            .join(
                WarehouseFeishuTable,
                WarehouseFeishuTable.id == WarehouseFeishuPageBinding.table_pk,
            )
            .join(
                WarehouseFeishuSourceRoot,
                WarehouseFeishuSourceRoot.id == WarehouseFeishuTable.source_root_id,
            )
            .where(
                WarehouseFeishuPageBinding.page_key == page_key,
                WarehouseFeishuPageBinding.is_deleted.is_(False),
                WarehouseFeishuPageBinding.is_enabled.is_(True),
                WarehouseFeishuPageBinding.status == "published",
                WarehouseFeishuTable.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.config_id == config_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.is_active.is_(True),
            )
            .order_by(
                WarehouseFeishuPageBinding.is_default.desc(),
                asc(WarehouseFeishuPageBinding.display_order),
                asc(WarehouseFeishuPageBinding.created_at),
            )
        )
        return list(result.scalars().all())

    async def get_page_binding(
        self, config_id: UUID, page_key: str, binding_id: UUID
    ) -> WarehouseFeishuPageBinding | None:
        result = await self.session.execute(
            select(WarehouseFeishuPageBinding)
            .join(
                WarehouseFeishuTable,
                WarehouseFeishuTable.id == WarehouseFeishuPageBinding.table_pk,
            )
            .join(
                WarehouseFeishuSourceRoot,
                WarehouseFeishuSourceRoot.id == WarehouseFeishuTable.source_root_id,
            )
            .where(
                WarehouseFeishuPageBinding.id == binding_id,
                WarehouseFeishuPageBinding.page_key == page_key,
                WarehouseFeishuPageBinding.is_deleted.is_(False),
                WarehouseFeishuPageBinding.is_enabled.is_(True),
                WarehouseFeishuPageBinding.status == "published",
                WarehouseFeishuTable.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.config_id == config_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_page_binding_by_id(
        self, config_id: UUID, binding_id: UUID
    ) -> WarehouseFeishuPageBinding | None:
        result = await self.session.execute(
            select(WarehouseFeishuPageBinding)
            .join(
                WarehouseFeishuTable,
                WarehouseFeishuTable.id == WarehouseFeishuPageBinding.table_pk,
            )
            .join(
                WarehouseFeishuSourceRoot,
                WarehouseFeishuSourceRoot.id == WarehouseFeishuTable.source_root_id,
            )
            .where(
                WarehouseFeishuPageBinding.id == binding_id,
                WarehouseFeishuPageBinding.is_deleted.is_(False),
                WarehouseFeishuPageBinding.is_enabled.is_(True),
                WarehouseFeishuPageBinding.status == "published",
                WarehouseFeishuTable.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.config_id == config_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
                WarehouseFeishuSourceRoot.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def replace_page_bindings(
        self, page_key: str, bindings: list[WarehouseFeishuPageBinding]
    ) -> list[WarehouseFeishuPageBinding]:
        await self.session.execute(
            update(WarehouseFeishuPageBinding)
            .where(
                WarehouseFeishuPageBinding.page_key == page_key,
                WarehouseFeishuPageBinding.is_deleted.is_(False),
            )
            .values(is_deleted=True, is_enabled=False)
        )
        for binding in bindings:
            self.session.add(binding)
        await self.session.flush()
        return bindings

    async def save_sync_run(self, run: WarehouseFeishuSyncRun) -> WarehouseFeishuSyncRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def fail_running_sync_runs(
        self,
        table_pk: UUID,
        *,
        error_message: str,
        completed_at: datetime,
    ) -> None:
        await self.session.execute(
            update(WarehouseFeishuSyncRun)
            .where(
                WarehouseFeishuSyncRun.table_pk == table_pk,
                WarehouseFeishuSyncRun.status == "running",
                WarehouseFeishuSyncRun.is_deleted.is_(False),
            )
            .values(
                status="failed",
                error_message=error_message,
                completed_at=completed_at,
            )
        )

    async def table_requires_history(self, table_pk: UUID) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(WarehouseFeishuPageBinding)
            .where(
                WarehouseFeishuPageBinding.table_pk == table_pk,
                WarehouseFeishuPageBinding.is_deleted.is_(False),
                WarehouseFeishuPageBinding.is_enabled.is_(True),
                WarehouseFeishuPageBinding.history_mode == "daily_snapshot",
            )
        )
        return bool(result.scalar_one() or 0)

    async def save_record_snapshots(
        self, snapshots: list[WarehouseFeishuRecordSnapshot]
    ) -> None:
        self.session.add_all(snapshots)
        await self.session.flush()

    async def aggregate_feishu_records(
        self,
        *,
        table: WarehouseFeishuTable,
        metric: str,
        metric_field: str | None,
        group_field: str | None,
        time_field: str | None,
        period: str,
        limit: int,
    ) -> list[dict[str, object]]:
        conditions = [
            WarehouseFeishuRecord.is_deleted.is_(False),
            WarehouseFeishuRecord.business_domain == table.business_domain,
            WarehouseFeishuRecord.app_token == table.app_token,
            WarehouseFeishuRecord.table_id == table.table_id,
        ]
        select_items: list[object] = []
        group_items: list[object] = []
        if time_field and period != "none":
            time_text = self._feishu_field_display_text(time_field)
            epoch = case(
                (time_text.op("~")(r"^\d{10,13}$"), cast(time_text, Float)),
                else_=None,
            )
            seconds = case((epoch > 100000000000, epoch / 1000), else_=epoch)
            bucket = func.date_trunc(period, func.to_timestamp(seconds)).label("period")
            select_items.append(bucket)
            group_items.append(bucket)
        if group_field:
            group_value = self._feishu_field_display_text(group_field).label("group")
            select_items.append(group_value)
            group_items.append(group_value)

        metric_text = (
            self._feishu_field_display_text(metric_field) if metric_field else None
        )
        if metric == "count":
            metric_expr = func.count(WarehouseFeishuRecord.id)
        elif metric == "count_distinct" and metric_text is not None:
            metric_expr = func.count(func.distinct(metric_text))
        elif metric_text is not None:
            numeric = case(
                (metric_text.op("~")(r"^\s*-?\d+(\.\d+)?\s*$"), cast(metric_text, Float)),
                else_=None,
            )
            metric_expr = getattr(func, metric)(numeric)
        else:
            metric_expr = func.count(WarehouseFeishuRecord.id)
        select_items.append(metric_expr.label("value"))
        query = select(*select_items).where(*conditions)
        if group_items:
            query = query.group_by(*group_items)
        query = query.order_by(desc("value")).limit(limit)
        result = await self.session.execute(query)
        return [dict(row._mapping) for row in result.all()]

    async def save_analysis_profile(
        self, profile: WarehouseFeishuAnalysisProfile
    ) -> WarehouseFeishuAnalysisProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_analysis_profile(
        self, profile_id: UUID
    ) -> WarehouseFeishuAnalysisProfile | None:
        result = await self.session.execute(
            select(WarehouseFeishuAnalysisProfile).where(
                WarehouseFeishuAnalysisProfile.id == profile_id,
                WarehouseFeishuAnalysisProfile.is_deleted.is_(False),
                WarehouseFeishuAnalysisProfile.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_auto_analysis_profiles(
        self, resource_id: UUID
    ) -> list[WarehouseFeishuAnalysisProfile]:
        result = await self.session.execute(
            select(WarehouseFeishuAnalysisProfile).where(
                WarehouseFeishuAnalysisProfile.is_deleted.is_(False),
                WarehouseFeishuAnalysisProfile.is_active.is_(True),
                WarehouseFeishuAnalysisProfile.auto_run.is_(True),
                WarehouseFeishuAnalysisProfile.resource_ids.contains([str(resource_id)]),
            )
        )
        return list(result.scalars().all())

    async def save_prompt_version(
        self, prompt: WarehouseFeishuPromptVersion
    ) -> WarehouseFeishuPromptVersion:
        self.session.add(prompt)
        await self.session.flush()
        return prompt

    async def get_prompt_version(
        self, prompt_id: UUID
    ) -> WarehouseFeishuPromptVersion | None:
        result = await self.session.execute(
            select(WarehouseFeishuPromptVersion).where(
                WarehouseFeishuPromptVersion.id == prompt_id,
                WarehouseFeishuPromptVersion.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_prompt_versions(
        self, profile_id: UUID
    ) -> list[WarehouseFeishuPromptVersion]:
        result = await self.session.execute(
            select(WarehouseFeishuPromptVersion)
            .where(
                WarehouseFeishuPromptVersion.profile_id == profile_id,
                WarehouseFeishuPromptVersion.is_deleted.is_(False),
            )
            .order_by(desc(WarehouseFeishuPromptVersion.version))
        )
        return list(result.scalars().all())

    async def next_prompt_version(self, profile_id: UUID) -> int:
        result = await self.session.execute(
            select(func.max(WarehouseFeishuPromptVersion.version)).where(
                WarehouseFeishuPromptVersion.profile_id == profile_id,
                WarehouseFeishuPromptVersion.is_deleted.is_(False),
            )
        )
        return int(result.scalar_one_or_none() or 0) + 1

    async def save_analysis_run(
        self, run: WarehouseFeishuAnalysisRun
    ) -> WarehouseFeishuAnalysisRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_analysis_run(
        self, run_id: UUID
    ) -> WarehouseFeishuAnalysisRun | None:
        result = await self.session.execute(
            select(WarehouseFeishuAnalysisRun).where(
                WarehouseFeishuAnalysisRun.id == run_id,
                WarehouseFeishuAnalysisRun.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def claim_queued_analysis_runs(
        self, limit: int = 10
    ) -> list[WarehouseFeishuAnalysisRun]:
        result = await self.session.execute(
            select(WarehouseFeishuAnalysisRun)
            .where(
                WarehouseFeishuAnalysisRun.status == "queued",
                WarehouseFeishuAnalysisRun.is_deleted.is_(False),
            )
            .order_by(WarehouseFeishuAnalysisRun.started_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        runs = list(result.scalars().all())
        for run in runs:
            run.status = "running"
        await self.session.flush()
        return runs

    async def save_analysis_result(
        self, result: WarehouseFeishuAnalysisResult
    ) -> WarehouseFeishuAnalysisResult:
        self.session.add(result)
        await self.session.flush()
        return result

    async def get_analysis_result(
        self, run_id: UUID
    ) -> WarehouseFeishuAnalysisResult | None:
        result = await self.session.execute(
            select(WarehouseFeishuAnalysisResult).where(
                WarehouseFeishuAnalysisResult.run_id == run_id,
                WarehouseFeishuAnalysisResult.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_analysis_records(
        self, table: WarehouseFeishuTable, limit: int
    ) -> list[WarehouseFeishuRecord]:
        result = await self.session.execute(
            select(WarehouseFeishuRecord)
            .where(
                WarehouseFeishuRecord.is_deleted.is_(False),
                WarehouseFeishuRecord.business_domain == table.business_domain,
                WarehouseFeishuRecord.app_token == table.app_token,
                WarehouseFeishuRecord.table_id == table.table_id,
            )
            .order_by(
                WarehouseFeishuRecord.feishu_last_modified_time.desc().nullslast(),
                WarehouseFeishuRecord.updated_at.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())
