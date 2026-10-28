"""操规合规审核与批量导入服务。

两个核心能力：
1. 批量上传车间操规文档：保存文件 → 提取正文 → 识别车间/岗位/名称
   （文件名规则优先，可用大模型辅助修正）→ 创建操规台账记录；
2. AI 法规合规审核：以内置法规基线（安全生产法、危化品管理条例、
   GB 30871 特殊作业规范、个体防护与应急管理等审核要点）为依据，
   调用 llm_client 对操规内容逐项审核，产出结论/评分/缺失项/不合规项。

AI 结论仅作辅助分析，整改与放行由车间和安全管理员人工确认。
"""

from __future__ import annotations

import logging
import os
import re
import uuid as uuid_module
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.safety.document_parser import extract_to_markdown
from app.modules.safety.models import OperationRegulation, RegulationReview
from app.modules.safety.schemas.regulations import (
    RegulationBatchUploadItem,
    RegulationReviewItem,
)
from app.platform.audit.service import record_audit_log

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join("uploads", "safety", "regulations")
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
MAX_REVIEW_CONTENT_CHARS = 30000
MAX_ITEMS = 20

# 可提取正文的扩展名；.doc 为旧版二进制格式，仅登记文件不提取
EXTRACTABLE_EXTS = {".docx", ".docm", ".pdf", ".txt", ".md"}
ALLOWED_EXTS = EXTRACTABLE_EXTS | {".doc"}

SEVERITY_LEVELS = ("严重", "一般", "建议")
RESULT_LEVELS = ("pass", "conditional_pass", "fail")

# ── 内置法规审核基线（审核要点） ──────────────────────────────
# 依据现行主要安全法规拆解为操规文档的审核要点；法规条文以官方文本为准。
REGULATORY_BASELINE: list[dict[str, str]] = [
    {
        "item": "编制审批与版本管理",
        "requirement": (
            "操规应标明编制、审核、批准人及生效日期，"
            "纳入受控文件管理并保留修订记录"
        ),
        "basis": "《安全生产法》第二十一条；GB/T 33000-2016 5.4.2",
    },
    {
        "item": "适用范围与岗位",
        "requirement": "明确适用的装置、设备、岗位和工况范围，避免规程与实际岗位脱节",
        "basis": "GB/T 33000-2016《企业安全生产标准化基本规范》5.4.2",
    },
    {
        "item": "岗位职责与持证上岗",
        "requirement": (
            "明确岗位安全职责；涉及电工、焊工、叉车等特种作业的"
            "须注明持证上岗要求"
        ),
        "basis": "《安全生产法》第三十条；《特种作业人员安全技术培训考核管理规定》",
    },
    {
        "item": "危险因素辨识与风险提示",
        "requirement": (
            "辨识本岗位主要危险有害因素（物料危害、高温高压、机械伤害、"
            "高处坠落等）并向操作人员提示"
        ),
        "basis": "《安全生产法》第四十一条；《危险化学品企业安全风险隐患排查治理导则》",
    },
    {
        "item": "安全操作步骤与工艺参数",
        "requirement": (
            "开机前检查、正常操作、停车操作步骤完整，"
            "关键工艺参数和安全控制指标（温度、压力、液位等）明确且可执行"
        ),
        "basis": "《危险化学品安全管理条例》第十五条；AQ/T 3034 导则",
    },
    {
        "item": "个体防护用品配备",
        "requirement": (
            "明确作业过程必须佩戴的个体防护用品"
            "（防毒面具、防护服、护目镜、防护手套等）及使用检查要求"
        ),
        "basis": "《安全生产法》第四十五条；《用人单位劳动防护用品管理规范》",
    },
    {
        "item": "特殊作业管控",
        "requirement": (
            "涉及动火、受限空间、高处、吊装、临时用电、检维修等作业时"
            "应引用特殊作业许可与管控要求"
        ),
        "basis": "GB 30871-2022《化学品生产单位特殊作业安全规范》",
    },
    {
        "item": "异常与故障处置",
        "requirement": (
            "明确常见异常、设备故障的判断与处置步骤，"
            "禁止违章处置和擅自变更工艺条件"
        ),
        "basis": "AQ/T 3034《化工过程安全管理导则》",
    },
    {
        "item": "应急处置措施",
        "requirement": (
            "明确泄漏、火灾、中毒窒息、灼烫等事故的现场应急处置步骤、"
            "应急电话和疏散要求"
        ),
        "basis": "《生产安全事故应急条例》第十条；GB 30077 配备要求",
    },
    {
        "item": "职业健康与环境保护",
        "requirement": (
            "涉及职业病危害因素的应有防护、警示与告知要求；"
            "废水、废气、危险废弃物按规处置"
        ),
        "basis": "《职业病防治法》第二十一条；《固体废物污染环境防治法》",
    },
    {
        "item": "安全警示与禁止事项",
        "requirement": (
            "列明禁止行为（如带压拆卸、无证操作、单人独自进入受限空间作业等）"
            "与现场安全警示标识要求"
        ),
        "basis": "《安全生产法》第四十一条",
    },
    {
        "item": "培训考核与记录",
        "requirement": "操规应经培训考核合格后执行，培训与执行记录可追溯",
        "basis": "《生产经营单位安全培训规定》第十四条",
    },
]

