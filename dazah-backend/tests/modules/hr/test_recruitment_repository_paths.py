from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.hr import recruitment_repository
from app.modules.hr.recruitment_repository import (
    TBL_CANDIDATE,
    TBL_JOB_POSTING,
    TBL_ONBOARDING,
    RecruitmentBitableRepo,
)


@pytest.mark.asyncio
async def test_recruitment_repository_maps_and_filters_all_tables() -> None:
    job = {
        "record_id": "job-1",
        "fields": {
            "职位名称": [{"text": "质量员", "type": "text"}],
            "发布时间": 1_756_000_000_000,
        },
    }
    candidate = {
        "record_id": "candidate-1",
        "fields": {
            "姓名": [{"text": "张三", "type": "text"}],
            "联系方式": "13800000000",
            "邮箱": "candidate@example.test",
            "应聘职位": [{"id": "job-1"}],
            "技能匹配度": 90,
            "招聘符合程度": "高",
            "面试状态": "待面试",
            "简历附件": [
                {
                    "file_token": "file-1",
                    "name": "resume.pdf",
                    "type": "pdf",
                    "size": 12,
                }
            ],
        },
    }
    onboarding = [
        {
            "record_id": "ob-1",
            "fields": {
                "姓名": "李四",
                "入职部门": "质量部",
                "入职状态": "已完成",
            },
        },
        {
            "record_id": "ob-2",
            "fields": {
                "姓名": "王五",
                "入职部门": "生产部",
                "入职状态": "进行中",
                "体检状态": "未进行",
                "入职日期": "2026-08-26",
                "离职证明": "未提供",
                "身份证信息": "已提供",
                "学历证明": "未提供",
            },
        },
    ]

    async def search_records(
        table_id: str, **_kwargs: object
    ) -> list[dict[str, object]]:
        return {
            TBL_JOB_POSTING: [job],
            TBL_CANDIDATE: [candidate],
            TBL_ONBOARDING: onboarding,
        }.get(table_id, [])

    async def create_record(
        table_id: str, _fields: dict[str, object]
    ) -> dict[str, object]:
        if table_id == TBL_ONBOARDING:
            return onboarding[0]
        return job

    client = SimpleNamespace(
        search_records=search_records,
        create_record=AsyncMock(side_effect=create_record),
        update_record=AsyncMock(),
        delete_record=AsyncMock(),
    )
    repo = RecruitmentBitableRepo(app_token="app-token")
    repo._client = client
    repo._resolved_token = "app-token"

    jobs, job_total = await repo.list_jobs(keyword="质量")
    assert job_total == 1
    assert jobs[0]["title"] == "质量员"
    assert (await repo.get_job_names()) == {"job-1": "质量员"}
    assert (await repo.get_job("job-1"))["id"] == "job-1"
    assert (await repo.list_candidates(keyword="张三", fit_level="高", job_id="job-1"))[
        1
    ] == 1
    candidate_result = await repo.get_candidate("candidate-1")
    assert candidate_result["resume_attachment"]["file_token"] == "file-1"
    assert (await repo.list_onboarding(dept_alias_set={"质量部"}))[1] == 1
    dashboard = await repo.get_dashboard_stats()
    assert dashboard["total"] == 2
    assert dashboard["stages"]["stage_5_done"]["count"] == 1
    scoped_dashboard = await repo.get_dashboard_stats({"质量部"})
    assert scoped_dashboard["total"] == 1

    await repo.create_job({"title": "新岗位", "publish_date": "2026-08-26"})
    await repo.update_job("job-1", {"title": "更新岗位"})
    await repo.create_candidate({"name": "新候选人"})
    await repo.update_candidate("candidate-1", {"remark": "已联系"})
    await repo.soft_delete_candidate("candidate-1")
    await repo.create_onboarding({"name": "新员工"})
    await repo.update_onboarding("ob-1", {"status": "进行中"})
    assert client.update_record.await_count == 3
    assert client.delete_record.await_count == 1


@pytest.mark.asyncio
async def test_recruitment_repository_unconfigured_and_not_found_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = RecruitmentBitableRepo()
    monkeypatch.setattr(
        recruitment_repository,
        "get_module_setting",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: type("Settings", (), {"FEISHU_BITABLE_APP_TOKEN": ""})(),
    )
    assert await repo._get_client() is None
    assert await repo.list_jobs() == ([], 0)
    with pytest.raises(Exception):
        await repo.get_job("missing")
