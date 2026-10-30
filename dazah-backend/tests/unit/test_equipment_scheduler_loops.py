"""设备模块调度循环注册冒烟：main.py 注册的循环可通过 stop flag 干净退出。"""

import asyncio

import pytest

from app.modules.equipment import scheduler


@pytest.mark.asyncio
async def test_calibration_reminder_loop_exits_when_stopped():
    """stop flag 置位后循环立即退出，不产生扫描或异常。"""
    scheduler.stop_calibration_reminder_flag.set()
    # 5 秒内正常返回即通过：循环检测到停止标志后跳过扫描直接退出
    await asyncio.wait_for(scheduler.calibration_reminder_loop(), timeout=5)
    scheduler.stop_calibration_reminder_flag.clear()
