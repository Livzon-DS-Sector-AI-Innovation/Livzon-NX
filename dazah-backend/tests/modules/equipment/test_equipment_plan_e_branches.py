"""方案E 深分支覆盖：卡片构建器、调度器、语音报修、转派/备件/再报处理器分支."""

import uuid as uuid_mod
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    EquipmentCategoryLink,
    EquipmentPersonnel,
    Location,
    SparePart,
    SparePartPurchaseSuggestion,
    SparePartStock,
    WorkOrder,
)
from app.modules.equipment.schemas import (
    WorkOrderComplete,
    WorkOrderCreate,
    WorkOrderVerify,
)
from app.modules.equipment.service import (
    assign_work_order,
    close_work_order,
    complete_work_order,
    create_work_order,
    start_work_order,
    verify_work_order,
)
from app.platform.identity.models import User


def _hex() -> str:
    return uuid_mod.uuid4().hex[:8]


def _toast(result: dict) -> tuple[str, str]:
    toast = result.get("toast") or {}
    return toast.get("type", ""), toast.get("content", "")


@pytest.fixture
async def b_user(db_session: AsyncSession) -> User:
    user = User(name="方案E分支用户", employee_no=f"EMP-B1-{_hex()}")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def b_user2(db_session: AsyncSession) -> User:
    user = User(name="方案E分支用户2", employee_no=f"EMP-B2-{_hex()}")
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_equipment(db: AsyncSession, no: str) -> Equipment:
    category = EquipmentCategory(name="泵类B", code=f"PB-{_hex()}")
    db.add(category)
    await db.flush()
    location = Location(name="泵房B", code=f"LB-{_hex()}")
    db.add(location)
    await db.flush()
    eq = Equipment(
        equipment_no=no,
        name=f"反应釜B-{no}",
        location_id=location.id,
        status="在用",
        workshop_code="201-1",
    )
    db.add(eq)
    await db.flush()
    db.add(
        EquipmentCategoryLink(equipment_id=eq.id, category_id=category.id)
    )
    await db.flush()
    return eq


async def _open_fault_order(
    db: AsyncSession, eq: Equipment, user: User
) -> WorkOrder:
    wo = await create_work_order(
        db,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=user.id,
    )
    await assign_work_order(db, wo.id, user.id)
    return wo


async def _close_order(db: AsyncSession, wo: WorkOrder, user: User) -> None:
    await start_work_order(db, wo.id)
    await complete_work_order(
        db, wo.id, WorkOrderComplete(repair_detail="ok")
    )
    await verify_work_order(
        db, wo.id, user.id, WorkOrderVerify(result="合格")
    )
    await close_work_order(db, wo.id)


# ==================== 卡片构建器（纯函数） ====================


def test_transfer_candidates_card_build() -> None:
    from app.modules.equipment.feishu.plan_e_cards import (
        build_transfer_candidates_card,
    )

    card = build_transfer_candidates_card(
        work_order_no="WO-1",
        candidates=[
            {"user_id": "u1", "name": "张三", "employee_no": "E001"},
            {"user_id": "u2", "name": "李四", "employee_no": None},
        ],
    )
    assert card["header"]["template"] == "turquoise"
    actions = [e for e in card["elements"] if e.get("tag") == "action"][0]
    assert [a["text"]["content"] for a in actions["actions"]] == [
        "张三（E001）",
        "李四（-）",
    ]
    assert actions["actions"][0]["value"] == {
        "act": "transfer_pick", "oid": "WO-1", "uid": "u1"
    }


def test_parts_select_card_stock_states() -> None:
    from app.modules.equipment.feishu.plan_e_cards import (
        build_parts_select_card,
    )

    card = build_parts_select_card(
        work_order_no="WO-2",
        equipment_label="离心泵（LB-01）",
        parts=[
            {"id": "p1", "name": "轴承", "current_qty": 5},
            {"id": "p2", "name": "密封圈", "current_qty": 0},
        ],
    )
    fields = [e for e in card["elements"] if e.get("fields")][0]["fields"]
    assert "✅" in fields[0]["text"]["content"]
    assert "❌缺货" in fields[1]["text"]["content"]
    actions = [e for e in card["elements"] if e.get("tag") == "action"][0][
        "actions"
    ]
    assert actions[0]["value"] == {
        "act": "parts_pick", "oid": "WO-2", "sp": "p1", "nm": "轴承"
    }

    empty = build_parts_select_card(
        work_order_no="WO-3", equipment_label="设备", parts=[]
    )
    assert not [e for e in empty["elements"] if e.get("fields")]


