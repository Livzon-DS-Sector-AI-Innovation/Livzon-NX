"""培训台账 201 二车间归属规则测试（口径移植自老项目）.

口径（仅 201 二车间特殊处理，其他拆分部门不受影响）：
- 授课部门归一：MC/DR 规范名 → 裸名「201二车间」（DR/MC 是台账线维度，
  授课部门是车间实体，不由培训师登记决定）；
- 主记录半边修正：裸名展开 MC+DR 取有参训人员的那半；已落半边但人员
  不在该半时挪到有人的半；识别不到人维持原口径（裸名归 MC 优先）；
- 导入补线：授课部门为裸名 201二车间且归属为空时按参训人员飞书部门补
  半边，跨半边各建一条内容一致的副本；查不到回退所选 Tab；
- 拦截：签到/手动新增涉及 201 家族但整份名单均无法从飞书识别线别 → 400；
- 拆副本收敛：某半边没有参训人员不建该半边副本（识别不到兜底全建）。
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.hr import training_dept_resolver
from app.modules.hr.models import HrFeishuMember, TrainingDeptMapping, TrainingLedger
from app.modules.hr.repository import TrainingLedgerRepository
from app.modules.hr.schemas import TrainingLedgerCreate
from app.modules.hr.service import TrainingLedgerService
from app.modules.hr.training_dept_resolver import (
    base_201_department,
    invalidate_training_dept_mapping_cache,
)

_MC = "201二车间（MC）"
_DR = "201二车间（DR）"
_BARE = "201二车间"

# 独有标记，避免与真库数据互相干扰
_SUBJ_PREFIX = "SPEC201归属"


def _mapping_list(with_split: bool = True) -> list[dict]:
    """镜像 hr.training_dept_mappings 中 201 家族的生产配置。"""
    mappings = [
        {
            "source_name": _BARE,
            "target_name": _MC,
            "match_level": "first",
            "mapping_type": "special",
            "priority": 99,
        },
        {
            "source_name": "201二车间（霉酚酸）",
            "target_name": _MC,
            "match_level": "second",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "201二车间（多拉）",
            "target_name": _DR,
            "match_level": "second",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "201三车间",
            "target_name": _DR,
            "match_level": "both",
            "mapping_type": "special",
            "priority": 10,
        },
        # 非映射部门自映射：避免 resolve_training_department 步骤3回落查库
        {
            "source_name": "质量部",
            "target_name": "质量部",
            "match_level": "first",
            "mapping_type": "special",
            "priority": 200,
        },
    ]
    if with_split:
        mappings += [
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
    return mappings


@pytest.fixture(autouse=True)
def _patch_resolver_mappings(monkeypatch):
    """绕过 DB 与进程内缓存，直接注入映射配置快照。"""

    async def _fake_load(session):
        return _mapping_list()

    monkeypatch.setattr(training_dept_resolver, "_load_mappings", _fake_load)
    invalidate_training_dept_mapping_cache()
    yield
    invalidate_training_dept_mapping_cache()


def _execute_result(rows: list[tuple]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _service_with_execute_results(results: list[MagicMock]) -> TrainingLedgerService:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))
    return TrainingLedgerService(session)


def _ledger_data(**overrides) -> TrainingLedgerCreate:
    base = dict(
        employee_number="",
        training_date=date(2026, 9, 15),
        training_subject=f"{_SUBJ_PREFIX}培训",
        training_method="面授",
        teaching_dept=_DR,
        instructor="王国民",
        trainees="测金养蓬、测康正宇",
    )
    base.update(overrides)
    return TrainingLedgerCreate(**base)


def _attach_create_spy(service: TrainingLedgerService) -> list[TrainingLedger]:
    created: list[TrainingLedger] = []

    async def _fake_create(record):
        record.id = uuid.uuid4()
        created.append(record)
        return record

    service.repo.create = AsyncMock(side_effect=_fake_create)
    service.repo.add_all = AsyncMock()
    return created


# ── 导入链路（create_many：按人补线 + 跨半边副本 + 回退） ──────────────


@pytest.mark.asyncio
async def test_import_routes_by_trainees_even_when_trainer_registered_mc():
    """培训师登记为 MC、导入 Tab 为 DR 时：受训人员（DR 线）优先定归属，
    授课部门归一为裸名「201二车间」。"""
    data = _ledger_data()
    service = _service_with_execute_results(
        [
            _execute_result([("王国民", _MC)]),  # 培训师部门查询
            _execute_result(
                [
                    ("测金养蓬", "201二车间（多拉）"),
                    ("测康正宇", "201二车间（多拉）"),
                ]
            ),  # 受训人员飞书部门查询
        ]
    )
    created = _attach_create_spy(service)

    created_count, matched = await service.create_many([data])

    assert created_count == 1
    assert matched == 1
    assert data.teaching_dept == _BARE
    assert data.ledger_department == _DR  # 受训人员归属，未被培训师 MC 带跑
    assert not created  # 单线不拆副本


@pytest.mark.asyncio
async def test_import_falls_back_to_selected_tab_when_trainees_unknown():
    """受训人员飞书未命中 → 回退所选 Tab，记录保证可见。"""
    data = _ledger_data()
    service = _service_with_execute_results(
        [
            _execute_result([]),  # 培训师表无此人
            _execute_result([]),  # 飞书未命中
        ]
    )
    _attach_create_spy(service)

    created_count, matched = await service.create_many([data])

    assert created_count == 1
    assert matched == 0
    assert data.teaching_dept == _BARE
    assert data.ledger_department == _DR


@pytest.mark.asyncio
async def test_import_cross_half_trainees_build_copies_for_both_lines():
    """受训人员横跨 MC/DR → 两线各建一条内容一致的副本（跨半边双副本）。"""
    data = _ledger_data()
    service = _service_with_execute_results(
        [
            _execute_result([]),  # 培训师表无此人
            _execute_result(
                [
                    ("测金养蓬", "201二车间（多拉）"),  # → DR
                    ("测康正宇", _BARE),  # → MC
                ]
            ),
        ]
    )
    _attach_create_spy(service)

    created_count, matched = await service.create_many([data])

    assert created_count == 1
    assert matched == 1
    added = service.repo.add_all.await_args.args[0]
    ledger_depts = {r.ledger_department for r in added}
    assert ledger_depts == {_MC, _DR}
    assert data.ledger_department == _MC  # 主记录归 MC（MC 优先）
    assert {r.teaching_dept for r in added} == {_BARE}


@pytest.mark.asyncio
async def test_import_auto_routes_to_other_line_when_trainees_match():
    """在 MC Tab 导入但受训人员全部是 DR 线 → 自动纠正归属到 DR。"""
    data = _ledger_data(teaching_dept=_MC)
    service = _service_with_execute_results(
        [
            _execute_result([]),
            _execute_result(
                [
                    ("测金养蓬", "201二车间（多拉）"),
                    ("测康正宇", "201二车间（多拉）"),
                ]
            ),
        ]
    )
    _attach_create_spy(service)

    created_count, matched = await service.create_many([data])

    assert created_count == 1
    assert matched == 1
    assert data.ledger_department == _DR


@pytest.mark.asyncio
async def test_import_skips_non_201_family_tab():
    """非 201 家族 Tab 不做受训人员自动归属（其他拆分部门不受影响）。"""
    data = _ledger_data(teaching_dept="102二车间（DR）")
    service = _service_with_execute_results([_execute_result([])])
    _attach_create_spy(service)

    created_count, matched = await service.create_many([data])

    assert created_count == 1
    assert matched == 0
    assert data.teaching_dept == "102二车间（DR）"  # 非 201 部门不压平
    assert data.ledger_department is None


@pytest.mark.asyncio
async def test_import_unresolved_201_rows_fall_back_to_tab_on_unconfigured(
    monkeypatch,
):
    """未配置 201 拆分映射（如全新环境）时授课部门不压平、不落归属。"""

    async def _fake_load(session):
        return [m for m in _mapping_list() if m["mapping_type"] != "split"]

    monkeypatch.setattr(training_dept_resolver, "_load_mappings", _fake_load)
    invalidate_training_dept_mapping_cache()

    data = _ledger_data()
    service = _service_with_execute_results([_execute_result([])])
    _attach_create_spy(service)

    created_count, matched = await service.create_many([data])

    assert created_count == 1
    assert matched == 0
    assert data.teaching_dept == _DR  # 无拆分配置 → 不压平
    assert data.ledger_department is None


# ── 签到表转入 / 手动新增（create_record） ──────────────────


@pytest.mark.asyncio
async def test_create_record_bare_context_dr_trainees_route_to_dr():
    """签到表场景复现：部门语境是裸名「201二车间」（显示归一后的值）、
    受训人员全在 DR 线 → 主记录归 DR（不再落 MC 兜底），也不拆 MC 副本。"""
    norms_rows = [
        ("测金养蓬", "201二车间（多拉）"),
        ("测康正宇", "201二车间（多拉）"),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result(norms_rows),  # 拦截用飞书查询
            _scalar_result(None),  # 培训师表无此人
            _execute_result(norms_rows),  # 半边修正用飞书查询
            _execute_result(norms_rows),  # 拆副本人员收敛
        ]
    )
    service = TrainingLedgerService(session)
    created = _attach_create_spy(service)

    await service.create_record(
        _ledger_data(
            teaching_dept=_BARE,
            ledger_department=_BARE,
            involved_depts=_BARE,
            session_id=uuid.uuid4(),
        )
    )

    assert len(created) == 1
    assert created[0].teaching_dept == _BARE
    assert created[0].ledger_department == _DR  # 裸名展开后取有人的那半
    assert created[0].involved_depts == _BARE


@pytest.mark.asyncio
async def test_create_record_cross_half_builds_copies_only_for_occupied_halves():
    """跨线培训：MC、DR 各建一份完整副本；其他部门副本照旧。"""
    norms_rows = [
        ("测金养蓬", "201二车间（多拉）"),  # DR
        ("测康正宇", _BARE),  # MC
        ("测李四", "质量部"),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result(norms_rows),  # 拦截用飞书查询
            _scalar_result(None),  # 培训师表无此人
            _execute_result(norms_rows),  # 拆副本人员收敛
        ]
    )
    service = TrainingLedgerService(session)
    created = _attach_create_spy(service)

    await service.create_record(
        _ledger_data(
            teaching_dept="人事行政部",
            ledger_department="人事行政部",
            involved_depts=f"{_BARE}、质量部",
            session_id=uuid.uuid4(),
            level_category=None,
        )
    )

    ledger_depts = [r.ledger_department for r in created]
    # 主记录（公司级落款保留）+ MC/DR 两线副本 + 质量部副本
    assert ledger_depts == ["人事行政部", _MC, _DR, "质量部"]
    assert {r.teaching_dept for r in created} == {"人事行政部"}


@pytest.mark.asyncio
async def test_create_record_single_line_skips_empty_half_copy():
    """单线培训：裸名上下文按人员修正为 DR，且不凭空建 MC 半边副本。"""
    norms_rows = [("测金养蓬", "201二车间（多拉）")]
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result(norms_rows),  # 拦截用飞书查询
            _scalar_result(None),  # 培训师表无此人
            _execute_result(norms_rows),  # 半边修正用飞书查询
            _execute_result(norms_rows),  # 拆副本人员收敛
        ]
    )
    service = TrainingLedgerService(session)
    created = _attach_create_spy(service)

    await service.create_record(
        _ledger_data(
            teaching_dept=_BARE,
            ledger_department=_BARE,
            involved_depts=_BARE,
            trainees="测金养蓬",
            session_id=uuid.uuid4(),
        )
    )

    # 主记录按人员落 DR；MC 半边无参训人员 → 不建副本
    ledger_depts = [r.ledger_department for r in created]
    assert ledger_depts == [_DR]


@pytest.mark.asyncio
async def test_create_record_intercepts_when_no_trainee_resolves():
    """涉及 201 家族但整份名单都查不到飞书线别 → 400 拦截列出人名。"""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result([]),  # 飞书未命中
            _scalar_result(None),  # 培训师表查询（拦截后不应到达）
        ]
    )
    service = TrainingLedgerService(session)
    _attach_create_spy(service)

    with pytest.raises(AppException) as exc_info:
        await service.create_record(
            _ledger_data(
                teaching_dept=_BARE,
                ledger_department=_BARE,
                trainees="测不存在、测也没有",
            )
        )

    assert exc_info.value.status_code == 400
    assert "测不存在" in exc_info.value.message
    service.repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_record_partial_match_routes_to_hit_line():
    """部分命中：命中 DR 线的人员在名单里 → 按命中线归档，不拦截。"""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result([("测金养蓬", "201二车间（多拉）")]),  # 拦截用
            _scalar_result(None),
            _execute_result([("测金养蓬", "201二车间（多拉）")]),  # 半边修正
        ]
    )
    service = TrainingLedgerService(session)
    _attach_create_spy(service)

    await service.create_record(
        _ledger_data(
            teaching_dept=_BARE,
            ledger_department=_BARE,
            trainees="测金养蓬、测未同步",
            involved_depts=None,
            session_id=None,
        )
    )

    created = service.repo.create.await_args_list
    assert len(created) == 1
    assert created[0].args[0].ledger_department == _DR


@pytest.mark.asyncio
async def test_create_record_non_201_dept_untouched():
    """非 201 家族不受任何影响：授课部门不压平、归属为空不误判。"""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _scalar_result(None),  # 培训师表无此人
        ]
    )
    service = TrainingLedgerService(session)
    _attach_create_spy(service)

    await service.create_record(
        _ledger_data(
            teaching_dept="102二车间（DR）",
            trainees="测张三",
            involved_depts=None,
            session_id=None,
        )
    )

    created = service.repo.create.await_args.args[0]
    assert created.teaching_dept == "102二车间（DR）"
    assert created.ledger_department is None


@pytest.mark.asyncio
async def test_base_201_department_normalization():
    """base_201_department：MC/DR 规范名 → 裸名；其他部门原样返回。"""
    session = None  # _load_mappings 已被 fixture 打桩，不触碰 DB
    assert await base_201_department(session, _MC) == _BARE
    assert await base_201_department(session, _DR) == _BARE
    assert await base_201_department(session, _BARE) == _BARE
    assert await base_201_department(session, "102二车间（DR）") == "102二车间（DR）"
    assert await base_201_department(session, "质量部") == "质量部"
    assert await base_201_department(session, None) is None


# ── 读端路由（真实 DB，验证 Tab 过滤口径） ───────────────────


def _db_mapping_row(data: dict) -> TrainingDeptMapping:
    return TrainingDeptMapping(**data)


def _db_ledger(subject: str, ledger_dept: str | None, trainees: str) -> TrainingLedger:
    return TrainingLedger(
        employee_number=f"SPEC-{subject}",
        training_date=date(2031, 9, 15),
        training_datetime="2031-09-15",
        training_subject=subject,
        teaching_dept=_BARE,
        trainees=trainees,
        ledger_department=ledger_dept,
        source_type="manual",
    )


@pytest.mark.asyncio
async def test_list_by_department_routes_normalized_records(
    db_session: AsyncSession,
) -> None:
    """显式归属的记录只进对应 Tab；裸名历史记录按受训人员动态归属。

    端到端复现用户报告的混线场景：授课部门同为「201二车间」的记录，
    按 ledger_department / 受训人员飞书部门分线，互不串 Tab。
    """
    for m in _mapping_list():
        existing = await db_session.execute(
            select(TrainingDeptMapping).where(
                TrainingDeptMapping.source_name == m["source_name"],
                TrainingDeptMapping.target_name == m["target_name"],
                TrainingDeptMapping.match_level == m["match_level"],
                TrainingDeptMapping.mapping_type == m["mapping_type"],
            )
        )
        if existing.scalar_one_or_none() is None:
            db_session.add(_db_mapping_row(m))
    db_session.add_all(
        [
            HrFeishuMember(
                open_id="SPEC201-dr-jin",
                name="测金养蓬",
                department="201二车间（多拉）",
            ),
            HrFeishuMember(
                open_id="SPEC201-mc-li",
                name="测李连",
                department=_BARE,
            ),
        ]
    )
    subj_dr = f"{_SUBJ_PREFIX}-显式DR"
    subj_mc = f"{_SUBJ_PREFIX}-显式MC"
    subj_bare = f"{_SUBJ_PREFIX}-裸名历史"
    db_session.add_all(
        [
            _db_ledger(subj_dr, _DR, "测金养蓬"),
            _db_ledger(subj_mc, _MC, "测李连"),
            _db_ledger(subj_bare, None, "测金养蓬"),  # 裸名 + DR 线受训人员
        ]
    )
    await db_session.flush()
    invalidate_training_dept_mapping_cache()

    repo = TrainingLedgerRepository(db_session)
    dr_rows, _ = await repo.list_by_department(_DR, page=1, page_size=500)
    mc_rows, _ = await repo.list_by_department(_MC, page=1, page_size=500)
    dr_subjects = {r.training_subject for r in dr_rows}
    mc_subjects = {r.training_subject for r in mc_rows}

    assert subj_dr in dr_subjects
    assert subj_bare in dr_subjects  # 裸名历史记录按受训人员归 DR
    assert subj_mc in mc_subjects
    # MC/DR 互不可见
    assert subj_dr not in mc_subjects
    assert subj_mc not in dr_subjects
    assert subj_bare not in mc_subjects
