"""Business service for read-only Energy Wiki ingestion and analytics."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.modules.energy.feishu_client import (
    EnergyFeishuClient,
    EnergyFeishuRequestError,
)
from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergyFeishuSourceRoot,
    EnergyMetricFact,
    EnergySheetMapping,
    EnergySheetSnapshot,
    EnergySnapshotRow,
    EnergySyncRun,
    EnergyWikiDocument,
    EnergyWorkbookSheet,
)
from app.modules.energy.schemas import (
    SHEET_TITLE_DIMENSION,
    EnergyFeishuConfigResponse,
    EnergyFeishuConfigUpsert,
    EnergyFeishuConnectivityResult,
    EnergyFeishuConnectivityStep,
    EnergyFeishuSourceRootInput,
    EnergyFeishuSourceRootResponse,
    EnergyMappingMetricInput,
    EnergyMappingPreviewResponse,
    EnergyMappingPreviewRow,
    EnergyOverviewResponse,
    EnergySheetMappingUpsert,
)
from app.modules.energy.wiki_repository import EnergyWikiRepository
from app.modules.warehouse.feishu_client import (
    WarehouseFeishuClient,
    parse_feishu_root_token,
)
from app.platform.integrations.feishu.auth import FeishuAuth

logger = logging.getLogger(__name__)
CST = ZoneInfo("Asia/Shanghai")


class EnergyWikiService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = EnergyWikiRepository(session)

    async def get_config(self) -> EnergyFeishuConfigResponse:
        config = await self.repo.get_config()
        if config is None:
            return EnergyFeishuConfigResponse(
                config_name="能源 Wiki 数据源",
                app_id="",
                app_secret_configured=False,
                app_secret_masked="",
                root_wiki_url="",
                root_wiki_token=None,
                timezone="Asia/Shanghai",
                daily_sync_time="02:00",
                is_active=False,
                last_successful_sync_date=None,
                sync_status="pending",
                sync_error=None,
                remark=None,
            )
        return self._config_response(config)

    async def save_config(
        self, data: EnergyFeishuConfigUpsert
    ) -> EnergyFeishuConfigResponse:
        config = await self.repo.get_config()
        root_token = (
            EnergyFeishuClient.parse_wiki_token(data.root_wiki_url)
            if data.root_wiki_url.strip()
            else None
        )
        if config is None:
            if not data.app_secret:
                raise AppException(message="首次保存飞书配置必须填写 App Secret")
            config = EnergyFeishuConfig(
                config_name=data.config_name,
                app_id=data.app_id,
                encrypted_app_secret=encrypt_secret(data.app_secret),
                root_wiki_url=data.root_wiki_url,
                root_wiki_token=root_token,
                timezone=data.timezone,
                daily_sync_time=data.daily_sync_time,
                is_active=data.is_active,
                remark=data.remark,
            )
        else:
            config.config_name = data.config_name
            config.app_id = data.app_id
            if data.app_secret:
                config.encrypted_app_secret = encrypt_secret(data.app_secret)
            config.root_wiki_url = data.root_wiki_url
            config.root_wiki_token = root_token
            config.timezone = data.timezone
            config.daily_sync_time = data.daily_sync_time
            config.is_active = data.is_active
            config.remark = data.remark
            config.sync_error = None
        await self.repo.save_config(config)
        if data.root_wiki_url.strip() and not await self.repo.list_source_roots(
            config.id
        ):
            await self.repo.save_source_root(
                EnergyFeishuSourceRoot(
                    config_id=config.id,
                    name="默认 Wiki 入口",
                    source_type="wiki",
                    source_url=data.root_wiki_url,
                    root_token=root_token or "",
                    is_active=True,
                    discovery_status="pending",
                )
            )
        await self.session.commit()
        stored = await self.repo.get_config()
        assert stored is not None
        return self._config_response(stored)

    async def list_source_roots(self) -> list[EnergyFeishuSourceRootResponse]:
        config = await self._config_or_raise()
        return [
            EnergyFeishuSourceRootResponse.model_validate(item)
            for item in await self.repo.list_source_roots(config.id)
        ]

    async def create_source_root(
        self, data: EnergyFeishuSourceRootInput
    ) -> EnergyFeishuSourceRootResponse:
        config = await self._config_or_raise()
        root = EnergyFeishuSourceRoot(
            config_id=config.id,
            name=data.name.strip(),
            source_type=data.source_type,
            source_url=data.source_url.strip(),
            root_token=parse_feishu_root_token(data.source_url, data.source_type),
            is_active=data.is_active,
            discovery_status="pending",
        )
        await self.repo.save_source_root(root)
        await self.session.commit()
        return EnergyFeishuSourceRootResponse.model_validate(root)

    async def delete_source_root(self, root_id: UUID) -> None:
        root = await self.repo.get_source_root(root_id)
        if root is None:
            raise AppException(message="能源飞书数据入口不存在", status_code=404)
        root.is_deleted = True
        root.is_active = False
        await self.session.commit()

    async def test_connectivity(self) -> EnergyFeishuConnectivityResult:
        config = await self._config_or_raise()
        steps: list[EnergyFeishuConnectivityStep] = []
        try:
            roots = [
                item
                for item in await self.repo.list_source_roots(config.id)
                if item.is_active
            ]
            root = roots[0] if roots else None
            if root is None:
                await FeishuAuth.get_tenant_access_token(
                    config.app_id,
                    decrypt_secret(config.encrypted_app_secret),
                )
                steps.append(
                    EnergyFeishuConnectivityStep(
                        name="应用凭据",
                        status="ok",
                        message=(
                            "App ID / Secret 认证成功；"
                            "请继续添加 Wiki 或多维表格入口"
                        ),
                    )
                )
                return EnergyFeishuConnectivityResult(ok=True, steps=steps)
            if root.source_type == "base":
                tables = await WarehouseFeishuClient(
                    app_id=config.app_id,
                    app_secret=decrypt_secret(config.encrypted_app_secret),
                    app_token=root.root_token,
                ).list_tables(page_size=100)
                steps.append(
                    EnergyFeishuConnectivityStep(
                        name="应用凭据与多维表格",
                        status="ok",
                        message=f"可读取 {len(tables)} 张数据表",
                    )
                )
                return EnergyFeishuConnectivityResult(ok=True, steps=steps)
            client = self._client_for(config)
            root_token = root.root_token
            node = await client.get_wiki_node(root_token)
            steps.append(
                EnergyFeishuConnectivityStep(
                    name="应用凭据与 Wiki 根节点",
                    status="ok",
                    message=f"已读取节点：{node.get('title') or root_token}",
                )
            )
            space_id = str(node.get("space_id") or "")
            if node.get("has_child") and space_id:
                children = await client.list_child_nodes(
                    space_id=space_id,
                    parent_node_token=str(node.get("node_token") or root_token),
                )
                steps.append(
                    EnergyFeishuConnectivityStep(
                        name="Wiki 子节点读取",
                        status="ok",
                        message=f"可读取 {len(children)} 个直接子节点",
                    )
                )
            document_token = str(node.get("obj_token") or "")
            if str(node.get("obj_type") or "") == "sheet" and document_token:
                sheets = await client.list_workbook_sheets(document_token)
                steps.append(
                    EnergyFeishuConnectivityStep(
                        name="电子表格读取",
                        status="ok",
                        message=f"可读取 {len(sheets)} 个工作表",
                    )
                )
            else:
                steps.append(
                    EnergyFeishuConnectivityStep(
                        name="电子表格读取",
                        status="warning",
                        message="根节点不是电子表格，将在后代节点中继续发现月度表",
                    )
                )
        except Exception as exc:
            steps.append(
                EnergyFeishuConnectivityStep(
                    name="飞书连通性",
                    status="error",
                    message=self._safe_error(exc),
                )
            )
        return EnergyFeishuConnectivityResult(
            ok=bool(steps) and all(step.status != "error" for step in steps),
            steps=steps,
        )

    async def trigger_sync(self, *, force: bool = False) -> EnergySyncRun:
        config = await self._config_or_raise()
        if not config.is_active:
            raise AppException(message="能源 Wiki 同步配置已停用")
        suffix = "force" if force else "manual"
        run = EnergySyncRun(
            config_id=config.id,
            idempotency_key=f"energy:wiki:{suffix}:{uuid4()}",
            trigger_type="manual",
        )
        await self.repo.save_sync_run(run)
        await self.session.commit()
        await self.execute_sync(run.id)
        refreshed = await self.repo.get_sync_run_by_key(run.idempotency_key)
        assert refreshed is not None
        return refreshed

    async def execute_sync(self, run_id: UUID) -> EnergySyncRun:
        run = await self.session.get(EnergySyncRun, run_id)
        if run is None or run.is_deleted:
            raise AppException(message="同步运行不存在", status_code=404)
        config = await self.repo.get_config_by_id(run.config_id)
        if config is None:
            raise AppException(message="同步配置不存在", status_code=404)
        if run.status == "success":
            return run

        run.status = "running"
        run.error_message = None
        run.claimed_at = datetime.now(UTC)
        await self.session.commit()
        try:
            client = self._client_for(config)
            roots = [
                item
                for item in await self.repo.list_source_roots(config.id)
                if item.is_active
            ]
            if not roots and config.root_wiki_url.strip():
                roots = [
                    EnergyFeishuSourceRoot(
                        config_id=config.id,
                        name="兼容旧 Wiki 入口",
                        source_type="wiki",
                        source_url=config.root_wiki_url,
                        root_token=config.root_wiki_token
                        or EnergyFeishuClient.parse_wiki_token(config.root_wiki_url),
                        is_active=True,
                    )
                ]
            for root in roots:
                try:
                    if root.source_type == "base":
                        await self._sync_bitable_root(config, root, run)
                    else:
                        nodes = await client.discover_tree(root.root_token)
                        for node in nodes:
                            if str(node.get("obj_type") or "") != "sheet":
                                continue
                            document_token = str(node.get("obj_token") or "")
                            if not document_token:
                                continue
                            document = await self._upsert_document(
                                config, node, document_token
                            )
                            run.document_count += 1
                            (
                                sheet_count,
                                snapshot_count,
                                fact_count,
                            ) = await self._sync_document(
                                client=client, document=document, run=run
                            )
                            run.sheet_count += sheet_count
                            run.snapshot_count += snapshot_count
                            run.fact_count += fact_count
                            document.last_synced_at = datetime.now(UTC)
                    root.discovery_status = "success"
                    root.last_discovered_at = datetime.now(UTC)
                    root.discovery_error = None
                except Exception as exc:
                    run.error_count += 1
                    root.discovery_status = "failed"
                    root.discovery_error = self._safe_error(exc)
                    logger.exception("能源飞书入口同步失败: %s", root.name)
                    run.error_message = self._join_error(
                        run.error_message, self._safe_error(exc)
                    )
            run.completed_at = datetime.now(UTC)
            run.status = "success" if run.error_count == 0 else "partial"
            config.sync_status = run.status
            config.sync_error = run.error_message
            if run.status == "success":
                config.last_successful_sync_date = datetime.now(CST).date()
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            run = await self.session.get(EnergySyncRun, run_id)
            config = await self.repo.get_config_by_id(run.config_id) if run else None
            if run:
                run.status = "failed"
                run.completed_at = datetime.now(UTC)
                run.error_count += 1
                run.error_message = self._safe_error(exc)
            if config:
                config.sync_status = "failed"
                config.sync_error = self._safe_error(exc)
            await self.session.commit()
        latest = await self.session.get(EnergySyncRun, run_id)
        assert latest is not None
        return latest

    async def list_sync_runs(
        self, *, page: int, page_size: int
    ) -> tuple[list[EnergySyncRun], int]:
        config = await self._config_or_raise()
        return await self.repo.list_sync_runs(
            config_id=config.id, page=page, page_size=page_size
        )

    async def list_sources(
        self,
        *,
        period_month: str | None = None,
        mapping_status: str | None = None,
    ) -> list[tuple[EnergyWorkbookSheet, EnergyWikiDocument]]:
        config = await self._config_or_raise()
        return await self.repo.list_sheets(
            config_id=config.id,
            period_month=period_month,
            mapping_status=mapping_status,
        )

    async def list_documents(
        self, *, period_month: str | None
    ) -> list[EnergyWikiDocument]:
        config = await self._config_or_raise()
        return await self.repo.list_documents(
            config_id=config.id, period_month=period_month
        )

    async def get_sheet_or_raise(self, sheet_id: UUID) -> EnergyWorkbookSheet:
        sheet = await self.repo.get_sheet_by_id(sheet_id)
        if sheet is None:
            raise AppException(message="来源工作表不存在", status_code=404)
        return sheet

    async def list_snapshots(self, sheet_id: UUID) -> list[EnergySheetSnapshot]:
        await self.get_sheet_or_raise(sheet_id)
        return await self.repo.list_snapshots(sheet_id)

    async def list_snapshot_rows(
        self, *, snapshot_id: UUID, page: int, page_size: int
    ) -> tuple[EnergySheetSnapshot, list[EnergySnapshotRow], int]:
        snapshot = await self.repo.get_snapshot(snapshot_id)
        if snapshot is None:
            raise AppException(message="快照不存在", status_code=404)
        rows, total = await self.repo.list_snapshot_rows(
            snapshot_id=snapshot_id, page=page, page_size=page_size
        )
        return snapshot, rows, total

    async def get_mapping(self, sheet_id: UUID) -> EnergySheetMapping | None:
        await self.get_sheet_or_raise(sheet_id)
        return await self.repo.get_current_mapping(sheet_id)

    async def preview_mapping(
        self, sheet_id: UUID, data: EnergySheetMappingUpsert
    ) -> EnergyMappingPreviewResponse:
        if not data.is_enabled:
            raise AppException(
                message="仅归档的工作表无需预览；请先启用分析并配置字段映射"
            )
        sheet = await self.get_sheet_or_raise(sheet_id)
        snapshot = await self.repo.get_latest_snapshot(sheet.id)
        if snapshot is None:
            raise AppException(message="请先同步该工作表后再配置映射")
        rows = await self.repo.list_all_snapshot_rows(snapshot.id)
        parsed, errors = self._parse_rows(
            snapshot_rows=rows,
            mapping=data,
            sheet=sheet,
            mapping_id=uuid4(),
            snapshot_id=snapshot.id,
            mapping_version=1,
            preview=True,
        )
        previews = [
            EnergyMappingPreviewRow(
                row_index=item["row_index"],
                values=item["values"],
                errors=item["errors"],
            )
            for item in parsed[:20]
        ]
        invalid_row_indexes = {item["row_index"] for item in parsed if item["errors"]}
        valid_row_indexes = {
            item["row_index"]
            for item in parsed
            if item["values"] and not item["errors"]
        } - invalid_row_indexes
        return EnergyMappingPreviewResponse(
            valid_row_count=len(valid_row_indexes),
            invalid_row_count=len(invalid_row_indexes) or len(errors),
            rows=previews,
        )

    async def save_mapping(
        self, sheet_id: UUID, data: EnergySheetMappingUpsert
    ) -> EnergySheetMapping:
        sheet = await self.get_sheet_or_raise(sheet_id)
        current = await self.repo.get_current_mapping(sheet.id)
        version = (current.version + 1) if current else 1
        if current:
            current.is_current = False
        mapping = EnergySheetMapping(
            sheet_id=sheet.id,
            version=version,
            is_current=True,
            is_enabled=data.is_enabled,
            source_role=data.source_role,
            schema_hash=sheet.schema_hash,
            header_row=data.header_row,
            date_column=data.date_column,
            date_format=data.date_format,
            dimensions=data.dimensions,
            metrics=[metric.model_dump(mode="json") for metric in data.metrics],
        )
        await self.repo.save_mapping(mapping)
        sheet.header_row = data.header_row
        sheet.mapping_status = "mapped" if data.is_enabled else "unmapped"
        await self.session.flush()
        await self._rebuild_mapping_facts(mapping, sheet)
        await self.session.commit()
        refreshed = await self.repo.get_current_mapping(sheet.id)
        assert refreshed is not None
        return refreshed

    async def get_overview(
        self,
        *,
        start: datetime,
        end: datetime,
        energy_type: str | None,
        group_by: str | None,
        source_scope: str = "detail",
        workshop: str | None = None,
        source_sheet_title: str | None = None,
    ) -> EnergyOverviewResponse:
        if start.tzinfo is None:
            start = start.replace(tzinfo=CST)
        if end.tzinfo is None:
            end = end.replace(tzinfo=CST)
        facts = await self.repo.list_current_facts(
            start=start,
            end=end,
            energy_type=energy_type,
            source_scope=source_scope,
            workshop=workshop,
            source_sheet_title=source_sheet_title,
        )
        direct: list[EnergyMetricFact] = []
        cumulative: list[EnergyMetricFact] = []
        for fact in facts:
            if fact.value_semantics == "cumulative":
                cumulative.append(fact)
            elif start <= fact.observed_at <= end:
                direct.append(fact)

        preserve_metric_key = source_scope != "detail"
        metric_totals: dict[tuple[str | None, str, str], Decimal] = defaultdict(Decimal)
        trend_totals: dict[tuple[date, str | None, str, str], Decimal] = defaultdict(
            Decimal
        )
        distribution_totals: dict[tuple[str, str | None, str, str], Decimal] = (
            defaultdict(Decimal)
        )
        record_counts: dict[tuple[str | None, str, str], int] = defaultdict(int)
        latest_by_metric: dict[tuple[str, str, str], EnergyMetricFact] = {}
        invalid_count = 0

        for fact in direct:
            latest_key = (fact.metric_key, fact.energy_type, fact.unit)
            previous = latest_by_metric.get(latest_key)
            if previous is None or fact.observed_at > previous.observed_at:
                latest_by_metric[latest_key] = fact
            if self._is_ratio_metric(fact):
                continue
            metric_key = fact.metric_key if preserve_metric_key else None
            key = (metric_key, fact.energy_type, fact.unit)
            metric_totals[key] += fact.value
            record_counts[key] += 1
            trend_totals[(fact.observed_at.astimezone(CST).date(), *key)] += fact.value
            distribution_key = self._distribution_key(fact, group_by)
            distribution_totals[(distribution_key, *key)] += fact.value

        cumulative_groups: dict[tuple[str, str, str, str], list[EnergyMetricFact]] = (
            defaultdict(list)
        )
        for fact in cumulative:
            meter_key = fact.meter_key or "__missing_meter__"
            cumulative_groups[
                (fact.energy_type, fact.unit, fact.metric_key, meter_key)
            ].append(fact)
        for (
            fact_type,
            unit,
            cumulative_metric_key,
            _meter_key,
        ), items in cumulative_groups.items():
            items.sort(key=lambda item: item.observed_at)
            before = [item for item in items if item.observed_at < start]
            within = [item for item in items if start <= item.observed_at <= end]
            if not within:
                continue
            baseline = before[-1] if before else within[0]
            ending = within[-1]
            delta = ending.value - baseline.value
            if delta < 0:
                invalid_count += 1
                continue
            metric_key = cumulative_metric_key if preserve_metric_key else None
            key = (metric_key, fact_type, unit)
            metric_totals[key] += delta
            record_counts[key] += len(within)
            trend_totals[(ending.observed_at.astimezone(CST).date(), *key)] += delta
            distribution_key = self._distribution_key(ending, group_by)
            distribution_totals[(distribution_key, *key)] += delta

        from app.modules.energy.schemas import (
            EnergyOverviewDistributionPoint,
            EnergyOverviewLatestMetric,
            EnergyOverviewMetric,
            EnergyOverviewTrendPoint,
        )

        return EnergyOverviewResponse(
            source_scope=source_scope,
            metrics=[
                EnergyOverviewMetric(
                    metric_key=metric_key,
                    energy_type=energy,
                    unit=unit,
                    total_value=float(value),
                    record_count=record_counts[(metric_key, energy, unit)],
                )
                for (metric_key, energy, unit), value in sorted(
                    metric_totals.items(),
                    key=lambda item: (item[0][1], item[0][2], item[0][0] or ""),
                )
            ],
            trend=[
                EnergyOverviewTrendPoint(
                    date=day,
                    metric_key=metric_key,
                    energy_type=energy,
                    unit=unit,
                    value=float(value),
                )
                for (day, metric_key, energy, unit), value in sorted(
                    trend_totals.items(),
                    key=lambda item: (
                        item[0][0],
                        item[0][2],
                        item[0][3],
                        item[0][1] or "",
                    ),
                )
            ],
            distribution=[
                EnergyOverviewDistributionPoint(
                    key=key,
                    metric_key=metric_key,
                    energy_type=energy,
                    unit=unit,
                    value=float(value),
                )
                for (key, metric_key, energy, unit), value in sorted(
                    distribution_totals.items(),
                    key=lambda item: (
                        item[0][0],
                        item[0][2],
                        item[0][3],
                        item[0][1] or "",
                    ),
                )
            ],
            latest_metrics=[
                EnergyOverviewLatestMetric(
                    metric_key=metric_key,
                    energy_type=energy,
                    unit=unit,
                    value=float(fact.value),
                    observed_at=fact.observed_at,
                )
                for (metric_key, energy, unit), fact in sorted(
                    latest_by_metric.items(),
                    key=lambda item: (item[0][1], item[0][2], item[0][0]),
                )
            ],
            last_observed_at=max((fact.observed_at for fact in direct), default=None),
            invalid_count=invalid_count,
        )

    async def run_scheduled_sync_if_due(self) -> None:
        config = await self.repo.lock_active_config()
        if config is None:
            return
        local_now = datetime.now(ZoneInfo(config.timezone))
        hour, minute = (int(value) for value in config.daily_sync_time.split(":"))
        due_at = datetime.combine(
            local_now.date(), time(hour, minute), tzinfo=local_now.tzinfo
        )
        if local_now < due_at or config.last_successful_sync_date == local_now.date():
            return
        key = f"energy:wiki:scheduled:{local_now.date().isoformat()}"
        existing = await self.repo.get_sync_run_by_key(key)
        if existing and existing.status in {"running", "success", "partial"}:
            return
        run = existing or EnergySyncRun(
            config_id=config.id,
            idempotency_key=key,
            trigger_type="scheduled",
            scheduled_for=due_at,
        )
        if not existing:
            await self.repo.save_sync_run(run)
            await self.session.commit()
        await self.execute_sync(run.id)

    async def _upsert_document(
        self, config: EnergyFeishuConfig, node: dict[str, Any], document_token: str
    ) -> EnergyWikiDocument:
        node_token = str(node.get("node_token") or "")
        if not node_token:
            raise RuntimeError("发现的 Wiki 节点缺少 node_token")
        path = [
            {
                "token": str(item.get("token") or ""),
                "title": str(item.get("title") or ""),
            }
            for item in node.get("node_path", [])
            if isinstance(item, dict)
        ]
        period = self._period_from_path(path)
        document = await self.repo.get_document(
            config_id=config.id, wiki_node_token=node_token
        )
        fields = {
            "parent_node_token": str(node.get("parent_node_token") or "") or None,
            "space_id": str(node.get("space_id") or "") or None,
            "object_type": str(node.get("obj_type") or "sheet"),
            "document_token": document_token,
            "title": str(node.get("title") or node_token),
            "node_path": path,
            "period_month": period,
            "classification_status": "monthly" if period else "unclassified",
        }
        if document is None:
            document = EnergyWikiDocument(
                config_id=config.id, wiki_node_token=node_token, **fields
            )
        else:
            for key, value in fields.items():
                setattr(document, key, value)
            document.is_deleted = False
        return await self.repo.save_document(document)

    async def _sync_document(
        self,
        *,
        client: EnergyFeishuClient,
        document: EnergyWikiDocument,
        run: EnergySyncRun,
    ) -> tuple[int, int, int]:
        if not document.document_token:
            return 0, 0, 0
        raw_sheets = await client.list_workbook_sheets(document.document_token)
        sheet_count = snapshot_count = fact_count = 0
        for raw_sheet in raw_sheets:
            title = str(
                raw_sheet.get("title")
                or raw_sheet.get("name")
                or raw_sheet.get("sheet_id")
                or raw_sheet.get("id")
                or "未知工作表"
            )
            try:
                async with self.session.begin_nested():
                    counts = await self._sync_workbook_sheet(
                        client=client,
                        document=document,
                        run=run,
                        raw_sheet=raw_sheet,
                    )
                sheet_count += counts[0]
                snapshot_count += counts[1]
                fact_count += counts[2]
            except Exception as exc:
                run.error_count = (run.error_count or 0) + 1
                run.error_message = self._join_error(
                    run.error_message, f"{title}：{self._safe_error(exc)}"
                )
                logger.exception(
                    "能源 Wiki 工作表同步失败: %s / %s", document.title, title
                )
        await self.session.flush()
        return sheet_count, snapshot_count, fact_count

    async def _sync_bitable_root(
        self,
        config: EnergyFeishuConfig,
        root: EnergyFeishuSourceRoot,
        run: EnergySyncRun,
    ) -> None:
        client = WarehouseFeishuClient(
            app_id=config.app_id,
            app_secret=decrypt_secret(config.encrypted_app_secret),
            app_token=root.root_token,
        )
        document = await self._upsert_document(
            config,
            {
                "node_token": f"base:{root.root_token}",
                "obj_type": "bitable",
                "title": root.name,
                "node_path": [{"token": root.root_token, "title": root.name}],
            },
            root.root_token,
        )
        run.document_count += 1
        for index, raw_table in enumerate(await client.list_tables()):
            table_id = str(raw_table.get("table_id") or "")
            if not table_id:
                continue
            raw_fields = await client.list_fields(table_id)
            headers = [
                str(item.get("field_name") or item.get("name") or item.get("field_id"))
                for item in raw_fields
            ]
            records: list[dict[str, Any]] = []
            page_token: str | None = None
            expected_total: int | None = None
            while True:
                page_data = await client.search_records(
                    table_id, page_size=500, page_token=page_token
                )
                records.extend(page_data.get("items") or [])
                if page_data.get("total") is not None:
                    expected_total = int(page_data["total"])
                if not page_data.get("has_more"):
                    break
                page_token = str(page_data.get("page_token") or "")
                if not page_token:
                    raise RuntimeError("能源 Base 分页链缺少 page_token")
            unique_records = {
                str(item.get("record_id")): item
                for item in records
                if item.get("record_id")
            }
            if expected_total is not None and len(unique_records) != expected_total:
                raise RuntimeError(
                    f"能源 Base 完整性校验失败：应有 {expected_total} 条，"
                    f"实际 {len(unique_records)} 条"
                )
            values = [headers] + [
                [dict(item.get("fields") or {}).get(header) for header in headers]
                for item in unique_records.values()
            ]
            counts = await self._store_tabular_values(
                document=document,
                run=run,
                external_id=table_id,
                title=str(raw_table.get("name") or table_id),
                sheet_index=index,
                grid_properties={
                    "row_count": len(values),
                    "column_count": len(headers),
                },
                values=values,
                display_values=values,
                revision=str(raw_table.get("revision") or "") or None,
            )
            run.sheet_count += counts[0]
            run.snapshot_count += counts[1]
            run.fact_count += counts[2]
        document.last_synced_at = datetime.now(UTC)

    async def _sync_workbook_sheet(
        self,
        *,
        client: EnergyFeishuClient,
        document: EnergyWikiDocument,
        run: EnergySyncRun,
        raw_sheet: dict[str, Any],
    ) -> tuple[int, int, int]:
        assert document.document_token is not None
        external_id = str(raw_sheet.get("sheet_id") or raw_sheet.get("id") or "")
        if not external_id:
            return 0, 0, 0
        title = str(raw_sheet.get("title") or raw_sheet.get("name") or external_id)
        grid_properties = dict(raw_sheet.get("grid_properties") or {})
        row_count = grid_properties.get("row_count")
        column_count = grid_properties.get("column_count")
        values: list[list[Any]] = []
        display_values: list[list[Any]] = []
        revision: str | None = None
        display_revision: str | None = None
        for attempt in range(2):
            values, revision = await client.read_sheet_values(
                spreadsheet_token=document.document_token,
                sheet_id=external_id,
                row_count=row_count if isinstance(row_count, int) else None,
                column_count=column_count if isinstance(column_count, int) else None,
            )
            display_values, display_revision = await client.read_sheet_values(
                spreadsheet_token=document.document_token,
                sheet_id=external_id,
                row_count=row_count if isinstance(row_count, int) else None,
                column_count=column_count if isinstance(column_count, int) else None,
                value_render_option="FormattedValue",
            )
            if not revision or not display_revision or revision == display_revision:
                break
            if attempt == 1:
                raise RuntimeError("飞书工作表在读取期间发生变化，未发布不一致的镜像")
        return await self._store_tabular_values(
            document=document,
            run=run,
            external_id=external_id,
            title=title,
            sheet_index=int(raw_sheet.get("index") or 0),
            grid_properties=grid_properties,
            values=values,
            display_values=display_values,
            revision=display_revision or revision,
        )

    async def _store_tabular_values(
        self,
        *,
        document: EnergyWikiDocument,
        run: EnergySyncRun,
        external_id: str,
        title: str,
        sheet_index: int,
        grid_properties: dict[str, Any],
        values: list[list[Any]],
        display_values: list[list[Any]],
        revision: str | None,
    ) -> tuple[int, int, int]:
        existing = await self.repo.get_sheet(
            document_id=document.id, external_sheet_id=external_id
        )
        header_row = existing.header_row if existing else 1
        headers = self._header_values(values, header_row)
        schema_hash = self._hash(headers)
        if existing is None:
            sheet = EnergyWorkbookSheet(
                document_id=document.id,
                external_sheet_id=external_id,
                title=title,
                sheet_index=sheet_index,
                grid_properties=grid_properties,
                header_row=header_row,
                headers=headers,
                schema_hash=schema_hash,
            )
        else:
            sheet = existing
            sheet.title = title
            sheet.sheet_index = sheet_index
            sheet.grid_properties = grid_properties
            sheet.headers = headers
            if sheet.schema_hash and sheet.schema_hash != schema_hash:
                sheet.mapping_status = "needs_mapping"
            sheet.schema_hash = schema_hash
            sheet.is_deleted = False
        await self.repo.save_sheet(sheet)
        await self._inherit_mapping_if_possible(sheet)

        content_hash = self._hash({"values": values, "display_values": display_values})
        latest = await self.repo.get_latest_snapshot(sheet.id)
        if latest and latest.content_hash == content_hash:
            sheet.last_synced_at = datetime.now(UTC)
            return 1, 0, 0

        snapshot = EnergySheetSnapshot(
            sheet_id=sheet.id,
            sync_run_id=run.id,
            snapshot_number=await self.repo.next_snapshot_number(sheet.id),
            source_revision=revision,
            content_hash=content_hash,
            header_values=headers,
            row_count=len(values),
        )
        await self.repo.save_snapshot(snapshot)
        await self.repo.add_snapshot_rows(
            [
                EnergySnapshotRow(
                    snapshot_id=snapshot.id,
                    row_index=index,
                    values=row,
                    display_values=(
                        display_values[index - 1]
                        if index <= len(display_values)
                        else None
                    ),
                    row_hash=self._hash(row),
                )
                for index, row in enumerate(values, start=1)
            ]
        )
        sheet.latest_snapshot_id = snapshot.id
        sheet.latest_content_hash = content_hash
        sheet.last_synced_at = datetime.now(UTC)
        mapping = await self.repo.get_current_mapping(sheet.id)
        fact_count = 0
        if mapping and mapping.is_enabled and mapping.schema_hash == schema_hash:
            fact_count = await self._build_snapshot_facts(mapping, sheet, snapshot)
            sheet.mapping_status = "mapped"
        elif mapping:
            sheet.mapping_status = "needs_mapping"
        else:
            sheet.mapping_status = "unmapped"
        return 1, 1, fact_count

    async def _inherit_mapping_if_possible(self, sheet: EnergyWorkbookSheet) -> None:
        if not sheet.schema_hash or await self.repo.get_current_mapping(sheet.id):
            return
        candidates = await self.repo.list_current_mappings_by_schema(sheet.schema_hash)
        template = next(
            (candidate for candidate in candidates if candidate.sheet_id != sheet.id),
            None,
        )
        if template is None:
            return
        inherited = EnergySheetMapping(
            sheet_id=sheet.id,
            version=1,
            is_current=True,
            is_enabled=True,
            source_role=template.source_role,
            schema_hash=sheet.schema_hash,
            header_row=template.header_row,
            date_column=template.date_column,
            date_format=template.date_format,
            dimensions=dict(template.dimensions),
            metrics=list(template.metrics),
        )
        await self.repo.save_mapping(inherited)
        sheet.header_row = inherited.header_row
        sheet.mapping_status = "mapped"

    async def _rebuild_mapping_facts(
        self, mapping: EnergySheetMapping, sheet: EnergyWorkbookSheet
    ) -> None:
        snapshots = await self.repo.list_snapshots(sheet.id)
        for snapshot in snapshots:
            await self._build_snapshot_facts(mapping, sheet, snapshot)

    async def _build_snapshot_facts(
        self,
        mapping: EnergySheetMapping,
        sheet: EnergyWorkbookSheet,
        snapshot: EnergySheetSnapshot,
    ) -> int:
        rows = await self.repo.list_all_snapshot_rows(snapshot.id)
        data = EnergySheetMappingUpsert(
            is_enabled=mapping.is_enabled,
            source_role=mapping.source_role,
            header_row=mapping.header_row,
            date_column=mapping.date_column,
            date_format=mapping.date_format,
            dimensions=dict(mapping.dimensions),
            metrics=[
                EnergyMappingMetricInput.model_validate(item)
                for item in mapping.metrics
            ],
        )
        parsed, _errors = self._parse_rows(
            snapshot_rows=rows,
            mapping=data,
            sheet=sheet,
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            mapping_version=mapping.version,
            preview=False,
        )
        facts = [item["fact"] for item in parsed if item.get("fact")]
        if facts:
            await self.repo.add_facts(facts)
        return len(facts)

    def _parse_rows(
        self,
        *,
        snapshot_rows: list[EnergySnapshotRow],
        mapping: EnergySheetMappingUpsert,
        sheet: EnergyWorkbookSheet,
        mapping_id: UUID,
        snapshot_id: UUID,
        mapping_version: int,
        preview: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        rows_by_index = {row.row_index: row.values for row in snapshot_rows}
        headers = self._header_values(rows_by_index.get(mapping.header_row, []))
        columns = {header: index for index, header in enumerate(headers) if header}
        errors: list[str] = []
        results: list[dict[str, Any]] = []
        required = [mapping.date_column or ""]
        required.extend(metric.value_column for metric in mapping.metrics)
        missing = [column for column in required if column and column not in columns]
        if missing:
            return [], [f"映射列不存在：{', '.join(missing)}"]
        for row_index, raw_values in sorted(rows_by_index.items()):
            if row_index <= mapping.header_row:
                continue
            values = list(raw_values)
            if not any(value not in (None, "") for value in values):
                continue
            row_errors: list[str] = []
            try:
                observed_at = self._parse_datetime(
                    self._cell(values, columns[mapping.date_column or ""]),
                    mapping.date_format,
                )
            except ValueError as exc:
                errors.append(f"第 {row_index} 行：{exc}")
                results.append(
                    {"row_index": row_index, "values": {}, "errors": [str(exc)]}
                )
                continue
            dimension_values = {
                label: (
                    sheet.title
                    if column == SHEET_TITLE_DIMENSION
                    else str(self._cell(values, columns[column]) or "")
                )
                for label, column in mapping.dimensions.items()
                if column == SHEET_TITLE_DIMENSION or column in columns
            }
            for metric in mapping.metrics:
                try:
                    value = self._parse_decimal(
                        self._cell(values, columns[metric.value_column])
                    )
                    unit = metric.unit or str(
                        self._cell(values, columns[metric.unit_column or ""]) or ""
                    )
                    if not unit:
                        raise ValueError("单位为空")
                    meter_key = (
                        str(self._cell(values, columns[metric.meter_key_column]) or "")
                        if metric.meter_key_column
                        and metric.meter_key_column in columns
                        else None
                    )
                    if metric.value_semantics == "cumulative" and not meter_key:
                        raise ValueError("累计表底的计量点为空")
                    fact = EnergyMetricFact(
                        mapping_id=mapping_id,
                        mapping_version=mapping_version,
                        sheet_id=sheet.id,
                        snapshot_id=snapshot_id,
                        metric_key=metric.metric_key,
                        source_row_index=row_index,
                        observed_at=observed_at,
                        energy_type=metric.energy_type,
                        unit=unit,
                        meter_key=meter_key,
                        value_semantics=metric.value_semantics,
                        value=value,
                        dimensions=dimension_values,
                    )
                    results.append(
                        {
                            "row_index": row_index,
                            "values": {
                                "metric_key": metric.metric_key,
                                "observed_at": observed_at.isoformat(),
                                "value": float(value),
                                "unit": unit,
                            },
                            "errors": row_errors,
                            "fact": None if preview else fact,
                        }
                    )
                except ValueError as exc:
                    message = f"{metric.metric_key}：{exc}"
                    row_errors.append(message)
                    errors.append(f"第 {row_index} 行：{message}")
            if row_errors:
                results.append(
                    {"row_index": row_index, "values": {}, "errors": row_errors}
                )
        return results, errors

    async def _config_or_raise(self) -> EnergyFeishuConfig:
        config = await self.repo.get_config()
        if config is None:
            raise AppException(message="请先保存能源 Wiki 飞书配置", status_code=404)
        return config

    @staticmethod
    def _client_for(config: EnergyFeishuConfig) -> EnergyFeishuClient:
        return EnergyFeishuClient(
            app_id=config.app_id,
            app_secret=decrypt_secret(config.encrypted_app_secret),
        )

    @staticmethod
    def _config_response(config: EnergyFeishuConfig) -> EnergyFeishuConfigResponse:
        secret = decrypt_secret(config.encrypted_app_secret)
        return EnergyFeishuConfigResponse(
            id=str(config.id),
            config_name=config.config_name,
            app_id=config.app_id,
            app_secret_configured=bool(config.encrypted_app_secret),
            app_secret_masked=mask_secret(secret),
            root_wiki_url=config.root_wiki_url,
            root_wiki_token=config.root_wiki_token,
            timezone=config.timezone,
            daily_sync_time=config.daily_sync_time,
            is_active=config.is_active,
            last_successful_sync_date=config.last_successful_sync_date,
            sync_status=config.sync_status,
            sync_error=config.sync_error,
            remark=config.remark,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    @staticmethod
    def _hash(value: Any) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _header_values(values: list[Any], header_row: int | None = None) -> list[str]:
        header_values = values
        if header_row is not None:
            if len(values) < header_row:
                return []
            header_values = values[header_row - 1]
        return [
            str(value).strip() if value is not None else "" for value in header_values
        ]

    @staticmethod
    def _cell(values: list[Any], index: int) -> Any:
        return values[index] if index < len(values) else None

    @staticmethod
    def _period_from_path(path: list[dict[str, str]]) -> date | None:
        import re

        pattern = re.compile(
            r"(?P<year>20\d{2})\s*(?:年|[-./])\s*(?P<month>0?[1-9]|1[0-2])(?:月)?"
        )
        for item in reversed(path):
            match = pattern.search(item.get("title", ""))
            if match:
                return date(int(match.group("year")), int(match.group("month")), 1)
        return None

    @staticmethod
    def _parse_datetime(value: Any, date_format: str | None) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=CST)
        if isinstance(value, date):
            return datetime.combine(value, time.min, tzinfo=CST)
        if isinstance(value, (int, float)):
            return datetime(1899, 12, 30, tzinfo=CST) + timedelta(days=float(value))
        text = str(value or "").strip()
        if not text:
            raise ValueError("日期为空")
        if date_format:
            return datetime.strptime(text, date_format).replace(tzinfo=CST)
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=CST)
        except ValueError:
            pass
        for pattern in ("%Y/%m/%d", "%Y-%m-%d", "%Y年%m月%d日"):
            try:
                return datetime.strptime(text, pattern).replace(tzinfo=CST)
            except ValueError:
                continue
        raise ValueError(f"无法解析日期：{text}")

    @staticmethod
    def _parse_decimal(value: Any) -> Decimal:
        text = str(value or "").strip().replace(",", "")
        if not text:
            raise ValueError("数值为空")
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"无法解析数值：{text}") from exc

    @staticmethod
    def _distribution_key(fact: EnergyMetricFact, group_by: str | None) -> str:
        if group_by == "车间/区域":
            return (
                fact.dimensions.get("车间/区域")
                or fact.dimensions.get("车间")
                or fact.dimensions.get("区域")
                or "未设置"
            )
        if group_by:
            return fact.dimensions.get(group_by) or "未设置"
        return str(fact.energy_type)

    @staticmethod
    def _is_ratio_metric(fact: EnergyMetricFact) -> bool:
        label = f"{fact.metric_key} {fact.energy_type}"
        return fact.unit.strip() in {"%", "％"} or "占比" in label

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, EnergyFeishuRequestError):
            log_suffix = (
                f" 请求日志 ID：{exc.request_log_id}。" if exc.request_log_id else ""
            )
            if exc.feishu_code == 131006:
                return (
                    "飞书拒绝读取 Wiki 节点（131006）。请在飞书开放平台为应用开通"
                    "“查看知识空间节点信息”或“查看知识库”权限，并将应用添加为目标"
                    f"知识库成员/管理员或该节点协作者。{log_suffix}"
                )
            if exc.feishu_code == 131005:
                return (
                    "未找到 Wiki 节点（131005）。请确认配置的是可访问的 Wiki 链接，"
                    f"且节点未被移动或删除。{log_suffix}"
                )
            if exc.feishu_code == 131002:
                return (
                    "Wiki 节点参数无效（131002）。请重新从飞书地址栏复制完整的 "
                    f"/wiki/ 链接后保存配置。{log_suffix}"
                )
            if exc.feishu_code in {131001, 131007}:
                return (
                    f"飞书 Wiki 服务暂时失败（{exc.feishu_code}），请稍后重试。"
                    f"{log_suffix}"
                )
            if exc.feishu_code == 1310213:
                return (
                    "飞书拒绝读取电子表格（1310213）。请为应用开通电子表格读取权限，"
                    f"并在表格中通过“添加文档应用”授予访问权。{log_suffix}"
                )
            return f"飞书请求失败（{exc}）。"
        message = f"{exc!s}".replace("\n", " ")[:1000]
        for sensitive in ("app_secret", "tenant_access_token", "authorization"):
            if sensitive in message.lower():
                return "飞书请求失败，错误信息已脱敏"
        return message or type(exc).__name__

    @staticmethod
    def _join_error(current: str | None, next_error: str) -> str:
        return "; ".join(part for part in (current, next_error) if part)[:4000]
