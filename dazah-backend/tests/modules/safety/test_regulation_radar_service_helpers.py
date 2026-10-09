"""法规雷达编排层辅助函数与外部依赖分支的单测。"""

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.exceptions import AppException
from app.modules.safety.crawler.types import CrawledRegulation
from app.modules.safety.service import regulation_radar as radar

_COLUMN_HTML = (
    "<html><body><nav>导航</nav><script>x=1</script>"
    "<p>" + "某安全生产管理条例正文内容" * 20 + "</p></body></html>"
)


def _response(
    body: bytes,
    *,
    url: str = "https://example.gov.cn/art/1.html",
    status: int = 200,
    content_type: str = "text/html",
) -> httpx.Response:
    return httpx.Response(
        status,
        content=body,
        headers={"content-type": content_type},
        request=httpx.Request("GET", url),
    )


def _item(**overrides: Any) -> CrawledRegulation:
    base: dict[str, Any] = {
        "site_code": "mem_tzgg",
        "site_name": "应急管理部·通知公告",
        "title": "某安全生产管理条例",
        "url": "https://www.mem.gov.cn/art/1.html",
    }
    base.update(overrides)
    return CrawledRegulation(**base)


# ── 名称匹配 ──


def test_name_index_and_match_prefers_exact_then_containment() -> None:
    rows = [
        {"record_id": "r1", "name": "危险化学品安全管理条例"},
        {"record_id": "r2", "name": "建筑设计防火规范"},
        {"record_id": "r3", "name": "短名"},
    ]
    index = radar._build_index(rows)
    # 过短名称不入索引
    assert radar._norm_key("短名") not in index

    exact = radar._find_match(_item(title="危险化学品安全管理条例"), index)
    assert exact is not None and exact["record_id"] == "r1"

    # 名称带年份后缀时走包含匹配
    contained = radar._find_match(
        _item(title="建筑设计防火规范2026年版"), index
    )
    assert contained is not None and contained["record_id"] == "r2"

    assert radar._find_match(_item(title="极短"), index) is None
    assert radar._find_match(_item(title="完全不相关的法规名称"), index) is None


def test_parse_row_date_supports_timestamps_iso_and_invalid() -> None:
    assert radar._parse_row_date(None) is None
    ms = int(datetime(2025, 3, 14, tzinfo=UTC).timestamp() * 1000)
    assert radar._parse_row_date(ms) == date(2025, 3, 14)
    assert radar._parse_row_date("2025-03-14") == date(2025, 3, 14)
    assert radar._parse_row_date("无日期") is None
    assert radar._parse_row_date("2025-13-40") is None
    assert radar._parse_row_date(object()) is None


# ── 设置与表格字段 ──


@pytest.mark.anyio
async def test_load_settings_reports_missing_and_incomplete_configuration(
    db_session, monkeypatch
) -> None:
    async def _none(_db: Any) -> None:
        return None

    monkeypatch.setattr(radar, "_load_settings_impl", _none, raising=False)
    # 无配置行：直接查库得到空
    with pytest.raises(AppException):
        await radar._load_settings(db_session)

    from app.modules.safety.models import SafetyFeishuAppSettings

    row = SafetyFeishuAppSettings(app_id="cli_x", app_secret="secret", is_enabled=True)
    db_session.add(row)
    await db_session.commit()
    try:
        # 缺 App Token / Table ID 时同样拒绝
        with pytest.raises(AppException) as excinfo:
            await radar._load_settings(db_session)
        assert "EHS 法规库" in excinfo.value.message

        row.knowledge_app_token = "tok"
        row.knowledge_table_id = "tbl"
        await db_session.commit()
        loaded = await radar._load_settings(db_session)
        assert loaded.id == row.id
    finally:
        await db_session.rollback()
        await db_session.delete(row)
        await db_session.commit()


def test_table_row_normalizes_feishu_field_shapes() -> None:
    raw = {
        "record_id": "rec-1",
        "fields": {
            "法规编号": "001",
            "法律法规及标准名称": [{"text": "某条例名称"}],
            "法规类别": [{"text": "一安全类"}],
            "颁布机关": [{"text": "应急管理部"}],
            "法规状态": "现行有效",
            "法规链接": {"link": "https://example.com/a", "text": "官方"},
            "颁布修订日期": 1741392000000,
        },
    }
    row = radar._table_row(raw)
    assert row["record_id"] == "rec-1"
    assert row["no"] == "001"
    assert row["name"] == "某条例名称"
    assert row["link"] == "https://example.com/a"
    assert row["promulgation_date"] == 1741392000000
    # 空字段不抛错
    empty = radar._table_row({})
    assert empty["name"] == "" and empty["link"] == ""


