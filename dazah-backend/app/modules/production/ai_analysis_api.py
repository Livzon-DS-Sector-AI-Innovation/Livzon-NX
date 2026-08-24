"""MC 霉酚酸 - AI 分析 API"""

import json
import logging
from datetime import date

from fastapi import Depends, Query
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.llm import get_config
from app.core.response import success_response
from app.modules.production.ai_analysis_models import AiAnalysis
from app.modules.production.mc_lineage_api import (
    STAGE_LABELS,
    lineage_trace,
    lineage_yield_distribution,
)
from app.modules.production.mc_yield_anomaly_detector import (
    _compute_stage_iqr,
    judge_anomaly_severity,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])


async def _get_node_batch_date(
    session: AsyncSession, stage: str, batch_no: str
) -> date | None:
    """查询某个节点的生产日期，用于移动窗口 IQR 计算"""
    if stage in ("sub_tank", "crude_product"):
        row = (
            await session.execute(
                text(
                    "SELECT rb.produce_date FROM production.sub_tank_records st "
                    "JOIN production.refining_batches rb ON rb.batch_no = st.parent_batch AND rb.is_deleted = false "  # noqa: E501
                    "WHERE st.batch_no = :bn AND st.is_deleted = false"
                ),
                {"bn": batch_no},
            )
        ).fetchone()
        return row.produce_date if row else None
    elif stage == "extraction":
        row = (
            await session.execute(
                text(
                    "SELECT extract_date FROM production.extraction_records "
                    "WHERE batch_no = :bn AND is_deleted = false"
                ),
                {"bn": batch_no},
            )
        ).fetchone()
        return row.extract_date if row else None
    elif stage == "refinement":
        row = (
            await session.execute(
                text(
                    "SELECT input_date FROM production.mc_refinement_records "
                    "WHERE batch_no = :bn AND is_deleted = false"
                ),
                {"bn": batch_no},
            )
        ).fetchone()
        return row.input_date if row else None
    return None


async def _detect_yield_anomalies(
    session: AsyncSession,
    stages: list[dict],
) -> list[dict]:
    """用 3 月移动窗口 IQR 检测各节点的收率异常（替代旧的固定阈值法）"""
    anomalies = []
    for sg in stages:
        stage_name = sg.get("stage")
        # 只检测有收率数据的工段
        if stage_name not in ("sub_tank", "extraction", "refinement", "crude_product"):
            continue
        for n in sg.get("nodes", []):
            yr = n.get("yield_rate")
            bn = n.get("batch_no")
            if not yr or yr <= 0 or not bn:
                continue
            try:
                batch_date = await _get_node_batch_date(session, stage_name, bn)
                iqr = await _compute_stage_iqr(session, stage_name, batch_date)
                if iqr["n"] < 5:
                    continue
                sev = judge_anomaly_severity(yr, iqr["median"], iqr["iqr"])
                if sev is None:
                    continue
                direction = "低于" if yr < iqr["median"] else "高于"
                diff = abs(yr - iqr["median"])
                anomalies.append(
                    {
                        "stage": stage_name,
                        "batch_no": bn,
                        "metric": "yield_rate",
                        "value": round(yr, 1),
                        "benchmark": round(iqr["median"], 1),
                        "severity": sev,
                        "detail": f"{direction}移动窗口中位数{diff:.1f}个百分点(IQR={iqr['iqr']})",  # noqa: E501
                    }
                )
            except Exception:
                logger.exception(f"移动IQR检测失败 {stage_name}/{bn}")
    return anomalies


