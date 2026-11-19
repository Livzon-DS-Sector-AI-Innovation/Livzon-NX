"""Warehouse database queries live here."""

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Double,
    Integer,
    Numeric,
    String,
    all_,
    asc,
    bindparam,
    case,
    cast,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.inspection_progress import (
    build_change_transition,
    build_initial_transition,
    inspection_watched_field,
)
from app.modules.warehouse.legacy_models import (
    WarehouseFeishuAnalysisProfile,
    WarehouseFeishuAnalysisResult,
    WarehouseFeishuAnalysisRun,
    WarehouseFeishuConfig,
    WarehouseFeishuField,
    WarehouseFeishuPageBinding,
    WarehouseFeishuPromptVersion,
    WarehouseFeishuRecord,
    WarehouseFeishuSourceRoot,
    WarehouseFeishuSyncRun,
    WarehouseFeishuTable,
)
from app.modules.warehouse.models import (
    MaterialPageRow,
    MaterialPageSnapshot,
    PackagingMaterialInventory,
    ProductInventory,
    RawMaterialInventory,
)

_SYNC_BATCH_SIZE = 500
InventorySnapshotModel = (
    RawMaterialInventory | PackagingMaterialInventory | ProductInventory
)


class WarehouseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def fail_running_sync_runs(
        self,
        table_pk: UUID,
        *,
        error_message: str,
        completed_at: datetime,
    ) -> None:
        """Close legacy sync-run rows when a compatibility sync times out."""

        await self.session.execute(
            update(WarehouseFeishuSyncRun)
            .where(
                WarehouseFeishuSyncRun.table_pk == table_pk,
                WarehouseFeishuSyncRun.status == "running",
            )
            .values(
                status="failed",
                error_message=error_message,
                completed_at=completed_at,
            )
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

    async def upsert_inventory_snapshots(
        self,
        model: type[InventorySnapshotModel],
        rows: dict[str, dict[str, object]],
        *,
        synced_at: datetime,
    ) -> None:
        """按导入键批量查差异，跳过无变化行；冲突时只写真实变更。"""
        keys = list(rows)
        for offset in range(0, len(keys), _SYNC_BATCH_SIZE):
            batch_keys = keys[offset : offset + _SYNC_BATCH_SIZE]
            business_fields = tuple(rows[batch_keys[0]])
            existing = await self.session.execute(
                select(
                    model.import_key,
                    model.is_deleted,
                    *(getattr(model, field) for field in business_fields),
                ).where(model.import_key.in_(batch_keys))
            )
            by_key = {row["import_key"]: row for row in existing.mappings()}
            changed = []
            for key in batch_keys:
                payload = rows[key]
                current = by_key.get(key)
                if (
                    current is not None
                    and not current["is_deleted"]
                    and all(current[field] == value for field, value in payload.items())
                ):
                    continue
                changed.append(
                    {
                        **payload,
                        "import_key": key,
                        "is_deleted": False,
                        "last_synced_at": synced_at,
                    }
                )
            if not changed:
                continue
            statement = insert(model).values(changed)
            columns = statement.table.c
            updates = {
                field: statement.excluded[field]
                for field in (*business_fields, "is_deleted", "last_synced_at")
            }
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[model.import_key],
                    set_={**updates, "updated_at": func.now()},
                    where=or_(
                        model.is_deleted.is_(True),
                        *(
                            columns[field].is_distinct_from(statement.excluded[field])
                            for field in business_fields
                        ),
                    ),
                )
            )

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
        self, source_root_id: Any, app_token: str, table_id: str
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
        self, table_pk: Any, config_id: Any
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

    async def get_feishu_source_root(
        self, root_id: Any
    ) -> WarehouseFeishuSourceRoot | None:
        result = await self.session.execute(
            select(WarehouseFeishuSourceRoot).where(
                WarehouseFeishuSourceRoot.id == root_id,
                WarehouseFeishuSourceRoot.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

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

    async def save_feishu_source_root(
        self, root: WarehouseFeishuSourceRoot
    ) -> WarehouseFeishuSourceRoot:
        self.session.add(root)
        await self.session.flush()
        return root

    async def upsert_feishu_table(
        self,
        *,
        source_root_id: UUID,
        business_domain: str,
        app_token: str,
        table_id: str,
        name: str,
        revision: int | None = None,
        source_path: list[dict[str, str]] | None = None,
    ) -> WarehouseFeishuTable:
        """Persist one discovered legacy table without cloning business data.

        The migrated warehouse pages remain the authoritative local mirror.  This
        directory row only keeps the former root-discovery/Agent contract alive;
        it is deliberately upserted by the stable ``source_root + app + table``
        key and never duplicates material-page rows.
        """
        table = await self.get_feishu_table(source_root_id, app_token, table_id)
        if table is None:
            table = WarehouseFeishuTable(
                source_root_id=source_root_id,
                business_domain=business_domain,
                app_token=app_token,
                table_id=table_id,
                name=name,
                revision=revision,
                source_path=source_path or [],
                sync_status="discovered",
            )
            self.session.add(table)
        else:
            table.business_domain = business_domain
            table.name = name
            table.revision = revision
            table.source_path = source_path or []
            table.sync_status = table.sync_status or "discovered"
            table.is_deleted = False
        await self.session.flush()
        return table

    async def get_analysis_run(self, run_id: Any) -> WarehouseFeishuAnalysisRun | None:
        result = await self.session.execute(
            select(WarehouseFeishuAnalysisRun).where(
                WarehouseFeishuAnalysisRun.id == run_id,
                WarehouseFeishuAnalysisRun.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_page_bindings(
        self, config_id: UUID, page_key: str
    ) -> list[WarehouseFeishuPageBinding]:
        # ``table_pk`` is intentionally not joined here.  The migrated page
        # mirror uses stable UUIDs derived from its table IDs, while the legacy
        # table directory may be empty after migration.
        result = await self.session.execute(
            select(WarehouseFeishuPageBinding)
            .where(
                WarehouseFeishuPageBinding.page_key == page_key,
                WarehouseFeishuPageBinding.is_deleted.is_(False),
                WarehouseFeishuPageBinding.is_enabled.is_(True),
                WarehouseFeishuPageBinding.status == "published",
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
            select(WarehouseFeishuPageBinding).where(
                WarehouseFeishuPageBinding.id == binding_id,
                WarehouseFeishuPageBinding.page_key == page_key,
                WarehouseFeishuPageBinding.is_deleted.is_(False),
                WarehouseFeishuPageBinding.is_enabled.is_(True),
                WarehouseFeishuPageBinding.status == "published",
            )
        )
        return result.scalar_one_or_none()

    async def get_page_binding_by_id(
        self, config_id: UUID, binding_id: UUID
    ) -> WarehouseFeishuPageBinding | None:
        result = await self.session.execute(
            select(WarehouseFeishuPageBinding).where(
                WarehouseFeishuPageBinding.id == binding_id,
                WarehouseFeishuPageBinding.is_deleted.is_(False),
                WarehouseFeishuPageBinding.is_enabled.is_(True),
                WarehouseFeishuPageBinding.status == "published",
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
            .order_by(WarehouseFeishuPromptVersion.version.desc())
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

    async def create_raw_material(
        self, item: RawMaterialInventory
    ) -> RawMaterialInventory:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def create_packaging_material(
        self, item: PackagingMaterialInventory
    ) -> PackagingMaterialInventory:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def create_product(self, item: ProductInventory) -> ProductInventory:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def get_material_page_snapshot(
        self, page_key: str
    ) -> MaterialPageSnapshot | None:
        result = await self.session.execute(
            select(MaterialPageSnapshot).where(
                MaterialPageSnapshot.page_key == page_key,
                MaterialPageSnapshot.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def sum_finished_inbound_kg(
        self,
        snapshot: MaterialPageSnapshot,
        *,
        product_field: str,
        product_name: str,
        date_field: str,
        kg_field: str,
        start_ms: int,
        end_ms: int,
    ) -> float:
        """按产品名与日期区间（飞书毫秒时间戳，闭区间）聚合行内 KG 数值。

        KG 列以文本兜底解析（空值/非数值按 0 计），避免脏行导致整表聚合失败。
        """
        date_ms = cast(MaterialPageRow.cells[date_field].as_string(), BigInteger)
        kg_text = MaterialPageRow.cells[kg_field].as_string()
        kg_value = cast(
            case(
                (kg_text.regexp_match(r"^-?\d+(\.\d+)?$"), kg_text),
                else_="0",
            ),
            Numeric,
        )
        result = await self.session.execute(
            select(func.coalesce(func.sum(kg_value), 0.0)).where(
                MaterialPageRow.page_snapshot_id == snapshot.id,
                MaterialPageRow.is_deleted.is_(False),
                func.btrim(MaterialPageRow.cells[product_field].as_string())
                == product_name,
                date_ms.between(start_ms, end_ms),
            )
        )
        return float(result.scalar_one())

    async def aggregate_finished_inbound(
        self,
        snapshot: MaterialPageSnapshot,
        *,
        product_field: str,
        product_name: str,
        date_field: str,
        kg_field: str,
        start_ms: int,
        end_ms: int,
    ) -> tuple[int, float]:
        """按产品名与日期区间（飞书毫秒时间戳，闭区间）统计入库行数与 KG 合计。

        成品入库总账一行即一次入库（预混剂等一批一行），行数即入库批次；
        KG 列以文本兜底解析（空值/非数值按 0 计），与 sum_finished_inbound_kg 同口径。
        """
        date_ms = cast(MaterialPageRow.cells[date_field].as_string(), BigInteger)
        kg_text = MaterialPageRow.cells[kg_field].as_string()
        kg_value = cast(
            case(
                (kg_text.regexp_match(r"^-?\d+(\.\d+)?$"), kg_text),
                else_="0",
            ),
            Numeric,
        )
        result = await self.session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(kg_value), 0.0),
            ).where(
                MaterialPageRow.page_snapshot_id == snapshot.id,
                MaterialPageRow.is_deleted.is_(False),
                func.btrim(MaterialPageRow.cells[product_field].as_string())
                == product_name,
                date_ms.between(start_ms, end_ms),
            )
        )
        row = result.one()
        return int(row[0]), float(row[1])

    async def list_finished_inbound_cells(
        self,
        snapshot: MaterialPageSnapshot,
        *,
        product_field: str,
        product_name: str,
    ) -> list[dict[str, Any]]:
        """成品入库明细中指定产品的全部行 cells（批次级实际入库源数据）。

        行量级为数百，取回 cells 后由调用方解析批号/日期/数量/确认位；
        不在 SQL 内做日期过滤（调用方需要全量批次做状态判定）。
        """
        result = await self.session.execute(
            select(MaterialPageRow.cells).where(
                MaterialPageRow.page_snapshot_id == snapshot.id,
                MaterialPageRow.is_deleted.is_(False),
                func.btrim(MaterialPageRow.cells[product_field].as_string())
                == product_name,
            )
        )
        return [row[0] for row in result.all()]

    async def upsert_material_page_snapshot(
        self,
        *,
        page_key: str,
        page_title: str,
        table_name: str,
        table_id: str,
        columns: list[dict[str, str]],
        total_rows: int,
        source: str,
        last_synced_at: Any,
        last_error: str | None = None,
    ) -> MaterialPageSnapshot:
        snapshot = await self.get_material_page_snapshot(page_key)
        payload = {
            "page_key": page_key,
            "page_title": page_title,
            "table_name": table_name,
            "table_id": table_id,
            "columns": columns,
            "total_rows": total_rows,
            "source": source,
            "last_synced_at": last_synced_at,
            "last_error": last_error,
        }
        if snapshot:
            for field, value in payload.items():
                setattr(snapshot, field, value)
            snapshot.is_deleted = False
            await self.session.flush()
            await self.session.refresh(snapshot)
            return snapshot

        snapshot = MaterialPageSnapshot(**payload)
        self.session.add(snapshot)
        await self.session.flush()
        await self.session.refresh(snapshot)
        return snapshot

    async def replace_material_page_rows(
        self,
        snapshot_id: Any,
        rows: Sequence[MaterialPageRow],
    ) -> None:
        await self.session.execute(
            delete(MaterialPageRow).where(
                MaterialPageRow.page_snapshot_id == snapshot_id
            )
        )
        if rows:
            self.session.add_all(list(rows))
        await self.session.flush()

    async def upsert_material_page_rows(
        self,
        snapshot_id: UUID,
        rows: Sequence[MaterialPageRow],
        *,
        page_key: str | None = None,
        record_meta: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """全量对账只回读本轮记录，未匹配的有效历史行一次软删。"""
        await self._upsert_material_page_batches(
            snapshot_id,
            rows,
            full=True,
            page_key=page_key,
            record_meta=record_meta,
        )
        incoming_ids = list({row.source_record_id for row in rows})
        await self.session.execute(
            update(MaterialPageRow)
            .where(
                MaterialPageRow.page_snapshot_id == snapshot_id,
                MaterialPageRow.is_deleted.is_(False),
                MaterialPageRow.source_record_id
                != all_(
                    bindparam("incoming_ids", incoming_ids, type_=ARRAY(String)),
                ),
            )
            .values(is_deleted=True)
        )

    async def upsert_material_page_rows_incremental(
        self,
        snapshot_id: UUID,
        rows: Sequence[MaterialPageRow],
        *,
        page_key: str | None = None,
        record_meta: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """只更新发生变化的记录，保留历史、软删状态和已有行序。"""
        await self._upsert_material_page_batches(
            snapshot_id,
            rows,
            full=False,
            page_key=page_key,
            record_meta=record_meta,
        )

    async def _upsert_material_page_batches(
        self,
        snapshot_id: UUID,
        rows: Sequence[MaterialPageRow],
        *,
        full: bool,
        page_key: str | None,
        record_meta: dict[str, dict[str, Any]] | None,
    ) -> None:
        for offset in range(0, len(rows), _SYNC_BATCH_SIZE):
            batch = rows[offset : offset + _SYNC_BATCH_SIZE]
            result = await self.session.scalars(
                select(MaterialPageRow).where(
                    MaterialPageRow.page_snapshot_id == snapshot_id,
                    MaterialPageRow.source_record_id.in_(
                        row.source_record_id for row in batch
                    ),
                )
            )
            existing_by_id = {row.source_record_id: row for row in result}
            for row in batch:
                existing = existing_by_id.get(row.source_record_id)
                if existing is not None:
                    if existing.is_deleted and not full:
                        continue
                    if (
                        not existing.is_deleted
                        and existing.cells == row.cells
                        and existing.search_text == row.search_text
                        and (not full or existing.row_order == row.row_order)
                    ):
                        continue
                self._record_status_transitions(
                    snapshot_id,
                    row,
                    existing=existing,
                    page_key=page_key,
                    record_meta=record_meta,
                )
                if existing is None:
                    self.session.add(row)
                    continue
                existing.cells = row.cells
                existing.search_text = row.search_text
                if full:
                    existing.row_order = row.row_order
                existing.last_synced_at = row.last_synced_at
                existing.is_deleted = False
            await self.session.flush()

    async def count_material_page_rows(self, snapshot_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(MaterialPageRow)
                .where(
                    MaterialPageRow.page_snapshot_id == snapshot_id,
                    MaterialPageRow.is_deleted.is_(False),
                )
            )
            or 0
        )

    async def upsert_material_page_row_write_through(
        self,
        snapshot_id: Any,
        row: MaterialPageRow,
        *,
        page_key: str | None = None,
        record_meta: dict[str, dict[str, Any]] | None = None,
    ) -> bool:
        """单条写穿：编辑保存后按 source_record_id 精确 upsert，不等增量/全量。

        与 upsert_material_page_rows_incremental 的差异：
        - 只加载目标行，避免大表为单条更新整表载入内存；
        - 本地软删行直接恢复——写穿以刚 GET 回的飞书记录为准，记录确认存在。
        更新已有行保留原 row_order，维持快照行序稳定。
        返回是否为新增行（调用方据此维护 snapshot.total_rows）。
        """
        result = await self.session.execute(
            select(MaterialPageRow).where(
                MaterialPageRow.page_snapshot_id == snapshot_id,
                MaterialPageRow.source_record_id == row.source_record_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            self._record_status_transitions(
                snapshot_id,
                row,
                existing=existing,
                page_key=page_key,
                record_meta=record_meta,
            )
            existing.cells = row.cells
            existing.search_text = row.search_text
            existing.last_synced_at = row.last_synced_at
            existing.is_deleted = False
            await self.session.flush()
            return False
        self._record_status_transitions(
            snapshot_id,
            row,
            existing=None,
            page_key=page_key,
            record_meta=record_meta,
        )
        self.session.add(row)
        await self.session.flush()
        return True

    async def soft_delete_material_page_row(
        self,
        snapshot_id: Any,
        source_record_id: str,
    ) -> bool:
        """删除写穿：按 source_record_id 软删镜像行，立即从本地列表消失。

        增量同步只 upsert 变更行、永远追不掉飞书侧删除，全量对账要等
        每日凌晨兜底；删除成功后同步软删本地行，页面无需再等。
        返回是否实际删除了未删行。
        """
        result = await self.session.execute(
            select(MaterialPageRow).where(
                MaterialPageRow.page_snapshot_id == snapshot_id,
                MaterialPageRow.source_record_id == source_record_id,
                MaterialPageRow.is_deleted.is_(False),
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            return False
        existing.is_deleted = True
        await self.session.flush()
        return True

    def _record_status_transitions(
        self,
        snapshot_id: Any,
        row: MaterialPageRow,
        *,
        existing: MaterialPageRow | None,
        page_key: str | None,
        record_meta: dict[str, dict[str, Any]] | None,
    ) -> None:
        """对比受监控状态字段新旧取值，写检验状态变更日志。

        仅在页面受监控且带 record_meta（飞书记录顶层时间戳）时捕获：
        - 已有行取值变化 → 变更记录（occurred_at=记录 last_modified_time）
        - 新进入镜像的行 → 初始状态记录（occurred_at=记录 created_time）
        """
        field_name = inspection_watched_field(page_key) if page_key else None
        if field_name is None or not record_meta:
            return
        meta = record_meta.get(row.source_record_id)
        if not meta:
            return
        detected_at = row.last_synced_at
        if existing is None:
            self.session.add(
                build_initial_transition(
                    page_key=page_key or "",
                    page_snapshot_id=snapshot_id,
                    source_record_id=row.source_record_id,
                    field_name=field_name,
                    new_value=row.cells.get(field_name) if row.cells else None,
                    occurred_ms=meta.get("created_ms"),
                    modified_ms=meta.get("modified_ms"),
                    detected_at=detected_at,
                )
            )
            return
        transition = build_change_transition(
            page_key=page_key or "",
            page_snapshot_id=snapshot_id,
            source_record_id=row.source_record_id,
            field_name=field_name,
            old_value=existing.cells.get(field_name) if existing.cells else None,
            new_value=row.cells.get(field_name) if row.cells else None,
            modified_ms=meta.get("modified_ms"),
            detected_at=detected_at,
        )
        if transition is not None:
            self.session.add(transition)

    async def iter_material_page_rows(
        self,
        snapshot_id: UUID,
        *,
        sort_date_field: str | None,
        department_names: set[str] | None,
    ) -> AsyncIterator[Sequence[tuple[str, dict[str, Any]]]]:
        """Yield bounded batches of cell data in the material page's display order."""
        row = MaterialPageRow
        stmt = select(row.source_record_id, row.cells).where(
            row.page_snapshot_id == snapshot_id,
            row.is_deleted.is_(False),
        )
        if department_names is not None:
            department = row.cells["车间"]
            # Keep historical non-string cells for the service's scope check.
            python_whitespace = (
                "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680"
                "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
                "\u2028\u2029\u202f\u205f\u3000"
            )
            stmt = stmt.where(
                func.jsonb_typeof(department).is_distinct_from("string")
                | func.btrim(department.astext, python_whitespace).in_(department_names)
            )
        if sort_date_field:
            cell = row.cells[sort_date_field]
            date_order = case(
                (func.jsonb_typeof(cell) == "number", cast(cell.astext, Double)),
                (
                    func.jsonb_typeof(cell) == "boolean",
                    (cell.astext == "true").cast(Integer),
                ),
                else_=0,
            )
            stmt = stmt.order_by(date_order.desc())
        stmt = stmt.order_by(row.row_order, row.created_at, row.source_record_id)
        result = await self.session.stream(stmt.execution_options(yield_per=256))
        try:
            async for batch in result.partitions():
                yield [(record_id, cells) for record_id, cells in batch]
        finally:
            await result.close()

    async def list_material_page_rows(
        self,
        snapshot_id: Any,
        *,
        keyword: str | None = None,
        offset: int = 0,
        limit: int | None = 50,
    ) -> tuple[list[MaterialPageRow], int]:
        count_stmt = (
            select(func.count())
            .select_from(MaterialPageRow)
            .where(
                MaterialPageRow.page_snapshot_id == snapshot_id,
                MaterialPageRow.is_deleted.is_(False),
            )
        )
        stmt = (
            select(MaterialPageRow)
            .where(
                MaterialPageRow.page_snapshot_id == snapshot_id,
                MaterialPageRow.is_deleted.is_(False),
            )
            .order_by(asc(MaterialPageRow.row_order), asc(MaterialPageRow.created_at))
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        if keyword:
            keyword_value = f"%{keyword.lower()}%"
            count_stmt = count_stmt.where(
                func.lower(MaterialPageRow.search_text).like(keyword_value)
            )
            stmt = stmt.where(
                func.lower(MaterialPageRow.search_text).like(keyword_value)
            )

        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)
        rows = list((await self.session.execute(stmt)).scalars().all())
        return rows, total

    # ── 页面飞书配置 ────────────────────────────────────────────────

    async def list_page_feishu_configs(self) -> list[dict[str, Any]]:
        """获取所有页面飞书配置"""
        from app.modules.warehouse.models import WarehousePageFeishuConfig

        stmt = select(WarehousePageFeishuConfig).where(
            WarehousePageFeishuConfig.is_deleted.is_(False)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {
                "page_key": r.page_key,
                "app_token": r.app_token,
                "table_id": r.table_id,
                "table_name": r.table_name,
                "view_id": r.view_id,
                "feishu_inbound_form_url": r.feishu_inbound_form_url,
                "feishu_outbound_form_url": r.feishu_outbound_form_url,
            }
            for r in rows
        ]

    async def get_page_feishu_config(self, page_key: str) -> dict[str, Any] | None:
        """获取指定页面的飞书配置"""
        from app.modules.warehouse.models import WarehousePageFeishuConfig

        stmt = select(WarehousePageFeishuConfig).where(
            WarehousePageFeishuConfig.page_key == page_key,
            WarehousePageFeishuConfig.is_deleted.is_(False),
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if not row:
            return None
        return {
            "page_key": row.page_key,
            "app_token": row.app_token,
            "table_id": row.table_id,
            "table_name": row.table_name,
            "view_id": row.view_id,
            "feishu_inbound_form_url": row.feishu_inbound_form_url,
            "feishu_outbound_form_url": row.feishu_outbound_form_url,
        }

    async def upsert_page_feishu_config(self, config: dict[str, Any]) -> None:
        """新增或更新页面飞书配置"""
        from app.modules.warehouse.models import WarehousePageFeishuConfig

        stmt = select(WarehousePageFeishuConfig).where(
            WarehousePageFeishuConfig.page_key == config["page_key"],
            WarehousePageFeishuConfig.is_deleted.is_(False),
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row:
            row.app_token = config["app_token"]
            row.table_id = config["table_id"]
            row.table_name = config["table_name"]
            row.view_id = config.get("view_id")
            row.feishu_inbound_form_url = config.get("feishu_inbound_form_url")
            row.feishu_outbound_form_url = config.get("feishu_outbound_form_url")
        else:
            new_row = WarehousePageFeishuConfig(**config)
            self.session.add(new_row)
        await self.session.commit()
