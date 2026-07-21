"""生产历史数据的校验、幂等导入、对账与回滚服务。"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.models import (
    Batch,
    FermentationRecord,
    NonConformingEvent,
    ProcessExecutionRecord,
    ProductionExecutionPlan,
    ProductionMigrationChange,
    ProductionMigrationRecordMap,
    ProductionMigrationRun,
    SalesPlanDetail,
    SeedCultureRecord,
    ShiftHandover,
    ShiftLog,
)
from app.modules.production.operations_schemas import (
    FermentationCreate,
    NonConformingEventCreate,
    SeedCultureCreate,
    ShiftHandoverCreate,
    ShiftLogCreate,
)
from app.modules.production.process_schemas import ProcessExecutionRecordCreate
from app.modules.production.schemas import (
    BatchCreate,
    ProductionExecutionPlanCreate,
    SalesPlanDetailCreate,
)
from app.shared.base_model import BaseModel as OrmBaseModel


@dataclass(frozen=True)
class EntityDefinition:
    model: type[OrmBaseModel]
    schema: type[BaseModel]


ENTITY_DEFINITIONS = {
    "batches": EntityDefinition(Batch, BatchCreate),
    "production_execution_plans": EntityDefinition(
        ProductionExecutionPlan, ProductionExecutionPlanCreate
    ),
    "sales_plan_details": EntityDefinition(SalesPlanDetail, SalesPlanDetailCreate),
    "process_execution_records": EntityDefinition(
        ProcessExecutionRecord, ProcessExecutionRecordCreate
    ),
    "fermentation_records": EntityDefinition(FermentationRecord, FermentationCreate),
    "seed_culture_records": EntityDefinition(SeedCultureRecord, SeedCultureCreate),
    "non_conforming_events": EntityDefinition(
        NonConformingEvent, NonConformingEventCreate
    ),
    "shift_logs": EntityDefinition(ShiftLog, ShiftLogCreate),
    "shift_handovers": EntityDefinition(ShiftHandover, ShiftHandoverCreate),
}


class MigrationInputError(ValueError):
    pass


class ProductionMigrationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def load_directory(
        input_dir: Path,
    ) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        bundle: dict[str, list[dict[str, Any]]] = {}
        errors: list[str] = []
        for entity in ENTITY_DEFINITIONS:
            path = input_dir / f"{entity}.json"
            if not path.exists():
                bundle[entity] = []
                continue
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{path.name}: {exc}")
                bundle[entity] = []
                continue
            records = content.get("records") if isinstance(content, dict) else content
            if not isinstance(records, list):
                errors.append(f"{path.name}: 根节点必须是数组或包含 records 数组")
                bundle[entity] = []
                continue
            bundle[entity] = records
        return bundle, errors

    @staticmethod
    def validate_bundle(
        bundle: dict[str, list[dict[str, Any]]],
    ) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        validated: dict[str, list[dict[str, Any]]] = {}
        errors: list[str] = []
        for entity, records in bundle.items():
            definition = ENTITY_DEFINITIONS.get(entity)
            if not definition:
                errors.append(f"不支持的实体: {entity}")
                continue
            validated[entity] = []
            seen: set[str] = set()
            for index, record in enumerate(records):
                source_id = (
                    record.get("source_record_id") if isinstance(record, dict) else None
                )
                payload = record.get("data") if isinstance(record, dict) else None
                if not source_id or not isinstance(payload, dict):
                    errors.append(
                        f"{entity}[{index}]: 必须包含 source_record_id 和 data 对象"
                    )
                    continue
                if source_id in seen:
                    errors.append(f"{entity}[{index}]: 来源标识重复 {source_id}")
                    continue
                seen.add(source_id)
                try:
                    parsed = definition.schema.model_validate(payload)
                except Exception as exc:  # Pydantic provides the field-level detail.
                    errors.append(f"{entity}[{index}]: {exc}")
                    continue
                validated[entity].append(
                    {"source_record_id": str(source_id), "data": parsed.model_dump()}
                )
        return validated, errors

    async def execute(
        self,
        *,
        bundle: dict[str, list[dict[str, Any]]],
        source_system: str,
        run_key: str,
        dry_run: bool,
    ) -> ProductionMigrationRun:
        existing = await self.session.scalar(
            select(ProductionMigrationRun).where(
                ProductionMigrationRun.run_key == run_key
            )
        )
        if existing:
            return existing
        validated, errors = self.validate_bundle(bundle)
        run = ProductionMigrationRun(
            run_key=run_key,
            source_system=source_system,
            mode="dry_run" if dry_run else "import",
            status="running",
            started_at=datetime.now(UTC),
            input_counts={entity: len(records) for entity, records in bundle.items()},
            report={"validation_errors": errors, "entities": {}},
        )
        self.session.add(run)
        await self.session.flush()
        if errors:
            run.status = "validation_failed"
            run.failed_count = len(errors)
            run.finished_at = datetime.now(UTC)
            await self.session.flush()
            return run

        report_entities: dict[str, Any] = {}
        for entity, records in validated.items():
            counts = {
                "input": len(records),
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
            }
            report_entities[entity] = counts
            for record in records:
                try:
                    async with self.session.begin_nested():
                        action = await self._apply_record(
                            run, entity, record, source_system, dry_run
                        )
                    counts[action] += 1
                    setattr(run, f"{action}_count", getattr(run, f"{action}_count") + 1)
                except Exception as exc:
                    counts["failed"] += 1
                    run.failed_count += 1
                    run.report = {
                        **run.report,
                        "record_errors": [
                            *(run.report.get("record_errors") or []),
                            {
                                "entity": entity,
                                "source_record_id": record["source_record_id"],
                                "error": str(exc),
                            },
                        ],
                    }
        run.report = {**run.report, "entities": report_entities}
        run.status = (
            "dry_run_complete"
            if dry_run
            else ("completed_with_errors" if run.failed_count else "completed")
        )
        run.finished_at = datetime.now(UTC)
        await self.session.flush()
        return run

    async def _apply_record(
        self,
        run: ProductionMigrationRun,
        entity: str,
        record: dict[str, Any],
        source_system: str,
        dry_run: bool,
    ) -> str:
        definition = ENTITY_DEFINITIONS[entity]
        source_id = record["source_record_id"]
        payload = dict(record["data"])
        if hasattr(definition.model, "source"):
            payload["source"] = source_system
        if hasattr(definition.model, "source_record_id"):
            payload["source_record_id"] = source_id
        fingerprint = self._fingerprint(payload)
        mapping = await self.session.scalar(
            select(ProductionMigrationRecordMap).where(
                ProductionMigrationRecordMap.source_system == source_system,
                ProductionMigrationRecordMap.entity == entity,
                ProductionMigrationRecordMap.source_record_id == source_id,
                ProductionMigrationRecordMap.is_deleted.is_(False),
            )
        )
        if mapping and mapping.fingerprint == fingerprint:
            return "skipped"
        if dry_run:
            return "updated" if mapping else "inserted"

        before_data = None
        before_fingerprint = None
        if mapping:
            target = await self.session.scalar(
                select(definition.model).where(
                    definition.model.id == mapping.target_id,
                    definition.model.is_deleted.is_(False),
                )
            )
            if not target:
                raise MigrationInputError("映射存在但目标记录不存在")
            before_data = self._snapshot(definition, target)
            before_fingerprint = mapping.fingerprint
            await self.session.execute(
                update(definition.model)
                .where(definition.model.id == mapping.target_id)
                .values(**payload)
            )
            mapping.fingerprint = fingerprint
            mapping.last_run_id = run.id
            action = "updated"
        else:
            target = definition.model(**payload)
            self.session.add(target)
            await self.session.flush()
            mapping = ProductionMigrationRecordMap(
                source_system=source_system,
                entity=entity,
                source_record_id=source_id,
                target_table=definition.model.__tablename__,
                target_id=target.id,
                fingerprint=fingerprint,
                last_run_id=run.id,
            )
            self.session.add(mapping)
            await self.session.flush()
            action = "inserted"
        self.session.add(
            ProductionMigrationChange(
                run_id=run.id,
                map_id=mapping.id,
                entity=entity,
                target_id=mapping.target_id,
                action=action,
                before_data=before_data,
                before_fingerprint=before_fingerprint,
                after_fingerprint=fingerprint,
            )
        )
        await self.session.flush()
        return action

    async def rollback(self, run_id: uuid.UUID, run_key: str) -> ProductionMigrationRun:
        source_run = await self.session.scalar(
            select(ProductionMigrationRun).where(ProductionMigrationRun.id == run_id)
        )
        if not source_run or source_run.mode != "import":
            raise MigrationInputError("仅能回滚已记录的正式导入批次")
        rollback_run = ProductionMigrationRun(
            run_key=run_key,
            source_system=source_run.source_system,
            mode="rollback",
            status="running",
            started_at=datetime.now(UTC),
            input_counts={},
            report={},
            rollback_of=source_run.id,
        )
        self.session.add(rollback_run)
        await self.session.flush()
        changes = list(
            (
                await self.session.execute(
                    select(ProductionMigrationChange)
                    .where(
                        ProductionMigrationChange.run_id == run_id,
                        ProductionMigrationChange.rolled_back_at.is_(None),
                    )
                    .order_by(ProductionMigrationChange.created_at.desc())
                )
            ).scalars()
        )
        for change in changes:
            definition = ENTITY_DEFINITIONS[change.entity]
            mapping = await self.session.get(
                ProductionMigrationRecordMap, change.map_id
            )
            if change.action == "inserted":
                await self.session.execute(
                    update(definition.model)
                    .where(definition.model.id == change.target_id)
                    .values(is_deleted=True)
                )
                if mapping:
                    mapping.is_deleted = True
            elif change.before_data is not None:
                restored = definition.schema.model_validate(
                    change.before_data
                ).model_dump()
                await self.session.execute(
                    update(definition.model)
                    .where(definition.model.id == change.target_id)
                    .values(**restored)
                )
                if mapping and change.before_fingerprint:
                    mapping.fingerprint = change.before_fingerprint
                    mapping.last_run_id = rollback_run.id
            change.rolled_back_at = datetime.now(UTC)
        rollback_run.updated_count = len(changes)
        rollback_run.status = "completed"
        rollback_run.finished_at = datetime.now(UTC)
        rollback_run.report = {"rolled_back_changes": len(changes)}
        await self.session.flush()
        return rollback_run

    async def reconcile(self, source_system: str) -> dict[str, Any]:
        report: dict[str, Any] = {}
        for entity, definition in ENTITY_DEFINITIONS.items():
            mappings = list(
                (
                    await self.session.execute(
                        select(ProductionMigrationRecordMap).where(
                            ProductionMigrationRecordMap.source_system == source_system,
                            ProductionMigrationRecordMap.entity == entity,
                            ProductionMigrationRecordMap.is_deleted.is_(False),
                        )
                    )
                ).scalars()
            )
            missing = 0
            for mapping in mappings:
                target_id = await self.session.scalar(
                    select(definition.model.id).where(
                        definition.model.id == mapping.target_id,
                        definition.model.is_deleted.is_(False),
                    )
                )
                if target_id is None:
                    missing += 1
            report[entity] = {"mapped": len(mappings), "missing_targets": missing}
        return report

    @staticmethod
    def _fingerprint(data: dict[str, Any]) -> str:
        canonical = json.dumps(
            data, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _snapshot(definition: EntityDefinition, target: OrmBaseModel) -> dict[str, Any]:
        values = {
            name: getattr(target, name)
            for name in definition.schema.model_fields
            if hasattr(target, name)
        }
        return definition.schema.model_validate(values).model_dump(mode="json")
