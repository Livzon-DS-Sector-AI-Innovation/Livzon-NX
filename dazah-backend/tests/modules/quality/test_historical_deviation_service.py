"""历史偏差 service 综合分支测试（仅覆盖已提交版本函数）。"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.quality.service import historical_deviation as svc


def _record(**kw: Any) -> Any:
    base: dict[str, Any] = {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "code": "HD-2024-001",
        "deviation_event": "事件",
        "deviation_content": "内容",
        "direct_cause": "直接",
        "root_cause": "根本",
        "investigation_conclusion": None,
        "remark": None,
        "ai_extract_payload": None,
        "attachments": [],
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 1, tzinfo=UTC),
        "is_deleted": False,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _attach(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "a1",
        "file_name": "f.pdf",
        "storage_key": "s1",
        "content_type": "application/pdf",
        "file_size": 100,
        "converted": False,
        "converted_md_key": None,
        "asset_keys": [],
        "uploaded_at": "2024-01-01T00:00:00Z",
        "uploaded_by": "u1",
    }
    base.update(kw)
    return base


# ── 纯函数与 schema ──────────────────────────────────────


def test_attachment_url_and_new_attachment() -> None:
    url = svc._attachment_content_url(uuid.UUID("11111111-1111-1111-1111-111111111111"), "a/b c")  # noqa: E501
    assert "/attachments/a/b%20c/content" in url
    att = svc._new_attachment("f.docx", "s", "text/markdown", 10, converted=True)
    assert att["converted"] is True
    assert att["asset_keys"] == []
    assert att["uploaded_at"]


def test_schema_roundtrip() -> None:
    record = _record(attachments=[_attach()])
    item = svc._list_item_to_schema(record)
    assert item.attachment_count == 1
    detail = svc._detail_to_schema(record)
    assert len(detail.attachments) == 1
    assert detail.attachments[0].file_name == "f.pdf"


@pytest.mark.asyncio
async def test_require_quality_ai_config_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(config_type: str) -> Any:
        raise LLMConfigError("no config")

    monkeypatch.setattr(svc, "get_config", _boom)
    with pytest.raises(AppException) as exc:
        await svc._require_quality_ai_config()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_or_raise_not_found() -> None:
    session = SimpleNamespace(get=AsyncMock(return_value=None))
    with pytest.raises(NotFoundException):
        await svc._get_or_raise(session, "r1")  # type: ignore[arg-type]
    session2 = SimpleNamespace(get=AsyncMock(return_value=_record(is_deleted=True)))
    with pytest.raises(NotFoundException):
        await svc._get_or_raise(session2, "r1")  # type: ignore[arg-type]


# ── 列表 / 创建 / 更新 / 删除 ────────────────────────────


class _FakeListSession:
    def __init__(self, count: int, items: list[Any]) -> None:
        self._count = count
        self._items = items

    async def execute(self, stmt: Any) -> Any:
        if "count(" in str(stmt):
            return SimpleNamespace(scalar=lambda: self._count)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._items))


@pytest.mark.asyncio
async def test_get_historical_deviation_list() -> None:
    item = _record(code="HD-9")
    session = _FakeListSession(3, [item])
    out = await svc.get_historical_deviation_list(
        session, keyword="偏差", page=1, page_size=20  # type: ignore[arg-type]
    )
    assert out["total"] == 3 and out["items"][0].code == "HD-9"
    out2 = await svc.get_historical_deviation_list(
        session, keyword=None, page=2, page_size=10  # type: ignore[arg-type]
    )
    assert out2["page"] == 2


def _capture_session(fn: str = "commit") -> tuple[Any, list[Any]]:
    created: list[Any] = []

    def _add(record: Any) -> None:
        record.id = record.id or uuid.UUID("11111111-1111-1111-1111-111111111111")
        record.created_at = record.created_at or datetime(2024, 1, 1, tzinfo=UTC)
        record.updated_at = record.updated_at or datetime(2024, 1, 1, tzinfo=UTC)
        created.append(record)

    session = SimpleNamespace(
        add=_add,
        flush=AsyncMock(),
        commit=AsyncMock(),
        get=AsyncMock(return_value=None),
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: created[0])),
    )
    return session, created


@pytest.mark.asyncio
async def test_create_historical_deviation(monkeypatch: pytest.MonkeyPatch) -> None:
    session, created = _capture_session()
    monkeypatch.setattr(svc, "generate_code", AsyncMock(return_value="HD-1"))
    detail = await svc.create_historical_deviation(
        session,  # type: ignore[arg-type]
        SimpleNamespace(
            deviation_event="事件", deviation_content="内容", direct_cause=None,
            root_cause=None, investigation_conclusion=None, remark=None,
        ),
        user_id="u1",
    )
    assert detail.code == "HD-1"
    assert created[0].deviation_event == "事件"
    assert created[0].code == "HD-1"


@pytest.mark.asyncio
async def test_update_historical_deviation() -> None:
    record = _record()
    session = SimpleNamespace(
        get=AsyncMock(return_value=record),
        commit=AsyncMock(),
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: record)),
    )
    detail = await svc.update_historical_deviation(
        session,  # type: ignore[arg-type]
        record.id,
        SimpleNamespace(
            deviation_event="新事件", deviation_content="新内容", direct_cause="新直接",
            root_cause="新根本", investigation_conclusion="结论", remark="备注",
        ),
        user_id="u1",
    )
    assert record.deviation_event == "新事件"
    assert detail.deviation_event == "新事件"


@pytest.mark.asyncio
async def test_delete_historical_deviation(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _record(attachments=[_attach(storage_key="s1", converted_md_key="m1")])
    session = SimpleNamespace(get=AsyncMock(return_value=record), commit=AsyncMock())
    monkeypatch.setattr(
        svc, "attachment_storage_keys", lambda att: ["s1", "m1"]
    )
    deleted: list[str] = []
    monkeypatch.setattr(svc, "delete_file", lambda sub, key: deleted.append(key))
    await svc.delete_historical_deviation(session, record.id, user_id="u1")  # type: ignore[arg-type]  # noqa: E501
    assert record.is_deleted is True
    assert set(deleted) == {"s1", "m1"}


# ── 附件上传 ────────────────────────────────────────────


def _fake_upload(filename: str) -> Any:
    upload = MagicMock()
    upload.filename = filename
    return upload


def _upload_session(record: Any) -> tuple[Any, Any]:
    session = SimpleNamespace(
        get=AsyncMock(return_value=record),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    return session, record


@pytest.mark.asyncio
async def test_upload_attachment_md_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()
    session, _ = _upload_session(record)
    monkeypatch.setattr(
        svc, "read_upload_secure", AsyncMock(return_value=("a.md", b"# md"))
    )
    monkeypatch.setattr(svc, "sniff_upload_mime", lambda *a: "text/markdown")
    monkeypatch.setattr(svc, "store_file", lambda *a: None)
    with pytest.raises(AppException, match="附件文件名不能为空"):
        await svc.upload_historical_deviation_attachment(  # type: ignore[arg-type]
            session, record.id, _fake_upload(""), "u1"
        )
    out = await svc.upload_historical_deviation_attachment(  # type: ignore[arg-type]
        session, record.id, _fake_upload("x.md"), "u1"
    )
    assert out.converted is True
    assert len(record.attachments) == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_word_convert_failure_and_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 转换失败：原样存储
    record = _record()
    session, _ = _upload_session(record)
    monkeypatch.setattr(
        svc, "read_upload_secure", AsyncMock(return_value=("a.docx", b"docx"))
    )
    monkeypatch.setattr(
        svc, "sniff_upload_mime", lambda *a: "application/msword"
    )
    monkeypatch.setattr(
        svc, "render_word_to_md",
        AsyncMock(side_effect=RuntimeError("convert failed")),
    )
    monkeypatch.setattr(svc, "store_file", lambda *a: None)
    out = await svc.upload_historical_deviation_attachment(  # type: ignore[arg-type]
        session, record.id, _fake_upload("a.docx"), "u1"
    )
    assert out.converted is False

    # 转换成功：图片资产 + md 入库
    record2 = _record()
    session2, _ = _upload_session(record2)
    images = [SimpleNamespace(name="img1.png", data=b"png", content_type="image/png")]
    monkeypatch.setattr(
        svc, "render_word_to_md",
        lambda name, content: ("![image](img1.png)", images),
    )
    monkeypatch.setattr(
        svc, "MD_IMAGE_REF_RE", __import__("re").compile(r"!\[image\]\((.*?)\)")
    )
    stored: list[str] = []
    monkeypatch.setattr(svc, "store_file", lambda sub, key, data, ctype: stored.append(key))  # noqa: E501
    out2 = await svc.upload_historical_deviation_attachment(  # type: ignore[arg-type]
        session2, record2.id, _fake_upload("b.docx"), "u1"
    )
    assert out2.converted is True
    assert any(k.endswith(".md") for k in stored)
    assert any(k.endswith("img1.png") for k in stored)


# ── 附件删除 / 读取 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_attachment_found_and_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(attachments=[_attach(id="a1")])
    session = SimpleNamespace(
        get=AsyncMock(return_value=record),
        commit=AsyncMock(),
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: record)),
    )
    monkeypatch.setattr(svc, "attachment_storage_keys", lambda att: ["s1"])
    deleted: list[str] = []
    monkeypatch.setattr(svc, "delete_file", lambda sub, key: deleted.append(key))
    detail = await svc.delete_historical_deviation_attachment(
        session, record.id, "a1", "u1"  # type: ignore[arg-type]
    )
    assert record.attachments == [] and deleted == ["s1"]
    assert detail.attachment_count == 0

    record2 = _record()
    session2 = SimpleNamespace(get=AsyncMock(return_value=record2))
    with pytest.raises(NotFoundException):
        await svc.delete_historical_deviation_attachment(
            session2, record2.id, "missing", "u1"  # type: ignore[arg-type]
        )


def test_read_attachment_content_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _record(
        attachments=[
            _attach(storage_key="md-s", converted=True, converted_md_key="conv-key"),
            _attach(storage_key="plain", content_type="image/png"),
            _attach(storage_key="asset-parent", asset_keys=["asset-1"]),
        ]
    )

    def _read(sub: str, key: str) -> tuple[bytes, str] | None:
        return {
            "conv-key": (b"# md", "text/markdown"),
            "plain": (b"png", "image/png"),
            "asset-1": (b"\xff\xfe", "application/octet-stream"),
        }.get(key)

    monkeypatch.setattr(svc, "read_file", _read)
    monkeypatch.setattr(svc, "sniff_upload_mime", lambda name, data: "text/plain")
    md_data, md_type = svc.read_historical_deviation_attachment_content(record, "md-s")
    assert md_type == svc.TEXT_MD_MIME
    plain_data, plain_type = svc.read_historical_deviation_attachment_content(record, "plain")  # noqa: E501
    assert plain_type == "image/png"
    asset_data, asset_type = svc.read_historical_deviation_attachment_content(record, "asset-1")  # noqa: E501
    assert asset_type == "text/plain"  # octet-stream → sniff
    assert svc.read_historical_deviation_attachment_content(record, "missing") == (
        b"", "application/octet-stream",
    )


# ── AI 提取 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_extract_missing_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(attachments=[])
    session = SimpleNamespace(get=AsyncMock(return_value=record))
    with pytest.raises(AppException, match="请先上传可解析的附件"):
        await svc.ai_extract_historical_deviation(session, record.id, "u1")  # type: ignore[arg-type]  # noqa: E501


@pytest.mark.asyncio
async def test_ai_extract_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(attachments=[_attach(storage_key="s1")])
    session = SimpleNamespace(
        get=AsyncMock(return_value=record),
        commit=AsyncMock(),
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: record)),
    )
    monkeypatch.setattr(
        svc, "_build_ai_context_text", AsyncMock(return_value="附件正文")
    )
    monkeypatch.setattr(
        svc, "_require_quality_ai_config", AsyncMock(return_value=SimpleNamespace(model_name="llm"))  # noqa: E501
    )
    monkeypatch.setattr(
        svc, "llm_client",
        SimpleNamespace(
            chat_json=AsyncMock(
                return_value={
                    "deviation_event": "事件", "deviation_content": "内容",
                    "direct_cause": "直接", "root_cause": "根本",
                }
            )
        ),
    )
    detail = await svc.ai_extract_historical_deviation(session, record.id, "u1")  # type: ignore[arg-type]  # noqa: E501
    assert record.deviation_event == "事件"
    assert record.ai_extract_payload["model_name"] == "llm"
    assert detail.direct_cause == "直接"


@pytest.mark.asyncio
async def test_ai_extract_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        svc, "_build_ai_context_text", AsyncMock(return_value="正文")
    )
    monkeypatch.setattr(
        svc, "_require_quality_ai_config", AsyncMock(return_value=SimpleNamespace(model_name="m"))  # noqa: E501
    )
    for exc, expected in [
        (LLMRateLimitError("429", status_code=429), "AI 限流"),
        (LLMOutputError("bad"), "AI 输出格式错误"),
        (LLMProviderError("down", status_code=502), "AI 服务调用失败"),
    ]:
        session = SimpleNamespace(get=AsyncMock(return_value=_record(attachments=[_attach()])))  # noqa: E501
        monkeypatch.setattr(
            svc, "llm_client",
            SimpleNamespace(chat_json=AsyncMock(side_effect=exc)),
        )
        with patch.object(svc.asyncio, "sleep", new=AsyncMock()):
            with pytest.raises(  # noqa: E501
            AppException, match=expected.replace("，请稍后重试", "")
        ):
                await svc.ai_extract_historical_deviation(session, "r1", "u1")  # type: ignore[arg-type]  # noqa: E501

    # LLM 返回空结果 → 502
    session = SimpleNamespace(get=AsyncMock(return_value=_record(attachments=[_attach()])))  # noqa: E501
    monkeypatch.setattr(
        svc, "llm_client", SimpleNamespace(chat_json=AsyncMock(return_value={"deviation_event": ""}))  # noqa: E501
    )
    with pytest.raises(AppException, match="未提取到有效内容"):
        await svc.ai_extract_historical_deviation(session, "r1", "u1")  # type: ignore[arg-type]  # noqa: E501
