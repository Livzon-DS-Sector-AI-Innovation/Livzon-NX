"""岗位培训清单 Service."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import PositionTrainingList, PositionTrainingListItem
from app.modules.hr.position_training_repository import PositionTrainingListRepository


class PositionTrainingListService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = PositionTrainingListRepository(session)

    async def list_lists(
        self,
        page: int = 1,
        page_size: int = 20,
        department: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[PositionTrainingList], int]:
        return await self.repo.list_lists(
            page=page,
            page_size=page_size,
            department=department,
            dept_alias_set=dept_alias_set,
        )

    async def get_by_id(self, list_id: UUID) -> PositionTrainingList | None:
        return await self.repo.get_by_id(list_id)

    async def create(
        self, data: dict[str, Any], items_data: list[dict[str, Any]] | None = None
    ) -> PositionTrainingList:
        list_obj = PositionTrainingList(**data)
        list_obj = await self.repo.create(list_obj)

        if items_data:
            for idx, item_data in enumerate(items_data):
                item = PositionTrainingListItem(
                    list_id=list_obj.id,
                    sort_order=idx,
                    **item_data,
                )
                self.repo.session.add(item)
            await self.repo.session.flush()

        return list_obj

    async def update(
        self, list_id: UUID, data: dict[str, Any]
    ) -> PositionTrainingList | None:
        list_obj = await self.repo.get_by_id(list_id)
        if not list_obj:
            return None
        return await self.repo.update(list_obj, data)

    async def delete(self, list_id: UUID) -> bool:
        list_obj = await self.repo.get_by_id(list_id)
        if not list_obj:
            return False
        await self.repo.delete(list_obj)
        return True

    async def batch_update_items(
        self, list_id: UUID, items_data: list[dict[str, Any]]
    ) -> list[PositionTrainingListItem]:
        return await self.repo.batch_update_items(list_id, items_data)

    async def list_positions_by_department(self, department: str) -> list[str]:
        """获取指定部门的所有岗位名称（去重）。"""
        return await self.repo.list_distinct_positions(department)
