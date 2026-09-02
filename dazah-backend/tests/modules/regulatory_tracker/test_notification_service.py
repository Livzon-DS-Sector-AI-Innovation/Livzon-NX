from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AppException
from app.modules.regulatory_tracker.services.notification_service import (
    RegulatoryTrackerNotificationService,
    _build_notification_content,
    _is_qa_department,
    _normalize_department,
    _normalize_department_text,
    _resolve_display_summary,
    _truncate_summary,
)


@pytest.mark.anyio
async def test_list_notification_recipient_options_only_returns_qa_contacts(
    db_session,
) -> None:
    service = RegulatoryTrackerNotificationService(db_session)

    with patch(
        "app.modules.quality.service.department_contacts.get_department_contact_list_from_feishu",
        new=AsyncMock(
            return_value={
                "items": [
                    {
                        "open_id": "ou_qa_1",
                        "name": "武巧玲",
                        "department": "QA",
                        "enterprise_email": "wuqiaoling@example.com",
                    },
                    {
                        "open_id": "ou_qa_2",
                        "name": "李四",
                        "department": "质量保证部",
                        "enterprise_email": "lisi@example.com",
                    },
                    {
                        "open_id": "ou_non_qa",
                        "name": "王五",
                        "department": "注册管理",
                        "enterprise_email": "wangwu@example.com",
                    },
                ]
            }
        ),
    ):
        result = await service.list_notification_recipient_options()

    assert [item.open_id for item in result] == ["ou_qa_1", "ou_qa_2"]
    assert [item.name for item in result] == ["武巧玲", "李四"]


# ── 纯函数 ──────────────────────────────────────────────


def test_normalize_department() -> None:
    assert _normalize_department("  质量管理部  部 ") == "质量管理部 部"
    assert _normalize_department(None) == ""
    assert _normalize_department("") == ""


def test_normalize_department_text_and_qa_check() -> None:
    assert _normalize_department_text(" 质量 保证 部 ") == "质量保证部"
    assert _is_qa_department("质量保证部")
    assert _is_qa_department("QA 部")
    assert _is_qa_department("生产部") is False
    assert _is_qa_department("") is False


def test_truncate_summary_and_display() -> None:
    assert _truncate_summary(None) == "暂无内容总结"
    assert _truncate_summary("  短摘要  ") == "短摘要"
    out = _truncate_summary("长" * 120)
    assert out.endswith("…")
    assert (
        _resolve_display_summary(
            SimpleNamespace(ai_summary="AI 摘要", summary_text="备用")
        )
        == "AI 摘要"
    )
    assert (
        _resolve_display_summary(
            SimpleNamespace(ai_summary=None, summary_text="文本摘要")
        )
        == "文本摘要"
    )


def test_build_notification_content_overflow_and_missing_fields() -> None:
    def _doc(i: int) -> Any:
        return SimpleNamespace(
            title=f"法规{i}",
            source_site_name="NMPA",
            publish_date=date(2024, 1, i),
            ai_summary=None,
            summary_text=f"摘要{i}",
            source_url=f"https://x/{i}",
            original_url=None,
        )

    docs = [_doc(i) for i in range(1, 13)]
    content = _build_notification_content(docs)
    assert "法规1" in content and "NMPA" in content
    assert "其余还有 **2** 条" in content
    assert "日期：2024-01-01" in content
    small = _build_notification_content(docs[:3])
    assert "其余还有" not in small
    missing = _build_notification_content(
        [
            SimpleNamespace(
                title="t",
                source_site_name=None,
                publish_date=None,
                ai_summary=None,
                summary_text=None,
                source_url=None,
                original_url=None,
            )
        ]
    )
    assert "—" in missing


# ── Service 方法分支（不触库，全 mock）──────────────────


def _service(session: Any = None) -> RegulatoryTrackerNotificationService:
    return RegulatoryTrackerNotificationService(session or AsyncMock())


