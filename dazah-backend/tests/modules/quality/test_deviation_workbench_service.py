"""偏差工作台 service 综合分支测试：纯函数、列表过滤、附件上传、分析与 LLM 失败路径。"""

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
from app.modules.quality.service import deviation_workbench as svc


def _report(**kw: Any) -> Any:
    base: dict[str, Any] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "code": "WB-1",
        "source_type": "manual",
        "source_record_id": None,
        "manual_text": "内容",
        "deviation_summary": "概述",
        "status": "completed",
        "error_message": None,
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 1, tzinfo=UTC),
        "attachments": [],
        "context_snapshot": {},
        "report_payload": {},
        "report_md": "# 报告",
        "model_name": "m",
        "is_deleted": False,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── 纯函数 ──────────────────────────────────────────────


def test_truncate() -> None:
    assert svc._truncate("短文本") == "短文本"
    assert svc._truncate(None) == ""
    out = svc._truncate("长" * 1000)
    assert out.endswith("...") and len(out) == 803


def test_normalize_analysis() -> None:
    assert svc._normalize_analysis(None) == {d: "" for d in svc._5M1E_DIMS}
    out = svc._normalize_analysis(
        {"人": "人员因素", "机-设备": "设备因素", "其他": "忽略"}
    )
    assert out["人"] == "人员因素"
    # 前缀匹配：'机' 键以 '机' 开头
    assert "设备因素" in out["机"]
    assert len(out) == 6  # 只保留五个维度 + 无多余键


def test_normalize_string_list() -> None:
    assert svc._normalize_string_list(["a", "  b ", ""]) == ["a", "b"]
    assert svc._normalize_string_list("单项") == ["单项"]
    assert svc._normalize_string_list(None) == []
    assert svc._normalize_string_list(123) == []


def test_validate_report() -> None:
    raw = {
        "deviation_summary": "概述",
        "analysis": {"人": "因素"},
        "direct_cause": "直接",
        "root_cause": "根本",
        "conclusion": "结论",
        "recommendations": ["建议1", ""],
        "referenced_sources": ["来源1"],
    }
    payload = svc._validate_report(raw)
    assert payload["deviation_summary"] == "概述"
    assert payload["recommendations"] == ["建议1"]
    assert payload["analysis"]["人"] == "因素"
    with pytest.raises(AppException, match="未生成有效调查报告"):
        svc._validate_report({"deviation_summary": "", "direct_cause": " "})


def test_payload_to_md_sections() -> None:
    payload = {
        "deviation_summary": "概述",
        "analysis": {"人": "人员因素"},
        "direct_cause": "直接原因",
        "root_cause": "根本原因",
        "conclusion": "调查结论",
        "recommendations": ["建议一"],
        "referenced_sources": ["来源一"],
    }
    md = svc._payload_to_md(payload)
    assert "# 偏差调查报告" in md
    assert "### 人" in md and "人员因素" in md
    assert "## 六、纠正预防建议" in md and "- 建议一" in md
    assert "## 七、参考来源" in md and "- 来源一" in md
    # 空建议/来源用 '-' 占位
    empty_md = svc._payload_to_md(
        {**payload, "recommendations": [], "referenced_sources": []}
    )
    assert empty_md.count("-") >= 2


def test_escape_like_and_attachment_url() -> None:
    assert svc._escape_like(r"a\b%c_d") == r"a\\b\%c\_d"
    url = svc._attachment_content_url("a/b c")
    assert "/api/v1/quality/deviation-workbench/attachments/a/b%20c/content" in url


def test_attachment_out_prefers_converted_md() -> None:
    out = svc._attachment_out(
        "r1", {"id": "a1", "file_name": "f.docx", "converted_md_key": "md", "storage_key": "orig"}  # noqa: E501
    )
    assert out.url.endswith("/md/content")
    out2 = svc._attachment_out("r1", {"file_name": "f.pdf"})
    assert out2.file_name == "f.pdf" and out2.id == ""


def test_list_and_detail_schema_roundtrip() -> None:
    report = _report(
        attachments=[{"id": "a1", "file_name": "f", "storage_key": "s", "converted": False}]  # noqa: E501
    )
    item = svc._list_item_to_schema(report)
    assert item.code == "WB-1"
    detail = svc._detail_to_schema(report)
    assert detail.report_md == "# 报告"
    assert len(detail.attachments) == 1


# ── 列表过滤与日期校验 ──────────────────────────────────


