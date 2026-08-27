"""离职提醒功能测试"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_offboarding_record():
    """模拟离职记录"""
    record = MagicMock()
    record.id = "test-record-id"
    record.name = "张三"
    record.employee_number = "10038"
    record.department = "生产部"
    record.offboarding_date = datetime(2026, 7, 29).date()
    record.offboarding_type = "合同到期"
    record.handover_status = "待交接"
    record.reminder_sent = False
    record.is_deleted = False
    record.created_at = datetime(2026, 7, 28, 10, 0, 0)
    return record


@pytest.fixture
def mock_reminder_config():
    """模拟离职提醒配置"""
    config = MagicMock()
    config.entity_code = "offboarding"
    config.is_enabled = True
    config.is_deleted = False
    config.trigger_hour = 9
    config.notify_hours = 24
    config.message_template = (
        "员工：{姓名}，工号：{工号}，部门：{部门}，"
        "离职日期：{离职日期}，离职类型：{离职类型}"
    )
    config.recipient_open_ids = ["ou_test_123"]
    config.dept_notify_enabled = False
    return config


def test_message_template_variable_replacement():
    """测试消息模板变量替换"""
    template = (
        "员工：{姓名}，工号：{工号}，部门：{部门}，"
        "离职日期：{离职日期}，离职类型：{离职类型}"
    )

    # 直接构造测试数据，不使用 fixture
    name = "张三"
    employee_number = "10038"
    department = "生产部"
    offboarding_date = datetime(2026, 7, 29).date()
    offboarding_type = "合同到期"

    content = template.replace("{姓名}", name or "未知")
    content = content.replace("{工号}", employee_number or "未知")
    content = content.replace("{部门}", department or "未知")
    content = content.replace(
        "{离职日期}", str(offboarding_date) if offboarding_date else "未知"
    )
    content = content.replace("{离职类型}", offboarding_type or "未知")

    assert "张三" in content
    assert "10038" in content
    assert "生产部" in content
    assert "2026-07-29" in content
    assert "合同到期" in content


def test_notify_hours_max_constraint():
    """测试 notify_hours 最大值约束为 72"""
    from app.modules.hr.contract_settings_schemas import ReminderConfigUpdate

    # 正常值
    config = ReminderConfigUpdate(notify_hours=24)
    assert config.notify_hours == 24

    # 最大值
    config = ReminderConfigUpdate(notify_hours=72)
    assert config.notify_hours == 72

    # 超过最大值应报错
    with pytest.raises(Exception):
        ReminderConfigUpdate(notify_hours=73)

    # 小于 1 应报错
    with pytest.raises(Exception):
        ReminderConfigUpdate(notify_hours=0)


def test_threshold_time_calculation():
    """测试阈值时间计算逻辑"""
    now = datetime(2026, 7, 29, 9, 0, 0)
    notify_hours = 24
    threshold_time = now - timedelta(hours=notify_hours)

    # 记录创建时间是 7月28日10点，小于阈值时间（7月28日9点），应该被选中
    record_created = datetime(2026, 7, 28, 8, 0, 0)
    assert record_created <= threshold_time

    # 记录创建时间是 7月28日10点，大于阈值时间，不应该被选中
    record_created_later = datetime(2026, 7, 28, 10, 0, 0)
    assert not record_created_later <= threshold_time


@pytest.mark.asyncio
async def test_ensure_default_offboarding_config():
    """测试默认离职提醒配置创建"""
    from app.modules.hr.contract_settings_service import ContractSettingsService

    session = MagicMock()
    # 模拟数据库没有配置：实现使用 result.scalars().all() 判断
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    service = ContractSettingsService(session)

    # 模拟 create_reminder_config
    with patch.object(
        service, "create_reminder_config", new_callable=AsyncMock
    ) as mock_create:
        mock_config = MagicMock()
        mock_create.return_value = mock_config

        result = await service.ensure_default_offboarding_config()

        # 验证调用了 create_reminder_config
        mock_create.assert_called_once()
        # 验证传入的参数包含 notify_hours
        call_args = mock_create.call_args[0][0]
        assert call_args["entity_code"] == "offboarding"
        assert call_args["entity_label"] == "离职管理"
        assert call_args["notify_hours"] == 24
        assert call_args["trigger_hour"] == 9
        assert not call_args["is_enabled"]
        assert result == mock_config