@pytest.mark.anyio
async def test_list_options_handles_feishu_failure(monkeypatch) -> None:
    async def _boom(session: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("feishu down")

    monkeypatch.setattr(
        "app.modules.quality.service.department_contacts"
        ".get_department_contact_list_from_feishu",
        _boom,
    )
    assert await _service()._list_reminder_recipient_options() == []


@pytest.mark.anyio
async def test_get_recipient_by_open_id(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(
        service,
        "_list_reminder_recipient_options",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    open_id="ou-1", name="张三", department="QA部",
                    enterprise_email=None,
                ),
                SimpleNamespace(
                    open_id="ou-2", name="李四", department="QA部",
                    enterprise_email=None,
                ),
            ]
        ),
    )
    assert (await service._get_recipient_by_open_id("ou-2")).name == "李四"
    assert await service._get_recipient_by_open_id("ou-9") is None


@pytest.mark.anyio
async def test_count_pending_documents(monkeypatch) -> None:
    session = AsyncMock()
    session.execute.return_value = MagicMock(
        scalars=lambda: MagicMock(
            all=lambda: [
                SimpleNamespace(id=1, content_hash="a"),
                SimpleNamespace(id=2, content_hash="b"),
                SimpleNamespace(id=3, content_hash="c"),
            ]
        )
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.notification_record_exists",
        AsyncMock(side_effect=[True, False, False]),
    )
    service = _service(session)
    assert (
        await service._count_pending_documents(
            recipient_open_id="ou-1", recent_days=7
        )
        == 2
    )
    assert (
        await service._count_pending_documents(
            recipient_open_id=None, recent_days=7
        )
        == 0
    )


@pytest.mark.anyio
async def test_get_notification_settings_default_and_existing(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=None),
    )
    setting = await service.get_notification_settings()
    assert setting.is_enabled is False and setting.pending_count == 0

    existing = SimpleNamespace(
        is_enabled=True,
        recent_days=3,
        recipient_open_id="ou-1",
        recipient_name="张三",
        recipient_department="QA部",
        schedule_time="10:00",
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(service, "_count_pending_documents", AsyncMock(return_value=5))
    setting2 = await service.get_notification_settings()
    assert setting2.is_enabled is True and setting2.pending_count == 5


@pytest.mark.anyio
async def test_update_notification_settings_validations(monkeypatch) -> None:
    service = _service()
    save_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.save_notification_setting",
        save_mock,
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service, "_get_recipient_by_open_id", AsyncMock(return_value=None)
    )
    with pytest.raises(AppException, match="必须选择接收人"):
        await service.update_notification_settings(
            SimpleNamespace(is_enabled=True, recipient_open_id="", recent_days=7)
        )
    with pytest.raises(AppException, match="不在 QA 联系人范围"):
        await service.update_notification_settings(
            SimpleNamespace(is_enabled=True, recipient_open_id="ou-x", recent_days=7)
        )
    # 禁用时清空接收人
    monkeypatch.setattr(
        service,
        "get_notification_settings",
        AsyncMock(return_value=SimpleNamespace(is_enabled=False, pending_count=0)),
    )
    out = await service.update_notification_settings(
        SimpleNamespace(is_enabled=False, recipient_open_id="ou-x", recent_days=7)
    )
    save_mock.assert_awaited()
    assert out.is_enabled is False
    # 合法接收人启用成功
    monkeypatch.setattr(
        service,
        "_get_recipient_by_open_id",
        AsyncMock(
            return_value=SimpleNamespace(
                name="张三", department="QA部", open_id="ou-1"
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "get_notification_settings",
        AsyncMock(return_value=SimpleNamespace(is_enabled=True, pending_count=1)),
    )
    out2 = await service.update_notification_settings(
        SimpleNamespace(is_enabled=True, recipient_open_id="ou-1", recent_days=7)
    )
    assert out2.is_enabled is True


def _doc(id_: str, content_hash: str = "h1") -> Any:
    return SimpleNamespace(
        id=id_,
        title="法规",
        ai_summary=None,
        summary_text="摘要",
        source_site_name="NMPA",
        publish_date=None,
        source_url=None,
        original_url=None,
        content_hash=content_hash,
    )


def _enabled_setting() -> Any:
    return SimpleNamespace(
        is_enabled=True,
        recipient_open_id="ou-1",
        recipient_name="张三",
        recent_days=7,
        schedule_time="10:00",
    )


@pytest.mark.anyio
async def test_send_update_notifications_skip_paths(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=None),
    )
    assert await service.send_update_notifications(document_ids=["1"]) == {
        "sent": 0,
        "skipped": 1,
        "failed": 0,
    }
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(
            return_value=SimpleNamespace(
                is_enabled=False, recipient_open_id="", recipient_name=None
            )
        ),
    )
    assert await service.send_update_notifications(document_ids=["1"]) == {
        "sent": 0,
        "skipped": 1,
        "failed": 0,
    }
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
    )
    monkeypatch.setattr(
        service, "_get_recipient_by_open_id", AsyncMock(return_value=None)
    )
    assert await service.send_update_notifications(document_ids=["1"]) == {
        "sent": 0,
        "skipped": 1,
        "failed": 0,
    }
    # 空 ID 列表需先有合法接收人才能走到该分支
    monkeypatch.setattr(
        service,
        "_get_recipient_by_open_id",
        AsyncMock(
            return_value=SimpleNamespace(
                open_id="ou-1", name="张三", department="QA部",
                enterprise_email=None,
            )
        ),
    )
    assert await service.send_update_notifications(document_ids=["", ""]) == {
        "sent": 0,
        "skipped": 0,
        "failed": 0,
    }


