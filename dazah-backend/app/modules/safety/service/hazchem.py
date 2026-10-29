"""危化品与 MSDS：危化品档案、车间存量（超储预警）与 MSDS 附件。"""

from __future__ import annotations

import logging
import uuid as uuid_module
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import (
    ChemicalInventory,
    ChemicalMsdsAttachment,
    HazardousChemical,
)
from app.modules.safety.schemas.hazchem import (
    ChemicalInventoryCreate,
    ChemicalInventoryResponse,
    ChemicalInventoryStatsResponse,
    ChemicalInventoryUpdate,
    HazardousChemicalCreate,
    HazardousChemicalUpdate,
    HazchemStatsResponse,
)

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {
    "explosive",
    "flammable_gas",
    "oxidizing_gas",
    "flammable_liquid",
    "flammable_solid",
    "self_reactive",
    "oxidizing_liquid",
    "organic_peroxide",
    "toxic",
    "corrosive",
    "other",
}


def build_search_text(
    name: str, alias: str, cas_no: str, hazard_statements: str
) -> str:
    return " ".join(part for part in (name, alias, cas_no, hazard_statements) if part)


def inventory_over_limit(quantity: float, upper_limit: float | None) -> bool:
    return upper_limit is not None and quantity > upper_limit


# ── MSDS 附件存储：MinIO 优先、本地 uploads/safety/hazchem 回退 ──

MSDS_ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}
MSDS_MAX_BYTES = 30 * 1024 * 1024


def _msds_local_root() -> Path:
    root = (Path(get_settings().UPLOAD_DIR) / "safety" / "hazchem").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _msds_local_path(storage_key: str) -> Path:
    """把存储 key 解析为本地路径；旧迁移数据存 uploads/ 前缀整体路径。"""
    normalized = storage_key.replace("\\", "/")
    if normalized.startswith("uploads/"):
        return Path(normalized).resolve()
    root = _msds_local_root()
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AppException(message="非法文件路径") from exc
    if path == root:
        raise AppException(message="非法文件路径")
    return path


def store_msds_object(storage_key: str, content: bytes, content_type: str) -> str:
    if storage.is_enabled():
        storage.upload_object(
            "safety", storage_key, content, len(content), content_type
        )
        return storage_key
    path = _msds_local_path(storage_key)
    with open(path, "wb") as file_obj:
        file_obj.write(content)
    return storage_key


def read_msds_object(storage_key: str) -> tuple[bytes, str] | None:
    if storage.is_enabled():
        found = storage.get_object("safety", storage_key)
        if found is not None:
            return found
    path = _msds_local_path(storage_key)
    if not path.exists():
        return None
    return path.read_bytes(), "application/octet-stream"


def delete_msds_object(storage_key: str) -> None:
    if storage.is_enabled():
        try:
            storage.delete_object("safety", storage_key)
        except Exception:
            # 旧迁移数据只存在于本地：MinIO 删除失败不阻断本地清理
            logger.warning(
                "删除 MinIO MSDS 对象失败: key=%s", storage_key, exc_info=True
            )
    path = _msds_local_path(storage_key)
    if path.exists():
        path.unlink()


def build_msds_storage_key(chemical_id: UUID, file_ext: str) -> str:
    return f"msds_{chemical_id}_{uuid_module.uuid4().hex}{file_ext}"


