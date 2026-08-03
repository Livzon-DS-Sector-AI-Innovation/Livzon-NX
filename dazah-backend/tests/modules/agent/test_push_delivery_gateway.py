import uuid
from types import SimpleNamespace

import pytest

from app.modules.agent import push_delivery_service
from app.modules.agent.push_delivery_service import PushDeliveryService


class ScalarDb:
    def __init__(self, value) -> None:
        self.value = value

    async def scalar(self, statement):
        return self.value


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"id": "delivery-1", "status": "queued"}


class FakeHttpClient:
    request = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url, **kwargs):
        type(self).request = {"url": url, **kwargs}
        return FakeResponse()

    async def get(self, url, **kwargs):
        type(self).request = {"url": url, **kwargs}
        if url.endswith("/message-queued"):
            return QueuedReceiptResponse()
        return ReceiptResponse()


class ReceiptResponse(FakeResponse):
    def json(self) -> dict[str, str]:
        return {
            "status": "delivered",
            "message_id": "message-final",
            "last_error": "",
        }


class QueuedReceiptResponse(FakeResponse):
    def json(self) -> dict[str, str]:
        return {"status": "queued"}


class ReceiptResult:
    def __init__(self, delivery) -> None:
        self.delivery = delivery

    def scalars(self):
        return [self.delivery]


class ReceiptDb:
    def __init__(self, delivery) -> None:
        self.delivery = delivery

    async def execute(self, statement):
        return ReceiptResult(self.delivery)

    async def get(self, model, item_id):
        return None


def _delivery() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        recipient_user_id=uuid.uuid4(),
        idempotency_key="push:test",
    )


@pytest.mark.anyio
async def test_gateway_delivery_requires_configuration_and_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PushDeliveryService()
    monkeypatch.setattr(
        push_delivery_service,
        "get_settings",
        lambda: SimpleNamespace(HERMES_INTERNAL_URL="", HERMES_INTERNAL_TOKEN=""),
    )
    with pytest.raises(RuntimeError, match="not configured"):
        await service._enqueue_gateway_delivery(
            ScalarDb("ou-user"),
            delivery=_delivery(),
            title="Title",
            markdown="Body",
            actions=None,
        )

    monkeypatch.setattr(
        push_delivery_service,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes.internal/",
            HERMES_INTERNAL_TOKEN="token",
        ),
    )
    with pytest.raises(RuntimeError, match="identity binding"):
        await service._enqueue_gateway_delivery(
            ScalarDb(None),
            delivery=_delivery(),
            title="Title",
            markdown="Body",
            actions=None,
        )


@pytest.mark.anyio
async def test_gateway_delivery_builds_controlled_card_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery = _delivery()
    monkeypatch.setattr(
        push_delivery_service,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes.internal/",
            HERMES_INTERNAL_TOKEN="token",
        ),
    )
    monkeypatch.setattr(push_delivery_service.httpx, "AsyncClient", FakeHttpClient)

    result = await PushDeliveryService()._enqueue_gateway_delivery(
        ScalarDb("ou-user"),
        delivery=delivery,
        title="受控提醒",
        markdown="请查看业务详情",
        actions=[{"label": "打开详情", "url": "/details/1"}],
    )

    assert result == {
        "status": "sent",
        "message_id": "delivery-1",
        "gateway_status": "queued",
    }
    request = FakeHttpClient.request
    assert request["url"] == "http://hermes.internal/internal/feishu/deliveries"
    assert request["headers"] == {"Authorization": "Bearer token"}
    assert request["json"]["idempotency_key"] == "push:test"
    assert request["json"]["chat_id"] == "ou-user"
    assert request["json"]["metadata"] == {
        "trace_id": str(delivery.run_id),
        "agent_push_delivery_id": str(delivery.id),
        "receive_id_type": "open_id",
    }
    action = request["json"]["card"]["body"]["elements"][1]["actions"][0]
    assert action["text"]["content"] == "打开详情"
    assert action["value"]["resource_domain"] == "dazah_business"
    assert action["value"]["trace_id"] == str(delivery.run_id)


@pytest.mark.anyio
async def test_gateway_receipt_reconciliation_updates_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery = SimpleNamespace(
        run_id=uuid.uuid4(),
        external_message_id="message-pending",
        status="sent",
        delivered_at=None,
        last_error_message=None,
    )
    monkeypatch.setattr(
        push_delivery_service,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes.internal/",
            HERMES_INTERNAL_TOKEN="token",
        ),
    )
    monkeypatch.setattr(push_delivery_service.httpx, "AsyncClient", FakeHttpClient)

    updated = await PushDeliveryService().reconcile_gateway_receipts(
        ReceiptDb(delivery)
    )

    assert updated == 1
    assert delivery.status == "delivered"
    assert delivery.external_message_id == "message-final"
    assert delivery.delivered_at is not None
    assert delivery.last_error_message == ""
    assert FakeHttpClient.request["url"].endswith(
        "/internal/feishu/deliveries/message-pending"
    )


@pytest.mark.anyio
async def test_gateway_receipt_reconciliation_ignores_nonterminal_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery = SimpleNamespace(
        run_id=uuid.uuid4(),
        external_message_id="message-queued",
        status="sent",
    )
    monkeypatch.setattr(
        push_delivery_service,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes.internal/",
            HERMES_INTERNAL_TOKEN="token",
        ),
    )
    monkeypatch.setattr(push_delivery_service.httpx, "AsyncClient", FakeHttpClient)

    updated = await PushDeliveryService().reconcile_gateway_receipts(
        ReceiptDb(delivery)
    )

    assert updated == 0
    assert delivery.status == "sent"
