import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.modules.agent.memory_policy import (
    AgentMemoryPolicyService,
    anonymous_scope_ref,
    memory_command_help_text,
    parse_memory_command,
    policy_limitation_sources,
)


def test_anonymous_scope_ref_is_stable_and_does_not_leak_identity() -> None:
    value = anonymous_scope_ref("tenant-a", "user-a")

    assert value == anonymous_scope_ref("tenant-a", "user-a")
    assert len(value) == 16
    assert "tenant" not in value
    assert "user" not in value


def test_memory_help_lists_complete_command_set() -> None:
    response = memory_command_help_text()

    for command in (
        "/memory status",
        "/memory auto",
        "/memory explicit",
        "/memory pause",
        "/memory resume",
        "/memory forget <关键词>",
        "/memory clear",
        "/memory clear confirm",
        "/memory help",
    ):
        assert f"`{command}`" in response


@pytest.mark.parametrize(
    ("message", "action", "argument"),
    [
        ("/memory status", "status", None),
        ("开启自动记忆", "auto", None),
        ("只在我明确要求时记忆", "explicit", None),
        ("暂停记忆", "pause", None),
        ("恢复记忆", "resume", None),
        ("消除我的记忆", "clear", None),
        ("确认清空记忆", "clear_confirm", None),
        ("请忘记关于表格输出", "forget", "表格输出"),
    ],
)
def test_memory_commands_are_deterministic(
    message: str, action: str, argument: str | None
) -> None:
    command = parse_memory_command(message)

    assert command is not None
    assert command.action == action
    assert command.argument == argument


def test_ambiguous_text_is_not_a_memory_command() -> None:
    assert parse_memory_command("你觉得自动记忆功能怎么样？") is None
    assert parse_memory_command("请总结今天的工作") is None


def test_policy_limitation_sources_identify_the_strictest_upstream_level() -> None:
    assert policy_limitation_sources(
        global_mode="auto", tenant_mode="explicit_only", user_mode="auto"
    ) == ["租户策略"]
    assert policy_limitation_sources(
        global_mode="disabled", tenant_mode="disabled", user_mode="auto"
    ) == ["全局策略", "租户策略"]
    assert policy_limitation_sources(
        global_mode="auto", tenant_mode="auto", user_mode="paused"
    ) == []


@pytest.mark.anyio
async def test_effective_policy_uses_the_strictest_level(monkeypatch) -> None:
    settings = Settings(AGENT_USER_MEMORY_MODE="auto")
    service = AgentMemoryPolicyService(settings)
    tenant = SimpleNamespace(mode="explicit_only", policy_version=3)
    preference = SimpleNamespace(
        mode="paused",
        preference_version=4,
        notice_sent_version=1,
        last_cleared_at=None,
    )
    monkeypatch.setattr(service, "_tenant_row", AsyncMock(return_value=tenant))
    monkeypatch.setattr(service, "_preference", AsyncMock(return_value=preference))
    user = SimpleNamespace(id=uuid.uuid4(), tenant_key="tenant-a")

    policy = await service.resolve(SimpleNamespace(), user=user)

    assert policy.effective_mode == "disabled"
    assert policy.policy_version >= 3_000_000


@pytest.mark.anyio
async def test_group_memory_command_is_rejected_before_data_access() -> None:
    service = AgentMemoryPolicyService(Settings())
    user = SimpleNamespace(id=uuid.uuid4(), tenant_key="tenant-a")

    result = await service.handle_command(
        SimpleNamespace(),
        user=user,
        message="/memory",
        private_channel=False,
    )

    assert result is not None and "群聊不读取" in result


@pytest.mark.anyio
async def test_tenant_policy_cannot_be_relaxed(monkeypatch) -> None:
    service = AgentMemoryPolicyService(Settings())
    row = SimpleNamespace(mode="disabled", policy_version=2)
    monkeypatch.setattr(service, "_tenant_row", AsyncMock(return_value=row))

    with pytest.raises(HTTPException) as error:
        await service.update_tenant_policy(
            SimpleNamespace(),
            user=SimpleNamespace(id=uuid.uuid4(), tenant_key="tenant-a"),
            mode="auto",
        )

    assert error.value.status_code == 409


@pytest.mark.anyio
async def test_privacy_notice_is_marked_only_by_explicit_delivery_ack(
    monkeypatch,
) -> None:
    service = AgentMemoryPolicyService(Settings(AGENT_USER_MEMORY_NOTICE_VERSION=2))
    preference = SimpleNamespace(
        mode="auto",
        preference_version=4,
        notice_sent_version=0,
        last_cleared_at=None,
        updated_by=None,
    )
    monkeypatch.setattr(service, "_tenant_row", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_preference", AsyncMock(return_value=preference))
    db = SimpleNamespace(flush=AsyncMock())
    user = SimpleNamespace(id=uuid.uuid4(), tenant_key="tenant-a")

    policy = await service.resolve(db, user=user)

    assert policy.notice_required is True
    assert preference.notice_sent_version == 0
    assert await service.mark_notice_sent(db, user=user) is True
    assert preference.notice_sent_version == 2
    assert await service.mark_notice_sent(db, user=user) is False