# ── 文件名识别规则 ──────────────────────────────────────────

# 车间识别：按优先级排列（先匹配更具体的写法）
_WORKSHOP_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"201[-—]?\s*1车间|201一车间", "201一车间"),
    (r"201[-—]?\s*2车间|201二车间", "201二车间"),
    (r"201[-—]?\s*3车间|201三车间", "201三车间"),
    (r"101[-—]?\s*1车间|101一车间", "101一车间"),
    (r"101[-—]?\s*2车间|101二车间", "101二车间"),
    (r"102[-—]?\s*1车间|102一车间", "102一车间"),
    (r"102[-—]?\s*2车间|102二车间", "102二车间"),
    (r"10[12]\s*车间", "101-102车间"),
    (r"103\s*车间", "103车间"),
    (r"202\s*车间", "202车间"),
    (r"203\s*车间", "203车间"),
    (r"20[14]\s*车间", "201车间"),
    (r"设备动力部|动力部|动力科", "动力部"),
    (r"热动站", "热动站"),
    (r"污水处理", "污水处理车间"),
)

# 岗位关键词（文件名无「××岗位」时兜底匹配）
_POSITION_KEYWORDS: tuple[str, ...] = (
    "机修班组", "机修", "化测", "工艺值班", "值班", "消毒", "配料", "仪表",
    "工艺", "压滤", "回收", "大超", "MVR浓缩", "MVR", "尾气", "浓缩",
    "烘干包装", "烘干", "离心", "脱色过滤", "脱色", "酸化过滤", "酸化",
    "MV过滤", "MV提取", "MV精制", "精制", "提取", "过滤", "洁净区班组",
    "公用班组", "液氨站", "空压", "循环水", "变电站", "电工",
)

_TITLE_NOISE_PATTERNS = (
    r"[-—～]?\s*\(\d+\)",          # (1) (4) 等下载副本号
    r"[-—～]?\s*（\d+）",
    r"[-—～]\s*副本",
    r"\([、.\d\-/年月日]+\)",       # (2026.07.06) (6.30) 等半角括号日期
    r"（[、.\d\-/年月日]+）",       # （2026.05.13） 等全角括号日期
    r"（2026版修订）|\(2026版修订\)",
    r"[-—]?\s*（?2026版）?|\(2026版\)",   # （2026版）/ 2026版
    r"20\d{2}\s*[.\-/年]\s*\d{1,2}\s*[.\-/月]?\s*\d{0,2}\s*日?",
    r"(?<![\d])20\d{2}(?![\d])",   # 独立年份
    r"（新版）|\(?新版\)?",
    r"docx|docm|\bdoc\b",
    r"\bok\b|(?<=[\u4e00-\u9fa5])ok\b",
    r"（修订）",
)


