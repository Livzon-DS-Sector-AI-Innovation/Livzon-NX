"""成品异常 AI 聊天服务（数据问答 + 不合格项分析）。

模式镜像 hr/ai_agent_service：chat_with_tools 工具循环（最多 5 轮）+
stream_chat 流式回答；业务数据通过工具实时查询（飞书记录 + AI 分类缓存），
不落库、不回传 prompt/raw_response。

工具：
- fp_query_anomaly_records：按年份/产品/异常类型/关键词查询异常记录明细
- fp_get_anomaly_aggregation：按产品×异常类型聚合统计（即仪表盘数据）
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import (
    LLMConfigError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.llm.config import get_config
from app.modules.quality.service.finished_product_anomaly_analysis import (
    _list_year_items,
    _load_cached_classifications,
    get_dashboard_aggregation,
)
from app.modules.quality.service.finished_product_anomaly_analysis_prompt import (
    ANOMALY_TYPE_OPTIONS,
    PRODUCT_OPTIONS,
    PRODUCT_PREFIX_HINTS,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
_MAX_RESULTS = 30
_DESC_LIMIT = 300

# 支持一层嵌套大括号（如 {"name": "...", "arguments": {}}）
_QWEN_TC_RE = re.compile(
    r"call\s*\n(\{[^{}]*(?:\{[^{}]*\})*[^{}]*\})",
    re.MULTILINE,
)

FP_QUERY_RECORDS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fp_query_anomaly_records",
        "description": (
            "查询成品异常记录明细。支持按年份、月份、产品、异常类型、关键词过滤，"
            "返回记录ID、日期、产品、异常类型、不合格描述、数据来源、是否结案。"
            "用于列出/查找具体异常记录或按条件计数（如'这个月/某月有哪些异常'）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "年份（2025 或 2026），不传查全部年份",
                },
                "month": {
                    "type": "string",
                    "description": (
                        "月份，格式 YYYY-MM（如 2026-09），"
                        "按记录日期（发现时间/提交时间）过滤"
                    ),
                },
                "product": {
                    "type": "string",
                    "description": (
                        "产品名，可选：洛伐他汀/美伐他汀/霉酚酸/盐酸林可霉素/"
                        "多拉菌素/L-苯丙氨酸/色氨酸/氟苯尼考预混剂/芬苯达唑粉"
                    ),
                },
                "anomaly_type": {
                    "type": "string",
                    "description": (
                        "异常类型，可选：检验结果超标（OOS）/检验结果超趋势（OOT）/"
                        "杂质异常/溶剂残留异常/异物混入/性状与外观异常/稳定性考察异常/"
                        "微生物与污染/生产与包装现场问题/其他-未分类"
                    ),
                },
                "keyword": {
                    "type": "string",
                    "description": "描述关键词（如批号、残渣、黑渣）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数上限，默认 20，最大 30",
                },
            },
        },
    },
}

FP_AGGREGATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fp_get_anomaly_aggregation",
        "description": (
            "获取成品异常的聚合统计：各产品异常数量、产品×异常类型分布、类型总量。"
            "用于回答'有多少/哪个产品最多/各类异常占比'类问题。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "年份（2025 或 2026），不传统计全部年份",
                },
            },
        },
    },
}

ALL_TOOL_SCHEMAS = [FP_QUERY_RECORDS_SCHEMA, FP_AGGREGATION_SCHEMA]

_TOOL_LABELS = {
    "fp_query_anomaly_records": "成品异常记录",
    "fp_get_anomaly_aggregation": "成品异常统计",
}

_SYSTEM_PROMPT_TEMPLATE = """你是原料药（API）生产企业的资深现场QA，从事生产现场质量管理十余年，
熟悉发酵与合成类原料药的检验（QC/IC）、稳定性考察、偏差与OOS/OOT调查、生产包装现场巡查。
你正在通过聊天协助用户分析成品异常数据。

【当前日期】{today}
用户说"这个月/本月/最近"时，按当前日期换算成具体月份（本月={month}），并使用工具的 month 参数过滤；
若该月无记录，应说明并给出最近一个月的情况。

【你的能力】
1. 通过工具查询成品异常记录与聚合统计（数据实时来自飞书多维表格）；
2. 基于查询结果做资深 QA 视角的分析：现象归纳、可能原因（人机料法环）、处置建议、趋势提醒。

【数据范围】2025/2026 两年成品异常记录（约 486 条），字段包括：不合格项目描述、
涉及产品、数据来源（QC检测/IC检测/QA）、是否结案、相关照片等附件。
每条记录已由 AI 标注"异常类型"，枚举为：
{type_options}

