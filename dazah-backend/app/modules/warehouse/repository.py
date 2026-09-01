"""Warehouse database queries live here."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import asc, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
        snapshot_id: Any,
        rows: Sequence[MaterialPageRow],
    ) -> None:
        """按 source_record_id 增量 upsert 页面行，替代全量 delete+add_all。

        - 命中已有 source_record_id → 更新 cells/search_text/row_order/
          last_synced_at，并恢复 is_deleted=False
        - 未命中 → 新增
        - 本地存在但本次未传入的 source_record_id → 软删（is_deleted=True）
        """
        result = await self.session.execute(
            select(MaterialPageRow).where(
                MaterialPageRow.page_snapshot_id == snapshot_id,
            )
        )
        existing_rows: dict[str, MaterialPageRow] = {
            row.source_record_id: row for row in result.scalars().all()
        }

        incoming_ids: set[str] = set()
        for row in rows:
            incoming_ids.add(row.source_record_id)
            existing = existing_rows.get(row.source_record_id)
            if existing:
                existing.cells = row.cells
                existing.search_text = row.search_text
                existing.row_order = row.row_order
                existing.last_synced_at = row.last_synced_at
                existing.is_deleted = False
            else:
                self.session.add(row)

        for record_id, existing in existing_rows.items():
            if record_id not in incoming_ids and existing.is_deleted is not True:
                existing.is_deleted = True

        await self.session.flush()

    async def upsert_material_page_rows_incremental(
        self,
        snapshot_id: Any,
        rows: Sequence[MaterialPageRow],
    ) -> None:
        """增量同步专用：只 upsert 本次传入的变更记录，不软删未传入的历史记录。

        与 upsert_material_page_rows 的差异：历史记录（本次未变更）保持原状，
        避免高频增量拉取把未变更的旧记录误标为已删除。
        """
        result = await self.session.execute(
            select(MaterialPageRow).where(
                MaterialPageRow.page_snapshot_id == snapshot_id,
            )
        )
        existing_rows: dict[str, MaterialPageRow] = {
            row.source_record_id: row for row in result.scalars().all()
        }

        for row in rows:
            existing = existing_rows.get(row.source_record_id)
            if existing:
                # 已在本地软删的记录，增量同步不应自动复活——只有全量同步
                # （upsert_material_page_rows）确认飞书仍有该记录时才恢复，
                # 避免飞书删除未生效 / 定时同步把已删记录反复拉回。
                if existing.is_deleted:
                    continue
                existing.cells = row.cells
                existing.search_text = row.search_text
                existing.row_order = row.row_order
                existing.last_synced_at = row.last_synced_at
                existing.is_deleted = False
            else:
                self.session.add(row)

        await self.session.flush()

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
        else:
            new_row = WarehousePageFeishuConfig(**config)
            self.session.add(new_row)
        await self.session.commit()
