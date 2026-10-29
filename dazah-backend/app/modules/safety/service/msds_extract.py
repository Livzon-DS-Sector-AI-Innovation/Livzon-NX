"""MSDS 附件 AI 识别：提取危化品档案字段建议值。

按 LLM 调用边界走「业务模块 Service → app.core.llm.llm_client」：
- PDF/DOCX 先提取文本（复用安全模块 document_parser），再 chat_json 结构化；
- 图片 MSDS 走 chat_vision_json（data URI）；
- 识别结果经校验后仅作为「建议值」返回前端，由人工确认后才写入档案
  （LLM 输出不替代人工确认，见平台 AI 治理约定）。
"""

from __future__ import annotations

import base64
import logging
import os
import re
import tempfile
from typing import Any

from app.core.llm import llm_client
from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.safety.document_parser import extract_to_markdown
from app.modules.safety.schemas.hazchem import MsdsExtractionSuggestion

logger = logging.getLogger(__name__)

_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

# 危险性类别枚举 ↔ 中文标签（与 HazchemPanel 前端口径一致）
CATEGORY_LABELS: dict[str, str] = {
    "explosive": "爆炸物",
    "flammable_gas": "易燃气体",
    "oxidizing_gas": "氧化性气体",
    "flammable_liquid": "易燃液体",
    "flammable_solid": "易燃固体",
    "self_reactive": "自反应物质",
    "oxidizing_liquid": "氧化性液体",
    "organic_peroxide": "有机过氧化物",
    "toxic": "毒性物质",
    "corrosive": "腐蚀性物质",
    "other": "其他",
}
_LABEL_TO_CATEGORY = {label: code for code, label in CATEGORY_LABELS.items()}
# MSDS 中常见同义写法 → 枚举（模型输出标签不在枚举时兜底映射）
_LABEL_ALIASES: dict[str, str] = {
    "氧化剂": "oxidizing_liquid",
    "氧化性物质": "oxidizing_liquid",
    "易燃物": "flammable_liquid",
    "易燃": "flammable_liquid",
    "有毒": "toxic",
    "剧毒": "toxic",
    "毒害品": "toxic",
    "急性毒性": "toxic",
    "腐蚀品": "corrosive",
    "腐蚀性": "corrosive",
    "刺激": "corrosive",
}

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
_TEXT_EXTS = {".pdf", ".docx", ".doc"}
_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

_EXPECTED_KEYS = [
    "name",
    "alias",
    "cas_no",
    "category",
    "hazard_statements",
    "storage_requirements",
    "remark",
]

_PROMPT_TEMPLATE = """你是一名 EHS 工程师。请从下面的 MSDS（化学品安全技术说明书）\
内容中提取危化品档案信息，严格输出 JSON 对象（不要输出其他文字），字段如下：

- name: 化学品名称（中文优先，取说明书正式品名；没有则为 null）
- alias: 别名/商品名（多个用顿号连接；没有则为 null）
- cas_no: CAS 号（格式如 67-64-1；没有则为 null）
- category: 危险性类别，只能从以下选项中选一个最匹配的：{category_labels}；\
无法判断则为 null
- hazard_statements: 危险性概述（GHS 危险性说明/H 代码与文字，压缩为一段简明中文，\
500 字内；没有则为 null）
- storage_requirements: 储存要求（储存条件/禁配物/温度等，压缩为一段简明中文，\
300 字内；没有则为 null）
- remark: 其他对档案有价值的补充（如灭火剂、应急处理要点，200 字内；没有则为 null）

MSDS 内容：
{content}"""


