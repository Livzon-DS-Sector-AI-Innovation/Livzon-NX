"""quality public_api 新增公开能力的契约测试。"""

from app.modules.quality import public_api


def test_office_content_to_pdf_reexports_conversion(monkeypatch) -> None:
    """公开函数应直连 LibreOffice 转换管线（阻塞调用由调用方放线程）。"""
    calls: list[tuple[bytes, str]] = []

    def _fake_convert(content: bytes, file_name: str) -> bytes:
        calls.append((content, file_name))
        return b"%PDF-1.4 fake"

    monkeypatch.setattr(
        "app.modules.quality.service.feishu_attachment_preview.convert_office_to_pdf",
        _fake_convert,
    )
    result = public_api.office_content_to_pdf(b"xlsx-bytes", "导出.xlsx")
    assert result == b"%PDF-1.4 fake"
    assert calls == [(b"xlsx-bytes", "导出.xlsx")]


def test_office_content_to_pdf_exposed_in_all() -> None:
    assert "office_content_to_pdf" in public_api.__all__
