"""维修派单卡片构建与飞书消息接口的单测（外呼全部 mock）。"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.modules.equipment.feishu import repair_card
from app.modules.equipment.feishu.repair_card import (
    build_accepted_card,
    build_completed_card,
    build_dispatch_card,
    get_card_title,
    patch_card_message,
    send_card_to_chat,
)


@pytest.fixture(autouse=True)
def _isolate_token_cache():
    """重置模块级 token 缓存：本文件用例断言"缓存为空→发请求"的初始态，
    也避免本文件写入的长效缓存泄漏到同进程的其他测试。"""
    repair_card._token_cache["token"] = ""
    repair_card._token_cache["expires_at"] = 0.0
    yield
    repair_card._token_cache["token"] = ""
    repair_card._token_cache["expires_at"] = 0.0


def _dispatch_card(priority: str = "高"):
    return build_dispatch_card(
        work_order_no="WO-20261026-0001",
        equipment_label="离心泵A（LB-DEMO-8）",
        workshop_name="201一车间",
        reporter_name="秦佳豪",
        fault="密封漏了",
        priority=priority,
    )


def test_dispatch_card_styles_by_priority():
    urgent = _dispatch_card("紧急")
    assert urgent["header"]["template"] == "red"
    assert "紧急" in urgent["header"]["title"]["content"]

    normal = _dispatch_card("高")
    assert normal["header"]["template"] == "orange"
    # 按钮值带动作与工单号
    accept = normal["elements"][-2]["actions"][0]
    assert accept["value"] == {"act": "accept", "oid": "WO-20261026-0001"}

    low = _dispatch_card("低")
    assert low["header"]["template"] == "grey"


def test_accepted_card_switches_to_complete_action():
    card = build_accepted_card(
        work_order_no="WO-1",
        equipment_label="离心泵A",
        assignee_name="秦佳豪",
        accepted_at=datetime(2026, 10, 26, 7, 24, tzinfo=UTC),
    )
    assert card["header"]["template"] == "green"
    assert "已接单" in card["header"]["title"]["content"]
    action = card["elements"][-1]["actions"][0]
    assert action["value"] == {"act": "complete", "oid": "WO-1"}


def test_completed_card_has_no_actions():
    card = build_completed_card(
        work_order_no="WO-1", equipment_label="离心泵A", assignee_name="秦佳豪"
    )
    assert card["header"]["template"] == "turquoise"
    assert "已完成，待验收" in card["header"]["title"]["content"]
    assert all(el.get("tag") != "action" for el in card["elements"])


@pytest.mark.asyncio
async def test_tenant_token_cached_within_window():
    with patch.object(repair_card.httpx, "AsyncClient") as client_cls:
        resp = Mock()
        resp.json.return_value = {"tenant_access_token": "t-1", "expire": 1800}
        inner = Mock(post=AsyncMock(return_value=resp))
        client_cls.return_value.__aenter__ = AsyncMock(return_value=inner)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        token1 = await repair_card._tenant_token()
    assert token1 == "t-1"
    # 缓存命中：不再发请求
    repair_card._token_cache["expires_at"] = 9999999999
    assert await repair_card._tenant_token() == "t-1"


@pytest.mark.asyncio
async def test_send_card_to_chat_returns_message_id():
    with patch.object(repair_card, "_tenant_token", AsyncMock(return_value="t")):
        with patch.object(repair_card.httpx, "AsyncClient") as client_cls:
            resp = Mock(status_code=200)
            resp.json.return_value = {"code": 0, "data": {"message_id": "om_1"}}
            client_cls.return_value.__aenter__ = AsyncMock(
                return_value=Mock(post=AsyncMock(return_value=resp))
            )
            client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mid = await send_card_to_chat("oc_1", _dispatch_card())
    assert mid == "om_1"


@pytest.mark.asyncio
async def test_send_card_to_chat_raises_on_error_code():
    with patch.object(repair_card, "_tenant_token", AsyncMock(return_value="t")):
        with patch.object(repair_card.httpx, "AsyncClient") as client_cls:
            resp = Mock(status_code=200)
            resp.json.return_value = {"code": 99991672, "msg": "no scope"}
            client_cls.return_value.__aenter__ = AsyncMock(
                return_value=Mock(post=AsyncMock(return_value=resp))
            )
            client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(RuntimeError, match="99991672"):
                await send_card_to_chat("oc_1", _dispatch_card())


def _client_stub(payload: dict, status_code: int = 200):
    resp = Mock(status_code=status_code)
    resp.json.return_value = payload
    client = Mock(patch=AsyncMock(return_value=resp), get=AsyncMock(return_value=resp))
    cls = Mock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return cls


@pytest.mark.asyncio
async def test_patch_card_message_success_and_failure():
    card = build_completed_card(
        work_order_no="WO-1", equipment_label="x", assignee_name="y"
    )
    with patch.object(repair_card, "_tenant_token", AsyncMock(return_value="t")):
        with patch.object(repair_card.httpx, "AsyncClient", _client_stub({"code": 0})):
            assert await patch_card_message("om_1", card) is True
        with patch.object(
            repair_card.httpx, "AsyncClient", _client_stub({"code": 230002, "msg": "x"})
        ):
            assert await patch_card_message("om_1", card) is False


@pytest.mark.asyncio
async def test_get_card_title_parses_normalized_content():
    content = '{"title": "🛠 已完成，待验收 WO-1", "elements": []}'
    payload = {"code": 0, "data": {"items": [{"body": {"content": content}}]}}
    with patch.object(repair_card, "_tenant_token", AsyncMock(return_value="t")):
        with patch.object(repair_card.httpx, "AsyncClient", _client_stub(payload)):
            assert await get_card_title("om_1") == "🛠 已完成，待验收 WO-1"

    with patch.object(repair_card, "_tenant_token", AsyncMock(return_value="t")):
        with patch.object(
            repair_card.httpx, "AsyncClient", _client_stub({"code": 230001})
        ):
            assert await get_card_title("om_1") == ""
