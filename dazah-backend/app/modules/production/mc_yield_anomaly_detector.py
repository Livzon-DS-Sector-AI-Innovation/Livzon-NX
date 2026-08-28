"""MC 霉酚酸 — 收率异常自动检测引擎

飞书同步完成后自动扫描三工段收率数据，基于 3 月移动窗口 IQR 规则判断异常，
仅异常批次调用 LLM 分析，结果写入 ai_analysis 表。
独立于手动 AI 分析，互不影响。
"""
import json
import logging
import re
import uuid as _uuid
from datetime import date, timedelta
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionUserMessageParam
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_config
from app.modules.production.ai_analysis_models import AiAnalysis

logger = logging.getLogger(__name__)

# ── 工段 → (表名, 收率字段) 映射 ──
STAGE_TABLE = {
    "sub_tank": ("sub_tank_records", "yield_rate"),
    "extraction": ("extraction_records", "yield_rate"),
    "refinement": ("mc_refinement_records", "single_step_yield"),
}

# 阶段中文标签
STAGE_LABELS_ZH = {
    "sub_tank": "粗提分罐",
    "extraction": "提取",
    "refinement": "二次精制",
}

# 最小样本量
MIN_SAMPLE_SIZE = 5
# 移动窗口：当前月 + 前 N 个月
ROLLING_MONTHS = 2

# ── JSON 解析工具（同 ai_analysis_api.py） ──


def _parse_json(text: str) -> dict[str, Any]:
    t = text.strip()
    if t.startswith("```json"):
        t = t[7:]
    if t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    t = t.strip()
    try:
        parsed = json.loads(t)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    for suffix in ['"}]', '"]}]', "}]", "]}]", "}", '"}}', '"}', '"]}']:
        try:
            parsed = json.loads(t + suffix)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    result = {}
    m = re.search(r'"summary"\s*:\s*"([^"]*)"', t)
    if m:
        result["summary"] = m.group(1)
    m = re.search(r'"severity"\s*:\s*"([^"]*)"', t)
    if m:
        result["severity"] = m.group(1)
    for key in ("causes", "suggestions"):
        try:
            start = t.find(f'"{key}"')
            if start > -1:
                end = t.find("]", start)
                items = re.findall(r'"([^"]*)"', t[start:end])
                if items:
                    result[key] = items
        except Exception:
            pass
    return result


# ═══════════════════════════════════════════════════════
# 步骤1 — 扫描新批次（含日期，供后续移动窗口用）
# ═══════════════════════════════════════════════════════


async def scan_new_batches(session: AsyncSession) -> list[dict[str, Any]]:
    """扫描三工段中有收率但尚未被自动分析过的批次，同时返回批次日期"""
    rows_raw = (
        await session.execute(
            text("""
        SELECT 'sub_tank' AS stage, st.batch_no, st.yield_rate,
               rb.produce_date AS batch_date
        FROM production.sub_tank_records st
        JOIN production.refining_batches rb ON rb.batch_no = st.parent_batch AND
        rb.is_deleted = false
        WHERE st.yield_rate IS NOT NULL AND st.yield_rate > 0 AND st.is_deleted = false
        AND NOT EXISTS (
            SELECT 1 FROM production.ai_analysis aa
            WHERE aa.batch_no = st.batch_no AND aa.stage = 'sub_tank'
            AND aa.created_by = 'auto' AND aa.is_deleted = false
        )
        UNION ALL
        SELECT 'extraction', batch_no, yield_rate, extract_date
        FROM production.extraction_records
        WHERE yield_rate IS NOT NULL AND yield_rate > 0 AND is_deleted = false
        AND NOT EXISTS (
            SELECT 1 FROM production.ai_analysis aa
            WHERE aa.batch_no = extraction_records.batch_no AND aa.stage = 'extraction'
            AND aa.created_by = 'auto' AND aa.is_deleted = false
        )
        UNION ALL
        SELECT 'refinement', batch_no, single_step_yield, input_date
        FROM production.mc_refinement_records
        WHERE single_step_yield IS NOT NULL AND single_step_yield > 0 AND is_deleted =
        false
        AND NOT EXISTS (
            SELECT 1 FROM production.ai_analysis aa
            WHERE aa.batch_no = mc_refinement_records.batch_no AND aa.stage =
        'refinement'
            AND aa.created_by = 'auto' AND aa.is_deleted = false
        )
        ORDER BY stage, batch_no
    """)
        )
    ).fetchall()
    return [
        {
            "stage": r.stage,
            "batch_no": r.batch_no,
            "yield_rate": float(r.yield_rate),
            "batch_date": r.batch_date,  # 可能是 None
        }
        for r in rows_raw
    ]


