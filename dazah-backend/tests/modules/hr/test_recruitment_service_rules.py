from __future__ import annotations

from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.llm import LLMOutputError, LLMProviderError, LLMRateLimitError
from app.modules.hr import recruitment_service as service

SimpleNamespace: Any = _SimpleNamespace


def _recruitment(repo: SimpleNamespace) -> service.RecruitmentService:
    instance = service.RecruitmentService.__new__(service.RecruitmentService)
    instance.repo = repo
    return instance


def _onboarding(repo: SimpleNamespace) -> service.OnboardingService:
    instance = service.OnboardingService.__new__(service.OnboardingService)
    instance.repo = repo
    return instance


def test_translate_and_untranslate_preserve_unknown_fields() -> None:
    translated = service._translate(
        {"title": "工程师", "custom": 1}, service.JOB_FIELD_MAP
    )
    assert translated == {"职位名称": "工程师", "custom": 1}
    assert service._untranslate(translated, service.JOB_FIELD_MAP) == {
        "title": "工程师",
        "custom": 1,
    }


@pytest.mark.anyio
async def test_job_crud_and_list_support_dict_tuple_and_invalid_results() -> None:
    repo: Any = SimpleNamespace(
        list_jobs=AsyncMock(
            return_value={"items": [{"id": "j1", "职位名称": "工程师"}], "total": 1}
        ),
        list_candidates=AsyncMock(return_value=([{"job_id": "j1"}, {"job_id": ""}], 2)),
        create_job=AsyncMock(return_value={"id": "j2", "职位名称": "经理"}),
        get_job=AsyncMock(return_value={"id": "j1", "职位名称": "工程师"}),
        update_job=AsyncMock(return_value={"id": "j1", "招聘状态": "关闭"}),
    )
    instance = _recruitment(repo)
    jobs, total = await instance.list_jobs(keyword="工")
    assert total == 1
    assert jobs[0]["candidate_count"] == 1
    assert (await instance.create_job({"title": "经理"}))["title"] == "经理"
    assert (await instance.get_job("j1"))["title"] == "工程师"
    assert (await instance.update_job("j1", {"status": "关闭"}))["status"] == "关闭"

    repo.list_jobs.return_value = ([{"id": "j1", "职位名称": "工程师"}], 3)
    assert (await instance.list_jobs())[1] == 3
    repo.list_jobs.return_value = [{"id": "j1", "职位名称": "工程师"}]
    assert (await instance.list_jobs())[1] == 1
    repo.list_jobs.return_value = None
    assert await instance.list_jobs() == ([], 0)


@pytest.mark.anyio
async def test_candidate_crud_listing_job_resolution_and_status_email_failure() -> None:
    repo: Any = SimpleNamespace(
        list_candidates=AsyncMock(
            return_value={
                "items": [{"id": "c1", "姓名": "张三", "应聘职位": "j1"}],
                "total": 1,
            }
        ),
        get_job_names=AsyncMock(return_value={"j1": "工程师"}),
        create_candidate=AsyncMock(return_value={"id": "c2", "姓名": "李四"}),
        get_candidate=AsyncMock(
            return_value={"id": "c1", "姓名": "张三", "应聘职位": "j1"}
        ),
        update_candidate=AsyncMock(
            return_value={
                "id": "c1",
                "姓名": "张三",
                "邮箱": "a@example.com",
                "应聘职位": "j1",
            }
        ),
        soft_delete_candidate=AsyncMock(),
    )
    instance = _recruitment(repo)
    items, total = await instance.list_candidates(job_id="j1")
    assert total == 1
    assert items[0]["job_position"] == "工程师"
    assert (await instance.create_candidate({"name": "李四"}))["name"] == "李四"
    assert (await instance.get_candidate("c1"))["job_position"] == "工程师"

    instance._send_status_email = AsyncMock(side_effect=RuntimeError("mail failed"))  # type: ignore[method-assign]
    updated = await instance.update_candidate("c1", {"interview_status": "通过"})
    assert updated["name"] == "张三"
    await instance.update_candidate("c1", {"interview_status": "待面试"})
    await instance.delete_candidate("c1")
    repo.soft_delete_candidate.assert_awaited_once_with("c1")

    repo.list_candidates.return_value = ([{"id": "c1", "姓名": "张三"}],)
    assert (await instance.list_candidates())[1] == 1
    repo.list_candidates.return_value = None
    assert await instance.list_candidates() == ([], 0)


