"""FA 苯丙氨酸 - AI 多轮对话 API

POST /fa/chat/send — 发送消息，SSE 流式返回（自动注入批次数据）
GET  /fa/chat/history — 获取会话历史消息
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
from app.modules.production.fa_lineage_api import FA_STAGE_LABELS
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])

FA_CHAT_SYSTEM_PROMPT = """你是丽珠制药 203 车间的 FA（L-苯丙氨酸）生产工艺助手。

你了解以下工段：发酵放罐(菌种培养→发酵液→放罐)、酸化过滤(pH调节→酸化→膜过滤)、一次脱色(活性炭脱色→板框过滤)、脱色离心(二次脱色→离心)。

对话风格：
- 像车间老师傅一样直接说事，不要先讲一堆分析思路
- 不要用"我来拆解""首先我们需要理解"这类开场白，直奔答案
- 不要用 markdown 格式（##、**、- 列表等），用自然段落
- 给具体的、可操作的建议，别泛泛而谈
- 用中文回答"""


def _build_chat_prompt(
    history: list[dict],
    user_msg: str,
    batch_no: str,
    stage: str,
    trace_context: str,
) -> list[dict]:
    """构建 LLM 消息列表，注入批次数据"""
    stage_label = FA_STAGE_LABELS.get(stage, stage)
    system = FA_CHAT_SYSTEM_PROMPT

    if batch_no and trace_context:
        system += f"\n\n当前关注批次: {batch_no}（{stage_label}）\n{trace_context}"

    messages: list[dict] = [{"role": "system", "content": system}]

    recent = [h for h in history if h.get("role") in ("user", "assistant")][-20:]
    for h in recent:
        content = h.get("llm_response") or h.get("summary", "")
        messages.append({"role": h["role"], "content": content[:2000]})

    messages.append({"role": "user", "content": user_msg})
    return messages


async def _gather_fa_context(batch_no: str, stage: str, session: AsyncSession) -> str:
    """收集 FA 批次的追溯、收率统计和生产数据，拼成上下文文本（参照 MC 模式）"""
    from app.modules.production.fa_ai_analysis_api import _get_trace_data

    parts = []

    # ── 1. 追溯链路 + 收率数据 ──
    try:
        # BFS 追踪上下游
        sibling_sql = """
            SELECT bl.upstream_type, bl.upstream_batch, bl.quantity
            FROM production.fa_batch_lineage bl
            WHERE bl.downstream_batch = :batch AND bl.downstream_type = :stage
        """
        downstream_sql = """
            SELECT bl.downstream_type, bl.downstream_batch, bl.quantity
            FROM production.fa_batch_lineage bl
            WHERE bl.upstream_batch = :batch AND bl.upstream_type = :stage
        """

        # 收集所有相关批次
        all_batches: list[
            tuple[str, str, float | None]
        ] = []  # (stage, batch_no, quantity)

        # upstream BFS
        cur = [(batch_no, stage)]
        seen = {(batch_no, stage)}
        while cur:
            nxt = []
            for cb, cs in cur:
                rows = (
                    await session.execute(text(sibling_sql), {"batch": cb, "stage": cs})
                ).fetchall()
                for r in rows:
                    k = (r.upstream_batch, r.upstream_type)
                    if k not in seen:
                        seen.add(k)
                        qty = float(r.quantity) if r.quantity else None
                        all_batches.append((r.upstream_type, r.upstream_batch, qty))
                        nxt.append(k)
            cur = nxt

        # downstream BFS
        cur = [(batch_no, stage)]
        seen_dn = {(batch_no, stage)}
        while cur:
            nxt = []
            for cb, cs in cur:
                rows = (
                    await session.execute(
                        text(downstream_sql), {"batch": cb, "stage": cs}
                    )
                ).fetchall()
                for r in rows:
                    k = (r.downstream_batch, r.downstream_type)
                    if k not in seen_dn:
                        seen_dn.add(k)
                        qty = float(r.quantity) if r.quantity else None
                        all_batches.append((r.downstream_type, r.downstream_batch, qty))
                        nxt.append(k)
            cur = nxt

        # 按工段排序
        stage_order = {
            "fermentation": 0,
            "acidification": 1,
            "decolor1": 2,
            "decolor_centrifuge": 3,
        }
        all_batches.sort(key=lambda x: stage_order.get(x[0], 99))

        # 收集每个批次的收率信息
        batch_lines: list[str] = []
        for s, bn, qty in all_batches:
            label = FA_STAGE_LABELS.get(s, s)
            is_target = " ← 当前" if bn == batch_no else ""
            detail_parts = []
            if qty and qty > 0:
                detail_parts.append(f"{qty:.0f}kg")

            # 查收率
            if s == "acidification":
                ar = (
                    await session.execute(
                        text(
                            'SELECT "批收率" FROM production.fa_acidification_records WHERE "批号" = :bn LIMIT 1'  # noqa: E501
                        ),
                        {"bn": bn},
                    )
                ).fetchone()
                if ar and ar[0]:
                    try:
                        yr_str = str(ar[0]).replace("%", "")
                        yr = float(yr_str)
                        if yr < 2:
                            yr *= 100
                        detail_parts.append(f"收率{yr:.1f}%")
                    except (ValueError, TypeError):
                        pass
            elif s == "decolor_centrifuge":
                cr = (
                    await session.execute(
                        text(
                            'SELECT "收率" FROM production.fa_decolor_centrifuge_records WHERE "批号" = :bn ORDER BY "批号" LIMIT 1'  # noqa: E501
                        ),
                        {"bn": bn},
                    )
                ).fetchone()
                if cr and cr[0]:
                    try:
                        yr = float(cr[0])
                        if yr < 2:
                            yr *= 100
                        detail_parts.append(f"收率{yr:.1f}%")
                    except (ValueError, TypeError):
                        pass
            elif s == "fermentation":
                fr = (
                    await session.execute(
                        text(
                            'SELECT "汇总总量_kg" FROM production.fa_fermentation_batches WHERE "发酵罐号" = :bn'  # noqa: E501
                        ),
                        {"bn": bn},
                    )
                ).fetchone()
                if fr and fr[0]:
                    detail_parts.append(f"产量{float(fr[0]):.0f}kg")

            detail = ", ".join(detail_parts)
            batch_lines.append(f"  {label} {bn} {detail}{is_target}")

        if batch_lines:
            parts.append("=== 批次追溯链路 ===")
            parts.extend(batch_lines)

    except Exception as e:
        logger.warning(f"FA 追溯链路收集失败: {e}")

    # ── 2. 工段收率统计 ──
    try:
        stats_parts = []
        # 酸化收率统计
        acid_stats = (
            await session.execute(
                text("""
            SELECT ROUND(MIN(NULLIF(REGEXP_REPLACE("批收率", '%', '', 'g'),
        '')::numeric)::numeric, 1),
                   ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY
        NULLIF(REGEXP_REPLACE("批收率", '%', '', 'g'), '')::numeric)::numeric, 1),
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
        NULLIF(REGEXP_REPLACE("批收率", '%', '', 'g'), '')::numeric)::numeric, 1),
                   ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY
        NULLIF(REGEXP_REPLACE("批收率", '%', '', 'g'), '')::numeric)::numeric, 1),
                   ROUND(MAX(NULLIF(REGEXP_REPLACE("批收率", '%', '', 'g'),
        '')::numeric)::numeric, 1)
            FROM production.fa_acidification_records
        """)
            )
        ).fetchone()
        if acid_stats and acid_stats[0]:
            stats_parts.append(
                f"  酸化收率: min={acid_stats[0]} Q1={acid_stats[1]} 中位={acid_stats[2]} Q3={acid_stats[3]} max={acid_stats[4]}%"  # noqa: E501
            )

        # 离心收率统计
        cent_stats = (
            await session.execute(
                text("""
            SELECT ROUND(MIN(CASE WHEN "收率"::numeric < 2 THEN "收率"::numeric *
        100 ELSE
        "收率"::numeric END)::numeric, 1),
                   ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY CASE WHEN
        "收率"::numeric < 2 THEN "收率"::numeric * 100 ELSE "收率"::numeric
        END)::numeric, 1),
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CASE WHEN
        "收率"::numeric < 2 THEN "收率"::numeric * 100 ELSE "收率"::numeric
        END)::numeric, 1),
                   ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY CASE WHEN
        "收率"::numeric < 2 THEN "收率"::numeric * 100 ELSE "收率"::numeric
        END)::numeric, 1),
                   ROUND(MAX(CASE WHEN "收率"::numeric < 2 THEN "收率"::numeric *
        100 ELSE
        "收率"::numeric END)::numeric, 1)
            FROM production.fa_decolor_centrifuge_records WHERE "收率" IS NOT NULL
        """)
            )
        ).fetchone()
        if cent_stats and cent_stats[0]:
            stats_parts.append(
                f"  离心收率: min={cent_stats[0]} Q1={cent_stats[1]} 中位={cent_stats[2]} Q3={cent_stats[3]} max={cent_stats[4]}%"  # noqa: E501
            )

        # 电导统计
        cond_stats = (
            await session.execute(
                text("""
            SELECT ROUND(AVG("电导_uscm")::numeric, 0),
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
        "电导_uscm")::numeric, 0)
            FROM production.fa_fermentation_batches
        """)
            )
        ).fetchone()
        if cond_stats and cond_stats[0]:
            stats_parts.append(
                f"  电导(us/cm): 均值={cond_stats[0]} 中位={cond_stats[1]}"
            )

        if stats_parts:
            parts.append("\n=== 工段收率与参数统计 (全量) ===")
            parts.extend(stats_parts)
    except Exception as e:
        logger.warning(f"FA 收率统计收集失败: {e}")

    # ── 3. 批次详细生产数据 ──
    try:
        batch_data, _stats_data = await _get_trace_data(session, batch_no, stage)
        if batch_data:
            parts.append("\n=== 批次详细生产数据 ===")
            parts.append(batch_data)
    except Exception as e:
        logger.warning(f"FA 收集批次详细数据失败: {e}")
        parts.append("(批次数据暂时无法获取)")

    return "\n".join(parts)


@router.post("/fa/chat/send", summary="发送对话消息（SSE流式）")
async def fa_chat_send(request: Request, session: AsyncSession = Depends(get_db)):
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

    first = history_rows[0]
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
    trace_context = await _gather_fa_context(batch_no, stage, session)
    messages = _build_chat_prompt(
        history_dicts, message, batch_no, stage, trace_context
    )

    # 5. SSE 流
    async def generate():
        full_text = ""
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
            logger.error(f"FA LLM 流式失败: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # 6. 存 AI 回复
        try:
            ai_msg = AiAnalysis(
                session_id=sid,
                batch_no=batch_no,
                stage=stage,
                message_seq=last_seq + 2,
                role="assistant",
                summary=full_text[:500] if full_text else "",
                llm_response=full_text or "",
                llm_prompt=json.dumps(messages, ensure_ascii=False),
                model_used=cfg.model_name or "deepseek-v4-pro",
                created_by=first.created_by or "AI对话",
            )
            session.add(ai_msg)
            await session.commit()
        except Exception as e2:
            logger.error(f"FA 存 AI 回复失败: {e2}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/fa/chat/history", summary="获取会话历史消息")
async def fa_chat_history(
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
