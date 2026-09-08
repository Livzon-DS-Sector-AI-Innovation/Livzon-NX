"""验证方案/报告 AI 审核提示词模板。

prompt 明确要求模型仅基于提供的原文输出、禁止编造，引用必须给出原文片段
（quote），供后端做原文包含校验（quote_verified）。

三类提示词：
- P1 总审核（build_review_prompt）：方案↔报告互查/数值/一致性/规范性 + 用户关注点
- P2 关键依据筛选（build_basis_selection_prompt）：从引用命中的依据中选实质相关者
- P3 正文一致性比对（build_content_compare_prompt）：验证文档正文 vs 依据正文
"""

from __future__ import annotations

from typing import Any

FINDING_CATEGORIES = [
    "reference_missing",
    "version_mismatch",
    "plan_report_mismatch",
    "content_consistency",
    "format_issue",
    "numeric_check",
    "basis_content_mismatch",
]
SEVERITY_LEVELS = ["high", "medium", "low"]

# 单份正文输入 LLM 的最大字符数（超长截断，保留开头+结尾）
PLAN_TEXT_LIMIT = 12000
REPORT_TEXT_LIMIT = 12000
TAIL_KEEP = 2000
# 大文档分块审核：每块字符数与块间重叠（防跨块边界漏审）
CHUNK_SIZE = 10000
CHUNK_OVERLAP = 500
# 依据正文比对时的单份依据正文上限
BASIS_TEXT_LIMIT = 20000
# 关键依据筛选时的单份依据摘要长度
BASIS_DIGEST_LEN = 500
# 正文比对一次审核最多比对的依据份数
MAX_CONTENT_COMPARE_BASES = 5