class _FakeListSession:
    def __init__(self, count: int, items: list[Any]) -> None:
        self._count = count
        self._items = items

    async def execute(self, stmt: Any) -> Any:
        if isinstance(stmt, MagicMock):
            return stmt
        text = str(stmt)
        if "count(" in text:
            return SimpleNamespace(scalar=lambda: self._count)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._items))


@pytest.mark.asyncio
async def test_list_workbench_reports_filters_and_result() -> None:
    item = _report(code="WB-9")
    session = _FakeListSession(3, [item])
    out = await svc.list_workbench_reports(
        session,  # type: ignore[arg-type]
        keyword="WB",
        source_type="manual",
        status="completed",
        date_from="2024-01-01",
        date_to="2024-01-02",
        page=1,
        page_size=20,
    )
    assert out["total"] == 3 and out["items"][0].code == "WB-9"
    # 非法日期
    with pytest.raises(AppException, match="开始日期格式不合法"):
        await svc.list_workbench_reports(
            session,  # type: ignore[arg-type]
            keyword=None, source_type=None, status=None,
            date_from="bad", date_to=None, page=1, page_size=20,
        )
    with pytest.raises(AppException, match="结束日期格式不合法"):
        await svc.list_workbench_reports(
            session,  # type: ignore[arg-type]
            keyword=None, source_type=None, status=None,
            date_from=None, date_to="nope", page=1, page_size=20,
        )


# ── 设置 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_workbench_settings_found_and_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalar_one_or_none=lambda: SimpleNamespace(
                    report_system_prompt="提示词", updated_at=datetime(2024, 1, 1)
                )
            )
        )
    )
    out = await svc.get_workbench_settings(session)  # type: ignore[arg-type]
    assert out.report_system_prompt == "提示词"

    session2 = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    out2 = await svc.get_workbench_settings(session2)  # type: ignore[arg-type]
    assert out2.report_system_prompt == ""


@pytest.mark.asyncio
async def test_update_workbench_settings_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(commit=AsyncMock())
    settings = SimpleNamespace(id="11111111-1111-1111-1111-111111111111", report_system_prompt="", updated_by=None)  # noqa: E501
    monkeypatch.setattr(svc, "_get_or_create_settings", AsyncMock(return_value=settings))  # noqa: E501
    monkeypatch.setattr(
        svc,
        "_fetch_settings_row",
        AsyncMock(
            return_value=SimpleNamespace(
                report_system_prompt="新提示词", updated_at=datetime(2024, 1, 1)
            )
        ),
    )
    out = await svc.update_workbench_settings(
        session,  # type: ignore[arg-type]
        SimpleNamespace(report_system_prompt="  新提示词  "),
        user_id="u1",
    )
    assert out.report_system_prompt == "新提示词"
    session.commit.assert_awaited_once()


# ── 附件上传/读取/删除 ──────────────────────────────────


def _fake_upload(filename: str, content: bytes = b"x") -> Any:
    upload = MagicMock()
    upload.filename = filename
    return upload


@pytest.mark.asyncio
async def test_upload_workbench_attachment_md_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        svc, "read_upload_secure",
        AsyncMock(return_value=("a.md", b"# md")),
    )
    monkeypatch.setattr(svc, "sniff_upload_mime", lambda *a: "text/markdown")
    stored: list[tuple[str, str]] = []
    monkeypatch.setattr(
        svc, "store_file", lambda sub, key, data, ctype: stored.append((key, data.decode()))  # noqa: E501
    )
    # 空文件名
    with pytest.raises(AppException, match="附件文件名不能为空"):
        await svc.upload_workbench_attachment(session, _fake_upload(""), "u1")  # type: ignore[arg-type]  # noqa: E501
    # .md → converted 指向原 key
    desc = await svc.upload_workbench_attachment(
        session, _fake_upload("x.md"), "u1"  # type: ignore[arg-type]
    )
    assert desc.converted is True
    assert desc.converted_md_key == desc.storage_key
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_workbench_word_convert_failure_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(commit=AsyncMock())
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
    stored: list[str] = []
    monkeypatch.setattr(
        svc, "store_file", lambda sub, key, data, ctype: stored.append(key)
    )
    desc = await svc.upload_workbench_attachment(
        session, _fake_upload("a.docx"), "u1"  # type: ignore[arg-type]
    )
    assert desc.converted is False
    assert desc.converted_md_key is None


