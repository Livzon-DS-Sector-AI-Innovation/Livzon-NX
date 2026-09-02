"""招聘模块 职位↔候选人 关联回归测试。

背景：飞书候选人表「应聘职位」字段可能存职位 record_id（关联字段），
也可能存职位名称文本（文本/单选字段）。旧代码只按 record_id 匹配，
导致「应聘职位存名称」时点职位看不到候选人、候选人数恒为 0。

修复后按 record_id 或职位名称并集匹配，本测试用假 bitable client 覆盖三种场景：
- 按职位名称过滤候选人
- 按职位 record_id 过滤候选人
- 职位候选人计数（candidate_count）与职位显示名（job_position）解析
"""

from __future__ import annotations

import pytest

from app.modules.hr.recruitment_repository import RecruitmentBitableRepo
from app.modules.hr.recruitment_service import RecruitmentService

TBL_JOB = "tbldWBRTNm5RrQHw"
TBL_CAND = "tblx3KvkQoHdGjFL"

JOBS = [
    {"record_id": "rec_job_env", "fields": {
        "职位名称": "环保主管", "招聘状态": "招聘中"
    }},
    {"record_id": "rec_job_yb", "fields": {
        "职位名称": "仪表工", "招聘状态": "招聘中"
    }},
]

# 候选人「应聘职位」：前两条存职位名称，第三条存 record_id（关联字段形态）
CANDIDATES = [
    {"record_id": "rec_c1", "fields": {
        "姓名": "张三", "应聘职位": "环保主管", "面试状态": "待安排"
    }},
    {"record_id": "rec_c2", "fields": {
        "姓名": "李四", "应聘职位": "仪表工", "面试状态": "待安排"
    }},
    {
        "record_id": "rec_c3",
        "fields": {
            "姓名": "王五",
            "应聘职位": {"link_record_ids": ["rec_job_env"]},
            "面试状态": "待安排",
        },
    },
    {"record_id": "rec_c4", "fields": {
        "姓名": "赵六", "应聘职位": "环保主管", "面试状态": "已删除"
    }},
]


class FakeBitableClient:
    """按表返回假飞书记录的 client，search_records 是异步方法。"""

    def __init__(self) -> None:
        self._by_table = {TBL_JOB: JOBS, TBL_CAND: CANDIDATES}

    async def search_records(self, table_id: str, **kwargs) -> list[dict]:
        return self._by_table.get(table_id, [])


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> RecruitmentService:
    client = FakeBitableClient()

    async def fake_get_client(self):
        return client

    monkeypatch.setattr(RecruitmentBitableRepo, "_get_client", fake_get_client)
    return RecruitmentService()


@pytest.mark.asyncio
async def test_filter_by_title(service: RecruitmentService) -> None:
    """按职位 record_id 过滤：应聘职位存职位名称的候选人也能命中。"""
    items, total = await service.list_candidates(job_id="rec_job_env", page_size=100)
    names = {it["name"] for it in items}
    assert total == 2
    assert names == {"张三", "王五"}  # 张三=名称命中，王五=record_id 命中
    assert "李四" not in names


@pytest.mark.asyncio
async def test_filter_by_record_id(service: RecruitmentService) -> None:
    """按职位 record_id 过滤：应聘职位存 record_id（关联字段）的候选人也命中。"""
    items, total = await service.list_candidates(job_id="rec_job_yb", page_size=100)
    names = {it["name"] for it in items}
    assert total == 1
    assert names == {"李四"}


@pytest.mark.asyncio
async def test_soft_deleted_filtered_out(service: RecruitmentService) -> None:
    """面试状态=已删除 的候选人在按职位过滤后仍被排除。"""
    items, _ = await service.list_candidates(job_id="rec_job_env", page_size=100)
    names = {it["name"] for it in items}
    assert "赵六" not in names


@pytest.mark.asyncio
async def test_job_position_resolved(service: RecruitmentService) -> None:
    """候选人 job_position 能正确显示职位名称（无论存的是 record_id 还是名称）。"""
    items, _ = await service.list_candidates(page_size=100)
    by_name = {it["name"]: it for it in items}
    assert by_name["张三"]["job_position"] == "环保主管"
    assert by_name["王五"]["job_position"] == "环保主管"  # record_id → 名称
    assert by_name["李四"]["job_position"] == "仪表工"


@pytest.mark.asyncio
async def test_candidate_count_per_job(service: RecruitmentService) -> None:
    """职位列表 candidate_count：按 record_id 或名称都能正确统计。"""
    jobs, total = await service.list_jobs(page_size=100)
    assert total == 2
    by_id = {j["id"]: j for j in jobs}
    assert by_id["rec_job_env"]["candidate_count"] == 2  # 张三(名称) + 王五(record_id)
    assert by_id["rec_job_yb"]["candidate_count"] == 1   # 李四
