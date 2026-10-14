"""质量模块跨模块公开 API 测试。"""

import pytest

from app.core.exceptions import AppException
from app.modules.quality import public_api


def test_convert_word_attachment_text_rejects_unsupported_type() -> None:
    """不支持的扩展名沿管线抛业务异常（不静默返回空文本）。"""
    with pytest.raises(AppException):
        public_api.convert_word_attachment_text("x.txt", b"hello")


def test_convert_word_attachment_text_extracts_docx(monkeypatch) -> None:
    """docx 走 OOXML 直析管线：返回文本且不含图片。"""
    import io

    from docx import Document

    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("跨模块解析的正文内容")
    doc.save(buf)
    docx_bytes = buf.getvalue()

    def fake_convert(file_name: str, content: bytes) -> tuple[str, list]:
        assert file_name.endswith(".docx")
        return "跨模块解析的正文内容", []

    monkeypatch.setattr(
        "app.modules.quality.service.document_catalog_md.convert_word_attachment",
        fake_convert,
    )
    text = public_api.convert_word_attachment_text("a.docx", docx_bytes)
    assert text == "跨模块解析的正文内容"


def test_public_api_exports_surface() -> None:
    assert set(public_api.__all__) == {
        "convert_word_attachment_text",
        "get_module_feishu_app_credentials",
        "get_qa_reminder_recipients",
    }
