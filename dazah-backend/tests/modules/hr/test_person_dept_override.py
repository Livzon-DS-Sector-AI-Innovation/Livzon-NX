"""人员归属覆写（person 映射）测试.

口径：
- person 行（source_name=人员姓名, target_name=台账规范部门）优先于
  飞书部门参与 201 半边落线判定；
- 覆写姓名无需出现在飞书通讯录也能计入（解决"人已调线、飞书未改"）；
- 涉及 201 家族但整份名单均无法识别线别时的拦截不再误伤覆写人员；
- person 类型经 /training/dept-mappings 现有端点全流程可维护。
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.modules.hr import training_dept_resolver
from app.modules.hr.schemas import TrainingLedgerCreate
from app.modules.hr.service import TrainingLedgerService
from app.modules.hr.training_dept_resolver import (
    get_person_overrides,
    invalidate_training_dept_mapping_cache,
)

_MC = "201二车间（MC）"
_DR = "201二车间（DR）"
_BARE = "201二车间"


@pytest.fixture(autouse=True)
def _patch_resolver_mappings(monkeypatch):
    """注入含 person 覆写行的映射配置快照（绕过 DB 与进程内缓存）。"""

    async def _fake_load(session):
        return _mapping_list() + _person_rows()

    monkeypatch.setattr(training_dept_resolver, "_load_mappings", _fake_load)
    invalidate_training_dept_mapping_cache()
    yield
    invalidate_training_dept_mapping_cache()


def _mapping_list() -> list[dict]:
    return [
        {
            "source_name": _BARE,
            "target_name": _MC,
            "match_level": "first",
            "mapping_type": "special",
            "priority": 99,
        },
        {
            "source_name": "201二车间（多拉）",
            "target_name": _DR,
            "match_level": "second",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": _BARE,
            "target_name": _MC,
            "match_level": "first",
            "mapping_type": "split",
            "priority": 100,
        },
        {
            "source_name": _BARE,
            "target_name": _DR,
            "match_level": "first",
            "mapping_type": "split",
            "priority": 101,
        },
    ]


def _person_rows() -> list[dict]:
    """人员归属覆写配置：已调 DR 但飞书部门仍挂在 201二车间 的人员。"""
    return [
        {
            "source_name": "安志刚",
            "target_name": _DR,
            "match_level": "both",
            "mapping_type": "person",
            "priority": 10,
        },
        {
            "source_name": "测未同步",
            "target_name": _DR,
            "match_level": "both",
            "mapping_type": "person",
            "priority": 10,
        },
    ]


def _execute_result(rows: list[tuple]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_get_person_overrides_reads_person_rows():
    """覆写映射读取：person 行 → {姓名: 规范部门}。"""
    overrides = await get_person_overrides(None)  # _load_mappings 已打桩
    assert overrides == {"安志刚": _DR, "测未同步": _DR}


@pytest.mark.asyncio
async def test_norms_prefer_person_override_over_feishu():
    """覆写优先：飞书旧部门（裸名→MC）不影响；无飞书行的人员按覆写计入。"""
    service = TrainingLedgerService(_session_with_execute_results(
        [_execute_result([("安志刚", _BARE)])]  # 飞书旧部门=裸名（归 MC）
    ))

    norms = await service._resolve_trainee_feishu_norms("安志刚、测未同步")

    assert norms == {_DR}  # 两人均按覆写归 DR


def _session_with_execute_results(results: list[MagicMock]) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))
    return session


@pytest.mark.asyncio
async def test_guard_does_not_intercept_overridden_trainees():
    """涉及 201 家族但名单仅含覆写人员（飞书未命中）→ 不拦截，按覆写落线。"""
    session = _session_with_execute_results(
        [
            _execute_result([]),  # 飞书未命中（覆写人员不在通讯录匹配结果里）
            _scalar_result(None),  # 培训师表无此人
        ]
    )
    service = TrainingLedgerService(session)
    created: list = []

    async def _fake_create(record):
        created.append(record)
        return record

    service.repo.create = AsyncMock(side_effect=_fake_create)

    await service.create_record(
        TrainingLedgerCreate(
            employee_number="",
            training_date=date(2026, 9, 15),
            training_subject="SPEC覆写落线培训",
            training_method="面授",
            teaching_dept=_BARE,
            ledger_department=_BARE,
            trainees="安志刚、测未同步",
        )
    )

    assert len(created) == 1
    assert created[0].ledger_department == _DR


@pytest.mark.asyncio
async def test_person_mapping_crud_via_endpoint(client: AsyncClient):
    """person 类型经现有映射端点全流程：创建 → 列表可见 → 停用。"""
    url = "/api/v1/hr/training/dept-mappings"
    create_resp = await client.post(
        url,
        json={
            "source_name": "安志刚",
            "target_name": _DR,
            "match_level": "both",
            "mapping_type": "person",
            "priority": 10,
            "enabled": True,
            "remark": "调入DR，飞书未改",
        },
    )
    assert create_resp.status_code == 200
    mapping_id = create_resp.json()["data"]["id"]

    list_resp = await client.get(url)
    assert list_resp.status_code == 200
    rows = [r for r in list_resp.json()["data"] if r["mapping_type"] == "person"]
    assert len(rows) == 1
    assert rows[0]["source_name"] == "安志刚"
    assert rows[0]["target_name"] == _DR

    disable_resp = await client.put(f"{url}/{mapping_id}", json={"enabled": False})
    assert disable_resp.status_code == 200
    assert disable_resp.json()["data"]["enabled"] is False