@pytest.mark.asyncio
async def test_upload_workbench_word_with_images_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        svc, "read_upload_secure", AsyncMock(return_value=("a.docx", b"docx"))
    )
    monkeypatch.setattr(
        svc, "sniff_upload_mime", lambda *a: "application/msword"
    )
    images = [
        SimpleNamespace(name="img1.png", data=b"png", content_type="image/png")
    ]
    monkeypatch.setattr(
        svc, "render_word_to_md",
        lambda name, content: ("test ![image](img1.png)", images),
    )
    monkeypatch.setattr(svc, "MD_IMAGE_REF_RE", __import__("re").compile(r"!\[image\]\((.*?)\)"))  # noqa: E501
    stored: list[str] = []
    monkeypatch.setattr(
        svc, "store_file", lambda sub, key, data, ctype: stored.append(key)
    )
    deleted: list[str] = []
    monkeypatch.setattr(
        svc, "delete_file", lambda sub, key: deleted.append(key)
    )
    # 成功路径：图片资产 + md 均入库
    desc = await svc.upload_workbench_attachment(
        session, _fake_upload("a.docx"), "u1"  # type: ignore[arg-type]
    )
    assert desc.converted is True
    assert len(desc.asset_keys) == 1
    # 清理路径：图片资产写入失败时回滚已存对象
    stored.clear()
    deleted.clear()

    def _store_with_image_failure(sub: str, key: str, data: bytes, ctype: str) -> None:
        stored.append(key)
        if key.endswith(".png"):
            raise RuntimeError("image store failed")

    monkeypatch.setattr(svc, "store_file", _store_with_image_failure)
    with pytest.raises(RuntimeError, match="image store failed"):
        await svc.upload_workbench_attachment(
            session, _fake_upload("a.docx"), "u1"  # type: ignore[arg-type]
        )
    # 原件先写入、后续步骤失败 → 已登记 key 全部回滚删除
    assert deleted
    assert set(deleted) <= set(stored)


def test_read_workbench_attachment_content_and_delete_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        svc, "read_file",
        lambda sub, key: (b"data", "application/octet-stream") if key == "k1" else None,
    )
    monkeypatch.setattr(
        svc, "sniff_upload_mime", lambda name, data: "text/plain"
    )
    data, ctype = svc.read_workbench_attachment_content("k1")
    assert ctype == "text/plain"
    assert svc.read_workbench_attachment_content("missing") == (
        b"", "application/octet-stream"
    )
    deleted: list[str] = []
    monkeypatch.setattr(
        svc, "delete_file",
        lambda sub, key: deleted.append(key) if key != "bad" else (_ for _ in ()).throw(RuntimeError("x")),  # noqa: E501
    )
    svc.delete_workbench_attachment_files(["", "k2", "bad"])
    assert "k2" in deleted


@pytest.mark.asyncio
async def test_get_and_delete_workbench_report(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _report(
        attachments=[
            {"id": "a1", "storage_key": "s1", "converted_md_key": "m1", "asset_keys": []}  # noqa: E501
        ]
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=report),
        commit=AsyncMock(),
    )
    detail = await svc.get_workbench_report_detail(session, "r1")  # type: ignore[arg-type]  # noqa: E501
    assert detail.code == "WB-1"
    monkeypatch.setattr(
        svc, "attachment_storage_keys", lambda att: ["s1", "m1"]
    )
    deleted: list[str] = []
    monkeypatch.setattr(
        svc, "delete_file", lambda sub, key: deleted.append(key)
    )
    await svc.delete_workbench_report(session, "r1", user_id="u1")  # type: ignore[arg-type]  # noqa: E501
    assert report.is_deleted is True
    assert set(deleted) == {"s1", "m1"}
    session.commit.assert_awaited_once()
    # 不存在/已删除 → 404
    session.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException):
        await svc.get_workbench_report_detail(session, "r9")  # type: ignore[arg-type]


# ── analyze：LLM 失败路径 ───────────────────────────────


def _fake_analyze_db() -> tuple[Any, list[Any]]:
    created: list[Any] = []

    def _add(report: Any) -> None:
        # 真实 ORM 对象在 flush 前 id/时间字段均未赋值，
        # 预填避免 _detail_to_schema 校验失败
        report.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        report.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        report.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
        created.append(report)

    session = SimpleNamespace(
        add=_add,
        flush=AsyncMock(),
        commit=AsyncMock(),
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: created[0])),
        get=AsyncMock(return_value=None),
    )
    return session, created


def _request() -> Any:
    return SimpleNamespace(
        source_type="manual",
        source_record_id=None,
        manual_text="灌装压力超限",
        attachments=[],
    )


