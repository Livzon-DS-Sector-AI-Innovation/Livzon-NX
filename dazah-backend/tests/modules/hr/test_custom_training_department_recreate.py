"""自定义培训部门同名重建（软删除后重新添加）测试。

回归：`hr_custom_training_departments` 曾用全量唯一索引（含软删除行），
删过的部门再次添加会撞唯一键并抛 IntegrityError（接口 500，前端只看到
Server Component 的通用报错）。这里同时锁定索引声明与真实库上的重建行为。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import HrCustomTrainingDepartment
from app.modules.hr.repository import TrainingLedgerRepository

_NAME = "重名验证部门"


def test_name_index_is_partial_unique() -> None:
    """名字唯一索引必须带 is_deleted = false 条件（部分唯一索引）。"""
    index = next(
        item
        for item in HrCustomTrainingDepartment.__table__.indexes
        if item.name == "ix_hr_custom_training_depts_name"
    )
    assert index.unique is True
    assert "is_deleted" in str(index.dialect_options["postgresql"]["where"])


@pytest.mark.asyncio
async def test_recreate_custom_department_after_soft_delete(
    db_session: AsyncSession,
) -> None:
    """软删除后同名部门可重新添加，并恢复原行（不产生重复的未删除行）。"""
    repo = TrainingLedgerRepository(db_session)

    created = await repo.add_custom_training_department(_NAME)
    assert created.is_deleted is False
    first_id = created.id

    assert await repo.delete_custom_training_department(_NAME) is True

    again = await repo.add_custom_training_department(_NAME)
    assert again.is_deleted is False
    assert again.id == first_id  # 恢复原行，不新增

    assert (await repo.list_custom_training_departments()).count(_NAME) == 1
