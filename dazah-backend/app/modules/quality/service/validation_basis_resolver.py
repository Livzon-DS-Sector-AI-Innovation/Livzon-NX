"""验证文档引用基准匹配：从 VP/VR 正文提取引用编号并反查文件管理目录。

职责：
- 引用编号抽取（容忍 Word 空格与 -// 修订分隔写法），设备位号/批号噪音过滤；
- 逐引用在文件管理目录（document_entries）反查，比对修订号新旧；
- 输出结构化核对结果（命中/缺失/版本不一致/噪音），供 AI 审核编排使用。

设计原则：编号存在性与修订号新旧一律由代码比对，不采信 LLM 结论。
目录条目一次性轻量加载（load_document_basis），匹配为纯同步函数便于单测。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.document_catalog import DocumentEntry

# 候选文件编号：前缀(2-4大写字母)-若干字母数字段-2~3位数字，可选修订号 /NN 或 -NN
_REF_CODE_RE = re.compile(
    r"([A-Z]{2,4}(?:-[A-Za-z0-9（）()]+){1,4}-\d{2,3}(?:[-/]\d{1,3})?)"
)
# 修订号拆分：仅识别尾部 /NN（受控文件修订号）；-NN 结尾是文档序号，不拆分
_REV_SPLIT_RE = re.compile(r"^(?P<core>.+?)/(?P<rev>\d{1,3})$")
# 设备/仪表位号特征：FT3-1-1-077、QC-1-2-002 这类中间连续纯数字段
_EQ_NOISE_RE = re.compile(r"^[A-Z]{2,4}(?:-\d{1,2}){2,}-\d{2,3}$")
# 目录条目 code 的修订号（尾部 /NN）
_ENTRY_REV_RE = re.compile(r"/(\d+)$")
# 文档类型编号：VP-xxx-xxx-NN（方案/报告自身编号，NN 为 2 位序号，后接非字母数字）
_DOC_NUMBER_RE = re.compile(
    r"\b(VP|VR)-[A-Za-z0-9（）()]+-[A-Za-z0-9（）()]+-\d{2}(?![A-Za-z0-9])"
)

# 位号/批号等噪音前缀：即使形态像文件编号也排除
_NOISE_PREFIXES = frozenset({"FT3FP", "USMC", "FT3"})
# 目录前缀动态集合缺失时的兜底文件类型前缀（受控文件常见类型）
_COMMON_DOC_PREFIXES = frozenset(
    {"SMP", "SOP", "STP", "KP", "VP", "VR", "MS", "QS", "PS", "EQ", "QC", "RA"}
)

MatchType = Literal["exact", "related", "missing", "noise"]
IssueKind = Literal["version_mismatch", "missing", "none"]


@dataclass
class BasisEntry:
    """目录条目的轻量视图（仅基准匹配所需字段）。"""

    id: uuid.UUID
    code: str | None
    name: str | None
    effective_date: date | None
    updated_at: datetime | None


@dataclass
class DocumentBasis:
    """一次审核的目录快照：条目集合 + 前缀集合。"""

    entries: list[BasisEntry] = field(default_factory=list)
    prefixes: set[str] = field(
        default_factory=lambda: set(_COMMON_DOC_PREFIXES)
    )


@dataclass
class ReferenceCheckItem:
    """单个引用编号的核对结果。"""

    code: str
    core: str
    revision: str | None
    matched: bool
    match_type: MatchType
    issue: IssueKind = "none"
    entry_id: uuid.UUID | None = None
    entry_code: str | None = None
    entry_name: str | None = None
    current_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "core": self.core,
            "revision": self.revision,
            "matched": self.matched,
            "match_type": self.match_type,
            "issue": self.issue,
            "entry_id": str(self.entry_id) if self.entry_id else None,
            "entry_code": self.entry_code,
            "entry_name": self.entry_name,
            "current_revision": self.current_revision,
        }


def _compact(value: str) -> str:
    """去掉空白与 -// 分隔符，统一大写，用于编号比较。"""
    return re.sub(r"[\s\-/]+", "", value or "").upper()


def _split_revision(code: str) -> tuple[str, str | None]:
    """拆分为 (主干, 修订号)。修订号仅识别结尾 /NN（受控文件修订写法）。"""
    m = _REV_SPLIT_RE.match(code)
    if m:
        return m.group("core"), m.group("rev")
    return code, None


def _entry_revision(code: str | None) -> str | None:
    if not code:
        return None
    m = _ENTRY_REV_RE.search(code)
    return m.group(1) if m else None


def _is_noise(code: str) -> bool:
    """判断候选编号是否为设备位号/批号等噪音（形态像文件编号但不是）。"""
    prefix = re.match(r"^([A-Za-z]{2,4})", code)
    if prefix and prefix.group(1).upper() in _NOISE_PREFIXES:
        return True
    return bool(_EQ_NOISE_RE.match(code))


def infer_doc_kind(file_name: str) -> str:
    """按文件名推断文档类型：VP 前缀→plan，VR 前缀→report，否则 plan。"""
    m = re.match(r"^\s*(VP|VR)[-\s_]", file_name or "")
    if m and m.group(1).upper() == "VR":
        return "report"
    return "plan"


def extract_document_number(file_name: str) -> str | None:
    """从文件名提取文档自身编号（VP-xxx-xxx-NN[-NN] 形态）。"""
    m = _DOC_NUMBER_RE.search(file_name or "")
    return m.group(0) if m else None


