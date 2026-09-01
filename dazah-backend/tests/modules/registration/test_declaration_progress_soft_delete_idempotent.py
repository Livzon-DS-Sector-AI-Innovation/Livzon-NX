"""回归：申报进度版本同组同版本二次软删除不再触发唯一冲突。

UQ 已改为 partial unique index（仅约束 is_deleted=false 行），
同一 (record_group_id, version_number) 允许多条软删历史共存。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.models import RegistrationDeclarationProgressVersion


async def _seed_version(db_session: AsyncSession, group_id) -> None:
    db_session.add(
        RegistrationDeclarationProgressVersion(
            record_group_id=group_id,
            version_number=1,
            sheet_key="domestic-associated-review",
            sheet_name="国内注册（关联审评机制）",
            sheet_title="国内注册（关联审评机制）",
            source_sequence=1,
            values_data={"项目名称": "测试项目"},
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_double_soft_delete_same_group_version_allowed(
    db_session: AsyncSession,
) -> None:
    from sqlalchemy import select, update

    group_id = uuid4()
    await _seed_version(db_session, group_id)
    await db_session.commit()

    try:
        # 第一次软删
        await db_session.execute(
            update(RegistrationDeclarationProgressVersion).values(is_deleted=True)
            .execution_options(synchronize_session=False)
        )
        await db_session.commit()
        # 同组同版本再次插入并软删（旧 UQ 含 is_deleted 时会 IntegrityError）
        await _seed_version(db_session, group_id)
        await db_session.commit()
        await db_session.execute(
            update(RegistrationDeclarationProgressVersion).values(is_deleted=True)
            .execution_options(synchronize_session=False)
        )
        await db_session.commit()

        remaining = (
            await db_session.execute(
                select(RegistrationDeclarationProgressVersion).where(
                    RegistrationDeclarationProgressVersion.record_group_id
                    == group_id
                )
            )
        ).scalars().all()
        assert len(remaining) == 2, "两条软删历史应共存"
    finally:
        await db_session.execute(
            delete(RegistrationDeclarationProgressVersion)
        )
        await db_session.commit()