class HazchemService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------- 危化品档案 ----------

    async def list_chemicals(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[HazardousChemical], int]:
        conditions: list[ColumnElement[bool]] = [
            HazardousChemical.is_deleted.is_(False)
        ]
        if category:
            conditions.append(HazardousChemical.category == category)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    HazardousChemical.name.ilike(pattern),
                    HazardousChemical.alias.ilike(pattern),
                    HazardousChemical.cas_no.ilike(pattern),
                    HazardousChemical.search_text.ilike(pattern),
                )
            )

        total = (
            await self.db.execute(
                select(func.count()).select_from(HazardousChemical).where(*conditions)
            )
        ).scalar() or 0
        rows = await self.db.execute(
            select(HazardousChemical)
            .where(*conditions)
            .order_by(HazardousChemical.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total

    async def get_chemical(self, chemical_id: UUID) -> HazardousChemical | None:
        result = await self.db.execute(
            select(HazardousChemical).where(
                HazardousChemical.id == chemical_id,
                HazardousChemical.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_chemical_by_name(self, name: str) -> HazardousChemical | None:
        result = await self.db.execute(
            select(HazardousChemical).where(
                HazardousChemical.name == name,
                HazardousChemical.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_chemical(
        self, data: HazardousChemicalCreate, user_id: UUID | None = None
    ) -> HazardousChemical:
        if data.category not in _VALID_CATEGORIES:
            raise AppException(status_code=422, message="无效的危险性类别")
        if await self.get_chemical_by_name(data.name) is not None:
            raise AppException(status_code=409, message="同名气化学品档案已存在")
        chemical = HazardousChemical(
            **data.model_dump(),
            search_text=build_search_text(
                data.name, data.alias, data.cas_no, data.hazard_statements
            ),
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(chemical)
        await self.db.flush()
        return chemical

    async def update_chemical(
        self,
        chemical_id: UUID,
        data: HazardousChemicalUpdate,
        user_id: UUID | None = None,
    ) -> HazardousChemical:
        chemical = await self.get_chemical(chemical_id)
        if chemical is None:
            raise NotFoundException("危化品档案不存在")
        changes = data.model_dump(exclude_unset=True)
        if "category" in changes and changes["category"] not in _VALID_CATEGORIES:
            raise AppException(status_code=422, message="无效的危险性类别")
        new_name = changes.get("name", chemical.name)
        if new_name != chemical.name:
            existing = await self.get_chemical_by_name(new_name)
            if existing is not None and existing.id != chemical.id:
                raise AppException(status_code=409, message="同名气化学品档案已存在")
        for field, value in changes.items():
            setattr(chemical, field, value)
        chemical.search_text = build_search_text(
            chemical.name, chemical.alias, chemical.cas_no, chemical.hazard_statements
        )
        chemical.updated_by = user_id
        await self.db.flush()
        return chemical

    async def delete_chemical(self, chemical_id: UUID) -> bool:
        chemical = await self.get_chemical(chemical_id)
        if chemical is None:
            return False
        chemical.is_deleted = True
        # 级联软删该车间的存量记录，避免超储列表残留已删化学品
        result = await self.db.execute(
            select(ChemicalInventory).where(
                ChemicalInventory.chemical_id == chemical_id,
                ChemicalInventory.is_deleted.is_(False),
            )
        )
        for inventory in result.scalars():
            inventory.is_deleted = True
        await self.db.flush()
        return True

    async def set_msds_file(
        self,
        chemical_id: UUID,
        file_path: str,
        file_name: str,
        user_id: UUID | None = None,
    ) -> HazardousChemical:
        chemical = await self.get_chemical(chemical_id)
        if chemical is None:
            raise NotFoundException("危化品档案不存在")
        chemical.msds_file_path = file_path
        chemical.msds_file_name = file_name
        chemical.updated_by = user_id
        chemical.updated_at = datetime.now(UTC)
        await self.db.flush()
        return chemical

    # ---------- MSDS 多附件 ----------

    async def list_msds_files(
        self, chemical_id: UUID
    ) -> list[ChemicalMsdsAttachment]:
        if await self.get_chemical(chemical_id) is None:
            raise NotFoundException("危化品档案不存在")
        result = await self.db.execute(
            select(ChemicalMsdsAttachment)
            .where(
                ChemicalMsdsAttachment.chemical_id == chemical_id,
                ChemicalMsdsAttachment.is_deleted.is_(False),
            )
            .order_by(ChemicalMsdsAttachment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_msds_file(
        self, chemical_id: UUID, file_id: UUID
    ) -> ChemicalMsdsAttachment:
        result = await self.db.execute(
            select(ChemicalMsdsAttachment).where(
                ChemicalMsdsAttachment.id == file_id,
                ChemicalMsdsAttachment.chemical_id == chemical_id,
                ChemicalMsdsAttachment.is_deleted.is_(False),
            )
        )
        attachment = result.scalar_one_or_none()
        if attachment is None:
            raise NotFoundException("MSDS 附件")
        return attachment

    async def add_msds_file(
        self,
        chemical_id: UUID,
        *,
        file_name: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        user_id: UUID | None = None,
    ) -> ChemicalMsdsAttachment:
        if await self.get_chemical(chemical_id) is None:
            raise NotFoundException("危化品档案不存在")
        attachment = ChemicalMsdsAttachment(
            chemical_id=chemical_id,
            file_name=file_name,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=size_bytes,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(attachment)
        await self.db.flush()
        return attachment

    async def delete_msds_file(
        self, chemical_id: UUID, file_id: UUID
    ) -> bool:
        attachment = await self.get_msds_file(chemical_id, file_id)
        attachment.is_deleted = True
        await self.db.flush()
        return True

    # ---------- 车间存量 ----------

    async def list_inventories(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        workshop: str | None = None,
        chemical_id: UUID | None = None,
        over_limit_only: bool = False,
        keyword: str | None = None,
    ) -> tuple[list[ChemicalInventoryResponse], int]:
        conditions: list[ColumnElement[bool]] = [
            ChemicalInventory.is_deleted.is_(False)
        ]
        if workshop:
            conditions.append(ChemicalInventory.workshop == workshop)
        if chemical_id is not None:
            conditions.append(ChemicalInventory.chemical_id == chemical_id)
        if over_limit_only:
            conditions.append(
                ChemicalInventory.upper_limit.is_not(None)
                & (ChemicalInventory.quantity > ChemicalInventory.upper_limit)
            )
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                HazardousChemical.name.ilike(pattern)
                | HazardousChemical.alias.ilike(pattern)
                | ChemicalInventory.workshop.ilike(pattern)
            )

        base = (
            select(ChemicalInventory, HazardousChemical)
            .join(
                HazardousChemical,
                HazardousChemical.id == ChemicalInventory.chemical_id,
            )
            .where(*conditions, HazardousChemical.is_deleted.is_(False))
        )
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(ChemicalInventory)
                .join(
                    HazardousChemical,
                    HazardousChemical.id == ChemicalInventory.chemical_id,
                )
                .where(*conditions, HazardousChemical.is_deleted.is_(False))
            )
        ).scalar() or 0
        rows = await self.db.execute(
            base.order_by(
                ChemicalInventory.workshop.asc(), HazardousChemical.name.asc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [
            _inventory_response(inventory, chemical)
            for inventory, chemical in rows.all()
        ]
        return items, total

    async def get_inventory(
        self, inventory_id: UUID
    ) -> tuple[ChemicalInventory, HazardousChemical] | None:
        result = await self.db.execute(
            select(ChemicalInventory, HazardousChemical)
            .join(
                HazardousChemical,
                HazardousChemical.id == ChemicalInventory.chemical_id,
            )
            .where(
                ChemicalInventory.id == inventory_id,
                ChemicalInventory.is_deleted.is_(False),
            )
        )
        row = result.first()
        return (row[0], row[1]) if row else None

    async def get_inventory_by_chemical_workshop(
        self, chemical_id: UUID, workshop: str
    ) -> ChemicalInventory | None:
        result = await self.db.execute(
            select(ChemicalInventory).where(
                ChemicalInventory.chemical_id == chemical_id,
                ChemicalInventory.workshop == workshop,
                ChemicalInventory.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_inventory(
        self, data: ChemicalInventoryCreate, user_id: UUID | None = None
    ) -> ChemicalInventory:
        chemical = await self.get_chemical(data.chemical_id)
        if chemical is None:
            raise NotFoundException("危化品档案不存在")
        existing = await self.get_inventory_by_chemical_workshop(
            data.chemical_id, data.workshop
        )
        if existing is not None:
            raise AppException(status_code=409, message="该化学品在此车间已有存量记录")
        inventory = ChemicalInventory(
            chemical_id=data.chemical_id,
            workshop=data.workshop,
            quantity=data.quantity,
            upper_limit=data.upper_limit,
            unit=data.unit,
            remark=data.remark,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(inventory)
        await self.db.flush()
        return inventory

    async def update_inventory(
        self,
        inventory_id: UUID,
        data: ChemicalInventoryUpdate,
        user_id: UUID | None = None,
    ) -> ChemicalInventory:
        found = await self.get_inventory(inventory_id)
        if found is None:
            raise NotFoundException("存量记录不存在")
        inventory = found[0]
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(inventory, field, value)
        inventory.updated_by = user_id
        await self.db.flush()
        return inventory

    async def delete_inventory(self, inventory_id: UUID) -> bool:
        found = await self.get_inventory(inventory_id)
        if found is None:
            return False
        found[0].is_deleted = True
        await self.db.flush()
        return True

    async def get_inventory_response(
        self, inventory_id: UUID
    ) -> ChemicalInventoryResponse:
        found = await self.get_inventory(inventory_id)
        if found is None:
            raise NotFoundException("存量记录不存在")
        return _inventory_response(found[0], found[1])

    async def get_over_limit_top(
        self, *, limit: int = 10
    ) -> list[ChemicalInventoryResponse]:
        rows = await self.db.execute(
            select(ChemicalInventory, HazardousChemical)
            .join(
                HazardousChemical,
                HazardousChemical.id == ChemicalInventory.chemical_id,
            )
            .where(
                ChemicalInventory.is_deleted.is_(False),
                HazardousChemical.is_deleted.is_(False),
                ChemicalInventory.upper_limit.is_not(None),
                ChemicalInventory.quantity > ChemicalInventory.upper_limit,
            )
            .order_by(
                (ChemicalInventory.quantity / ChemicalInventory.upper_limit).desc()
            )
            .limit(limit)
        )
        return [
            _inventory_response(inventory, chemical)
            for inventory, chemical in rows.all()
        ]

    async def get_stats(self) -> HazchemStatsResponse:
        from app.modules.safety.page_tables import HAZCHEM_PAGE_KEY
        from app.modules.safety.service.page_table import (
            collect_mirror_over_limit_rows,
        )

        chemicals_total = (
            await self.db.execute(
                select(func.count())
                .select_from(HazardousChemical)
                .where(HazardousChemical.is_deleted.is_(False))
            )
        ).scalar() or 0
        # MSDS 已上传 = 至少挂一个附件的未删档案数（旧单文件数据已由迁移入附件表）
        msds_uploaded = (
            await self.db.execute(
                select(func.count(func.distinct(ChemicalMsdsAttachment.chemical_id)))
                .select_from(ChemicalMsdsAttachment)
                .join(
                    HazardousChemical,
                    HazardousChemical.id == ChemicalMsdsAttachment.chemical_id,
                )
                .where(
                    ChemicalMsdsAttachment.is_deleted.is_(False),
                    HazardousChemical.is_deleted.is_(False),
                )
            )
        ).scalar() or 0

        # 存量统计：统计表镜像配置了超储列时走镜像口径，否则本地库存口径
        mirror_rows = await collect_mirror_over_limit_rows(self.db, HAZCHEM_PAGE_KEY)
        if mirror_rows is not None:
            return HazchemStatsResponse(
                chemicals_total=chemicals_total,
                msds_uploaded=msds_uploaded,
                inventory=ChemicalInventoryStatsResponse(
                    total_entries=len(mirror_rows),
                    over_limit_count=sum(
                        1 for row in mirror_rows if row.over_limit
                    ),
                    limited_count=sum(
                        1 for row in mirror_rows if row.upper_limit is not None
                    ),
                    by_category={},  # 统计表列不承诺档案类别枚举，镜像口径不提供
                ),
            )

        rows = (
            await self.db.execute(
                select(
                    HazardousChemical.category,
                    ChemicalInventory.quantity,
                    ChemicalInventory.upper_limit,
                )
                .join(
                    HazardousChemical,
                    HazardousChemical.id == ChemicalInventory.chemical_id,
                )
                .where(
                    ChemicalInventory.is_deleted.is_(False),
                    HazardousChemical.is_deleted.is_(False),
                )
            )
        ).all()
        by_category: dict[str, int] = {}
        over_limit = 0
        limited = 0
        for category, quantity, upper_limit in rows:
            by_category[category] = by_category.get(category, 0) + 1
            if upper_limit is not None:
                limited += 1
                if quantity > upper_limit:
                    over_limit += 1
        return HazchemStatsResponse(
            chemicals_total=chemicals_total,
            msds_uploaded=msds_uploaded,
            inventory=ChemicalInventoryStatsResponse(
                total_entries=len(rows),
                over_limit_count=over_limit,
                limited_count=limited,
                by_category=by_category,
            ),
        )


def _inventory_response(
    inventory: ChemicalInventory, chemical: HazardousChemical
) -> ChemicalInventoryResponse:
    over = inventory_over_limit(
        float(inventory.quantity), _as_float(inventory.upper_limit)
    )
    over_pct: float | None = None
    if over and inventory.upper_limit:
        upper = _as_float(inventory.upper_limit) or 0.0
        if upper > 0:
            over_pct = round((float(inventory.quantity) - upper) / upper * 100, 1)
    return ChemicalInventoryResponse(
        id=inventory.id,
        chemical_id=inventory.chemical_id,
        chemical_name=chemical.name,
        category=chemical.category,
        workshop=inventory.workshop,
        quantity=float(inventory.quantity),
        upper_limit=_as_float(inventory.upper_limit),
        over_limit=over,
        over_pct=over_pct,
        unit=inventory.unit,
        remark=inventory.remark,
        updated_at=inventory.updated_at,
    )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))
