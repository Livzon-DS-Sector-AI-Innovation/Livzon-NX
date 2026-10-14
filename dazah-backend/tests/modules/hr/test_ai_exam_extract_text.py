"""AI 笔试上传文档文本提取接口测试（/ai/exam/extract-text）。

覆盖旧格式 .doc/.wps 兜底链路（直接调用路由函数，与 test_ai_exam_async_source_migration
同模式，绕开本地测试环境无 Redis 的操作保护中间件）：
- 真旧格式（OLE2 二进制）.doc：平台 OOXML 直析失败 → 质量模块文件管理
  同一转换管线（LibreOffice/catdoc）兜底成功
- 兜底仍失败：422 与"另存为 .docx/.pdf"指引
- 伪 .doc（实为 OOXML，WPS 常见保存方式）：平台直析成功，不触发兜底
- .docx 解析失败：不走兜底直接 422
"""

from io import BytesIO
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import pytest
from docx import Document
from fastapi import HTTPException, UploadFile

from app.modules.hr.ai_exam_api import extract_exam_document_text

_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


async def test_extract_doc_legacy_fallback_success():
    """真旧格式 .doc：平台解析失败后走质量模块转换管线兜底成功。"""
    with patch(
        "app.modules.quality.public_api.convert_word_attachment_text",
        return_value="# 文本提取模式\n\nDR冷冻菌外观、性状确认试验记录 正文",
    ) as mock_convert:
        resp = await extract_exam_document_text(
            file=_upload("QR1-SOP-SC(DR)-413-05.doc", _OLE2_MAGIC),
            current_user=MagicMock(),
        )

    assert resp.status_code == 200
    data = resp.body.decode()
    assert "DR冷冻菌外观、性状确认试验记录" in data
    assert "QR1-SOP-SC(DR)-413-05.doc" in data
    mock_convert.assert_called_once()


async def test_extract_doc_fallback_failure_returns_422():
    """兜底管线也失败（如环境无 soffice）：422 并提示另存为 .docx/.pdf。"""
    with patch(
        "app.modules.quality.public_api.convert_word_attachment_text",
        side_effect=RuntimeError("soffice convert failed"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await extract_exam_document_text(
                file=_upload("QR4-报告.doc", _OLE2_MAGIC),
                current_user=MagicMock(),
            )

    assert exc_info.value.status_code == 422
    assert "另存为" in str(exc_info.value.detail)


async def test_extract_doc_disguised_ooxml_parses_directly():
    """实为 OOXML 的 .doc：平台直析成功，不触发兜底。"""
    buffer = BytesIO()
    doc = Document()
    doc.add_paragraph("DR冷冻菌生长确认试验记录")
    doc.save(buffer)

    with patch(
        "app.modules.quality.public_api.convert_word_attachment_text"
    ) as mock_convert:
        resp = await extract_exam_document_text(
            file=_upload("QR2-记录.doc", buffer.getvalue()),
            current_user=MagicMock(),
        )

    assert resp.status_code == 200
    assert "DR冷冻菌生长确认试验记录" in resp.body.decode()
    mock_convert.assert_not_called()


async def test_extract_docx_failure_skips_fallback():
    """.docx 解析失败（document.xml 损坏）：不触发 .doc 兜底，直接 422。"""
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><broken>")
    with patch(
        "app.modules.quality.public_api.convert_word_attachment_text"
    ) as mock_convert:
        with pytest.raises(HTTPException) as exc_info:
            await extract_exam_document_text(
                file=_upload("损坏文档.docx", buffer.getvalue()),
                current_user=MagicMock(),
            )

    assert exc_info.value.status_code == 422
    mock_convert.assert_not_called()