def recognize_from_filename(
    filename: str, hint_workshop: str = ""
) -> tuple[str, str, str]:
    """从文件名识别（车间, 岗位, 操规名称）。

    车间优先取文件名中的明确标识，识别不到时用 hint_workshop（调用方
    通常传入来源文件夹对应的车间）。
    """

    stem = os.path.splitext(os.path.basename(filename))[0]

    workshop = ""
    for pattern, name in _WORKSHOP_PATTERNS:
        if re.search(pattern, stem):
            workshop = name
            break
    if not workshop:
        workshop = hint_workshop.strip()

    position = ""
    pos_match = re.findall(r"([\u4e00-\u9fa5A-Za-z0-9]{1,10}?)岗位", stem)
    if pos_match:
        position = pos_match[-1]
    else:
        for keyword in _POSITION_KEYWORDS:
            if keyword in stem:
                position = keyword
                break
    # 岗位剥离误带入的车间/编号前缀（如 "102车间机修"、"101二车间工艺值班"、"2压滤"）
    position = re.sub(
        r"^(?:\d{1,3}[一二三四]?车间|[一二三四]车间|\d{2,3}[-—]\d{0,1}|\d{1,3}(?=[\u4e00-\u9fa5]))",
        "",
        position,
    )
    position = position.strip("-—_ ")

    title = stem
    for pattern in _TITLE_NOISE_PATTERNS:
        title = re.sub(pattern, "", title)
    title = re.sub(r"[\s\-—_.]+$", "", title).strip()
    title = title.replace("~$", "").replace("$", "")
    if not title:
        title = stem.strip()

    return workshop, position, title


def _normalize_review_items(
    raw: Any, default_item_prefix: str
) -> list[RegulationReviewItem]:
    """校验并归一化 AI 返回的问题项列表。"""

    items: list[RegulationReviewItem] = []
    if not isinstance(raw, list):
        return items
    for index, entry in enumerate(raw[:MAX_ITEMS]):
        if not isinstance(entry, dict):
            continue
        severity = str(entry.get("severity") or "建议")
        if severity not in SEVERITY_LEVELS:
            severity = "建议"
        items.append(
            RegulationReviewItem(
                item=str(entry.get("item") or f"{default_item_prefix}{index + 1}"),
                requirement=str(entry.get("requirement") or ""),
                basis=str(entry.get("basis") or ""),
                severity=severity,
                suggestion=str(entry.get("suggestion") or ""),
            )
        )
    return items


