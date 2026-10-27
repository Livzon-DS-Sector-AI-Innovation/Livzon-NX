"""应急处置卡：车间/岗位级事故现场处置卡的查询与维护。

数据由种子迁移从各车间应急资料导入（98 张卡），页面按车间/岗位浏览；
支持按类型、关键字筛选与基本维护（新增/编辑/软删除）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import EmergencyCard
from app.modules.safety.schemas.emergency_cards import (
    EmergencyCardCreate,
    EmergencyCardStatsResponse,
    EmergencyCardUpdate,
    EmergencyCardWorkshopStat,
)


def build_search_text(
    title: str,
    subject: str,
    accident_type: str,
    workshop: str,
    position: str,
    steps: list[dict[str, Any]],
    phones: str,
) -> str:
    parts = [title, subject, accident_type, workshop, position, phones]
    for step in steps:
        parts.extend(
            str(step.get(key) or "")
            for key in ("step", "action", "person")
        )
    return " ".join(part for part in parts if part)


def _steps_raw(steps: list[Any] | None) -> list[dict[str, Any]]:
    return [step for step in (steps or []) if isinstance(step, dict)]


class EmergencyCardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_cards(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        workshop: str | None = None,
        position: str | None = None,
        accident_type: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[EmergencyCard], int]:
        conditions: list[ColumnElement[bool]] = [EmergencyCard.is_deleted.is_(False)]
        if workshop:
            conditions.append(EmergencyCard.workshop == workshop)
        if position:
            conditions.append(EmergencyCard.position == position)
        if accident_type:
            conditions.append(EmergencyCard.accident_type == accident_type)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    EmergencyCard.title.ilike(pattern),
                    EmergencyCard.search_text.ilike(pattern),
                )
            )

        total_result = await self.db.execute(
            select(func.count())
            .select_from(EmergencyCard)
            .where(*conditions)
        )
        total = total_result.scalar() or 0

        result = await self.db.execute(
            select(EmergencyCard)
            .where(*conditions)
            .order_by(
                EmergencyCard.workshop.asc(),
                EmergencyCard.sort_order.asc(),
                EmergencyCard.created_at.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_card(self, card_id: UUID) -> EmergencyCard | None:
        result = await self.db.execute(
            select(EmergencyCard).where(
                EmergencyCard.id == card_id,
                EmergencyCard.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_title(
        self, workshop: str, position: str, title: str
    ) -> EmergencyCard | None:
        result = await self.db.execute(
            select(EmergencyCard).where(
                EmergencyCard.workshop == workshop,
                EmergencyCard.position == position,
                EmergencyCard.title == title,
                EmergencyCard.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_card(
        self, data: EmergencyCardCreate, user_id: UUID | None = None
    ) -> EmergencyCard:
        existing = await self.get_by_title(data.workshop, data.position, data.title)
        if existing is not None:
            raise AppException(
                status_code=409,
                message="同车间/岗位下已存在同名应急处置卡",
            )
        card = EmergencyCard(
            workshop=data.workshop,
            position=data.position,
            title=data.title,
            subject=data.subject or data.title,
            accident_type=data.accident_type or "综合",
            steps=[step.model_dump() for step in data.steps],
            extras=[extra.model_dump() for extra in data.extras],
            phones=data.phones,
            risks=data.risks,
            precautions=data.precautions,
            search_text=build_search_text(
                data.title,
                data.subject or data.title,
                data.accident_type or "综合",
                data.workshop,
                data.position,
                _steps_raw([step.model_dump() for step in data.steps]),
                data.phones,
            ),
            sort_order=data.sort_order,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(card)
        await self.db.flush()
        return card

    async def update_card(
        self,
        card_id: UUID,
        data: EmergencyCardUpdate,
        user_id: UUID | None = None,
    ) -> EmergencyCard:
        card = await self.get_card(card_id)
        if card is None:
            raise NotFoundException("应急处置卡不存在")

        changes = data.model_dump(exclude_unset=True)
        if not changes:
            return card

        new_title = changes.get("title", card.title)
        new_workshop = changes.get("workshop", card.workshop)
        new_position = changes.get("position", card.position)
        if (new_workshop, new_position, new_title) != (
            card.workshop,
            card.position,
            card.title,
        ):
            existing = await self.get_by_title(
                new_workshop, new_position, new_title
            )
            if existing is not None and existing.id != card.id:
                raise AppException(
                    status_code=409,
                    message="同车间/岗位下已存在同名应急处置卡",
                )

        for field, value in changes.items():
            if field == "steps":
                card.steps = [step for step in value if isinstance(step, dict)]
            elif field == "extras":
                card.extras = [extra for extra in value if isinstance(extra, dict)]
            else:
                setattr(card, field, value)

        card.search_text = build_search_text(
            card.title,
            card.subject or card.title,
            card.accident_type,
            card.workshop,
            card.position,
            _steps_raw(card.steps),
            card.phones,
        )
        card.updated_by = user_id
        await self.db.flush()
        return card

    async def delete_card(self, card_id: UUID) -> bool:
        card = await self.get_card(card_id)
        if card is None:
            return False
        card.is_deleted = True
        await self.db.flush()
        return True

    async def get_stats(self) -> EmergencyCardStatsResponse:
        result = await self.db.execute(
            select(
                EmergencyCard.workshop,
                EmergencyCard.position,
                EmergencyCard.accident_type,
            ).where(EmergencyCard.is_deleted.is_(False))
        )
        rows = result.all()

        workshop_order: list[str] = []
        workshop_positions: dict[str, list[str]] = {}
        type_counts: dict[str, int] = {}
        for workshop, position, accident_type in rows:
            if workshop not in workshop_positions:
                workshop_order.append(workshop)
                workshop_positions[workshop] = []
            if position and position not in workshop_positions[workshop]:
                workshop_positions[workshop].append(position)
            type_counts[accident_type] = type_counts.get(accident_type, 0) + 1

        workshops = [
            EmergencyCardWorkshopStat(
                workshop=name,
                total=sum(1 for w, _, _ in rows if w == name),
                positions=sorted(workshop_positions[name]),
            )
            for name in workshop_order
        ]
        accident_types = [
            name
            for name, _ in sorted(type_counts.items(), key=lambda kv: -kv[1])
        ]
        return EmergencyCardStatsResponse(
            total=len(rows),
            workshops=workshops,
            accident_types=accident_types,
        )