def test_default_email_bodies_cover_offer_and_rejection() -> None:
    instance = _recruitment(SimpleNamespace())
    variables = {
        "name": "张三",
        "position": "工程师",
        "department": "质量部",
        "onboard_date": "2026-09-01",
    }
    assert "录用通知书" in instance._get_default_body("通过", variables)
    assert "未能通过" in instance._get_default_body("不符合", variables)


@pytest.mark.anyio
async def test_analyze_resume_success_with_and_without_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _recruitment(SimpleNamespace())
    chat: Any = AsyncMock(return_value={"name": "张三", "match_rate": 80})
    monkeypatch.setattr(type(service.llm_client), "chat_json", chat)  # type: ignore[attr-defined]
    assert (await instance.analyze_resume("简历", "岗位要求"))["match_rate"] == 80
    assert (await instance.analyze_resume("简历", ""))["name"] == "张三"
    assert "岗位信息卡" in chat.await_args_list[0].kwargs["messages"][1]["content"]
    assert "无岗位信息" in chat.await_args_list[1].kwargs["messages"][1]["content"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        LLMOutputError("invalid"),
        LLMProviderError("provider"),
        LLMRateLimitError("rate"),
    ],
)
async def test_analyze_resume_retries_and_raises_last_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    instance = _recruitment(SimpleNamespace())
    monkeypatch.setattr(
        type(service.llm_client),  # type: ignore[attr-defined]
        "chat_json",
        AsyncMock(side_effect=error),
    )
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())  # type: ignore[attr-defined]
    with pytest.raises(type(error)):
        await instance.analyze_resume("简历")


@pytest.mark.anyio
async def test_vision_analysis_short_non_pdf_and_invalid_pdf() -> None:
    instance = _recruitment(SimpleNamespace())
    assert await instance._try_vision_analysis(b"docx", "resume.docx", "") is None
    assert await instance._try_vision_analysis(b"pdf", "resume.pdf", "") is None
    assert (
        await instance._try_vision_analysis(b"not-a-pdf" * 20, "resume.pdf", "") is None
    )


@pytest.mark.anyio
async def test_onboarding_create_prefers_list_then_falls_back_and_resolves_job() -> (
    None
):
    repo: Any = SimpleNamespace(
        list_candidates=AsyncMock(
            return_value=([{"id": "c1", "姓名": "张三", "应聘职位": "j1"}], 1)
        ),
        get_candidate=AsyncMock(
            return_value={"id": "c2", "姓名": "李四", "应聘职位": "j2"}
        ),
        get_job_names=AsyncMock(return_value={"j1": "工程师", "j2": "经理"}),
        create_onboarding=AsyncMock(side_effect=lambda data: {"id": "o1", **data}),
        list_onboarding=AsyncMock(return_value={"items": [{"id": "o1"}], "total": 1}),
        get_onboarding=AsyncMock(return_value={"id": "o1"}),
        update_onboarding=AsyncMock(return_value={"id": "o1", "status": "完成"}),
        get_dashboard_stats=AsyncMock(return_value={"total": 1}),
    )
    instance = _onboarding(repo)
    created = await instance.create_from_interview("c1")
    assert created["level"] == "工程师"
    assert created["status"] == "进行中"

    repo.list_candidates.return_value = ([], 0)
    fallback = await instance.create_from_interview("c2")
    assert fallback["name"] == "李四"
    assert fallback["level"] == "经理"
    assert await instance.list_onboarding() == ([{"id": "o1"}], 1)
    assert await instance.get_onboarding("o1") == {"id": "o1"}
    assert (await instance.update_onboarding("o1", {"status": "完成"}))[
        "status"
    ] == "完成"
    assert await instance.get_dashboard({"质量部"}) == {"total": 1}


@pytest.mark.anyio
async def test_onboarding_list_supports_tuple_and_invalid_results() -> None:
    repo: Any = SimpleNamespace(
        list_onboarding=AsyncMock(return_value=([{"id": "o1"}], 4))
    )
    instance = _onboarding(repo)
    assert (await instance.list_onboarding())[1] == 4
    repo.list_onboarding.return_value = ([{"id": "o1"}],)
    assert (await instance.list_onboarding())[1] == 1
    repo.list_onboarding.return_value = None
    assert await instance.list_onboarding() == ([], 0)