def _clean_optional_str(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.lower() == "null":
        return None
    return text[:max_length]


def _clean_cas_no(value: Any) -> str | None:
    text = _clean_optional_str(value, 60)
    if text is None:
        return None
    if not _CAS_RE.match(text):
        return None
    return text


def _clean_category(value: Any) -> tuple[str | None, str]:
    text = _clean_optional_str(value, 40)
    if text is None:
        return None, ""
    code = _LABEL_TO_CATEGORY.get(text) or _LABEL_ALIASES.get(text)
    if code is None:
        # 模型可能输出枚举值本身或带说明的长句：仅接受完整匹配
        if text in CATEGORY_LABELS:
            code = text
        else:
            return None, ""
    return code, CATEGORY_LABELS[code]


def _build_suggestion(raw: dict[str, Any]) -> MsdsExtractionSuggestion:
    category, category_label = _clean_category(raw.get("category"))
    return MsdsExtractionSuggestion(
        name=_clean_optional_str(raw.get("name"), 200),
        alias=_clean_optional_str(raw.get("alias"), 200),
        cas_no=_clean_cas_no(raw.get("cas_no")),
        category=category,
        category_label=category_label,
        hazard_statements=_clean_optional_str(raw.get("hazard_statements"), 8000),
        storage_requirements=_clean_optional_str(
            raw.get("storage_requirements"), 8000
        ),
        remark=_clean_optional_str(raw.get("remark"), 8000),
    )


def _has_any_field(suggestion: MsdsExtractionSuggestion) -> bool:
    return any(
        (
            suggestion.name,
            suggestion.alias,
            suggestion.cas_no,
            suggestion.category,
            suggestion.hazard_statements,
            suggestion.storage_requirements,
            suggestion.remark,
        )
    )


def _extract_text_via_doc_conversion(content: bytes, file_name: str) -> str:
    """旧版二进制 .doc（OLE2 复合文档）→ LibreOffice 转 PDF → 文本提取。

    python-docx 只认 docx（zip）容器；真实 .doc 由 soffice 转换后再走
    既有 PDF 提取管线（含扫描件 OCR 回退）。转换失败返回空字符串。
    """
    from app.platform.storage.preview import convert_office_to_pdf

    pdf_bytes = convert_office_to_pdf(content, file_name)
    if not pdf_bytes:
        logger.warning("MSDS .doc 转 PDF 失败: file=%s", file_name)
        return ""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = tmp.name
    try:
        return extract_to_markdown(pdf_path, max_chars=20000)
    finally:
        try:
            os.unlink(pdf_path)
        except OSError:
            pass


def _extract_text_content(file_name: str, content: bytes) -> str:
    """PDF/DOCX/DOC → Markdown 文本；不支持的格式抛 ValueError。

    .doc 直接解析失败（python-docx 只认 zip 容器）或提取为空时，
    回退 LibreOffice 转换；其余格式解析失败按"无文本"处理，
    由调用方提示手动填写，不让附件上传链路失败。
    """
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in _TEXT_EXTS:
        raise ValueError(f"「{file_name}」格式暂不支持内容识别")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        try:
            text = extract_to_markdown(tmp_path, max_chars=20000)
        except Exception:
            # 解析器对损坏/旧格式文档抛出的异常类型不一，统一按"无文本"处理
            logger.warning(
                "MSDS 文本提取失败: file=%s ext=%s", file_name, ext, exc_info=True
            )
            text = ""
        if not text.strip() and ext == ".doc":
            text = _extract_text_via_doc_conversion(content, file_name)
        return text.strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _build_prompt(content_text: str) -> str:
    labels = "、".join(CATEGORY_LABELS.values())
    return _PROMPT_TEMPLATE.format(category_labels=labels, content=content_text)


async def extract_msds_suggestion(
    *, file_name: str, content: bytes
) -> tuple[MsdsExtractionSuggestion | None, str | None]:
    """识别 MSDS 附件内容，返回（建议值, 未识别原因）。

    附件保存与识别解耦：识别失败只返回原因，不影响上传结果。
    """
    ext = os.path.splitext(file_name)[1].lower()
    try:
        if ext in _IMAGE_EXTS:
            data_uri = (
                f"data:{_IMAGE_MIME[ext]};base64,"
                f"{base64.b64encode(content).decode('ascii')}"
            )
            raw = await llm_client.chat_vision_json(
                _build_prompt("（见图片，MSDS 扫描件）"),
                [data_uri],
                expected_keys=_EXPECTED_KEYS,
            )
        else:
            content_text = _extract_text_content(file_name, content)
            if not content_text:
                return None, "未能从附件中提取到文本内容"
            raw = await llm_client.chat_json(
                [
                    {
                        "role": "user",
                        "content": _build_prompt(content_text),
                    }
                ],
                expected_keys=_EXPECTED_KEYS,
            )
    except LLMConfigError:
        return None, "平台未配置 AI 模型，无法自动识别"
    except LLMRateLimitError:
        return None, "AI 模型限流，请稍后重试识别"
    except LLMOutputError:
        return None, "AI 识别结果格式无效，请重试或手动填写"
    except LLMProviderError:
        return None, "AI 模型服务暂不可用，请稍后重试识别"
    except ValueError as exc:
        return None, str(exc)

    suggestion = _build_suggestion(raw)
    if not _has_any_field(suggestion):
        return None, "AI 未能从该附件识别出有效档案信息"
    return suggestion, None
