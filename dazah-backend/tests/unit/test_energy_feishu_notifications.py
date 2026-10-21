import json

import httpx
import pytest

from app.platform.integrations.feishu.im import send_feishu_message


@pytest.mark.asyncio
async def test_energy_bot_delivery_passes_stable_uuid_and_explicit_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"code": 0, "data": {"message_id": "message-test"}}
        )

    actual_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)

    def client(**kwargs: object) -> httpx.AsyncClient:
        return actual_client(transport=transport)

    monkeypatch.setattr("app.platform.integrations.feishu.im.httpx.AsyncClient", client)
    result = await send_feishu_message(
        tenant_access_token="fake-test-token",
        receive_id="employee-test",
        receive_id_type="user_id",
        msg_type="interactive",
        content='{"header":{}}',
        uuid="stable-delivery-test",
    )
    assert result.ok and result.message_id == "message-test"
    assert json.loads(requests[0].content)["uuid"] == "stable-delivery-test"
    assert requests[0].url.params["receive_id_type"] == "user_id"
    assert requests[0].headers["Authorization"] == "Bearer fake-test-token"
