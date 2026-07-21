"""Reusable module-owned, read-only Feishu Base mirror service."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.modules.warehouse.feishu_client import WarehouseFeishuClient, parse_feishu_root_token
from app.core.exceptions import AppException


@dataclass(frozen=True)
class ReadMirrorModels:
    root: type[Any]
    resource: type[Any]
    field: type[Any]
    record: type[Any]
    binding: type[Any]
    sync_run: type[Any]


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
            select(self.models.root).where(
                self.models.root.config_id == config_id,
                self.models.root.source_type == normalized_type,
                self.models.root.root_token == token,
            ).order_by(self.models.root.updated_at.desc())
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
                path = base.get("path") if isinstance(base.get("path"), list) else []
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
        lock_key = f"{self.module_code}:feishu:read-sync:{resource_id}"
        lock_value = uuid.uuid4().hex
        acquired = await redis_client.set(lock_key, lock_value, ex=30 * 60, nx=True)
        if not acquired:
            raise AppException(message="该数据表正在同步，请稍后重试", status_code=409)
        try:
            return await self._sync_resource_locked(resource_id)
        finally:
            await redis_client.eval(
                "if redis.call('get',KEYS[1]) == ARGV[1] then "
                "return redis.call('del',KEYS[1]) else return 0 end",
                1,
                lock_key,
                lock_value,
            )

    async def _sync_resource_locked(self, resource_id: uuid.UUID) -> dict[str, Any]:
        resource = await self._resource(resource_id)
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
            fields = await self._replace_fields(resource.id, raw_fields)
            names_by_id = {item.field_id: item.field_name for item in fields}
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
                        source_modified_time=self._timestamp(item.get("last_modified_time")),
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
            await self.session.commit()
            return {"resource_id": str(resource.id), "record_count": len(records)}
        except Exception as exc:
            await self.session.rollback()
            resource = await self._resource(resource_id)
            failed_run = await self.session.get(self.models.sync_run, run_id)
            resource.sync_status = "failed"
            resource.sync_error = self._safe_error(exc)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error_message = self._safe_error(exc)
                failed_run.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise

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
    ) -> dict[str, Any]:
        binding, resource = await self._bound_resource(page_key, binding_id)
        fields = await self._fields(resource.id)
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
            total = int(
                await self.session.scalar(
                    select(func.count()).select_from(self.models.record).where(*conditions)
                )
                or 0
            )
            result = await self.session.execute(
                select(self.models.record)
                .where(*conditions)
                .order_by(self.models.record.record_id.asc())
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
                    "created_time": item.source_created_time.isoformat() if item.source_created_time else None,
                    "last_modified_time": item.source_modified_time.isoformat() if item.source_modified_time else None,
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
        result = await self._client(resource.app_token).download_media(file_token)
        return cast(tuple[bytes, str, str | None], result)

    async def _binding_payload(self, binding: Any, resource: Any) -> dict[str, Any]:
        field_count = int(
            await self.session.scalar(
                select(func.count()).select_from(self.models.field).where(
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
                    select(func.count()).select_from(self.models.record).where(
                        self.models.record.resource_id == resource.id,
                        self.models.record.mirror_version == resource.active_mirror_version,
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
                "last_synced_at": resource.last_complete_sync_at.isoformat() if resource.last_complete_sync_at else None,
                "sync_status": resource.sync_status,
                "sync_error": resource.sync_error,
                "source_root_id": str(resource.source_root_id),
                "source_path": resource.source_path,
                "schema_hash": resource.schema_hash,
                "active_mirror_version": str(resource.active_mirror_version) if resource.active_mirror_version else None,
            },
        }

    async def _replace_fields(self, resource_id: uuid.UUID, raw_fields: list[dict[str, Any]]) -> list[Any]:
        existing_result = await self.session.execute(
            select(self.models.field)
            .where(self.models.field.resource_id == resource_id)
            .order_by(self.models.field.is_deleted.asc(), self.models.field.updated_at.desc())
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
                "property": raw.get("property") if isinstance(raw.get("property"), dict) else {},
                "sort_order": index,
            }
            if item is None:
                item = self.models.field(resource_id=resource_id, field_id=field_id, **values)
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

    async def _upsert_resource(self, *, root: Any, app_token: str, table_id: str, title: str, source_path: list[Any]) -> Any:
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

    async def _resource(self, resource_id: uuid.UUID) -> Any:
        resource = await self.session.scalar(
            select(self.models.resource).where(
                self.models.resource.id == resource_id,
                self.models.resource.is_deleted.is_(False),
            )
        )
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

    async def _bound_resource(self, page_key: str, binding_id: uuid.UUID) -> tuple[Any, Any]:
        result = await self.session.execute(
            select(self.models.binding, self.models.resource)
            .join(self.models.resource, self.models.resource.id == self.models.binding.resource_id)
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
            if value.get("file_token") == file_token or value.get("attachment_token") == file_token:
                return True
            return any(cls._contains_attachment_token(item, file_token) for item in value.values())
        if isinstance(value, list):
            return any(cls._contains_attachment_token(item, file_token) for item in value)
        return False

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
