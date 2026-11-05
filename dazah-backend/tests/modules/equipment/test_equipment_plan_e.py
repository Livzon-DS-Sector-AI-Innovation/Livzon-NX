"""方案E：转派/工单事件/再报/申请备件/语音回落 测试."""

import uuid as uuid_mod
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    EquipmentPersonnel,
    Location,
    SparePart,
    SparePartPurchaseSuggestion,
    SparePartStock,
)
from app.modules.equipment.schemas import (
    WorkOrderComplete,
    WorkOrderCreate,
    WorkOrderVerify,
)
from app.modules.equipment.service import (
    assign_work_order,
    claim_work_order,
    close_work_order,
    complete_work_order,
    create_work_order,
    get_work_order_events,
    start_work_order,
    transfer_work_order,
    verify_work_order,
)
from app.platform.identity.models import User


def _hex() -> str:
    return uuid_mod.uuid4().hex[:8]


@pytest.fixture
async def e_user(db_session: AsyncSession) -> User:
    user = User(name="方案E用户", employee_no=f"EMP-E-{_hex()}")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def e_assignee2(db_session: AsyncSession) -> User:
    user = User(name="方案E新维修人", employee_no=f"EMP-E2-{_hex()}")
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_equipment(db: AsyncSession, no: str) -> Equipment:
    category = EquipmentCategory(name="泵类E", code=f"PE-{_hex()}")
    db.add(category)
    await db.flush()
    location = Location(name="泵房E", code=f"LE-{_hex()}")
    db.add(location)
    await db.flush()
    eq = Equipment(
        equipment_no=no,
        name=f"反应釜-{no}",
        location_id=location.id,
        status="在用",
        workshop_code="201-1",
    )
    db.add(eq)
    await db.flush()
    return eq


# ==================== 转派与事件 ====================


async def test_transfer_and_events(
    db_session: AsyncSession, e_user: User, e_assignee2: User
) -> None:
    eq = await _make_equipment(db_session, f"EQ-E-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=e_user.id,
    )
    await assign_work_order(db_session, wo.id, e_user.id)
    await start_work_order(db_session, wo.id)

    # 转派（执行中）
    wo = await transfer_work_order(
        db_session, wo.id, e_assignee2.id, operator_id=e_user.id, reason="不在厂"
    )
    assert wo.assignee_id == e_assignee2.id
    assert wo.transfer_count == 1
    assert wo.status == "执行中"
    assert wo.started_at is not None  # 执行中转派保留开始时间

    # 重复转派给同一人被拒
    with pytest.raises(AppException):
        await transfer_work_order(db_session, wo.id, e_assignee2.id)

    # 事件序列完整
    events = await get_work_order_events(db_session, wo.id)
    types = [e.event_type for e in events]
    assert types == ["created", "assigned", "started", "transferred"]
    transferred = events[-1]
    assert transferred.detail["from"] == e_user.name
    assert transferred.detail["to"] == e_assignee2.name
    assert transferred.detail["reason"] == "不在厂"

    # 已关闭不可转派
    await complete_work_order(
        db_session,
        wo.id,
        WorkOrderComplete(repair_detail="ok"),
    )
    await verify_work_order(
        db_session, wo.id, e_user.id, WorkOrderVerify(result="合格")
    )
    await close_work_order(db_session, wo.id)
    with pytest.raises(AppException):
        await transfer_work_order(db_session, wo.id, e_user.id)


async def test_claim_and_close_events_recorded(
    db_session: AsyncSession, e_user: User
) -> None:
    eq = await _make_equipment(db_session, f"EQ-E2-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=e_user.id,
    )
    await claim_work_order(db_session, wo.id, e_user.id)
    await start_work_order(db_session, wo.id)
    # 显式刷新工单对象，避免同一会话内的属性过期时序
    db_session.expire(wo)
    await db_session.refresh(wo)
    assert wo.status == "执行中"
    await complete_work_order(
        db_session,
        wo.id,
        WorkOrderComplete(repair_detail="修好"),
    )
    await verify_work_order(
        db_session, wo.id, e_user.id, WorkOrderVerify(result="合格")
    )
    await close_work_order(db_session, wo.id)

    events = await get_work_order_events(db_session, wo.id)
    types = [e.event_type for e in events]
    assert "claimed" in types
    assert "completed" in types
    assert "verified" in types
    assert "closed" in types
    # 打回事件
    assert "rejected" not in types


async def test_rejected_event_on_verify_fail(
    db_session: AsyncSession, e_user: User
) -> None:
    eq = await _make_equipment(db_session, f"EQ-E3-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=e_user.id,
    )
    await assign_work_order(db_session, wo.id, e_user.id)
    await start_work_order(db_session, wo.id)
    await complete_work_order(
        db_session, wo.id,
        WorkOrderComplete(repair_detail="还有问题"),
    )
    await verify_work_order(
        db_session, wo.id, e_user.id, WorkOrderVerify(result="不合格", remark="未修好")
    )
    events = await get_work_order_events(db_session, wo.id)
    assert events[-1].event_type == "rejected"
    assert events[-1].detail["remark"] == "未修好"


# ==================== 卡片回调：转派 / 申请备件（mock 环境） ====================


def _payload(act: str, **extra) -> dict:
    value = {"act": act, **extra}
    return {
        "operator": {"open_id": "ou_e", "union_id": "on_e", "user_id": ""},
        "action": {"value": value, "tag": "button"},
        "context": {"open_message_id": "om_e", "open_chat_id": "oc_e"},
    }


class _DbCtx:
    """会话替身：吞掉 commit/rollback（处理器按独立会话设计，
    直通共享 db_session 的提交会污染后续测试）。"""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __getattr__(self, name):
        return getattr(self._db, name)

    async def commit(self):
        pass

    async def rollback(self):
        await self._db.rollback()


