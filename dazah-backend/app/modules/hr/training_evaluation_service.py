"""培训评估表 Service."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import TrainingEvaluation
from app.modules.hr.training_evaluation_repository import TrainingEvaluationRepository


class TrainingEvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = TrainingEvaluationRepository(session)

    async def list_evaluations(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> tuple[list[TrainingEvaluation], int]:
        return await self.repo.list_evaluations(
            page=page, page_size=page_size, keyword=keyword
        )

    async def get_by_id(self, evaluation_id: UUID) -> TrainingEvaluation | None:
        return await self.repo.get_by_id(evaluation_id)

    async def create(self, data: dict[str, Any]) -> TrainingEvaluation:
        evaluation = TrainingEvaluation(**data)
        return await self.repo.create(evaluation)

    async def update(
        self, evaluation_id: UUID, data: dict[str, Any]
    ) -> TrainingEvaluation | None:
        evaluation = await self.repo.get_by_id(evaluation_id)
        if not evaluation:
            return None
        return await self.repo.update(evaluation, data)

    async def delete(self, evaluation_id: UUID) -> bool:
        evaluation = await self.repo.get_by_id(evaluation_id)
        if not evaluation:
            return False
        await self.repo.delete(evaluation)
        return True
