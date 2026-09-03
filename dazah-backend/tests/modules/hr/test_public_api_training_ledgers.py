"""hr public_api.query_training_ledgers 跨模块只读检索测试。"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from app.modules.hr.models import TrainingLedger
from app.modules.hr.public_api import query_training_ledgers


@pytest.mark.anyio
async def test_query_training_ledgers_empty_or_short_keywords(db_session) -> None:
    """空列表或清洗后不足 2 字符的关键词直接返回空，不查询数据库。"""
    assert await query_training_ledgers(db_session, []) == []
    assert await query_training_ledgers(db_session, ["", "a", "  "]) == []


@pytest.mark.anyio
async def test_query_training_ledgers_maps_matching_rows(db_session) -> None:
    """命中记录按只读结构映射返回（日期转 isoformat、内容截断等）。"""
    suffix = uuid4().hex[:8]
    db_session.add(
        TrainingLedger(
            employee_number=None,
            training_date=date(2026, 8, 1),
            training_subject=f"压塞机-{suffix}",
            training_content="压塞压力标准 0.40MPa",
            teaching_dept="质量部",
            trainer="张三",
            instructor="李四",
            trainees="灌装线操作工",
            training_method="现场",
            duration_hours=2.0,
            training_type="质量类",
            assessment_result=None,
            source_type="培训计划",
        )
    )
    await db_session.flush()

    rows = await query_training_ledgers(db_session, [f"压塞机-{suffix}"])
    assert len(rows) == 1
    assert rows[0]["training_date"] == "2026-08-01"
    assert rows[0]["training_subject"].endswith(suffix)
    assert rows[0]["training_content"] == "压塞压力标准 0.40MPa"
    assert rows[0]["trainees"] == "灌装线操作工"
    assert rows[0]["teaching_dept"] == "质量部"
    assert rows[0]["training_method"] == "现场"

    # 关键词不命中返回空列表
    assert await query_training_ledgers(db_session, ["不存在的关键词-xyz"]) == []
