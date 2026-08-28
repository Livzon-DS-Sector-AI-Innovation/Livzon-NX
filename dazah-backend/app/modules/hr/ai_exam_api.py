"""HR AI 考试生成与导出端点。

根据培训材料生成考核试卷，并支持导出为 Word 文档。
"""

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.jobs import get_job_status, submit_job, update_job_progress
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.redis import cache_incr
from app.core.response import success_response
from app.core.upload_security import read_upload_secure
from app.platform.ai.document_text_extractor import (
    DocumentParseError,
    extract_document_text,
)
from app.platform.ai.exam_generator import (
    build_generate_prompt,
    build_oral_generate_prompt,
    build_written_generate_prompt,
    generate_exam_docx,
    generate_written_exam_zip,
)
from app.platform.ai.schemas import (
    ChoiceQuestion,
    ExamExportRequest,
    ExamGenerateRequest,
    ExamGenerateResponse,
    FillBlankQuestion,
    OralExamGenerateRequest,
    OralExamGenerateResponse,
    TrueFalseQuestion,
    WrittenExamExportRequest,
    WrittenExamGenerateRequest,
    WrittenExamGenerateResponse,
    WrittenExamJobStatusResponse,
    WrittenExamJobSubmitResponse,
)
from app.shared.config_reader import get_module_setting

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 考试生成 ──────────────────────────────────────


@router.post(
    "/ai/exam/generate",
    summary="AI 生成培训考核试卷",
    response_model=ExamGenerateResponse,
)
async def generate_exam(
    body: ExamGenerateRequest, current_user: CurrentUser = None
) -> Any:
    """根据培训材料文本，调用 LLM 生成选择题和判断题。

    Returns:
        ExamGenerateResponse: 包含 choice_questions 和 true_false_questions
    """
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    prompt = build_generate_prompt(body.file_content)
    messages = [{"role": "user", "content": prompt}]

    logger.info("HR AI exam generation started")

    try:
        result = await llm_client.chat_json(
            messages,
            expected_keys=["choice_questions", "true_false_questions"],
            temperature=0.3,
        )
    except LLMOutputError:
        logger.error("LLM exam output parse failed", exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="AI 生成的考题格式不正确，请重试。",
        )
    except LLMRateLimitError:
        logger.warning("LLM rate limit exceeded during exam generation")
        raise HTTPException(
            status_code=429,
            detail="AI 服务当前请求过于频繁，请稍后再试。",
        )
    except (LLMProviderError, LLMConfigError):
        logger.error("LLM provider error during exam generation", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="AI 服务暂时不可用，请稍后重试。",
        )

    logger.info(
        "HR AI exam generated",
        extra={
            "choice_count": len(result.get("choice_questions", [])),
            "tf_count": len(result.get("true_false_questions", [])),
        },
    )

    return success_response(
        data=ExamGenerateResponse(
            choice_questions=result.get("choice_questions", []),
            true_false_questions=result.get("true_false_questions", []),
        ).model_dump(mode="json"),
    )


# ── 口试（问答）出题 ──────────────────────────────


@router.post(
    "/ai/exam/generate-oral",
    summary="AI 生成口试培训考核问答题",
    response_model=OralExamGenerateResponse,
)
async def generate_oral_exam(
    body: OralExamGenerateRequest,
    current_user: CurrentUser = None,
) -> Any:
    """根据培训材料文件内容，调用 LLM 生成口试问答题（问题+参考答案）。

    约束：每份文件 2~3 题；培训文件超过 5 份时总题数不超过 15 题。
    """
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    prompt = build_oral_generate_prompt(
        [f.model_dump() for f in body.files], question_count=body.question_count
    )
    messages = [{"role": "user", "content": prompt}]

    logger.info(
        "HR oral exam generation started",
        extra={"file_count": len(body.files)},
    )

    try:
        result = await llm_client.chat_json(
            messages,
            expected_keys=["questions"],
            temperature=0.3,
        )
    except LLMOutputError:
        logger.error("LLM oral exam output parse failed", exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="AI 生成的考题格式不正确，请重试。",
        )
    except LLMRateLimitError:
        logger.warning("LLM rate limit exceeded during oral exam generation")
        raise HTTPException(
            status_code=429,
            detail="AI 服务当前请求过于频繁，请稍后再试。",
        )
    except (LLMProviderError, LLMConfigError):
        logger.error("LLM provider error during oral exam generation", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="AI 服务暂时不可用，请稍后重试。",
        )
    except (httpx.TimeoutException, httpx.HTTPError):
        logger.error(
            "LLM request timeout/network error during oral exam generation",
            exc_info=True,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                "AI 服务响应超时或网络异常，请重试（文件较多时可适当减少勾选数量）。"
            ),
        )

    # 清洗 LLM 输出：过滤缺 question/answer 或非字典的无效项（LLM 偶发输出不完整）
    questions: list[dict[str, Any]] = []
    for q in result.get("questions") or []:
        if not isinstance(q, dict):
            continue
        question = str(q.get("question") or "").strip()
        answer = str(q.get("answer") or "").strip()
        if question and answer:
            questions.append({"question": question, "answer": answer})
    if not questions:
        logger.warning("LLM oral exam returned no valid questions")
        raise HTTPException(
            status_code=422,
            detail="AI 生成的考题格式不正确，请重试。",
        )
    logger.info(
        "HR oral exam generated",
        extra={"question_count": len(questions)},
    )

    return success_response(
        data=OralExamGenerateResponse(questions=questions).model_dump(mode="json"),
    )


