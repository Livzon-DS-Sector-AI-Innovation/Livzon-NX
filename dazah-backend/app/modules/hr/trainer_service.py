"""培训师清单 Service."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import Trainer
from app.modules.hr.trainer_repository import TrainerRepository


class TrainerService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = TrainerRepository(session)
        self.session = session

    async def list_trainers(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        department: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[Trainer], int]:
        return await self.repo.list_trainers(
            page=page,
            page_size=page_size,
            keyword=keyword,
            department=department,
            dept_alias_set=dept_alias_set,
        )

    async def import_trainers(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """按 姓名+部门 去重导入：已存在则更新，否则新增。

        导入文件中的部门写法（如 201二车间（多拉）/动力科）落库前归一为培训规范名。
        """
        from app.modules.hr.training_dept_resolver import resolve_training_department

        created = 0
        updated = 0
        skipped = 0
        for row in rows:
            name = (row.get("name") or "").strip()
            if not name:
                skipped += 1
                continue
            raw_dept = (row.get("department") or "").strip()
            if raw_dept:
                row["department"] = await resolve_training_department(
                    self.session, raw_dept
                )
            else:
                row["department"] = None
            existing = await self.repo.find_by_name_and_department(
                name, row.get("department")
            )
            if existing:
                changes = {k: v for k, v in row.items() if v is not None}
                await self.repo.update(existing, changes)
                updated += 1
            else:
                await self.repo.create(Trainer(**row))
                created += 1
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "total": len(rows),
        }

    async def get_by_id(self, trainer_id: UUID) -> Trainer | None:
        return await self.repo.get_by_id(trainer_id)

    async def create(self, data: dict[str, Any]) -> Trainer:
        trainer = Trainer(**data)
        return await self.repo.create(trainer)

    async def update(self, trainer_id: UUID, data: dict[str, Any]) -> Trainer | None:
        trainer = await self.repo.get_by_id(trainer_id)
        if not trainer:
            return None
        return await self.repo.update(trainer, data)

    async def delete(self, trainer_id: UUID) -> bool:
        trainer = await self.repo.get_by_id(trainer_id)
        if not trainer:
            return False
        await self.repo.delete(trainer)
        return True
