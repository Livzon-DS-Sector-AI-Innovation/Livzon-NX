"""培训人员配置按登录人隔离测试。

覆盖：
- upsert 写入 created_by；同人同名复用更新、不同人同名各自独立
- list：普通用户只见自己的；超管见全部（含 NULL 归属历史）
- delete：删他人配置 403；删自己的成功；超管可删任意
- 接口级：list 带 owner 过滤 + 越权删除 403

说明：DEV_BYPASS_AUTH 下当前用户固定为 dev 用户（id=DEV_USER_ID，
feishu_open_id=dev-bypass-open-id），权限由 monkeypatch 控制。
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import TrainingPersonnelConfig
from app.platform.identity.models import User

# dev 绕过模式下固定用户 ID（app.core.deps.get_current_user 创建）
DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
# DEV_BYPASS_OPEN_ID 固定值（rbac.py），_is_super_admin_user 会把它判为超管
DEV_BYPASS_OPEN_ID = "dev-bypass-open-id"

UA = str(uuid4())
UB = str(uuid4())

# 测试用配置名集合：唯一索引（level, department, config_name, created_by）下
# 同一键重复种会撞索引；每测试前清理本文件用过的键，避免 commit 残留污染
_TEST_KEYS = {
    ("部门级", "101一车间", "我的配置"),
    ("部门级", "101一车间", "别人的配置"),
    ("部门级", "101一车间", "历史公共配置"),
    ("部门级", "101一车间", "我配的"),
    ("部门级", "101一车间", "他人配的"),
    ("部门级", "101一车间", "他配的要删"),
}


@pytest.fixture(autouse=True)
async def _cleanup_config_keys(db_session: AsyncSession):
    from sqlalchemy import delete as sa_delete

    for level, department, name in _TEST_KEYS:
        await db_session.execute(
            sa_delete(TrainingPersonnelConfig).where(
                TrainingPersonnelConfig.level == level,
                TrainingPersonnelConfig.department == department,
                TrainingPersonnelConfig.config_name == name,
            )
        )
    await db_session.commit()


async def _seed_user(session: AsyncSession, user_id: str, name: str) -> None:
    """created_by 有 FK 指向 identity.users，先种用户行避免外键失败。"""
    from sqlalchemy import select

    exists = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if exists is None:
        session.add(User(id=user_id, name=name, feishu_open_id=f"t-{user_id}"))
        await session.flush()


async def _seed_config(
    session: AsyncSession,
    *,
    name: str,
    owner: str | None = None,
    level: str = "部门级",
    department: str | None = None,
    personnel: list | None = None,
) -> TrainingPersonnelConfig:
    c = TrainingPersonnelConfig(
        level=level,
        department=department,
        config_name=name,
        personnel=personnel or [{"name": "测试"}],
        remarks="",
        created_by=owner,
        updated_by=owner,
    )
    session.add(c)
    await session.flush()
    return c


# ─── service 层：归属隔离 ───


@pytest.mark.asyncio
async def test_upsert_writes_owner_and_same_owner_reuses(db_session: AsyncSession):
    """upsert 写入 created_by；同人同名复用更新（不会多建一条）。"""
    await _seed_user(db_session, UA, "用户甲")
    from app.modules.hr.schemas import TrainingPersonnelConfigCreate
    from app.modules.hr.service import TrainingPersonnelConfigService

    svc = TrainingPersonnelConfigService(db_session)
    created = await svc.upsert_config(
        TrainingPersonnelConfigCreate(
            level="部门级",
            department="101一车间",
            config_name="测试班A",
            personnel=[{"name": "甲"}],
            remarks="",
        ),
        owner_id=UA,
    )
    assert str(created.created_by) == UA

    updated = await svc.upsert_config(
        TrainingPersonnelConfigCreate(
            level="部门级",
            department="101一车间",
            config_name="测试班A",
            personnel=[{"name": "甲2"}],
            remarks="",
        ),
        owner_id=UA,
    )
    assert updated.id == created.id
    assert updated.personnel == [{"name": "甲2"}]

    rows = (
        (
            await db_session.execute(
                select(TrainingPersonnelConfig).where(
                    TrainingPersonnelConfig.config_name == "测试班A",
                    TrainingPersonnelConfig.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_different_owner_same_name_independent(db_session: AsyncSession):
    """不同用户可各自建同名配置，互不覆盖。"""
    await _seed_user(db_session, UA, "用户甲")
    await _seed_user(db_session, UB, "用户乙")
    from app.modules.hr.schemas import TrainingPersonnelConfigCreate
    from app.modules.hr.service import TrainingPersonnelConfigService

    svc = TrainingPersonnelConfigService(db_session)
    c1 = await svc.upsert_config(
        TrainingPersonnelConfigCreate(
            level="公司级",
            department=None,
            config_name="同名班",
            personnel=[{"name": "甲"}],
            remarks="",
        ),
        owner_id=UA,
    )
    c2 = await svc.upsert_config(
        TrainingPersonnelConfigCreate(
            level="公司级",
            department=None,
            config_name="同名班",
            personnel=[{"name": "乙"}],
            remarks="",
        ),
        owner_id=UB,
    )
    assert c1.id != c2.id
    assert str(c1.created_by) == UA
    assert str(c2.created_by) == UB
    assert c1.personnel == [{"name": "甲"}]
    assert c2.personnel == [{"name": "乙"}]


@pytest.mark.asyncio
async def test_list_filters_by_owner_and_admin_sees_all(db_session: AsyncSession):
    """list：普通用户只见自己的；超管可见全部（含 NULL 归属历史）。"""
    await _seed_user(db_session, UA, "用户甲")
    await _seed_user(db_session, UB, "用户乙")
    from app.modules.hr.service import TrainingPersonnelConfigService

    await _seed_config(
        db_session, name="我的配置", owner=UA, level="部门级", department="101一车间"
    )
    await _seed_config(
        db_session, name="别人的配置", owner=UB, level="部门级", department="101一车间"
    )
    await _seed_config(
        db_session,
        name="历史公共配置",
        owner=None,
        level="部门级",
        department="101一车间",
    )

    svc = TrainingPersonnelConfigService(db_session)

    # 普通用户 UA：只见自己的（不含他人、不含历史 NULL）
    own = await svc.list_configs(
        level="部门级", department="101一车间", owner_id=UA, is_admin=False
    )
    names = {c.config_name for c in own}
    assert names == {"我的配置"}

    # 超管：全部
    allc = await svc.list_configs(
        level="部门级", department="101一车间", owner_id=UA, is_admin=True
    )
    all_names = {c.config_name for c in allc}
    assert all_names == {"我的配置", "别人的配置", "历史公共配置"}


@pytest.mark.asyncio
async def test_delete_requires_owner(db_session: AsyncSession):
    """删除：非超管只能删自己的；删他人 403；超管可删任意。"""
    await _seed_user(db_session, UA, "用户甲")
    await _seed_user(db_session, UB, "用户乙")
    from app.core.exceptions import ForbiddenException
    from app.modules.hr.service import TrainingPersonnelConfigService

    mine = await _seed_config(
        db_session, name="待删我的", owner=UA, level="部门级", department="101一车间"
    )
    theirs = await _seed_config(
        db_session, name="待删他人的", owner=UB, level="部门级", department="101一车间"
    )

    svc = TrainingPersonnelConfigService(db_session)

    # 删他人 → 403
    with pytest.raises(ForbiddenException):
        await svc.delete_config(theirs.id, user_id=UA, is_admin=False)

    # 删自己的 → 成功（软删）
    await svc.delete_config(mine.id, user_id=UA, is_admin=False)
    mine_row = (
        await db_session.execute(
            select(TrainingPersonnelConfig).where(TrainingPersonnelConfig.id == mine.id)
        )
    ).scalar_one()
    assert mine_row.is_deleted is True

    # 超管删他人的 → 成功
    await svc.delete_config(theirs.id, user_id=UA, is_admin=True)
    theirs_row = (
        await db_session.execute(
            select(TrainingPersonnelConfig).where(
                TrainingPersonnelConfig.id == theirs.id
            )
        )
    ).scalar_one()
    assert theirs_row.is_deleted is True


# ─── 接口级：list 带 owner 过滤 + 越权删除 403 ───


@pytest.mark.asyncio
async def test_api_list_owner_filtered(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """接口 list：模拟普通用户（偷换 _is_super_admin_user 返回 False）只返回自己的。"""
    await _seed_user(db_session, DEV_USER_ID, "dev用户")
    await _seed_user(db_session, UA, "用户甲")
    await _seed_config(
        db_session,
        name="我配的",
        owner=DEV_USER_ID,
        level="部门级",
        department="101一车间",
    )
    await _seed_config(
        db_session, name="他人配的", owner=UA, level="部门级", department="101一车间"
    )
    # 本项目 client 与 db_session 为独立会话：种的数据需提交，API 才能查到
    await db_session.commit()

    async def _fake_is_admin(db, user):
        return False

    monkeypatch.setattr("app.modules.hr.api._is_super_admin_user", _fake_is_admin)

    resp = await client.get(
        "/api/v1/hr/training-personnel-configs",
        params={"level": "部门级", "department": "101一车间"},
    )
    assert resp.status_code == 200, resp.text
    names = {c["config_name"] for c in resp.json()["data"]}
    assert names == {"我配的"}


@pytest.mark.asyncio
async def test_api_delete_other_forbidden(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """接口 delete：普通用户删除他人配置 → 403。"""
    await _seed_user(db_session, UA, "用户甲")
    cfg = await _seed_config(
        db_session, name="他配的要删", owner=UA, level="部门级", department="101一车间"
    )
    await db_session.commit()

    async def _fake_is_admin(db, user):
        return False

    monkeypatch.setattr("app.modules.hr.api._is_super_admin_user", _fake_is_admin)

    resp = await client.delete(f"/api/v1/hr/training-personnel-configs/{cfg.id}")
    assert resp.status_code == 403, resp.text


# ─── 二级培训会话 from-ledger（建会话+复制试卷+过滤人员）───


@pytest.mark.asyncio
async def test_from_ledger_creates_session_and_copies_docs(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """from-ledger：创建部门级会话、复制上级试卷、返回新 id。"""
    from datetime import date

    from app.modules.hr import api as hr_api
    from app.modules.hr.models import TrainingDocument, TrainingLedger, TrainingSession
    from app.modules.hr.schemas import TrainingSessionFromLedgerRequest

    await _seed_user(db_session, "00000000-0000-0000-0000-000000000099", "台账用户")
    parent = TrainingSession(
        id=uuid4(),
        training_level="公司级",
        department="人事行政部",
        topic="上级公司培训",
        employee_names=["甲", "乙"],
        employee_dept_map={"甲": "101一车间", "乙": "102一车间"},
        created_by="00000000-0000-0000-0000-000000000099",
        updated_by="00000000-0000-0000-0000-000000000099",
    )
    db_session.add(parent)
    await db_session.flush()
    db_session.add(
        TrainingDocument(
            session_id=parent.id,
            doc_type="ai_written_exam",
            title="笔试卷",
            payload={"choice_questions": [{"number": 1, "question": "Q"}]},
            created_by="00000000-0000-0000-0000-000000000099",
            updated_by="00000000-0000-0000-0000-000000000099",
        )
    )
    db_session.add(
        TrainingDocument(
            session_id=parent.id,
            doc_type="evaluation",
            title="评估表",
            payload={"assessment_method": "笔试"},
            created_by="00000000-0000-0000-0000-000000000099",
            updated_by="00000000-0000-0000-0000-000000000099",
        )
    )
    db_session.add(
        TrainingLedger(
            training_date=date(2026, 8, 27),
            training_subject="上级公司培训",
            session_id=parent.id,
            ledger_department="101一车间",
            trainees="甲",
            created_by="00000000-0000-0000-0000-000000000099",
            updated_by="00000000-0000-0000-0000-000000000099",
        )
    )
    await db_session.flush()
    ledger = (
        await db_session.execute(
            select(TrainingLedger).where(TrainingLedger.session_id == parent.id)
        )
    ).scalar_one()
    await db_session.commit()

    # 本项目 client 与 db_session 为独立会话：直接调用端点函数（db=db_session）
    # 使新建会话/文档写入同一会话，测试可查；HTTP 层已有 surface 测试覆盖
    monkeypatch.setattr(hr_api, "_require_user", lambda _user: None)
    import json as _json

    result = await hr_api.create_second_level_session_from_ledger(
        TrainingSessionFromLedgerRequest(record_id=ledger.id),
        db=db_session,
        current_user=SimpleNamespace(id="00000000-0000-0000-0000-000000000099"),
    )
    payload = _json.loads(result.body)
    data = payload["data"]
    assert set(data["copied_doc_types"]) == {"ai_written_exam", "evaluation"}

    copied_docs = (
        (
            await db_session.execute(
                select(TrainingDocument).where(
                    TrainingDocument.session_id == data["id"]
                )
            )
        )
        .scalars()
        .all()
    )
    assert {d.doc_type for d in copied_docs} == {"ai_written_exam", "evaluation"}
    eval_doc = next(d for d in copied_docs if d.doc_type == "evaluation")
    assert eval_doc.payload == {"assessment_method": "笔试"}  # 考核方式随评估表带入

    child = (
        (
            await db_session.execute(
                select(TrainingSession).where(TrainingSession.id == uuid4())
            )
        )
        .scalars()
        .first()
    )
    child = (
        await db_session.execute(
            select(TrainingSession).where(
                TrainingSession.parent_session_id == parent.id
            )
        )
    ).scalar_one()
    assert child.training_level == "部门级"
    assert child.department in (None, "")
    assert child.training_date is None
    assert child.instructor in (None, "")
    assert child.employee_names in (
        None,
        [],
    )  # 二级培训人员由各部门自行配置，不带入上级名单
    assert child.topic == "上级公司培训"  # 只带培训主题

    copied = (
        (
            await db_session.execute(
                select(TrainingDocument).where(TrainingDocument.session_id == child.id)
            )
        )
        .scalars()
        .all()
    )
    assert {d.doc_type for d in copied} == {"ai_written_exam", "evaluation"}
    written = next(d for d in copied if d.doc_type == "ai_written_exam")
    assert written.payload == {"choice_questions": [{"number": 1, "question": "Q"}]}
