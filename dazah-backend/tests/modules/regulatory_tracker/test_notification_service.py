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
    _normalize_department,
    _resolve_display_summary,
    _truncate_summary,
)


@pytest.mark.anyio
async def test_list_notification_recipient_options_only_returns_qa_contacts(
    db_session,
) -> None:
    service = RegulatoryTrackerNotificationService(db_session)

    with patch(
        "app.modules.quality.public_api.get_qa_reminder_recipients",
        new=AsyncMock(
            return_value=[
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
            ]
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
        "app.modules.quality.public_api.get_qa_reminder_recipients",
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
        header_template="开头",
        footer_template="结尾",
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(service, "_count_pending_documents", AsyncMock(return_value=5))
    setting2 = await service.get_notification_settings()
    assert setting2.is_enabled is True and setting2.pending_count == 5
    assert setting2.header_template == "开头"
    assert setting2.footer_template == "结尾"


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
            SimpleNamespace(
                is_enabled=True,
                recipient_open_id="",
                recent_days=7,
                header_template=None,
                footer_template=None,
            )
        )
    with pytest.raises(AppException, match="不在 QA 联系人范围"):
        await service.update_notification_settings(
            SimpleNamespace(
                is_enabled=True,
                recipient_open_id="ou-x",
                recent_days=7,
                header_template=None,
                footer_template=None,
            )
        )
    # 禁用时清空接收人
    monkeypatch.setattr(
        service,
        "get_notification_settings",
        AsyncMock(return_value=SimpleNamespace(is_enabled=False, pending_count=0)),
    )
    out = await service.update_notification_settings(
        SimpleNamespace(
            is_enabled=False,
            recipient_open_id="ou-x",
            recent_days=7,
            header_template=None,
            footer_template=None,
        )
    )
    save_mock.assert_awaited()
    assert out.is_enabled is False
    # 合法接收人启用成功，模板字段透传保存（空白归一为 None）
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
        SimpleNamespace(
            is_enabled=True,
            recipient_open_id="ou-1",
            recent_days=7,
            header_template="  开头 {count}  ",
            footer_template="   ",
        )
    )
    assert out2.is_enabled is True
    assert save_mock.await_args.kwargs["header_template"] == "开头 {count}"
    assert save_mock.await_args.kwargs["footer_template"] is None


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
        header_template=None,
        footer_template=None,
    )


def _patch_send_chain(
    monkeypatch, *, credentials: tuple[str, str], resolved: Any
) -> AsyncMock:
    """统一 mock 凭证读取、接收人跨应用解析与飞书发送。"""
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.notification_service"
        ".get_module_feishu_app_credentials",
        AsyncMock(return_value=credentials),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.notification_service"
        ".resolve_feishu_notification_recipient",
        AsyncMock(return_value=resolved),
    )
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.notification_service.send_user_card",
        send_mock,
    )
    return send_mock


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
    # 空 ID 列表（启用配置下直接拦截，不触凭证与解析）
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
    )
    assert await service.send_update_notifications(document_ids=["", ""]) == {
        "sent": 0,
        "skipped": 0,
        "failed": 0,
    }


@pytest.mark.anyio
async def test_send_update_notifications_missing_credentials_fails(
    monkeypatch,
) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.list_documents_by_ids",
        AsyncMock(return_value=[_doc("11111111-1111-1111-1111-111111111111")]),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.notification_record_exists",
        AsyncMock(return_value=False),
    )
    _patch_send_chain(monkeypatch, credentials=("", ""), resolved=None)
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.notification_service.send_user_card",
        send_mock,
    )
    result = await service.send_update_notifications(
        document_ids=["11111111-1111-1111-1111-111111111111"]
    )
    assert result == {"sent": 0, "skipped": 0, "failed": 1}
    send_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_send_update_notifications_unresolvable_recipient_fails(
    monkeypatch,
) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.list_documents_by_ids",
        AsyncMock(return_value=[_doc("11111111-1111-1111-1111-111111111111")]),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.notification_record_exists",
        AsyncMock(return_value=False),
    )
    _patch_send_chain(
        monkeypatch,
        credentials=("cli_app", "secret"),
        resolved=None,
    )
    result = await service.send_update_notifications(
        document_ids=["11111111-1111-1111-1111-111111111111"]
    )
    assert result == {"sent": 0, "skipped": 0, "failed": 1}