class RegulationComplianceService:
    """操规批量导入 + AI 法规合规审核。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ==================== 批量上传 ====================

    async def batch_upload(
        self,
        files: list[tuple[str, bytes]],
        *,
        hint_workshop: str = "",
        use_ai: bool = True,
        user_id: uuid_module.UUID | None = None,
    ) -> list[RegulationBatchUploadItem]:
        """批量导入操规文档。

        files 为 (文件名, 字节内容) 列表；hint_workshop 用于文件名未标明
        车间时的兜底归属。单文件失败不影响其余文件。
        """

        results: list[RegulationBatchUploadItem] = []
        for file_name, content in files:
            try:
                results.append(
                    await self._import_single(
                        file_name, content, hint_workshop=hint_workshop,
                        use_ai=use_ai, user_id=user_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — 单文件失败继续处理其余文件
                logger.warning("操规导入失败 %s: %s", file_name, exc)
                results.append(
                    RegulationBatchUploadItem(
                        file_name=file_name, ok=False, message=f"导入失败：{exc}"
                    )
                )
        return results

    async def _import_single(
        self,
        file_name: str,
        content: bytes,
        *,
        hint_workshop: str,
        use_ai: bool,
        user_id: uuid_module.UUID | None,
    ) -> RegulationBatchUploadItem:
        safe_name = os.path.basename(file_name.replace("\\", "/"))
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in ALLOWED_EXTS:
            return RegulationBatchUploadItem(
                file_name=safe_name,
                ok=False,
                message=f"不支持的文件格式 {ext}，仅支持 docx/doc/docm/pdf/txt/md",
            )
        if len(content) > MAX_UPLOAD_SIZE:
            return RegulationBatchUploadItem(
                file_name=safe_name, ok=False, message="文件超过 20MB 限制"
            )

        workshop, position, title = recognize_from_filename(safe_name, hint_workshop)

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        stored_name = f"{uuid_module.uuid4().hex}_{safe_name}"
        file_path = os.path.join(UPLOAD_DIR, stored_name)
        with open(file_path, "wb") as fh:
            fh.write(content)

        extract_note = ""
        content_text = ""
        if ext in EXTRACTABLE_EXTS:
            try:
                content_text = extract_to_markdown(file_path, max_chars=60000)
            except Exception as exc:  # noqa: BLE001 — 提取失败不阻断登记
                logger.warning("操规正文提取失败 %s: %s", safe_name, exc)
                extract_note = f"正文提取失败（{exc}），已登记文件"
        else:
            extract_note = (
                "旧版 .doc 文件已登记，未提取正文；"
                "如需 AI 审核或标准化生成请另存为 .docx"
            )

        recognized_by = "heuristic"
        if use_ai and content_text:
            ai_info = await self._ai_recognize(
                file_name=safe_name, content_excerpt=content_text[:4000]
            )
            if ai_info is not None:
                recognized_by = "ai"
                if ai_info.get("workshop"):
                    workshop = str(ai_info["workshop"])
                if ai_info.get("position"):
                    position = str(ai_info["position"])
                if ai_info.get("title"):
                    title = str(ai_info["title"])

        if not workshop:
            workshop = "未分配车间"
        if not title:
            title = os.path.splitext(safe_name)[0]

        existing = await self.session.execute(
            select(OperationRegulation).where(
                OperationRegulation.workshop == workshop,
                OperationRegulation.document_original_name == safe_name,
                OperationRegulation.is_deleted.is_(False),
            )
        )
        if existing.scalar_one_or_none() is not None:
            return RegulationBatchUploadItem(
                file_name=safe_name,
                ok=False,
                workshop=workshop,
                position=position,
                recognized_by=recognized_by,
                message="该文件此前已导入（同车间同名文件），已跳过",
            )

        regulation = OperationRegulation(
            regulation_no=None,
            regulation_name=title,
            workshop=workshop,
            position=position or None,
            document_path=file_path,
            document_original_name=safe_name,
            source_document_path=file_path,
            status="draft",
            created_by=user_id,
            updated_by=user_id,
        )
        self.session.add(regulation)
        await self.session.flush()
        await self._audit(
            "create", "regulation", resource_id=regulation.id, user_id=user_id,
            extra={"source": "batch_upload", "file_name": safe_name},
        )
        return RegulationBatchUploadItem(
            file_name=safe_name,
            ok=True,
            regulation_id=regulation.id,
            regulation_name=title,
            workshop=workshop,
            position=position,
            recognized_by=recognized_by,
            message=extract_note,
        )

    async def _ai_recognize(
        self, *, file_name: str, content_excerpt: str
    ) -> dict[str, str] | None:
        """大模型辅助识别车间/岗位/名称；不可用时返回 None 走规则结果。"""

        prompt = f"""请根据以下操规文件名和内容开头，识别其归属信息。

文件名：{file_name}

内容开头：
{content_excerpt}

要求：
1. workshop：车间/部门，尽量使用规范名称（如 101一车间、101二车间、\
102一车间、102二车间、103车间、201一车间、201二车间、201三车间、202车间、\
203车间、动力部、热动站、污水处理车间、质量部、仓储）；公司级共用可写"公司级"
2. position：岗位（如 配料、化测、消毒、工艺、值班、机修、仪表、电工），\
无法判断时为空字符串
3. title：操规规范名称（去除版本号、日期、副本标记），\
如"103车间液氨站安全操作规程"