@pytest.mark.asyncio
async def test_analyze_workbench_success_with_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, created = _fake_analyze_db()
    monkeypatch.setattr(
        svc, "generate_code", AsyncMock(return_value="WB-2024-001")
    )
    monkeypatch.setattr(
        svc, "_get_or_create_settings", AsyncMock(return_value=SimpleNamespace(report_system_prompt=""))  # noqa: E501
    )
    monkeypatch.setattr(
        svc, "_build_context", AsyncMock(return_value=({"s": 1}, "语境", "概述"))
    )
    monkeypatch.setattr(
        svc, "get_config", AsyncMock(return_value=SimpleNamespace(model_name="llm-a"))
    )
    valid_payload = {
        "deviation_summary": "概述",
        "analysis": {"人": "因素"},
        "direct_cause": "直接",
        "root_cause": "根本",
        "conclusion": "结论",
        "recommendations": [],
        "referenced_sources": [],
    }
    chat_json = AsyncMock(
        side_effect=[LLMRateLimitError("429", status_code=429), valid_payload]
    )
    monkeypatch.setattr(svc, "llm_client", SimpleNamespace(chat_json=chat_json))

    detail = await svc.analyze_workbench(session, _request(), user_id="u1")  # type: ignore[arg-type]  # noqa: E501
    assert detail.status == "completed"
    assert created[0].report_payload["direct_cause"] == "直接"
    assert created[0].model_name == "llm-a"
    assert chat_json.await_count == 2  # 第一次 429 重试


@pytest.mark.asyncio
async def test_analyze_workbench_llm_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for exc, expected in [
        (LLMRateLimitError("429", status_code=429), "AI 限流"),
        (LLMOutputError("bad"), "AI 输出格式错误"),
        (LLMProviderError("down", status_code=502), "AI 服务调用失败"),
    ]:
        session, created = _fake_analyze_db()
        monkeypatch.setattr(svc, "generate_code", AsyncMock(return_value="WB-1"))
        monkeypatch.setattr(
            svc, "_get_or_create_settings", AsyncMock(return_value=SimpleNamespace(report_system_prompt=""))  # noqa: E501
        )
        monkeypatch.setattr(
            svc, "_build_context", AsyncMock(return_value=({"s": 1}, "语境", "概述"))
        )
        monkeypatch.setattr(
            svc,
            "get_config",
            AsyncMock(return_value=SimpleNamespace(model_name="llm-a")),
        )
        monkeypatch.setattr(
            svc, "llm_client", SimpleNamespace(chat_json=AsyncMock(side_effect=exc))
        )
        with patch.object(svc.asyncio, "sleep", new=AsyncMock()):
            detail = await svc.analyze_workbench(session, _request(), user_id="u1")  # type: ignore[arg-type]  # noqa: E501
        assert detail.status == "failed"
        assert expected in detail.error_message


@pytest.mark.asyncio
async def test_analyze_workbench_config_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, created = _fake_analyze_db()
    monkeypatch.setattr(svc, "generate_code", AsyncMock(return_value="WB-1"))
    monkeypatch.setattr(
        svc, "_get_or_create_settings", AsyncMock(return_value=SimpleNamespace(report_system_prompt=""))  # noqa: E501
    )
    monkeypatch.setattr(
        svc, "_build_context", AsyncMock(return_value=({"s": 1}, "语境", "概述"))
    )
    monkeypatch.setattr(
        svc, "get_config", AsyncMock(side_effect=LLMConfigError("no config"))
    )
    detail = await svc.analyze_workbench(session, _request(), user_id="u1")  # type: ignore[arg-type]  # noqa: E501
    assert detail.status == "failed"
    assert detail.error_message == "AI 服务尚未配置"


# ── 检索辅助与快照补充分支 ──


def test_split_keywords_edges() -> None:
    assert svc._split_keywords("") == []
    assert svc._split_keywords("  \t ") == []
    kws = svc._split_keywords(
        "a 精密 精密 灌装、压塞；灭菌 干燥 清洗 灯检 贴标 装箱 仓储"
    )
    assert "a" not in kws  # 长度不足 2 被清洗
    assert kws.count("精密") == 1  # 去重
    assert len(kws) == 8  # 上限截断


async def test_retrieve_documents_dedupes_entries() -> None:
    entry = MagicMock(id="doc-1", code="PC-1", name="压塞机操作")
    with (
        patch.object(
            svc,
            "list_document_entries",
            AsyncMock(return_value=([entry, entry], 2)),
        ),
        patch.object(
            svc,
            "read_entry_md_contents",
            return_value=[{"md_text": "标准内容"}],
        ),
    ):
        result = await svc._retrieve_documents(None, ["压塞"])  # type: ignore[arg-type]
    assert len(result) == 1  # 重复条目被去重
    assert result[0]["code"] == "PC-1"
    assert result[0]["content"] == "标准内容"


