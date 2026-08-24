"""培训评估表 Repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import TrainingEvaluation


class TrainingEvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_evaluations(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> tuple[list[TrainingEvaluation], int]:
        query = select(TrainingEvaluation).where(
            TrainingEvaluation.is_deleted.is_(False)
        )
        count_query = (
            select(func.count())
            .select_from(TrainingEvaluation)
            .where(TrainingEvaluation.is_deleted.is_(False))
        )

        if keyword:
            query = query.where(
                TrainingEvaluation.training_content.ilike(f"%{keyword}%")
            )
            count_query = count_query.where(
                TrainingEvaluation.training_content.ilike(f"%{keyword}%")
            )

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(TrainingEvaluation.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        evaluations = list(result.scalars().all())
        return evaluations, total

    async def get_by_id(self, evaluation_id: UUID) -> TrainingEvaluation | None:
        query = select(TrainingEvaluation).where(
            TrainingEvaluation.id == evaluation_id,
            TrainingEvaluation.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, evaluation: TrainingEvaluation) -> TrainingEvaluation:
        self.session.add(evaluation)
        await self.session.flush()
        return evaluation

    async def update(
        self, evaluation: TrainingEvaluation, data: dict[str, Any]
    ) -> TrainingEvaluation:
        for key, value in data.items():
            if value is not None:
                setattr(evaluation, key, value)
        await self.session.flush()
        return evaluation

    async def delete(self, evaluation: TrainingEvaluation) -> None:
        evaluation.is_deleted = True
        await self.session.flush()
