"""AI 笔试出题异步任务测试。

测试范围（对应 AI 笔试出题性能优化规格说明 Testing Decisions）：
- Semaphore 并发限流：并发峰值 ≤ 配置值（mock llm_client.chat_json 记录并发）
- 指数退避重试：LLMRateLimitError 重试 2 次、退避 1s/2s(+3s)、最终成功；
  LLMOutputError 不重试直接失败
- POST /ai/exam/generate-written：提交后台任务返回 job_id，任务参数正确传递
- GET /ai/exam/generate-written/{job_id}：running/completed/failed/404 四种状态

外部依赖（llm_client、jobs Redis、module_settings DB）全部 mock。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AppException
from app.core.llm import LLMOutputError, LLMRateLimitError
from app.modules.hr.ai_exam_api import generate_written_exam, get_written_exam_job
from app.platform.ai.schemas import OralExamFile, WrittenExamGenerateRequest

# ── Helpers ───────────────────────────────────────────


def _make_body(
    single: int = 5,
    multiple: int = 0,
    true_false: int = 0,
    fill: int = 5,
    file_count: int = 1,
    file_chars: int = 1000,
) -> WrittenExamGenerateRequest:
    """构造出题请求：file_count 份文件（各 file_chars 字符），内容不同避免去重。"""
    files = [
        OralExamFile(
            name=f"文件{i}",
            code=f"FILE-{i}",
            content=f"培训内容{i}" * (file_chars // 4 + 1),
        )
        for i in range(file_count)
    ]
    return WrittenExamGenerateRequest(
        files=files,
        uploaded_content="",
        manual_content="",
        single_choice_count=single,
        multiple_choice_count=multiple,
        true_false_count=true_false,
        fill_blank_count=fill,
    )


def _question_result(prefix: str = "q") -> dict:
    """模拟 LLM chat_json 的成功返回。"""
    return {
        "choice_questions": [
            {
                "number": 1,
                "question": f"{prefix}题干",
                "options": [
                    {"label": "A", "text": "a"},
                    {"label": "B", "text": "b"},
                    {"label": "C", "text": "c"},
                    {"label": "D", "text": "d"},
                ],
                "answer": "A",
            }
        ],
        "true_false_questions": [
            {"number": 1, "question": f"{prefix}判断", "answer": "√"}
        ],
        "fill_blank_questions": [
            {"number": 1, "question": f"{prefix}填空______", "answer": "答案"}
        ],
    }


async def _fake_module_setting(*args, **kwargs):
    """mock get_module_setting：按 key 返回出题参数缺省值。"""
    defaults = {
        "HR_EXAM_MAX_CONCURRENCY": "3",
        "HR_EXAM_QUESTIONS_PER_BATCH": "10",
        "HR_EXAM_BATCH_TIMEOUT": "300",
        "HR_EXAM_BATCH_CONTENT_MAX": "20000",
        "HR_EXAM_TOTAL_CONTENT_MAX": "120000",
        "HR_EXAM_SUBMIT_RATE_LIMIT": "5",
    }
    return defaults.get(args[1], kwargs.get("default", ""))


class _CapturedJob:
    """捕获 submit_job 传入的任务函数与参数，供测试直接执行。"""

    def __init__(self) -> None:
        self.fn = None
        self.kwargs = None
        self.task_id = None

    async def submit(self, fn, task_id=None, **kwargs):
        self.fn = fn
        self.kwargs = kwargs
        self.task_id = task_id
        return task_id or "job:test"

    async def run(self) -> dict:
        assert self.fn is not None
        return await self.fn(**self.kwargs)


# ── POST：提交异步任务返回 job_id ─────────────────────


@pytest.mark.asyncio
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
async def test_submit_returns_job_id(mock_setting):
    """POST 应提交后台任务并立即返回 job_id（不阻塞等待出题完成）。"""
    captured = _CapturedJob()
    body = _make_body(single=3, fill=2, file_count=1)

    with patch("app.modules.hr.ai_exam_api.submit_job", side_effect=captured.submit):
        resp = await generate_written_exam(body, current_user=MagicMock())

    # 立即返回 job_id
    assert resp.status_code == 200
    data = resp.body.decode() if isinstance(resp.body, bytes) else resp.body
    import json

    payload = json.loads(data)["data"]
    assert payload["job_id"].startswith("hr:exam:written:")
    assert payload["job_id"] == captured.task_id

    # 任务参数正确传递
    assert captured.fn is not None
    assert captured.kwargs["single_choice_count"] == 3
    assert captured.kwargs["fill_blank_count"] == 2
    assert len(captured.kwargs["files"]) == 1


@pytest.mark.asyncio
async def test_submit_requires_login():
    """未登录提交出题应返回 401。"""
    with pytest.raises(AppException) as exc_info:
        await generate_written_exam(_make_body(), current_user=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
async def test_submit_rejects_zero_questions(mock_setting):
    """所有题型数量均为 0 时应返回 400。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await generate_written_exam(
            _make_body(single=0, fill=0), current_user=MagicMock()
        )
    assert exc_info.value.status_code == 400