【日期语义（重要，避免误导）】
- 2025 表的"发现时间"= 异常发现日期，可信；
- 2026 表的"提交时间"= 记录录入时间（该表 2026-09-08 才批量导入，历史记录的提交时间
  全部集中在导入日），不代表异常发生时间。因此：
  1) 用户问"这个月/某月"时，工具的 month 过滤基于记录日期字段，回答时必须说明口径：
     "2025 年按发现时间、2026 年按录入时间（≠异常发生时间，发生时间需结合批号判断）"；
  2) 2026 批号含时间线索（如 MC-2601xx 中 2601 为年序），可辅助说明大致期间；
  3) 不要把 2026 年"9 月 N 条"表述成"9 月发生的异常"，应表述为"9 月录入/导入的记录"。

【产品枚举与批号前缀】
{product_lines}
（批号前缀映射：{prefix_hints}）

【不合格项分析要求】
用户要求分析某条不合格项时，先用工具查到该记录全文，再按以下结构回答：
1. 现象归纳：不合格项的核心问题与涉及批次；
2. 可能原因：从人、机、料、法、环五个维度给出 2-4 条可能性，并按可能性排序；
3. 处置建议：现场可执行的处置与调查动作（含是否需要启动偏差/OOS 调查）；
4. 后续关注：需要跟踪的趋势或验证动作。

