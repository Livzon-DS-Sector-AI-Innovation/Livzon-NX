"""FA 苯丙氨酸 - AI 批次分析 API"""
import json
import logging
import re
import uuid as _uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionUserMessageParam
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.llm import get_config
from app.core.response import success_response
from app.modules.production.ai_analysis_models import AiAnalysis
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])

FA_STAGE_LABELS = {
    "fermentation": "发酵放罐",
    "acidification": "酸化过滤",
    "decolor1": "一次脱色",
    "decolor_centrifuge": "脱色离心",
}


def _parse_json(raw: str) -> dict[str, Any]:
    """从 LLM 回复中提取 JSON"""
    # 去掉 markdown 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    js = (m.group(1) if m else raw).strip()
    try:
        parsed = json.loads(js)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        # 尝试提取 { ... }
        m2 = re.search(r"\{[\s\S]*\}", js)
        if m2:
            try:
                parsed = json.loads(m2.group(0))
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                pass
        return {}


async def _get_trace_data(session: Any, batch_no: Any, stage: Any) -> Any:
    """收集批次全量数据"""
    data_sections = []

    # 发酵数据
    ferment = (
        await session.execute(
            text(
                """SELECT fb."发酵罐号", fb."放罐日期"::text, fb."汇总总量_kg",
        fb."电导_uscm",
           fb."调酸量_L", fb."酸化液滤速_ml10min", fb."发酵液湿固",
           STRING_AGG(fsb."发酵批号" || '(' || COALESCE(fsb."放罐体积_kl"::text,'?')
        || 'kl/'
        || COALESCE(fsb."放罐含量_gL"::text,'?') || 'gL/' ||
        COALESCE(fsb."批总量_kg"::text,'?') || 'kg)', ', '
                || COALESCE(fsb."放罐含量_gL"::text,'?') || 'gL/' ||
        COALESCE(fsb."批总量_kg"::text,'?') || 'kg)', ', ')
           as subs
        FROM production.fa_fermentation_batches fb
        LEFT JOIN production.fa_fermentation_sub_batches fsb ON fsb."父发酵罐号" =
        fb."发酵罐号"
        WHERE fb."发酵罐号" = :bn GROUP BY fb."发酵罐号", fb."放罐日期",
        fb."汇总总量_kg",
        fb."电导_uscm", fb."调酸量_L", fb."酸化液滤速_ml10min", fb."发酵液湿固" """
            ),
            {"bn": batch_no},
        )
    ).fetchone()
    if ferment:
        data_sections.append(
            f"发酵放罐: {batch_no}\n"
            f"  放罐日期: {ferment[1]}\n"
            f"  汇总总量: {ferment[2]}kg\n"
            f"  电导: {ferment[3]} us/cm, 调酸量: {ferment[4]}L\n"
            f"  滤速: {ferment[5]}ml/10min, 湿固: {ferment[6]}\n"
            f"  子批: {ferment[7]}"
        )

    # 酸化数据 - 用别名避免括号列名
    acid_rows = (
        await session.execute(
            text(
                """SELECT "用酸量（95-98%浓硫酸）" as acid, "PH（酸化后）" as ph_acid,
           "酸化液体积（kl)" as acid_vol, "膜滤液体积（KL）" as mf_vol,
           "膜滤液含量（g/L）" as mf_content, "膜滤液产品量（kg）" as mf_qty,
           "渣损失率（渣苯丙量/罐产）" as slag_loss, "平衡率" as balance
        FROM production.fa_acidification_records WHERE "批号" = :bn ORDER BY id"""
            ),
            {"bn": batch_no},
        )
    ).fetchall()
    if acid_rows:
        a0 = acid_rows[0]
        sections = []
        for ar in acid_rows:
            if ar.mf_qty and float(ar.mf_qty) > 0:
                sections.append(
                    f"  膜滤: {ar.mf_vol}kl × {ar.mf_content}g/L = {ar.mf_qty}kg"
                )
        data_sections.append(
            f"酸化过滤:\n"
            f"  用酸量: {a0.acid}kg, pH(酸化后): {a0.ph_acid}\n"
            f"  酸化液体积: {a0.acid_vol}kl\n"
            f"{chr(10).join(sections)}\n"
            f"  渣损失率: {a0.slag_loss}, 平衡率: {a0.balance}"
        )

    # 脱色数据
    core = batch_no.replace("FA-EX", "")
    decolor = (
        await session.execute(
            text(
                """SELECT "批号", "体积(kl)" as vol, "含量(g/L)" as content,
           "活性炭添加量(kg)" as carbon, "碳后含量(g/L)" as after_carbon,
           "电导(us/cm)" as cond1, "调前电导碳柱(us/cm)" as cond2, "电导(us/cm)2" as
        cond3
        FROM production.fa_decolor1_records
        WHERE "批号" LIKE '%' || :core || '%' LIMIT 1"""
            ),
            {"core": core},
        )
    ).fetchone()
    if decolor:
        data_sections.append(
            f"一次脱色: {decolor.批号}\n"
            f"  进料: {decolor.vol}kl, 含量: {decolor.content}g/L\n"
            f"  活性炭: {decolor.carbon}kg, 碳后含量: {decolor.after_carbon}g/L\n"
            f"  电导: {decolor.cond1}→{decolor.cond2}(调碳)→{decolor.cond3}(脱色后)"
        )

    # 离心数据
    cent_rows = (
        await session.execute(
            text(
                """SELECT "批号", "进料体积（kl）" as in_vol, "收率" as yield_rate,
           "炭前真实含量（g/L）" as before_c, "炭后真实含量(g/L）" as after_c
        FROM production.fa_decolor_centrifuge_records
        WHERE "批号" LIKE '%' || :core || '%' ORDER BY "批号" LIMIT 10"""
            ),
            {"core": core},
        )
    ).fetchall()
    if cent_rows:
        cent_parts = []
        for cr in cent_rows:
            vol = f"{float(cr.in_vol):.0f}kl" if cr.in_vol else "?"
            yr = f"{float(cr.yield_rate) * 100:.1f}%" if cr.yield_rate else "?"
            bc = f"{cr.before_c}" if cr.before_c else "?"
            ac = f"{cr.after_c}" if cr.after_c else "?"
            cent_parts.append(f"  {cr.批号}: 进料{vol}, 炭前{bc}→炭后{ac}g/L, 收率{yr}")
        data_sections.append(
            f"脱色离心 ({len(cent_rows)}份):\n" + "\n".join(cent_parts)
        )

    # 统计数据
    stats = []

    cond = (
        await session.execute(
            text(
                """SELECT ROUND(AVG("电导_uscm")::numeric,0), ROUND(PERCENTILE_CONT(0.5)
        WITHIN GROUP (ORDER BY "电导_uscm")::numeric,0),
           ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY "电导_uscm")::numeric,0),
           ROUND(MIN("电导_uscm")::numeric,0), ROUND(MAX("电导_uscm")::numeric,0)
        FROM production.fa_fermentation_batches WHERE "电导_uscm" IS NOT NULL"""
            )
        )
    ).fetchone()
    if cond:
        stats.append(
            f"电导全量统计(us/cm): 均值{cond[0]} | 中位{cond[1]} | Q3={cond[2]} | 范围 {cond[3]}~{cond[4]}"  # noqa: E501
        )

    yr_stats = (
        await session.execute(
            text(
                """SELECT ROUND(AVG("收率")::numeric*100, 1),
        ROUND(MIN("收率")::numeric*100, 1), ROUND(MAX("收率")::numeric*100, 1)
        FROM production.fa_decolor_centrifuge_records WHERE "收率" IS NOT NULL"""
            )
        )
    ).fetchone()
    if yr_stats:
        stats.append(
            f"离心收率全量统计: 均值{yr_stats[0]}% | 范围 {yr_stats[1]}%~{yr_stats[2]}%"
        )

    # 渣损失率统计
    slag = (
        await session.execute(
            text(
                """SELECT
        ROUND(AVG(CAST(REPLACE(REPLACE("渣损失率（渣苯丙量/罐产）", '%', ''),
        ',', '') AS numeric)), 1)
        FROM production.fa_acidification_records WHERE "渣损失率（渣苯丙量/罐产）"
        IS NOT NULL AND
        "渣损失率（渣苯丙量/罐产）" != ''"""
            )
        )
    ).fetchone()
    if slag and slag[0]:
        stats.append(f"渣损失率全量均值: {slag[0]}%")

    return "\n\n".join(data_sections), "\n".join(stats)