仅返回 JSON：{{"workshop": "...", "position": "...", "title": "..."}}"""
        try:
            result = await llm_client.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是化工工厂的安全资料管理员，擅长从操作规程文档"
                            "识别所属车间、岗位和规范名称。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                expected_keys=["workshop", "position", "title"],
                temperature=0.05,
            )
            return {
                key: str(result.get(key) or "").strip()[:60]
                for key in ("workshop", "position", "title")
            }
        except (
            LLMConfigError,
            LLMOutputError,
            LLMRateLimitError,
            LLMProviderError,
        ) as exc:
            logger.info("AI 识别操规归属不可用，使用文件名规则：%s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 识别操规归属异常：%s", exc)
            return None

    # ==================== AI 法规合规审核 ====================

    async def run_compliance_review(
        self,
        regulation_id: uuid_module.UUID,
        *,
        user_id: uuid_module.UUID | None = None,
    ) -> RegulationReview:
        """对操规执行 AI 法规合规审核并保存审核记录。"""

        result_row = await self.session.execute(
            select(OperationRegulation).where(
                OperationRegulation.id == regulation_id,
                OperationRegulation.is_deleted.is_(False),
            )
        )
        regulation = result_row.scalar_one_or_none()
        if regulation is None:
            raise NotFoundException("操规不存在")

        content = self._load_regulation_content(regulation)
        if not content:
            raise AppException(
                status_code=400,
                message="操规无可审核内容：请先上传文档（docx）或生成标准化内容",
            )

        raw = await self._ai_review(
            regulation_name=regulation.regulation_name,
            workshop=regulation.workshop or "",
            position=regulation.position or "",
            content=content,
        )

        result = str(raw.get("result") or "fail")
        if result not in RESULT_LEVELS:
            result = "fail"
        try:
            score = int(raw.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))

        review = RegulationReview(
            regulation_id=regulation.id,
            regulation_name=regulation.regulation_name,
            result=result,
            score=score,
            summary=str(raw.get("summary") or "")[:4000],
            missing_items=[
                item.model_dump()
                for item in _normalize_review_items(raw.get("missing_items"), "缺失项")
            ],
            non_compliant_items=[
                item.model_dump()
                for item in _normalize_review_items(
                    raw.get("non_compliant_items"), "不合规项"
                )
            ],
            suggestions=[
                str(item) for item in (raw.get("suggestions") or [])[:MAX_ITEMS] if item
            ],
            reviewed_by=user_id,
            created_by=user_id,
            updated_by=user_id,
        )
        self.session.add(review)
        await self.session.flush()
        await self._audit(
            "create",
            "regulation_review",
            resource_id=review.id,
            user_id=user_id,
            extra={
                "regulation_id": str(regulation.id),
                "result": result,
                "score": score,
            },
        )
        return review

    async def list_reviews(
        self, regulation_id: uuid_module.UUID
    ) -> tuple[list[RegulationReview], int]:
        """获取某操规的全部审核记录（按时间倒序）。"""

        result = await self.session.execute(
            select(RegulationReview)
            .where(
                RegulationReview.regulation_id == regulation_id,
                RegulationReview.is_deleted.is_(False),
            )
            .order_by(RegulationReview.created_at.desc())
        )
        reviews = list(result.scalars().all())
        return reviews, len(reviews)

    async def latest_reviews(
        self, regulation_ids: list[uuid_module.UUID]
    ) -> dict[uuid_module.UUID, RegulationReview]:
        """批量获取每个操规的最新审核记录（台账列表状态列用）。"""

        if not regulation_ids:
            return {}
        result = await self.session.execute(
            select(RegulationReview)
            .where(
                RegulationReview.regulation_id.in_(regulation_ids),
                RegulationReview.is_deleted.is_(False),
            )
            .order_by(RegulationReview.created_at.desc())
        )
        latest: dict[uuid_module.UUID, RegulationReview] = {}
        for review in result.scalars().all():
            latest.setdefault(review.regulation_id, review)
        return latest

    # ==================== 文档预览 ====================

    async def get_regulation_for_document(
        self, regulation_id: uuid_module.UUID
    ) -> OperationRegulation | None:
        result = await self.session.execute(
            select(OperationRegulation).where(
                OperationRegulation.id == regulation_id,
                OperationRegulation.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_document_preview(
        self, regulation: OperationRegulation
    ) -> dict[str, str]:
        """提取操规文档正文用于在线预览。

        优先提取上传文档正文；文档缺失或不可提取时回退标准化内容，
        并在 note 中说明原因。
        """

        file_name = (
            regulation.document_original_name
            or os.path.basename(regulation.document_path or "")
            or regulation.regulation_name
        )
        content = ""
        note = ""
        path = regulation.document_path
        if path and os.path.exists(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in EXTRACTABLE_EXTS:
                try:
                    content = extract_to_markdown(path, max_chars=60000)
                except Exception as exc:  # noqa: BLE001 — 提取失败给出提示
                    logger.warning("操规预览提取失败 %s: %s", path, exc)
                    note = f"文档正文提取失败（{exc}）"
            else:
                note = "旧版 .doc 文件暂不支持在线预览，请下载后查看或另存为 .docx"
        else:
            note = (
                "文档文件不存在，以下为标准化内容"
                if regulation.content
                else "尚未上传文档文件"
            )
        if not content and regulation.content:
            content = regulation.content
        return {"file_name": file_name, "content": content, "note": note}

    @staticmethod
    def get_document_file(
        regulation: OperationRegulation,
    ) -> tuple[str, str] | None:
        """返回 (文件路径, 下载文件名)；无文档文件返回 None。"""

        path = regulation.document_path
        if not path or not os.path.exists(path):
            return None
        download_name = regulation.document_original_name or os.path.basename(path)
        return path, download_name

    # ==================== 内部方法 ====================

    @staticmethod
    def _load_regulation_content(regulation: OperationRegulation) -> str:
        """优先取标准化内容，否则从文档文件提取正文。"""

        if regulation.content:
            return regulation.content[:MAX_REVIEW_CONTENT_CHARS]
        path = regulation.document_path
        if path and os.path.exists(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in EXTRACTABLE_EXTS:
                try:
                    return extract_to_markdown(
                        path, max_chars=MAX_REVIEW_CONTENT_CHARS
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("读取操规文档失败 %s: %s", path, exc)
        return ""

    @staticmethod
    def _build_baseline_text() -> str:
        lines = []
        for index, point in enumerate(REGULATORY_BASELINE, start=1):
            lines.append(
                f"{index}. 【{point['item']}】要求：{point['requirement']}；"
                f"依据：{point['basis']}"
            )
        return "\n".join(lines)

    async def _ai_review(
        self, *, regulation_name: str, workshop: str, position: str, content: str
    ) -> dict[str, Any]:
        prompt = f"""请依据下列安全法规审核要点，审核这份安全操作规程的合规性。

