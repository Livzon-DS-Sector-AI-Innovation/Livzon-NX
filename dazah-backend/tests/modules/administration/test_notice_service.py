"""公告 AI 识别服务测试：mock llm_client，覆盖正常/清洗/各类 LLM 异常。"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.administration import notice_service
from app.modules.administration.notice_service import (
    NoticeParseError,
    _build_search_text,
    extract_notice_content,
    extract_notice_suggestion,
)


def _install_llm(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]
) -> SimpleNamespace:
    fake_client = SimpleNamespace(
        chat_json=AsyncMock(return_value=result),
        chat_vision_json=AsyncMock(return_value=result),
    )
    monkeypatch.setattr(notice_service, "llm_client", fake_client)
    return fake_client


def _docx_bytes() -> bytes:
    """构造一个最小可解析 docx（DocumentParser 走 python-docx）。"""
    from docx import Document

    doc = Document()
    doc.add_paragraph("公告编号：2026-第03号")
    doc.add_paragraph("关于开展年度安全培训的通知")
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


_GOOD_OUTPUT = {
    "notice_no": "2026-第03号",
    "title": "关于开展年度安全培训的通知",
    "publisher": "厂办公室",
    "published_at": "2026-03-05",
    "category": "安全公告",
    "content": "全厂定于下周开展年度安全培训……",
    "remark": "抄送：各车间",
}


async def test_extract_suggestion_from_docx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_llm(monkeypatch, dict(_GOOD_OUTPUT))
    suggestion, error = await extract_notice_suggestion(
        file_name="公告.docx", content=_docx_bytes()
    )
    assert error is None
    assert suggestion is not None
    assert suggestion.notice_no == "2026-第03号"
    assert suggestion.title == "关于开展年度安全培训的通知"
    assert suggestion.publisher == "厂办公室"
    assert suggestion.published_at == "2026-03-05"
    assert suggestion.category == "安全公告"
    # 建议值契约不含公告内容：内容仅在确认导入后经专用端点下发
    assert not hasattr(suggestion, "content")
    chat_json = fake.chat_json
    chat_json.assert_awaited_once()
    prompt = chat_json.await_args.args[0][0]["content"]
    assert "2026-第03号" in prompt
    assert fake.chat_vision_json.await_count == 0


async def test_extract_suggestion_from_image_uses_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_llm(monkeypatch, dict(_GOOD_OUTPUT))
    suggestion, error = await extract_notice_suggestion(
        file_name="公告.jpg", content=b"\xff\xd8\xff\xe0fake-jpeg"
    )
    assert error is None
    assert suggestion is not None
    assert suggestion.notice_no == "2026-第03号"
    fake.chat_vision_json.assert_awaited_once()
    data_uri = fake.chat_vision_json.await_args.args[1][0]
    assert data_uri.startswith("data:image/jpeg;base64,")
    assert fake.chat_json.await_count == 0


async def test_extract_suggestion_cleans_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_llm(
        monkeypatch,
        {
            "notice_no": "null",
            "title": "标" + "题" * 300,
            "publisher": "  ",
            "published_at": "2026年3月5日",
            "category": "x" * 60,
            "content": "正文",
            "remark": None,
        },
    )
    suggestion, error = await extract_notice_suggestion(
        file_name="公告.docx", content=_docx_bytes()
    )
    assert error is None
    assert suggestion is not None
    assert suggestion.notice_no is None
    assert len(suggestion.title or "") == 255
    assert suggestion.publisher is None
    # 中文日期归一化为 ISO
    assert suggestion.published_at == "2026-03-05"
    assert len(suggestion.category or "") == 50


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (LLMConfigError("no config"), "平台未配置 AI 模型"),
        (LLMRateLimitError("rate"), "限流"),
        (LLMOutputError("bad output"), "格式无效"),
        (LLMProviderError("provider"), "暂不可用"),
    ],
)
async def test_extract_suggestion_maps_llm_errors(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, expected: str
) -> None:
    fake = _install_llm(monkeypatch, dict(_GOOD_OUTPUT))
    fake.chat_json.side_effect = exc
    suggestion, error = await extract_notice_suggestion(
        file_name="公告.docx", content=_docx_bytes()
    )
    assert suggestion is None
    assert error is not None
    assert expected in error


async def test_extract_suggestion_rejects_unsupported_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_llm(monkeypatch, dict(_GOOD_OUTPUT))
    suggestion, error = await extract_notice_suggestion(
        file_name="公告.txt", content="纯文本".encode()
    )
    assert suggestion is None
    assert error is not None
    assert "格式暂不支持" in error


async def test_extract_suggestion_reports_empty_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_llm(monkeypatch, dict(_GOOD_OUTPUT))
    suggestion, error = await extract_notice_suggestion(
        file_name="公告.pdf", content=b"not-a-real-pdf"
    )
    assert suggestion is None
    assert error is not None
    assert "未能从附件中提取到文本内容" in error


async def test_extract_content_returns_clean_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_llm(monkeypatch, dict(_GOOD_OUTPUT))
    content = await extract_notice_content(file_name="公告.docx", content=_docx_bytes())
    assert content == "全厂定于下周开展年度安全培训……"


async def test_extract_content_wraps_llm_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_llm(monkeypatch, dict(_GOOD_OUTPUT))
    fake.chat_json.side_effect = LLMProviderError("down")
    with pytest.raises(NoticeParseError) as exc_info:
        await extract_notice_content(file_name="公告.docx", content=_docx_bytes())
    assert exc_info.value.status_code == 502
    assert "暂不可用" in str(exc_info.value.message)


def test_search_text_excludes_content() -> None:
    text = _build_search_text(
        "2026-第03号", "培训通知", "厂办公室", "安全公告", "抄送各车间"
    )
    assert "2026-第03号" in text and "培训通知" in text
    # 元数据搜索文本不含公告内容，防止关键字搜索泄露内容线索
    assert "正文内容" not in _build_search_text("A", "B", "C", "D", "E")