@router.get("/mc/lineage/ai-analysis", summary="AI 分析追溯链路")
async def ai_analyze(
    batch_no: str = Query(...),
    stage: str = Query(...),
    include_siblings: bool = Query(True),
    session: AsyncSession = Depends(get_db),
):
    # 1. trace
    trace_resp = await lineage_trace(
        batch_no=batch_no,
        stage=stage,
        include_siblings=include_siblings,
        session=session,
    )
    trace_data = json.loads(trace_resp.body).get("data", {})
    stages = trace_data.get("stages", [])
    cumulative_yield = trace_data.get("cumulative_yield", 100)
    max_loss_stage = trace_data.get("max_loss_stage")
    real_stage = trace_data.get("target_stage", stage)

    # 2. yield dist
    dist_resp = await lineage_yield_distribution(session=session)
    dist_data = json.loads(dist_resp.body).get("data", [])
    {d.get("stage"): d for d in dist_data}

    # 3. yield anomalies（3月移动窗口 IQR）
    anomalies = await _detect_yield_anomalies(session, stages)

    # 4. blending RRT impurity check
    blend_impurities = []
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
                imp = {"batch_no": bn}
                for key in (
                    "rrt_053",
                    "rrt_0755",
                    "rrt_094_096",
                    "rrt_103_106",
                    "rrt_201",
                ):
                    val = getattr(row, key, None)
                    imp[key] = round(float(val), 4) if val is not None else None
                ti = getattr(row, "total_impurity", None)
                imp["total_impurity"] = round(float(ti), 4) if ti is not None else None
                blend_impurities.append(imp)

                # flag impurity anomalies
                if imp.get("total_impurity") and imp["total_impurity"] > 1.5:
                    anomalies.append(
                        {
                            "stage": "blending",
                            "batch_no": bn,
                            "metric": "total_impurity",
                            "value": imp["total_impurity"],
                            "benchmark": 1.5,
                            "severity": "high",
                            "detail": f"总杂{imp['total_impurity']}%, 超出1.5%",
                        }
                    )
                for rrt_key in (
                    "rrt_053",
                    "rrt_0755",
                    "rrt_094_096",
                    "rrt_103_106",
                    "rrt_201",
                ):
                    val = imp.get(rrt_key)
                    if val and val > 0.5:
                        sev = "high" if val > 1.0 else "medium"
                        anomalies.append(
                            {
                                "stage": "blending",
                                "batch_no": bn,
                                "metric": rrt_key,
                                "value": val,
                                "benchmark": 0.5,
                                "severity": sev,
                                "detail": f"{rrt_key}={val}%, 超出0.5%",
                            }
                        )

    overall_sev = (
        "high"
        if cumulative_yield < 70
        else "medium"
        if cumulative_yield < 85
        else "low"
    )

    # 5. history
    ref_cases = []
    if anomalies:
        history = (
            await session.execute(
                text("""
            SELECT id, batch_no, stage, summary, causes, suggestions, severity,
        created_at
            FROM production.ai_analysis WHERE stage = :st AND is_deleted = false
            ORDER BY created_at DESC LIMIT 3
        """),
                {"st": real_stage},
            )
        ).fetchall()
        ref_cases = [
            {
                "id": str(r.id),
                "batch_no": r.batch_no,
                "summary": r.summary,
                "causes": r.causes,
                "suggestions": r.suggestions,
                "severity": r.severity,
            }
            for r in history
        ]

    # 6. prompt
    prompt = _build_prompt(
        batch_no,
        real_stage,
        stages,
        cumulative_yield,
        max_loss_stage,
        anomalies,
        blend_impurities,
        ref_cases,
    )

    # 7. LLM
    llm_text = ""
    summary = ""
    causes = []
    suggestions = []
    llm_severity = overall_sev
    try:
        cfg = await get_config("text")
        client = AsyncOpenAI(
            base_url=cfg.api_base_url or "https://newapi.livzon.cn/v1",
            api_key=cfg.api_key or "",
        )

        async def _call_llm(temperature: float, extra_hint: str = "") -> str:
            msgs = [{"role": "user", "content": prompt + extra_hint}]
            resp = await client.chat.completions.create(
                model=cfg.model_name or "deepseek-v4-pro",
                messages=msgs,
                temperature=temperature,
                max_tokens=3000,
                timeout=120,
                extra_body={"thinking": {"type": "disabled"}},
            )
            return resp.choices[0].message.content or ""

        llm_text = await _call_llm(0.3)
        parsed = _parse_json(llm_text)
        summary = parsed.get("summary", "")
        causes = parsed.get("causes", [])
        suggestions = parsed.get("suggestions", [])
        llm_severity = parsed.get("severity", overall_sev)

        # 兜底：如果分析太敷衍（causes < 3 条），用更高温度重试
        if len(causes) < 3 or len(suggestions) < 3:
            logger.warning(
                f"AI 分析过于简短（causes={len(causes)}, suggestions={len(suggestions)}），重试中..."  # noqa: E501
            )
            llm_text = await _call_llm(
                0.7,
                "\n\n【重要提醒】上一轮分析太简略。请逐工段详细评价：收率是否合理、操作控制情况、与历史均值对比。causes和suggestions各至少4条。",
            )
            parsed = _parse_json(llm_text)
            summary = parsed.get("summary", summary)
            causes = parsed.get("causes", causes)
            suggestions = parsed.get("suggestions", suggestions)
            llm_severity = parsed.get("severity", llm_severity)
    except Exception as e:
        logger.error(f"LLM failed: {e}")
        llm_text = f"分析失败: {e}"
        label = STAGE_LABELS.get(real_stage, real_stage)
        summary = f"{label}{batch_no}分析失败（{str(e)[:50]}），以下为后端自动检测结果"
        # 后端兜底：从 anomalies 和 stages 生成基本分析
        if not causes:
            for a in anomalies or []:
                causes.append(
                    f"{a['stage']} {a['batch_no']} {a['metric']}={a['value']}，{a['detail']}"  # noqa: E501
                )
            if not causes:
                causes.append("各工段收率均在正常范围内，无异常标记")
        if not suggestions:
            for a in anomalies or []:
                suggestions.append(
                    f"关注 {a['stage']} 工段 {a['batch_no']}，{a['detail']}，建议排查工艺参数"  # noqa: E501
                )
            if not suggestions:
                suggestions.append("持续监控各工段关键参数，保持当前操作水平")

    # 8. save
    import uuid as _uuid

    sid = str(_uuid.uuid4())
    analysis = AiAnalysis(
        batch_no=batch_no,
        stage=real_stage,
        include_siblings=include_siblings,
        trace_snapshot=trace_data,
        dist_snapshot=dist_data,
        anomalies=anomalies,
        llm_prompt=prompt,
        llm_response=llm_text,
        summary=summary,
        causes=causes,
        suggestions=suggestions,
        severity=llm_severity,
        model_used=cfg.model_name or "",
        reference_cases=[c["id"] for c in ref_cases],
        created_by="AI自动分析",
        session_id=sid,
        message_seq=0,
        role="system",
    )
    session.add(analysis)
    await session.commit()

    return success_response(
        data={
            "id": str(analysis.id),
            "session_id": sid,
            "summary": summary,
            "anomalies": anomalies,
            "causes": causes,
            "suggestions": suggestions,
            "severity": llm_severity,
            "analysis_text": llm_text,
            "reference_cases": ref_cases,
        }
    )


