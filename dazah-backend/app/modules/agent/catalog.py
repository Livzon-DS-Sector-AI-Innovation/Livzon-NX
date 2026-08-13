import hashlib
import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import User

from .access_scope import AgentAccessScopeService
from .models import AgentToolCatalog
from .schemas import AgentToolCatalogEntry, AgentToolSearchRequest
from .tool_registration import ensure_agent_tools_registered
from .tools import AgentToolSpec, tool_registry


def _metadata_hash(spec: AgentToolSpec) -> str:
    payload = json.dumps(
        spec.public_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _catalog_entry(row: AgentToolCatalog) -> AgentToolCatalogEntry:
    return AgentToolCatalogEntry(
        operation=row.operation,
        module=row.module,
        version=row.capability_version,
        summary=row.summary,
        status=row.status,
        risk_level=row.risk_level,
        write=row.write,
        confirmation_required=row.confirmation_required,
        permission_key=row.permission_key,
        input_schema=row.input_schema,
        output_schema=row.output_schema,
        timeout_seconds=row.timeout_seconds,
        idempotent=row.idempotent,
    )


class ToolCatalogService:
    def __init__(self) -> None:
        self.access_scope = AgentAccessScopeService()

    async def synchronize(self, db: AsyncSession) -> None:
        ensure_agent_tools_registered()
        rows = list((await db.execute(select(AgentToolCatalog))).scalars().all())
        by_operation = {row.operation: row for row in rows}
        active_operations: set[str] = set()
        for spec in tool_registry.list():
            active_operations.add(spec.name)
            row = by_operation.get(spec.name)
            if row is None:
                row = AgentToolCatalog(operation=spec.name)
                db.add(row)
            row.module = spec.module
            row.capability_version = spec.capability_version
            row.summary = spec.summary
            row.status = "active" if row.admin_enabled else "disabled"
            row.risk_level = spec.risk_level
            row.write = spec.write
            row.confirmation_required = spec.write
            row.permission_key = spec.permission_key
            row.input_schema = spec.input_schema or spec.input_model.model_json_schema()
            row.output_schema = spec.output_schema
            row.timeout_seconds = spec.timeout_seconds
            row.idempotent = spec.idempotent
            row.metadata_hash = _metadata_hash(spec)
        for row in rows:
            if row.operation not in active_operations:
                row.status = "disabled"
        await db.flush()

    async def set_enabled(
        self,
        db: AsyncSession,
        *,
        operation: str,
        enabled: bool,
    ) -> AgentToolCatalogEntry:
        await self.synchronize(db)
        row = await db.scalar(
            select(AgentToolCatalog).where(AgentToolCatalog.operation == operation)
        )
        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Agent tool was not found",
            )
        row.admin_enabled = enabled
        row.status = "active" if enabled else "disabled"
        await db.flush()
        return _catalog_entry(row)

    async def require_enabled(
        self,
        db: AsyncSession,
        *,
        operation: str,
    ) -> None:
        """Fail closed when an administrator has disabled an operation."""
        row = await db.scalar(
            select(AgentToolCatalog).where(AgentToolCatalog.operation == operation)
        )
        if row is None:
            await self.synchronize(db)
            row = await db.scalar(
                select(AgentToolCatalog).where(AgentToolCatalog.operation == operation)
            )
        if row is None or row.status != "active" or not row.admin_enabled:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "该能力已被管理员停用，当前无法执行",
            )

    async def list_all(
        self,
        db: AsyncSession,
    ) -> list[AgentToolCatalogEntry]:
        await self.synchronize(db)
        rows = list(
            (
                await db.execute(
                    select(AgentToolCatalog).order_by(
                        AgentToolCatalog.module.asc(),
                        AgentToolCatalog.operation.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_catalog_entry(row) for row in rows]

    async def list_page(
        self,
        db: AsyncSession,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        module: str | None = None,
        status_value: str | None = None,
        risk_level: str | None = None,
        write: bool | None = None,
    ) -> tuple[list[AgentToolCatalogEntry], int]:
        await self.synchronize(db)
        conditions = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    AgentToolCatalog.operation.ilike(pattern),
                    AgentToolCatalog.summary.ilike(pattern),
                )
            )
        if module:
            conditions.append(
                AgentToolCatalog.module.is_(None)
                if module == "platform"
                else AgentToolCatalog.module == module
            )
        if status_value:
            conditions.append(AgentToolCatalog.status == status_value)
        if risk_level:
            conditions.append(AgentToolCatalog.risk_level == risk_level)
        if write is not None:
            conditions.append(AgentToolCatalog.write == write)
        total = int(
            await db.scalar(
                select(func.count()).select_from(AgentToolCatalog).where(*conditions)
            )
            or 0
        )
        rows = list(
            (
                await db.execute(
                    select(AgentToolCatalog)
                    .where(*conditions)
                    .order_by(
                        AgentToolCatalog.module.asc(),
                        AgentToolCatalog.operation.asc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return [_catalog_entry(row) for row in rows], total

    async def _trusted_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        tenant_id: str,
    ) -> User:
        user = await db.get(User, user_id)
        if user is None or user.is_deleted or user.status != "active":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Trusted Agent subject is not an active local user",
            )
        if (user.tenant_key or "default") != tenant_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Trusted Agent subject tenant does not match the local user",
            )
        return user

    async def search(
        self,
        db: AsyncSession,
        request: AgentToolSearchRequest,
    ) -> list[AgentToolCatalogEntry]:
        await self.synchronize(db)
        user = await self._trusted_user(
            db,
            request.subject.user_id,
            tenant_id=request.subject.tenant_id,
        )
        query = request.query.strip().casefold()
        rows = list(
            (
                await db.execute(
                    select(AgentToolCatalog)
                    .where(AgentToolCatalog.status == "active")
                    .order_by(AgentToolCatalog.operation.asc())
                )
            )
            .scalars()
            .all()
        )
        result: list[AgentToolCatalogEntry] = []
        for row in rows:
            if request.module and row.module != request.module:
                continue
            haystack = f"{row.operation} {row.module or ''} {row.summary}".casefold()
            if query and query not in haystack:
                continue
            try:
                await self.access_scope.require_tool_access(
                    db,
                    user=user,
                    tool_name=row.operation,
                    module=row.module,
                )
            except HTTPException as exc:
                if exc.status_code == status.HTTP_403_FORBIDDEN:
                    continue
                raise
            result.append(_catalog_entry(row))
            if len(result) >= request.limit:
                break
        return result

    async def describe(
        self,
        db: AsyncSession,
        *,
        operation: str,
        user_id: uuid.UUID,
        tenant_id: str,
    ) -> AgentToolCatalogEntry:
        await self.synchronize(db)
        row = await db.scalar(
            select(AgentToolCatalog).where(
                AgentToolCatalog.operation == operation,
                AgentToolCatalog.status == "active",
            )
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent tool was not found")
        user = await self._trusted_user(db, user_id, tenant_id=tenant_id)
        await self.access_scope.require_tool_access(
            db,
            user=user,
            tool_name=row.operation,
            module=row.module,
        )
        return _catalog_entry(row)