# ═══════════════════════════════════════════════════════
# 步骤2 — SQL 统计计算（3 月移动窗口）
# ═══════════════════════════════════════════════════════


async def _compute_stage_iqr(
    session: AsyncSession,
    stage: str,
    near_date: date | None,
) -> dict[str, Any]:
    """计算工段在 near_date 前 3 个月内的收率 IQR（移动窗口）"""
    table, yield_col = STAGE_TABLE[stage]

    # 日期过滤：near_date - 3个月 → near_date
    # 不同工段用不同日期字段
    date_field = {
        "sub_tank": "rb.produce_date",
        "extraction": "extract_date",
        "refinement": "input_date",
    }[stage]

    if near_date is None:
        near_date = date.today()
    window_start = near_date - timedelta(days=30 * (ROLLING_MONTHS + 1))  # 含当前月

    # 子查询：sub_tank 需要 JOIN refining_batches 拿日期
    if stage == "sub_tank":
        subquery = f"""
            SELECT st.{yield_col} AS y
            FROM production.{table} st
            JOIN production.refining_batches rb ON rb.batch_no = st.parent_batch AND
        rb.is_deleted = false
            WHERE st.{yield_col} IS NOT NULL AND st.{yield_col} > 0 AND st.is_deleted =
        false
            AND {date_field} >= :ws AND {date_field} <= :nd
        """
    else:
        subquery = f"""
            SELECT {yield_col} AS y FROM production.{table}
            WHERE {yield_col} IS NOT NULL AND {yield_col} > 0 AND is_deleted = false
            AND {date_field} >= :ws AND {date_field} <= :nd
        """

    rows = (
        await session.execute(
            text(f"""
        SELECT COUNT(*) AS n,
               ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY y)::numeric, 1) AS q1,
               ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY y)::numeric, 1) AS
        median,
               ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY y)::numeric, 1) AS q3
        FROM ({subquery}) t
    """),
            {"ws": window_start, "nd": near_date},
        )
    ).fetchone()

    if rows is None:
        return {
            "n": 0,
            "median": 0.0,
            "q1": 0.0,
            "q3": 0.0,
            "iqr": 0.0,
            "window_start": window_start.isoformat(),
            "window_end": near_date.isoformat(),
        }
    q1 = float(rows.q1 or 0)
    q3 = float(rows.q3 or 0)
    median = float(rows.median or 0)
    iqr = round(q3 - q1, 1)
    return {
        "n": rows.n or 0,
        "median": median,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "window_start": window_start.isoformat(),
        "window_end": near_date.isoformat(),
    }


async def _compute_similar_range(
    session: AsyncSession, stage: str, yield_rate: float
) -> dict[str, Any]:
    """同工段收率 ±2% 范围内的历史批次统计"""
    table, yield_col = STAGE_TABLE[stage]
    low = round(yield_rate - 2, 1)
    high = round(yield_rate + 2, 1)
    row = (
        await session.execute(
            text(f"""
        SELECT COUNT(*) AS cnt,
               ROUND(AVG(y)::numeric, 1) AS avg_yr,
               ROUND(MIN(y)::numeric, 1) AS min_yr,
               ROUND(MAX(y)::numeric, 1) AS max_yr
        FROM (
            SELECT {yield_col} AS y FROM production.{table}
            WHERE {yield_col} IS NOT NULL AND {yield_col} > 0 AND is_deleted = false
            AND {yield_col} BETWEEN :low AND :high
        ) t
    """),
            {"low": low, "high": high},
        )
    ).fetchone()
    if row is None:
        return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": row.cnt or 0,
        "avg": float(row.avg_yr or 0),
        "min": float(row.min_yr or 0),
        "max": float(row.max_yr or 0),
    }