# ── Semaphore 并发限流 ───────────────────────────────


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.update_job_progress", new_callable=AsyncMock)
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
async def test_concurrency_limited_by_semaphore(mock_setting, mock_progress):
    """并发峰值不得超过配置的并发数（HR_EXAM_MAX_CONCURRENCY=2）。"""
    active = 0
    peak = 0
    lock = asyncio.Lock()
    call_count = 0

    async def _fake_chat_json(messages, **kwargs):
        nonlocal active, peak, call_count
        async with lock:
            active += 1
            peak = max(peak, active)
            call_count += 1
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1
        return _question_result(f"q{call_count}")

    captured = _CapturedJob()
    # 3 份大文件（各 31255 字符 > 单批素材上限 20000）→ 各自独立成 3 批；
    # 请求 3 单选+3 填空 → 加权后每批恰好 1+1=2 题（3 批均有任务）
    body = _make_body(single=3, fill=3, file_count=3, file_chars=25000)

    async def _fake_setting_two(*args, **kwargs):
        if args[1] == "HR_EXAM_MAX_CONCURRENCY":
            return "2"
        return await _fake_module_setting(*args, **kwargs)

    with (
        patch(
            "app.modules.hr.ai_exam_api.llm_client.chat_json",
            side_effect=_fake_chat_json,
        ),
        patch("app.modules.hr.ai_exam_api.submit_job", side_effect=captured.submit),
        patch(
            "app.modules.hr.ai_exam_api.get_module_setting",
            side_effect=_fake_setting_two,
        ),
    ):
        await generate_written_exam(body, current_user=MagicMock())
        result = await captured.run()

    assert call_count == 3
    assert peak <= 2, f"并发峰值 {peak} 超过配置并发数 2"
    # 出题成功且题目汇总后返回
    assert len(result["choice_questions"]) >= 1


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.update_job_progress", new_callable=AsyncMock)
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
async def test_concurrency_serial_when_limit_one(mock_setting, mock_progress):
    """并发数配置为 1 时批次应串行执行（峰值=1）。"""
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def _fake_chat_json(messages, **kwargs):
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1
        return _question_result()

    captured = _CapturedJob()
    body = _make_body(single=3, fill=3, file_count=3, file_chars=25000)

    async def _fake_setting_one(*args, **kwargs):
        if args[1] == "HR_EXAM_MAX_CONCURRENCY":
            return "1"
        return await _fake_module_setting(*args, **kwargs)

    with (
        patch(
            "app.modules.hr.ai_exam_api.llm_client.chat_json",
            side_effect=_fake_chat_json,
        ),
        patch("app.modules.hr.ai_exam_api.submit_job", side_effect=captured.submit),
        patch(
            "app.modules.hr.ai_exam_api.get_module_setting",
            side_effect=_fake_setting_one,
        ),
    ):
        await generate_written_exam(body, current_user=MagicMock())
        await captured.run()

    assert peak == 1, f"并发数=1 时峰值应为 1，实际 {peak}"


