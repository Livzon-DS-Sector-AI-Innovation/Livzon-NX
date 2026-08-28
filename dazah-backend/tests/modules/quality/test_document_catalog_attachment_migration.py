from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.core.llm import LLMConfigError
from app.modules.quality.models.document_catalog import DocumentEntry
from app.modules.quality.service import document_catalog_attachment as service


class _Result:
    def __init__(self, rows: list[object] | None = None):
        self.rows = rows or []

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.rows


class _Db:
    def __init__(self, *rows: list[object]) -> None:
        self.execute = AsyncMock(side_effect=[_Result(row) for row in rows])
        self.flush = AsyncMock()


def _entry(*, name: str = "偏差处理程序", code: str = "SOP-QA-001/02") -> DocumentEntry:
    item = DocumentEntry(department_id=uuid4(), name=name, code=code, attachments=[])
    item.id = uuid4()
    item.created_at = datetime(2026, 8, 20, tzinfo=UTC)
    item.updated_at = item.created_at
    item.is_deleted = False
    return item


@pytest.mark.anyio
async def test_attachment_storage_matching_and_llm_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(service, "_local_upload_dir", lambda: tmp_path)
    monkeypatch.setattr(service, "minio_enabled", lambda: False)
    entry = _entry()

    md = await service.upload_attachment_to_entry(
        _Db(), entry, "偏差处理程序.md", "# 目录".encode(), "text/markdown", "u1"
    )
    assert md["converted"] is True
    assert (
        service.read_attachment_preview(entry, md["storage_key"])[0]
        == "# 目录".encode()
    )
    assert service.read_entry_md_contents(entry)[0]["md_text"] == "# 目录"

    monkeypatch.setattr(service, "convert_word_attachment", lambda *_args: "# Word")
    word = await service.upload_attachment_to_entry(
        _Db(), entry, "SOP-QA-001-03.docx", b"word", "application/octet-stream", "u1"
    )
    assert word["converted"] is True
    assert len(service.read_entry_md_contents(entry)) == 2

    with pytest.raises(AppException, match="不支持"):
        await service.upload_attachment_to_entry(
            _Db(), entry, "bad.exe", b"x", "application/octet-stream"
        )
    with pytest.raises(AppException, match="20MB"):
        await service.upload_attachment_to_entry(
            _Db(),
            entry,
            "large.pdf",
            b"x" * (service.ATTACHMENT_MAX_SIZE + 1),
            "application/pdf",
        )

    exact = _entry(code="SOP-QA-001/03")
    assert (
        await service.find_entry_by_file_name(_Db([exact]), "SOP-QA-001-03.pdf")
        is exact
    )
    same_code_a = _entry(code="SOP-QA-001/02")
    same_code_b = _entry(code="SOP-QA-001/02")
    same_code_a.attachments = [{"storage_key": "a"}]
    same_code_b.attachments = []
    assert (
        await service.find_entry_by_file_name(
            _Db([same_code_a, same_code_b]), "SOP-QA-001-02.pdf"
        )
    ) is same_code_b

    prefix = _entry(code="SOP-QA-001/04")
    assert (
        await service.find_entry_by_file_name(_Db([prefix]), "SOP-QA-001.pdf") is prefix
    )
    ambiguous = [_entry(name="偏差处理程序A"), _entry(name="偏差处理程序B")]
    assert (
        await service.find_entry_by_file_name(
            _Db([], ambiguous), "SOP-QA-001-偏差处理程序.pdf"
        )
    ) is None
    named = _entry(name="偏差处理程序")
    assert (
        await service.match_entry_by_name(_Db([named]), "偏差处理程序-附件.pdf")
        is named
    )

    candidate = _entry(name="偏差处理程序")
    llm_db = _Db([candidate])
    monkeypatch.setattr(
        type(service.llm_client),
        "chat_json",
        AsyncMock(return_value={"index": 1}),
    )
    assert (
        await service.llm_match_entry(llm_db, "SOP-QA-001-偏差处理程序.pdf")
        is candidate
    )
    monkeypatch.setattr(
        type(service.llm_client),
        "chat_json",
        AsyncMock(side_effect=LLMConfigError("not configured")),
    )
    assert (
        await service.llm_match_entry(_Db([candidate]), "SOP-QA-001-附件.pdf") is None
    )

    monkeypatch.setattr(
        service, "find_entry_by_file_name", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(service, "match_entry_by_name", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "llm_match_entry", AsyncMock(return_value=candidate))
    assert await service.match_entry_for_attachment(_Db(), "附件.pdf") == (
        candidate,
        "llm",
    )


@pytest.mark.anyio
async def test_attachment_delete_preview_and_compensation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry()
    entry.attachments = [
        {
            "file_name": "政策.docx",
            "storage_key": "original",
            "converted_md_key": "converted",
            "content_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        }
    ]
    db = _Db()
    monkeypatch.setattr(
        service,
        "_read_file",
        Mock(
            side_effect=[(b"doc", "application/octet-stream"), (b"md", "text/markdown")]
        ),
    )
    deleted_keys: list[str] = []
    monkeypatch.setattr(service, "_delete_file", Mock(side_effect=deleted_keys.append))
    assert await service.delete_attachment_from_entry(db, entry, "original") is True
    assert deleted_keys == ["original", "converted"]
    assert entry.attachments == []
    assert await service.delete_attachment_from_entry(db, entry, "missing") is False

    entry.attachments = [{"storage_key": "original", "converted_md_key": None}]
    monkeypatch.setattr(
        service, "_read_file", Mock(return_value=(b"data", "application/pdf"))
    )
    monkeypatch.setattr(
        service, "_delete_file", Mock(side_effect=RuntimeError("storage"))
    )
    with pytest.raises(AppException, match="已回滚"):
        await service.delete_attachment_from_entry(db, entry, "original")
    assert entry.attachments[0]["storage_key"] == "original"

    monkeypatch.setattr(
        service, "_read_file", Mock(side_effect=[(b"converted", "text/markdown"), None])
    )
    entry.attachments = [
        {
            "storage_key": "original",
            "converted_md_key": "converted",
            "content_type": "application/pdf",
        }
    ]
    assert service.read_attachment_preview(entry, "original") == (
        b"converted",
        service.TEXT_MD_MIME,
    )
    assert service.read_attachment_preview(entry, "not-found") == (
        b"",
        "application/octet-stream",
    )

    monkeypatch.setattr(
        service,
        "_read_file",
        Mock(side_effect=[(b"good", "text/markdown"), (b"\xff", "text/markdown")]),
    )
    entry.attachments = [
        {"file_name": "good.md", "converted_md_key": "good"},
        {"file_name": "bad.md", "converted_md_key": "bad"},
        {"file_name": "pdf", "converted_md_key": None},
    ]
    assert service.read_entry_md_contents(entry) == [
        {"file_name": "good.md", "md_text": "good"}
    ]

    assert service.extract_code_and_rev("SOP-QA-001-02.pdf") == ("SOP-QA-001", "02")
    assert service.extract_code_and_rev("没有编码.pdf") is None
    assert service.extract_cjk_core("abc-偏差处理程序-附件.pdf") == "偏差处理程序"
    assert service.extract_cjk_core("abc.pdf") == ""