async def _compute_equipment_trend(
    session: AsyncSession, stage: str, batch_no: str
) -> list[dict[str, Any]]:
    """设备/工段近3月收率列表（最近 20 条）"""
    table, yield_col = STAGE_TABLE[stage]
    date_fields = {
        "sub_tank": "created_at",
        "extraction": "extract_date",
        "refinement": "input_date",
    }
    date_col = date_fields[stage]

    tank_filter = ""
    params = {}
    if stage == "refinement":
        tank_row = (
            await session.execute(
                text(
                    "SELECT dissolution_tank, crystallization_tank FROM production.mc_refinement_records "  # noqa: E501
                    "WHERE batch_no = :bn AND is_deleted = false"
                ),
                {"bn": batch_no},
            )
        ).fetchone()
        if tank_row and (tank_row.dissolution_tank or tank_row.crystallization_tank):
            tank = tank_row.dissolution_tank or tank_row.crystallization_tank
            tank_filter = (
                "AND (dissolution_tank = :tank OR crystallization_tank = :tank)"
            )
            params["tank"] = tank

    rows = (
        await session.execute(
            text(f"""
        SELECT batch_no, {yield_col} AS yield_rate
        FROM production.{table}
        WHERE {yield_col} IS NOT NULL AND {yield_col} > 0 AND is_deleted = false
        AND {date_col} >= CURRENT_DATE - INTERVAL '3 months'
        {tank_filter}
        ORDER BY {date_col} DESC
        LIMIT 20
    """),
            params,
        )
    ).fetchall()
    return [{"batch_no": r.batch_no, "yield_rate": float(r.yield_rate)} for r in rows]


async def _compute_downstream_comparison(
    session: AsyncSession, stage: str, batch_no: str
) -> list[dict[str, Any]]:
    """通过 batch_lineage 找下游批次，对比其收率与工段历史均值"""
    ds_rows = (
        await session.execute(
            text("""
        SELECT bl.downstream_type, bl.downstream_batch,
               COALESCE(st.yield_rate, er.yield_rate, rr.single_step_yield) AS ds_yield
        FROM production.batch_lineage bl
        LEFT JOIN production.sub_tank_records st
            ON st.batch_no = bl.downstream_batch AND bl.downstream_type = 'sub_tank'
        LEFT JOIN production.extraction_records er
            ON er.batch_no = bl.downstream_batch AND bl.downstream_type = 'extraction'
        LEFT JOIN production.mc_refinement_records rr
            ON rr.batch_no = bl.downstream_batch AND bl.downstream_type = 'refinement'
        WHERE bl.upstream_batch = :bn AND bl.upstream_type = :st
    """),
            {"bn": batch_no, "st": stage},
        )
    ).fetchall()

    result = []
    for r in ds_rows:
        ds_stage = r.downstream_type
        ds_batch = r.downstream_batch
        ds_yield = float(r.ds_yield) if r.ds_yield is not None else None
        if ds_stage in STAGE_TABLE:
            ds_table, ds_yield_col = STAGE_TABLE[ds_stage]
            mean_row = (
                await session.execute(
                    text(f"""
                SELECT ROUND(AVG(y)::numeric, 1) AS mean_yr, COUNT(*) AS n
                FROM (
                    SELECT {ds_yield_col} AS y FROM production.{ds_table}
                    WHERE {ds_yield_col} IS NOT NULL AND {ds_yield_col} > 0 AND
        is_deleted = false
                ) t
            """)
                )
            ).fetchone()
            if mean_row is None:
                mean_yr = 0.0
                n = 0
            else:
                mean_yr = float(mean_row.mean_yr or 0)
                n = mean_row.n or 0
        else:
            mean_yr = 0
            n = 0
        result.append(
            {
                "downstream_type": ds_stage,
                "downstream_batch": ds_batch,
                "yield_rate": ds_yield,
                "stage_mean": mean_yr,
                "stage_n": n,
            }
        )
    return result


# ═══════════════════════════════════════════════════════
# 步骤3 — 异常判定（纯规则，不调 LLM）
# ═══════════════════════════════════════════════════════


def judge_anomaly_severity(yield_rate: float, median: float, iqr: float) -> str | None:
    """
    < median - 1.5 * IQR → high
    < median - IQR       → medium
    否则                   → None (normal，跳过)
    """
    if iqr <= 0:
        return None
    if yield_rate < median - 1.5 * iqr:
        return "high"
    if yield_rate < median - iqr:
        return "medium"
    return None