@pytest.mark.anyio
async def test_fetch_table_rows_uses_bitable_client() -> None:
    records = [{"record_id": "rec-1", "fields": {"法律法规及标准名称": "某条例"}}]
    client = AsyncMock()
    client.search_records.return_value = records

    rows = await radar.fetch_table_rows(client, "tbl")

    client.search_records.assert_awaited_once_with(table_id="tbl", page_size=500)
    assert rows[0]["record_id"] == "rec-1"


def test_next_sequential_nos_follows_existing_numbers() -> None:
    rows = [{"no": "163"}, {"no": "002"}, {"no": "无编号"}]
    assert radar._next_sequential_nos(rows, 2) == ["164", "165"]
    assert radar._next_sequential_nos([], 1) == ["1"]


# ── 详情页与附件 ──


@pytest.mark.anyio
async def test_fetch_detail_text_strips_scripts_and_skips_pdf() -> None:
    class OkClient:
        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            return _response(_COLUMN_HTML.encode("utf-8"))

    text = await radar._fetch_detail_text(OkClient(), "https://example.gov.cn/a.html")  # type: ignore[arg-type]
    assert text is not None
    assert "脚本" not in text and "x=1" not in text
    assert "某安全生产管理条例正文内容" in text

    class PdfClient:
        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            return _response(b"%PDF-1.4", content_type="application/pdf")

    assert await radar._fetch_detail_text(PdfClient(), "https://x/a.pdf") is None  # type: ignore[arg-type]

    class ShortClient:
        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            return _response(b"<html>short</html>")

    assert await radar._fetch_detail_text(ShortClient(), "https://x/a.html") is None  # type: ignore[arg-type]

    class FailClient:
        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            raise httpx.ConnectError("down", request=httpx.Request("GET", url))

    assert await radar._fetch_detail_text(FailClient(), "https://x/a.html") is None  # type: ignore[arg-type]

    class Not200Client:
        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            return _response(b"", status=500)

    assert await radar._fetch_detail_text(Not200Client(), "https://x/a.html") is None  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_fetch_attachment_uploads_first_matching_file() -> None:
    page = (
        '<html><body><a href="/files/条例.pdf">附件下载</a>'
        '<a href="/files/logo.png">图片</a></body></html>'
    )

    class Client:
        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            if url.endswith(".pdf"):
                return _response(b"pdf-bytes", url=url, content_type="application/pdf")
            return _response(page.encode("utf-8"), url=url)

    bitable = AsyncMock()
    bitable.upload_media.return_value = "file-token-1"

    token = await radar._fetch_attachment_for_record(
        Client(), "https://example.gov.cn/art/1.html", bitable  # type: ignore[arg-type]
    )

    assert token == "file-token-1"
    bitable.upload_media.assert_awaited_once()
    args = bitable.upload_media.await_args.args
    # 附件名优先取链接文字，其次取路径文件名
    assert args[0] == b"pdf-bytes" and args[1] == "附件下载"


@pytest.mark.anyio
async def test_fetch_attachment_returns_none_when_unavailable() -> None:
    bitable = AsyncMock()

    class NoLinkClient:
        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            return _response(b"<html><body>no links</body></html>")

    assert (
        await radar._fetch_attachment_for_record(
            NoLinkClient(), "https://x/a.html", bitable  # type: ignore[arg-type]
        )
        is None
    )

    class FailClient:
        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            raise httpx.ConnectError("down", request=httpx.Request("GET", url))

    assert (
        await radar._fetch_attachment_for_record(
            FailClient(), "https://x/a.html", bitable  # type: ignore[arg-type]
        )
        is None
    )
    bitable.upload_media.assert_not_awaited()


# ── AI 相关性过滤与结构化 ──


