"""登录凭证隔离的安全回归测试。"""

import ast
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.platform.integrations.feishu import auth, message, notification


def test_shared_credentials_are_read_only_by_login_and_directory():
    root = Path(__file__).resolve().parents[2] / "app"
    allowed = {
        "core/config.py",
        "platform/identity/api.py",
        "platform/identity/service.py",
        "platform/integrations/feishu/oauth.py",
        "platform/integrations/feishu/contact.py",
    }
    violations = []
    for path in root.rglob("*.py"):
        if path.relative_to(root).as_posix() in allowed:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            value = (
                node.attr
                if isinstance(node, ast.Attribute)
                else node.value
                if isinstance(node, ast.Constant)
                else None
            )
            if value in ("FEISHU_APP_ID", "FEISHU_APP_SECRET"):
                violations.append(str(path.relative_to(root)))
    assert not violations


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "app_id,app_secret", [(None, None), ("business", None), (None, "secret"), ("", "")]
)
async def test_incomplete_credentials_never_open_network(
    monkeypatch, app_id, app_secret
):
    network = Mock(side_effect=AssertionError("network must not be used"))
    monkeypatch.setattr(auth.httpx, "AsyncClient", network)
    with pytest.raises(auth.FeishuCredentialsRequiredError) as error:
        await auth.FeishuAuth.get_tenant_access_token(app_id, app_secret)
    assert error.value.status_code == 503
    network.assert_not_called()


@pytest.mark.asyncio
async def test_unconfigured_notifications_do_not_send(monkeypatch):
    network = Mock(side_effect=AssertionError("network must not be used"))
    monkeypatch.setattr(auth.httpx, "AsyncClient", network)
    assert not await notification.send_user_card("ou-user", "title", "text")
    assert (
        await notification.send_user_card_with_message_id("ou-user", "title", "text")
        is None
    )
    assert not await notification.update_card("message", {})
    assert not await message.send_group_card("chat", "title", "text")
    network.assert_not_called()
