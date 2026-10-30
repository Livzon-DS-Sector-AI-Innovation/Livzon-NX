"""拍照报修测试：视觉识别、确认卡片、限流与巡检图片路由转交。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.equipment.service.inspection_feishu as insp
import app.modules.equipment.service.repair_photo as rp
from app.core.llm import LLMError
from app.modules.equipment.service.repair_photo import process_repair_photo

from .test_work_order_feishu_bot import _eq, _factory, _Result, _ws

# 1x1 像素合法 JPEG（无需真实照片内容）
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a"
    "0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434"
    "341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f000001050101010101"
    "0100000000000000000102030405060708090a0bffc400b51000020103030204030505040400"
    "0000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433"
    "62728209a164535a2b3c2435363783b445c464738494a5b5d6e0f4f5f6f7f8f9fafbffc4001f"
    "0100030101010101010101010000000000000102030405060708090a0bffc400b51100020102"
    "040403040705040400010277000102031104052131061241516107137223114328191a108234"
    "2b1c12552d1f04361633728209a2445535a2b3c26437384b445c4d6e0f5f6f7f8f9faffda0008"
    "0101000000003f00fbfe8a28a2800a28a2800a28a2803ffd9"
)


def _fake_redis(
    *, incr_return: int = 1, set_return: object = True, get_return: object = None
) -> Mock:
    return Mock(
        incr=AsyncMock(return_value=incr_return),
        expire=AsyncMock(),
        set=AsyncMock(return_value=set_return),
        get=AsyncMock(return_value=get_return),
    )


def _intent(**kw):
    base = {
        "workshop": "201一车间",
        "equipment_name": "离心泵A",
        "equipment_no": "LB-001",
        "fault": "泄漏",
    }
    base.update(kw)
    return base


def _vision_mock(return_value):
    return AsyncMock(return_value=return_value)


@pytest.fixture
def _photo_env(monkeypatch, tmp_path):
    """公共桩：下载、卡片、会话工厂与临时上传目录。"""
    sent: list[dict] = []

    async def _send_user_card(**kw):
        sent.append(kw)
        return True

    monkeypatch.setattr(rp, "send_user_card", _send_user_card)
    monkeypatch.setattr(rp.settings, "UPLOAD_DIR", str(tmp_path), raising=False)
    download = AsyncMock(return_value=(_TINY_JPEG, "image/jpeg"))
    return sent, download


@pytest.mark.asyncio
async def test_photo_unique_match_sends_confirm_card(
    monkeypatch, _photo_env
):
    sent, download = _photo_env
    import app.modules.equipment.service.inspection_feishu as insp_mod

    monkeypatch.setattr(insp_mod, "_download_image", download)
    redis = _fake_redis()
    monkeypatch.setattr("app.core.redis.redis_client", redis)
    eq = _eq(no="LB-001")
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Result([_ws()]), _Result([eq])])
    )
    monkeypatch.setattr(rp, "async_session_factory", _factory(db))
    monkeypatch.setattr(
        type(rp.llm_client), "chat_vision_json", _vision_mock(_intent())
    )

    await process_repair_photo(
        user_id="u1",
        open_id="ou_1",
        message_id="om_1",
        image_key="img_1",
        chat_id="oc_1",
        chat_type="group",
    )

    assert len(sent) == 1
    card = sent[0]
    assert card["title"] == "📷 拍照报修确认"
    assert "离心泵A" in card["content"]
    actions = card["elements"][0]["actions"]
    confirm = actions[0]["value"]
    assert confirm["act"] == "photo_repair"
    assert confirm["eq"] == str(eq.id)
    assert confirm["ft"] == "泄漏"
    assert confirm["ph"]  # 照片 nonce 已登记


@pytest.mark.asyncio
async def test_photo_multiple_candidates_sends_selector(monkeypatch, _photo_env):
    sent, _download = _photo_env
    import app.modules.equipment.service.inspection_feishu as insp_mod

    monkeypatch.setattr(insp_mod, "_download_image", AsyncMock(
        return_value=(_TINY_JPEG, "image/jpeg")
    ))
    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())
    eq1, eq2 = _eq(name="离心泵1", no="LB-001"), _eq(name="离心泵2", no="LB-002")
    # 车间 → （编号为空跳过编号查询）→ 名称命中两台
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[_Result([_ws()]), _Result([eq1, eq2])]
        )
    )
    monkeypatch.setattr(rp, "async_session_factory", _factory(db))
    monkeypatch.setattr(
        type(rp.llm_client),
        "chat_vision_json",
        _vision_mock(_intent(equipment_no="", equipment_name="离心泵")),
    )

    await process_repair_photo(
        user_id="u1",
        open_id="ou_1",
        message_id="om_1",
        image_key="img_1",
        chat_id="oc_1",
        chat_type="group",
    )

    assert sent[0]["title"] == "📷 拍照报修：请选择设备"
    values = [a["value"] for a in sent[0]["elements"][0]["actions"]]
    assert len(values) == 2
    assert {v["eq"] for v in values} == {str(eq1.id), str(eq2.id)}


@pytest.mark.asyncio
async def test_photo_vision_failure_falls_back_to_text_guide(
    monkeypatch, _photo_env
):
    sent, _download = _photo_env
    import app.modules.equipment.service.inspection_feishu as insp_mod

    monkeypatch.setattr(insp_mod, "_download_image", AsyncMock(
        return_value=(_TINY_JPEG, "image/jpeg")
    ))
    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())
    monkeypatch.setattr(rp, "async_session_factory", _factory(SimpleNamespace(
        execute=AsyncMock(return_value=_Result([_ws()]))
    )))
    monkeypatch.setattr(
        type(rp.llm_client),
        "chat_vision_json",
        AsyncMock(side_effect=LLMError("no config", "raw")),
    )

    await process_repair_photo(
        user_id="u1",
        open_id="ou_1",
        message_id="om_1",
        image_key="img_1",
        chat_id="oc_1",
        chat_type="p2p",
    )

    assert sent[0]["title"] == "📷 拍照报修未识别成功"
    assert "报修" in sent[0]["content"]


@pytest.mark.asyncio
async def test_photo_rate_limited_rejects(monkeypatch, _photo_env):
    sent, download = _photo_env
    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis(incr_return=6))
    # 限流时应直接回复且不触发下载
    await process_repair_photo(
        user_id="u1",
        open_id="ou_1",
        message_id="om_1",
        image_key="img_1",
        chat_id="oc_1",
        chat_type="group",
    )
    assert sent[0]["title"] == "⏳ 稍后再试"
    download.assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_oversize_image_rejected(monkeypatch, _photo_env):
    sent, _download = _photo_env
    import app.modules.equipment.service.inspection_feishu as insp_mod

    monkeypatch.setattr(insp_mod, "_download_image", AsyncMock(
        return_value=(b"x" * (10 * 1024 * 1024 + 1), "image/jpeg")
    ))
    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())

    await process_repair_photo(
        user_id="u1",
        open_id="ou_1",
        message_id="om_1",
        image_key="img_1",
        chat_id="oc_1",
        chat_type="group",
    )
    assert sent[0]["title"] == "📷 图片过大"


@pytest.mark.asyncio
async def test_inspection_without_task_hands_off_to_repair_photo(monkeypatch):
    """无巡检会话且无执行中任务的图片 → 转交拍照报修（路由回归）。"""
    handed: list[dict] = []

    async def _fake_handoff(**kw):
        handed.append(kw)

    db = SimpleNamespace(execute=AsyncMock(return_value=_Result([])))
    monkeypatch.setattr(insp, "async_session_factory", _factory(db))
    monkeypatch.setattr(
        insp, "_find_user_by_user_id", AsyncMock(return_value=SimpleNamespace(id="u1"))
    )
    monkeypatch.setattr(insp, "get_session", AsyncMock(return_value=None))
    monkeypatch.setattr(insp, "_find_active_task", AsyncMock(return_value=None))
    monkeypatch.setattr(insp, "_handoff_to_repair_photo", _fake_handoff)

    await insp.process_feishu_image(
        user_id="u1",
        open_id="ou_1",
        message_id="om_1",
        image_key="img_1",
        chat_id="oc_1",
        chat_type="group",
    )
    assert handed and handed[0]["image_key"] == "img_1"


@pytest.mark.asyncio
async def test_inspection_unbound_user_hands_off_to_repair_photo(monkeypatch):
    """未绑定平台账号的图片同样转交拍照报修（回落系统管理员建单）。"""
    handed: list[dict] = []

    async def _fake_handoff(**kw):
        handed.append(kw)

    monkeypatch.setattr(insp, "async_session_factory", _factory(SimpleNamespace()))
    monkeypatch.setattr(insp, "_find_user_by_user_id", AsyncMock(return_value=None))
    monkeypatch.setattr(insp, "_handoff_to_repair_photo", _fake_handoff)

    await insp.process_feishu_image(
        user_id="ghost",
        open_id="ou_2",
        message_id="om_2",
        image_key="img_2",
        chat_id="oc_1",
        chat_type="group",
    )
    assert handed and handed[0]["open_id"] == "ou_2"


@pytest.mark.asyncio
async def test_inspection_empty_user_id_hands_off_to_repair_photo(monkeypatch):
    """user_id 缺失（企业未开通 user_id 权限）的图片也必须转交拍照报修。

    回归：此前该分支直接丢弃图片，拍照报修在此类企业永远无法触发。
    """
    handed: list[dict] = []

    async def _fake_handoff(**kw):
        handed.append(kw)

    monkeypatch.setattr(insp, "_handoff_to_repair_photo", _fake_handoff)

    await insp.process_feishu_image(
        user_id="",
        open_id="ou_3",
        message_id="om_3",
        image_key="img_3",
        chat_id="oc_1",
        chat_type="p2p",
    )
    assert handed and handed[0]["image_key"] == "img_3"


@pytest.mark.asyncio
async def test_card_trigger_event_allows_photo_actions(monkeypatch):
    """事件通道的卡片动作过滤器必须放行 photo_repair/photo_cancel。

    回归：过滤器曾硬编码只认 accept/complete，确认卡片的回调被静默丢弃，
    拍照报修在事件通道下永远无法建单。
    """
    import app.modules.equipment.feishu.ws_client as ws

    handled: list[dict] = []

    async def _fake_handle(payload):
        handled.append(payload)
        return {"code": 0}

    monkeypatch.setattr(
        "app.modules.equipment.service.work_order_feishu.handle_card_action",
        _fake_handle,
    )
    for act in ("photo_repair", "photo_cancel", "accept", "complete"):
        event = {
            "action": {"tag": "button", "value": {"act": act}},
            "operator": {"open_id": "ou_1"},
        }
        await ws._handle_card_trigger_event(event)
    assert len(handled) == 4

    await ws._handle_card_trigger_event(
        {"action": {"tag": "button", "value": {"act": "other"}}}
    )
    assert len(handled) == 4  # 未知动作仍被过滤


# ── 群消息 @机器人 过滤与「照片 + @报修」配对 ──────────────


def _msg_event(msg_type="text", chat_type="p2p", text="", image_key="", mentions=None):
    content = (
        {"text": text} if msg_type == "text" else {"image_key": image_key}
    )
    return {
        "message": {
            "message_type": msg_type,
            "message_id": "om_g1",
            "chat_id": "oc_group",
            "chat_type": chat_type,
            "content": __import__("json").dumps(content),
            "mentions": mentions or [],
        },
        "sender": {"sender_id": {"open_id": "ou_1", "user_id": "", "union_id": ""}},
    }


@pytest.mark.asyncio
async def test_group_text_without_mention_is_ignored(monkeypatch):
    import app.modules.equipment.feishu.ws_client as ws

    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())
    text_cmd = AsyncMock()
    monkeypatch.setattr(ws, "_handle_text_command", text_cmd)

    await ws._handle_message_event(_msg_event(chat_type="group", text="今天下午开会"))

    text_cmd.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_image_without_mention_is_buffered(monkeypatch):
    import app.modules.equipment.feishu.ws_client as ws

    redis = _fake_redis()
    monkeypatch.setattr("app.core.redis.redis_client", redis)
    process_image = AsyncMock()
    monkeypatch.setattr(
        "app.modules.equipment.service.inspection_feishu.process_feishu_image",
        process_image,
    )

    await ws._handle_message_event(
        _msg_event(msg_type="image", chat_type="group", image_key="img_g1")
    )

    process_image.assert_not_awaited()  # 未 @机器人：不进识别流程
    redis.set.assert_awaited_once()  # 但已进缓冲
    buffered_key = redis.set.await_args.args[0]
    assert "oc_group" in buffered_key and "ou_1" in buffered_key


@pytest.mark.asyncio
async def test_group_mention_repair_pairs_buffered_photo(monkeypatch):
    """群内「照片缓冲 + @机器人 报修」→ 拍照报修并携带文字故障提示。"""
    import json as json_mod

    import app.modules.equipment.feishu.ws_client as ws

    photo = {"message_id": "om_g1", "image_key": "img_g1"}
    monkeypatch.setattr(
        ws,
        "_take_buffered_group_photo",
        AsyncMock(return_value=photo),
    )
    process_photo = AsyncMock()
    monkeypatch.setattr(
        "app.modules.equipment.service.repair_photo.process_repair_photo",
        process_photo,
    )
    text_repair = AsyncMock()
    monkeypatch.setattr(
        "app.modules.equipment.service.work_order_feishu.create_repair_by_text",
        text_repair,
    )
    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())

    await ws._handle_text_command(
        user_id="",
        open_id="ou_1",
        union_id="",
        chat_id="oc_group",
        chat_type="group",
        content=json_mod.dumps({"text": "@_user_1 报修 密封漏了"}),
    )

    process_photo.assert_awaited_once()
    kwargs = process_photo.await_args.kwargs
    assert kwargs["image_key"] == "img_g1"
    assert kwargs["fault_hint"] == "密封漏了"
    text_repair.assert_not_awaited()  # 配对成功则不走文字报修


@pytest.mark.asyncio
async def test_group_mention_repair_without_photo_falls_back_to_text(monkeypatch):
    import json as json_mod

    import app.modules.equipment.feishu.ws_client as ws

    monkeypatch.setattr(
        ws, "_take_buffered_group_photo", AsyncMock(return_value=None)
    )
    text_repair = AsyncMock()
    monkeypatch.setattr(
        "app.modules.equipment.service.work_order_feishu.create_repair_by_text",
        text_repair,
    )
    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())

    await ws._handle_text_command(
        user_id="",
        open_id="ou_1",
        union_id="",
        chat_id="oc_group",
        chat_type="group",
        content=json_mod.dumps({"text": "@_user_1 报修 201一车间 离心泵A 漏了"}),
    )

    text_repair.assert_awaited_once()


@pytest.mark.asyncio
async def test_photo_fault_hint_fills_missing_fault(monkeypatch, _photo_env):
    """视觉未识别出故障现象时，群配对文字的描述作为兜底。"""
    sent, _dl = _photo_env
    import app.modules.equipment.service.inspection_feishu as insp_mod

    monkeypatch.setattr(insp_mod, "_download_image", AsyncMock(
        return_value=(_TINY_JPEG, "image/jpeg")
    ))
    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())
    eq = _eq(no="LB-001")
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Result([_ws()]), _Result([eq])])
    )
    monkeypatch.setattr(rp, "async_session_factory", _factory(db))
    monkeypatch.setattr(
        type(rp.llm_client),
        "chat_vision_json",
        _vision_mock(_intent(fault="")),
    )

    await process_repair_photo(
        user_id="u1",
        open_id="ou_1",
        message_id="om_1",
        image_key="img_1",
        chat_id="oc_group",
        chat_type="group",
        fault_hint="密封漏了",
    )

    actions = sent[0]["elements"][0]["actions"]
    assert actions[0]["value"]["ft"] == "密封漏了"


@pytest.mark.asyncio
async def test_group_repair_prefix_text_passes_without_mention(monkeypatch):
    """方案 Y：群里不带 @ 的「报修 …」文字直接放行（扫码粘贴一步到位）。"""
    import app.modules.equipment.feishu.ws_client as ws

    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())
    text_cmd = AsyncMock()
    monkeypatch.setattr(ws, "_handle_text_command", text_cmd)

    await ws._handle_message_event(
        _msg_event(chat_type="group", text="报修 201一车间 离心泵A LB-001")
    )

    text_cmd.assert_awaited_once()


@pytest.mark.asyncio
async def test_group_normal_chat_stays_silent_even_with_selection(monkeypatch):
    """普通聊天（非指令、无@、无选择会话）在群里被忽略。"""
    import app.modules.equipment.feishu.ws_client as ws

    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())
    text_cmd = AsyncMock()
    monkeypatch.setattr(ws, "_handle_text_command", text_cmd)

    await ws._handle_message_event(
        _msg_event(chat_type="group", text="今天下午三点开会")
    )

    text_cmd.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_photo_repair_alias_triggers_pairing(monkeypatch):
    """「拍照报修」别名同样触发照片配对，且归一化后描述提取正确。"""
    import json as json_mod

    import app.modules.equipment.feishu.ws_client as ws

    monkeypatch.setattr(
        ws,
        "_take_buffered_group_photo",
        AsyncMock(return_value={"message_id": "om_g2", "image_key": "img_g2"}),
    )
    process_photo = AsyncMock()
    monkeypatch.setattr(
        "app.modules.equipment.service.repair_photo.process_repair_photo",
        process_photo,
    )
    text_repair = AsyncMock()
    monkeypatch.setattr(
        "app.modules.equipment.service.work_order_feishu.create_repair_by_text",
        text_repair,
    )
    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())

    await ws._handle_text_command(
        user_id="",
        open_id="ou_1",
        union_id="",
        chat_id="oc_group",
        chat_type="group",
        content=json_mod.dumps({"text": "拍照报修 密封漏了"}),
    )

    process_photo.assert_awaited_once()
    assert process_photo.await_args.kwargs["fault_hint"] == "密封漏了"
    assert process_photo.await_args.kwargs["image_key"] == "img_g2"
    text_repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_photo_repair_alias_passes_gate(monkeypatch):
    """群门槛放行「拍照报修 …」前缀（不带 @ 也进路由）。"""
    import app.modules.equipment.feishu.ws_client as ws

    monkeypatch.setattr("app.core.redis.redis_client", _fake_redis())
    text_cmd = AsyncMock()
    monkeypatch.setattr(ws, "_handle_text_command", text_cmd)

    await ws._handle_message_event(
        _msg_event(chat_type="group", text="拍照报修 轴承异响")
    )

    text_cmd.assert_awaited_once()