@router.get(
    "/mc/lineage/ai-analysis-stream", summary="AI 分析（SSE 流式，展示思考过程）"
)
async def ai_analyze_stream(
    batch_no: str = Query(...),
    stage: str = Query(...),
    include_siblings: bool = Query(True),
    session: AsyncSession = Depends(get_db),
):
    async def generate():
        import uuid as _uuid

        sid = str(_uuid.uuid4())
        cfg = await get_config("text")
        def evt(t, d):
            return (
                    f"data: {json.dumps({'type': t, **d}, ensure_ascii=False)}\n\n"
                )

        yield evt("step", {"step": "trace", "msg": "正在查询批次追溯链路..."})

        # 1. trace
        trace_resp = await lineage_trace(
            batch_no=batch_no,
            stage=stage,
            include_siblings=include_siblings,
            session=session,
        )
        trace_data = json.loads(trace_resp.body).get("data", {})
        stages = trace_data.get("stages", [])
        total_nodes = sum(len(sg.get("nodes", [])) for sg in stages)
        yield evt(
            "step",
            {
                "step": "trace",
                "done": True,
                "msg": f"已获取 {len(stages)} 个工段、{total_nodes} 个节点",
            },
        )

        cumulative_yield = trace_data.get("cumulative_yield", 100)
        max_loss_stage = trace_data.get("max_loss_stage")
        real_stage = trace_data.get("target_stage", stage)
        STAGE_LABELS.get(real_stage, real_stage)

        # 2. yield dist
        yield evt("step", {"step": "yield", "msg": "正在计算收率分布..."})
        dist_resp = await lineage_yield_distribution(session=session)
        dist_data = json.loads(dist_resp.body).get("data", [])
        {d.get("stage"): d for d in dist_data}
        yield evt(
            "step",
            {
                "step": "yield",
                "done": True,
                "msg": f"已获取 {len(dist_data)} 个工段的收率统计",
            },
        )

        # 3. anomalies（3月移动窗口 IQR）
        yield evt(
            "step", {"step": "anomaly", "msg": "正在用移动窗口IQR检测收率异常..."}
        )
        anomalies = await _detect_yield_anomalies(session, stages)
        yield evt(
            "step",
            {
                "step": "anomaly",
                "done": True,
                "msg": f"检测到 {len(anomalies)} 个收率异常",
            },
        )

        blend_impurities = []
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
                            text(
                                "SELECT rrt_053, rrt_0755, rrt_094_096, rrt_103_106, rrt_201, total_impurity FROM production.blending_records WHERE batch_no = :bn AND is_deleted = false"  # noqa: E501
                            ),
                            {"bn": bn},
                        )
                    ).fetchone()
                    if not row:
                        continue
                    imp = {"batch_no": bn}
                    for key in (
                        "rrt_053",
                        "rrt_0755",
                        "rrt_094_096",
                        "rrt_103_106",
                        "rrt_201",
                    ):
                        val = getattr(row, key, None)
                        imp[key] = round(float(val), 4) if val is not None else None
                    ti = getattr(row, "total_impurity", None)
                    imp["total_impurity"] = (
                        round(float(ti), 4) if ti is not None else None
                    )
                    blend_impurities.append(imp)
                    if imp.get("total_impurity") and imp["total_impurity"] > 1.5:
                        anomalies.append(
                            {
                                "stage": "blending",
                                "batch_no": bn,
                                "metric": "total_impurity",
                                "value": imp["total_impurity"],
                                "benchmark": 1.5,
                                "severity": "high",
                                "detail": f"总杂{imp['total_impurity']}%, 超出1.5%",
                            }
                        )
                    for rrt_key in (
                        "rrt_053",
                        "rrt_0755",
                        "rrt_094_096",
                        "rrt_103_106",
                        "rrt_201",
                    ):
                        val = imp.get(rrt_key)
                        if val and val > 0.5:
                            sev = "high" if val > 1.0 else "medium"
                            anomalies.append(
                                {
                                    "stage": "blending",
                                    "batch_no": bn,
                                    "metric": rrt_key,
                                    "value": val,
                                    "benchmark": 0.5,
                                    "severity": sev,
                                    "detail": f"{rrt_key}={val}%, 超出0.5%",
                                }
                            )

        overall_sev = (
            "high"
            if cumulative_yield < 70
            else "medium"
            if cumulative_yield < 85
            else "low"
        )
        yield evt(
            "step",
            {
                "step": "anomaly",
                "done": True,
                "msg": f"检测到 {len(anomalies)} 个异常点，严重程度: {overall_sev}",
            },
        )

        # 4. ref cases
        yield evt("step", {"step": "history", "msg": "正在检索历史分析案例..."})
        ref_cases = []
        history_rows = (
            await session.execute(
                text(
                    "SELECT id, batch_no, stage, summary, causes, suggestions, severity FROM production.ai_analysis WHERE stage = :st AND is_deleted = false ORDER BY created_at DESC LIMIT 3"  # noqa: E501
                ),
                {"st": real_stage},
            )
        ).fetchall()
        ref_cases = [
            {
                "id": str(r.id),
                "batch_no": r.batch_no,
                "summary": r.summary,
                "severity": r.severity,
            }
            for r in history_rows
        ]
        yield evt(
            "step",
            {
                "step": "history",
                "done": True,
                "msg": f"找到 {len(ref_cases)} 个历史参考案例",
            },
        )

        # 5. prompt
        prompt = _build_prompt(
            batch_no,
            real_stage,
            stages,
            cumulative_yield,
            max_loss_stage,
            anomalies,
            blend_impurities,
            ref_cases,
        )

        # 6. LLM
        yield evt("step", {"step": "llm", "msg": "正在调用 AI 模型分析，请稍候..."})
        llm_text = ""
        summary = ""
        causes = []
        suggestions = []
        llm_severity = overall_sev
        try:
            client = AsyncOpenAI(
                base_url=cfg.api_base_url or "https://newapi.livzon.cn/v1",
                api_key=cfg.api_key or "",
            )

            async def _call_llm_stream(temp, extra=""):
                nonlocal llm_text
                msgs = [{"role": "user", "content": prompt + extra}]
                s = await client.chat.completions.create(
                    model=cfg.model_name or "deepseek-v4-pro",
                    messages=msgs,
                    temperature=temp,
                    max_tokens=3000,
                    timeout=120,
                    stream=True,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                async for chunk in s:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        llm_text += delta.content
                        yield evt("token", {"content": delta.content})

            async for e in _call_llm_stream(0.3):
                yield e

            parsed = _parse_json(llm_text)
            summary = parsed.get("summary", "")
            causes = parsed.get("causes", [])
            suggestions = parsed.get("suggestions", [])
            llm_severity = parsed.get("severity", overall_sev)

            if len(causes) < 3 or len(suggestions) < 3:
                yield evt("step", {"step": "llm_retry", "msg": "分析过短，重新生成..."})
                prev_text = llm_text
                async for e in _call_llm_stream(
                    0.7,
                    "\n\n【重要提醒】上一轮分析太简略。请逐工段详细评价。causes和suggestions各至少4条。",
                ):
                    yield e
                parsed_retry = _parse_json(llm_text)
                if not parsed_retry.get("summary") and prev_text:
                    parsed_retry = _parse_json(prev_text)
                if parsed_retry.get("summary"):
                    summary = parsed_retry["summary"]
                if parsed_retry.get("causes"):
                    causes = parsed_retry["causes"]
                if parsed_retry.get("suggestions"):
                    suggestions = parsed_retry["suggestions"]
                if parsed_retry.get("severity"):
                    llm_severity = parsed_retry["severity"]
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            llm_text = f"分析失败: {e}"
            if not causes:
                for a in anomalies:
                    causes.append(
                        f"{a['stage']} {a['batch_no']} {a['metric']}={a['value']}，{a['detail']}"  # noqa: E501
                    )
                if not causes:
                    causes.append("各工段收率正常")
            if not suggestions:
                for a in anomalies:
                    suggestions.append(
                        f"关注 {a['stage']} {a['batch_no']}，{a['detail']}"
                    )
                if not suggestions:
                    suggestions.append("持续监控各工段关键参数")

        yield evt("step", {"step": "llm", "done": True, "msg": "AI 分析完成"})

        # save
        analysis = AiAnalysis(
            batch_no=batch_no,
            stage=real_stage,
            include_siblings=include_siblings,
            trace_snapshot=trace_data,
            dist_snapshot=dist_data,
            anomalies=anomalies,
            llm_prompt=prompt,
            llm_response=llm_text,
            summary=summary,
            causes=causes,
            suggestions=suggestions,
            severity=llm_severity,
            model_used=cfg.model_name or "",
            reference_cases=[c["id"] for c in ref_cases],
            created_by="AI自动分析",
            session_id=sid,
            message_seq=0,
            role="system",
        )
        session.add(analysis)
        await session.commit()

        yield evt(
            "result",
            {
                "id": str(analysis.id),
                "session_id": sid,
                "summary": summary,
                "anomalies": anomalies,
                "causes": causes,
                "suggestions": suggestions,
                "severity": llm_severity,
                "analysis_text": llm_text,
                "reference_cases": ref_cases,
                "trace_nodes": total_nodes,
                "trace_stages": len(stages),
            },
        )
        yield evt("done", {})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/mc/lineage/ai-history", summary="查询批次 AI 分析历史")
async def ai_history(
    batch_no: str = Query(...),
    stage: str = Query(...),
    limit: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_db),
):
    """返回同批次同工段的历史分析记录（仅 seq=0 的首条报告）。
    兼容 MC- 前缀有无、阶段别名（如 na_batch→sub_tank）。"""
    # 阶段别名解析（与 mc_lineage_api._resolve_batch 一致）
    _stage_aliases = {
        "na_batch": "sub_tank",
        "crude_product": "sub_tank",
        "wet_powder": "extraction",
    }
    resolved_stage = _stage_aliases.get(stage, stage)
    # 批号：去掉 MC- 前缀，同时兼容带前缀的写法
    clean_bn = batch_no.removeprefix("MC-")
    rows = (
        await session.execute(
            text("""
        SELECT id, session_id, batch_no, stage, summary, severity,
               causes, suggestions, anomalies, created_at, created_by
        FROM production.ai_analysis
        WHERE (batch_no = :bn1 OR batch_no = :bn2)
          AND (stage = :st1 OR stage = :st2)
          AND message_seq = 0 AND is_deleted = false
        ORDER BY created_at DESC LIMIT :lim
    """),
            {
                "bn1": clean_bn,
                "bn2": f"MC-{clean_bn}",
                "st1": stage,
                "st2": resolved_stage,
                "lim": limit,
            },
        )
    ).fetchall()

    records = [
        {
            "id": str(r.id),
            "session_id": r.session_id,
            "batch_no": r.batch_no,
            "stage": r.stage,
            "stage_label": STAGE_LABELS.get(r.stage, r.stage),
            "summary": r.summary,
            "severity": r.severity,
            "causes": r.causes,
            "suggestions": r.suggestions,
            "anomalies": r.anomalies,
            "created_by": r.created_by,
            "created_at": str(r.created_at),
        }
        for r in rows
    ]

    return success_response(
        data={
            "batch_no": batch_no,
            "stage": stage,
            "records": records,
            "total": len(records),
        }
    )