# ── 考试导出 ──────────────────────────────────────


@router.post(
    "/ai/exam/export",
    summary="导出培训考核试卷为 Word 文档",
)
async def export_exam(body: ExamExportRequest, current_user: CurrentUser = None) -> Any:
    """将考题数据导出为格式化的 Word 文档（.docx）。

    Returns:
        StreamingResponse: Word 文档二进制流
    """
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    logger.info(
        "HR AI exam export started",
        extra={"title": body.title},
    )

    try:
        buffer = generate_exam_docx(body)
    except Exception:
        logger.exception("Failed to generate exam docx")
        raise HTTPException(
            status_code=500,
            detail="试卷文档生成失败，请检查数据格式后重试。",
        )

    # RFC 5987 编码支持中文文件名
    encoded_filename = quote(body.title)
    content_disposition = (
        f'attachment; filename="{encoded_filename}.docx"; '
        f"filename*=UTF-8''{encoded_filename}.docx"
    )

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": content_disposition,
        },
    )


# ── 笔试上传文档文本提取 ──────────────────────


@router.post(
    "/ai/exam/extract-text",
    summary="提取上传培训文档的全文（docx/doc/wps/pdf/txt/md）",
)
async def extract_exam_document_text(
    file: UploadFile,
    current_user: CurrentUser = None,
) -> Any:
    """解析上传的培训文档，返回纯文本，供 AI 笔试出题使用。"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")

    # 上传文件大小上限 20MB：防止超大文件一次性读入内存
    safe_name, content = await read_upload_secure(
        file,
        max_bytes=min(20, get_settings().MAX_UPLOAD_SIZE_MB) * 1024 * 1024,
        allowed_extensions={".docx", ".doc", ".wps", ".pdf", ".txt", ".md"},
        what="培训文档",
    )

    try:
        text = extract_document_text(safe_name, content)
    except DocumentParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    logger.info(
        "HR exam document text extracted",
        extra={"doc_name": safe_name, "text_len": len(text)},
    )
    return success_response(data={"text": text, "filename": safe_name})


# ── 笔试（选择+填空）出题 ──────────────────────


_QUESTION_PREFIX_RE = re.compile(
    r"^(根据文件内容|根据上述材料|根据以上内容|根据培训文件)[，,：:]?\s*"
)


def _strip_question_prefix(questions: list[dict[str, Any]], key: str) -> None:
    """兼容清理题目中的"根据文件内容，"等前缀（LLM 未遵循指令时兑底）。"""
    for q in questions:
        text = q.get(key) or ""
        cleaned = _QUESTION_PREFIX_RE.sub("", text)
        if cleaned != text:
            q[key] = cleaned


# ── 分批并列出题参数（HR_EXAM_* 运行时可配置，缺省即历史硬编码值） ──
_EXAM_SETTING_DEFAULTS: dict[str, str] = {
    "HR_EXAM_MAX_CONCURRENCY": "3",  # 同时进行的 LLM 出题批次数
    "HR_EXAM_QUESTIONS_PER_BATCH": "10",  # 单批题数上限
    "HR_EXAM_BATCH_TIMEOUT": "300",  # 单批 LLM 调用超时（秒）
    "HR_EXAM_BATCH_CONTENT_MAX": "20000",  # 单批素材字符上限（小文件合并阈值）
    "HR_EXAM_TOTAL_CONTENT_MAX": "120000",  # 全部素材总字符上限（沿用现状）
    "HR_EXAM_SUBMIT_RATE_LIMIT": "5",  # 每用户每分钟提交出题任务上限（防刷）
}

_MAX_QUESTIONS_PER_BATCH = 10

# 进程级全局并发信号量：按并发配置值缓存。
# 每个后台任务内不再各自创建 Semaphore，否则 N 个用户同时提交时
# LLM 总并发 = N × max_concurrency，超出供应商限流后延迟/费用被放大。
# 假定单事件循环运行（uvicorn 生产环境），与共享 httpx client 约束一致。
_global_exam_semaphores: dict[int, asyncio.Semaphore] = {}


def _get_global_exam_semaphore(max_concurrency: int) -> asyncio.Semaphore:
    """获取进程级出题并发信号量（按配置值缓存复用）。"""
    sem = _global_exam_semaphores.get(max_concurrency)
    if sem is None:
        sem = asyncio.Semaphore(max_concurrency)
        _global_exam_semaphores[max_concurrency] = sem
    return sem


async def _exam_setting(key: str) -> int:
    """读取 HR 出题运行参数（字符串转 int，缺省回退常量）。"""
    raw = await get_module_setting("hr", key, _EXAM_SETTING_DEFAULTS[key])
    try:
        return int(raw)
    except (ValueError, TypeError):
        return int(_EXAM_SETTING_DEFAULTS[key])


def _clamp_setting(value: int, min_v: int, max_v: int) -> int:
    """钳制运行参数到安全区间：配置 0/负数/超大值会导致 Semaphore 死锁或失控。"""
    return max(min_v, min(value, max_v))


def _weighted_alloc(total: int, weights: list[int]) -> list[int]:
    """将 total 道题按内容长度加权分配给各批（最大余数法，总和恒等于 total）。

    每批至少分到 floor(total * w_i / sum(w)) 道，余数依次补给小数部分最大的一批。
    若某批权重为 0（无素材），分配 0 道。
    """
    if total <= 0 or not weights:
        return [0] * len(weights)
    total_w = sum(weights)
    if total_w <= 0:
        # 全 0 权重兜底：均分给非零批（通常不会走到）
        n = len(weights)
        base, rem = divmod(total, n)
        return [base + (1 if i < rem else 0) for i in range(n)]
    raw = [total * w / total_w for w in weights]
    floor = [int(x) for x in raw]
    remaining = total - sum(floor)
    # 按小数部分从大到小补足余数
    order = sorted(range(len(weights)), key=lambda i: raw[i] - floor[i], reverse=True)
    for i in range(remaining):
        floor[order[i % len(order)]] += 1
    return floor


def _split_files_into_batches(
    files: list[dict[str, Any]],
    uploaded_content: str,
    manual_content: str,
    single: int,
    multiple: int,
    true_false: int,
    fill: int,
    max_content_per_batch: int = 20000,
    max_questions_per_batch: int = _MAX_QUESTIONS_PER_BATCH,
) -> list[dict[str, Any]]:
    """按文件分批：每批只携带本批文件的全文，题目按各批内容长度加权分配。

    返回批次列表，每批结构：
        {
            "files": [{"name", "code", "content"}, ...],  # 本批文件子集
            "uploaded": str,  # 本批附带的上传内容（默认空）
            "manual": str,  # 本批附带的手动内容（默认空）
            "single": int, "multiple": int, "true_false": int, "fill": int,
        }

    分批策略：
    - 文件按内容长度降序，贪心合并到一组，使每组素材总量 ≤ max_content_per_batch；
      单个超大文件超出上限时独立成批
      （由 build_written_generate_prompt 总上限兜底截断）。
    - uploaded_content / manual_content 各自独立成批（素材不再与文件批次重复）。
    - 各批次（含上传/手动批）按自身素材长度加权分配四种题型题数。
    """
    # 1) 文件按内容长度降序，贪心分组
    nonempty = [f for f in files if (f.get("content") or "").strip()]
    nonempty.sort(key=lambda f: len(f.get("content") or ""), reverse=True)
    file_groups: list[list[dict[str, Any]]] = []
    for f in nonempty:
        f_len = len(f.get("content") or "")
        cur_group = None
        for g in file_groups:
            group_len = sum(len(x.get("content") or "") for x in g)
            if group_len + f_len <= max_content_per_batch:
                cur_group = g
                break
        if cur_group is not None:
            cur_group.append(f)
        else:
            file_groups.append([f])

    # 2) 构建批次：每个文件组一批 + 上传内容一批 + 手动内容一批
    batches: list[dict[str, Any]] = []
    for g in file_groups:
        batches.append(
            {
                "files": g,
                "uploaded": "",
                "manual": "",
                "single": 0,
                "multiple": 0,
                "true_false": 0,
                "fill": 0,
            }
        )
    if (uploaded_content or "").strip():
        batches.append(
            {
                "files": [],
                "uploaded": uploaded_content,
                "manual": "",
                "single": 0,
                "multiple": 0,
                "true_false": 0,
                "fill": 0,
            }
        )
    if (manual_content or "").strip():
        batches.append(
            {
                "files": [],
                "uploaded": "",
                "manual": manual_content,
                "single": 0,
                "multiple": 0,
                "true_false": 0,
                "fill": 0,
            }
        )
    if not batches:
        return []

    # 3) 按素材长度加权分配题型题数
    def _batch_len(b: dict[str, Any]) -> int:
        files_len = sum(len(f.get("content") or "") for f in b["files"])
        return files_len + len(b.get("uploaded") or "") + len(b.get("manual") or "")

    weights = [_batch_len(b) for b in batches]
    singles = _weighted_alloc(single, weights)
    multiples = _weighted_alloc(multiple, weights)
    tfs = _weighted_alloc(true_false, weights)
    fills = _weighted_alloc(fill, weights)

    # 4) 每批题数不得超过单批上限：超出时按题数再拆子批
    #    文件批次：子批共享本批文件素材（文件无法按题数切分，素材量受单批上限约束）；
    #    上传/手动内容批次：内容按子批题数比例切分，避免大内容整份复制到每个子批
    #    （否则 12 万字上传内容在 2 个子批中各带全量 → 输入放大 2x）。
    out: list[dict[str, Any]] = []
    for b, s, m, t, fl in zip(batches, singles, multiples, tfs, fills):
        total_q = s + m + t + fl
        if total_q == 0:
            continue  # 分到 0 题的批跳过，不调用 LLM
        if total_q <= max_questions_per_batch:
            out.append({**b, "single": s, "multiple": m, "true_false": t, "fill": fl})
            continue
        # 拆子批：把题型依次分配到每份 ≤ max_questions_per_batch 的子批
        units = ["single"] * s + ["multiple"] * m + ["true_false"] * t + ["fill"] * fl
        sub_batches: list[dict[str, Any]] = []
        cur = {"single": 0, "multiple": 0, "true_false": 0, "fill": 0}
        q = 0
        for u in units:
            if q >= max_questions_per_batch:
                sub_batches.append(cur)
                cur = {"single": 0, "multiple": 0, "true_false": 0, "fill": 0}
                q = 0
            cur[u] += 1
            q += 1
        if q > 0:
            sub_batches.append(cur)
        # 上传/手动内容按子批题数占比切分（仅内容批切分，文件批保持整批素材）
        # 注意：cut 基于原始全长计算，循环内 uploaded 是剩余内容，
        # 不可直接取 len 再乘占比，否则后续子批内容会偏少。
        uploaded = b["uploaded"]
        manual = b["manual"]
        uploaded_total = len(uploaded)
        manual_total = len(manual)
        # 文件批拆子批：各文件内容同样按子批题数占比切分，
        # 避免超大文件（如 50 万字）整份复制到每个子批造成输入放大。
        # 最后一个子批取剩余全部内容（不按比例截断，避免内容丢失）。
        file_remaining = [f.get("content") or "" for f in b["files"]]
        for sb_idx, sb in enumerate(sub_batches):
            is_last = sb_idx == len(sub_batches) - 1
            sb_total = sb["single"] + sb["multiple"] + sb["true_false"] + sb["fill"]
            if uploaded and total_q > 0:
                cut = (
                    len(uploaded)
                    if is_last
                    else int(uploaded_total * sb_total / total_q)
                )
                sb_uploaded = uploaded[:cut]
                uploaded = uploaded[cut:]
            else:
                sb_uploaded = ""
            if manual and total_q > 0:
                cut = len(manual) if is_last else int(manual_total * sb_total / total_q)
                sb_manual = manual[:cut]
                manual = manual[cut:]
            else:
                sb_manual = ""
            # 文件内容按占比切片：每个文件取当前段，剩余内容留给后续子批
            sb_files: list[dict[str, Any]] = []
            if b["files"] and total_q > 0:
                for i, (f, rest) in enumerate(zip(b["files"], file_remaining)):
                    if is_last:
                        sb_files.append({**f, "content": rest})
                        file_remaining[i] = ""
                    else:
                        flen = len(f.get("content") or "")
                        cut = int(flen * sb_total / total_q)
                        sb_files.append({**f, "content": rest[:cut]})
                        file_remaining[i] = rest[cut:]
            else:
                sb_files = list(b["files"])
            out.append(
                {
                    "files": sb_files,
                    "uploaded": sb_uploaded,
                    "manual": sb_manual,
                    **sb,
                }
            )
    return out


def _normalize_question(text: str) -> str:
    """题目文本归一化（去空白），用于跨批去重。"""
    return re.sub(r"\s+", "", text or "")


def _dedupe_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按归一化题干去重，保留先出现的题目。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for q in questions:
        key = _normalize_question(q.get("question") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


_TF_ANSWER_MARK = {
    "√",
    "×",
    "对",
    "错",
    "正确",
    "错误",
    "true",
    "false",
    "True",
    "False",
    "T",
    "F",
}


def _sanitize_questions(
    choices: list[dict[str, Any]],
    true_falses: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """LLM 输出容错归类：把误放入 choice_questions 的判断题移回 true_false，
    并逐题按目标 Schema 校验（不合格的题目丢弃），保证 WrittenExamGenerateResponse
    Pydantic 校验不因任何单条脏数据崩溃。

    典型脏数据（实测日志）：LLM 在 choice_questions 里返回了
    {'number': 4, 'question': '...', 'answer': '√'}（无 options 的判断题）；
    以及 options 元素缺 label/text、缺少 answer 的残缺选择题。
    """
    clean_choices: list[dict[str, Any]] = []
    for q in choices:
        if not isinstance(q, dict):
            continue
        question = (q.get("question") or "").strip()
        if not question:
            continue
        opts = q.get("options")
        # 有效选择题：options 为非空列表，且逐题通过 ChoiceQuestion 校验
        if isinstance(opts, list) and opts:
            try:
                ChoiceQuestion.model_validate({**q, "number": q.get("number", 0)})
            except Exception:
                continue  # options 元素残缺/答案缺失等，直接丢弃
            clean_choices.append(q)
            continue
        # 无 options：若答案是判断标记 → 归入判断题；否则丢弃
        answer = str(q.get("answer") or "").strip()
        if answer in _TF_ANSWER_MARK:
            true_falses.append({"question": question, "answer": answer})
        # 其余无 options 且答案非判断标记的脏数据直接丢弃

    clean_tf: list[dict[str, Any]] = []
    for q in true_falses:
        if not isinstance(q, dict):
            continue
        question = (q.get("question") or "").strip()
        if not question:
            continue
        answer = str(q.get("answer") or "").strip()
        if not answer:
            continue
        try:
            TrueFalseQuestion.model_validate({**q, "number": q.get("number", 0)})
        except Exception:
            continue
        clean_tf.append({"question": question, "answer": answer})

    clean_fills: list[dict[str, Any]] = []
    for q in fills:
        if not isinstance(q, dict):
            continue
        question = (q.get("question") or "").strip()
        if not question:
            continue
        try:
            FillBlankQuestion.model_validate({**q, "number": q.get("number", 0)})
        except Exception:
            continue
        clean_fills.append({"question": question, "answer": q.get("answer") or ""})

    return clean_choices, clean_tf, clean_fills


_RETRYABLE_LLM_ERRORS = (LLMRateLimitError, httpx.TimeoutException, LLMProviderError)


@router.post(
    "/ai/exam/generate-written",
    summary="AI 生成笔试培训考核试卷（选择题+填空题）",
    response_model=WrittenExamJobSubmitResponse,
)
async def generate_written_exam(
    body: WrittenExamGenerateRequest,
    current_user: CurrentUser = None,
) -> Any:
    """根据培训材料文件内容 + 上传附件 + 手动粘贴，
    提交后台任务生成单选题、多选题和填空题。

    按文件分批（每批只携带本批文件素材，题目按内容长度加权分配），
    批间实现并发限流与指数退避重试；任务提交后立即返回 job_id，
    通过 GET /ai/exam/generate-written/{job_id} 轮询进度与结果。
    """
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")

    # 提交节流：每用户每分钟最多 HR_EXAM_SUBMIT_RATE_LIMIT 次（防刷消耗 LLM token）。
    # Redis 不可用时放行（节流失效不阻断出题），仅记录告警。
    rate_limit = await _exam_setting("HR_EXAM_SUBMIT_RATE_LIMIT")
    try:
        submit_count = await cache_incr(f"rate:hr:exam:submit:{current_user.id}", ex=60)
        if submit_count > rate_limit:
            raise HTTPException(
                status_code=429,
                detail=f"提交过于频繁，每分钟最多提交 {rate_limit} 次，请稍后再试。",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("HR exam submit rate check skipped: %s", e)

    req_choice = body.single_choice_count + body.multiple_choice_count
    if req_choice + body.true_false_count + body.fill_blank_count <= 0:
        raise HTTPException(status_code=400, detail="请至少配置一种题型的数量")

    # 空素材校验：文件/上传/手动全部无有效内容时直接拒绝，
    # 避免后台任务"空转成功"返回 0 题 + shortfall 的误导结果
    total_material = sum(len(f.content or "") for f in body.files)
    total_material += len(body.uploaded_content or "")
    total_material += len(body.manual_content or "")
    if total_material == 0:
        raise HTTPException(
            status_code=400,
            detail="请至少提供一份培训材料内容（文件/上传附件/手动粘贴）",
        )

    max_concurrency = _clamp_setting(
        await _exam_setting("HR_EXAM_MAX_CONCURRENCY"), 1, 20
    )
    questions_per_batch = _clamp_setting(
        await _exam_setting("HR_EXAM_QUESTIONS_PER_BATCH"), 1, 50
    )
    batch_timeout = _clamp_setting(
        await _exam_setting("HR_EXAM_BATCH_TIMEOUT"), 30, 600
    )
    batch_content_max = _clamp_setting(
        await _exam_setting("HR_EXAM_BATCH_CONTENT_MAX"), 1000, 100_000
    )
    total_content_max = _clamp_setting(
        await _exam_setting("HR_EXAM_TOTAL_CONTENT_MAX"), 10_000, 500_000
    )

    files_dump = [f.model_dump() for f in body.files]

    logger.info(
        "HR written exam generation submitted",
        extra={
            "file_count": len(body.files),
            "single_choice": body.single_choice_count,
            "multiple_choice": body.multiple_choice_count,
            "true_false": body.true_false_count,
            "fill_blank": body.fill_blank_count,
            "max_concurrency": max_concurrency,
        },
    )

    async def _run_written_generation(**kwargs: Any) -> dict[str, Any]:
        """后台任务：按文件分批并列出题，返回已后处理的题目数据。"""
        job_id: str = kwargs["_job_id"]
        files: list[dict[str, Any]] = kwargs["files"]
        uploaded_content: str = kwargs["uploaded_content"]
        manual_content: str = kwargs["manual_content"]

        batches = _split_files_into_batches(
            files,
            uploaded_content,
            manual_content,
            kwargs["single_choice_count"],
            kwargs["multiple_choice_count"],
            kwargs["true_false_count"],
            kwargs["fill_blank_count"],
            max_content_per_batch=batch_content_max,
            max_questions_per_batch=questions_per_batch,
        )
        batch_count = len(batches)
        logger.info(
            "HR written exam batches prepared",
            extra={"job_id": job_id, "batch_count": batch_count},
        )

        # 并发限流：进程级全局信号量，跨任务共享（总 LLM 并发 ≤ 配置值）
        semaphore = _get_global_exam_semaphore(max_concurrency)

        async def _gen_batch(idx: int, b: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                await update_job_progress(
                    job_id, f"正在生成第 {idx + 1}/{batch_count} 批题目…"
                )
                prompt = build_written_generate_prompt(
                    files=b["files"],
                    uploaded_content=b["uploaded"],
                    manual_content=b["manual"],
                    single_choice_count=b["single"],
                    multiple_choice_count=b["multiple"],
                    fill_blank_count=b["fill"],
                    true_false_count=b["true_false"],
                    # 素材总上限走配置（HR_EXAM_TOTAL_CONTENT_MAX），而非硬编码
                    total_content_max=total_content_max,
                )
                # 各批 temperature 递增，降低并行批次间的题目重复率
                temperature = round(min(0.3 + idx * 0.1, 0.7), 2)
                # 动态 expected_keys：只校验本批实际请求的题型键。
                # 若某批只要填空题，LLM 只返回 fill_blank_questions，
                # 硬编码三个键会导致 expected_keys 校验误报整批失败。
                expected = []
                if b["single"] or b["multiple"]:
                    expected.append("choice_questions")
                if b["true_false"]:
                    expected.append("true_false_questions")
                if b["fill"]:
                    expected.append("fill_blank_questions")
                return await llm_client.chat_json(
                    [{"role": "user", "content": prompt}],
                    expected_keys=expected or None,
                    temperature=temperature,
                )

        async def _gen_batch_with_retry(idx: int, b: dict[str, Any]) -> dict[str, Any]:
            """指数退避重试：LLM 限流/超时/5xx 重试至多 2 次
            （退避 1s/2s，429 额外 +3s）；LLMOutputError 等格式类错误不重试。"""
            last_err: Exception | None = None
            for attempt in range(3):
                try:
                    return await asyncio.wait_for(
                        _gen_batch(idx, b), timeout=batch_timeout
                    )
                except (TimeoutError, *_RETRYABLE_LLM_ERRORS) as e:
                    last_err = e
                    if attempt >= 2:
                        break
                    wait = [1, 2][attempt]
                    if isinstance(e, LLMRateLimitError):
                        wait += 3
                    logger.warning(
                        "HR written exam batch %s failed (attempt %s), "
                        "retrying in %ss: %s",
                        idx,
                        attempt + 1,
                        wait,
                        e,
                    )
                    await asyncio.sleep(wait)
            raise last_err  # type: ignore[misc]

        results = await asyncio.gather(
            *[_gen_batch_with_retry(i, b) for i, b in enumerate(batches)],
            return_exceptions=True,
        )

        # 收集成功批次的题目。
        # 注意用 BaseException 而非 Exception 判断：asyncio.CancelledError
        # 继承自 BaseException（任务被取消时 gather 会将其作为结果返回），
        # 若按 Exception 判断会落入 else 分支对非 dict 调用 .get() 崩溃。
        choices: list[dict[str, Any]] = []
        true_falses: list[dict[str, Any]] = []
        fills: list[dict[str, Any]] = []
        failed: list[BaseException] = []
        for r in results:
            if isinstance(r, BaseException):
                failed.append(r)
                logger.error("HR written exam batch failed: %s", r)
                continue
            choices.extend(r.get("choice_questions", []))
            true_falses.extend(r.get("true_false_questions", []))
            fills.extend(r.get("fill_blank_questions", []))

        # 任务被取消（如优雅停机）：保持取消语义，不再继续返回结果
        if any(isinstance(e, asyncio.CancelledError) for e in failed):
            raise asyncio.CancelledError

        # 全部批次失败：按首个异常类型映射错误信息
        if failed and not choices and not true_falses and not fills:
            first = failed[0]
            if isinstance(first, (TimeoutError, httpx.TimeoutException)):
                raise HTTPException(status_code=504, detail="AI 出题超时，请稍后重试。")
            if isinstance(first, LLMRateLimitError):
                raise HTTPException(
                    status_code=429, detail="AI 服务当前请求过于频繁，请稍后再试。"
                )
            if isinstance(first, LLMOutputError):
                raise HTTPException(
                    status_code=422,
                    detail="AI 生成的考题格式不正确，请重试。",
                )
            raise HTTPException(
                status_code=503, detail="AI 服务暂时不可用，请稍后重试。"
            )

        req_choice = kwargs["single_choice_count"] + kwargs["multiple_choice_count"]
        # LLM 输出容错归类：把误放入 choice_questions 的判断题（√/× 答案、无 options）
        # 移回 true_false；过滤无题干/无答案/无效选项的脏数据，避免 Response 校验崩溃
        choices, true_falses, fills = _sanitize_questions(choices, true_falses, fills)
        # 跨批去重 + 重排题号 + 清理前缀 + 按请求数量截断（LLM 可能多生成）
        choices = _dedupe_questions(choices)[:req_choice]
        true_falses = _dedupe_questions(true_falses)[: kwargs["true_false_count"]]
        fills = _dedupe_questions(fills)[: kwargs["fill_blank_count"]]
        for i, q in enumerate(choices, start=1):
            q["number"] = i
        for i, q in enumerate(true_falses, start=1):
            q["number"] = i
        for i, q in enumerate(fills, start=1):
            q["number"] = i
        _strip_question_prefix(choices, "question")
        _strip_question_prefix(true_falses, "question")
        _strip_question_prefix(fills, "question")

        shortfall = (
            len(choices) < req_choice
            or len(true_falses) < kwargs["true_false_count"]
            or len(fills) < kwargs["fill_blank_count"]
        )

        logger.info(
            "HR written exam generated",
            extra={
                "job_id": job_id,
                "choice_count": len(choices),
                "true_false_count": len(true_falses),
                "fill_count": len(fills),
                "failed_batches": len(failed),
                "shortfall": shortfall,
            },
        )

        return WrittenExamGenerateResponse(
            choice_questions=choices,
            true_false_questions=true_falses,
            fill_blank_questions=fills,
            shortfall=shortfall,
        ).model_dump(mode="json")

    job_id = f"hr:exam:written:{uuid4().hex[:12]}"
    await submit_job(
        _run_written_generation,
        task_id=job_id,
        ttl=600,
        # 记录任务归属用户，轮询接口据此校验，防止 IDOR 读取他人试卷
        status_extra={"owner": str(current_user.id)},
        _job_id=job_id,
        files=files_dump,
        uploaded_content=body.uploaded_content,
        manual_content=body.manual_content,
        single_choice_count=body.single_choice_count,
        multiple_choice_count=body.multiple_choice_count,
        true_false_count=body.true_false_count,
        fill_blank_count=body.fill_blank_count,
    )

    return success_response(
        data=WrittenExamJobSubmitResponse(job_id=job_id).model_dump(mode="json")
    )


@router.get(
    "/ai/exam/generate-written/{job_id}",
    summary="查询 AI 笔试出题任务进度与结果",
    response_model=WrittenExamJobStatusResponse,
)
async def get_written_exam_job(job_id: str, current_user: CurrentUser = None) -> Any:
    """轮询 AI 笔试出题后台任务：返回 running 进度 / completed 结果 / failed 错误。"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")

    status = await get_job_status(job_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail="出题任务不存在或已过期，请重新提交出题。",
        )

    # 归属校验：任务记录的 owner 与当前用户不一致时视为不存在（防 IDOR）
    if status.get("owner") and status.get("owner") != str(current_user.id):
        raise HTTPException(
            status_code=404,
            detail="出题任务不存在或已过期，请重新提交出题。",
        )

    state = status.get("state", "running")
    progress = status.get("progress") or ""
    if state == "completed":
        result = status.get("result")
        return success_response(
            data=WrittenExamJobStatusResponse(
                state="completed",
                progress="完成",
                result=result,
            ).model_dump(mode="json"),
        )
    if state == "failed":
        err_detail = status.get("progress") or status.get("error") or "出题失败"
        return success_response(
            data=WrittenExamJobStatusResponse(
                state="failed",
                progress=err_detail,
                # 与 progress 同步填充 error，保证前端两种取值方式都能拿到错误信息
                error=err_detail,
            ).model_dump(mode="json"),
        )
    return success_response(
        data=WrittenExamJobStatusResponse(
            state="running", progress=progress
        ).model_dump(mode="json"),
    )


# ── 笔试（选择+填空）导出 ──────────────────────


@router.post(
    "/ai/exam/export-written",
    summary="导出笔试培训考核资料（试卷+答案分离 zip）",
)
async def export_written_exam(
    body: WrittenExamExportRequest,
    current_user: CurrentUser = None,
) -> Any:
    """将笔试考题数据导出为 zip：内含试卷卷（无答案）与答案卷两份 docx。"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")

    logger.info(
        "HR written exam export started",
        extra={"title": body.title},
    )

    try:
        buffer = generate_written_exam_zip(body)
    except Exception:
        logger.exception("Failed to generate written exam zip")
        raise HTTPException(
            status_code=500,
            detail="试卷文档生成失败，请检查数据格式后重试。",
        )

    encoded_filename = quote(f"{body.title}_试卷与答案")
    content_disposition = (
        f'attachment; filename="{encoded_filename}.zip"; '
        f"filename*=UTF-8''{encoded_filename}.zip"
    )

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition,
        },
    )
