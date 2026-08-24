"""岗位培训映射 Repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import PositionTrainingMapping


class PositionTrainingMappingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_department(
        self, department: str
    ) -> list[PositionTrainingMapping]:
        """按部门查询所有映射。"""
        query = (
            select(PositionTrainingMapping)
            .where(
                PositionTrainingMapping.is_deleted.is_(False),
                PositionTrainingMapping.department == department,
            )
            .order_by(PositionTrainingMapping.employee_position)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_mapping(
        self, department: str, employee_position: str
    ) -> PositionTrainingMapping | None:
        """查询指定部门+员工岗位的映射。"""
        query = select(PositionTrainingMapping).where(
            PositionTrainingMapping.is_deleted.is_(False),
            PositionTrainingMapping.department == department,
            PositionTrainingMapping.employee_position == employee_position,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, mapping: PositionTrainingMapping) -> PositionTrainingMapping:
        self.session.add(mapping)
        await self.session.flush()
        await self.session.refresh(mapping)
        return mapping

    async def delete(self, mapping_id: UUID) -> bool:
        mapping = await self.get_by_id(mapping_id)
        if not mapping:
            return False
        mapping.is_deleted = True
        await self.session.flush()
        return True

    async def get_by_id(self, mapping_id: UUID) -> PositionTrainingMapping | None:
        query = select(PositionTrainingMapping).where(
            PositionTrainingMapping.id == mapping_id,
            PositionTrainingMapping.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
