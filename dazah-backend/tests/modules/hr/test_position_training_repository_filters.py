"""岗位培训清单 Repository 部门过滤回归测试。

覆盖 list_lists 对「可见范围」与「选中部门」两个过滤条件的组合：
- 管理员（dept_alias_set=None）：按选中部门过滤
- 部门受限用户（dept_alias_set 非空）：同时按 可见范围 ∩ 选中部门 过滤，
  避免修复前 `elif` 分支导致切 tab 时 department 参数被忽略、返回全部可见部门数据。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.hr.models import PositionTrainingList
from app.modules.hr.position_training_repository import PositionTrainingListRepository
from app.modules.hr.training_dept_resolver import invalidate_training_dept_mapping_cache


@pytest.mark.anyio
async def test_position_training_list_lists_department_filter_combines_with_scope(
    db_session,
) -> None:
    """部门参数与可见范围应做交集过滤（回归：修复前 `elif` 会忽略部门参数）。"""
    invalidate_training_dept_mapping_cache()

    # 使用唯一部门名，避免与测试库既有数据互相干扰
    suffix = uuid4().hex[:8]
    dept_qa = f"QA部-{suffix}"
    dept_prod = f"生产部-{suffix}"
    dept_admin = f"行政部-{suffix}"
    for dept in (dept_qa, dept_prod, dept_admin):
        db_session.add(PositionTrainingList(department=dept, position="经理"))
    await db_session.flush()

    repo = PositionTrainingListRepository(db_session)

    # 1) 管理员（无可见范围）：选中部门只返回该部门数据
    rows, total = await repo.list_lists(department=dept_qa, page_size=50)
    assert total == 1
    assert {r.department for r in rows} == {dept_qa}

    # 2) 部门受限用户：可见范围 ∩ 选中部门 → 只返回选中部门（不能带出同范围其他部门）
    rows, total = await repo.list_lists(
        department=dept_qa,
        dept_alias_set={dept_qa, dept_prod},
        page_size=50,
    )
    assert total == 1
    assert {r.department for r in rows} == {dept_qa}

    # 3) 部门受限用户：未传部门 → 返回全部可见范围数据
    rows, total = await repo.list_lists(
        department=None,
        dept_alias_set={dept_qa, dept_prod},
        page_size=50,
    )
    assert total == 2
    assert {r.department for r in rows} == {dept_qa, dept_prod}
