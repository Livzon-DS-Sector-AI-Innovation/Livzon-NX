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

    monkeypatch.setattr(
        service, "convert_word_attachment", lambda *_args: ("# Word", [])
    )
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
    # 名称匹配为归一化完全一致：子串包含（计量室设备+状态标识管理程序）不得命中
    unrelated = _entry(name="计量室设备状态标识管理程序")
    assert (
        await service.match_entry_by_name(_Db([unrelated]), "状态标识管理程序.md")
        is None
    )
    # 名称匹配在编号之前生效
    code_entry = _entry(code="SOP-QA-001/12")
    assert (
        await service.find_entry_by_file_name(_Db([code_entry]), "SOP-QA-001-12.pdf")
        is code_entry
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
    monkeypatch.setattr(service, "match_entry_by_content", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "llm_match_entry", AsyncMock(return_value=candidate))
    assert await service.match_entry_for_attachment(_Db(), "附件.pdf") == (
        candidate,
        "llm",
    )
    # 正文匹配位于名称/编号之后、LLM 之前
    monkeypatch.setattr(
        service, "match_entry_by_content", AsyncMock(return_value=candidate)
    )
    assert await service.match_entry_for_attachment(
        _Db(), "附件.md", ("SMP-QA-001/12", "附件标题")
    ) == (candidate, "content")


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


def test_sync_entry_version_compares_revision_number_only() -> None:
    # 高于条目版本：升级编码并保留原前缀与补零宽度
    entry = _entry(code="SOP-QA-001/02")
    info = service.sync_entry_version(entry, "SOP-QA-001-03偏差处理程序.docx")
    assert info == service.VersionUpdateInfo(
        old_code="SOP-QA-001/02", new_code="SOP-QA-001/03"
    )
    assert entry.code == "SOP-QA-001/03"

    # 相等或更低不更新
    entry = _entry(code="SOP-QA-001/03")
    assert service.sync_entry_version(entry, "SOP-QA-001-03附件.pdf") is None
    assert service.sync_entry_version(entry, "SOP-QA-001-02附件.pdf") is None
    assert entry.code == "SOP-QA-001/03"

    # 条目无修订号：文件名有修订号则补版本
    entry = _entry(code="SOP-QA-001")
    info = service.sync_entry_version(entry, "SOP-QA-001-04附件.pdf")
    assert info is not None and info.new_code == "SOP-QA-001/04"

    # 全角括号前缀保留（文件名半角 → 条目全角）
    entry = _entry(code="SOP-SC（FA）-412/02")
    info = service.sync_entry_version(entry, "SOP-SC(FA)-412-03.pdf")
    assert info is not None and info.new_code == "SOP-SC（FA）-412/03"

    # 文件名无修订号/无编码、条目无编码不更新
    assert service.sync_entry_version(_entry(), "偏差处理程序.pdf") is None
    assert service.sync_entry_version(_entry(), "没有编码附件.pdf") is None
    assert service.sync_entry_version(_entry(code=""), "SOP-QA-001-09.pdf") is None

    # 编码结尾 3 位数字是文件编号本身，不当作修订号
    assert service._parse_entry_code_revision("SOP-QA-001") is None
    assert service._parse_entry_code_revision("SOP-QA-001-8") == (8, "8")
    assert service._parse_entry_code_revision("SOP-QA-001/08") == (8, "08")


@pytest.mark.anyio
async def test_find_entry_binds_latest_when_file_version_higher() -> None:
    low = _entry(code="SOP-QA-001/02")
    high = _entry(code="SOP-QA-001/04")
    assert (
        await service.find_entry_by_file_name(
            _Db([], [low, high]), "SOP-QA-001-05.pdf"
        )
        is high
    )
    # 文件名版本不高于任何候选时不走升级绑定分支（歧义仍返回 None）
    low = _entry(code="SOP-QA-001/02")
    high = _entry(code="SOP-QA-001/04")
    assert (
        await service.find_entry_by_file_name(
            _Db([], [low, high]), "SOP-QA-001-03.pdf"
        )
        is None
    )


@pytest.mark.anyio
async def test_word_attachment_images_assets_and_delete_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import base64

    monkeypatch.setattr(service, "_local_upload_dir", lambda: tmp_path)
    monkeypatch.setattr(service, "minio_enabled", lambda: False)
    entry = _entry(code="SOP-QA-001/02")

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    from app.modules.quality.service.document_catalog_md import ExtractedImage

    image = ExtractedImage(name="img_000.png", data=png, content_type="image/png")
    monkeypatch.setattr(
        service,
        "convert_word_attachment",
        lambda *_args: ("# 标准\n\n![image](img_000.png)", [image]),
    )

    word = await service.upload_attachment_to_entry(
        _Db(), entry, "SOP-QA-001-03.docx", b"word", "application/octet-stream", "u1"
    )
    assert word["converted"] is True
    assert len(word["asset_keys"]) == 1
    asset_key = word["asset_keys"][0]

    stored_md = service.read_attachment_preview(entry, word["storage_key"])[0].decode()
    assert "![image](img_000.png)" not in stored_md
    assert f"/api/v1/quality/document-entries/{entry.id}/attachments/" in stored_md
    assert asset_key in stored_md

    # 图片对象可经 asset_keys 预览（本地存储按字节嗅探 MIME）
    data, content_type = service.read_attachment_preview(entry, asset_key)
    assert data == png
    assert content_type == "image/png"

    # .wps 走 word 转换路径
    wps = await service.upload_attachment_to_entry(
        _Db(), entry, "标准.wps", b"wps", "application/octet-stream", "u1"
    )
    assert wps["converted"] is True

    # 删除附件联动删除图片对象（另一个 wps 附件保留）
    deleted: list[str] = []
    monkeypatch.setattr(service, "_read_file", Mock(return_value=None))
    monkeypatch.setattr(service, "_delete_file", Mock(side_effect=deleted.append))
    assert (
        await service.delete_attachment_from_entry(_Db(), entry, word["storage_key"])
        is True
    )
    assert asset_key in deleted
    assert [a["storage_key"] for a in entry.attachments] == [wps["storage_key"]]


def test_entry_md_contents_strip_image_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = _entry()
    entry.attachments = [{"file_name": "a.md", "converted_md_key": "a"}]
    monkeypatch.setattr(
        service,
        "_read_file",
        Mock(
            return_value=(
                b"# T\n![image](/api/v1/x/content)\n\n\nend",
                "text/markdown",
            )
        ),
    )
    assert service.read_entry_md_contents(entry) == [
        {"file_name": "a.md", "md_text": "# T\n\nend"}
    ]


def test_extract_content_identity_parses_md_header() -> None:
    md = "# 状态标识管理程序\n\n**文件编号**: SMP-QA-005-12\n\n---\n\n正文"
    assert service_module_extract(md) == ("SMP-QA-005-12", "状态标识管理程序")
    assert service_module_extract("# 仅标题") == (None, "仅标题")
    assert service_module_extract("无头部") == (None, None)


def service_module_extract(md: str):
    from app.modules.quality.service.document_catalog_attachment import (
        extract_content_identity,
    )

    return extract_content_identity(md)


@pytest.mark.anyio
async def test_match_entry_by_content_code_then_title() -> None:
    qa = _entry(name="状态标识管理程序", code="SMP-QA-005/12")
    ee = _entry(name="计量室设备状态标识管理程序", code="SMP-EE-403/01")

    # 正文编号主干 + 全串匹配
    assert (
        await service.match_entry_by_content(
            _Db([qa, ee]), "SMP-QA-005-12", "状态标识管理程序"
        )
        is qa
    )
    # 仅主干（无修订段）唯一命中
    assert (
        await service.match_entry_by_content(_Db([qa, ee]), "SMP-QA-005/12", None) is qa
    )
    # 编号匹配失败时按标题归一化完全一致（唯一命中）
    assert (
        await service.match_entry_by_content(_Db([qa]), None, "状态标识管理程序")
        is qa
    )
    # 同名重复条目时不唯一，不猜测
    dup = _entry(name="状态标识管理程序", code="SMP-QA-005/11")
    assert (
        await service.match_entry_by_content(_Db([qa, dup]), None, "状态标识管理程序")
        is None
    )
    # 编号与标题都无法唯一确定
    assert (
        await service.match_entry_by_content(_Db([], []), None, "状态标识管理程序")
        is None
    )
