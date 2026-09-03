"""ESG「从台账同步」部门归属判定测试（规格：ESG台账同步部门归属判定规格说明.md）。

口径：
- 培训范围 = 归属部门(ledger_department)等于选中部门的台账（空值回退授课部门）；
- 人员范围 = 名单姓名查员工档案，归一后归属部门等于选中部门才录入；
- 跳过三类：已存在 / 档案查无此人 / 非本部门；
- 同名多人取归一部门匹配者；重复同步幂等。

接缝：HTTP 端点（client）+ db_session 种子；conftest 全回滚，不污染数据库。
使用独有虚拟部门「SPEC测试车间」，真实台账/员工不会命中，计数不受真库数据干扰。
"""

from collections.abc import AsyncIterator
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.modules.hr.models import (
    Employee,
    HrFeishuMember,
    TrainingDeptMapping,
    TrainingLedger,
    TrainingSession,
)
from app.modules.hr.training_dept_resolver import invalidate_training_dept_mapping_cache

_SYNC_URL = "/api/v1/hr/esg-training-records/sync-from-ledger"
_LIST_URL = "/api/v1/hr/esg-training-records"
# 独有日期/名称，避免与真实数据去重键碰撞
_D = date(2031, 11, 11)
_D2 = date(2031, 11, 12)
_SUBJ = "SPEC同步口径测试培训"
_SUBJ2 = "SPEC同步口径测试培训QA场"
_SUBJ3 = "SPEC同步口径测试培训回退场"
DEPT = "SPEC测试车间"


