"""content_summary_service 综合分支测试。

覆盖 HTML 详情抽取、CJK/英文摘要生成、占位识别、LLM 回退、
429/HTTP 错误重试路径——LLM 与网络均 mock，不连真实服务。
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.llm import llm_client
from app.modules.regulatory_tracker.services import content_summary_service as svc

# ── 纯函数 ──────────────────────────────────────────────


def test_contains_cjk() -> None:
    assert svc.contains_cjk("中文内容")
    assert not svc.contains_cjk("english only")
    assert not svc.contains_cjk("")
    assert not svc.contains_cjk(None)


def test_normalize_summary_length() -> None:
    assert svc.normalize_summary_length("  内容 。 ") == "内容"
    assert svc.normalize_summary_length("短文本") == "短文本"
    long_text = "很" * 120 + "。"
    out = svc.normalize_summary_length(long_text)
    assert out.startswith("很" * 100)
    assert out.endswith("。")


def test_looks_like_placeholder_summary() -> None:
    assert svc.looks_like_placeholder_summary("系统已完成抓取整理")
    assert svc.looks_like_placeholder_summary(
        "This guideline explains gmp implementation"
    )
    assert not svc.looks_like_placeholder_summary("真实摘要内容")
    assert not svc.looks_like_placeholder_summary("")
    assert not svc.looks_like_placeholder_summary(None)


def test_summarize_cjk_text() -> None:
    out = svc.summarize_cjk_text(
        "本指导原则适用于药品生产。正文要求执行GMP。其他内容。", title="指导原则"
    )
    assert out is not None
    assert "适用于" in out and "药品生产" in out
    # 空文本/无有效分句 → None
    assert svc.summarize_cjk_text("   ") is None
    assert svc.summarize_cjk_text("。，；") is None
    # 带发布时间前缀且无空格分隔时整段被剥掉（既有正则行为：\S+ 连吞）
    assert svc.summarize_cjk_text("发布时间：2024年1月1日。第一条要求。") is None
    # 时间戳后有空格的场景正常出摘要
    out2 = svc.summarize_cjk_text("发布时间：2024年1月1日 第一条要求。")
    assert out2 is not None and "第一条要求" in out2
    # 纯文本按分句合并
    out3 = svc.summarize_cjk_text("GMP指南。GMP指南实施细则。")
    assert out3 is not None and "GMP指南实施细则" in out3


def test_summarize_english_text_keyword_rules() -> None:
    out = svc.summarize_english_text(
        "This guidance explains GMP implementation and inspection focus "
        "for manufacturers."
    )
    assert out is not None
    assert "GMP" in out or "质量体系" in out
    # 无关键词时用首句或标题 topic
    out2 = svc.summarize_english_text("Some brief note with no keywords here.")
    assert out2 is not None
    assert "brief note" in out2
    out3 = svc.summarize_english_text(
        "Guidance on real-world data. Second sentence.",
        title="Guidance on real-world data",
    )
    assert "真实世界" in out3
    assert svc.summarize_english_text("   ") is None


def test_localize_english_title() -> None:
    assert "药品生产质量管理规范" in svc._localize_english_title(
        "Good manufacturing practice guidance"
    )
    assert "问答说明" in svc._localize_english_title("Questions and answers")
    assert "附件" in svc._localize_english_title("Annex 2")
    assert svc._localize_english_title("plain title") == "plain title"


def test_build_source_text_dedupes_and_filters_placeholder() -> None:
    raw = {
        "detail_content": "正文内容",
        "detail_content_dup": "正文内容",
        "meta_description": "系统已完成抓取整理，占位",
        "detail_paragraphs": ["段落一", "段落一", "段落二"],
        "summary": "既有摘要",
    }
    out = svc._build_source_text(raw, existing_summary="已有总结")
    assert "正文内容" in out and "段落一" in out and "段落二" in out
    assert "系统已完成抓取整理" not in out
    assert out.count("段落一") == 1
    # existing_summary 为占位时跳过
    out2 = svc._build_source_text(
        {"detail_content": "x"}, existing_summary="系统已完成抓取整理"
    )
    assert "系统已完成" not in out2
    assert svc._build_source_text({"detail_content": "  "}, None) == ""


def test_looks_like_invalid_detail_page() -> None:
    assert svc._looks_like_invalid_detail_page("", "", "") is True
    assert svc._looks_like_invalid_detail_page("标题", "desc", "content") is False
    assert (
        svc._looks_like_invalid_detail_page(
            "server inaccessibility", "", ""
        )
        is True
    )


# ── HTML 抽取 ───────────────────────────────────────────


def test_extract_detail_payload_from_html() -> None:
    long_p = "第一段充分合规的正文内容，长度超过三十字，确保能被段落抽取逻辑收录。"
    html_text = f"""
    <html><head>
      <title>标题A</title>
      <meta name="description" content=" 摘要说明 "/>
    </head><body><main>
      <h1>主标题</h1>
      <p>{long_p}</p>
      <p>{long_p}</p>
      <p>cookie 提示文字加长到超过三十字以验证它不应被收录进正文。</p>
      <p>短</p>
    </main></body></html>
    """
    payload = svc.extract_detail_payload_from_html(html_text)
    assert payload["detail_title"] == "主标题"
    assert payload["meta_description"] == "摘要说明"
    assert "第一段充分合规" in payload["detail_content"]
    assert "cookie" not in payload["detail_content"]
    assert len(payload["detail_paragraphs"]) == 1  # 重复段落去重
    # 无效页返回 {}
    invalid = svc.extract_detail_payload_from_html(
        "<html><body><h1>We apologize for any inconvenience</h1></body></html>"
    )
    assert invalid == {}
    # 纯 body 兜底路径（≥40 字单段）
    fallback = svc.extract_detail_payload_from_html(
        "<html><body>没有具体标签的长正文内容，足够长以便进入兜底抽取逻辑，"
        "这是第二句。这段内容用于验证长度超过四十个字符的兜底抽取路径。</body></html>"
    )
    assert fallback.get("detail_paragraphs")


# ── LLM 摘要与回退 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_short_summary_cjk_shortcut() -> None:
    out = await svc.generate_short_summary(
        title="某指南", raw_data={"detail_content": "中文正文。要求落实。其他内容。"}
    )
    assert out is not None and "要求落实" in out


@pytest.mark.asyncio
async def test_generate_short_summary_llm_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_client,
        "chat_json",
        AsyncMock(return_value={"summary": "这是一条符合要求的中文摘要。"}),
    )
    out = await svc.generate_short_summary(
        title="EMA 指南",
        raw_data={"detail_content": "english content explains a new guidance."},
    )
    # normalize_summary_length 会去掉句末标点
    assert out == "这是一条符合要求的中文摘要"


@pytest.mark.asyncio
async def test_generate_short_summary_llm_failures_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # LLM 抛异常 → 英文规则摘要回退
    monkeypatch.setattr(
        llm_client, "chat_json", AsyncMock(side_effect=RuntimeError("down"))
    )
    out = await svc.generate_short_summary(
        title="GDP 指南",
        raw_data={"detail_content": "good distribution practice content here."},
    )
    assert out is not None and "流通" in out
    # LLM 返回非字符串 → 回退
    monkeypatch.setattr(
        llm_client, "chat_json", AsyncMock(return_value={"summary": 123})
    )
    out2 = await svc.generate_short_summary(
        title="x",
        raw_data={"detail_content": "questions and answers about inspection."},
    )
    assert out2 is not None
    # LLM 返回占位内容 → None
    monkeypatch.setattr(
        llm_client,
        "chat_json",
        AsyncMock(return_value={"summary": "系统已完成抓取整理"}),
    )
    out3 = await svc.generate_short_summary(
        title="x", raw_data={"detail_content": "some english words here"}
    )
    assert out3 is None
    # 无可用源文本 → None
    assert await svc.generate_short_summary(title="x", raw_data={}) is None


# ── 详情页抓取重试 ──────────────────────────────────────


class _FakeResponse:
    def __init__(self, status: int, text: str = "") -> None:
        self.status_code = status
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise svc.httpx.HTTPStatusError(
                "boom", request=MagicMock(), response=MagicMock()
            )


class _FakeClient:
    def __init__(self, queue: list[Any]) -> None:
        # queue 为测试内共享列表：重试循环每次都会新建 client，
        # 必须跨实例共享，否则永远取到同一份响应副本
        self._queue = queue

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def get(self, url: str) -> _FakeResponse:
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _patch_transport(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[Any],
) -> None:
    monkeypatch.setattr(
        svc.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeClient(responses),
    )


@pytest.mark.asyncio
async def test_fetch_detail_payload_429_retry_then_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(svc.asyncio, "sleep", _fake_sleep)
    long_p = "第一段充分合规的正文内容，长度超过三十字，确保能被段落抽取逻辑收录。"
    _patch_transport(
        monkeypatch,
        [
            _FakeResponse(429),
            _FakeResponse(
                200,
                f"<html><body><main><h1>标题</h1><p>{long_p}</p></main></body></html>",
            ),
        ],
    )
    payload = await svc.fetch_detail_payload("https://x/detail")
    assert sleeps == [2.0]
    assert payload.get("detail_title") == "标题"
    assert "第一段充分合规" in (payload.get("detail_content") or "")


@pytest.mark.asyncio
async def test_fetch_detail_payload_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_sleep(seconds: float) -> None:
        pass

    monkeypatch.setattr(svc.asyncio, "sleep", _fake_sleep)
    # 429 三次后放弃（跨 client 实例共享队列依次消费）
    _patch_transport(monkeypatch, [_FakeResponse(429)] * 3)
    assert await svc.fetch_detail_payload("https://x/detail") == {}
    # HTTPStatusError（5xx）立即返回空
    _patch_transport(monkeypatch, [_FakeResponse(500)])
    assert await svc.fetch_detail_payload("https://x/detail") == {}
    # 连接类 HTTPError 重试两次后最终放弃
    _patch_transport(
        monkeypatch,
        [svc.httpx.ConnectError("conn refused")] * 3,
    )
    assert await svc.fetch_detail_payload("https://x/detail") == {}
