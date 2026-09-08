"""成品异常记录 AI 分类 prompt 组装。

口径经用户确认（2026-09-08，基于 2025/2026 两年 486 条真实记录归纳）：
- 异常类型 10 类固定枚举，AI 只能从中选"最主要的一个"；
- 产品枚举 = 平台 7 个产品 + 氟苯尼考预混剂 + 其他/未知；
- 批号前缀映射作为产品判断的辅助线索写入 prompt。
"""

from __future__ import annotations

from typing import Any

# 异常类型枚举（与前端图表口径一致，勿随意改名）
ANOMALY_TYPE_OPTIONS: tuple[str, ...] = (
    "检验结果超标（OOS）",
    "检验结果超趋势（OOT）",
    "杂质异常",
    "溶剂残留异常",
    "异物混入",
    "性状与外观异常",
    "稳定性考察异常",
    "微生物与污染",
    "生产与包装现场问题",
    "其他/未分类",
)

ANOMALY_TYPE_OTHER = "其他/未分类"

PRODUCT_OPTIONS: tuple[str, ...] = (
    "洛伐他汀",
    "美伐他汀",
    "霉酚酸",
    "盐酸林可霉素",
    "多拉菌素",
    "L-苯丙氨酸",
    "色氨酸",
    "氟苯尼考预混剂",
    "芬苯达唑粉",
    "其他/未知",
)

PRODUCT_OTHER = "其他/未知"

# 批号前缀 → 产品（辅助线索，AI 仍需结合描述判断）
PRODUCT_PREFIX_HINTS: dict[str, str] = {
    "LV": "洛伐他汀",
    "MV": "美伐他汀",
    "USMC": "霉酚酸",
    "USMV": "美伐他汀",
    "MC": "霉酚酸",
    "LN": "盐酸林可霉素",
    "DR": "多拉菌素",
    "FA": "L-苯丙氨酸",
    "TY": "色氨酸",
    "FL": "氟苯尼考预混剂",
    "FE": "芬苯达唑粉",
}

# 单条描述截断长度（字段原始文本通常 50-200 字）
_DESC_LIMIT = 300

_OUTPUT_SHAPE = (
    '{{"items": [{{"id": "记录ID原样返回", "product": "产品名", '
    '"anomaly_type": "异常类型", "reason": "一句话依据(≤40字)"}}]}}'
)


def _truncate_desc(text: str) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= _DESC_LIMIT:
        return text
    return text[:_DESC_LIMIT] + f"…(剩余{len(text) - _DESC_LIMIT}字省略)"


def build_classification_prompt(
    items: list[dict[str, Any]],
    *,
    anomaly_type_options: tuple[str, ...] = ANOMALY_TYPE_OPTIONS,
    product_options: tuple[str, ...] = PRODUCT_OPTIONS,
) -> str:
    """组装批量分类 prompt。

    items 每项：{"id": 记录ID, "year": 年份, "desc": 描述, "product_hint": 结构化产品线索, "source": 数据来源}
    """
    type_lines = "\n".join(f"  {index}. {name}" for index, name in enumerate(anomaly_type_options, 1))
    product_lines = "、".join(product_options)
    prefix_lines = "\n".join(
        f"  {prefix} → {product}" for prefix, product in PRODUCT_PREFIX_HINTS.items()
    )
    record_lines = []
    for item in items:
        hint = item.get("product_hint") or "（无）"
        source = item.get("source") or "（无）"
        record_lines.append(
            f"- id={item.get('id')} | 年份={item.get('year')} | 产品线索={hint} "
            f"| 数据来源={source} | 描述：{_truncate_desc(str(item.get('desc') or ''))}"
        )
    record_block = "\n".join(record_lines)
    expected_shape = _OUTPUT_SHAPE.format()

    return f"""你是原料药（API）生产企业的一名资深现场QA，从事生产现场质量管理十余年，
熟悉发酵与合成类原料药的检验（QC/IC）、稳定性考察、偏差与OOS/OOT调查、生产包装现场巡查。

请对下面 {len(items)} 条成品异常记录逐条分类，输出产品与最主要的异常类型。

【产品候选（只能选其一）】
{product_lines}

【异常类型候选（只能选其一，按主要矛盾归类）】
{type_lines}

【归类边界规则】
1. 任一检验项超出注册/内控标准 → 优先归"检验结果超标（OOS）"，即使伴随其他现象；
2. 结果合格但超出历史趋势/接近限度/压线 → "检验结果超趋势（OOT）"；
3. 有关物质/特定杂质 RRT 偏高或超标、发酵液杂质与色纯不合格 → "杂质异常"；
4. 残留溶剂超标或检出异常峰（甲苯、乙酸乙酯、乙腈、正丁醇等）→ "溶剂残留异常"；
5. 可见异物（黑渣/黑点/白点/毛发/线头/虫子/颗粒/包装内异物等，含检测溶解后发现）→ "异物混入"；
6. 颜色发黄、结块、流动性差、溶解性/澄清度/浊度异常但无明确异物主体 → "性状与外观异常"；
7. 稳定性考察（6/12/18/24/36/48个月）样品各项结果超标或超趋势 → "稳定性考察异常"；
8. 微生物限度异常、霉菌、发酵污染 → "微生物与污染"；
9. QA 现场巡查发现的生产/包装过程问题（设备故障污染、操作与混合偏差、包装破损变形、标签问题）→ "生产与包装现场问题"；
10. 无法判断 → "其他/未分类"。

【产品判断线索】
- 记录若自带产品线索（涉及产品字段/产品附件列），优先采用；
- 无线索时按批号前缀映射：{prefix_lines.replace(chr(10), '；')}
- 涉及多个批次不同产品时，选择描述中占主导的产品；实在无法判断选"其他/未知"。

【待分类记录】
{record_block}

【输出要求】
只输出一个 JSON 对象，不要 markdown 代码块，不要额外解释，shape 如下：
{expected_shape}

其中 id 必须与输入记录的 id 完全一致；product 与 anomaly_type 必须严格取自上述候选清单；reason 不超过 40 字。"""