# ── 指数退避重试 ─────────────────────────────────────


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.update_job_progress", new_callable=AsyncMock)
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
async def test_retry_on_rate_limit_with_backoff(mock_setting, mock_progress):
    """LLMRateLimitError 应重试至多 2 次（共 3 次尝试）。

    退避 1s/2s，并为 429 增加额外 3s，最终成功。
    """
    attempts = 0
    sleep_calls: list[float] = []

    async def _fake_chat_json(messages, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise LLMRateLimitError("rate limited", status_code=429)
        return _question_result()

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    captured = _CapturedJob()
    body = _make_body(single=1, fill=1, file_count=1)

    with (
        patch(
            "app.modules.hr.ai_exam_api.llm_client.chat_json",
            side_effect=_fake_chat_json,
        ),
        patch("app.modules.hr.ai_exam_api.submit_job", side_effect=captured.submit),
        patch("app.modules.hr.ai_exam_api.asyncio.sleep", side_effect=_fake_sleep),
    ):
        await generate_written_exam(body, current_user=MagicMock())
        result = await captured.run()

    assert attempts == 3, f"应重试 2 次共 3 次尝试，实际 {attempts}"
    # 退避：第一次失败 wait=1+3=4s，第二次失败 wait=2+3=5s（429 额外 +3s）
    assert sleep_calls == [4.0, 5.0], f"退避时间应为 [4, 5]，实际 {sleep_calls}"
    # 重试后成功
    assert result["choice_questions"]
    assert len(result["choice_questions"]) == 1


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.update_job_progress", new_callable=AsyncMock)
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
async def test_no_retry_on_output_error(mock_setting, mock_progress):
    """LLMOutputError（格式错误）不应重试：仅 1 次调用，全部批次失败 → 422。"""
    calls = 0

    async def _fake_chat_json(messages, **kwargs):
        nonlocal calls
        calls += 1
        raise LLMOutputError("bad json", raw_response="not json")

    captured = _CapturedJob()
    body = _make_body(single=1, fill=1, file_count=1)

    with (
        patch(
            "app.modules.hr.ai_exam_api.llm_client.chat_json",
            side_effect=_fake_chat_json,
        ),
        patch("app.modules.hr.ai_exam_api.submit_job", side_effect=captured.submit),
    ):
        await generate_written_exam(body, current_user=MagicMock())
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await captured.run()

    # 不重试：仅 1 次调用；全部批次失败 → HTTPException(422)
    assert calls == 1
    assert exc_info.value.status_code == 422


# ── GET：轮询任务状态 ────────────────────────────────


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_job_status")
async def test_get_job_running(mock_status):
    """running 状态返回进度文案。"""
    mock_status.return_value = {
        "state": "running",
        "progress": "正在生成第 1/3 批题目…",
        "result": None,
    }
    resp = await get_written_exam_job("job:1", current_user=MagicMock())
    import json

    payload = json.loads(resp.body)["data"]
    assert payload["state"] == "running"
    assert payload["progress"] == "正在生成第 1/3 批题目…"
    assert payload.get("result") is None


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_job_status")
async def test_get_job_completed(mock_status):
    """completed 状态返回题目结果。"""
    mock_status.return_value = {
        "state": "completed",
        "progress": "完成",
        "result": {
            "choice_questions": [],
            "true_false_questions": [],
            "fill_blank_questions": [],
            "shortfall": False,
        },
    }
    resp = await get_written_exam_job("job:1", current_user=MagicMock())
    import json

    payload = json.loads(resp.body)["data"]
    assert payload["state"] == "completed"
    assert payload["result"]["shortfall"] is False


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_job_status")
async def test_get_job_failed(mock_status):
    """failed 状态返回错误信息。"""
    mock_status.return_value = {
        "state": "failed",
        "progress": "失败: AI 服务暂时不可用",
        "result": None,
    }
    resp = await get_written_exam_job("job:1", current_user=MagicMock())
    import json

    payload = json.loads(resp.body)["data"]
    assert payload["state"] == "failed"
    assert "AI 服务暂时不可用" in payload["progress"]


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_job_status")
async def test_get_job_not_found(mock_status):
    """任务不存在（Redis 已过期）应返回 404。"""
    mock_status.return_value = None
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_written_exam_job("job:gone", current_user=MagicMock())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_job_requires_login():
    """未登录查询任务应返回 401。"""
    with pytest.raises(AppException) as exc_info:
        await get_written_exam_job("job:1", current_user=None)
    assert exc_info.value.status_code == 401


# ── M1：job_id 归属校验（防 IDOR） ──────────────────────


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_job_status")
async def test_get_job_owner_mismatch_returns_404(mock_status):
    """任务 owner 与当前用户不一致时应返回 404（防 IDOR）。"""
    mock_status.return_value = {
        "state": "running",
        "progress": "正在生成第 1/3 批题目…",
        "owner": "other-user-id",
    }
    from fastapi import HTTPException

    me = MagicMock()
    me.id = "my-user-id"
    with pytest.raises(HTTPException) as exc_info:
        await get_written_exam_job("job:1", current_user=me)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_job_status")
async def test_get_job_owner_match_ok(mock_status):
    """任务 owner 与当前用户一致时可以正常读取。"""
    mock_status.return_value = {
        "state": "running",
        "progress": "正在生成第 1/3 批题目…",
        "owner": "my-user-id",
    }

    me = MagicMock()
    me.id = "my-user-id"
    resp = await get_written_exam_job("job:1", current_user=me)
    import json

    payload = json.loads(resp.body)["data"]
    assert payload["state"] == "running"


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_job_status")
async def test_get_job_no_owner_field_ok(mock_status):
    """旧任务无 owner 字段（历史任务）时不阻断读取，保持兼容。"""
    mock_status.return_value = {
        "state": "completed",
        "progress": "完成",
        "result": {"shortfall": False},
    }

    me = MagicMock()
    me.id = "my-user-id"
    resp = await get_written_exam_job("job:1", current_user=me)
    import json

    payload = json.loads(resp.body)["data"]
    assert payload["state"] == "completed"


# ── M3：运行参数钳制（防 0/负数死锁） ────────────────────


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_module_setting")
async def test_exam_setting_clamped_zero(mock_setting):
    """HR_EXAM_MAX_CONCURRENCY=0 时应钳制为 1，避免 Semaphore 死锁。"""
    from app.modules.hr.ai_exam_api import _clamp_setting, _exam_setting

    mock_setting.side_effect = ["0", "-5", "999", "0", "0"]
    assert await _exam_setting("HR_EXAM_MAX_CONCURRENCY") == 0  # 原始读取值
    # 钳制函数直接验证
    assert _clamp_setting(0, 1, 20) == 1
    assert _clamp_setting(-5, 1, 20) == 1
    assert _clamp_setting(999, 1, 20) == 20
    assert _clamp_setting(10, 1, 20) == 10


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_module_setting")
@patch("app.modules.hr.ai_exam_api.cache_incr", new_callable=AsyncMock)
@patch("app.modules.hr.ai_exam_api.submit_job", new_callable=AsyncMock)
async def test_generate_submits_with_owner(mock_submit, mock_incr, mock_setting):
    """提交任务时应记录 owner 字段（M1）。"""
    mock_setting.side_effect = ["5", "3", "10", "300", "20000", "120000"]
    mock_incr.return_value = 1
    body = _make_body(single=2, multiple=0, true_false=1, fill=2)
    me = MagicMock()
    me.id = "user-abc"
    await generate_written_exam(body, current_user=me)
    kwargs = mock_submit.call_args.kwargs
    assert kwargs["status_extra"] == {"owner": "user-abc"}


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_module_setting")
@patch("app.modules.hr.ai_exam_api.cache_incr", new_callable=AsyncMock)
@patch("app.modules.hr.ai_exam_api.submit_job", new_callable=AsyncMock)
async def test_generate_submits_job_id_length(mock_submit, mock_incr, mock_setting):
    """job_id 应使用 12 位 hex（M1 熵提升）。"""
    mock_setting.side_effect = ["5", "3", "10", "300", "20000", "120000"]
    mock_incr.return_value = 1
    body = _make_body(single=2, multiple=0, true_false=1, fill=2)
    me = MagicMock()
    me.id = "user-abc"
    await generate_written_exam(body, current_user=me)
    job_id = mock_submit.call_args.kwargs["task_id"]
    assert job_id.startswith("hr:exam:written:")
    suffix = job_id.split(":")[-1]
    assert len(suffix) == 12


# ── S1：输入内容长度上限 ─────────────────────────────


def test_written_request_content_max_length():
    """uploaded_content/manual_content 超 20 万字符应校验失败。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WrittenExamGenerateRequest(
            uploaded_content="x" * 200_001,
        )


def test_oral_file_content_max_length():
    """OralExamFile.content 超 20 万字符应校验失败。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OralExamFile(name="f.md", content="x" * 200_001)


# ── A4：failed 状态同步填充 error 字段 ─────────────────


@pytest.mark.asyncio
@patch("app.modules.hr.ai_exam_api.get_job_status")
async def test_get_job_failed_fills_error_field(mock_status):
    """failed 分支 progress 与 error 字段应同步填充（A4）。"""
    mock_status.return_value = {
        "state": "failed",
        "progress": "失败: AI 服务暂时不可用",
        "result": None,
    }
    me = MagicMock()
    me.id = "my-user-id"
    resp = await get_written_exam_job("job:1", current_user=me)
    import json

    payload = json.loads(resp.body)["data"]
    assert payload["state"] == "failed"
    assert payload["error"] == "失败: AI 服务暂时不可用"
    assert payload["progress"] == "失败: AI 服务暂时不可用"


# ── A5：空素材提交直接 400 ────────────────────────────


@pytest.mark.asyncio
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
async def test_generate_empty_material_returns_400(mock_setting):
    """文件/上传/手动全部无有效内容时直接 400（A5）。"""
    from fastapi import HTTPException

    body = WrittenExamGenerateRequest(
        files=[OralExamFile(name="empty.md", content="")],
        uploaded_content="",
        manual_content="",
        single_choice_count=3,
        fill_blank_count=2,
    )
    with pytest.raises(HTTPException) as exc_info:
        await generate_written_exam(body, current_user=MagicMock())
    assert exc_info.value.status_code == 400
    assert "培训材料内容" in str(exc_info.value.detail)


# ── A7：提交节流（Redis 计数器） ─────────────────────


@pytest.mark.asyncio
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
@patch("app.modules.hr.ai_exam_api.submit_job", new_callable=AsyncMock)
@patch("app.modules.hr.ai_exam_api.cache_incr", new_callable=AsyncMock)
async def test_generate_rate_limited_returns_429(mock_incr, mock_submit, mock_setting):
    """同一用户提交次数超过每分钟上限应返回 429（A7）。"""
    from fastapi import HTTPException

    mock_incr.return_value = 6  # 默认上限 5，第 6 次拒绝
    body = _make_body(single=2, fill=2)
    me = MagicMock()
    me.id = "user-abc"
    with pytest.raises(HTTPException) as exc_info:
        await generate_written_exam(body, current_user=me)
    assert exc_info.value.status_code == 429
    mock_submit.assert_not_called()


@pytest.mark.asyncio
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
@patch("app.modules.hr.ai_exam_api.submit_job", new_callable=AsyncMock)
@patch("app.modules.hr.ai_exam_api.cache_incr", new_callable=AsyncMock)
async def test_generate_rate_ok_within_limit(mock_incr, mock_submit, mock_setting):
    """未超限时正常提交任务（A7）。"""
    mock_incr.return_value = 3
    body = _make_body(single=2, fill=2)
    me = MagicMock()
    me.id = "user-abc"
    await generate_written_exam(body, current_user=me)
    mock_submit.assert_called_once()


@pytest.mark.asyncio
@patch(
    "app.modules.hr.ai_exam_api.get_module_setting", side_effect=_fake_module_setting
)
@patch("app.modules.hr.ai_exam_api.submit_job", new_callable=AsyncMock)
@patch(
    "app.modules.hr.ai_exam_api.cache_incr",
    new_callable=AsyncMock,
    side_effect=RuntimeError("redis down"),
)
async def test_generate_rate_check_failure_does_not_block(
    mock_incr, mock_submit, mock_setting
):
    """Redis 不可用时节流失效但不应阻断出题（A7 fail-open）。"""
    body = _make_body(single=2, fill=2)
    me = MagicMock()
    me.id = "user-abc"
    await generate_written_exam(body, current_user=me)
    mock_submit.assert_called_once()
