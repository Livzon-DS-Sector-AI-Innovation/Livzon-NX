import base64
import json
from types import SimpleNamespace

import pytest

from app.platform.identity import feishu_card_ws


@pytest.mark.anyio
async def test_event_dispatches_private_message_and_tracks_counter(monkeypatch) -> None:
    received: list[dict] = []
    original_count = feishu_card_ws._frame_count["im_message"]

    async def fake_message_handler(payload: dict) -> None:
        received.append(payload)

    monkeypatch.setattr(
        feishu_card_ws,
        "_handle_message_receive_event",
        fake_message_handler,
    )

    payload = {"header": {"event_type": "im.message.receive_v1"}, "event": {}}
    result = await feishu_card_ws._dispatch_event(payload)

    assert result == {"code": 200}
    assert received == [payload]
    assert feishu_card_ws._frame_count["im_message"] == original_count + 1


@pytest.mark.anyio
async def test_card_callback_wraps_raw_card_in_v2_response(monkeypatch) -> None:
    async def fake_card_handler(payload: dict) -> dict:
        return {
            "toast": {"type": "success", "content": "已执行"},
            "card": {
                "config": {"wide_screen_mode": True},
                "elements": [{"tag": "markdown", "content": "已执行"}],
            },
        }

    monkeypatch.setattr(
        feishu_card_ws,
        "_handle_card_action_event",
        fake_card_handler,
    )

    result = await feishu_card_ws._dispatch_event(
        {"header": {"event_type": "card.action.trigger"}, "event": {}}
    )
    decoded = json.loads(base64.b64decode(result["data"]).decode("utf-8"))

    assert result["code"] == 200
    assert decoded == {
        "toast": {"type": "success", "content": "已执行"},
        "card": {
            "type": "raw",
            "data": {
                "config": {"wide_screen_mode": True},
                "elements": [{"tag": "markdown", "content": "已执行"}],
            },
        },
    }


@pytest.mark.anyio
async def test_raw_ws_acknowledges_card_before_background_processing(
    monkeypatch,
) -> None:
    from lark_oapi.ws.const import HEADER_TYPE
    from lark_oapi.ws.enum import FrameType, MessageType
    from lark_oapi.ws.pb.pbbp2_pb2 import Frame

    scheduled: list[dict] = []

    class FakeWs:
        def __init__(self) -> None:
            self.sent: list[bytes] = []

        async def send(self, value: bytes) -> None:
            self.sent.append(value)

    monkeypatch.setattr(
        feishu_card_ws,
        "_schedule_event_after_ack",
        scheduled.append,
    )
    payload = {
        "header": {"event_type": "card.action.trigger"},
        "event": {"action": {"value": {"action_id": "action-1"}}},
    }
    frame = Frame()
    frame.method = FrameType.DATA.value
    frame.SeqID = 1
    frame.LogID = 1
    frame.service = 1
    frame.payload = json.dumps(payload).encode()
    header = frame.headers.add()
    header.key = HEADER_TYPE
    header.value = MessageType.EVENT.value
    ws = FakeWs()

    await feishu_card_ws._handle_binary_message(ws, frame.SerializeToString())

    assert scheduled == [payload]
    assert len(ws.sent) == 1
    response_frame = Frame()
    response_frame.ParseFromString(ws.sent[0])
    response = json.loads(response_frame.payload)
    callback = json.loads(base64.b64decode(response["data"]))
    assert response["code"] == 200
    assert callback["toast"]["content"] == "操作已受理，正在处理"


@pytest.mark.anyio
async def test_event_ws_status_exposes_new_and_legacy_switches(monkeypatch) -> None:
    monkeypatch.setattr(feishu_card_ws, "_delegated_to_global_ws", False)
    monkeypatch.setattr(
        feishu_card_ws,
        "get_settings",
        lambda: SimpleNamespace(
            LIVZON_FEISHU_EVENT_WS_ENABLED=True,
            LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=False,
        ),
    )

    status = await feishu_card_ws.get_livzon_card_ws_status()

    assert status["enabled"] is True
    assert status["event_ws_enabled"] is True
    assert status["legacy_card_callback_ws_enabled"] is False
    assert status["event_types"] == ["im.message.receive_v1", "card.action.trigger"]


@pytest.mark.anyio
async def test_start_delegates_when_identity_uses_global_app(monkeypatch) -> None:
    monkeypatch.setattr(
        feishu_card_ws,
        "get_settings",
        lambda: SimpleNamespace(
            FEISHU_WS_ENABLED=True,
            FEISHU_APP_ID="shared-app",
            LIVZON_FEISHU_EVENT_WS_ENABLED=True,
            LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=True,
        ),
    )

    async def fake_active_app_id() -> str:
        return "shared-app"

    monkeypatch.setattr(feishu_card_ws, "_active_app_id", fake_active_app_id)
    monkeypatch.setattr(feishu_card_ws, "_delegated_to_global_ws", False)

    await feishu_card_ws.start_livzon_card_ws()

    assert feishu_card_ws._delegated_to_global_ws is True
    status = await feishu_card_ws.get_livzon_card_ws_status()
    assert status["running"] is True
