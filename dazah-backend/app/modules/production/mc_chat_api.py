"""MC 霉酚酸 - AI 多轮对话 API

POST /mc/chat/send — 发送消息，SSE 流式返回（自动注入批次追溯数据）
GET  /mc/chat/history — 获取会话历史消息
"""

import json
import logging

from fastapi import Depends, Query, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.llm import get_config
from app.core.response import error_response, success_response
from app.modules.production.ai_analysis_models import AiAnalysis
from app.modules.production.mc_lineage_api import (
    STAGE_LABELS,
    lineage_trace,
    lineage_yield_distribution,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])

CHAT_SYSTEM_PROMPT = """你是丽珠制药 201 二车间的 MC（霉酚酸）生产工艺助手。

你了解以下工段：粗提(发酵液→提炼→分罐→钠化→酸化)、提取(萃取→湿粉)、
        二次精制(结晶→干粉MC-F2)、混粉杂质计算、QC 入库。

你可以帮助：
1. 解答工艺问题（收率、杂质、参数范围）
2. 解读批次追溯结果（血链表关系、上下游依赖）
3. 解释 AI 分析结论（收率异常原因、RRT 杂质控制建议）
4. 回答通用的生产管理问题

注意：给具体的、可操作的建议。用中文回答。"""


def _build_chat_prompt(
    history: list[dict],
    user_msg: str,
    batch_no: str,
    stage: str,
    trace_context: str,
) -> list[dict]:
    """构建 LLM 消息列表，注入批次追溯数据"""
    stage_label = STAGE_LABELS.get(stage, stage)
    system = CHAT_SYSTEM_PROMPT

    # 注入当前批次的追溯数据
    if batch_no and trace_context:
        system += f"\n\n当前关注批次: {batch_no}（{stage_label}）\n{trace_context}"

    messages: list[dict] = [{"role": "system", "content": system}]

    # 注入历史对话（最近10轮）
    recent = [h for h in history if h.get("role") in ("user", "assistant")][-20:]
    for h in recent:
        content = h.get("llm_response") or h.get("summary", "")
        messages.append({"role": h["role"], "content": content[:2000]})

    messages.append({"role": "user", "content": user_msg})
    return messages


async def _gather_trace_context(
    batch_no: str, stage: str, session: AsyncSession
) -> str:
    """收集批次的追溯和收率数据，拼成上下文文本"""
    parts = []
    try:
        # 追溯链路
        trace_resp = await lineage_trace(
            batch_no=batch_no, stage=stage, include_siblings=True, session=session
        )
        trace_data = json.loads(trace_resp.body).get("data", {})
        stages = trace_data.get("stages", [])
        cumulative_yield = trace_data.get("cumulative_yield", 0)
        max_loss_stage = trace_data.get("max_loss_stage")

        if stages:
            parts.append(f"=== 批次追溯链路 (累计收率 {cumulative_yield}%) ===")
            for sg in stages:
                for n in sg.get("nodes", []):
                    sib = " [同级]" if n.get("is_sibling") else ""
                    tgt = " ← 当前" if n.get("batch_no") == batch_no else ""
                    detail = n.get("detail", "")
                    yr = n.get("yield_rate")
                    yr_str = f" 收率{yr}%" if yr and yr > 0 else ""
                    parts.append(
                        f"  {sg['label']} {n['batch_no']}{yr_str}{sib}{tgt} {detail}"
                    )
            if max_loss_stage:
                parts.append(f"最大损失工段: {max_loss_stage}")

        # 收率分布
        try:
            dist_resp = await lineage_yield_distribution(session=session)
            dist_data = json.loads(dist_resp.body).get("data", [])
            if dist_data:
                parts.append("\n=== 工段收率统计 (min / Q1 / 中位 / Q3 / max) ===")
                for d in dist_data:
                    s = STAGE_LABELS.get(d.get("stage"), d.get("stage", ""))
                    parts.append(
                        f"  {s}: min={d.get('min')} Q1={d.get('q1')} 中位={d.get('median')} Q3={d.get('q3')} max={d.get('max')}"  # noqa: E501
                    )
        except Exception:
            pass

        # 如果是混粉/QC工段，查 RRT 杂质
        real_stage = trace_data.get("target_stage", stage)
        if real_stage in ("blending", "qc", "single_batch_blend", "single_batch_qc"):
            for sg in stages:
                if sg.get("stage") != "blending":
                    continue
                for n in sg.get("nodes", []):
                    bn = n.get("batch_no", "")
                    if not bn:
                        continue
                    row = (
                        await session.execute(
                            text("""
                        SELECT rrt_053, rrt_0755, rrt_094_096, rrt_103_106, rrt_201,
        total_impurity
                        FROM production.blending_records WHERE batch_no = :bn AND
        is_deleted = false
                    """),
                            {"bn": bn},
                        )
                    ).fetchone()
                    if not row:
                        continue
                    imp_parts = []
                    for key in (
                        "rrt_053",
                        "rrt_0755",
                        "rrt_094_096",
                        "rrt_103_106",
                        "rrt_201",
                    ):
                        val = getattr(row, key, None)
                        if val is not None:
                            imp_parts.append(f"{key}={round(float(val), 4)}%")
                    ti = getattr(row, "total_impurity", None)
                    if ti is not None:
                        imp_parts.append(f"总杂={round(float(ti), 4)}%")
                    if imp_parts:
                        parts.append(
                            f"\n=== RRT 杂质 ({bn}) ===\n  {', '.join(imp_parts)}"
                        )

    except Exception as e:
        logger.warning(f"收集批次上下文失败: {e}")
        parts.append("(批次数据暂时无法获取)")

    return "\n".join(parts)


