"""证件附件 AI 识别：提取人员特殊作业证件字段建议值。

按 LLM 调用边界走「业务模块 Service → app.core.llm.llm_client」：
- 图片扫描件走 chat_vision_json（data URI）；
- PDF 走 document_parser 文本提取 + chat_json；
- 识别结果仅作为「建议值」返回前端，人工确认后才写入证件
  （LLM 输出不替代人工确认）。失败返回原因，不影响附件保存。
"""

from __future__ import annotations

import base64
import logging
import os
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
from app.modules.safety.schemas.work_certificate import (
    CertificateExtractionSuggestion,
)
from app.modules.safety.service.work_permit_templates import (
    CERTIFICATE_CATEGORIES,
    CERTIFICATE_CATEGORY_LABELS,
)

logger = logging.getLogger(__name__)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
_TEXT_EXTS = {".pdf"}
_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

_EXPECTED_KEYS = [
    "person_name",
    "certificate_category",
    "certificate_no",
    "issuing_authority",
    "issue_date",
    "expiry_date",
    "qualification_scope",
]

_CATEGORY_LABELS_TEXT = "、".join(
    item["label"] for item in CERTIFICATE_CATEGORIES
)

_PROMPT_TEMPLATE = """你是一名工厂 EHS 管理员。请从下面的特种作业证件内容中提取信息，\
严格输出 JSON 对象（不要输出其他文字），字段如下：

- person_name: 持证人姓名（没有则为 null）
- certificate_category: 证件类别，只能从以下选项中选一个最匹配的：\
{category_labels}；无法判断则为 null
- certificate_no: 证件号/证号（没有则为 null）
- issuing_authority: 发证机关（没有则为 null）
- issue_date: 发证日期，格式 YYYY-MM-DD（没有则为 null）
- expiry_date: 有效期至/复审日期，格式 YYYY-MM-DD（没有则为 null）
- qualification_scope: 准操项目/作业类别明细（压缩为一句简明中文，200 字内；\
没有则为 null）

证件内容：
{content}"""


def _clean_optional_str(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.lower() == "null":
        return None
    return text[:max_length]


def _clean_date(value: Any) -> Any:
    from datetime import date as date_cls

    if isinstance(value, date_cls):
        return value
    text = _clean_optional_str(value, 20)
    if text is None:
        return None
    normalized = text.replace("/", "-").replace(".", "-")
    parts = normalized.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        try:
            return date_cls(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
    return None


def _clean_category(value: Any) -> tuple[str | None, str]:
    text = _clean_optional_str(value, 64)
    if text is None:
        return None, ""
    for code, label in CERTIFICATE_CATEGORY_LABELS.items():
        if text == code or text == label:
            return code, label
    for code, label in CERTIFICATE_CATEGORY_LABELS.items():
        core = label.split("（")[0].split("(")[0]
        if core and core in text:
            return code, label
    return None, ""


def _build_suggestion(raw: dict[str, Any]) -> CertificateExtractionSuggestion:
    category, category_label = _clean_category(raw.get("certificate_category"))
    return CertificateExtractionSuggestion(
        person_name=_clean_optional_str(raw.get("person_name"), 100),
        certificate_category=category,
        certificate_category_label=category_label,
        certificate_no=_clean_optional_str(raw.get("certificate_no"), 100),
        issuing_authority=_clean_optional_str(
            raw.get("issuing_authority"), 200
        ),
        issue_date=_clean_date(raw.get("issue_date")),
        expiry_date=_clean_date(raw.get("expiry_date")),
        qualification_scope=_clean_optional_str(
            raw.get("qualification_scope"), 2000
        ),
    )


def _has_any_field(suggestion: CertificateExtractionSuggestion) -> bool:
    return any(
        (
            suggestion.person_name,
            suggestion.certificate_category,
            suggestion.certificate_no,
            suggestion.issuing_authority,
            suggestion.issue_date,
            suggestion.expiry_date,
            suggestion.qualification_scope,
        )
    )


def _extract_text_content(file_name: str, content: bytes) -> str:
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in _TEXT_EXTS:
        raise ValueError(f"「{file_name}」格式暂不支持内容识别")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        try:
            text = extract_to_markdown(tmp_path, max_chars=12000)
        except Exception:
            logger.warning(
                "证件文本提取失败: file=%s ext=%s", file_name, ext, exc_info=True
            )
            text = ""
        return text.strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _build_prompt(content_text: str) -> str:
    return _PROMPT_TEMPLATE.format(
        category_labels=_CATEGORY_LABELS_TEXT, content=content_text
    )


async def extract_certificate_suggestion(
    *, file_name: str, content: bytes
) -> tuple[CertificateExtractionSuggestion | None, str | None]:
    """识别证件附件内容，返回（建议值, 未识别原因）。"""
    ext = os.path.splitext(file_name)[1].lower()
    try:
        if ext in _IMAGE_EXTS:
            data_uri = (
                f"data:{_IMAGE_MIME[ext]};base64,"
                f"{base64.b64encode(content).decode('ascii')}"
            )
            raw = await llm_client.chat_vision_json(
                _build_prompt("（见图片，证件扫描件/照片）"),
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
        return None, "AI 未能从该附件识别出有效证件信息"
    return suggestion, None


__all__ = ["extract_certificate_suggestion"]