def split_chunks(
    text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[dict[str, Any]]:
    """超长正文按段落边界分块（块间重叠 overlap 字符防边界漏审）。

    返回 [{"text": 块文本, "seq": 块序号, "total": 总块数}]；短文本返回单块。
    """
    text = text or ""
    if not text.strip():
        return []
    if len(text) <= size:
        return [{"text": text, "seq": 1, "total": 1}]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # 尽量在换行处切，避免截断段落/句子
        if end < len(text):
            newline = text.rfind("\n", start + size - 800, end)
            if newline > start:
                end = newline + 1
        chunks.append(text[start:end])
        start = end - overlap if end < len(text) else end
    total = len(chunks)
    return [
        {"text": chunk, "seq": i + 1, "total": total}
        for i, chunk in enumerate(chunks)
    ]


def _truncate_text(text: str, limit: int, tail: int = TAIL_KEEP) -> str:
    """超长正文截断：保留开头主体 + 结尾（结论/判定标准常在尾部）。"""
    if len(text) <= limit:
        return text
    return (
        f"{text[: limit - tail]}\n"
        f"……【中间内容因长度限制省略，共省略{len(text) - limit}字】……\n"
        f"{text[-tail:]}"
    )


def _format_identity(identity: dict[str, Any]) -> str:
    items = [f"{key}={value}" for key, value in identity.items() if value]
    return "；".join(items) if items else "未提取到身份信息"


def _focus_points_section(focus_points: str | None) -> list[str]:
    """用户特别关注点段（非空时逐条强调）。"""
    if not focus_points or not focus_points.strip():
        return []
    return [
        "【用户特别关注点】本次审核除固定维度外，请重点核查以下内容：\n"
        + focus_points.strip()
    ]


def build_review_prompt(
    *,
    plan_text: str | None,
    report_text: str | None,
    reference_summary: list[dict[str, Any]],
    plan_identity: dict[str, Any] | None = None,
    report_identity: dict[str, Any] | None = None,
    focus_points: str | None = None,
    quality_data_summary: list[dict[str, Any]] | None = None,
) -> str:
    """组装一次 AI 语义审核的完整 prompt。

    引用核对结果（reference_summary）由代码比对生成，作为事实输入供模型引用，
    模型不得自行判断引用是否存在/版本新旧。
    focus_points 为用户输入的特别关注点，与默认维度一并生效。
    quality_data_summary 为相关偏差/变更摘要（代码检索，事实输入）。
    """
    parts: list[str] = [
        "你是原料药工厂质量管理专家，负责对验证方案（VP）与验证报告（VR）做合规审核。",
        "请仅基于下面提供的原文核对以下内容，没有证据的问题不要提出，禁止编造：",
        "1. 方案↔报告一致性：报告引用的方案编号/标题、验证参数、判定标准、批次"
        "是否与方案一致；",
        "2. 数值与计算核对：报告中的实测结果是否落在方案或质量标准规定的区间内；"
        "方案/报告中的公式与计算是否正确（均值、标准差、RSD、回收率、合格率等"
        "的公式选用与代入计算，发现公式用错或算错必须指出，说明正确算法）；",
        "3. 内容一致性：两份文档内部及之间的关键数据、上下文、结论是否自洽；",
        "4. 规范性：文档编号（封面/页眉/文件名）是否一致、章节是否齐全；",
        "5. 文字质量：明显的错别字、前后表述矛盾、参数单位笔误（只报确定的问题）。",
    ]
    if quality_data_summary:
        parts.append(
            "6. 质量数据联动：结合下方相关偏差/变更记录，评估验证执行期间"
            "是否遗留未关闭的偏差/变更影响验证结论（missing_revalidation 类发现"
            "归入 content_consistency）。"
        )
    parts.append(
        "每一条发现必须给出可核对的原文片段（quote，尽量短，10~120字），"
        "并说明位置（location，如章节或表格名）。"
    )
    parts.append(
        "单次最多输出 15 条：优先报告严重度高的确定问题，宁缺毋滥、"
        "禁止凑数；被截断的问题会在后续部分继续审核。"
    )
    parts.append(
        "分类（category）只能是：" + "/".join(FINDING_CATEGORIES) + "。"
    )
    parts.append("严重程度（severity）只能是 high/medium/low。")
    parts.append(
        "只输出 JSON：{\"findings\": [{\"category\": \"...\", \"severity\": \"...\", "
        "\"location\": \"...\", \"quote\": \"...\", \"detail\": \"...\"}]}"
    )

    if plan_identity:
        parts.append(
            "方案文档身份（从文件名/正文提取）：" + _format_identity(plan_identity)
        )
    if report_identity:
        parts.append(
            "报告文档身份（从文件名/正文提取）：" + _format_identity(report_identity)
        )

    if reference_summary:
        # 只注入统计概要：完整清单由编号核对环节确定性输出，逐块重复注入
        # 既浪费 token 又会把模型注意力带偏到版本号问题
        mismatch_count = sum(
            1 for item in reference_summary if item.get("issue") == "version_mismatch"
        )
        missing_count = sum(
            1 for item in reference_summary if item.get("issue") == "missing"
        )
        parts.append(
            "引用文件核对说明（代码比对已完成，编号/版本类问题已单独输出，"
            "无需重复报告）：本次共核对 "
            f"{len(reference_summary)} 项引用，其中版本不一致 {mismatch_count} 项、"
            f"目录未命中 {missing_count} 项。请专注正文内容本身的问题；"
            "确实没有问题时才返回空数组。"
        )

    if quality_data_summary:
        parts.append(
            "相关偏差/变更记录摘要（代码检索自质量管理台账，事实输入）："
            + str(quality_data_summary)
        )

    parts.extend(_focus_points_section(focus_points))

    if plan_text:
        parts.append("【验证方案正文】\n" + _truncate_text(plan_text, PLAN_TEXT_LIMIT))
    if report_text:
        parts.append(
            "【验证报告正文】\n" + _truncate_text(report_text, REPORT_TEXT_LIMIT)
        )

    return "\n\n".join(parts)


def build_basis_selection_prompt(
    *,
    document_summary: str,
    candidate_bases: list[dict[str, Any]],
) -> str:
    """P2：从引用命中的依据中筛选与正文实质相关的关键依据。

    candidate_bases 每项含 code/name/正文长度/正文开头摘要。
    """
    parts: list[str] = [
        "以下是验证文档引用的受控依据文件列表（编号/名称/正文摘要）。",
        "验证文档信息：" + document_summary,
        "请判断哪些依据与该验证文档的正文存在实质性内容关联"
        "（如《清洁操作规程》之于清洁验证——正文中的清洁步骤/参数直接来源于规程），"
        f"筛选出需要做正文比对的依据（最多 {MAX_CONTENT_COMPARE_BASES} 份）。",
        "管理程序类（如偏差/变更管理程序、文档管理程序）通常只做引用核对，"
        "无需正文比对，不要选入。",
        "只输出 JSON：{\"selected\": [{\"code\": \"...\", \"reason\": \"...\"}]}",
        "",
    ]
    for item in candidate_bases:
        digest = (item.get("digest") or "")[:BASIS_DIGEST_LEN]
        parts.append(
            f"- 编号 {item.get('code')}《{item.get('name')}》"
            f"正文{item.get('length', 0)}字，开头：{digest}"
        )
    return "\n".join(parts)


def build_content_compare_prompt(
    *,
    validation_text: str,
    basis_name: str,
    basis_code: str,
    basis_text: str,
    focus_points: str | None = None,
) -> str:
    """P3：验证文档正文 vs 一份依据正文的逐项一致性比对。"""
    parts: list[str] = [
        "你是验证审核员。下面是【验证文档正文】和一份【受控依据文件正文】。",
        f"依据文件：{basis_code}《{basis_name}》",
        "请逐项核对验证文档中来源于该依据的内容（操作步骤、工艺参数、限度标准、"
        "取样/检验方法、判定条件），找出与依据正文不一致之处：",
        "- 数值/范围矛盾、步骤缺失或顺序不同、方法描述偏差、限度放宽",
        "- 文件编号/版本号差异已在编号核对环节单独处理，不要输出纯版本号差异；"
        "只报告实质内容矛盾，且必须两边正文都能逐字找到对应原文",
        "每条发现必须同时给出两边原文：validation_quote（验证文档原文）与 "
        "basis_quote（依据正文原文），均逐字摘录，禁止编造；无矛盾则不输出。"
        "单次最多输出 10 条，优先报告严重度高的确定矛盾。",
        "severity 只能是 high/medium/low。",
        "只输出 JSON：{\"findings\": [{\"validation_quote\": \"...\", "
        "\"basis_quote\": \"...\", \"dimension\": \"参数|步骤|限度|方法\", "
        "\"severity\": \"...\", \"detail\": \"...\"}]}",
    ]
    parts.extend(_focus_points_section(focus_points))
    parts.append(
        "【验证文档正文】\n" + _truncate_text(validation_text, PLAN_TEXT_LIMIT)
    )
    parts.append("【依据文件正文】\n" + _truncate_text(basis_text, BASIS_TEXT_LIMIT))
    return "\n\n".join(parts)
