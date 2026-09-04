"""培训师清单更新规则测试（PUT 编辑修复）.

口径：
- PUT 按「显式出现的字段」应用：显式传 null 即清空字段，缺省字段保留原值；
- 导入路径（import_trainers）对 None 预过滤，空单元格不清空已有字段。
"""

from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.modules.hr.models import Trainer

_URL = "/api/v1/hr/trainers"


@pytest.fixture(autouse=True)
async def _share_db_session(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncIterator[None]:
    """API 调用与测试种子共用同一会话（conftest 全回滚）。"""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def _trainer(**overrides) -> Trainer:
    data = dict(
        id=uuid4(),
        name="测培训师",
        department="SPEC测试车间",
        position="高级工程师",
        approval_date=date(2025, 3, 21),
        remarks="原备注",
    )
    data.update(overrides)
    return Trainer(**data)


async def _seed(session: AsyncSession, trainer: Trainer) -> Trainer:
    session.add(trainer)
    await session.flush()
    return trainer


@pytest.mark.asyncio
async def test_put_explicit_null_clears_field(
    client: AsyncClient, db_session: AsyncSession
):
    """显式传 null 清空字段（修复：清空保存后旧值残留）。"""
    trainer = await _seed(db_session, _trainer())

    resp = await client.put(
        f"{_URL}/{trainer.id}",
        json={"name": trainer.name, "remarks": None},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["remarks"] is None
    await db_session.refresh(trainer)
    assert trainer.remarks is None
    assert trainer.department == "SPEC测试车间"  # 未出现的字段保留


@pytest.mark.asyncio
async def test_put_partial_update_keeps_other_fields(
    client: AsyncClient, db_session: AsyncSession
):
    """部分更新：只传出现的字段，其余不受影响。"""
    trainer = await _seed(db_session, _trainer())

    resp = await client.put(
        f"{_URL}/{trainer.id}",
        json={"name": "改名字", "position": "新岗位"},
    )
    assert resp.status_code == 200
    await db_session.refresh(trainer)
    assert trainer.name == "改名字"
    assert trainer.position == "新岗位"
    assert trainer.remarks == "原备注"
    assert trainer.approval_date == date(2025, 3, 21)


@pytest.mark.asyncio
async def test_import_empty_cell_keeps_existing_value(db_session: AsyncSession):
    """导入去重更新时空单元格（None）不清空已有字段（回归保护）。"""
    trainer = await _seed(db_session, _trainer())

    from app.modules.hr.trainer_service import TrainerService

    rows = [
        {
            "name": trainer.name,
            "department": trainer.department,
            "position": None,  # Excel 空单元格 → None
            "approval_date": None,
            "approver": None,
            "remarks": None,
        }
    ]
    result = await TrainerService(db_session).import_trainers(rows)
    assert result["updated"] == 1

    await db_session.refresh(trainer)
    assert trainer.position == "高级工程师"  # None 未清空
    assert trainer.approval_date == date(2025, 3, 21)
    assert trainer.remarks == "原备注"