@pytest.mark.anyio
async def test_ai_relevance_filter_handles_empty_and_client_failures(
    monkeypatch,
) -> None:
    from app.core.llm import llm_client

    assert await radar._ai_relevance_filter([]) == ([], None)

    async def _config_error(*args: Any, **kwargs: Any) -> Any:
        from app.core.llm.exceptions import LLMConfigError

        raise LLMConfigError("未配置")

    monkeypatch.setattr(llm_client, "chat_json", _config_error)
    keep, error = await radar._ai_relevance_filter(["某条例"])
    assert keep == [False] and error is not None and "未配置 LLM" in error

    async def _output_error(*args: Any, **kwargs: Any) -> Any:
        from app.core.llm.exceptions import LLMOutputError

        raise LLMOutputError("坏输出")

    monkeypatch.setattr(llm_client, "chat_json", _output_error)
    keep, error = await radar._ai_relevance_filter(["某条例"])
    assert keep == [False] and error is not None and "LLM 输出无效" in error

    async def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("供应商挂了")

    monkeypatch.setattr(llm_client, "chat_json", _boom)
    keep, error = await radar._ai_relevance_filter(["某条例"])
    assert keep == [False] and error is not None and "RuntimeError" in error


@pytest.mark.anyio
async def test_ai_relevance_filter_keeps_valid_entries_only(monkeypatch) -> None:
    from app.core.llm import llm_client

    async def _ok(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "results": [
                {"index": 0, "relevant": True},
                {"index": 2, "relevant": True},
                {"index": 9, "relevant": True},  # 越界忽略
                {"index": "x", "relevant": True},  # 类型错误忽略
                "not-a-dict",
            ]
        }

    monkeypatch.setattr(llm_client, "chat_json", _ok)
    keep, error = await radar._ai_relevance_filter(["A", "B", "C"])
    assert keep == [True, False, True]
    assert error is None

    async def _bad_structure(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"results": "nope"}

    monkeypatch.setattr(llm_client, "chat_json", _bad_structure)
    keep, error = await radar._ai_relevance_filter(["A"])
    assert keep == [False] and error == "LLM 输出结构不符合预期"


@pytest.mark.anyio
async def test_analyze_regulation_normalizes_category_and_date(monkeypatch) -> None:
    from app.core.llm import llm_client

    async def _detail(_client: Any, _url: str) -> str | None:
        return "正文节选" * 40

    monkeypatch.setattr(radar, "_fetch_detail_text", _detail)

    async def _ok(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "category": "不存在的类别",
            "issuer": " 应急管理部 ",
            "implement_date": "2026/01/01",
            "summary": "要点",
        }

    monkeypatch.setattr(llm_client, "chat_json", _ok)
    analysis = await radar._analyze_regulation(object(), _item())  # type: ignore[arg-type]
    assert analysis is not None
    # 未知类别回落到「其他相关法规」，非法日期置空
    assert analysis["category"] == "其他相关法规"
    assert analysis["issuer"] == "应急管理部"
    assert analysis["implement_date"] is None
    assert analysis["summary"] == "要点"

    async def _valid(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "category": "特种设备",
            "issuer": "",
            "implement_date": "2026-02-01",
            "summary": "",
        }

    monkeypatch.setattr(llm_client, "chat_json", _valid)
    analysis = await radar._analyze_regulation(object(), _item())  # type: ignore[arg-type]
    assert analysis == {
        "category": "特种设备",
        "issuer": None,
        "implement_date": "2026-02-01",
        "summary": None,
        "analyzed_at": analysis["analyzed_at"],
    }

    async def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("AI 挂了")

    monkeypatch.setattr(llm_client, "chat_json", _boom)
    assert await radar._analyze_regulation(object(), _item()) is None  # type: ignore[arg-type]


# ── 写表与摘要 ──


@pytest.mark.anyio
async def test_create_in_table_builds_fields_and_counts_failures() -> None:
    client = AsyncMock()
    client.create_record.return_value = "rec-new"
    outcome = radar.RadarOutcome()
    analysis = {
        "category": "一安全类",
        "issuer": "应急管理部",
        "implement_date": "2026-02-01",
        "summary": "要点",
    }

    record_id = await radar._create_in_table(
        client,
        "tbl-1",
        _item(publish_date=date(2026, 1, 20)),
        outcome,
        analysis=analysis,
        seq_no="164",
        attachment_token="tok-1",
    )

    assert record_id == "rec-new"
    fields = client.create_record.await_args.args[0]
    assert fields["法规编号"] == "164"
    assert fields["法规类别"] == "一安全类"
    assert fields["颁布机关"] == "应急管理部"
    assert fields["核心要点总结"] == "要点"
    assert fields["附件"] == [{"file_token": "tok-1"}]
    assert isinstance(fields["颁布修订日期"], int)
    assert fields["法规链接"]["link"] == _item().url

    # 无 AI 分析时按来源兜底颁布机关；写入失败计数
    client.create_record.return_value = None
    failed = await radar._create_in_table(client, "tbl-1", _item(), outcome)
    assert failed is None
    assert outcome.failed_count == 1
    fallback_fields = client.create_record.await_args.args[0]
    assert fallback_fields["颁布机关"] == "应急管理部"


