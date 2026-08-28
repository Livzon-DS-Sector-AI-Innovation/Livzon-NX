"""岗位培训映射 Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import PositionTrainingMapping
from app.modules.hr.position_training_mapping_repository import (
    PositionTrainingMappingRepository,
)
from app.modules.hr.schemas import PositionTrainingMappingCreate


class PositionTrainingMappingService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = PositionTrainingMappingRepository(session)

    async def list_mappings(self, department: str) -> list[PositionTrainingMapping]:
        """按部门查询映射列表。"""
        return await self.repo.list_by_department(department)

    async def get_mapping(
        self, department: str, employee_position: str
    ) -> PositionTrainingMapping | None:
        """查询映射。"""
        return await self.repo.get_mapping(department, employee_position)

    async def create_mapping(
        self, data: PositionTrainingMappingCreate, user_id: UUID | None
    ) -> PositionTrainingMapping:
        """创建或更新映射（同一部门+员工岗位只保留一条）。"""
        existing = await self.repo.get_mapping(data.department, data.employee_position)
        if existing:
            # 更新现有映射
            existing.training_position = data.training_position
            existing.updated_by = user_id
            await self.repo.session.flush()
            await self.repo.session.refresh(existing)
            return existing
        else:
            # 创建新映射
            mapping = PositionTrainingMapping(
                department=data.department,
                employee_position=data.employee_position,
                training_position=data.training_position,
                created_by=user_id,
                updated_by=user_id,
            )
            return await self.repo.create(mapping)

    async def delete_mapping(self, mapping_id: UUID) -> bool:
        """删除映射。"""
        return await self.repo.delete(mapping_id)