def test_repay_confirm_card_truncates_and_defaults() -> None:
    from app.modules.equipment.feishu.plan_e_cards import (
        build_repay_confirm_card,
    )

    card = build_repay_confirm_card(
        equipment_label="离心泵（LB-02）",
        equipment_id="eq-1",
        workshop_code="201-1",
        last_fault="漏" * 100,
        work_order_no="WO-4",
    )
    actions = [e for e in card["elements"] if e.get("tag") == "action"][0][
        "actions"
    ]
    assert actions[0]["type"] == "primary"
    assert len(actions[0]["value"]["ft"]) == 60
    assert actions[1]["value"] == {"act": "repay_cancel"}

    default = build_repay_confirm_card(
        equipment_label="设备",
        equipment_id="eq-2",
        workshop_code="",
        last_fault="",
        work_order_no="WO-5",
    )
    body = [e for e in default["elements"] if e.get("text")][0]["text"]
    assert "设备故障" in body["content"]


# ==================== 调度器（方案B/C/E 新增任务项） ====================


async def test_plan_bce_scheduled_generators(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """健康快照/月报/采购扫描三个任务项的取数与执行分发."""
    import app.modules.equipment.service.health as health_mod
    import app.modules.equipment.service.monthly_report as mr_mod
    import app.modules.equipment.service.purchase_suggestion as ps_mod
    from app.modules.equipment import scheduled

    calls: list[str] = []

    async def _snapshots(db):
        calls.append("snapshots")
        return {"total": 0}

    monkeypatch.setattr(health_mod, "generate_daily_snapshots", _snapshots)
    health_gen = scheduled.EquipmentHealthSnapshotGenerator()
    assert await health_gen.find_due(db_session) == ["all"]
    await health_gen.execute_one(db_session, "all")
    assert calls == ["snapshots"]

    async def _report(db, month, operator_id=None):
        calls.append(f"report:{month}")
        return SimpleNamespace(report_month=month)

    monkeypatch.setattr(mr_mod, "generate_monthly_report", _report)
    report_gen = scheduled.EquipmentMonthlyHealthReportGenerator()
    due = await report_gen.find_due(db_session)
    assert len(due) == 1 and "-" in due[0]
    await report_gen.execute_one(db_session, due[0])
    assert f"report:{due[0]}" in calls

    async def _scan(db):
        calls.append("scan")
        return {"created": 0}

    async def _notify(db):
        calls.append("notify")

    monkeypatch.setattr(ps_mod, "scan_and_suggest", _scan)
    monkeypatch.setattr(ps_mod, "notify_low_stock_summary", _notify)
    scan_gen = scheduled.SparePartPurchaseScanGenerator()
    assert await scan_gen.find_due(db_session) == ["all"]
    await scan_gen.execute_one(db_session, "all")
    assert calls[-2:] == ["scan", "notify"]


# ==================== 语音报修分支 ====================


class _RedisCount:
    def __init__(self, count: int):
        self._count = count

    async def incr(self, key):
        return self._count

    async def expire(self, key, ttl):
        return True


def _send_capture(sends: list | None):
    async def _send(**kw):
        if sends is not None:
            sends.append(kw)

    return _send


def _voice_setup(monkeypatch, *, redis_count=1, sends=None):
    import app.core.redis as redis_mod
    from app.modules.equipment.service import voice_repair

    monkeypatch.setattr(
        redis_mod, "redis_client", _RedisCount(redis_count), raising=False
    )
    download = AsyncMock(return_value=b"opus")
    asr = AsyncMock(return_value="离心泵漏了")
    monkeypatch.setattr(voice_repair, "_download_voice", download)
    monkeypatch.setattr(voice_repair, "_speech_to_text", asr)
    monkeypatch.setattr(voice_repair, "send_user_card", _send_capture(sends))
    return voice_repair


async def _run_voice(vr, *, open_id="ou", content="{}") -> None:
    await vr.process_voice_repair(
        user_id="", open_id=open_id, union_id="", message_id="om",
        content=content,
    )


async def test_voice_rate_limited(monkeypatch, db_session) -> None:
    sends: list[dict] = []
    vr = _voice_setup(monkeypatch, redis_count=4, sends=sends)
    await _run_voice(vr)
    assert any("太频繁" in (s.get("title") or "") for s in sends)
    vr._download_voice.assert_not_awaited()  # noqa: SLF001


async def test_voice_invalid_json_falls_back(monkeypatch, db_session) -> None:
    sends: list[dict] = []
    vr = _voice_setup(monkeypatch, sends=sends)
    await _run_voice(vr, content="not-a-json")
    assert any("语音文件读取失败" in (s.get("content") or "") for s in sends)


async def test_voice_download_none_falls_back(monkeypatch, db_session) -> None:
    sends: list[dict] = []
    vr = _voice_setup(monkeypatch, sends=sends)
    monkeypatch.setattr(vr, "_download_voice", AsyncMock(return_value=None))
    await _run_voice(vr, content='{"file_key":"fk"}')
    assert any("语音文件下载失败" in (s.get("content") or "") for s in sends)


async def test_voice_empty_text_falls_back(monkeypatch, db_session) -> None:
    sends: list[dict] = []
    vr = _voice_setup(monkeypatch, sends=sends)
    monkeypatch.setattr(vr, "_speech_to_text", AsyncMock(return_value=""))
    await _run_voice(vr, content='{"file_key":"fk"}')
    assert any("语音未能识别" in (s.get("content") or "") for s in sends)


async def test_voice_asr_exception_outer_fallback(
    monkeypatch, db_session
) -> None:
    sends: list[dict] = []
    vr = _voice_setup(monkeypatch, sends=sends)

    async def _boom(audio):
        raise RuntimeError("asr exploded")

    monkeypatch.setattr(vr, "_speech_to_text", AsyncMock(side_effect=_boom))
    await _run_voice(vr, content='{"file_key":"fk"}')
    assert any("语音处理异常" in (s.get("content") or "") for s in sends)


async def test_voice_fallback_send_failure_swallowed(
    monkeypatch, db_session
) -> None:
    """回落提示本身发送失败也不得向外抛异常."""
    import app.core.redis as redis_mod
    from app.modules.equipment.service import voice_repair

    monkeypatch.setattr(
        redis_mod, "redis_client", _RedisCount(1), raising=False
    )

    async def _send_raises(**kw):
        raise RuntimeError("send failed")

    monkeypatch.setattr(voice_repair, "send_user_card", _send_raises)
    await voice_repair.process_voice_repair(
        user_id="", open_id="ou_f", union_id="", message_id="om",
        content="bad-json",
    )


async def test_speech_to_text_httpx_branches(monkeypatch, db_session) -> None:
    """ASR 内部分支：非 200 / 业务码非 0 / data.text / 全空 / 请求异常."""
    import httpx

    from app.modules.equipment.service import voice_repair

    monkeypatch.setattr(
        "app.modules.equipment.feishu.client.get_equipment_feishu_client",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "app.modules.equipment.feishu.client.get_equipment_tenant_token",
        AsyncMock(return_value="token"),
    )

    class _Resp:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

    class _Http:
        def __init__(self, resp=None, exc=None):
            self._resp = resp
            self._exc = exc

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            if self._exc is not None:
                raise self._exc
            return self._resp

    def _patch(resp=None, exc=None):
        monkeypatch.setattr(
            httpx, "AsyncClient", lambda **kw: _Http(resp=resp, exc=exc)
        )

    _patch(resp=_Resp(status_code=500))
    assert await voice_repair._speech_to_text(b"a") is None  # noqa: SLF001

    _patch(resp=_Resp(payload={"code": 12345}))
    assert await voice_repair._speech_to_text(b"a") is None  # noqa: SLF001

    _patch(resp=_Resp(payload={"code": 0, "text": " 泵漏 "}))
    assert await voice_repair._speech_to_text(b"a") == "泵漏"  # noqa: SLF001

    _patch(resp=_Resp(payload={"code": 0, "data": {"text": "电机过热"}}))
    assert await voice_repair._speech_to_text(b"a") == "电机过热"  # noqa: SLF001

    _patch(resp=_Resp(payload={"code": 0, "text": ""}))
    assert await voice_repair._speech_to_text(b"a") is None  # noqa: SLF001

    _patch(exc=RuntimeError("boom"))
    assert await voice_repair._speech_to_text(b"a") is None  # noqa: SLF001


# ==================== 卡片处理器公共替身 ====================


class _DbCtx:
    """会话替身：吞掉 commit（处理器按独立会话设计）."""

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


def _card_payload(act: str, **extra) -> dict:
    value = {"act": act, **extra}
    return {
        "operator": {"open_id": "ou_b", "union_id": "on_b", "user_id": ""},
        "action": {"value": value, "tag": "button"},
        "context": {"open_message_id": "om_b", "open_chat_id": "oc_b"},
    }


def _patch_wof(monkeypatch, db, *, user, sends=None):
    import app.modules.equipment.service.work_order_feishu as wof

    monkeypatch.setattr(
        wof, "async_session_factory", Mock(return_value=_DbCtx(db))
    )
    monkeypatch.setattr(
        wof, "_find_user_by_feishu", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(wof, "send_user_card", _send_capture(sends))
    return wof


# ==================== 卡片处理器：转派 ====================


async def test_transfer_handler_reject_branches(
    monkeypatch, db_session, b_user, b_user2
) -> None:
    eq = await _make_equipment(db_session, f"EQ-T1-{_hex()}")
    wo = await _open_fault_order(db_session, eq, b_user)

    wof = _patch_wof(monkeypatch, db_session, user=None)
    kind, content = _toast(
        await wof._handle_transfer_action(  # noqa: SLF001
            _card_payload("transfer", oid=wo.work_order_no),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "未绑定" in content

    wof = _patch_wof(monkeypatch, db_session, user=b_user)
    kind, content = _toast(
        await wof._handle_transfer_action(  # noqa: SLF001
            _card_payload("transfer", oid="WO-NOT-EXIST"),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "不存在" in content

    # 非当前维修人不可发起（操作者是另一名用户）
    await start_work_order(db_session, wo.id)
    wof = _patch_wof(monkeypatch, db_session, user=b_user2)
    kind, content = _toast(
        await wof._handle_transfer_action(  # noqa: SLF001
            _card_payload("transfer", oid=wo.work_order_no),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "当前维修人" in content

    # 已关闭工单不可转派（换回当前维修人操作）
    eq2 = await _make_equipment(db_session, f"EQ-T2-{_hex()}")
    wo2 = await _open_fault_order(db_session, eq2, b_user)
    await _close_order(db_session, wo2, b_user)
    wof = _patch_wof(monkeypatch, db_session, user=b_user)
    kind, content = _toast(
        await wof._handle_transfer_action(  # noqa: SLF001
            _card_payload("transfer", oid=wo2.work_order_no),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "无需转派" in content


async def test_transfer_no_candidates_fails(
    monkeypatch, db_session, b_user
) -> None:
    eq = await _make_equipment(db_session, f"EQ-T3-{_hex()}")
    wo = await _open_fault_order(db_session, eq, b_user)
    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    kind, content = _toast(
        await wof._handle_transfer_action(  # noqa: SLF001
            _card_payload("transfer", oid=wo.work_order_no),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "暂无其他" in content
    assert any("暂无其他" in (s.get("content") or "") for s in sends)


async def test_transfer_pick_executes(
    monkeypatch, db_session, b_user, b_user2
) -> None:
    eq = await _make_equipment(db_session, f"EQ-T4-{_hex()}")
    wo = await _open_fault_order(db_session, eq, b_user)
    await start_work_order(db_session, wo.id)
    db_session.add(
        EquipmentPersonnel(
            user_id=b_user2.id, name=b_user2.name, workshop_code="201-1"
        )
    )
    await db_session.flush()

    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    kind, content = _toast(
        await wof._handle_transfer_action(  # noqa: SLF001
            _card_payload("transfer_pick", oid=wo.work_order_no, uid=b_user2.id),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "success", content
    assert b_user2.name in content
    await db_session.refresh(wo)
    assert wo.assignee_id == b_user2.id
    assert wo.transfer_count == 1


# ==================== 卡片处理器：申请备件 ====================


async def _make_part(db: AsyncSession, *, qty: int, price=10) -> SparePart:
    part = SparePart(
        code=f"SP-B-{_hex()}",
        name=f"B备件{_hex()}",
        workshop_code="201-1",
        unit="个",
        unit_price=price,
    )
    db.add(part)
    await db.flush()
    db.add(
        SparePartStock(spare_part_id=part.id, current_qty=qty, safety_qty=1)
    )
    await db.flush()
    return part


async def test_parts_list_card_and_status_reject(
    monkeypatch, db_session, b_user
) -> None:
    eq = await _make_equipment(db_session, f"EQ-P1-{_hex()}")
    wo = await _open_fault_order(db_session, eq, b_user)

    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)

    # 车间无备件登记
    kind, content = _toast(
        await wof._handle_parts_action(  # noqa: SLF001
            _card_payload("parts_list", oid=wo.work_order_no),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "暂无登记备件" in content

    part = await _make_part(db_session, qty=3)
    sends.clear()
    kind, content = _toast(
        await wof._handle_parts_action(  # noqa: SLF001
            _card_payload("parts_list", oid=wo.work_order_no),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "success"
    card_send = [s for s in sends if s.get("elements")][0]
    assert any(part.name in str(el) for el in card_send["elements"])

    # 已关闭工单不可领料
    await _close_order(db_session, wo, b_user)
    kind, content = _toast(
        await wof._handle_parts_action(  # noqa: SLF001
            _card_payload("parts_list", oid=wo.work_order_no),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "不可领料" in content


async def test_parts_pick_invalid_uuid_and_consume_error(
    monkeypatch, db_session, b_user
) -> None:
    eq = await _make_equipment(db_session, f"EQ-P2-{_hex()}")
    wo = await _open_fault_order(db_session, eq, b_user)

    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    kind, content = _toast(
        await wof._handle_parts_action(  # noqa: SLF001
            _card_payload("parts_pick", oid=wo.work_order_no, sp="not-uuid"),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "备件信息无效" in content

    part = await _make_part(db_session, qty=2)
    import app.modules.equipment.service.work_order as wo_mod

    async def _raise(db, wo_id, items):
        raise RuntimeError("boom")

    monkeypatch.setattr(wo_mod, "consume_materials", _raise)
    kind, content = _toast(
        await wof._handle_parts_action(  # noqa: SLF001
            _card_payload(
                "parts_pick", oid=wo.work_order_no, sp=part.id, nm=part.name
            ),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "领料失败" in content


async def test_parts_pick_in_stock_consumes(
    monkeypatch, db_session, b_user
) -> None:
    eq = await _make_equipment(db_session, f"EQ-P3-{_hex()}")
    wo = await _open_fault_order(db_session, eq, b_user)
    part = await _make_part(db_session, qty=2, price=8)

    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    kind, content = _toast(
        await wof._handle_parts_action(  # noqa: SLF001
            _card_payload(
                "parts_pick", oid=wo.work_order_no, sp=part.id, nm=part.name
            ),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "success", content
    assert "已领用" in content
    await db_session.refresh(wo)
    assert float(wo.spare_parts_cost) == 8.0


async def test_parts_pick_existing_open_suggestion_reused(
    monkeypatch, db_session, b_user
) -> None:
    eq = await _make_equipment(db_session, f"EQ-P4-{_hex()}")
    wo = await _open_fault_order(db_session, eq, b_user)
    part = SparePart(
        code=f"SP-B4-{_hex()}", name="B测试皮带", workshop_code="201-1",
        unit="条",
    )
    db_session.add(part)
    await db_session.flush()
    db_session.add(
        SparePartStock(spare_part_id=part.id, current_qty=0, safety_qty=0)
    )
    db_session.add(
        SparePartPurchaseSuggestion(
            spare_part_id=part.id,
            current_qty=0,
            safety_qty=2,
            suggest_qty=4,
            status="submitted",
        )
    )
    await db_session.flush()

    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    kind, content = _toast(
        await wof._handle_parts_action(  # noqa: SLF001
            _card_payload(
                "parts_pick", oid=wo.work_order_no, sp=part.id, nm=part.name
            ),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "success" and "已有进行中的采购建议" in content


# ==================== 再报上次 ====================


async def test_repay_cancel_and_rejects(
    monkeypatch, db_session, b_user
) -> None:
    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    kind, content = _toast(
        await wof._handle_repay_action(  # noqa: SLF001
            _card_payload("repay_cancel"), open_id="ou_b", union_id="",
        )
    )
    assert kind == "success" and "已取消" in content

    wof = _patch_wof(monkeypatch, db_session, user=None, sends=sends)
    kind, content = _toast(
        await wof._handle_repay_action(  # noqa: SLF001
            _card_payload("repay_confirm", eq=str(uuid_mod.uuid4())),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "未绑定" in content

    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    kind, content = _toast(
        await wof._handle_repay_action(  # noqa: SLF001
            _card_payload("repay_confirm", eq="bad-uuid"),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error" and "设备信息无效" in content


async def test_repay_confirm_creates_and_tolerates_dispatch_failure(
    monkeypatch, db_session, b_user
) -> None:
    eq = await _make_equipment(db_session, f"EQ-R1-{_hex()}")
    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)

    async def _dispatch_raises(**kw):
        raise RuntimeError("chat down")

    monkeypatch.setattr(wof, "dispatch_repair_card", _dispatch_raises)
    kind, content = _toast(
        await wof._handle_repay_action(  # noqa: SLF001
            _card_payload(
                "repay_confirm", eq=str(eq.id), ft="密封泄漏", ws="201-1",
                el=f"{eq.name}（{eq.equipment_no}）",
            ),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "success", content
    assert "已建单" in content

    created = (
        (
            await db_session.execute(
                select(WorkOrder).where(
                    WorkOrder.equipment_id == eq.id,
                    WorkOrder.fault_description.like("[再报]%"),
                )
            )
        )
        .scalars()
        .first()
    )
    assert created is not None
    assert created.reporter_id == b_user.id


async def test_repay_confirm_business_rejection(
    monkeypatch, db_session, b_user
) -> None:
    """同设备已有开放工单时建单被业务规则拒绝 → 卡片回错并回滚."""
    eq = await _make_equipment(db_session, f"EQ-R2-{_hex()}")
    await _open_fault_order(db_session, eq, b_user)
    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    kind, content = _toast(
        await wof._handle_repay_action(  # noqa: SLF001
            _card_payload("repay_confirm", eq=str(eq.id), ft="又漏了"),
            open_id="ou_b", union_id="",
        )
    )
    assert kind == "error"


async def test_send_repay_confirm_card_paths(
    monkeypatch, db_session, b_user
) -> None:
    eq = await _make_equipment(db_session, f"EQ-R3-{_hex()}")
    sends: list[dict] = []
    wof = _patch_wof(monkeypatch, db_session, user=None, sends=sends)
    await wof.send_repay_confirm_card(user_id="", open_id="ou_n", union_id="")
    assert any("未绑定" in (s.get("content") or "") for s in sends)

    # 有绑定但无近 30 天报修记录
    sends.clear()
    wof = _patch_wof(monkeypatch, db_session, user=b_user, sends=sends)
    await wof.send_repay_confirm_card(user_id="", open_id="ou_h", union_id="")
    assert any("没有你的报修记录" in (s.get("content") or "") for s in sends)

    # 有历史报修 → 预填确认卡（按钮带设备标签）
    await create_work_order(
        db_session,
        WorkOrderCreate(
            equipment_id=eq.id,
            order_type="故障维修",
            fault_description="上次漏了",
        ),
        reporter_id=b_user.id,
    )
    sends.clear()
    await wof.send_repay_confirm_card(user_id="", open_id="ou_y", union_id="")
    confirm_sends = [
        s for s in sends
        if any(isinstance(el, dict) and el.get("actions")
               for el in s.get("elements") or [])
    ]
    assert confirm_sends, sends
    found = False
    for el in confirm_sends[0]["elements"]:
        for btn in el.get("actions", []):
            if btn["value"].get("act") == "repay_confirm":
                assert btn["value"]["eq"] == str(eq.id)
                assert eq.equipment_no in btn["value"]["el"]
                found = True
    assert found
