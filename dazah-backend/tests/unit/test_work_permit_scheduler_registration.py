"""作业票/证件/承诺推送/烟酒镜像调度注册守护测试。

main.py lifespan 将这些生成器注册进统一调度引擎；任务重名会在启动时
抛 ValueError 导致应用无法启动，这里守护名称唯一且可注册。
"""

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
