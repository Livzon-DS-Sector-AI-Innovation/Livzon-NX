"""作业票/证件/承诺推送/烟酒镜像调度注册守护测试。

main.py lifespan 将这些生成器注册进统一调度引擎；任务重名会在启动时
抛 ValueError 导致应用无法启动，这里守护名称唯一且可注册。
"""

import asyncio

import pytest

from app.modules.administration.scheduled import (
    AdministrationFeishuReadSyncGenerator,
)
from app.modules.safety.scheduled import (
    SafetyCertificateExpiryReminderGenerator,
    SafetyCommitmentPushGenerator,
    SafetyWorkPermitGasDueGenerator,
)
from app.platform.scheduler.registry import SchedulerRegistry


def test_multi_batch_generators_register_with_unique_names() -> None:
    gas_gen = SafetyWorkPermitGasDueGenerator()
    cert_gen = SafetyCertificateExpiryReminderGenerator()
    push_gen = SafetyCommitmentPushGenerator()
    admin_gen = AdministrationFeishuReadSyncGenerator()

    assert gas_gen.name == "safety.work_permit_gas_due"
    assert cert_gen.name == "safety.cert_expiry_daily"
    assert push_gen.name == "safety.commitment_daily_push"
    assert admin_gen.name == "administration.feishu_read_sync"

    registry = SchedulerRegistry()
    for gen in (gas_gen, cert_gen, push_gen, admin_gen):
        registry.register_generator(gen)

    for gen in (gas_gen, cert_gen, push_gen, admin_gen):
        with pytest.raises(ValueError):
            registry.register_generator(gen)


async def test_sign_relay_config_and_poller_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """签名中继：默认配置不启用；配置网关后 poller 才启动。"""
    from app.core.config import get_settings
    from app.modules.safety.sign_relay_poller import (
        start_sign_relay_poller_task,
    )

    # 默认无网关地址 → 不启动
    settings = get_settings()
    assert settings.SIGN_RELAY_GATEWAY_BASE == ""
    assert settings.SIGN_RELAY_GATEWAY_ENABLED is False
    task = start_sign_relay_poller_task()
    assert task is None

    # 启用后创建后台协程（async 事件循环内 asyncio.create_task 可用）
    monkeypatch.setattr(
        "app.modules.safety.sign_relay_poller.get_settings",
        lambda: type("S", (), {
            "SIGN_RELAY_GATEWAY_BASE": "http://relay.test",
            "SIGN_RELAY_KEY": "k",
            "SIGN_RELAY_POLL_SECONDS": 10,
            "SIGN_RELAY_GATEWAY_ENABLED": True,
        })(),
    )
    task2 = start_sign_relay_poller_task()
    assert task2 is not None
    task2.cancel()
    try:
        await task2
    except asyncio.CancelledError:
        pass