@router.post("/mc/chat/send", summary="发送对话消息（SSE流式）")
async def chat_send(request: Request, session: AsyncSession = Depends(get_db)):
    """发送消息，返回 SSE 流"""
    body = await request.json()
    sid = body.get("session_id", "").strip()
    message = body.get("message", "").strip()

    if not sid:
        return error_response("缺少 session_id")
    if not message:
        return error_response("消息不能为空")

    # 1. 查历史消息
    result = await session.execute(
        select(AiAnalysis)
        .where(AiAnalysis.session_id == sid, AiAnalysis.is_deleted.is_(False))
        .order_by(AiAnalysis.message_seq.asc())
    )
    history_rows = result.scalars().all()

    if not history_rows:
        return error_response("会话不存在")

    first = history_rows[0]  # seq=0 的分析报告
    batch_no = first.batch_no
    stage = first.stage
    last_seq = max(r.message_seq for r in history_rows)

    # 2. 存用户消息
    user_msg = AiAnalysis(
        session_id=sid,
        batch_no=batch_no,
        stage=stage,
        message_seq=last_seq + 1,
        role="user",
        summary=message[:500],
        llm_response=message,
        created_by=first.created_by or "AI对话",
    )
    session.add(user_msg)
    await session.commit()

    # 3. 构建历史上下文
    history_dicts = [
        {"role": r.role, "llm_response": r.llm_response, "summary": r.summary}
        for r in history_rows
    ]

    # 4. 收集批次上下文 + 构建 prompt
    trace_context = await _gather_trace_context(batch_no, stage, session)
    messages = _build_chat_prompt(
        history_dicts, message, batch_no, stage, trace_context
    )

    # 5. SSE 流
    async def generate():
        full_text = ""
        llm_error = ""
        try:
            cfg = await get_config("text")
            client = AsyncOpenAI(
                base_url=cfg.api_base_url or "https://newapi.livzon.cn/v1",
                api_key=cfg.api_key or "",
            )
            stream = await client.chat.completions.create(
                model=cfg.model_name or "deepseek-v4-pro",
                messages=messages,
                temperature=0.7,
                max_tokens=1500,
                timeout=90,
                stream=True,
                extra_body={"thinking": {"type": "disabled"}},
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta:
                    token = delta.content or ""
                    if token:
                        full_text += token
                        yield f"data: {json.dumps({'token': token})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            llm_error = str(e)
            logger.error(f"LLM 流式失败: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # 5. 存 AI 回复
        try:
            ai_msg = AiAnalysis(
                session_id=sid,
                batch_no=batch_no,
                stage=stage,
                message_seq=last_seq + 2,
                role="assistant",
                summary=full_text[:500]
                if full_text
                else (f"分析失败: {llm_error}" if llm_error else ""),
                llm_response=full_text or "",
                llm_prompt=json.dumps(messages, ensure_ascii=False),
                model_used=cfg.model_name or "deepseek-v4-pro",
                created_by=first.created_by or "AI对话",
            )
            session.add(ai_msg)
            await session.commit()
        except Exception as e2:
            logger.error(f"存 AI 回复失败: {e2}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/mc/chat/history", summary="获取会话历史消息")
async def chat_history(
    session_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    """获取指定会话的全部消息"""
    result = await session.execute(
        select(AiAnalysis)
        .where(AiAnalysis.session_id == session_id, AiAnalysis.is_deleted.is_(False))
        .order_by(AiAnalysis.message_seq.asc())
    )
    rows = result.scalars().all()

    messages = []
    for r in rows:
        content = r.llm_response
        if r.role == "system":
            content = {
                "summary": r.summary,
                "anomalies": r.anomalies,
                "causes": r.causes,
                "suggestions": r.suggestions,
                "severity": r.severity,
                "analysis_text": r.llm_response,
            }
        messages.append(
            {
                "id": str(r.id),
                "session_id": r.session_id,
                "seq": r.message_seq,
                "role": r.role,
                "content": content,
                "created_at": str(r.created_at) if r.created_at else None,
            }
        )

    return success_response(data={"session_id": session_id, "messages": messages})
