"""QA 候选查询回归：部门条件必须在多部门聚合前执行，无数据库连接。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppException
from app.modules.quality.service.person_directory import get_qa_reminder_recipients


@pytest.mark.asyncio
async def test_qa_department_filter_precedes_multi_department_aggregation() -> None:
    row = SimpleNamespace(
        open_id="ou_multi",
        name="兼属QA",
        department="质量保证部",
        job_title=None,
        email=None,
        mobile=None,
        enterprise_email="qa@example.com",
        avatar_url=None,
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=Mock(all=lambda: [row])))
    recipients = await get_qa_reminder_recipients(db)
    assert recipients == [
        {
            "open_id": "ou_multi",
            "name": "兼属QA",
            "department": "质量保证部",
            "enterprise_email": "qa@example.com",
        }
    ]
    query = db.execute.call_args.args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    where_sql = str(compiled).split("WHERE", 1)[1].split("GROUP BY", 1)[0]
    assert "department LIKE" in where_sql
    assert "QA" in compiled.params.values()
    assert "质量保证" in compiled.params.values()
    assert "1" in compiled.params.values()
    assert "is_deleted IS false" in where_sql


@pytest.mark.asyncio
async def test_no_qa_members_in_synced_directory_returns_empty() -> None:
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                Mock(all=lambda: []),
                Mock(scalar_one=lambda: 2),
            ]
        )
    )
    assert await get_qa_reminder_recipients(db) == []


@pytest.mark.asyncio
async def test_unsynced_directory_keeps_actionable_error() -> None:
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                Mock(all=lambda: []),
                Mock(scalar_one=lambda: 0),
            ]
        )
    )
    with pytest.raises(AppException, match="尚未同步"):
        await get_qa_reminder_recipients(db)