def test_build_summary_lines_covers_all_actions() -> None:
    lines = radar._build_summary_lines(
        [
            {
                "action": "new",
                "name": "新法规",
                "url": "https://x/a",
                "date": "2026-01-01",
            },
            {"action": "new", "name": "无链接新法规"},
            {
                "action": "revised",
                "name": "法规B",
                "old_date": "2020-01-01",
                "new_date": "2026-01-01",
            },
            {"action": "obsolete", "name": "法规C"},
            {"action": "link_fixed", "name": "忽略项"},
        ]
    )
    assert lines == [
        "**新增** [新法规](https://x/a)（2026-01-01）",
        "**新增** 无链接新法规",
        "**已修订** 法规B（2020-01-01 → 2026-01-01）",
        "**已废止** 法规C",
    ]


@pytest.mark.anyio
async def test_send_test_notification_raises_on_errors(monkeypatch) -> None:
    async def _ok(*args: Any, **kwargs: Any) -> tuple[int, list[str] | None]:
        return 2, []

    monkeypatch.setattr(radar, "send_radar_notifications", _ok)
    assert await radar.send_test_notification(object()) == {"sent": 2, "errors": []}  # type: ignore[arg-type]

    async def _failed(*args: Any, **kwargs: Any) -> tuple[int, list[str] | None]:
        return 0, ["未配置通知目标"]

    monkeypatch.setattr(radar, "send_radar_notifications", _failed)
    with pytest.raises(AppException) as excinfo:
        await radar.send_test_notification(object())  # type: ignore[arg-type]
    assert "未配置通知目标" in excinfo.value.message

# ── 雷达通知设置落库与抓取类型契约 ──


@pytest.mark.anyio
async def test_update_settings_persists_radar_notify_targets(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cryptography.fernet import Fernet

    from app.modules.safety.schemas.feishu_settings import (
        UpdateSafetyFeishuAppSettingsRequest,
    )
    from app.modules.safety.service import feishu_settings

    monkeypatch.setenv("LLM_ENCRYPTION_KEY", Fernet.generate_key().decode())

    detail = await feishu_settings.update_safety_feishu_app_settings(
        db_session,
        UpdateSafetyFeishuAppSettingsRequest(
            app_id="cli_radar",
            app_secret="plain-secret",
            radar_notify_enabled=True,
            radar_notify_chat_ids=["oc_a", "oc_b"],
            radar_notify_user_ids=["ou_a"],
        ),
    )
    assert detail.radar_notify_enabled is True
    assert detail.radar_notify_chat_ids == ["oc_a", "oc_b"]
    assert detail.radar_notify_user_ids == ["ou_a"]

    # 只提交通知目标：未提交的字段保持原值
    trimmed = await feishu_settings.update_safety_feishu_app_settings(
        db_session,
        UpdateSafetyFeishuAppSettingsRequest(
            app_id="cli_radar",
            radar_notify_chat_ids=["oc_only"],
        ),
    )
    assert trimmed.radar_notify_chat_ids == ["oc_only"]
    assert trimmed.radar_notify_user_ids == ["ou_a"]


def test_crawled_regulation_contract_properties() -> None:
    from app.modules.safety.crawler.types import (
        CrawledRegulation,
        CrawlResult,
        normalize_standard_no,
    )

    assert normalize_standard_no(None) is None
    assert normalize_standard_no("某条例") is None
    assert normalize_standard_no("GB/T 30871-2022 危险化学品作业") == "GB/T 30871-2022"

    item = CrawledRegulation(
        site_code="mem_tzgg",
        site_name="应急管理部·通知公告",
        title="危险化学品安全管理条例",
        url="https://mem.gov.cn/art/1.html",
    )
    assert item.core_name == radar.core_name(item.title)
    assert item.standard_no is None

    assert CrawlResult(site_code="s", site_name="S", items=()).ok is True
    assert CrawlResult(site_code="s", site_name="S", items=(), error="boom").ok is False

