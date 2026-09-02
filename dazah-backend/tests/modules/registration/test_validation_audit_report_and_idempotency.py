"""回归：药审核对报告生成格式与问题保存幂等。

1. generate_report 是自然语言 Markdown，必须显式 response_format=None，
   否则 llm_client 默认 json_object 会把报告内容损坏（AGENTS.md LLM 边界）。
2. save_issues 必须先清空该任务旧问题再插入，重试审核不得重复插入。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.registration.schemas.validation_audit import (
    AuditIssueItem,
    AuditResult,
    TaskConclusion,
)
from app.modules.registration.service.validation_audit import ValidationAuditService


def _make_result() -> AuditResult:
    return AuditResult(
        conclusion=TaskConclusion.CONDITIONAL_PASS,
        risk_level="medium",
        summary="总结",
        issues=[
            AuditIssueItem(
                issue_no="P001",
                issue_type="general",
                dimension="内容",
                check_item="检查项",
                description="描述",
                suggestion="建议",
            )
        ],
    )


def _make_task() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        task_name="任务",
        product_name="产品",
        method_name="方法",
        source_company="公司",
        audit_mode="protocol",
        conclusion=None,
        risk_level=None,
        serious_count=0,
        general_count=0,
        suggestion_count=0,
        compliant_count=0,
        non_compliant_count=0,
    )


def _make_service() -> tuple[ValidationAuditService, SimpleNamespace]:
    session = SimpleNamespace()
    service = ValidationAuditService(session)  # type: ignore[arg-type]
    service.issue_repo.delete_by_task_id = AsyncMock()  # type: ignore[method-assign]
    service.issue_repo.list_by_task_id = AsyncMock(return_value=[])  # type: ignore[method-assign]
    return service, session


@pytest.mark.asyncio
async def test_generate_report_requests_markdown_not_json(tmp_path) -> None:
    """报告必须以非 JSON 模式请求 LLM，且 markdown 正常落盘。"""
    service, session = _make_service()
    task = _make_task()
    result = _make_result()

    captured: dict = {}

    async def _fake_chat(messages, **kwargs):
        captured.update(kwargs)
        return "# 审核报告\n\n正文内容"

    service.report_repo = SimpleNamespace(
        get_by_task_id=AsyncMock(return_value=None),
        create=AsyncMock(side_effect=lambda report: report),
    )
    service.task_repo = SimpleNamespace(update=AsyncMock())

    with patch(
        "app.modules.registration.service.validation_audit.llm_client"
    ) as fake_llm:
        fake_llm.chat = AsyncMock(side_effect=_fake_chat)
        with patch(
            "app.modules.registration.service.validation_audit._task_storage_path",
            return_value=tmp_path,
        ):
            report = await service.generate_report(task, result)

    assert captured.get("response_format") is None, (
        "generate_report 必须显式传 response_format=None（Markdown 报告），"
        "否则 llm_client 默认 json_object 会损坏报告内容"
    )
    assert report.report_markdown.startswith("# 审核报告")
    service.task_repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_issues_clears_existing_issues_before_insert() -> None:
    """重新审核时先删旧问题再插入，保证幂等不重复。"""
    service, session = _make_service()
    task = _make_task()
    result = _make_result()

    service.issue_repo.create_batch = AsyncMock(
        side_effect=lambda issues: list(issues)
    )
    service.task_repo = SimpleNamespace(update=AsyncMock())

    await service.save_issues(task, result)

    service.issue_repo.delete_by_task_id.assert_awaited_once_with(task.id)
    service.issue_repo.create_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_failed_sets_failed_status() -> None:
    """报告/保存环节失败后任务必须置 FAILED，不能停留 COMPLETED。"""
    service, session = _make_service()
    task = _make_task()
    update = AsyncMock()
    service.task_repo = SimpleNamespace(update=update)

    await service.mark_failed(task)

    update.assert_awaited_once()
    assert update.await_args.kwargs["status"] == "failed"
