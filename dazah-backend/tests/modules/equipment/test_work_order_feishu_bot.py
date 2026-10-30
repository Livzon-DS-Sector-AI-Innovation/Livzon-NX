"""飞书报修机器人逻辑单测：分词匹配、镜像回落注册、建单分支与卡片回调。"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.equipment.service.work_order_feishu as wof
from app.modules.equipment.service.work_order_feishu import (
    _compact_hit,
    _match_equipments,
    _patch_card_reliably,
    _register_mirror_equipment,
    _split_tokens,
    create_repair_by_text,
    handle_card_action,
)

USER_ID = str(uuid.uuid4())


def _ws(code="201-1", name="201一车间"):
    return SimpleNamespace(code=code, name=name)


def _eq(name="离心泵A", no="LB-DEMO-8", status="在用"):
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, equipment_no=no, status=status,
        workshop_code="201-1",
    )


class _Scalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)

    def __iter__(self):
        return iter(self._items)

    def first(self):
        return self._items[0] if self._items else None


class _Result:
    def __init__(self, items):
        self._scalars = _Scalars(items)

    def scalars(self):
        return self._scalars


class _DbCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


def _db_mock(rows_by_call=None):
    db = Mock()
    results = list(rows_by_call or [])
    db.execute = AsyncMock(side_effect=[_Result(r) for r in results])
    db.commit = AsyncMock()
    db.add = Mock()
    db.flush = AsyncMock()
    return db


def _factory(db):
    return Mock(return_value=_DbCtx(db))


# ── 纯函数 ──────────────────────────────────────────────


def test_split_tokens_drops_short_and_strip_words():
    tokens = _split_tokens("201一车间 下卸料离心机 漏了 紧急", "201-1", "201一车间")
    # 紧急词由 create_repair_by_text 先行剔除，这里只验证分词与去干扰词
    assert tokens == ["下卸料离心机", "漏了", "紧急"]


def test_compact_hit_matches_name_with_spaces():
    assert _compact_hit("下卸料离心机 1", None, "下卸料离心机1漏了")
    assert not _compact_hit("下卸料离心机 2", None, "下卸料离心机1漏了")
    assert _compact_hit(None, "XT1-1-1-078", "漏了XT1-1-1-078")


@pytest.mark.asyncio
async def test_match_equipments_exact_over_token():
    eq_a, eq_b = _eq("离心泵A"), _eq("离心泵B")
    db = _db_mock([[eq_a, eq_b]])
    matched = await _match_equipments(db, "201-1", ["离心泵"], body="离心泵B 漏了")
    assert matched == [eq_b]


@pytest.mark.asyncio
async def test_register_mirror_equipment_reuses_existing_by_no():
    existing = _eq("下卸料离心机 1", "XT1-1-1-078")
    db = _db_mock([[existing]])
    device = SimpleNamespace(
        equipment_no="XT1-1-1-078", equipment_name="下卸料离心机 1",
        workshop_code="201-1", record_id="rec1",
    )
    got = await _register_mirror_equipment(db, device)
    assert got is existing
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_register_mirror_equipment_creates_with_location():
    from app.modules.equipment.models.equipment import Location

    location = Location(name="一楼泵房", code="P1")
    location.id = uuid.uuid4()
    db = _db_mock([[], [location]])

    def _flush():
        for call in db.add.call_args_list:
            obj = call.args[0]
            if getattr(obj, "equipment_no", "") == "XT1-1-1-078":
                obj.id = uuid.uuid4()

    db.flush = AsyncMock(side_effect=_flush)
    device = SimpleNamespace(
        equipment_no="XT1-1-1-078", equipment_name="下卸料离心机 1",
        workshop_code="201-1", record_id="rec1",
    )
    eq = await _register_mirror_equipment(db, device)
    assert eq.name == "下卸料离心机 1"
    assert eq.status == "在用"


# ── create_repair_by_text 分支 ─────────────────────────


def _patch_flow(monkeypatch, db, *, workshops, equipments=None, mirror=None):
    sends: list = []
    monkeypatch.setattr(wof, "async_session_factory", _factory(db), raising=False)
    user_obj = SimpleNamespace(id=USER_ID, name="秦佳豪", username="qin")
    monkeypatch.setattr(
        wof, "_find_user_by_feishu", AsyncMock(return_value=user_obj)
    )
    monkeypatch.setattr(
        wof, "_match_workshops", AsyncMock(return_value=workshops)
    )
    monkeypatch.setattr(
        wof,
        "_match_equipments",
        AsyncMock(return_value=equipments if equipments is not None else []),
    )
    mirror_rows = mirror if mirror is not None else []
    # create_repair_by_text 先查注册车间（LLM 接地），再查巡检镜像
    lead_ws = workshops[0] if workshops else _ws()
    db.execute = AsyncMock(
        side_effect=[_Result([lead_ws]), _Result(mirror_rows)]
    )
    monkeypatch.setattr(
        wof, "_sample_ledger_names", AsyncMock(return_value=[]), raising=False
    )
    eq = equipments[0] if equipments else _eq()
    monkeypatch.setattr(
        wof, "_register_mirror_equipment", AsyncMock(return_value=eq), raising=False
    )
    wo = SimpleNamespace(
        id=uuid.uuid4(), work_order_no="WO-1", status="待处理",
        priority="高", equipment=eq,
    )
    monkeypatch.setattr(
        wof, "create_work_order", AsyncMock(return_value=wo), raising=False
    )
    monkeypatch.setattr(wof, "dispatch_repair_card", AsyncMock(), raising=False)

    async def _send(*, open_id, title, content, receive_id_type="open_id", **kw):
        sends.append((title, content))

    monkeypatch.setattr(wof, "send_user_card", _send)
    return sends


@pytest.mark.asyncio
async def test_repair_requires_content_shows_format_help(monkeypatch):
    db = _db_mock()
    sends = _patch_flow(monkeypatch, db, workshops=[])
    await create_repair_by_text(user_id="", open_id="ou_1", text="报修")
    assert any("报修格式" in t for t, _ in sends)


@pytest.mark.asyncio
async def test_repair_unknown_workshop_lists_enabled(monkeypatch):
    db = _db_mock([[_ws(), _ws("301-1", "301一车间")]])
    sends = _patch_flow(monkeypatch, db, workshops=[])
    await create_repair_by_text(
        user_id="", open_id="ou_1", text="报修 九车间 离心泵 漏了"
    )
    assert any("未识别车间" in t for t, _ in sends)


@pytest.mark.asyncio
async def test_repair_multiple_workshops_asks_full_name(monkeypatch):
    db = _db_mock()
    sends = _patch_flow(
        monkeypatch, db, workshops=[_ws(), _ws("201-2", "201二车间")]
    )
    await create_repair_by_text(
        user_id="", open_id="ou_1", text="报修 201 离心泵 漏了"
    )
    assert any("多个车间" in t or "匹配到多个车间" in t for t, _ in sends)


@pytest.mark.asyncio
async def test_repair_urgent_keyword_creates_urgent_order(monkeypatch):
    eq = _eq("离心泵A")
    db = _db_mock()
    sends = _patch_flow(monkeypatch, db, workshops=[_ws()], equipments=[eq])
    await create_repair_by_text(
        user_id="", open_id="ou_1", text="报修 201一车间 离心泵A 漏了 紧急"
    )
    wof.create_work_order.assert_awaited_once()  # type: ignore[attr-defined]
    order = wof.create_work_order.await_args.args[1]  # type: ignore[attr-defined]
    assert order.priority == "紧急"
    assert "漏了" in order.fault_description
    assert any("WO-1" in c for _, c in sends)


@pytest.mark.asyncio
async def test_repair_mirror_multi_match_lists_candidates(monkeypatch):
    db = _db_mock()
    devices = [
        SimpleNamespace(equipment_name=f"下卸料离心机 {i}", equipment_no=f"XT-{i}")
        for i in (1, 2)
    ]
    sends = _patch_flow(monkeypatch, db, workshops=[_ws()], mirror=devices)
    await create_repair_by_text(
        user_id="", open_id="ou_1", text="报修 201一车间 下卸料离心机 漏了"
    )
    assert any("多台设备" in t for t, _ in sends)


@pytest.mark.asyncio
async def test_repair_no_match_shows_mirror_samples(monkeypatch):
    db = _db_mock()
    device = SimpleNamespace(
        equipment_name="酸化罐 1", equipment_no="XT1-1-1-028"
    )
    sends = _patch_flow(monkeypatch, db, workshops=[_ws()], mirror=[device])
    await create_repair_by_text(
        user_id="", open_id="ou_1", text="报修 201一车间 空压机 漏了"
    )
    assert any("未识别设备" in t and "酸化罐 1" in c for t, c in sends)


# ── 卡片回调 ────────────────────────────────────────────


def _payload(act="accept", oid="WO-1", open_id="ou_1"):
    return {
        "operator": {"open_id": open_id, "union_id": "on_1", "user_id": ""},
        "action": {"value": {"act": act, "oid": oid}, "tag": "button"},
        "context": {"open_message_id": "om_1", "open_chat_id": "oc_1"},
    }


class _Redis:
    async def get(self, key):
        return "om_redis"


def _patch_card_env(monkeypatch, db, *, user, wo):
    monkeypatch.setattr(wof, "async_session_factory", _factory(db), raising=False)
    monkeypatch.setattr(wof, "_find_user_by_feishu", AsyncMock(return_value=user))
    monkeypatch.setattr(wof.repo, "get_work_order_by_no", AsyncMock(return_value=wo))
    monkeypatch.setattr("app.core.redis.redis_client", _Redis(), raising=False)

    import app.modules.equipment.service.work_order as wo_svc

    monkeypatch.setattr(wo_svc, "assign_work_order", AsyncMock(return_value=wo))
    monkeypatch.setattr(wo_svc, "start_work_order", AsyncMock(return_value=wo))
    monkeypatch.setattr(wo_svc, "complete_work_order", AsyncMock(return_value=wo))
    monkeypatch.setattr(
        wof, "_patch_card_reliably", AsyncMock(), raising=False
    )
    sends: list = []

    async def _send(**kw):
        sends.append(kw)

    monkeypatch.setattr(wof, "send_user_card", _send)
    return sends


@pytest.mark.asyncio
async def test_card_action_accept_commits_and_schedules_patch(monkeypatch):
    db = _db_mock()
    user_obj = SimpleNamespace(id=USER_ID, name="秦佳豪", username="q")
    wo = SimpleNamespace(
        id=uuid.uuid4(), status="待处理",
        equipment=SimpleNamespace(name="离心泵A", equipment_no="LB-DEMO-8"),
    )
    _patch_card_env(monkeypatch, db, user=user_obj, wo=wo)

    result = await handle_card_action(_payload())

    assert result["code"] == 0
    db.commit.assert_awaited()
    # 后台补丁任务异步调度，不阻塞回调返回
    wof._patch_card_reliably.assert_not_awaited()


@pytest.mark.asyncio
async def test_card_action_rejects_wrong_status(monkeypatch):
    db = _db_mock()
    user_obj = SimpleNamespace(id=USER_ID, name="秦佳豪", username="q")
    wo = SimpleNamespace(
        id=uuid.uuid4(), status="已关闭",
        equipment=SimpleNamespace(name="离心泵A", equipment_no="LB-DEMO-8"),
    )
    sends = _patch_card_env(monkeypatch, db, user=user_obj, wo=wo)

    result = await handle_card_action(_payload(act="accept"))

    assert result["toast"]["type"] == "error"
    assert sends


@pytest.mark.asyncio
async def test_card_action_unbound_user(monkeypatch):
    db = _db_mock()
    sends = _patch_card_env(monkeypatch, db, user=None, wo=None)

    result = await handle_card_action(_payload())

    assert "未绑定" in result["toast"]["content"]
    assert sends


@pytest.mark.asyncio
async def test_patch_reliably_retries_until_confirmed(monkeypatch):
    async def _sleep(_s):
        return None

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    import app.modules.equipment.feishu.repair_card as rc

    titles = iter(["旧标题", "✅ 已接单 WO-1"])
    get_title = AsyncMock(side_effect=lambda mid: next(titles))
    monkeypatch.setattr(rc, "get_card_title", get_title)
    patched = AsyncMock()
    monkeypatch.setattr(rc, "patch_card_message", patched)
    await _patch_card_reliably(
        "om_1", {"header": {}}, expected_title_prefix="✅ 已接单 WO-1"
    )
    assert patched.await_count == 2  # 立即一次 + 复核未生效重打一次


# ── 拍照报修确认卡片回调 ─────────────────────────────────


def _photo_payload(
    eq_id,
    *,
    act="photo_repair",
    ft="泄漏",
    ph="nonce-1",
    open_id="ou_1",
):
    return {
        "operator": {"open_id": open_id, "union_id": "on_1", "user_id": ""},
        "action": {
            "value": {"act": act, "eq": eq_id, "ft": ft, "ph": ph},
            "tag": "button",
        },
        "context": {"open_message_id": "om_p", "open_chat_id": "oc_1"},
    }


def _patch_photo_env(monkeypatch, db, *, user_obj, eq, wo, set_return=True):
    monkeypatch.setattr(wof, "async_session_factory", _factory(db), raising=False)
    monkeypatch.setattr(wof, "_find_user_by_feishu", AsyncMock(return_value=user_obj))
    monkeypatch.setattr(wof.repo, "get_equipment_by_id", AsyncMock(return_value=eq))

    import app.modules.equipment.service.work_order as wo_svc

    create_mock = AsyncMock(return_value=wo)
    monkeypatch.setattr(wo_svc, "create_work_order", create_mock)

    redis = SimpleNamespace(
        set=AsyncMock(return_value=set_return), get=AsyncMock(return_value=None)
    )
    monkeypatch.setattr("app.core.redis.redis_client", redis)

    dispatch = AsyncMock()
    monkeypatch.setattr(wof, "dispatch_repair_card", dispatch)
    sends: list = []

    async def _send(**kw):
        sends.append(kw)

    monkeypatch.setattr(wof, "send_user_card", _send)
    return create_mock, dispatch, sends


@pytest.mark.asyncio
async def test_card_photo_repair_creates_order_and_dispatches(monkeypatch):
    db = _db_mock()
    user_obj = SimpleNamespace(id=USER_ID, name="秦佳豪", username="q")
    eq = _eq()
    wo = SimpleNamespace(id=uuid.uuid4(), work_order_no="WO-P1", status="待处理")

    create_mock, dispatch, sends = _patch_photo_env(
        monkeypatch, db, user_obj=user_obj, eq=eq, wo=wo
    )

    result = await handle_card_action(_photo_payload(str(eq.id)))

    assert result["code"] == 0
    create_mock.assert_awaited_once()
    payload_arg = create_mock.await_args.args[1]
    assert payload_arg.equipment_id == eq.id
    assert payload_arg.priority == "高"
    assert payload_arg.fault_description == "[拍照报修] 泄漏"
    # 与文字报修一致：建单后由维修群接单，不自动指派
    dispatch.assert_awaited_once()
    assert dispatch.await_args.kwargs["work_order_no"] == "WO-P1"
    assert any("拍照报修已受理" in s["title"] for s in sends)
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_card_photo_repair_rejects_replay(monkeypatch):
    db = _db_mock()
    user_obj = SimpleNamespace(id=USER_ID, name="秦佳豪", username="q")
    eq = _eq()
    wo = SimpleNamespace(id=uuid.uuid4(), work_order_no="WO-P2", status="待处理")

    create_mock, dispatch, _ = _patch_photo_env(
        monkeypatch, db, user_obj=user_obj, eq=eq, wo=wo, set_return=False
    )

    result = await handle_card_action(_photo_payload(str(eq.id)))

    assert result["toast"]["type"] == "error"
    create_mock.assert_not_awaited()
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_card_photo_cancel_is_ack_only(monkeypatch):
    db = _db_mock()
    create_mock, dispatch, sends = _patch_photo_env(
        monkeypatch,
        db,
        user_obj=SimpleNamespace(id=USER_ID, name="秦佳豪", username="q"),
        eq=_eq(),
        wo=SimpleNamespace(id=uuid.uuid4(), work_order_no="WO-P3", status="待处理"),
    )

    result = await handle_card_action(
        _photo_payload("ignored", act="photo_cancel")
    )

    assert result["code"] == 0
    create_mock.assert_not_awaited()
    dispatch.assert_not_awaited()
    assert sends == []


@pytest.mark.asyncio
async def test_dispatch_routes_to_workshop_chat(monkeypatch):
    """派单卡按车间维修群路由：车间已配 → 车间群；未配 → 全局默认群。"""
    import app.modules.equipment.service.work_order_feishu as wof_mod

    sent_chats: list[str] = []

    async def _fake_send(chat_id, card):
        sent_chats.append(chat_id)
        return "om_x"

    monkeypatch.setattr(
        "app.modules.equipment.feishu.repair_card.send_card_to_chat", _fake_send
    )

    class _Redis:
        async def set(self, *a, **kw):
            return True

    monkeypatch.setattr("app.core.redis.redis_client", _Redis(), raising=False)

    ws_with_chat = SimpleNamespace(code="201-1", name="201一车间",
                                   feishu_chat_id="oc_ws_201")
    db_ws = SimpleNamespace(
        execute=AsyncMock(return_value=_Result([ws_with_chat]))
    )
    monkeypatch.setattr(
        wof_mod, "async_session_factory", _factory(db_ws), raising=False
    )
    await wof_mod.dispatch_repair_card(
        work_order_no="WO-R1",
        equipment_label="离心泵A（LB-1）",
        workshop_name="201一车间",
        fault="漏了",
        priority="高",
        reporter_name="张三",
        workshop_code="201-1",
    )
    assert sent_chats == ["oc_ws_201"]

    # 未配置维修群的车间 → 回落全局默认
    ws_no_chat = SimpleNamespace(code="202-1", name="202一车间",
                                 feishu_chat_id=None)
    db_ws2 = SimpleNamespace(
        execute=AsyncMock(return_value=_Result([ws_no_chat]))
    )
    monkeypatch.setattr(
        wof_mod, "async_session_factory", _factory(db_ws2), raising=False
    )
    import app.core.config as cfg

    monkeypatch.setattr(
        cfg.get_settings(), "FEISHU_EQUIPMENT_CHAT_ID", "oc_global",
        raising=False,
    )
    await wof_mod.dispatch_repair_card(
        work_order_no="WO-R2",
        equipment_label="离心泵B（LB-2）",
        workshop_name="202一车间",
        fault="异响",
        priority="高",
        reporter_name="李四",
        workshop_code="202-1",
    )
    assert sent_chats == ["oc_ws_201", "oc_global"]


@pytest.mark.asyncio
async def test_dispatch_skips_when_no_chat_configured(monkeypatch):
    """车间与全局默认群都未配置 → 记警告并跳过派单卡片（返回 None）。"""
    import app.modules.equipment.service.work_order_feishu as wof_mod

    db_ws = SimpleNamespace(execute=AsyncMock(return_value=_Result([])))
    monkeypatch.setattr(
        "app.core.database.async_session_factory", _factory(db_ws)
    )
    import app.core.config as cfg

    monkeypatch.setattr(
        cfg.get_settings(),
        "FEISHU_EQUIPMENT_CHAT_ID",
        "",
        raising=False,
    )
    result = await wof_mod.dispatch_repair_card(
        work_order_no="WO-NC",
        equipment_label="离心泵A（LB-1）",
        workshop_name="201一车间",
        fault="漏了",
        priority="高",
        reporter_name="张三",
        workshop_code="201-1",
    )
    assert result is None