# ═══════════════════════════════════════════════════════
# 步骤4 — 查历史类似案例
# ═══════════════════════════════════════════════════════


async def _get_similar_cases(
    session: AsyncSession, stage: str, severity: str, limit: int = 3
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                "SELECT id, batch_no, stage, summary, severity FROM production.ai_analysis "  # noqa: E501
                "WHERE stage = :st AND severity = :sev AND message_seq = 0 AND is_deleted = false "  # noqa: E501
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"st": stage, "sev": severity, "lim": limit},
        )
    ).fetchall()
    return [
        {
            "id": str(r.id),
            "batch_no": r.batch_no,
            "stage": r.stage,
            "summary": r.summary,
            "severity": r.severity,
        }
        for r in rows
    ]


# ═══════════════════════════════════════════════════════
# 步骤5 — Prompt + LLM + 写入
# ═══════════════════════════════════════════════════════


def _build_auto_detect_prompt(
    batch_no: str,
    stage: str,
    yield_rate: float,
    severity: str,
    stage_iqr: dict[str, Any],
    similar_range: dict[str, Any],
    equipment_trend: list[dict[str, Any]],
    downstream_comparison: list[dict[str, Any]],
    ref_cases: list[dict[str, Any]],
) -> str:
    label = STAGE_LABELS_ZH.get(stage, stage)
    median = stage_iqr["median"]
    deviation = round(yield_rate - median, 1)
    direction = "低于" if deviation < 0 else "高于"
    window_info = f"（移动窗口: {stage_iqr.get('window_start', '?')} → {stage_iqr.get('window_end', '?')}）"  # noqa: E501

    lines = [
        "你是制药工艺分析师，拥有霉酚酸(MC)生产线深度知识。分析中必须使用中文工段名称（如粗提分罐、萃取、精制），禁止出现sub_tank/extraction/refinement等英文工段代码。请针对自动检测到的收率异常进行分析。",
        "",
        "=== 批次信息 ===",
        f"工段: {label}({stage})",
        f"批号: {batch_no}",
        f"收率: {yield_rate}%",
        f"异常等级: {severity}",
        "",
        "=== 工段历史统计 ===",
        f"统计范围: {window_info}",
        f"窗口内批次: {stage_iqr['n']} 条",
        f"中位数收率: {median}%",
        f"Q1: {stage_iqr['q1']}% / Q3: {stage_iqr['q3']}%",
        f"IQR: {stage_iqr['iqr']}",
        f"偏离: 本批收率 {direction} 中位数 {abs(deviation)} 个百分点",
    ]

    if similar_range["count"] > 0:
        lines.extend(
            [
                "",
                "=== 同收率范围(±2%)历史批次 ===",
                f"共 {similar_range['count']} 批，收率范围 [{similar_range['min']}%, {similar_range['max']}%]",  # noqa: E501
                f"均值: {similar_range['avg']}%",
            ]
        )

    if equipment_trend:
        trend_text = "\n".join(
            f"  {r['batch_no']}: {r['yield_rate']}%" for r in equipment_trend[:10]
        )
        lines.extend(
            [
                "",
                "=== 同工段/设备近3月收率趋势(最近10条) ===",
                trend_text,
            ]
        )

    if downstream_comparison:
        lines.append("\n=== 下游工段收率对比 ===")
        for d in downstream_comparison:
            ds_label = STAGE_LABELS_ZH.get(d["downstream_type"], d["downstream_type"])
            y = f"{d['yield_rate']}%" if d["yield_rate"] is not None else "无数据"
            lines.append(
                f"  {ds_label} {d['downstream_batch']}: 收率 {y} "
                f"(该工段历史均值 {d['stage_mean']}%, 共 {d['stage_n']} 批)"
            )
    else:
        lines.append("\n=== 下游工段 ===\n（该批次暂无下游数据，无法对比）")

    if ref_cases:
        lines.append("\n=== 历史类似案例 ===")
        for c in ref_cases:
            lines.append(f"  [{c['severity']}] {c['batch_no']}: {c.get('summary', '')}")
    else:
        lines.append("\n=== 历史类似案例 ===\n（无，这是该工段该严重度的首次检测）")

    lines.append(f"""
请以 JSON 格式返回详细分析结果：
{{
  "summary": "一句话摘要（含关键数据，40字内）",
  "causes": ["原因1（从工艺角度分析）", "原因2", "原因3"],
  "suggestions": ["建议1（具体可操作）", "建议2", "建议3"],
  "severity": "{severity}"
}}

分析要求：
- 必须使用中文工段名称（粗提分罐、萃取、精制），禁止出现英文工段代码
- 先指出收率偏离中位数的程度和方向
- 注意控制线基于近3个月移动窗口，不是全量历史数据
- 结合设备趋势判断是单点波动还是持续下滑
- 如有下游数据，对比下游收率判断问题出在上游输入还是本工段操作
- 参考历史类似案例给出针对性建议
- causes 和 suggestions 各至少 3 条
只返回JSON。""")
    return "\n".join(lines)