审核要点（逐项核对）：
{self._build_baseline_text()}

被审核操规：
- 名称：{regulation_name}
- 车间/部门：{workshop or "未标注"}
- 岗位：{position or "未标注"}

操规内容：
{content}

审核要求：
1. 逐项核对审核要点，指出文档中「完全缺失」的要点（missing_items）\
和「有内容但不满足要求」的要点（non_compliant_items）；合规的要点不要列出
2. 每个问题项给出 requirement（要求内容）、basis（依据法规名称，可含条款）、\
severity（严重/一般/建议）和 suggestion（整改建议，具体可执行）
3. result 判定：存在「严重」问题 → fail；仅有一般/建议问题 → \
conditional_pass；无问题 → pass
4. score 为 0-100 的合规评分（pass≥90，conditional_pass 60-89，fail<60）
5. summary 用 3-5 句话概括整体合规状况；suggestions 给出 3-6 条优先整改建议

仅返回 JSON：
{{"result": "pass|conditional_pass|fail", "score": 0,
"summary": "...", "missing_items": [{{"item": "...", "requirement": "...", \
"basis": "...", "severity": "严重|一般|建议", "suggestion": "..."}}],
"non_compliant_items": [{{...同上...}}], "suggestions": ["...", "..."]}}"""

        try:
            return await llm_client.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是原料药工厂的安全生产法规审核专家，熟悉中国安全生产"
                            "法律法规与化工行业标准，负责审核车间安全操作规程的合规性。"
                            "审核结论仅作为辅助分析，最终整改与放行由人工确认。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                expected_keys=[
                    "result",
                    "score",
                    "summary",
                    "missing_items",
                    "non_compliant_items",
                    "suggestions",
                ],
                temperature=0.05,
            )
        except LLMConfigError as exc:
            raise AppException(
                status_code=503,
                message=(
                    f"AI 审核不可用：模型未配置（{exc}）。"
                    "请在系统设置中配置大模型后重试"
                ),
            ) from exc
        except LLMRateLimitError as exc:
            raise AppException(
                status_code=429, message=f"AI 审核请求过于频繁，请稍后重试（{exc}）"
            ) from exc
        except LLMOutputError as exc:
            raise AppException(
                status_code=502,
                message=f"AI 审核输出无法解析，请重试或联系管理员（{exc}）",
            ) from exc
        except LLMProviderError as exc:
            raise AppException(
                status_code=502, message=f"AI 服务调用失败：{exc}"
            ) from exc

    async def _audit(
        self,
        action: str,
        resource_type: str,
        resource_id: uuid_module.UUID | None = None,
        user_id: uuid_module.UUID | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            await record_audit_log(
                self.session,
                action=action,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                extra=extra,
            )
        except Exception:  # noqa: BLE001 — 审计失败不阻断业务
            logger.exception("审计日志记录失败 (%s:%s)", resource_type, action)
