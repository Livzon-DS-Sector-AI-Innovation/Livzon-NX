"""Production-owned Feishu configuration and Bitable preview service."""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.modules.production.models import (
    FermentationRecord,
    ProductionFeishuConfig,
    ProductionFeishuSyncBinding,
    SeedCultureRecord,
)
from app.modules.production.operations_repository import OperationsRepository
from app.modules.production.operations_schemas import (
    FermentationCreate,
    FermentationUpdate,
    SeedCultureCreate,
    SeedCultureUpdate,
)
from app.modules.production.process_catalog import (
    PROCESS_STEP_BY_CODE,
    validate_process_data,
)
from app.modules.production.process_schemas import (
    ProcessExecutionRecordCreate,
    ProcessExecutionRecordUpdate,
)
from app.modules.production.process_service import ProcessExecutionService
from app.modules.production.repository import ProductionRepository
from app.modules.production.schemas import (
    BatchCreate,
    BatchUpdate,
    ProductionExecutionPlanCreate,
    ProductionExecutionPlanUpdate,
    ProductionFeishuConfigResponse,
    ProductionFeishuConfigUpsert,
    ProductionFeishuConnectivityResult,
    ProductionFeishuConnectivityStep,
    ProductionFeishuFieldPreview,
    ProductionFeishuRecordPreview,
    ProductionFeishuSyncBindingCreate,
    ProductionFeishuSyncBindingResponse,
    ProductionFeishuSyncBindingUpdate,
    ProductionFeishuSyncExecuteRequest,
    ProductionFeishuSyncRunResponse,
    ProductionFeishuTableItem,
    ProductionFeishuTableListResponse,
    ProductionFeishuTablePreviewResponse,
)
from app.platform.integrations.feishu.utils import (
    OPEN_API_BASE_URL,
    ConnectivityStep,
    get_tenant_access_token,
    resolve_bitable_reference,
    test_bitable_table_with_token,
)

PROCESS_SYNC_TARGETS: dict[str, tuple[str, str | None]] = {
    "broth_receive": ("receive", None),
    "broth_pretreat": ("pretreat", None),
    "ceramic_feed": ("ceramic", "feed"),
    "ceramic_ops": ("ceramic", "operations"),
    "ceramic_clean": ("ceramic", "clean"),
    "ceramic_sep": ("ceramic", "separation"),
    "ceramic_equip": ("ceramic", "equipment"),
    **{code: (code, None) for code in PROCESS_STEP_BY_CODE},
}
BASE_SYNC_TARGETS = {
    "sales_plan_detail",
    "production_plan",
    "batch",
    "fermentation_record",
    "fermentation",
    "seed_culture",
}