async def _call_llm_and_save(
    session: AsyncSession,
    batch_no: str,
    stage: str,
    yield_rate: float,
    severity: str,
    stage_iqr: dict[str, Any],
    similar_range: dict[str, Any],
    equipment_trend: list[dict[str, Any]],
    downstream_comparison: list[dict[str, Any]],
    ref_cases: list[dict[str, Any]],
) -> AiAnalysis | None:
    """调 LLM 分析并写入 ai_analysis 表"""
    cfg = await get_config("text")
    prompt = _build_auto_detect_prompt(
        batch_no,
        stage,
        yield_rate,
        severity,
        stage_iqr,
        similar_range,
        equipment_trend,
        downstream_comparison,
        ref_cases,
    )

    llm_text = ""
    summary = ""
    causes = []
    suggestions = []
    try:
        client = AsyncOpenAI(
            base_url=cfg.api_base_url or "https://newapi.livzon.cn/v1",
            api_key=cfg.api_key or "",
        )
        msgs: list[ChatCompletionUserMessageParam] = [
            {"role": "user", "content": prompt}
        ]
        resp = await client.chat.completions.create(
            model=cfg.model_name or "deepseek-v4-pro",
            messages=msgs,
            temperature=0.3,
            max_tokens=3000,
            timeout=120,
            extra_body={"thinking": {"type": "disabled"}},
        )
        llm_text = resp.choices[0].message.content or ""
        parsed = _parse_json(llm_text)
        summary = parsed.get("summary", "")
        causes = parsed.get("causes", [])
        suggestions = parsed.get("suggestions", [])

        if len(causes) < 3 or len(suggestions) < 3:
            logger.warning(f"[异常检测] LLM 分析过短 {batch_no}，重试...")
            msgs2: list[ChatCompletionUserMessageParam] = [
                {
                    "role": "user",
                    "content": prompt
                    + "\n\n【重要提醒】请详细分析，causes 和 suggestions 各至少 3 条。",
                }
            ]
            resp2 = await client.chat.completions.create(
                model=cfg.model_name or "deepseek-v4-pro",
                messages=msgs2,
                temperature=0.7,
                max_tokens=3000,
                timeout=120,
                extra_body={"thinking": {"type": "disabled"}},
            )
            llm_text = resp2.choices[0].message.content or ""
            parsed2 = _parse_json(llm_text)
            if parsed2.get("summary"):
                summary = parsed2["summary"]
            if parsed2.get("causes"):
                causes = parsed2["causes"]
            if parsed2.get("suggestions"):
                suggestions = parsed2["suggestions"]
    except Exception as e:
        logger.error(f"[异常检测] LLM 调用失败 {batch_no}: {e}")
        label = STAGE_LABELS_ZH.get(stage, stage)
        summary = f"{label}{batch_no} 收率{yield_rate}%异常(LLM调用失败)"
        causes = [
            f"收率{yield_rate}%, 低于中位数{stage_iqr['median']}%",
            "LLM调用失败,无法自动分析",
        ]
        suggestions = ["建议人工复核该批次收率数据", "检查飞书台账原始记录是否准确"]

    sid = str(_uuid.uuid4())
    label = STAGE_LABELS_ZH.get(stage, stage)
    anomalies = [
        {
            "stage": label,
            "batch_no": batch_no,
            "metric": "yield_rate",
            "value": round(yield_rate, 1),
            "benchmark": round(stage_iqr["median"], 1),
            "severity": severity,
            "detail": (
                f"收率{yield_rate}%{'低于' if yield_rate < stage_iqr['median'] else '高于'}"  # noqa: E501
                f"移动窗口中位数{stage_iqr['median']}%, IQR={stage_iqr['iqr']}"
            ),
        }
    ]

    analysis = AiAnalysis(
        batch_no=batch_no,
        stage=stage,
        include_siblings=False,
        trace_snapshot=None,
        dist_snapshot=None,
        anomalies=anomalies,
        llm_prompt=prompt,
        llm_response=llm_text,
        summary=summary,
        causes=causes,
        suggestions=suggestions,
        severity=severity,
        model_used=cfg.model_name or "",
        reference_cases=[c["id"] for c in ref_cases],
        created_by="auto",
        session_id=sid,
        message_seq=0,
        role="system",
    )
    session.add(analysis)
    await session.commit()
    logger.info(f"[异常检测] {batch_no}({stage}) severity={severity}, session={sid}")
    return analysis


