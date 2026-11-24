"""Reusable module-owned, read-only Feishu Base mirror service."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx
from redis.exceptions import RedisError
from sqlalchemy import Numeric, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.redis import redis_client
from app.modules.warehouse.feishu_client import (
    WarehouseFeishuClient,
    parse_feishu_root_token,
)

logger = logging.getLogger(__name__)


#: 数值型镜像字段类型（数字/日期/创建与修改时间），排序时按数值比较。
_RECORD_NUMERIC_FIELD_TYPES = {2, 5, 1001, 1002}
_RECORD_FILTER_OPERATORS = frozenset({"contains", "eq", "ne", "gt", "gte", "lt", "lte"})


def _record_order_expression(
    record_model: type[Any],
    field_name: str,
    field_type: int | None,
    direction: str,
) -> Any:
    """镜像记录 raw_fields 字段的排序表达式（JSONB 取文本，数值型按数值比较）。

    空值统一排最后：升序 nulls_first 会把整页空行顶到最前
    （员工住宿退宿清单等表存在 raw_fields 为空的记录），与倒序 nulls_last
    保持对称。
    """
    text_expr = record_model.raw_fields[field_name].astext
    if field_type in _RECORD_NUMERIC_FIELD_TYPES:
        text_expr = cast(text_expr, Numeric)
    if direction == "asc":
        return text_expr.asc().nulls_last()
    return text_expr.desc().nulls_last()


def _record_filter_expression(
    record_model: type[Any],
    field_name: str,
    field_type: int | None,
    operator: str,
    value: str,
) -> Any:
    """镜像记录单条件筛选表达式；条件之间由调用方以 AND 组合。"""
    if operator not in _RECORD_FILTER_OPERATORS:
        raise AppException(message="不支持的筛选操作符", status_code=400)
    text_expr = record_model.raw_fields[field_name].astext
    if operator == "contains":
        escaped = value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        return text_expr.ilike(f"%{escaped}%")
    if field_type in _RECORD_NUMERIC_FIELD_TYPES:
        try:
            number = float(value)
        except ValueError as exc:
            raise AppException(
                message="该字段为数值或日期类型，筛选值必须是数字", status_code=400
            ) from exc
        column_expr = cast(text_expr, Numeric)
        if operator == "eq":
            return column_expr == number
        if operator == "ne":
            return column_expr != number
        if operator == "gt":
            return column_expr > number
        if operator == "gte":
            return column_expr >= number
        if operator == "lt":
            return column_expr < number
        return column_expr <= number
    if operator == "eq":
        return text_expr == value
    if operator == "ne":
        return text_expr != value
    if operator == "gt":
        return text_expr > value
    if operator == "gte":
        return text_expr >= value
    if operator == "lt":
        return text_expr < value
    return text_expr <= value


@dataclass(frozen=True)
class ReadMirrorModels:
    root: type[Any]
    resource: type[Any]
    field: type[Any]
    record: type[Any]
    binding: type[Any]
    sync_run: type[Any]
    fence_sync_runs: bool = False


class ModuleFeishuReadMirrorService:
    """Operate a module's local mirror using explicitly supplied credentials."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        module_code: str,
        app_id: str,
        app_secret: str,
        models: ReadMirrorModels,
    ) -> None:
        self.session = session
        self.module_code = module_code
        self.app_id = app_id
        self.app_secret = app_secret
        self.models = models

    async def list_roots(self, config_id: uuid.UUID) -> list[Any]:
        result = await self.session.execute(
            select(self.models.root)
            .where(
                self.models.root.config_id == config_id,
                self.models.root.is_deleted.is_(False),
            )
            .order_by(self.models.root.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_root(
        self,
        *,
        config_id: uuid.UUID,
        name: str,
        source_type: str,
        source_url: str,
    ) -> Any:
        normalized_type = source_type.strip().lower()
        if normalized_type not in {"wiki", "base"}:
            raise AppException(message="入口类型仅支持 wiki 或 base")
        try:
            token = parse_feishu_root_token(source_url, normalized_type)
        except ValueError as exc:
            raise AppException(message=str(exc)) from exc
        existing = await self.session.scalar(
            select(self.models.root)
            .where(
                self.models.root.config_id == config_id,
                self.models.root.source_type == normalized_type,
                self.models.root.root_token == token,
            )
            .order_by(self.models.root.updated_at.desc())
        )
        if existing is not None:
            if not existing.is_deleted:
                raise AppException(message="该飞书入口已存在")
            existing.name = name.strip() or token
            existing.source_url = source_url.strip()
            existing.is_deleted = False
            existing.is_active = True
            existing.discovery_status = "pending"
            existing.discovery_error = None
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        root = self.models.root(
            config_id=config_id,
            name=name.strip() or token,
            source_type=normalized_type,
            source_url=source_url.strip(),
            root_token=token,
            is_active=True,
            discovery_status="pending",
        )
        self.session.add(root)
        await self.session.commit()
        await self.session.refresh(root)
        return root

    async def delete_root(self, root_id: uuid.UUID) -> None:
        root = await self._root(root_id)
        root.is_deleted = True
        root.is_active = False
        await self.session.commit()

    async def discover_root(self, root_id: uuid.UUID) -> list[Any]:
        root = await self._root(root_id)
        root.discovery_status = "running"
        root.discovery_error = None
        await self.session.commit()
        try:
            if root.source_type == "wiki":
                discovery_client = self._client("")
                bases = await discovery_client.discover_wiki_bases(root.root_token)
            else:
                bases = [
                    {
                        "app_token": root.root_token,
                        "path": [{"token": root.root_token, "title": root.name}],
                    }
                ]
            resources: list[Any] = []
            for base in bases:
                app_token = str(base.get("app_token") or "")
                if not app_token:
                    continue
                raw_path = base.get("path")
                path: list[Any] = raw_path if isinstance(raw_path, list) else []
                for table in await self._client(app_token).list_tables(page_size=100):
                    table_id = str(table.get("table_id") or table.get("id") or "")
                    if not table_id:
                        continue
                    resources.append(
                        await self._upsert_resource(
                            root=root,
                            app_token=app_token,
                            table_id=table_id,
                            title=str(table.get("name") or table_id),
                            source_path=path,
                        )
                    )
            root.discovery_status = "success"
            root.last_discovered_at = datetime.now(UTC)
            await self.session.commit()
            return resources
        except Exception as exc:
            await self.session.rollback()
            root = await self._root(root_id)
            root.discovery_status = "failed"
            root.discovery_error = self._safe_error(exc)
            await self.session.commit()
            raise

    async def list_resources(self) -> list[Any]:
        result = await self.session.execute(
            select(self.models.resource)
            .where(self.models.resource.is_deleted.is_(False))
            .order_by(self.models.resource.title.asc())
        )
        return list(result.scalars().all())

    async def sync_resource(self, resource_id: uuid.UUID) -> dict[str, Any]:
        result = await self._sync_with_lease(resource_id)
        assert result is not None
        return result

    async def sync_due_resource(
        self, resource_id: uuid.UUID, due_on: date
    ) -> dict[str, Any] | None:
        """Recheck the date under the same lock used by manual sync."""
        return await self._sync_with_lease(resource_id, due_on=due_on)

    async def _sync_with_lease(
        self, resource_id: uuid.UUID, *, due_on: date | None = None
    ) -> dict[str, Any] | None:
        lock_key = f"{self.module_code}:feishu:read-sync:{resource_id}"
        lock_value = uuid.uuid4().hex
        redis_timeout = 5 if self.models.fence_sync_runs else None
        async with asyncio.timeout(redis_timeout):
            acquired = await redis_client.set(lock_key, lock_value, ex=30 * 60, nx=True)
        if not acquired:
            if due_on is not None:
                logger.info("Mirror %s sync skipped: resource lock held", resource_id)
                return None
            raise AppException(message="该数据表正在同步，请稍后重试", status_code=409)
        try:
            if self.models.fence_sync_runs:
                return await self._sync_resource_locked(
                    resource_id, due_on=due_on, lease=(lock_key, lock_value)
                )
            return await self._sync_resource_locked(resource_id)
        finally:
            try:
                cleanup = redis_client.eval(
                    "if redis.call('get',KEYS[1]) == ARGV[1] then "
                    "return redis.call('del',KEYS[1]) else return 0 end",
                    1,
                    lock_key,
                    lock_value,
                )
                if inspect.isawaitable(cleanup):
                    async with asyncio.timeout(redis_timeout):
                        await cleanup
            except (RedisError, TimeoutError) as exc:
                if not self.models.fence_sync_runs:
                    raise
                logger.warning(
                    "Mirror %s lock cleanup failed (%s)",
                    resource_id,
                    type(exc).__name__,
                )

    async def _require_lease(self, lease: tuple[str, str]) -> None:
        async with asyncio.timeout(5):
            owner = await redis_client.get(lease[0])
        if owner != lease[1]:
            raise AppException(message="同步已失去资源锁，请重新同步", status_code=409)

    async def _sync_resource_locked(
        self,
        resource_id: uuid.UUID,
        *,
        due_on: date | None = None,
        lease: tuple[str, str] | None = None,
    ) -> dict[str, Any] | None:
        if lease is None:
            resource = await self._resource(resource_id)
        else:
            resource = await self._resource(resource_id, for_update=True)
            await self._require_lease(lease)
            if (
                due_on is not None
                and resource.last_complete_sync_at is not None
                and resource.last_complete_sync_at.astimezone(UTC).date() >= due_on
            ):
                await self.session.rollback()
                return None
            # A previous process may have died after committing its running record.
            run_model = self.models.sync_run
            await self.session.execute(
                update(run_model)
                .where(
                    run_model.resource_id == resource_id, run_model.status == "running"
                )
                .values(
                    status="failed",
                    error_message="同步中断，已由后续执行接管",
                    completed_at=datetime.now(UTC),
                )
            )
        version = uuid.uuid4()
        run = self.models.sync_run(
            resource_id=resource.id,
            mirror_version=version,
            status="running",
        )
        self.session.add(run)
        resource.sync_status = "running"
        resource.sync_error = None
        await self.session.flush()
        run_id = run.id
        await self.session.commit()
        try:
            client = self._client(resource.app_token)
            raw_fields = await client.list_fields(resource.table_id, page_size=100)
            if lease is None:
                fields = await self._replace_fields(resource_id, raw_fields)
            records: list[dict[str, Any]] = []
            seen: set[str] = set()
            page_token: str | None = None
            expected_total: int | None = None
            page_size = 500
            while True:
                page = await client.search_records(
                    resource.table_id,
                    page_size=page_size,
                    page_token=page_token,
                )
                if page.get("total") is not None:
                    expected_total = int(page["total"])
                for item in page.get("items") or []:
                    record_id = str(item.get("record_id") or item.get("id") or "")
                    if not record_id:
                        raise RuntimeError("飞书记录缺少 record_id")
                    if record_id in seen:
                        continue
                    seen.add(record_id)
                    records.append(item)
                if not page.get("has_more"):
                    break
                next_token = str(page.get("page_token") or "")
                if not next_token or next_token == page_token:
                    raise RuntimeError("飞书分页链不完整")
                page_token = next_token
            if expected_total is not None and len(seen) != expected_total:
                raise RuntimeError(
                    f"完整性校验失败：飞书 total={expected_total}，唯一记录={len(seen)}"
                )
            if lease is not None:
                # Serialize final writes against the transaction starting any successor.
                resource = await self._resource(resource_id, for_update=True)
                await self._require_lease(lease)
                fields = await self._replace_fields(resource_id, raw_fields)
            names_by_id = {item.field_id: item.field_name for item in fields}
            for item in records:
                raw = item.get("fields") if isinstance(item.get("fields"), dict) else {}
                search_text = json.dumps(raw, ensure_ascii=False, default=str)
                self.session.add(
                    self.models.record(
                        resource_id=resource.id,
                        record_id=str(item.get("record_id") or item.get("id")),
                        mirror_version=version,
                        raw_fields=raw,
                        normalized_fields=raw,
                        search_text=search_text,
                        source_created_time=self._timestamp(item.get("created_time")),
                        source_modified_time=self._timestamp(
                            item.get("last_modified_time")
                        ),
                    )
                )
            schema_payload = [
                (field_id, names_by_id[field_id]) for field_id in sorted(names_by_id)
            ]
            resource.schema_hash = hashlib.sha256(
                json.dumps(schema_payload, ensure_ascii=False).encode()
            ).hexdigest()
            resource.active_mirror_version = version
            resource.last_complete_sync_at = datetime.now(UTC)
            resource.sync_status = "success"
            run.status = "success"
            run.expected_count = expected_total
            run.actual_count = len(records)
            run.completed_at = datetime.now(UTC)
            if lease is not None:
                await self.session.flush()
                await self._require_lease(lease)
            await self.session.commit()
            return {"resource_id": str(resource_id), "record_count": len(records)}
        except (Exception, asyncio.CancelledError) as exc:
            if lease is not None or not isinstance(exc, asyncio.CancelledError):
                await self._fail_sync_run(
                    resource_id, run_id, exc, fenced=lease is not None
                )
            raise

    async def _fail_sync_run(
        self,
        resource_id: uuid.UUID,
        run_id: uuid.UUID,
        exc: Exception | asyncio.CancelledError,
        *,
        fenced: bool,
    ) -> None:
        await self.session.rollback()
        if fenced:
            resource = await self._resource(resource_id, for_update=True)
            failed_run = await self.session.get(
                self.models.sync_run, run_id, populate_existing=True
            )
            if failed_run is None or failed_run.status != "running":
                await self.session.rollback()
                return
        else:
            resource = await self._resource(resource_id)
            failed_run = await self.session.get(self.models.sync_run, run_id)
        if isinstance(exc, asyncio.CancelledError):
            error = "同步执行已取消"
        elif fenced:
            error = f"镜像同步失败（{type(exc).__name__}）"
        else:
            error = self._safe_error(exc)
        resource.sync_status = "failed"
        resource.sync_error = error
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_message = error
            failed_run.completed_at = datetime.now(UTC)
        await self.session.commit()

    async def replace_bindings(
        self, page_key: str, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        existing = await self.session.execute(
            select(self.models.binding).where(
                self.models.binding.page_key == page_key,
                self.models.binding.is_deleted.is_(False),
            )
        )
        existing_by_resource = {
            binding.resource_id: binding for binding in existing.scalars().all()
        }
        for binding in existing_by_resource.values():
            binding.is_enabled = False
        seen: set[uuid.UUID] = set()
        for index, item in enumerate(items):
            resource_id = uuid.UUID(str(item["resource_id"]))
            if resource_id in seen:
                raise AppException(message="同一页面不能重复绑定同一数据表")
            seen.add(resource_id)
            resource = await self._resource(resource_id)
            binding = existing_by_resource.get(resource.id)
            values: dict[str, Any] = {
                "tab_name": str(item.get("tab_name") or resource.title),
                "sort_order": int(item.get("sort_order", index)),
                "is_default": bool(item.get("is_default", index == 0)),
                "is_enabled": bool(item.get("is_enabled", True)),
                "visible_field_ids": list(item.get("visible_field_ids") or []),
            }
            if binding is None:
                binding = self.models.binding(
                    page_key=page_key,
                    resource_id=resource.id,
                    **values,
                )
                self.session.add(binding)
            else:
                for key, value in values.items():
                    setattr(binding, key, value)
        await self.session.commit()
        return await self.page_data(page_key)

    async def page_data(self, page_key: str) -> dict[str, Any]:
        result = await self.session.execute(
            select(self.models.binding, self.models.resource)
            .join(
                self.models.resource,
                self.models.resource.id == self.models.binding.resource_id,
            )
            .where(
                self.models.binding.page_key == page_key,
                self.models.binding.is_enabled.is_(True),
                self.models.binding.is_deleted.is_(False),
                self.models.resource.is_deleted.is_(False),
            )
            .order_by(self.models.binding.sort_order.asc())
        )
        bindings = [
            await self._binding_payload(binding, resource)
            for binding, resource in result.all()
        ]
        return {"page_key": page_key, "bindings": bindings}

    async def page_records(
        self,
        *,
        page_key: str,
        binding_id: uuid.UUID,
        page: int,
        page_size: int,
        keyword: str | None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
        filters: Sequence[Mapping[str, str]] | None = None,
    ) -> dict[str, Any]:
        binding, resource = await self._bound_resource(page_key, binding_id)
        fields = await self._fields(resource.id)
        order_by: tuple[Any, ...] = (self.models.record.record_id.asc(),)
        if sort_field:
            # 前端排序控件传 field_id，这里同时兼容字段名（raw_fields 的键）
            meta = next(
                (
                    f
                    for f in fields
                    if f.field_name == sort_field or f.field_id == sort_field
                ),
                None,
            )
            if meta is None:
                raise AppException(message="排序字段不属于该数据表", status_code=404)
            try:
                field_type: int | None = int(meta.field_type)
            except (TypeError, ValueError):
                field_type = None
            order_by = (
                _record_order_expression(
                    self.models.record, meta.field_name, field_type, sort_direction
                ),
                self.models.record.record_id.asc(),
            )
        if resource.active_mirror_version is None:
            records: list[Any] = []
            total = 0
        else:
            conditions = [
                self.models.record.resource_id == resource.id,
                self.models.record.mirror_version == resource.active_mirror_version,
                self.models.record.is_deleted.is_(False),
            ]
            if keyword:
                conditions.append(self.models.record.search_text.ilike(f"%{keyword}%"))
            field_index = {
                **{f.field_id: f for f in fields},
                **{f.field_name: f for f in fields},
            }
            for item in filters or ():
                field_meta = field_index.get(str(item.get("field", "")))
                if field_meta is None:
                    raise AppException(
                        message="筛选字段不属于该数据表", status_code=404
                    )
                value = str(item.get("value", "")).strip()
                if not value:
                    continue
                try:
                    filter_type: int | None = int(field_meta.field_type)
                except (TypeError, ValueError):
                    filter_type = None
                conditions.append(
                    _record_filter_expression(
                        self.models.record,
                        field_meta.field_name,
                        filter_type,
                        str(item.get("operator", "contains")),
                        value,
                    )
                )
            total = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(self.models.record)
                    .where(*conditions)
                )
                or 0
            )
            result = await self.session.execute(
                select(self.models.record)
                .where(*conditions)
                .order_by(*order_by)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            records = list(result.scalars().all())
        return {
            "dataset": await self._binding_payload(binding, resource),
            "fields": [self._field_payload(item) for item in fields],
            "records": [
                {
                    "record_id": item.record_id,
                    "fields": item.raw_fields,
                    "normalized_fields": item.normalized_fields,
                    "created_time": item.source_created_time.isoformat()
                    if item.source_created_time
                    else None,
                    "last_modified_time": item.source_modified_time.isoformat()
                    if item.source_modified_time
                    else None,
                }
                for item in records
            ],
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }

    async def download_attachment(
        self,
        *,
        page_key: str,
        binding_id: uuid.UUID,
        record_id: str,
        field_id: str,
        file_token: str,
    ) -> tuple[bytes, str, str | None]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,512}", file_token):
            raise AppException(message="附件标识不合法")
        _binding, resource = await self._bound_resource(page_key, binding_id)
        field = await self.session.scalar(
            select(self.models.field).where(
                self.models.field.resource_id == resource.id,
                self.models.field.field_id == field_id,
                self.models.field.is_deleted.is_(False),
            )
        )
        if field is None or resource.active_mirror_version is None:
            raise AppException(message="附件字段不存在", status_code=404)
        record = await self.session.scalar(
            select(self.models.record).where(
                self.models.record.resource_id == resource.id,
                self.models.record.mirror_version == resource.active_mirror_version,
                self.models.record.record_id == record_id,
                self.models.record.is_deleted.is_(False),
            )
        )
        if record is None:
            raise AppException(message="镜像记录不存在", status_code=404)
        value = record.raw_fields.get(field.field_name)
        if not self._contains_attachment_token(value, file_token):
            raise AppException(message="附件不属于该记录", status_code=404)
        client = self._client(resource.app_token)
        try:
            return await client.download_media(file_token)
        except httpx.HTTPStatusError as exc:
            # 应用无云盘下载权限时（Base 附件常见），medias/download 返回无体 400；
            # 改用记录自带的 tmp_url 换签名直链，权限判定走 bitable，与读记录一致。
            if exc.response.status_code not in (400, 403):
                raise
            tmp_url = self._attachment_tmp_url(value, file_token)
            if tmp_url is None:
                raise
            return await client.download_media_via_tmp_url(tmp_url)

    async def _binding_payload(self, binding: Any, resource: Any) -> dict[str, Any]:
        field_count = int(
            await self.session.scalar(
                select(func.count())
                .select_from(self.models.field)
                .where(
                    self.models.field.resource_id == resource.id,
                    self.models.field.is_deleted.is_(False),
                )
            )
            or 0
        )
        record_count = 0
        if resource.active_mirror_version:
            record_count = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(self.models.record)
                    .where(
                        self.models.record.resource_id == resource.id,
                        self.models.record.mirror_version
                        == resource.active_mirror_version,
                        self.models.record.is_deleted.is_(False),
                    )
                )
                or 0
            )
        return {
            "id": str(binding.id),
            "page_key": binding.page_key,
            "table_pk": str(resource.id),
            "tab_label": binding.tab_name,
            "display_order": binding.sort_order,
            "is_default": binding.is_default,
            "visible_field_ids": binding.visible_field_ids,
            "default_sort": [],
            "history_mode": "current_mirror",
            "is_enabled": binding.is_enabled,
            "status": "published",
            "table": {
                "id": str(resource.id),
                "business_domain": self.module_code,
                "app_token": resource.app_token,
                "table_id": resource.table_id,
                "name": resource.title,
                "is_enabled": True,
                "field_count": field_count,
                "record_count": record_count,
                "last_synced_at": resource.last_complete_sync_at.isoformat()
                if resource.last_complete_sync_at
                else None,
                "sync_status": resource.sync_status,
                "sync_error": resource.sync_error,
                "source_root_id": str(resource.source_root_id),
                "source_path": resource.source_path,
                "schema_hash": resource.schema_hash,
                "active_mirror_version": str(resource.active_mirror_version)
                if resource.active_mirror_version
                else None,
            },
        }

    async def _replace_fields(
        self, resource_id: uuid.UUID, raw_fields: list[dict[str, Any]]
    ) -> list[Any]:
        existing_result = await self.session.execute(
            select(self.models.field)
            .where(self.models.field.resource_id == resource_id)
            .order_by(
                self.models.field.is_deleted.asc(), self.models.field.updated_at.desc()
            )
        )
        existing: dict[str, Any] = {}
        for item in existing_result.scalars().all():
            existing.setdefault(item.field_id, item)
        active_ids: set[str] = set()
        output: list[Any] = []
        for index, raw in enumerate(raw_fields):
            field_id = str(raw.get("field_id") or raw.get("id") or "")
            if not field_id:
                continue
            active_ids.add(field_id)
            item = existing.get(field_id)
            values: dict[str, Any] = {
                "field_name": str(raw.get("field_name") or raw.get("name") or field_id),
                "field_type": str(raw.get("type") or "0"),
                "property": raw.get("property")
                if isinstance(raw.get("property"), dict)
                else {},
                "sort_order": index,
            }
            if item is None:
                item = self.models.field(
                    resource_id=resource_id, field_id=field_id, **values
                )
                self.session.add(item)
            else:
                for key, value in values.items():
                    setattr(item, key, value)
                item.is_deleted = False
            output.append(item)
        for field_id, item in existing.items():
            if field_id not in active_ids:
                item.is_deleted = True
        await self.session.flush()
        return output

    async def _upsert_resource(
        self,
        *,
        root: Any,
        app_token: str,
        table_id: str,
        title: str,
        source_path: list[Any],
    ) -> Any:
        resource = await self.session.scalar(
            select(self.models.resource).where(
                self.models.resource.app_token == app_token,
                self.models.resource.table_id == table_id,
                self.models.resource.is_deleted.is_(False),
            )
        )
        if resource is None:
            resource = self.models.resource(
                source_root_id=root.id,
                app_token=app_token,
                table_id=table_id,
                title=title,
                source_path=source_path,
            )
            self.session.add(resource)
        else:
            resource.source_root_id = root.id
            resource.title = title
            resource.source_path = source_path
        await self.session.flush()
        return resource

    async def _root(self, root_id: uuid.UUID) -> Any:
        root = await self.session.scalar(
            select(self.models.root).where(
                self.models.root.id == root_id,
                self.models.root.is_deleted.is_(False),
            )
        )
        if root is None:
            raise AppException(message="飞书入口不存在", status_code=404)
        return root

    async def _resource(
        self, resource_id: uuid.UUID, *, for_update: bool = False
    ) -> Any:
        stmt = select(self.models.resource).where(
            self.models.resource.id == resource_id,
            self.models.resource.is_deleted.is_(False),
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        resource = await self.session.scalar(stmt)
        if resource is None:
            raise AppException(message="飞书数据表资源不存在", status_code=404)
        return resource

    async def _fields(self, resource_id: uuid.UUID) -> list[Any]:
        result = await self.session.execute(
            select(self.models.field)
            .where(
                self.models.field.resource_id == resource_id,
                self.models.field.is_deleted.is_(False),
            )
            .order_by(self.models.field.sort_order.asc())
        )
        return list(result.scalars().all())

    async def _bound_resource(
        self, page_key: str, binding_id: uuid.UUID
    ) -> tuple[Any, Any]:
        result = await self.session.execute(
            select(self.models.binding, self.models.resource)
            .join(
                self.models.resource,
                self.models.resource.id == self.models.binding.resource_id,
            )
            .where(
                self.models.binding.id == binding_id,
                self.models.binding.page_key == page_key,
                self.models.binding.is_enabled.is_(True),
                self.models.binding.is_deleted.is_(False),
                self.models.resource.is_deleted.is_(False),
            )
        )
        row = result.first()
        if row is None:
            raise AppException(message="页面数据表绑定不存在", status_code=404)
        return row[0], row[1]

    def client_for_resource(self, app_token: str) -> WarehouseFeishuClient:
        """公开的按资源构建客户端入口（模块侧导出等编排场景使用）。"""
        return self._client(app_token)

    def _client(self, app_token: str) -> WarehouseFeishuClient:
        if not self.app_id or not self.app_secret:
            raise AppException(message="飞书 App ID 或 Secret 未配置")
        return WarehouseFeishuClient(
            app_id=self.app_id,
            app_secret=self.app_secret,
            app_token=app_token,
        )

    @classmethod
    def _contains_attachment_token(cls, value: Any, file_token: str) -> bool:
        if isinstance(value, dict):
            if (
                value.get("file_token") == file_token
                or value.get("attachment_token") == file_token
            ):
                return True
            return any(
                cls._contains_attachment_token(item, file_token)
                for item in value.values()
            )
        if isinstance(value, list):
            return any(
                cls._contains_attachment_token(item, file_token) for item in value
            )
        return False

    @classmethod
    def _attachment_tmp_url(cls, value: Any, file_token: str) -> str | None:
        """取与 file_token 匹配附件项的 tmp_url（batch_get_tmp_download_url 串）。"""
        if isinstance(value, dict):
            if (
                value.get("file_token") == file_token
                or value.get("attachment_token") == file_token
            ):
                tmp_url = value.get("tmp_url")
                if isinstance(tmp_url, str) and tmp_url.startswith(
                    "https://open.feishu.cn/open-apis/"
                ):
                    return tmp_url
                return None
            for item in value.values():
                found = cls._attachment_tmp_url(item, file_token)
                if found:
                    return found
            return None
        if isinstance(value, list):
            for item in value:
                found = cls._attachment_tmp_url(item, file_token)
                if found:
                    return found
        return None

    @staticmethod
    def _field_payload(item: Any) -> dict[str, Any]:
        try:
            field_type = int(item.field_type)
        except (TypeError, ValueError):
            field_type = None
        return {
            "field_id": item.field_id,
            "field_name": item.field_name,
            "type": field_type,
            "property": item.property,
            "display_order": item.sort_order,
        }

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            number = float(value)
            if number > 10_000_000_000:
                number /= 1000
            return datetime.fromtimestamp(number, UTC)
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc).replace("Bearer ", "Bearer ***")
        return message[:1000]
