"""危化品与 MSDS：危化品档案、车间存量（超储预警）与 MSDS 附件。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import ChemicalInventory, HazardousChemical
from app.modules.safety.schemas.hazchem import (
    ChemicalInventoryCreate,
    ChemicalInventoryResponse,
    ChemicalInventoryStatsResponse,
    ChemicalInventoryUpdate,
    HazardousChemicalCreate,
    HazardousChemicalUpdate,
    HazchemStatsResponse,
)

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
        chemicals_total = (
            await self.db.execute(
                select(func.count())
                .select_from(HazardousChemical)
                .where(HazardousChemical.is_deleted.is_(False))
            )
        ).scalar() or 0
        msds_uploaded = (
            await self.db.execute(
                select(func.count())
                .select_from(HazardousChemical)
                .where(
                    HazardousChemical.is_deleted.is_(False),
                    HazardousChemical.msds_file_path != "",
                )
            )
        ).scalar() or 0

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
        upper = _as_float(inventory.upper_limit)
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
    return float(value) if value is not None else None