# ═══════════════════════════════════════════════════════
# 主编排函数
# ═══════════════════════════════════════════════════════


async def run_anomaly_detection(session: AsyncSession) -> dict[str, Any]:
    """执行一次完整的收率异常自动检测，返回汇总"""
    new_batches = await scan_new_batches(session)
    if not new_batches:
        return {
            "scanned": 0,
            "detected": 0,
            "high": 0,
            "medium": 0,
            "skipped_normal": 0,
            "errors": 0,
            "details": [],
        }

    # 按 (stage, year-month) 缓存 IQR
    iqr_cache: dict[str, dict[str, Any]] = {}

    def _cache_key(stage: str, batch_date: date | None) -> str:
        if batch_date is None:
            return f"{stage}:unknown"
        return f"{stage}:{batch_date.year}-{batch_date.month:02d}"

    async def _get_iqr(stage: str, batch_date: date | None) -> dict[str, Any]:
        key = _cache_key(stage, batch_date)
        if key not in iqr_cache:
            iqr_cache[key] = await _compute_stage_iqr(session, stage, batch_date)
        return iqr_cache[key]

    detected = 0
    high_count = 0
    medium_count = 0
    skipped_normal = 0
    errors = 0
    details = []

    for batch in new_batches:
        try:
            stage = batch["stage"]
            yr = batch["yield_rate"]
            bn = batch["batch_no"]
            batch_date = batch.get("batch_date")

            stage_stats = await _get_iqr(stage, batch_date)

            if stage_stats["n"] < MIN_SAMPLE_SIZE:
                logger.info(
                    f"[异常检测] {stage} 窗口样本不足 ({stage_stats['n']}<{MIN_SAMPLE_SIZE}), 跳过 {bn}"  # noqa: E501
                )
                skipped_normal += 1
                continue

            severity = judge_anomaly_severity(
                yr, stage_stats["median"], stage_stats["iqr"]
            )
            if severity is None:
                skipped_normal += 1
                continue

            detected += 1
            if severity == "high":
                high_count += 1
            else:
                medium_count += 1

            similar_range = await _compute_similar_range(session, stage, yr)
            equipment_trend = await _compute_equipment_trend(session, stage, bn)
            downstream_comp = await _compute_downstream_comparison(session, stage, bn)
            ref_cases = await _get_similar_cases(session, stage, severity, limit=3)

            await _call_llm_and_save(
                session,
                bn,
                stage,
                yr,
                severity,
                stage_stats,
                similar_range,
                equipment_trend,
                downstream_comp,
                ref_cases,
            )
            details.append(
                {"batch_no": bn, "stage": stage, "severity": severity, "yield_rate": yr}
            )
        except Exception as e:
            logger.exception(
                f"[异常检测] 批次 {batch.get('batch_no', '?')} 检测失败: {e}"
            )
            errors += 1

    return {
        "scanned": len(new_batches),
        "detected": detected,
        "high": high_count,
        "medium": medium_count,
        "skipped_normal": skipped_normal,
        "errors": errors,
        "details": details,
    }
