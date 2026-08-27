from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.modules.hr import push_settings_service
from app.modules.hr.push_settings_service import PushSettingsService


def _result(items: list[object]) -> SimpleNamespace:
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: items),
        scalar_one_or_none=lambda: items[0] if items else None,
    )


@pytest.mark.asyncio
async def test_send_notice_for_candidate_reports_email_and_feishu_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    templates = [
        SimpleNamespace(
            channel="email",
            title_template="面试 - {name}",
            body_template="时间：{interview_time}",
        ),
        SimpleNamespace(
            channel="feishu",
            title_template="飞书 - {name}",
            body_template="岗位：{position}",
        ),
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=_result(templates)))
    service = PushSettingsService(session)
    service._resolve_recipients = AsyncMock(return_value=["open-1", "open-2"])
    service._log_push = AsyncMock()
    monkeypatch.setattr(
        push_settings_service,
        "_send_email_with_retry",
        AsyncMock(),
    )
    monkeypatch.setattr(
        push_settings_service,
        "_send_feishu_with_retry",
        AsyncMock(side_effect=[None, RuntimeError("飞书暂不可用")]),
    )

    result = await service.send_notice_for_candidate(
        candidate_id="candidate-1",
        candidate_name="张三",
        candidate_email="candidate@example.test",
        scene_code="interview_notice",
        variables={
            "name": "张三",
            "interview_time": "2026-08-26 10:00",
            "position": "质量员",
            "department": "质量部",
        },
        triggered_by="tester",
    )

    assert result["email_sent"] is True
    assert result["feishu_sent"] is True
    assert result["feishu_recipients"] == ["open-1"]
    assert len(result["feishu_errors"]) == 1
    assert service._log_push.await_count == 3


@pytest.mark.asyncio
async def test_push_template_and_recipient_queries_and_safe_rendering() -> None:
    template = SimpleNamespace(id=uuid4(), title_template="{name}-{missing}")
    recipient = SimpleNamespace(recipient_open_ids=["u1", "u2"])
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[_result([template]), _result([recipient])]),
        flush=AsyncMock(),
    )
    service = PushSettingsService(session)
    assert await service.list_push_templates() == [template]
    assert set(await service._resolve_recipients("interview_notice")) == {"u1", "u2"}
    assert (
        push_settings_service._render_template("{name}/{missing}", {"name": "张三"})
        == "张三/"
    )
    assert push_settings_service._render_template("{", {}) == "{"


@pytest.mark.asyncio
async def test_email_and_feishu_retry_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "HR_MAIL_SMTP_HOST": "smtp.example.test",
        "HR_MAIL_SMTP_PORT": "465",
        "HR_MAIL_SMTP_USER": "sender@example.test",
        "HR_MAIL_SMTP_PASS": "encrypted-pass",
        "HR_MAIL_FROM": "sender@example.test",
    }

    async def setting(_module: str, key: str, default: str | None = None) -> str | None:
        return values.get(key, default)

    monkeypatch.setattr(push_settings_service, "get_module_setting", setting)
    monkeypatch.setattr(
        "app.core.llm.decrypt_api_key",
        lambda _value: "decrypted-pass",
    )
    smtp = MagicMock()
    monkeypatch.setattr(
        push_settings_service.smtplib,
        "SMTP_SSL",
        lambda *args, **kwargs: smtp,
    )
    await push_settings_service._send_email_with_retry(
        "to@example.test", "主题", "正文"
    )
    smtp.login.assert_called_once_with("sender@example.test", "decrypted-pass")
    smtp.sendmail.assert_called_once()

    values["HR_MAIL_SMTP_HOST"] = None
    with pytest.raises(RuntimeError, match="SMTP"):
        await push_settings_service._send_email_with_retry(
            "to@example.test", "主题", "正文"
        )

    values["HR_MAIL_SMTP_HOST"] = "smtp.example.test"
    im = SimpleNamespace(
        send_text_message=AsyncMock(side_effect=[RuntimeError("temporary"), None])
    )
    monkeypatch.setattr(
        "app.modules.hr.feishu.im.FeishuIM",
        lambda: im,
    )
    monkeypatch.setattr(push_settings_service.asyncio, "sleep", AsyncMock())
    await push_settings_service._send_feishu_with_retry("open-1", "消息")
    assert im.send_text_message.await_count == 2


@pytest.mark.asyncio
async def test_test_push_handles_email_and_feishu_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_id = uuid4()
    email_template = SimpleNamespace(
        channel="email", title_template="标题", body_template="正文"
    )
    feishu_template = SimpleNamespace(
        channel="feishu", title_template="标题", body_template="正文"
    )
    service = PushSettingsService(
        SimpleNamespace(
            execute=AsyncMock(
                side_effect=[_result([email_template]), _result([feishu_template])]
            )
        )
    )
    monkeypatch.setattr(
        push_settings_service,
        "_send_email_with_retry",
        AsyncMock(side_effect=RuntimeError("mail")),
    )
    monkeypatch.setattr(
        push_settings_service,
        "_send_feishu_with_retry",
        AsyncMock(side_effect=RuntimeError("feishu")),
    )
    email_result = await service.test_push(template_id, "to@example.test", {})
    feishu_result = await service.test_push(template_id, "open-1", {})
    assert email_result["success"] is False
    assert feishu_result["success"] is False