async def test_retrieve_training_ledgers_empty_and_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await svc._retrieve_training_ledgers(None, []) == []  # type: ignore[arg-type]

    async def _hr_down(
        _db: Any, keywords: list[str], *, limit: int = 5
    ) -> list[dict[str, Any]]:
        raise RuntimeError("hr down")

    monkeypatch.setattr("app.modules.hr.public_api.query_training_ledgers", _hr_down)
    assert await svc._retrieve_training_ledgers(None, ["灌装"]) == []  # type: ignore[arg-type]


async def test_build_context_with_retrievals_and_extra_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    from app.modules.quality.schemas.deviation_workbench import (
        CreateDeviationWorkbenchRequest,
        DeviationWorkbenchAttachmentIn,
    )

    monkeypatch.setattr(
        svc,
        "_retrieve_historical_deviations",
        AsyncMock(
            return_value=[
                {
                    "code": "HD-1",
                    "deviation_event": "压塞压力超上限",
                    "deviation_content": "内容",
                    "root_cause": "传感器漂移",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        svc,
        "_retrieve_documents",
        AsyncMock(return_value=[{"code": "PC-1", "name": "压塞机", "content": "标准"}]),
    )
    monkeypatch.setattr(
        svc,
        "_retrieve_training_ledgers",
        AsyncMock(return_value=[{"training_subject": "压塞机操作培训"}]),
    )
    monkeypatch.setattr(
        svc, "_attachment_context_text", AsyncMock(return_value="附件内容")
    )

    request = CreateDeviationWorkbenchRequest(
        source_type="manual",
        manual_text="灌装线压塞压力超上限",
        affected_items="产品A 批号B",
        supplement_text="已停机检查",
        attachments=[
            DeviationWorkbenchAttachmentIn(
                id="att-1",
                file_name="a.docx",
                storage_key="uploads/a.docx",
                content_type="application/octet-stream",
                file_size=10,
            )
        ],
    )
    snapshot, context_text, summary = await svc._build_context(None, request)  # type: ignore[arg-type]
    assert snapshot["source"]["affected_items"] == "产品A 批号B"
    assert snapshot["source"]["supplement_text"] == "已停机检查"
    assert snapshot["historical_deviations"][0]["code"] == "HD-1"
    assert snapshot["historical_deviations"][0]["deviation_event"] == "压塞压力超上限"
    assert snapshot["documents"][0]["code"] == "PC-1"
    assert snapshot["training_ledgers"][0]["training_subject"] == "压塞机操作培训"
    assert "【附件：a.docx】" in context_text
    assert summary == "灌装线压塞压力超上限"


async def test_build_context_from_report_record_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.quality.schemas.deviation_workbench import (
        CreateDeviationWorkbenchRequest,
    )

    monkeypatch.setattr(
        "app.modules.quality.service.tracking_records.get_deviation_report_record_from_feishu",
        AsyncMock(
            return_value={
                "deviation_code": "DR-2026-001",
                "description": "压塞压力超上限",
                "product_batch": "批号B-01",
                "department": "灌装车间",
                "report_time": "2026-08-01",
                "attachments": [
                    {"name": "a.pdf", "url": "http://x/a.pdf", "type": "pdf"}
                ],
            }
        ),
    )
    monkeypatch.setattr(
        svc, "_retrieve_historical_deviations", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(svc, "_retrieve_documents", AsyncMock(return_value=[]))
    monkeypatch.setattr(svc, "_retrieve_training_ledgers", AsyncMock(return_value=[]))
    monkeypatch.setattr(svc, "_attachment_context_text", AsyncMock(return_value=""))

    request = CreateDeviationWorkbenchRequest(
        source_type="report_record",
        source_record_id="rec-dr-1",
    )
    snapshot, context_text, _ = await svc._build_context(None, request)  # type: ignore[arg-type]
    assert snapshot["source"]["deviation_code"] == "DR-2026-001"
    assert "批号B-01" in context_text

    # 报告记录读取失败（AppException）→ 来源降级为空；仍需其余输入支撑上下文
    async def _raise(_db: Any, record_id: str) -> dict[str, Any]:
        raise AppException(message="飞书记录不存在")

    monkeypatch.setattr(
        "app.modules.quality.service.tracking_records.get_deviation_report_record_from_feishu",
        _raise,
    )
    degraded = CreateDeviationWorkbenchRequest(
        source_type="report_record",
        source_record_id="rec-dr-1",
        manual_text="灌装线压塞压力超上限",
    )
    snapshot, _, _ = await svc._build_context(None, degraded)  # type: ignore[arg-type]
    assert snapshot["source"] == {"manual_text": "灌装线压塞压力超上限"}