def extract_reference_codes(parsed_text: str) -> list[str]:
    """从正文提取候选引用编号（去重保序，已过滤设备位号/批号噪音）。

    正文引用形态：〈文件名称〉（SMP-QA-105/03）或表格行 | SMP-QA-105/03 | 名称 | …。
    容忍 Word 转换产生的修订号空格变体（SMP-QA-105 / 03 → SMP-QA-105/03）。
    """
    seen: set[str] = set()
    codes: list[str] = []
    text = parsed_text or ""
    for m in _REF_CODE_RE.finditer(text):
        code = m.group(1)
        # 修订号空格容错：编号后紧跟 空格 + /NN 或 -NN，且后接非字母数字
        rest = text[m.end() : m.end() + 6]
        revision_tail = re.match(r"\s*[-/]\s*(\d{1,3})(?![\dA-Za-z])", rest)
        if revision_tail:
            code = f"{code}/{revision_tail.group(1)}"
        if _is_noise(code):
            continue
        key = _compact(code)
        if key in seen:
            continue
        seen.add(key)
        codes.append(code)
    return codes


async def load_document_basis(db: AsyncSession) -> DocumentBasis:
    """加载文件管理目录快照：全部未删除条目的轻量字段 + code 前缀集合。"""
    result = await db.execute(
        select(
            DocumentEntry.id,
            DocumentEntry.code,
            DocumentEntry.name,
            DocumentEntry.effective_date,
            DocumentEntry.updated_at,
        ).where(DocumentEntry.is_deleted.is_(False))
    )
    entries: list[BasisEntry] = []
    prefixes: set[str] = set()
    for row in result.all():
        entries.append(
            BasisEntry(
                id=row.id,
                code=row.code,
                name=row.name,
                effective_date=row.effective_date,
                updated_at=row.updated_at,
            )
        )
        if row.code:
            m = re.match(r"^\s*([A-Za-z]{2,4})", row.code)
            if m:
                prefixes.add(m.group(1).upper())
    return DocumentBasis(
        entries=entries, prefixes=prefixes or set(_COMMON_DOC_PREFIXES)
    )


def _find_entries_by_core(
    basis: DocumentBasis, core_compact: str
) -> list[BasisEntry]:
    """按主干（去分隔符大写）匹配目录条目（含同主干不同修订的版本）。"""
    matches: list[BasisEntry] = []
    for entry in basis.entries:
        entry_code = _compact(entry.code or "")
        if not entry_code:
            continue
        if (
            entry_code == core_compact
            or entry_code.startswith(core_compact)
            or core_compact.startswith(entry_code)
        ):
            matches.append(entry)
    return matches


def _latest_entry(entries: list[BasisEntry]) -> BasisEntry:
    """现行版判定：code 尾部修订号 /NN 最大 → 生效日期 → 更新时间（与目录一致）。"""
    return max(
        entries,
        key=lambda e: (
            int(_entry_revision(e.code) or -1),
            e.effective_date or date.min,
            e.updated_at or datetime.min,
        ),
    )


def resolve_references(
    basis: DocumentBasis, parsed_text: str
) -> list[ReferenceCheckItem]:
    """对正文全部候选引用做目录反查与修订号比对（纯同步，便于单测）。"""
    items: list[ReferenceCheckItem] = []
    for raw in extract_reference_codes(parsed_text):
        core, rev = _split_revision(raw)
        core_compact = _compact(core)
        # 前缀取带分隔符主干，避免 compact 后贪婪吞入后续段（SMPQA999 → SMPQ）
        prefix = re.match(r"^([A-Za-z]{2,4})", core)
        entries = _find_entries_by_core(basis, core_compact)
        if not entries:
            # 目录未命中：前缀属于常见文件类型时才判"缺失"，否则视为噪音忽略
            if prefix and prefix.group(1) in basis.prefixes:
                items.append(
                    ReferenceCheckItem(
                        code=raw,
                        core=core_compact,
                        revision=rev,
                        matched=False,
                        match_type="missing",
                        issue="missing",
                    )
                )
            else:
                items.append(
                    ReferenceCheckItem(
                        code=raw,
                        core=core_compact,
                        revision=rev,
                        matched=False,
                        match_type="noise",
                    )
                )
            continue
        latest = _latest_entry(entries)
        current_rev = _entry_revision(latest.code)
        raw_compact = _compact(raw)
        entry_compact = _compact(latest.code or "")
        matched = entry_compact == raw_compact
        issue: IssueKind = "none"
        if rev and current_rev and rev != current_rev:
            issue = "version_mismatch"
        items.append(
            ReferenceCheckItem(
                code=raw,
                core=core_compact,
                revision=rev,
                matched=matched,
                match_type="exact" if matched else "related",
                issue=issue,
                entry_id=latest.id,
                entry_code=latest.code,
                entry_name=latest.name,
                current_revision=current_rev,
            )
        )
    return items


# 单份依据正文传给 LLM 前的最大字符数
BASIS_CONTENT_LIMIT = 20000


async def load_basis_contents(
    db: AsyncSession, entry_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """按目录条目 ID 拉取附件受控正文（word 转 MD 产物），返回 {entry_id: 正文}。

    一个条目多份附件时按顺序合并；正文超长截断到 BASIS_CONTENT_LIMIT。
    """
    from app.modules.quality.service.document_catalog_attachment import (
        read_entry_md_contents,
    )

    contents: dict[uuid.UUID, str] = {}
    for entry_id in entry_ids:
        entry = await db.get(DocumentEntry, entry_id)
        if not entry or entry.is_deleted:
            continue
        pieces = await asyncio.to_thread(read_entry_md_contents, entry)
        merged = "\n\n".join(
            piece.get("md_text") or "" for piece in pieces
        ).strip()
        if merged:
            contents[entry_id] = merged[:BASIS_CONTENT_LIMIT]
    return contents
