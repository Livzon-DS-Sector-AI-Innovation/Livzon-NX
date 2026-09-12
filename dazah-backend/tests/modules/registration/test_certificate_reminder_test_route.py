"""POST /reminder-settings/test 路由级测试（AsyncClient 真实调用路由）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

ROUTE = "/api/v1/registration/certificate-management/reminder-settings/test"


@pytest.mark.asyncio
async def test_test_certificate_reminder_settings_returns_result_payload(
    client: AsyncClient,
) -> None:
    result_payload = {
        "sent": True,
        "recipient_name": "张起智",
        "detail": "测试消息已发送至 张起智",
    }
    with patch(
        "app.modules.registration.api.certificates.CertificateWorkbookService.send_test_notification",
        new=AsyncMock(return_value=result_payload),
    ) as mocked_test:
        response = await client.post(
            ROUTE,
            json={
                "recipient_open_id": "ou_zqz",
                "header_template": "开头 {count}",
                "footer_template": "结尾",
            },
        )

    assert response.status_code == 200
    mocked_test.assert_awaited_once()
    kwargs = mocked_test.await_args.kwargs
    assert kwargs["recipient_open_id"] == "ou_zqz"
    assert kwargs["header_template"] == "开头 {count}"
    assert kwargs["footer_template"] == "结尾"
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["sent"] is True
    assert body["data"]["recipient_name"] == "张起智"


@pytest.mark.asyncio
async def test_test_certificate_reminder_settings_rejects_missing_recipient(
    client: AsyncClient,
) -> None:
    """失败路径：缺少 recipient_open_id 时请求校验拒绝（422）。"""
    response = await client.post(ROUTE, json={"header_template": "开头"})

    assert response.status_code == 422