【回答要求】
- 只基于工具查到的真实数据回答，禁止编造批号、数字或结论；
- 数据问题优先调用工具查询；一个疑问通常 1-3 次工具调用即可，不要反复查询相同条件；
- 回答用中文，简洁、结构化（可用 markdown 列表）。"""


def build_chat_system_prompt() -> str:
    type_lines = "、".join(ANOMALY_TYPE_OPTIONS)
    product_lines = "、".join(PRODUCT_OPTIONS)
    prefix_hints = "；".join(
        f"{prefix}→{product}" for prefix, product in PRODUCT_PREFIX_HINTS.items()
    )
    now = datetime.now()
    return _SYSTEM_PROMPT_TEMPLATE.format(
        type_options=type_lines,
        product_lines=product_lines,
        prefix_hints=prefix_hints,
        today=now.strftime("%Y-%m-%d"),
        month=now.strftime("%Y-%m"),
    )


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, name)


def _parse_qwen_tool_calls(content: str) -> list[dict[str, Any]] | None:
    """解析 Qwen/DashScope 文本格式的工具调用（与 hr 同款兼容）。"""
    if not content or "call" not in content[:200]:
        return None
    matches = _QWEN_TC_RE.findall(content)
    if not matches:
        return None
    tool_calls = []
    for index, json_str in enumerate(matches):
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            continue
        if "name" in parsed:
            tool_calls.append(
                {
                    "id": f"qwen_tc_{index}",
                    "type": "function",
                    "function": {
                        "name": parsed["name"],
                        "arguments": json.dumps(parsed.get("arguments", {})),
                    },
                }
            )
    return tool_calls or None


# 各年子表的记录日期字段（"这个月/某月"筛选依据）
_YEAR_DATE_FIELD = {2025: "发现时间", 2026: "提交时间"}


def _record_date_millis(item: dict[str, Any], year: int) -> int | None:
    """取记录的日期毫秒值（飞书 DateTime/CreatedTime 为 ms 数字或数字字符串）。"""
    field = _YEAR_DATE_FIELD.get(year)
    if not field:
        return None
    value = item.get(field)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return None


async def _tool_query_records(db: AsyncSession, arguments: dict[str, Any]) -> str:
    year = arguments.get("year")
    years = [int(year)] if int(year or 0) in (2025, 2026, 2027, 2028) else [2025, 2026]
    month_filter = str(arguments.get("month") or "").strip()
    product_filter = str(arguments.get("product") or "").strip()
    type_filter = str(arguments.get("anomaly_type") or "").strip().replace(
        "其他-未分类", "其他/未分类"
    )
    keyword = str(arguments.get("keyword") or "").strip()
    limit = max(1, min(int(arguments.get("limit") or 20), _MAX_RESULTS))

    matched: list[dict[str, Any]] = []
    total_matched = 0
    for item_year in years:
        try:
            items = await _list_year_items(db, item_year)
        except Exception:
            continue
        cached = await _load_cached_classifications(
            db, item_year, [str(i.get("record_id") or "") for i in items]
        )
        for item in items:
            record_id = str(item.get("record_id") or "")
            desc = str(item.get("不合格项目描述") or item.get("不合格项目") or "")
            classification = cached.get(record_id)
            payload = (classification or {}).get("payload") or {}
            product = str(payload.get("product") or "") or (
                f"{item_year}年待分析"
            )
            anomaly_type = str(payload.get("anomaly_type") or "") or "待分析"
            if product_filter and product_filter != product:
                continue
            if type_filter and type_filter != anomaly_type:
                continue
            if keyword and keyword not in desc:
                continue
            date_millis = _record_date_millis(item, item_year)
            if month_filter:
                if date_millis is None:
                    continue
                if (
                    datetime.fromtimestamp(date_millis / 1000).strftime("%Y-%m")
                    != month_filter
                ):
                    continue
            total_matched += 1
            if len(matched) >= limit:
                continue
            date_text = (
                datetime.fromtimestamp(date_millis / 1000).strftime("%Y-%m-%d")
                if date_millis
                else ""
            )
            matched.append(
                {
                    "id": record_id,
                    "year": item_year,
                    "date": date_text,
                    "product": product,
                    "anomaly_type": anomaly_type,
                    "desc": desc[:_DESC_LIMIT],
                    "source": str(item.get("数据来源") or ""),
                    "closed": str(item.get("是否结案") or ""),
                }
            )
    return json.dumps(
        {"total_matched": total_matched, "returned": matched},
        ensure_ascii=False,
    )


async def _tool_aggregation(db: AsyncSession, arguments: dict[str, Any]) -> str:
    year = arguments.get("year")
    year_int = int(year or 0)
    data = await get_dashboard_aggregation(
        db, year_int if year_int in (2025, 2026, 2027, 2028) else None
    )
    return json.dumps(data, ensure_ascii=False)


async def execute_tool_call(
    db: AsyncSession, tool_name: str, arguments: dict[str, Any]
) -> str:
    try:
        if tool_name == "fp_query_anomaly_records":
            return await _tool_query_records(db, arguments)
        if tool_name == "fp_get_anomaly_aggregation":
            return await _tool_aggregation(db, arguments)
        return json.dumps(
            {"success": False, "error": f"未知工具: {tool_name}"},
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("Tool execution failed", extra={"tool": tool_name})
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """粗略估算 token：中文按 1、其他字符按 0.25。"""
    total = 0
    for message in messages:
        content = str(message.get("content") or "")
        cjk = sum(1 for ch in content if "一" <= ch <= "鿿")
        total += cjk + int((len(content) - cjk) * 0.25)
    return total


async def run_anomaly_chat_loop(
    db: AsyncSession,
    messages: list[dict[str, Any]],
    system_prompt: dict[str, Any],
) -> AsyncGenerator[dict[str, Any], None]:
    """成品异常 AI 聊天循环：工具调用（≤5 轮）→ 流式最终回答。"""
    llm_config = await get_config("text")
    enable_thinking = getattr(llm_config, "enable_thinking", None)

    full_messages: list[dict[str, Any]] = [system_prompt] + list(messages)
    if _estimate_tokens(full_messages) > 24000:
        full_messages = [full_messages[0]] + list(full_messages[1:][-10:])
        yield {"type": "status", "text": "对话较长，已压缩早期上下文。"}

    for round_index in range(MAX_TOOL_ROUNDS):
        # 每轮开始前先下发状态，保证浏览器秒级收到事件
        yield {
            "type": "status",
            "text": f"AI 正在理解问题并决定查询（第 {round_index + 1} 步）…",
        }
        try:
            response = await llm_client.chat_with_tools(
                full_messages,
                tools=ALL_TOOL_SCHEMAS,
                temperature=0.3,
                max_tokens=4096,
                enable_thinking=enable_thinking,
            )
        except (LLMRateLimitError, LLMProviderError, LLMConfigError):
            raise

        reasoning = response.get("reasoning_content")
        if reasoning:
            yield {"type": "reasoning", "text": reasoning}

        tool_calls = response.get("tool_calls")
        if not tool_calls and response.get("content"):
            tool_calls = _parse_qwen_tool_calls(response["content"])
        if not tool_calls:
            break

        full_messages.append(
            {
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            try:
                arguments = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError:
                arguments = {}
            yield {"type": "status", "text": f"正在查询{_tool_label(tool_name)}..."}
            result = await execute_tool_call(db, tool_name, arguments)
            full_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                }
            )
        yield {"type": "status", "text": "正在分析数据..."}

    try:
        async for chunk in llm_client.stream_chat(
            full_messages,
            max_tokens=4096,
            enable_thinking=False,
        ):
            yield chunk
    except (LLMRateLimitError, LLMProviderError, LLMConfigError):
        raise

    yield {"type": "done"}
