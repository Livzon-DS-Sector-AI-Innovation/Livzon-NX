import asyncio
from unittest.mock import AsyncMock

from app.core import maintenance
from app.modules.hr.feishu import card_handler

pytest_plugins = ("tests.maintenance_fixtures",)

EVENT = {
    "event": {
        "action": {
            "value": {
                "module": "position_transfer_approval",
                "record_id": "fixture",
                "node": "hr",
                "action": "approve",
            }
        }
    }
}


async def test_maintenance_refuses_card_approval_before_claiming_or_mutating(
    isolated_redis, monkeypatch
):
    handler = AsyncMock()
    monkeypatch.setattr(card_handler, "_handle_position_transfer_approval", handler)
    await maintenance.set_release_phase("draining")
    response = await card_handler.handle_card_action(EVENT)
    assert "本次审批未受理" in response["toast"]["content"]
    handler.assert_not_awaited()
    assert await maintenance.active_work() == {}


async def test_card_approval_worker_is_counted_after_event_acknowledgement(
    isolated_redis, monkeypatch
):
    gate = asyncio.Event()
    monkeypatch.setattr("app.core.redis.cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr("app.core.redis.cache_set", AsyncMock())

    async def approve(*args):
        await gate.wait()

    monkeypatch.setattr(card_handler, "_do_position_transfer_approval", approve)
    response = await card_handler.handle_card_action(EVENT)
    assert response["toast"]["type"] == "success"
    await maintenance.set_release_phase("draining")
    assert await maintenance.active_work() == {"job": 1}
    gate.set()
    for _ in range(100):
        if not await maintenance.active_work():
            break
        await asyncio.sleep(0.01)
    assert await maintenance.active_work() == {}


async def test_failed_admission_removes_unexecuted_approval_claim(
    isolated_redis, monkeypatch
):
    monkeypatch.setattr("app.core.redis.cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr("app.core.redis.cache_set", AsyncMock())
    remove = AsyncMock()
    monkeypatch.setattr("app.core.redis.cache_delete", remove)
    monkeypatch.setattr(
        card_handler,
        "submit_job",
        AsyncMock(side_effect=maintenance.MaintenanceActiveError()),
    )
    response = await card_handler.handle_card_action(EVENT)
    assert response["toast"]["type"] == "warning"
    remove.assert_awaited_once_with("hr:position_transfer:fixture:hr:approve")
    assert await maintenance.active_work() == {}
