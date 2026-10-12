"""Rank already-authorized capabilities using provider-owned schema descriptions."""

import re
from collections.abc import Mapping

# Language normalization only: these terms never identify or authorize tools.
_ACTION_TERMS = (
    ("查询", "查看", "检索", "查找", "找找", "看看", "list", "get", "search"),
    ("创建", "新增", "新建", "起草", "草拟", "拟定", "create", "draft"),
    ("统计", "汇总", "聚合", "分析", "aggregate", "statistics", "analyze"),
    ("修改", "更新", "编辑", "update", "edit"),
)
_GENERIC = {
    "平台",
    "哪些",
    "怎么",
    "如何",
    "可以",
    "能够",
    "当前",
    "用户",
    "请问",
    "什么",
    "帮我",
    "一下",
    "查询",
    "查看",
    "记录",
}


def _normalized(text: str) -> str:
    text = text.casefold()
    for terms in _ACTION_TERMS:
        for term in terms:
            text = (
                re.sub(rf"\b{term}\b", terms[0], text)
                if term.isascii()
                else text.replace(term, terms[0])
            )
    return text


def schema_search_text(schema: Mapping[str, object], *, depth: int = 0) -> str:
    """Index descriptions/examples, never arbitrary schema defaults or user data."""
    if depth > 8:
        return ""
    parts: list[str] = []
    for key, value in schema.items():
        if key in {"default", "const"}:
            continue
        if key in {"title", "description"} and isinstance(value, str):
            parts.append(value[:500])
        elif key in {"examples", "enum"} and isinstance(value, list):
            parts.extend(item[:200] for item in value[:10] if isinstance(item, str))
        elif isinstance(value, Mapping):
            parts.append(schema_search_text(value, depth=depth + 1))
        elif isinstance(value, list):
            parts.extend(
                schema_search_text(item, depth=depth + 1)
                for item in value[:30]
                if isinstance(item, Mapping)
            )
    return " ".join(parts)[:8000]


def capability_score(query: str, primary: str, schema_text: str = "") -> int:
    """Exact names outrank summaries, which outrank schema-only fuzzy matches."""
    query = query.strip().casefold()
    if not query:
        return 1
    if query in primary.casefold():
        return 1000 + len(query)
    normalized = _normalized(query)
    primary = _normalized(primary)
    secondary = _normalized(schema_text)
    if normalized in primary:
        return 500 + len(normalized)
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    tokens.update(
        word[i : i + 2]
        for word in re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
        for i in range(len(word) - 1)
    )
    tokens -= _GENERIC
    return sum(
        10 if token in primary else 2 if token in secondary else 0 for token in tokens
    )
