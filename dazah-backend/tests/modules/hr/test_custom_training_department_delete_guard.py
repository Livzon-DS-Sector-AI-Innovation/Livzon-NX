"""自定义培训部门删除守卫测试。

回归：删除守卫曾用「全部部门 − 自定义部门」做集合差，于是**既是自定义行、
又由其它来源（人员配置/台账等）产生的部门**会被判成"非数据驱动"而放行：
接口提示删除成功，但部门仍出现在列表里（此时它由数据驱动，连删除入口都没有）。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.hr.models import HrCustomTrainingDepartment, TrainingPersonnelConfig
from app.modules.hr.repository import TrainingLedgerRepository
from app.modules.hr.service import TrainingLedgerService

_NAME = "守卫验证部门"


async def _live_custom_row(
    session: AsyncSession,
) -> HrCustomTrainingDepartment | None:
    return (
        (
            await session.execute(
                select(HrCustomTrainingDepartment).where(
                    HrCustomTrainingDepartment.name == _NAME,
                    HrCustomTrainingDepartment.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .first()
    )


@pytest.mark.asyncio
async def test_delete_refused_when_also_produced_by_personnel_config(
    db_session: AsyncSession,
) -> None:
    """同名部门由「人员配置」产生时删除被拒，且自定义行保持未删除。"""
    service = TrainingLedgerService(db_session)
    repo = TrainingLedgerRepository(db_session)

    await repo.add_custom_training_department(_NAME)
    db_session.add(
        TrainingPersonnelConfig(
            level="部门级",
            department=_NAME,
            config_name="守卫用例配置",
            personnel=[{"name": "测试员", "department": _NAME}],
            remarks="",
        )
    )
    await db_session.flush()

    with pytest.raises(AppException) as exc_info:
        await service.delete_custom_training_department(_NAME)

    assert exc_info.value.status_code == 400
    assert _NAME in exc_info.value.message
    assert await _live_custom_row(db_session) is not None  # 未被误删


@pytest.mark.asyncio
async def test_delete_allowed_when_only_custom_department(
    db_session: AsyncSession,
) -> None:
    """只有自定义行产生该部门时仍可删除。"""
    service = TrainingLedgerService(db_session)
    repo = TrainingLedgerRepository(db_session)

    await repo.add_custom_training_department(_NAME)

    assert await service.delete_custom_training_department(_NAME) is True
    assert await _live_custom_row(db_session) is None
