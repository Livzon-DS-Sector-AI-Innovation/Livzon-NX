"""培训师清单 Repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import Trainer
from app.modules.hr.training_dept_resolver import training_dept_aliases_of


class TrainerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_trainers(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        department: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[Trainer], int]:
        query = select(Trainer).where(Trainer.is_deleted.is_(False))
        count_query = (
            select(func.count())
            .select_from(Trainer)
            .where(Trainer.is_deleted.is_(False))
        )

        if keyword:
            query = query.where(Trainer.name.ilike(f"%{keyword}%"))
            count_query = count_query.where(Trainer.name.ilike(f"%{keyword}%"))

        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合
            query = query.where(Trainer.department.in_(dept_alias_set))
            count_query = count_query.where(Trainer.department.in_(dept_alias_set))
        elif department:
            # 部门归一匹配：选中部门（规范名）展开为全部别名（如 201二车间（MC）→
            # 裸名/霉酚酸/201三车间）
            dept_values = await training_dept_aliases_of(self.session, department)
            query = query.where(Trainer.department.in_(dept_values))
            count_query = count_query.where(Trainer.department.in_(dept_values))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Trainer.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        trainers = list(result.scalars().all())
        return trainers, total

    async def find_by_name_and_department(
        self, name: str, department: str | None
    ) -> Trainer | None:
        conditions = [Trainer.is_deleted.is_(False), Trainer.name == name]
        if department:
            conditions.append(Trainer.department == department)
        else:
            conditions.append(Trainer.department.is_(None))
        result = await self.session.execute(select(Trainer).where(*conditions))
        return result.scalars().first()

    async def get_by_id(self, trainer_id: UUID) -> Trainer | None:
        query = select(Trainer).where(
            Trainer.id == trainer_id, Trainer.is_deleted.is_(False)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, trainer: Trainer) -> Trainer:
        self.session.add(trainer)
        await self.session.flush()
        return trainer

    async def update(self, trainer: Trainer, data: dict[str, Any]) -> Trainer:
        for key, value in data.items():
            if value is not None:
                setattr(trainer, key, value)
        await self.session.flush()
        return trainer

    async def delete(self, trainer: Trainer) -> None:
        trainer.is_deleted = True
        await self.session.flush()