@pytest.mark.anyio
async def test_send_update_notifications_recipient_outside_qa_list_still_sends(
    monkeypatch,
) -> None:
    """接收人不在 QA 候选名单（如直接配置的跨部门接收人）时仍按 open_id 解析发送。"""
    service = _service()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.list_documents_by_ids",
        AsyncMock(return_value=[_doc("11111111-1111-1111-1111-111111111111")]),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.notification_record_exists",
        AsyncMock(return_value=False),
    )
    create_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.create_notification_records",
        create_mock,
    )
    _patch_send_chain(
        monkeypatch,
        credentials=("cli_app", "secret"),
        resolved=("zhangqizhi01", "user_id"),
    )
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.notification_service.send_user_card",
        send_mock,
    )
    result = await service.send_update_notifications(
        document_ids=["11111111-1111-1111-1111-111111111111"]
    )
    assert result == {"sent": 1, "skipped": 0, "failed": 0}
    send_mock.assert_awaited_once()
    create_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_send_update_notifications_send_and_records(monkeypatch) -> None:
    session = AsyncMock()
    service = _service(session)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=_enabled_setting()),
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
    _patch_send_chain(
        monkeypatch,
        credentials=("cli_app", "secret"),
        resolved=("zhangqizhi01", "user_id"),
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
    kwargs = send_mock.await_args.kwargs
    assert kwargs["open_id"] == "zhangqizhi01"
    assert kwargs["receive_id_type"] == "user_id"
    assert kwargs["app_id"] == "cli_app"
    assert kwargs["app_secret"] == "secret"
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
        "app.modules.regulatory_tracker.repository.list_documents_by_ids",
        AsyncMock(return_value=[_doc("11111111-1111-1111-1111-111111111111")]),
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.notification_record_exists",
        AsyncMock(return_value=False),
    )
    _patch_send_chain(
        monkeypatch,
        credentials=("cli_app", "secret"),
        resolved=("zhangqizhi01", "user_id"),
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


# ── 消息模板渲染与测试发送 ──────────────────────────────


def _template_doc(i: int) -> Any:
    return SimpleNamespace(
        title=f"法规{i}",
        source_site_name="NMPA",
        publish_date=date(2024, 1, i),
        ai_summary=None,
        summary_text=f"摘要{i}",
        source_url=f"https://x/{i}",
        original_url=None,
    )


def test_build_notification_content_templates() -> None:
    docs = [_template_doc(i) for i in range(1, 13)]
    # 默认文案保持历史行为
    default_content = _build_notification_content(docs)
    assert default_content.startswith("以下为今日法规跟踪自动抓取到的更新内容")
    assert "其余还有 **2** 条" in default_content

    # 自定义开头语/结尾语：占位符渲染；自定义结尾语替代默认溢出行
    custom = _build_notification_content(
        docs[:2],
        header_template="{date} 共 {count} 条法规更新（未知 {nope}）",
        footer_template="溢出 {overflow_count} 条，请及时处理",
    )
    assert custom.split("\n", 1)[0] == (
        f"{date.today().isoformat()} 共 2 条法规更新（未知 {{nope}}）"
    )
    assert "其余还有" not in custom
    assert "溢出 0 条，请及时处理" in custom

    # 空白模板回退默认
    blank = _build_notification_content(docs[:1], header_template="  ")
    assert blank.startswith("以下为今日法规跟踪自动抓取到的更新内容")


@pytest.mark.anyio
async def test_send_test_notification_paths(monkeypatch) -> None:
    service = _service()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service,
        "_get_recipient_by_open_id",
        AsyncMock(return_value=None),
    )
    with pytest.raises(AppException, match="QA 联系人范围"):
        await service.send_test_notification(recipient_open_id="ou-x")

    # 已保存的接收人调离 QA 名单后，仍允许测试验证（与真实发送行为一致）
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.get_notification_setting",
        AsyncMock(
            return_value=SimpleNamespace(
                is_enabled=True,
                recipient_open_id="ou_saved",
                recipient_name="张起智",
                recipient_department="AI创新部",
                schedule_time="10:00",
                recent_days=1,
                header_template=None,
                footer_template=None,
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_list_sample_documents",
        AsyncMock(return_value=[_template_doc(1)]),
    )
    _patch_send_chain(
        monkeypatch,
        credentials=("cli_app", "secret"),
        resolved=("zhangqizhi01", "user_id"),
    )
    result = await service.send_test_notification(recipient_open_id="ou_saved")
    assert result["sent"] is True
    assert result["recipient_name"] == "张起智"

    monkeypatch.setattr(
        service,
        "_get_recipient_by_open_id",
        AsyncMock(
            return_value=SimpleNamespace(
                open_id="ou-1", name="张起智", department="QA部",
                enterprise_email=None,
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_list_sample_documents",
        AsyncMock(return_value=[_template_doc(1)]),
    )
    # 凭证缺失 → 失败带原因
    _patch_send_chain(monkeypatch, credentials=("", ""), resolved=None)
    result = await service.send_test_notification(recipient_open_id="ou-1")
    assert result["sent"] is False
    assert "未配置" in str(result["detail"])

    # 成功 → 模板草稿生效，不写推送记录
    create_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.repository.create_notification_records",
        create_mock,
    )
    _patch_send_chain(
        monkeypatch,
        credentials=("cli_app", "secret"),
        resolved=("zhangqizhi01", "user_id"),
    )
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.notification_service.send_user_card",
        send_mock,
    )
    result = await service.send_test_notification(
        recipient_open_id="ou-1",
        header_template="测试开头 {count}",
        footer_template="测试结尾",
    )
    assert result == {
        "sent": True,
        "recipient_name": "张起智",
        "detail": "测试消息已发送至 张起智",
    }
    kwargs = send_mock.await_args.kwargs
    assert kwargs["open_id"] == "zhangqizhi01"
    assert kwargs["receive_id_type"] == "user_id"
    assert "测试开头 1" in kwargs["content"]
    assert "测试结尾" in kwargs["content"]
    create_mock.assert_not_awaited()
@pytest.mark.anyio
async def test_list_sample_documents_prefers_real_rows() -> None:
    """有 accepted 法规时返回真实最近 3 条。"""
    rows = [
        SimpleNamespace(title=f"真实法规 {i}", capture_date=date(2026, 9, 1 + i))
        for i in range(3)
    ]
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: rows)
            )
        )
    )
    service = RegulatoryTrackerNotificationService(session)
    docs = await service._list_sample_documents()
    assert len(docs) == 3
    assert all("真实法规" in doc.title for doc in docs)


@pytest.mark.anyio
async def test_list_sample_documents_synthesizes_when_empty() -> None:
    """无 accepted 法规时返回 3 条合成样例。"""
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [])
            )
        )
    )
    service = RegulatoryTrackerNotificationService(session)
    docs = await service._list_sample_documents()
    assert len(docs) == 3
    assert all("测试样例" in doc.title for doc in docs)