class ProductionFeishuService:
    """生产模块飞书配置与多维表格读取服务"""

    def __init__(self, session: AsyncSession):
        self.repo = ProductionRepository(session)
        self.operations_repo = OperationsRepository(session)
        self.process_service = ProcessExecutionService(session)

    async def get_config_response(self) -> ProductionFeishuConfigResponse:
        config = await self._get_any_config()
        if not config:
            return ProductionFeishuConfigResponse(
                id=None,
                config_name="生产飞书配置",
                app_id="",
                bitable_app_token="",
                table_id="",
                is_active=True,
                remark=None,
                app_secret_configured=False,
                app_secret_masked="",
            )
        return self._to_config_response(config)

    async def list_config_responses(self) -> list[ProductionFeishuConfigResponse]:
        configs = await self._list_configs()
        return [self._to_config_response(config) for config in configs]

    async def list_sync_bindings(
        self, config_id: uuid.UUID | None = None
    ) -> list[ProductionFeishuSyncBindingResponse]:
        """列出已配置的同步绑定，不触发任何飞书读写。"""
        try:
            bindings = await self.repo.list_feishu_sync_bindings(config_id)
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "飞书同步绑定表不可用，请先执行数据库迁移："
                    "alembic upgrade head"
                ),
                detail=str(exc.__class__.__name__),
            ) from exc
        return [self._to_sync_binding_response(binding) for binding in bindings]

    async def create_sync_binding(
        self, data: ProductionFeishuSyncBindingCreate
    ) -> ProductionFeishuSyncBindingResponse:
        """创建同步绑定，并校验其逻辑关联的生产飞书配置存在。"""
        await self._get_config_by_id_or_raise(data.config_id)
        try:
            binding = await self.repo.create_feishu_sync_binding(data.model_dump())
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=400,
                message="创建飞书同步绑定失败，请检查配置、目标和数据表是否重复",
                detail=str(exc.__class__.__name__),
            ) from exc
        return self._to_sync_binding_response(binding)

    async def update_sync_binding(
        self, binding_id: uuid.UUID, data: ProductionFeishuSyncBindingUpdate
    ) -> ProductionFeishuSyncBindingResponse | None:
        """更新同步绑定；启用仅代表允许后续同步任务使用，不会立即写入飞书。"""
        update_data = data.model_dump(exclude_unset=True)
        config_id = update_data.get("config_id")
        if config_id:
            await self._get_config_by_id_or_raise(config_id)
        try:
            binding = await self.repo.update_feishu_sync_binding(
                binding_id, update_data
            )
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=400,
                message="更新飞书同步绑定失败，请检查配置、目标和数据表是否重复",
                detail=str(exc.__class__.__name__),
            ) from exc
        return self._to_sync_binding_response(binding) if binding else None

    async def delete_sync_binding(self, binding_id: uuid.UUID) -> bool:
        """软删除同步绑定，不删除任何飞书数据。"""
        try:
            return await self.repo.delete_feishu_sync_binding(binding_id)
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message="删除飞书同步绑定失败",
                detail=str(exc.__class__.__name__),
            ) from exc

    async def get_sync_binding_preview(
        self, binding_id: uuid.UUID, page_size: int = 20
    ) -> ProductionFeishuTablePreviewResponse:
        """按绑定读取飞书表预览，不写入平台业务数据。"""
        binding = await self._get_sync_binding_by_id_or_raise(binding_id)
        return await self.get_table_preview(
            config_id=binding.config_id,
            table_id=binding.table_id,
            page_size=page_size,
        )

    async def list_sync_runs(
        self, binding_id: uuid.UUID, limit: int = 20
    ) -> list[ProductionFeishuSyncRunResponse]:
        """获取某个绑定的运行历史。"""
        await self._get_sync_binding_by_id_or_raise(binding_id)
        try:
            runs = await self.repo.list_feishu_sync_runs(binding_id, limit)
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "飞书同步运行记录表不可用，请先执行数据库迁移："
                    "alembic upgrade head"
                ),
                detail=str(exc.__class__.__name__),
            ) from exc
        return [ProductionFeishuSyncRunResponse.model_validate(run) for run in runs]

    async def execute_sync_binding(
        self, binding_id: uuid.UUID, data: ProductionFeishuSyncExecuteRequest
    ) -> ProductionFeishuSyncRunResponse:
        """预览或执行生产业务绑定同步。"""
        binding = await self._get_sync_binding_by_id_or_raise(binding_id)
        if not self._is_supported_sync_target(binding.sync_target):
            raise AppException(message=f"不支持的同步业务目标：{binding.sync_target}")
        if not data.dry_run and not binding.is_active:
            raise AppException(message="同步绑定未启用，只能执行预览")
        config = await self._get_config_by_id_or_raise(binding.config_id)
        if not config.is_active:
            raise AppException(message="关联的生产飞书配置未启用")

        idempotency_key = data.idempotency_key or str(uuid.uuid4())
        existing = await self.repo.get_feishu_sync_run_by_idempotency_key(
            binding_id, idempotency_key
        )
        if existing:
            return ProductionFeishuSyncRunResponse.model_validate(existing)

        sync_run = await self.repo.create_feishu_sync_run(
            {
                "binding_id": binding.id,
                "run_mode": "preview" if data.dry_run else "execute",
                "status": "running",
                "idempotency_key": idempotency_key,
            }
        )
        try:
            records = await self._get_all_binding_records(binding, config)
            async with self.repo.session.begin_nested():
                for record in records:
                    try:
                        mapped = self._map_target_record(binding, record)
                    except (ValueError, AppException):
                        sync_run.skipped_count += 1
                        continue
                    if (
                        binding.product_name
                        and mapped.get("product_name")
                        and mapped["product_name"] != binding.product_name
                    ):
                        sync_run.skipped_count += 1
                        continue
                    if data.dry_run:
                        sync_run.updated_count += 1
                        continue
                    outcome = await self._upsert_target_record(
                        binding, record.record_id, mapped
                    )
                    if outcome == "created":
                        sync_run.created_count += 1
                    elif outcome == "updated":
                        sync_run.updated_count += 1
                    else:
                        sync_run.skipped_count += 1

            sync_run.status = "success"
            sync_run.finished_at = datetime.now(UTC)
            binding.last_status = "success"
            binding.last_run_at = sync_run.finished_at
            binding.last_error = None
            await self.repo.session.flush()
        except Exception as exc:
            sync_run.status = "failed"
            sync_run.finished_at = datetime.now(UTC)
            sync_run.failed_count += 1
            sync_run.error_summary = self._safe_sync_error(str(exc), config)
            binding.last_status = "failed"
            binding.last_run_at = sync_run.finished_at
            binding.last_error = sync_run.error_summary
            await self.repo.session.flush()
        return ProductionFeishuSyncRunResponse.model_validate(sync_run)

    async def save_config(
        self, data: ProductionFeishuConfigUpsert
    ) -> ProductionFeishuConfigResponse:
        reference = resolve_bitable_reference(
            app_token=data.bitable_app_token,
            table_id=data.table_id,
        )
        existing = await self._get_config_by_id(data.id) if data.id else None
        if data.id and not existing:
            raise AppException(message="生产飞书配置不存在")
        if existing:
            existing.config_name = data.config_name
            existing.app_id = data.app_id
            if data.app_secret:
                existing.encrypted_app_secret = encrypt_secret(data.app_secret)
            existing.bitable_app_token = reference.app_token or ""
            existing.table_id = reference.table_id
            existing.is_active = data.is_active
            existing.remark = data.remark
            existing.timezone = data.timezone
            existing.daily_sync_time = data.daily_sync_time
            await self.repo.session.flush()
            await self.repo.session.commit()
            return self._to_config_response(existing)

        previous = await self._get_any_config()
        encrypted_secret = (
            encrypt_secret(data.app_secret)
            if data.app_secret
            else (previous.encrypted_app_secret if previous else "")
        )
        if not encrypted_secret:
            raise AppException(message="首次保存飞书配置时必须填写 App Secret")

        config = ProductionFeishuConfig(
            config_name=data.config_name,
            app_id=data.app_id,
            encrypted_app_secret=encrypted_secret,
            bitable_app_token=reference.app_token or "",
            table_id=reference.table_id,
            is_active=data.is_active,
            remark=data.remark,
            timezone=data.timezone,
            daily_sync_time=data.daily_sync_time,
        )
        await self.repo.save_feishu_config(config)
        await self.repo.session.commit()
        return self._to_config_response(config)

    async def test_connectivity(
        self, data: ProductionFeishuConfigUpsert | None = None
    ) -> ProductionFeishuConnectivityResult:
        config = await self._resolve_config(data)
        steps: list[ProductionFeishuConnectivityStep] = []

        token = await self._test_tenant_token(config, steps)
        if not token:
            return ProductionFeishuConnectivityResult(ok=False, steps=steps)

        reference = resolve_bitable_reference(
            app_token=config.bitable_app_token,
            table_id=config.table_id,
        )
        if not reference.app_token:
            steps.append(
                ProductionFeishuConnectivityStep(
                    name="数据入口",
                    status="ok",
                    message="应用凭据认证成功；请继续添加 Wiki 或多维表格入口",
                )
            )
            return ProductionFeishuConnectivityResult(ok=True, steps=steps)
        if reference.table_id:
            table_step = await test_bitable_table_with_token(
                tenant_access_token=token,
                app_token=reference.app_token or "",
                table_id=reference.table_id,
                name="默认数据表",
            )
            steps.append(self._connectivity_step_from_raw(table_step))
        else:
            try:
                tables = await self._fetch_bitable_tables(
                    token=token,
                    app_token=reference.app_token or "",
                )
                steps.append(
                    ProductionFeishuConnectivityStep(
                        name="数据表列表",
                        status="ok",
                        message=f"已读取 {len(tables)} 张数据表",
                    )
                )
            except Exception as exc:
                steps.append(
                    ProductionFeishuConnectivityStep(
                        name="数据表列表",
                        status="error",
                        message=f"读取数据表列表失败：{exc}",
                    )
                )
        return ProductionFeishuConnectivityResult(
            ok=all(step.status == "ok" for step in steps),
            steps=steps,
        )

    async def list_tables(
        self,
        *,
        config_id: uuid.UUID | None = None,
    ) -> ProductionFeishuTableListResponse:
        config = await self._get_config_for_read(config_id)
        token = await self._tenant_token_for_config(config)
        reference = resolve_bitable_reference(app_token=config.bitable_app_token)
        if not reference.app_token:
            raise AppException(message="生产飞书 App Token 未配置")

        tables = await self._fetch_bitable_tables(
            token=token,
            app_token=reference.app_token,
        )
        return ProductionFeishuTableListResponse(
            app_token=reference.app_token,
            tables=[self._table_from_raw(item) for item in tables],
            total=len(tables),
        )

    async def get_table_preview(
        self,
        *,
        config_id: uuid.UUID | None = None,
        table_id: str | None = None,
        page_size: int = 20,
        page_token: str | None = None,
    ) -> ProductionFeishuTablePreviewResponse:
        config = await self._get_config_for_read(config_id)
        token = await self._tenant_token_for_config(config)
        reference = resolve_bitable_reference(
            app_token=config.bitable_app_token,
            table_id=table_id or config.table_id,
        )
        if not reference.app_token:
            raise AppException(message="生产飞书 App Token 未配置")
        if not reference.table_id:
            tables = await self._fetch_bitable_tables(
                token=token,
                app_token=reference.app_token,
            )
            first_table = self._table_from_raw(tables[0]) if tables else None
            if not first_table:
                raise AppException(message="该多维表格下未读取到数据表")
            reference = resolve_bitable_reference(
                app_token=reference.app_token,
                table_id=first_table.table_id,
            )

        resolved_app_token = reference.app_token
        resolved_table_id = reference.table_id
        if not resolved_app_token or not resolved_table_id:
            raise AppException(message="生产飞书数据表引用未配置完整")

        normalized_page_size = max(1, min(page_size, 100))
        fields, records_body = await self._fetch_bitable_preview(
            token=token,
            app_token=resolved_app_token,
            table_id=resolved_table_id,
            page_size=normalized_page_size,
            page_token=page_token,
        )

        data = records_body.get("data") if isinstance(records_body, dict) else {}
        records_value = data.get("items") if isinstance(data, dict) else []
        records = records_value if isinstance(records_value, list) else []
        return ProductionFeishuTablePreviewResponse(
            app_token=resolved_app_token,
            table_id=resolved_table_id,
            fields=[self._field_from_raw(item) for item in fields],
            records=[self._record_from_raw(item) for item in records],
            page_size=normalized_page_size,
            has_more=bool(data.get("has_more")) if isinstance(data, dict) else False,
            page_token=(
                str(data.get("page_token"))
                if isinstance(data, dict) and data.get("page_token")
                else None
            ),
            total=self._safe_int(data.get("total")) if isinstance(data, dict) else None,
        )

    async def _get_all_binding_records(
        self, binding: ProductionFeishuSyncBinding, config: ProductionFeishuConfig
    ) -> list[ProductionFeishuRecordPreview]:
        """分页读取绑定表的全部记录，供一次受控同步使用。"""
        records: list[ProductionFeishuRecordPreview] = []
        page_token: str | None = None
        while True:
            preview = await self.get_table_preview(
                config_id=config.id,
                table_id=binding.table_id,
                page_size=100,
                page_token=page_token,
            )
            records.extend(preview.records)
            if not preview.has_more or not preview.page_token:
                break
            page_token = preview.page_token
        return records

    @classmethod
    def _is_supported_sync_target(cls, target: str) -> bool:
        return target in BASE_SYNC_TARGETS or target in PROCESS_SYNC_TARGETS

    @classmethod
    def _map_target_record(
        cls,
        binding: ProductionFeishuSyncBinding,
        record: ProductionFeishuRecordPreview,
    ) -> dict[str, Any]:
        if binding.sync_target == "sales_plan_detail":
            return cls._map_sales_plan_record(binding, record)

        mapped = {
            platform_field: cls._normalize_sync_value(
                cls._extract_feishu_value(record.fields.get(feishu_field))
            )
            for platform_field, feishu_field in binding.field_mapping.items()
        }
        mapped = {
            key: value for key, value in mapped.items() if value not in (None, "")
        }
        if (
            binding.product_name
            and "product_name" not in mapped
            and binding.sync_target
            in {
                "production_plan",
                "batch",
                "fermentation_record",
                "fermentation",
                "seed_culture",
            }
        ):
            mapped["product_name"] = binding.product_name

        target = binding.sync_target
        if target == "production_plan":
            return ProductionExecutionPlanCreate(
                **mapped, source="feishu", source_record_id=record.record_id
            ).model_dump()
        if target == "batch":
            return BatchCreate(**mapped).model_dump()
        if target in {"fermentation_record", "fermentation"}:
            cycle_data = {
                key: mapped.pop(key)
                for key in tuple(mapped)
                if key.startswith("cycle_")
            }
            if cycle_data:
                mapped["cycle_data"] = cycle_data
            return FermentationCreate(
                **mapped, source="feishu", source_record_id=record.record_id
            ).model_dump()
        if target == "seed_culture":
            material_fields = {
                "glucose_batch",
                "corn_starch_batch",
                "corn_syrup_batch",
                "ammonium_sulfate_batch",
                "soybean_meal_batch",
                "calcium_carbonate_batch",
            }
            quality_fields = {
                "ph_before_adjust",
                "ph_after_adjust",
                "ph_after_sterilization",
                "reducing_sugar",
                "total_sugar",
                "amino_nitrogen",
                "merge_ph",
                "merge_bacteria_density",
                "merge_total_sugar",
                "merge_reducing_sugar",
                "merge_amino_nitrogen",
            }
            common = {
                "batch_no",
                "product_name",
                "prepare_date",
                "tank_yield",
                "status",
                "remarks",
            }
            materials = {key: mapped[key] for key in material_fields if key in mapped}
            quality = {key: mapped[key] for key in quality_fields if key in mapped}
            operation = {
                key: value
                for key, value in mapped.items()
                if key not in common | material_fields | quality_fields
            }
            payload = {key: mapped[key] for key in common if key in mapped}
            payload.update(
                materials=materials,
                quality_data=quality,
                operation_data=operation,
                source="feishu",
                source_record_id=record.record_id,
            )
            return SeedCultureCreate(**payload).model_dump()

        process_code, substage = PROCESS_SYNC_TARGETS[target]
        common = {"batch_no", "recorded_at", "status", "remarks"}
        process_data = {
            key: value for key, value in mapped.items() if key not in common
        }
        if substage:
            process_data.setdefault("substage", substage)
        return ProcessExecutionRecordCreate(
            batch_no=str(mapped.get("batch_no", "")),
            workshop_code=binding.workshop_code or "203",
            process_code=process_code,
            recorded_at=mapped.get("recorded_at") or datetime.now(UTC),
            status=mapped.get("status", "in_progress"),
            remarks=mapped.get("remarks"),
            data=validate_process_data(process_code, process_data),
            source="feishu",
            source_record_id=record.record_id,
        ).model_dump()

    @staticmethod
    def _normalize_sync_value(value: Any) -> Any:
        """规范飞书常见的千分位数字，其他文本保持原样。"""
        if isinstance(value, str):
            cleaned = value.strip()
            if "," in cleaned:
                try:
                    return float(cleaned.replace(",", ""))
                except ValueError:
                    return cleaned
            return cleaned
        return value

    async def _upsert_target_record(
        self,
        binding: ProductionFeishuSyncBinding,
        source_record_id: str,
        mapped: dict[str, Any],
    ) -> str:
        target = binding.sync_target
        if target == "sales_plan_detail":
            current = await self.repo.get_sales_plan_detail_by_source_record(
                "feishu", source_record_id
            )
            if current:
                for field_name, value in mapped.items():
                    setattr(current, field_name, value)
                return "updated"
            await self.repo.create_sales_plan_detail(
                {**mapped, "source": "feishu", "source_record_id": source_record_id}
            )
            return "created"

        if target == "production_plan":
            execution_plan = await self.repo.get_execution_plan_by_source_record(
                "feishu", source_record_id
            )
            if execution_plan:
                execution_update = ProductionExecutionPlanUpdate(
                    **{
                        key: value
                        for key, value in mapped.items()
                        if key not in {"source", "source_record_id"}
                    }
                )
                await self.repo.update_execution_plan(
                    execution_plan.id, execution_update.model_dump(exclude_unset=True)
                )
                return "updated"
            await self.repo.create_execution_plan(mapped)
            return "created"

        if target == "batch":
            batch = await self.repo.get_batch_by_no(mapped["batch_no"])
            if batch:
                batch_update = BatchUpdate(**mapped)
                await self.repo.update_batch(
                    batch.id, batch_update.model_dump(exclude_unset=True)
                )
                return "updated"
            await self.repo.create_batch(mapped)
            return "created"

        if target in {"fermentation_record", "fermentation"}:
            fermentation = await self.operations_repo.get_by_source(
                FermentationRecord, "feishu", source_record_id
            )
            if fermentation:
                fermentation_update = FermentationUpdate(
                    **{
                        key: value
                        for key, value in mapped.items()
                        if key not in {"source", "source_record_id"}
                    }
                )
                await self.operations_repo.update(
                    FermentationRecord,
                    fermentation.id,
                    fermentation_update.model_dump(exclude_unset=True),
                )
                return "updated"
            await self.operations_repo.create(FermentationRecord, mapped)
            return "created"

        if target == "seed_culture":
            seed_culture = await self.operations_repo.get_by_source(
                SeedCultureRecord, "feishu", source_record_id
            )
            if seed_culture:
                seed_update = SeedCultureUpdate(
                    **{
                        key: value
                        for key, value in mapped.items()
                        if key not in {"source", "source_record_id"}
                    }
                )
                await self.operations_repo.update(
                    SeedCultureRecord,
                    seed_culture.id,
                    seed_update.model_dump(exclude_unset=True),
                )
                return "updated"
            await self.operations_repo.create(SeedCultureRecord, mapped)
            return "created"

        process_code = mapped["process_code"]
        process_record = await self.process_service.repo.get_record_by_source(
            process_code, "feishu", source_record_id
        )
        if process_record:
            if process_record.status == "completed":
                return "skipped"
            process_update = ProcessExecutionRecordUpdate(
                status=mapped["status"],
                recorded_at=mapped["recorded_at"],
                data=mapped["data"],
                remarks=mapped.get("remarks"),
            )
            await self.process_service.update_record(process_record.id, process_update)
            return "updated"
        await self.process_service.create_record(ProcessExecutionRecordCreate(**mapped))
        return "created"

    @staticmethod
    def _map_sales_plan_record(
        binding: ProductionFeishuSyncBinding, record: ProductionFeishuRecordPreview
    ) -> dict[str, str | float | None]:
        """将绑定映射转换为销售执行模型字段；缺少产品名称的记录不写入。"""
        numeric_fields = {
            "last_month_delivered_uninvoiced",
            "current_year_delivered",
            "month_planned_delivery",
            "month_delivered_qty",
            "undelivered_qty",
            "month_planned_invoice",
            "invoiced_qty",
            "delivery_completion_rate",
            "last_month_end_inventory",
            "month_planned_capacity",
            "month_end_inventory",
        }
        allowed_fields = numeric_fields | {"product_name", "unit", "remarks"}
        mapped: dict[str, str | float | None] = {}
        for platform_field, feishu_field in binding.field_mapping.items():
            if platform_field not in allowed_fields:
                continue
            value = record.fields.get(feishu_field)
            if value in (None, ""):
                continue
            if platform_field in numeric_fields:
                try:
                    mapped[platform_field] = float(str(value).replace(",", ""))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"字段 {platform_field} 不是数字") from exc
            else:
                mapped[platform_field] = str(value).strip() or None
        if not mapped.get("product_name"):
            raise ValueError("缺少 product_name 映射或产品名称为空")
        return mapped

    @staticmethod
    def _safe_sync_error(message: str, config: ProductionFeishuConfig) -> str:
        """避免错误摘要中泄露应用标识或表格 Token。"""
        safe_message = message.replace(config.app_id, "***")
        return safe_message.replace(config.bitable_app_token, "***")[:500]

    async def _fetch_bitable_tables(
        self,
        *,
        token: str,
        app_token: str,
    ) -> list[dict[str, Any]]:
        if not app_token:
            raise AppException(message="生产飞书 App Token 未配置")

        items: list[dict[str, Any]] = []
        page_token: str | None = None
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(
            base_url=OPEN_API_BASE_URL, timeout=20.0
        ) as client:
            while True:
                params: dict[str, Any] = {"page_size": 100}
                if page_token:
                    params["page_token"] = page_token
                resp = await client.get(
                    f"/bitable/v1/apps/{app_token}/tables",
                    headers=headers,
                    params=params,
                )
                body = self._feishu_response_body(resp)
                if resp.status_code >= 400:
                    raise AppException(
                        message=self._append_bitable_app_token_hint(
                            self._feishu_http_error_message(
                                resp,
                                body,
                                "读取飞书数据表失败",
                            )
                        )
                    )
                if body.get("code") != 0:
                    raise AppException(
                        message=self._append_bitable_app_token_hint(
                            self._feishu_business_error_message(
                                body,
                                "读取飞书数据表失败",
                            )
                        )
                    )
                data = body.get("data") if isinstance(body, dict) else {}
                page_items_value = data.get("items") if isinstance(data, dict) else []
                page_items = (
                    page_items_value if isinstance(page_items_value, list) else []
                )
                items.extend(item for item in page_items if isinstance(item, dict))
                if not isinstance(data, dict) or not data.get("has_more"):
                    break
                page_token = str(data.get("page_token") or "")
                if not page_token:
                    break
        return items

    async def _fetch_bitable_preview(
        self,
        *,
        token: str,
        app_token: str,
        table_id: str,
        page_size: int,
        page_token: str | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(
            base_url=OPEN_API_BASE_URL, timeout=20.0
        ) as client:
            fields_resp = await client.get(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                headers=headers,
                params={"page_size": 100},
            )
            fields_body = self._feishu_response_body(fields_resp)
            if fields_resp.status_code >= 400:
                raise AppException(
                    message=self._feishu_http_error_message(
                        fields_resp,
                        fields_body,
                        "读取飞书字段失败",
                    )
                )
            if fields_body.get("code") != 0:
                raise AppException(
                    message=self._feishu_business_error_message(
                        fields_body,
                        "读取飞书字段失败",
                    )
                )

            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            records_resp = await client.post(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/search",
                headers=headers,
                params=params,
                json={},
            )
            records_body = self._feishu_response_body(records_resp)
            if records_resp.status_code >= 400:
                raise AppException(
                    message=self._feishu_http_error_message(
                        records_resp,
                        records_body,
                        "读取飞书记录失败",
                    )
                )
            if records_body.get("code") != 0:
                raise AppException(
                    message=self._feishu_business_error_message(
                        records_body,
                        "读取飞书记录失败",
                    )
                )

        fields_data = fields_body.get("data") if isinstance(fields_body, dict) else {}
        fields_value = fields_data.get("items") if isinstance(fields_data, dict) else []
        fields = (
            [item for item in fields_value if isinstance(item, dict)]
            if isinstance(fields_value, list)
            else []
        )
        return fields, records_body

    async def _resolve_config(
        self, data: ProductionFeishuConfigUpsert | None
    ) -> ProductionFeishuConfig:
        if data:
            stored = await self._get_any_config()
            encrypted_secret = (
                encrypt_secret(data.app_secret)
                if data.app_secret
                else (stored.encrypted_app_secret if stored else "")
            )
            if not encrypted_secret:
                raise AppException(message="请填写 App Secret 后再测试连通性")
            reference = resolve_bitable_reference(
                app_token=data.bitable_app_token,
                table_id=data.table_id,
            )
            return ProductionFeishuConfig(
                config_name=data.config_name,
                app_id=data.app_id,
                encrypted_app_secret=encrypted_secret,
                bitable_app_token=reference.app_token or "",
                table_id=reference.table_id,
                is_active=data.is_active,
                remark=data.remark,
            )

        config = await self._get_any_config()
        if not config:
            raise AppException(message="请先保存生产飞书配置")
        return config

    async def _get_config_by_id(
        self, config_id: uuid.UUID | None
    ) -> ProductionFeishuConfig | None:
        if not config_id:
            return None
        try:
            return await self.repo.get_feishu_config_by_id(config_id)
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "生产飞书配置表不可用，请先执行数据库迁移："
                    "alembic upgrade head"
                ),
                detail=str(exc.__class__.__name__),
            ) from exc

    async def _get_config_by_id_or_raise(
        self, config_id: uuid.UUID
    ) -> ProductionFeishuConfig:
        config = await self._get_config_by_id(config_id)
        if not config:
            raise AppException(message="生产飞书配置不存在")
        if not config.is_active:
            raise AppException(message="该生产飞书配置未启用")
        return config

    async def _get_sync_binding_by_id_or_raise(
        self, binding_id: uuid.UUID
    ) -> ProductionFeishuSyncBinding:
        try:
            binding = await self.repo.get_feishu_sync_binding_by_id(binding_id)
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "飞书同步绑定表不可用，请先执行数据库迁移："
                    "alembic upgrade head"
                ),
                detail=str(exc.__class__.__name__),
            ) from exc
        if not binding:
            raise AppException(status_code=404, message="飞书同步绑定不存在")
        return binding

    async def _get_config_for_read(
        self, config_id: uuid.UUID | None = None
    ) -> ProductionFeishuConfig:
        if config_id:
            return await self._get_config_by_id_or_raise(config_id)
        return await self._get_active_config_or_raise()

    async def _list_configs(self) -> list[ProductionFeishuConfig]:
        try:
            return await self.repo.list_feishu_configs()
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "生产飞书配置表不可用，请先执行数据库迁移："
                    "alembic upgrade head"
                ),
                detail=str(exc.__class__.__name__),
            ) from exc

    async def _get_any_config(self) -> ProductionFeishuConfig | None:
        try:
            return await self.repo.get_any_feishu_config()
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "生产飞书配置表不可用，请先执行数据库迁移："
                    "alembic upgrade head"
                ),
                detail=str(exc.__class__.__name__),
            ) from exc

    async def _get_active_config_or_raise(self) -> ProductionFeishuConfig:
        try:
            config = await self.repo.get_active_feishu_config()
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "生产飞书配置表不可用，请先执行数据库迁移："
                    "alembic upgrade head"
                ),
                detail=str(exc.__class__.__name__),
            ) from exc
        if not config:
            raise AppException(message="请先启用生产飞书配置")
        return config

    async def _tenant_token_for_config(self, config: ProductionFeishuConfig) -> str:
        return await get_tenant_access_token(
            config.app_id,
            decrypt_secret(config.encrypted_app_secret),
            cache_key=f"production:{config.app_id}",
        )

    async def _test_tenant_token(
        self,
        config: ProductionFeishuConfig,
        steps: list[ProductionFeishuConnectivityStep],
    ) -> str | None:
        if not config.app_id or not config.encrypted_app_secret:
            steps.append(
                ProductionFeishuConnectivityStep(
                    name="应用凭证",
                    status="error",
                    message="App ID 或 App Secret 未配置",
                )
            )
            return None

        try:
            token = await self._tenant_token_for_config(config)
        except Exception as exc:
            steps.append(
                ProductionFeishuConnectivityStep(
                    name="应用凭证",
                    status="error",
                    message=f"飞书认证失败：{exc}",
                )
            )
            return None

        steps.append(
            ProductionFeishuConnectivityStep(
                name="应用凭证",
                status="ok",
                message="tenant_access_token 获取成功",
            )
        )
        return token

    def _to_config_response(
        self, config: ProductionFeishuConfig
    ) -> ProductionFeishuConfigResponse:
        return ProductionFeishuConfigResponse(
            id=config.id,
            config_name=config.config_name,
            app_id=config.app_id or "",
            bitable_app_token=config.bitable_app_token or "",
            table_id=config.table_id,
            is_active=config.is_active,
            remark=config.remark,
            timezone=config.timezone,
            daily_sync_time=config.daily_sync_time,
            app_secret_configured=bool(config.encrypted_app_secret),
            app_secret_masked=self._mask_encrypted_secret(config.encrypted_app_secret),
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    @staticmethod
    def _to_sync_binding_response(
        binding: ProductionFeishuSyncBinding,
    ) -> ProductionFeishuSyncBindingResponse:
        return ProductionFeishuSyncBindingResponse.model_validate(binding)

    @staticmethod
    def _table_from_raw(item: dict[str, Any]) -> ProductionFeishuTableItem:
        table_id = str(item.get("table_id") or "")
        return ProductionFeishuTableItem(
            table_id=table_id,
            name=str(item.get("name") or table_id),
            revision=ProductionFeishuService._safe_int(item.get("revision")),
        )

    @staticmethod
    def _connectivity_step_from_raw(
        step: ConnectivityStep,
    ) -> ProductionFeishuConnectivityStep:
        return ProductionFeishuConnectivityStep(
            name=step.name,
            status=step.status,
            message=step.message,
        )

    @staticmethod
    def _mask_encrypted_secret(encrypted_secret: str) -> str:
        if not encrypted_secret:
            return ""
        try:
            return mask_secret(decrypt_secret(encrypted_secret))
        except RuntimeError:
            return "****"

    @staticmethod
    def _field_from_raw(item: dict[str, Any]) -> ProductionFeishuFieldPreview:
        field_id = str(item.get("field_id") or item.get("id") or "")
        field_name = str(item.get("field_name") or item.get("name") or field_id)
        return ProductionFeishuFieldPreview(
            field_id=field_id,
            field_name=field_name,
            type=ProductionFeishuService._safe_int(item.get("type")),
            property=item.get("property")
            if isinstance(item.get("property"), dict)
            else None,
        )

    @staticmethod
    def _record_from_raw(item: dict[str, Any]) -> ProductionFeishuRecordPreview:
        raw_fields_value = item.get("fields")
        raw_fields: dict[str, Any] = (
            raw_fields_value if isinstance(raw_fields_value, dict) else {}
        )
        fields = {
            key: ProductionFeishuService._extract_feishu_value(value)
            for key, value in raw_fields.items()
        }
        return ProductionFeishuRecordPreview(
            record_id=str(item.get("record_id") or ""),
            fields=fields,
            created_time=ProductionFeishuService._safe_int(item.get("created_time")),
            last_modified_time=ProductionFeishuService._safe_int(
                item.get("last_modified_time")
            ),
        )

    @staticmethod
    def _extract_feishu_value(value: Any) -> Any:
        if isinstance(value, dict):
            if "value" in value:
                return ProductionFeishuService._extract_feishu_value(value.get("value"))

            for text_key in ("text", "name", "en_us", "zh_cn", "link", "url"):
                if text_key in value and value[text_key] not in (None, ""):
                    return ProductionFeishuService._extract_feishu_value(
                        value[text_key]
                    )

            return {
                key: ProductionFeishuService._extract_feishu_value(item)
                for key, item in value.items()
                if key != "type"
            }

        if isinstance(value, list):
            extracted = [
                ProductionFeishuService._extract_feishu_value(item) for item in value
            ]
            if len(extracted) == 1:
                return extracted[0]
            return extracted

        return value

    @staticmethod
    def _feishu_response_body(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            return {"raw": response.text}
        return body if isinstance(body, dict) else {"raw": body}

    @staticmethod
    def _feishu_http_error_message(
        response: httpx.Response,
        body: dict[str, Any],
        prefix: str,
    ) -> str:
        detail = body.get("msg") or body.get("message") or body.get("raw") or body
        code = body.get("code")
        code_text = f"，飞书 code={code}" if code is not None else ""
        return f"{prefix}：HTTP {response.status_code}{code_text}，{detail}"

    @staticmethod
    def _feishu_business_error_message(body: dict[str, Any], prefix: str) -> str:
        code = body.get("code")
        msg = body.get("msg") or body.get("message") or body
        return f"{prefix}：飞书 code={code}，{msg}"

    @staticmethod
    def _append_bitable_app_token_hint(message: str) -> str:
        return (
            f"{message}。请确认填写的是多维表格链接中 /base/ 后的 App Token，"
            "并且当前飞书应用已被授权访问该多维表格。"
        )

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