@pytest.fixture(autouse=True)
async def _share_db_session(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncIterator[None]:
    """Make API calls observe rows seeded through the test session."""

    mappings = [
        {
            "source_name": "质量管理部",
            "target_name": "QA",
            "match_level": "first",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "QC",
            "target_name": "QA",
            "match_level": "second",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "201二车间（霉酚酸）",
            "target_name": "201二车间（MC）",
            "match_level": "second",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "201二车间（多拉）",
            "target_name": "201二车间（DR）",
            "match_level": "second",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "201二车间",
            "target_name": "201二车间（MC）",
            "match_level": "first",
            "mapping_type": "special",
            "priority": 99,
        },
        {
            "source_name": "201二车间",
            "target_name": "201二车间（MC）",
            "match_level": "first",
            "mapping_type": "split",
            "priority": 100,
        },
        {
            "source_name": "201二车间",
            "target_name": "201二车间（DR）",
            "match_level": "first",
            "mapping_type": "split",
            "priority": 101,
        },
    ]
    for mapping_data in mappings:
        result = await db_session.execute(
            select(TrainingDeptMapping).where(
                TrainingDeptMapping.source_name == mapping_data["source_name"],
                TrainingDeptMapping.target_name == mapping_data["target_name"],
                TrainingDeptMapping.match_level == mapping_data["match_level"],
                TrainingDeptMapping.mapping_type == mapping_data["mapping_type"],
            )
        )
        if result.scalar_one_or_none() is None:
            db_session.add(TrainingDeptMapping(**mapping_data))
    await db_session.flush()
    invalidate_training_dept_mapping_cache()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def _emp(
    name: str, dept: str, sub: str | None = None, account: str | None = None
) -> Employee:
    return Employee(
        employee_number=f"SPEC-{account or name}",
        name=name,
        department=dept,
        sub_department=sub,
        position="测试员",
        domain_account=account,
        # 库表 NOT NULL（模型未标 nullable=False，schema 漂移）
        hire_date=date(2020, 1, 1),
        status="在职",
    )


def _ledger(
    dept: str | None,
    subject: str,
    d: date,
    trainees: str,
    session_id=None,
) -> TrainingLedger:
    return TrainingLedger(
        employee_number=f"SPEC-LEDGER-{subject}",
        training_date=d,
        training_datetime=d.isoformat(),
        training_subject=subject,
        teaching_dept=DEPT,
        involved_depts="201一车间、QA、人事行政部",
        trainees=trainees,
        ledger_department=dept,
        source_type="manual",  # 库表 NOT NULL
        session_id=session_id,
    )


async def _seed(session: AsyncSession) -> None:
    session.add_all(
        [
            _emp("测张三", DEPT, None, "zhangsan"),
            _emp("测李四", "质量管理部", "QC", "lisi"),  # 归一→QA，非本部门
            _emp("测王五", "人力资源部", None, "wangwu"),  # 归一→人事行政部，非本部门
            # 同名两人分属两部门
            _emp("测赵六", DEPT, None, "zhaoliu-a"),
            _emp("测赵六", "质量管理部", "QC", "zhaoliu-b"),
        ]
    )
    session.add_all(
        [
            _ledger(DEPT, _SUBJ, _D, "测张三、测李四、测王五、测赵六、测孙七"),
            _ledger(None, _SUBJ3, _D2, "测张三"),  # 归属空 → 回退授课部门
            _ledger("QA", _SUBJ2, _D, "测赵六"),
        ]
    )
    await session.flush()


async def _esg_rows(client: AsyncClient, dept: str, subject: str) -> list[dict]:
    resp = await client.get(_LIST_URL, params={"department": dept, "page_size": 200})
    rows = resp.json()["data"]
    return [r for r in rows if r["training_name"] == subject]


def _feishu(name: str, department: str, open_id: str | None = None) -> HrFeishuMember:
    """飞书联系人缓存行（裸名台账归属判定用）。"""
    return HrFeishuMember(
        open_id=open_id or f"SPEC-{name}-{department}",
        name=name,
        department=department,
    )


@pytest.mark.asyncio
async def test_sync_only_records_own_department_people(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """本部门（含虚拟部门直连）录入；跨部门与查无此人不计入并分类计数。"""
    await _seed(db_session)

    resp = await client.post(_SYNC_URL, params={"department": DEPT})
    assert resp.status_code == 200
    data = resp.json()["data"]

    # 测张三(_SUBJ) + 测赵六(_SUBJ) + 测张三(_SUBJ3 回退场)
    assert data["created"] == 3
    assert data["skipped_unmatched"] == 1  # 测孙七
    assert data["skipped_other_dept"] == 2  # 测李四、测王五
    assert data["skipped_existing"] == 0

    mine = await _esg_rows(client, DEPT, _SUBJ)
    names = {r["employee_name"] for r in mine}
    assert names == {"测张三", "测赵六"}
    zhao = next(r for r in mine if r["employee_name"] == "测赵六")
    assert zhao["employee_account"] == "zhaoliu-a"  # 同名取本部门那个
    # 集团填报固定口径
    assert zhao["training_method"] == "线下"
    assert zhao["caliber"] == "部门组织"


@pytest.mark.asyncio
async def test_sync_fallback_to_teaching_dept_when_ledger_dept_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """归属部门为空的历史台账按授课部门兜底归入。"""
    await _seed(db_session)

    await client.post(_SYNC_URL, params={"department": DEPT})
    rows = await _esg_rows(client, DEPT, _SUBJ3)
    assert [r["employee_name"] for r in rows] == ["测张三"]


@pytest.mark.asyncio
async def test_sync_same_name_goes_to_own_department(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """QA 部门同步：台账范围只含 QA 归属台账；同名「测赵六」录 QA 那个。"""
    await _seed(db_session)

    await client.post(_SYNC_URL, params={"department": "QA"})
    rows = await _esg_rows(client, "QA", _SUBJ2)
    assert len(rows) == 1
    assert rows[0]["employee_account"] == "zhaoliu-b"
    assert rows[0]["department"] == "QA"


@pytest.mark.asyncio
async def test_sync_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """重复同步不重复创建，只计已存在。"""
    await _seed(db_session)

    await client.post(_SYNC_URL, params={"department": DEPT})
    resp = await client.post(_SYNC_URL, params={"department": DEPT})
    data = resp.json()["data"]
    assert data["created"] == 0
    assert data["skipped_existing"] == 3


# ── 201二车间 家族：裸名/MC/DR 互见与人员分流 ──────────────
# 用真实家族名但独有培训名；计数可能含真库同家族台账，故只断言独有培训名的行
_MC = "201二车间（MC）"
_DR = "201二车间（DR）"
_SUBJ4 = "SPEC家族裸名测试培训"


@pytest.mark.asyncio
async def test_bare_copy_routed_by_trainee_feishu_dept(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """裸名「201二车间」副本按 trainees 在飞书联系人中的部门归属到 MC/DR。

    - 参训人是「201二车间」→ 只进（MC）Tab；
    - 参训人是「201二车间（多拉）」→ 只进（DR）Tab；
    - 参训人不在飞书联系人 → 两个 Tab 都不显示。
    """
    db_session.add_all(
        [
            _feishu("测MC人", "201二车间"),
            _feishu("测DR人", "201二车间（多拉）"),
            _ledger("201二车间", _SUBJ4, _D, "测MC人"),
            _ledger("201二车间", _SUBJ4 + "DR场", _D, "测DR人"),
            _ledger("201二车间", _SUBJ4 + "无档场", _D, "查无此人"),
        ]
    )
    await db_session.flush()

    async def _subjects(dept: str) -> set[str]:
        resp = await client.get(
            "/api/v1/hr/training-ledgers",
            params={"department": dept, "page_size": 200},
        )
        return {r["training_subject"] for r in resp.json()["data"]}

    mc = await _subjects(_MC)
    dr = await _subjects(_DR)
    assert _SUBJ4 in mc and _SUBJ4 not in dr
    assert (_SUBJ4 + "DR场") in dr and (_SUBJ4 + "DR场") not in mc
    assert (_SUBJ4 + "无档场") not in mc and (_SUBJ4 + "无档场") not in dr


@pytest.mark.asyncio
async def test_sync_family_splits_personnel_by_roster(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """裸名培训同步（MC）只录 MC 的人；（DR）只录 DR 的人。"""
    db_session.add_all(
        [
            _emp("测MC人", "201车间", "201二车间（霉酚酸）", "mc-ren"),
            _emp("测DR人", "201车间", "201二车间（多拉）", "dr-ren"),
            # 飞书联系人部门是裸名台账归属判定的依据
            _feishu("测MC人", "201二车间"),
            _feishu("测DR人", "201二车间（多拉）"),
            _ledger("201二车间", _SUBJ4, _D, "测MC人、测DR人"),
        ]
    )
    await db_session.flush()

    await client.post(_SYNC_URL, params={"department": _MC})
    rows = await _esg_rows(client, _MC, _SUBJ4)
    assert [r["employee_account"] for r in rows] == ["mc-ren"]
    assert await _esg_rows(client, _DR, _SUBJ4) == []  # DR 未同步前无记录

    await client.post(_SYNC_URL, params={"department": _DR})
    rows = await _esg_rows(client, _DR, _SUBJ4)
    assert [r["employee_account"] for r in rows] == ["dr-ren"]


@pytest.mark.asyncio
async def test_create_record_splits_bare_into_mc_and_dr_copies(
    db_session: AsyncSession,
) -> None:
    """写端归一：涉及裸名 201二车间 时拆 MC+DR 两副本，主记录归 MC。"""
    from uuid import uuid4

    from sqlalchemy import select

    from app.modules.hr.models import TrainingSession
    from app.modules.hr.schemas import TrainingLedgerCreate
    from app.modules.hr.service import TrainingLedgerService

    sid = uuid4()
    # session_id 外键指向 training_sessions，先造空壳会话
    db_session.add(TrainingSession(id=sid))
    await db_session.flush()
    data = TrainingLedgerCreate(
        employee_number="SPEC-LEDGER-CREATE",
        training_date=_D,
        training_subject=_SUBJ4,
        training_method="面授",
        teaching_dept="QA",
        involved_depts="201二车间、QA",
        trainees="测MC人",
        session_id=sid,
        ledger_department="201二车间",
    )
    main = await TrainingLedgerService(db_session).create_record(data)
    assert main.ledger_department == _MC

    res = await db_session.execute(
        select(TrainingLedger).where(TrainingLedger.session_id == sid)
    )
    depts = {r.ledger_department for r in res.scalars().all()}
    assert depts == {_MC, _DR, "QA"}


@pytest.mark.asyncio
async def test_bare_hidden_when_split_copies_exist(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """同会话已有规范拆分副本时，裸名总副本在 MC/DR Tab 隐藏；MC/DR 不互见。"""
    from uuid import uuid4

    sid = uuid4()
    db_session.add(TrainingSession(id=sid))
    await db_session.flush()
    db_session.add_all(
        [
            _ledger("201二车间", _SUBJ4, _D, "测张三", session_id=sid),
            _ledger(_MC, _SUBJ4, _D, "测MC人", session_id=sid),
        ]
    )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/hr/training-ledgers", params={"department": _MC, "page_size": 200}
    )
    rows = [r for r in resp.json()["data"] if r["training_subject"] == _SUBJ4]
    # 裸名总副本隐藏，只见自己的规范副本
    assert {r["ledger_department"] for r in rows} == {_MC}

    resp = await client.get(
        "/api/v1/hr/training-ledgers", params={"department": _DR, "page_size": 200}
    )
    rows = [r for r in resp.json()["data"] if r["training_subject"] == _SUBJ4]
    # DR 无副本且裸名被隐藏；MC 副本不串到 DR
    assert rows == []