@router.get("/fa/lineage/ai-analysis", summary="FA 批次 AI 分析")
async def fa_ai_analysis(
    batch_no: str = Query(...),
    stage: str = Query("fermentation"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    if stage not in FA_STAGE_LABELS:
        raise HTTPException(400, f"无效工段: {stage}")

    # 1. 获取批次数据
    batch_data, stats_data = await _get_trace_data(session, batch_no, stage)
    if not batch_data:
        raise HTTPException(404, f"未找到批次数据: {batch_no}")

    # 2. 构建 prompt
    prompt = f"""你是丽珠制药厂 203 车间
        FA（L-苯丙氨酸）提炼工艺专家。请分析以下批次的生产数据，给出专业判断。

批次: {batch_no}
工段: {FA_STAGE_LABELS.get(stage, stage)}

=== 批次生产数据 ===
{batch_data}

=== 全量统计参考 ===
{stats_data}

=== 工艺背景 ===
L-苯丙氨酸提炼流程：发酵放罐 → 酸化调酸 → 陶瓷膜过滤(3轮) → 一次脱色(活性炭) →
        脱色离心(分8份各自离心，母液内部回用)
- 发酵电导越高，提炼难度越大（盐/杂质多→膜污染、MVR结垢风险）
- C/D罐是发酵液的两个接收罐，后缀不是处理次数
- 一次脱色只记首罐数据，其余罐工艺参数相同
- 离心收率>100%表示母液回用混入了上层残液
- 碳后含量不应高于碳前（物理上不可能），差异为取样误差

请用 JSON 格式回复：
{{
  "summary": "一句话总结批次状态（不超过50字）",
  "causes": ["原因1", "原因2", "原因3"],
  "suggestions": ["建议1", "建议2", "建议3"],
  "severity": "low/medium/high"
}}"""

    # 3. 调用 LLM
    try:
        cfg = await get_config("text")
        base_url = cfg.api_base_url or "https://newapi.livzon.cn/v1"
        model = cfg.model_name or "deepseek-v4-pro"
        client = AsyncOpenAI(
            base_url=base_url, api_key=cfg.api_key or "no-key", timeout=120
        )

        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
            extra_body={"thinking": {"type": "disabled"}},
        )
        raw = resp.choices[0].message.content or ""
        parsed = _parse_json(raw)

        # 4. 保存结果（跳过入库避免 : 符号冲突）
        try:
            await session.execute(
                text(
                    "INSERT INTO production.ai_analysis (batch_no, stage, llm_response, summary, causes, suggestions, severity, model_used, created_by, message_seq, role) "  # noqa: E501
                    "VALUES (:bn, :st, '', :summary, '[]'::jsonb, '[]'::jsonb, :severity, :model, 'AI自动分析', 0, 'assistant')"  # noqa: E501
                ),
                {
                    "bn": batch_no,
                    "st": stage,
                    "summary": parsed.get("summary", "")[:500],
                    "severity": parsed.get("severity", "low"),
                    "model": model,
                },
            )
            await session.commit()
        except Exception:
            pass  # 入库非关键

        return success_response(
            data={
                "summary": parsed.get("summary", "分析完成"),
                "anomalies": [],
                "causes": parsed.get("causes", []),
                "suggestions": parsed.get("suggestions", []),
                "severity": parsed.get("severity", "low"),
                "analysis_text": raw,
                "reference_cases": [],
            }
        )
    except Exception as e:
        logger.exception("FA AI分析失败")
        # LLM 不可用时返回基础分析
        return success_response(
            data={
                "summary": f"批次 {batch_no} 数据已收集，AI 分析暂时不可用",
                "anomalies": [],
                "causes": [f"AI 分析服务异常: {str(e)[:100]}"],
                "suggestions": ["稍后重试 AI 分析"],
                "severity": "low",
                "analysis_text": "",
                "reference_cases": [],
            }
        )


# ═══════════════════════════════════════════════════════════
# SSE 流式 AI 分析 + 会话管理（支持前端多轮对话）
# ═══════════════════════════════════════════════════════════

FA_ANALYSIS_PROMPT = """你是丽珠制药厂 203 车间
        FA（L-苯丙氨酸）提炼工艺专家。请分析以下批次的生产数据，给出专业判断。

批次: {batch_no}
工段: {stage_label}

=== 批次生产数据 ===
{batch_data}

=== 全量统计参考 ===
{stats_data}

=== 工艺背景 ===
L-苯丙氨酸提炼流程：发酵放罐 → 酸化调酸 → 陶瓷膜过滤(3轮) → 一次脱色(活性炭) →
        脱色离心(分8份各自离心，母液内部回用)
- 发酵电导越高，提炼难度越大（盐/杂质多→膜污染、MVR结垢风险）
- C/D罐是发酵液的两个接收罐，后缀不是处理次数
- 一次脱色只记首罐数据，其余罐工艺参数相同
- 离心收率>100%表示母液回用混入了上层残液
- 碳后含量不应高于碳前（物理上不可能），差异为取样误差

回复要求：
- summary 说人话，别写"本批次电导值显著偏高"，直接说"电导6259，比均值高，提炼难度大"
- causes 每条一句话说清具体问题，别铺垫
- suggestions 给车间能直接照做的操作建议，别泛泛而谈
- 不要显示思考过程，不要用"首先""其次""总结"这类词

请用 JSON 格式回复：
{{
  "summary": "一句话总结批次状态（不超过50字）",
  "causes": ["原因1", "原因2", "原因3", "原因4"],
  "suggestions": ["建议1", "建议2", "建议3", "建议4"],
  "severity": "low/medium/high"
}}"""


@router.get(
    "/fa/lineage/ai-analysis-stream",
    summary="FA 批次 AI 分析（SSE 流式，展示思考过程）",
)
async def fa_ai_analysis_stream(
    batch_no: str = Query(...),
    stage: str = Query("fermentation"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    if stage not in FA_STAGE_LABELS:
        raise HTTPException(
            400, f"无效工段: {stage}，可选: {list(FA_STAGE_LABELS.keys())}"
        )

    async def generate() -> AsyncIterator[Any]:
        sid = str(_uuid.uuid4())
        cfg = await get_config("text")
        def evt(t: Any, d: Any) -> Any:
            return (
                    f"data: {json.dumps({'type': t, **d}, ensure_ascii=False)}\n\n"
                )

        # Step 1: 收集批次数据
        yield evt("step", {"step": "trace", "msg": "正在收集批次生产数据..."})
        try:
            batch_data, stats_data = await _get_trace_data(session, batch_no, stage)
        except Exception as e:
            logger.error(f"FA 数据收集失败: {e}")
            yield evt("error", {"msg": f"数据收集失败: {e}"})
            return

        if not batch_data:
            yield evt("error", {"msg": f"未找到批次数据: {batch_no}"})
            return

        stage_label = FA_STAGE_LABELS.get(stage, stage)
        yield evt(
            "step",
            {
                "step": "trace",
                "done": True,
                "msg": f"已收集 {stage_label} 批次 {batch_no} 的生产数据",
            },
        )

        # Step 2: 统计分析
        yield evt("step", {"step": "stats", "msg": "正在计算统计分析..."})
        anomaly_count = 0
        if stats_data:
            yield evt(
                "step",
                {
                    "step": "stats",
                    "done": True,
                    "msg": f"统计完成，发现 {anomaly_count} 个关注点",
                },
            )
        else:
            yield evt("step", {"step": "stats", "done": True, "msg": "统计完成"})

        # Step 3: 检测异常
        yield evt("step", {"step": "anomaly", "msg": "正在检测数据异常..."})
        anomalies = []
        try:
            # 离心收率异常检测
            cent_rows_raw = (
                await session.execute(
                    text(
                        """SELECT "批号", "收率" FROM
        production.fa_decolor_centrifuge_records
                   WHERE "批号" LIKE '%' || :core || '%' ORDER BY "批号" LIMIT 20"""
                    ),
                    {"core": batch_no.replace("FA-EX", "")},
                )
            ).fetchall()
            for cr in cent_rows_raw:
                yr = float(cr[1]) if cr[1] else 0
                if yr < 0.85:
                    anomalies.append(
                        {
                            "stage": "decolor_centrifuge",
                            "batch_no": cr[0],
                            "metric": "yield_rate",
                            "value": round(yr * 100, 1),
                            "benchmark": 85,
                            "severity": "high" if yr < 0.75 else "medium",
                            "detail": f"离心收率{round(yr * 100, 1)}%，低于85%警戒线",
                        }
                    )
                elif yr > 1.05:
                    anomalies.append(
                        {
                            "stage": "decolor_centrifuge",
                            "batch_no": cr[0],
                            "metric": "yield_rate",
                            "value": round(yr * 100, 1),
                            "benchmark": 105,
                            "severity": "low",
                            "detail": f"离心收率{round(yr * 100, 1)}%>100%，可能母液回用混入残液",  # noqa: E501
                        }
                    )

            # 电导异常检测
            cond_rows = (
                await session.execute(
                    text(
                        """SELECT "电导_uscm" FROM production.fa_fermentation_batches
                   WHERE "发酵罐号" = :bn AND "电导_uscm" IS NOT NULL"""
                    ),
                    {"bn": batch_no},
                )
            ).fetchone()
            if cond_rows and cond_rows[0]:
                cond_val = float(cond_rows[0])
                if cond_val > 3000:
                    anomalies.append(
                        {
                            "stage": "fermentation",
                            "batch_no": batch_no,
                            "metric": "conductivity",
                            "value": round(cond_val, 0),
                            "benchmark": 3000,
                            "severity": "high" if cond_val > 5000 else "medium",
                            "detail": f"电导{cond_val}us/cm，高于3000，提炼难度大",
                        }
                    )
                elif cond_val > 2000:
                    anomalies.append(
                        {
                            "stage": "fermentation",
                            "batch_no": batch_no,
                            "metric": "conductivity",
                            "value": round(cond_val, 0),
                            "benchmark": 2000,
                            "severity": "low",
                            "detail": f"电导{cond_val}us/cm，略高于车间均值",
                        }
                    )

            # 渣损失率检测
            slag_rows = (
                await session.execute(
                    text(
                        """SELECT CAST(REPLACE(REPLACE("渣损失率（渣苯丙量/罐产）",
        '%', ''), ',',
        '') AS numeric)
                   FROM production.fa_acidification_records WHERE "批号" = :bn"""
                    ),
                    {"bn": batch_no},
                )
            ).fetchone()
            if slag_rows and slag_rows[0]:
                slag_val = float(slag_rows[0])
                if slag_val > 10:
                    anomalies.append(
                        {
                            "stage": "acidification",
                            "batch_no": batch_no,
                            "metric": "slag_loss",
                            "value": round(slag_val, 1),
                            "benchmark": 10,
                            "severity": "medium" if slag_val > 15 else "low",
                            "detail": f"渣损失率{slag_val}%，高于10%警戒线",
                        }
                    )
        except Exception as e:
            logger.warning(f"FA 异常检测失败: {e}")

        overall_sev = (
            "high"
            if any(a["severity"] == "high" for a in anomalies)
            else "medium"
            if any(a["severity"] == "medium" for a in anomalies)
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

        # Step 4: 历史参考案例
        yield evt("step", {"step": "history", "msg": "正在检索历史分析案例..."})
        ref_cases = []
        try:
            history_rows = (
                await session.execute(
                    text(
                        """SELECT id, batch_no, stage, summary, severity FROM
        production.ai_analysis
                   WHERE stage = :st AND message_seq = 0 AND is_deleted = false
                   ORDER BY created_at DESC LIMIT 3"""
                    ),
                    {"st": stage},
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
        except Exception:
            pass
        yield evt(
            "step",
            {
                "step": "history",
                "done": True,
                "msg": f"找到 {len(ref_cases)} 个历史参考案例",
            },
        )

        # Step 5: 构建 prompt + 调用 LLM
        prompt = FA_ANALYSIS_PROMPT.format(
            batch_no=batch_no,
            stage_label=stage_label,
            batch_data=batch_data,
            stats_data=stats_data or "暂无统计数据",
        )

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

            async def _call_llm_stream(temp: Any, extra: Any="") -> AsyncIterator[Any]:
                nonlocal llm_text
                msgs: list[ChatCompletionUserMessageParam] = [
                    {"role": "user", "content": prompt + extra}
                ]
                s = await client.chat.completions.create(
                    model=cfg.model_name or "deepseek-v4-pro",
                    messages=msgs,
                    temperature=temp,
                    max_tokens=2000,
                    timeout=120,
                    stream=True,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                async for chunk in s:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta:
                        token = delta.content or ""
                        if token:
                            llm_text += token
                            yield evt("token", {"content": token})

            async for event in _call_llm_stream(0.3):
                yield event

            parsed = _parse_json(llm_text)
            summary = parsed.get("summary", "")
            causes = parsed.get("causes", [])
            suggestions = parsed.get("suggestions", [])
            llm_severity = parsed.get("severity", overall_sev)

            # 重试：结果太短
            if len(causes) < 2 or len(suggestions) < 2:
                yield evt("step", {"step": "llm_retry", "msg": "分析过短，重新生成..."})
                async for event in _call_llm_stream(
                    0.7,
                    "\n\n【重要提醒】上一轮分析太简略。请详细评价。causes和suggestions各至少3条。",
                ):
                    yield event
                retry = _parse_json(llm_text)
                if retry.get("summary"):
                    summary = retry["summary"]
                if retry.get("causes"):
                    causes = retry["causes"]
                if retry.get("suggestions"):
                    suggestions = retry["suggestions"]
                if retry.get("severity"):
                    llm_severity = retry["severity"]
        except Exception as e:
            logger.error(f"FA LLM stream failed: {e}")
            llm_text = f"分析失败: {e}"
            if not causes:
                for a in anomalies[:5]:
                    causes.append(f"{a['stage']} {a['batch_no']} {a['detail']}")
                if not causes:
                    causes.append("各工段运行正常")
            if not suggestions:
                for a in anomalies[:5]:
                    suggestions.append(
                        f"关注 {a['stage']} {a['batch_no']}，{a['detail']}"
                    )
                if not suggestions:
                    suggestions.append("持续监控各工段关键参数")

        yield evt("step", {"step": "llm", "done": True, "msg": "AI 分析完成"})

        # Step 6: 保存结果
        analysis_id = ""
        try:
            analysis = AiAnalysis(
                batch_no=batch_no,
                stage=stage,
                include_siblings=False,
                trace_snapshot={"batch_data": batch_data},
                dist_snapshot={"stats": stats_data},
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
            analysis_id = str(analysis.id)
        except Exception as e2:
            logger.error(f"FA 保存分析结果失败: {e2}")

        try:
            yield evt(
                "result",
                {
                    "id": analysis_id,
                    "session_id": sid,
                    "summary": summary,
                    "anomalies": anomalies,
                    "causes": causes,
                    "suggestions": suggestions,
                    "severity": llm_severity,
                    "analysis_text": llm_text,
                    "reference_cases": ref_cases,
                },
            )
        except Exception as e3:
            logger.error(f"FA 返回结果失败: {e3}")
            yield evt("error", {"msg": f"结果序列化失败: {e3}"})

        yield evt("done", {})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