@pytest.mark.anyio
async def test_send_update_notifications_send_and_records(monkeypatch) -> None:
    session = AsyncMock()
    service = _service(session)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
    )
    monkeypatch.setattr(
        service,
        "_get_recipient_by_open_id",
        AsyncMock(
            return_value=SimpleNamespace(
                open_id="ou-1", name="张三", department="QA部",
                enterprise_email=None,
            )
        ),
    )
    docs = [
        _doc("11111111-1111-1111-1111-111111111111"),
        _doc("22222222-2222-2222-2222-222222222222", content_hash="h2"),
    ]
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.list_documents_by_ids",
        AsyncMock(return_value=docs),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.notification_record_exists",
        AsyncMock(side_effect=[True, False]),
    )
    create_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.create_notification_records",
        create_mock,
    )
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.notification_service.send_user_card",
        send_mock,
    )
    result = await service.send_update_notifications(
        document_ids=[
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        ]
    )
    assert result == {"sent": 1, "skipped": 0, "failed": 0}
    send_mock.assert_awaited_once()
    assert create_mock.await_args is not None
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_send_update_notifications_send_failure(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
    )
    monkeypatch.setattr(
        service,
        "_get_recipient_by_open_id",
        AsyncMock(
            return_value=SimpleNamespace(
                open_id="ou-1", name="张三", department="QA部",
                enterprise_email="z@liv.com",
            )
        ),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.list_documents_by_ids",
        AsyncMock(return_value=[_doc("11111111-1111-1111-1111-111111111111")]),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.notification_record_exists",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.notification_service.send_user_card",
        AsyncMock(return_value=False),
    )
    result = await service.send_update_notifications(
        document_ids=["11111111-1111-1111-1111-111111111111"]
    )
    assert result == {"sent": 0, "skipped": 0, "failed": 1}


@pytest.mark.anyio
async def test_send_update_notifications_all_already_notified(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
    )
    monkeypatch.setattr(
        service,
        "_get_recipient_by_open_id",
        AsyncMock(
            return_value=SimpleNamespace(
                open_id="ou-1", name="张三", department="QA部",
                enterprise_email=None,
            )
        ),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.list_documents_by_ids",
        AsyncMock(return_value=[_doc("11111111-1111-1111-1111-111111111111")]),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.notification_record_exists",
        AsyncMock(return_value=True),
    )
    result = await service.send_update_notifications(
        document_ids=["11111111-1111-1111-1111-111111111111"]
    )
    assert result == {"sent": 0, "skipped": 1, "failed": 0}
