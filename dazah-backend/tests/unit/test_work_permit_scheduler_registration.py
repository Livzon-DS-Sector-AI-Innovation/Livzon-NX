"""作业票复检催办与证件到期提醒的调度注册守护测试。

main.py lifespan 将两个生成器注册进统一调度引擎；任务重名会在启动时
抛 ValueError 导致应用无法启动，这里守护名称唯一且可注册。
"""

import pytest

from app.modules.safety.scheduled import (
    SafetyCertificateExpiryReminderGenerator,
    SafetyWorkPermitGasDueGenerator,
)
from app.platform.scheduler.registry import SchedulerRegistry


def test_work_permit_generators_register_with_unique_names() -> None:
    gas_gen = SafetyWorkPermitGasDueGenerator()
    cert_gen = SafetyCertificateExpiryReminderGenerator()

    assert gas_gen.name == "safety.work_permit_gas_due"
    assert cert_gen.name == "safety.cert_expiry_daily"

    registry = SchedulerRegistry()
    registry.register_generator(gas_gen)
    registry.register_generator(cert_gen)

    with pytest.raises(ValueError):
        registry.register_generator(SafetyWorkPermitGasDueGenerator())
    with pytest.raises(ValueError):
        registry.register_generator(SafetyCertificateExpiryReminderGenerator())
