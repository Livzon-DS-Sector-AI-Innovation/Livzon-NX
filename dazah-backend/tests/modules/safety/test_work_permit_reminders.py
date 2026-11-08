"""作业票复检催办与证件到期提醒测试：生成器护栏/到期计算/推送去重。

APP_ENV 护栏按隐患到期提醒的测试模式 stub 掉 get_settings；
飞书发送 mock 掉，断言调用参数与去重记录落库。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import (
    SafetyFeishuAppSettings,
    SpecialWorkCertificate,
    SpecialWorkCertificateReminderLog,
    WorkPermit,
    WorkPermitGasAnalysis,
)
from app.modules.safety.scheduled import (
    SafetyCertificateExpiryReminderGenerator,
    SafetyWorkPermitGasDueGenerator,
)
from app.modules.safety.service import work_permit_reminders as reminders
from app.platform.identity.models import User

_WP_MARK = "GAS测试"
_CERT_MARK2 = "CEXP测试"


class NotifyRecorder:
    def __init__(self) -> None:
        self.gas_calls: list[dict] = []
        self.card_calls: list[tuple] = []

    async def notify_gas_due(self, db, permit, *, due_at, overdue) -> None:
        self.gas_calls.append(
            {"permit_no": permit.permit_no, "due_at": due_at, "overdue": overdue}
        )

    async def send_user_card(self, open_id, title, content, elements=None,
                             id_type="open_id") -> bool:
        self.card_calls.append(("user", open_id, title))
        return True

    async def send_group_card(self, chat_id, title, content, elements=None,
                              header_template="orange") -> str | None:
        self.card_calls.append(("group", chat_id, title))
        return "om_xxx"


async def _cleanup(db: AsyncSession) -> None:
    permit_ids = list(
        await db.scalars(
            select(WorkPermit.id).where(WorkPermit.remark.like(f"{_WP_MARK}%"))
        )
    )
    if permit_ids:
        await db.execute(
            delete(WorkPermitGasAnalysis).where(
                WorkPermitGasAnalysis.permit_id.in_(permit_ids)
            )
        )
        await db.execute(
            delete(WorkPermit).where(WorkPermit.id.in_(permit_ids))
        )
    cert_ids = list(
        await db.scalars(
            select(SpecialWorkCertificate.id).where(
                SpecialWorkCertificate.remark.like(f"{_CERT_MARK2}%")
            )
        )
    )
    if cert_ids:
        await db.execute(
            delete(SpecialWorkCertificateReminderLog).where(
                SpecialWorkCertificateReminderLog.certificate_id.in_(cert_ids)
            )
        )
        await db.execute(
            delete(SpecialWorkCertificate).where(
                SpecialWorkCertificate.id.in_(cert_ids)
            )
        )
    await db.execute(
        delete(SafetyFeishuAppSettings).where(
            SafetyFeishuAppSettings.app_id.like(f"{_WP_MARK}%")
        )
    )
    await db.commit()


async def _enabled_settings(db: AsyncSession) -> SafetyFeishuAppSettings:
    row = SafetyFeishuAppSettings(
        app_id=f"{_WP_MARK}app{uuid4().hex[:6]}",
        app_secret="secret",
        is_enabled=True,
        permit_notify_enabled=True,
        cert_expiry_notify_enabled=True,
        cert_expiry_notify_milestones=[30, 15, 7],
        cert_expiry_notify_chat_ids=["oc_test"],
        cert_expiry_notify_user_ids=[],
    )
    db.add(row)
    await db.flush()
    return row


async def test_gas_due_generator_env_guard(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cleanup(db_session)
    generator = SafetyWorkPermitGasDueGenerator()

    class _FakeSettings:
        APP_ENV = "development"

    # 生成器内 from app.core.config import get_settings → stub 源头
    import app.core.config as config_module

    monkeypatch.setattr(config_module, "get_settings", lambda: _FakeSettings())
    assert await generator.find_due(db_session) == []
    await _cleanup(db_session)


async def test_gas_due_generator_disabled_settings(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cleanup(db_session)

    class _FakeSettings:
        APP_ENV = "production"

    import app.core.config as config_module

    monkeypatch.setattr(
        config_module, "get_settings", lambda: _FakeSettings()
    )
    generator = SafetyWorkPermitGasDueGenerator()

    # 无设置行 → 关闭
    assert await generator.find_due(db_session) == []

    # 存在设置但 permit_notify_enabled=False → 关闭
    row = SafetyFeishuAppSettings(
        app_id=f"{_WP_MARK}off{uuid4().hex[:6]}",
        app_secret="s",
        is_enabled=True,
        permit_notify_enabled=False,
    )
    db_session.add(row)
    await db_session.flush()
    assert await generator.find_due(db_session) == []
    await _cleanup(db_session)


async def test_send_gas_due_reminders_overdue(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    await _enabled_settings(db_session)
    recorder = NotifyRecorder()
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_notify.notify_gas_due",
        recorder.notify_gas_due,
    )
    user = User(
        id=uuid4(), name=f"{_WP_MARK}监护{uuid4().hex[:6]}",
        role="user", status="active",
    )
    db_session.add(user)
    await db_session.flush()
    permit = WorkPermit(
        permit_no=f"DH-{uuid4().hex[:8]}",
        permit_type="hot_work",
        permit_level="grade2",
        status="active",
        actual_start_time=datetime.now(UTC) - timedelta(hours=2),
        persons=[
            {"role": "guardian", "name": "监护甲", "user_id": str(user.id)},
        ],
        remark=f"{_WP_MARK}{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(permit)
    await db_session.flush()
    db_session.add(
        WorkPermitGasAnalysis(
            permit_id=permit.id,
            phase="on_duty",
            sampled_at=datetime.now(UTC) - timedelta(minutes=120),
            analyst_name="分析员",
        )
    )
    await db_session.flush()

    sent, errors = await reminders.send_gas_due_reminders(db_session)
    assert sent == 1, errors
    assert recorder.gas_calls
    assert recorder.gas_calls[0]["overdue"] is True
    assert recorder.gas_calls[0]["permit_no"] == permit.permit_no

    # 同一到期窗口去重（Redis 去重）：再次运行不再推送。
    # 本地环境可能连不上 Redis（容器主机名），缓存静默降级时跳过该断言。
    from app.core.redis import cache_get, cache_set

    await cache_set("probe:wp_dedupe", "1", ex=10)
    redis_available = await cache_get("probe:wp_dedupe") == "1"
    if redis_available:
        sent_again, _ = await reminders.send_gas_due_reminders(db_session)
        assert sent_again == 0
    await _cleanup(db_session)


async def test_certificate_expiry_notifications_dedupe(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    await _enabled_settings(db_session)
    recorder = NotifyRecorder()
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_group_card",
        recorder.send_group_card,
    )
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_user_card",
        recorder.send_user_card,
    )

    cert = SpecialWorkCertificate(
        person_name=f"{_CERT_MARK2}赵六{uuid4().hex[:4]}",
        certificate_category="electrician",
        certificate_no=f"EXP{uuid4().hex[:8]}",
        expiry_date=date.today() + timedelta(days=7),
        status="expiring",
        remark=f"{_CERT_MARK2}{uuid4().hex[:8]}",
    )
    db_session.add(cert)
    await db_session.flush()

    sent, errors = await reminders.send_certificate_expiry_notifications(db_session)
    assert sent == 1, errors
    assert recorder.card_calls, "到期证件应推送飞书提醒"
    assert any(kind == "group" for kind, _, _ in recorder.card_calls)

    # 同一证件同一节点只推一次（DB 日志去重，不依赖 Redis）
    recorder.card_calls.clear()
    sent_again, _ = await reminders.send_certificate_expiry_notifications(db_session)
    assert sent_again == 0
    assert recorder.card_calls == []

    # 生成器护栏：非生产环境跳过
    class _FakeSettings:
        APP_ENV = "development"

    import app.core.config as config_module

    monkeypatch.setattr(config_module, "get_settings", lambda: _FakeSettings())
    generator = SafetyCertificateExpiryReminderGenerator()
    assert await generator.find_due(db_session) == []
    await _cleanup(db_session)