def _build_prompt(
    batch_no,
    stage,
    stages,
    cumulative_yield,
    max_loss_stage,
    anomalies,
    impurities,
    ref_cases,
):
    label = STAGE_LABELS.get(stage, stage)

    # 找本批提炼批号（主线子罐的父批）
    target_refining = ""
    for sg in stages:
        if sg.get("stage") != "sub_tank":
            continue
        for n in sg.get("nodes", []):
            if n.get("is_sibling"):
                continue
            bn = n.get("batch_no", "")
            target_refining = bn.rsplit("-", 1)[0] if "-" in bn else ""
            break

    # 找外批复联的提炼批号
    ext_refining = ""
    ext_batches: set[str] = set()
    for sg in stages:
        for n in sg.get("nodes", []):
            if not n.get("is_sibling"):
                continue
            bn = n.get("batch_no", "")
            parent = bn.rsplit("-", 1)[0] if "-" in bn else ""
            if parent and parent != target_refining:
                ext_refining = parent
                # 收集该提炼批下的所有子罐，用于匹配其下游节点
                for sg2 in stages:
                    for n2 in sg2.get("nodes", []):
                        bn2 = n2.get("batch_no", "")
                        p2 = bn2.rsplit("-", 1)[0] if "-" in bn2 else ""
                        if p2 == ext_refining:
                            ext_batches.add(bn2)

    # 分组输出
    main_lines, ext_lines = [], []
    ext_active = False
    for sg in stages:
        for n in sg.get("nodes", []):
            sib = " [同级]" if n.get("is_sibling") else ""
            tgt = " ← 目标" if n.get("batch_no") == batch_no else ""
            line = f"  {sg['label']} {n['batch_no']}({n.get('detail', '')}){sib}{tgt}"

            if ext_batches and (
                n.get("batch_no") in ext_batches
                or (
                    ext_active
                    and n.get("is_sibling")
                    and n.get("batch_no", "").startswith("MC-")
                )
            ):
                if n.get("batch_no") in ext_batches:
                    ext_active = True
                ext_lines.append(line)
            else:
                main_lines.append(line)

    # 如果没精准匹配到，回退：所有同级放到后面
    if not ext_lines:
        for sg in stages:
            for n in sg.get("nodes", []):
                if n.get("is_sibling"):
                    sib = " [同级]" if n.get("is_sibling") else ""
                    line = (
                        f"  {sg['label']} {n['batch_no']}({n.get('detail', '')}){sib}"
                    )
                    main_lines.remove(line) if line in main_lines else None
                    ext_lines.append(line)

    lines = [
        f"你是制药工艺分析师，拥有霉酚酸(MC)生产线深度知识。分析中必须使用中文工段名称（如粗提分罐、萃取），禁止出现sub_tank/extraction/refinement等英文工段代码。\n\n=== 批次信息 ===\n目标: {batch_no}（{label}）\n累计收率: {cumulative_yield}%\n最大损失工段: {max_loss_stage or '无'}\n\n=== 本批全链路 ==="  # noqa: E501
    ]
    lines.extend(main_lines)

    if ext_lines and ext_refining:
        lines.append(
            f"\n=== 外批复联（来自提炼批 {ext_refining}，非本批主线，因汇入同一混粉节点产生关联） ==="  # noqa: E501
        )
        lines.extend(ext_lines)
    elif ext_lines:
        lines.append("\n=== 同级批次 ===")
        lines.extend(ext_lines)

    if impurities:
        lines.append("\n=== RRT 杂质数据 ===")
        for imp in impurities:
            parts = []
            for k in ("rrt_053", "rrt_0755", "rrt_094_096", "rrt_103_106", "rrt_201"):
                if imp.get(k) is not None:
                    parts.append(f"{k}={imp[k]}%")
            if imp.get("total_impurity") is not None:
                parts.append(f"总杂={imp['total_impurity']}%")
            lines.append(f"  {imp['batch_no']}: {', '.join(parts)}")
        lines.append("（RRT杂质各点位正常值应<0.5%，总杂应<1.5%）")

    if anomalies:
        lines.append("\n=== 异常标记 ===")
        for a in anomalies:
            stage_cn = STAGE_LABELS.get(a["stage"], a["stage"])
            lines.append(
                f"⚠ {stage_cn} {a['batch_no']} {a['metric']}={a['value']} — {a['detail']}"  # noqa: E501
            )

    # 注入历史参考
    history_text = ""
    if ref_cases:
        history_text = "\n=== 历史参考案例 ==="
        for c in ref_cases:
            history_text += (
                f"\n- [{c['severity']}] {c['batch_no']}: {c.get('summary', '')}"
            )

    # 连历史也没有 → 也要完整分析
    if not ref_cases:
        history_text = "\n（无历史分析记录，这是该工段首次分析）"

    extra = ""
    if impurities:
        extra += "\n5. RRT杂质分析：各点位是否正常，偏高的可能原因及控制建议"

    lines.append(f"""
请以 JSON 格式返回详细分析结果，**无论正常与否都必须详细分析**：
{{
  "summary": "一句话摘要（含关键数据，如收率xx%、xx个异常点。正常也说正常，40字内）",
  "causes": ["原因1（即使正常也要说明哪些工段表现良好及原因）","原因2",...],
  "suggestions": ["建议1（即使正常也要给出监控重点）","建议2",...],
  "severity": "low|medium|high"
}}
{extra}

分析要求：
-
        必须使用中文工段名称（粗提分罐、萃取、精制、混粉、入库），禁止出现sub_tank/extraction/refinement等英文代码
- 首先用一句话说明分析覆盖范围（本批XX个节点 + 外批复联YY个节点的原因）
- 然后按工段逐项分析本批主线，每个工段至少一句评价
-
        如果存在外批复联，在全部本批分析结束后单独一段"外批复联参考"集中说明，明确标注"非本批主线"
- 正常批次也要给出监控重点，异常批次从工艺角度分析根因{history_text}
只返回JSON。""")
    return "\n".join(lines)


def _parse_json(text):
    t = text.strip()
    if t.startswith("```json"):
        t = t[7:]
    if t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # 尝试修复截断的 JSON：补全最后一个未闭合的结构
    for suffix in ['"}]', '"]}]', "}]", "]}]", "}", '"}}', '"}', '"]}']:
        try:
            return json.loads(t + suffix)
        except json.JSONDecodeError:
            continue
    # 都失败了，至少提取已经完整写入的 summary
    import re

    result = {}
    m = re.search(r'"summary"\s*:\s*"([^"]*)"', t)
    if m:
        result["summary"] = m.group(1)
    m = re.search(r'"severity"\s*:\s*"([^"]*)"', t)
    if m:
        result["severity"] = m.group(1)
    # causes/suggestions 用正则提取已完成的条目
    for key in ("causes", "suggestions"):
        items = re.findall(
            r'"([^"]*)"',
            t[t.find(f'"{key}"') : t.find("]", t.find(f'"{key}"'))]
            if f'"{key}"' in t
            else "",
        )
        if items:
            result[key] = items
    return result