@pytest.mark.asyncio
async def test_card_transfer_dispatch(monkeypatch, db_session, e_user, e_assignee2):
    """卡片 transfer：当前维修人触发 → 收到候选人卡（含新维修人）。"""
    import app.modules.equipment.service.work_order_feishu as wof

    eq = await _make_equipment(db_session, f"EQ-EC-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=e_user.id,
    )
    await assign_work_order(db_session, wo.id, e_user.id)

    # 人员池加同车间候选
    db_session.add(
        EquipmentPersonnel(
            user_id=e_assignee2.id, name=e_assignee2.name, workshop_code="201-1"
        )
    )
    await db_session.flush()

    monkeypatch.setattr(
        wof,
        "async_session_factory",
        Mock(return_value=_DbCtx(db_session)),
    )
    monkeypatch.setattr(
        wof, "_find_user_by_feishu", AsyncMock(return_value=e_user)
    )
    sends: list[dict] = []

    async def _send(**kw):
        sends.append(kw)

    monkeypatch.setattr(wof, "send_user_card", _send)

    result = await wof.handle_card_action(_payload("transfer", oid=wo.work_order_no))
    assert result["code"] == 0
    # 候选卡已发送（含新维修人姓名按钮）
    assert any(e_assignee2.name in str(s.get("elements")) for s in sends)


@pytest.mark.asyncio
async def test_card_parts_pick_insufficient_creates_suggestion(
    monkeypatch, db_session, e_user
):
    """卡片申请备件：库存 0 → 自动生成采购建议（source=work_order）。"""
    import app.modules.equipment.service.work_order_feishu as wof

    part = SparePart(
        code=f"SP-E-{_hex()}", name="E测试轴承", workshop_code="201-1", unit="个"
    )
    db_session.add(part)
    await db_session.flush()
    db_session.add(SparePartStock(spare_part_id=part.id, current_qty=0, safety_qty=0))
    await db_session.flush()

    eq = await _make_equipment(db_session, f"EQ-EP-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=e_user.id,
    )
    await assign_work_order(db_session, wo.id, e_user.id)

    monkeypatch.setattr(
        wof,
        "async_session_factory",
        Mock(return_value=_DbCtx(db_session)),
    )
    monkeypatch.setattr(
        wof, "_find_user_by_feishu", AsyncMock(return_value=e_user)
    )

    result = await wof.handle_card_action(
        _payload(
            "parts_pick", oid=wo.work_order_no, sp=str(part.id), nm=part.name
        )
    )
    assert result["code"] == 0
    sug = (
        (
            await db_session.execute(
                select(SparePartPurchaseSuggestion).where(
                    SparePartPurchaseSuggestion.spare_part_id == part.id
                )
            )
        )
        .scalars()
        .first()
    )
    assert sug is not None
    assert sug.source == "work_order"
    assert sug.source_work_order_id == wo.id


# ==================== 语音报修：ASR 失败回落 ====================


@pytest.mark.asyncio
async def test_voice_repair_falls_back_when_asr_unavailable(monkeypatch):
    """ASR 返回 None → 回落文字引导卡（链路可用性不依赖 ASR）。"""
    from app.modules.equipment.service import voice_repair

    sends: list[dict] = []

    async def _send(**kw):
        sends.append(kw)

    monkeypatch.setattr(voice_repair, "send_user_card", _send)
    monkeypatch.setattr(voice_repair, "_speech_to_text", AsyncMock(return_value=None))

    class _Redis:
        async def incr(self, key):
            return 1

        async def expire(self, key, ttl):
            return True

    import app.core.redis as redis_mod

    monkeypatch.setattr(redis_mod, "redis_client", _Redis(), raising=False)

    await voice_repair.process_voice_repair(
        user_id="",
        open_id="ou_v",
        union_id="",
        message_id="om_v",
        content='{"file_key":"fk"}',
    )
    assert sends, "应发送回落引导卡"
    assert any("语音报修暂不可用" in (s.get("title") or "") for s in sends)


@pytest.mark.asyncio
async def test_voice_repair_success_path(monkeypatch):
    """ASR 成功 → 识别回执 + 进入文字报修链路。"""
    from app.modules.equipment.service import voice_repair

    calls: list[str] = []
    sends: list[dict] = []

    async def _send(**kw):
        sends.append(kw)

    async def _asr(audio):
        return "201一车间 离心泵 漏了"

    async def _download(mid, fk):
        return b"opus-bytes"

    async def _create(**kw):
        calls.append(kw.get("text", ""))

    monkeypatch.setattr(voice_repair, "send_user_card", _send)
    monkeypatch.setattr(voice_repair, "_speech_to_text", AsyncMock(side_effect=_asr))
    monkeypatch.setattr(
        voice_repair, "_download_voice", AsyncMock(side_effect=_download)
    )

    import app.modules.equipment.service.work_order_feishu as wof

    monkeypatch.setattr(wof, "create_repair_by_text", AsyncMock(side_effect=_create))

    class _Redis:
        async def incr(self, key):
            return 1

        async def expire(self, key, ttl):
            return True

    import app.core.redis as redis_mod

    monkeypatch.setattr(redis_mod, "redis_client", _Redis(), raising=False)

    await voice_repair.process_voice_repair(
        user_id="",
        open_id="ou_v2",
        union_id="",
        message_id="om_v2",
        content='{"file_key":"fk2"}',
    )
    assert calls and calls[0].startswith("报修 201一车间")
    assert any("语音已识别" in (s.get("title") or "") for s in sends)
