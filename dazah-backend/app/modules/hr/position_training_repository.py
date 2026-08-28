"""岗位培训清单 Repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.hr.models import PositionTrainingList, PositionTrainingListItem
from app.modules.hr.training_dept_resolver import training_dept_aliases_of


class PositionTrainingListRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_lists(
        self,
        page: int = 1,
        page_size: int = 20,
        department: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[PositionTrainingList], int]:
        query = select(PositionTrainingList).where(
            PositionTrainingList.is_deleted.is_(False)
        )
        count_query = (
            select(func.count())
            .select_from(PositionTrainingList)
            .where(PositionTrainingList.is_deleted.is_(False))
        )

        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合
            query = query.where(PositionTrainingList.department.in_(dept_alias_set))
            count_query = count_query.where(
                PositionTrainingList.department.in_(dept_alias_set)
            )
        elif department:
            # 部门归一匹配：选中部门（规范名）展开为全部别名（如 201二车间（MC）→
            # 裸名/霉酚酸/201三车间）
            dept_values = await training_dept_aliases_of(self.session, department)
            query = query.where(PositionTrainingList.department.in_(dept_values))
            count_query = count_query.where(
                PositionTrainingList.department.in_(dept_values)
            )

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.options(selectinload(PositionTrainingList.items))
        query = query.order_by(PositionTrainingList.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        lists = list(result.scalars().unique().all())
        return lists, total

    async def get_by_id(self, list_id: UUID) -> PositionTrainingList | None:
        query = (
            select(PositionTrainingList)
            .where(
                PositionTrainingList.id == list_id,
                PositionTrainingList.is_deleted.is_(False),
            )
            .options(selectinload(PositionTrainingList.items))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, list_obj: PositionTrainingList) -> PositionTrainingList:
        self.session.add(list_obj)
        await self.session.flush()
        return list_obj

    async def update(
        self, list_obj: PositionTrainingList, data: dict[str, Any]
    ) -> PositionTrainingList:
        for key, value in data.items():
            if value is not None:
                setattr(list_obj, key, value)
        await self.session.flush()
        return list_obj

    async def delete(self, list_obj: PositionTrainingList) -> None:
        list_obj.is_deleted = True
        await self.session.flush()

    async def batch_update_items(
        self, list_id: UUID, items_data: list[dict[str, Any]]
    ) -> list[PositionTrainingListItem]:
        """批量更新清单明细（全量替换）"""
        # 软删除旧明细
        old_query = select(PositionTrainingListItem).where(
            PositionTrainingListItem.list_id == list_id,
            PositionTrainingListItem.is_deleted.is_(False),
        )
        old_result = await self.session.execute(old_query)
        old_items = old_result.scalars().all()
        for item in old_items:
            item.is_deleted = True

        # 创建新明细
        new_items = []
        for idx, item_data in enumerate(items_data):
            item = PositionTrainingListItem(
                list_id=list_id,
                sort_order=idx,
                **item_data,
            )
            self.session.add(item)
            new_items.append(item)

        await self.session.flush()
        return new_items

    async def list_distinct_departments(
        self, dept_alias_set: set[str] | None = None
    ) -> list[str]:
        """获取所有未删除清单的部门名（去重）。"""
        from sqlalchemy import distinct

        query = select(distinct(PositionTrainingList.department)).where(
            PositionTrainingList.is_deleted.is_(False),
        )
        if dept_alias_set is not None:
            # 部门级数据隔离：仅返回可见部门
            query = query.where(PositionTrainingList.department.in_(dept_alias_set))
        query = query.order_by("department")
        result = await self.session.execute(query)
        return [row[0] for row in result.all()]

    async def list_distinct_positions(self, department: str) -> list[str]:
        """获取指定部门的所有岗位名称（去重），部门名按别名集合匹配（覆盖清单中的裸名等写法）。"""
        from sqlalchemy import distinct

        dept_values = await training_dept_aliases_of(self.session, department)
        query = (
            select(distinct(PositionTrainingList.position))
            .where(
                PositionTrainingList.is_deleted.is_(False),
                PositionTrainingList.department.in_(dept_values),
            )
            .order_by(PositionTrainingList.position)
        )
        result = await self.session.execute(query)
        return [row[0] for row in result.all()]
