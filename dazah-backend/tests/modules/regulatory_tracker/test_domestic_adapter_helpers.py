"""domestic 爬虫适配器纯 helper 测试：文本清洗、日期解析、document_id 构造。"""

from datetime import date

from app.modules.regulatory_tracker.crawler.adapters.domestic import (
    CdeCrawlerAdapter,
    _build_document_id,
    _clean_text,
    _parse_date_text,
    _strip_trailing_date,
)


def test_clean_text_collapses_whitespace_and_nbsp() -> None:
    assert _clean_text("  药品\t注册\x0a指南 ") == "药品 注册 指南"
    assert _clean_text(None) == ""
    assert _clean_text("") == ""


def test_strip_trailing_date_removes_variants() -> None:
    assert _strip_trailing_date("药物临床试验 2024-01-05") == "药物临床试验"
    assert _strip_trailing_date("指导原则2024年1月5日") == "指导原则"
    # 无尾随日期时保持清洗后的原文
    assert _strip_trailing_date("普通标题 无日期") == "普通标题 无日期"


def test_parse_date_text_variants() -> None:
    assert _parse_date_text("发布：2024-01-05") == date(2024, 1, 5)
    assert _parse_date_text("2024/1/5") == date(2024, 1, 5)
    assert _parse_date_text("2024年01月05日") == date(2024, 1, 5)
    assert _parse_date_text("编号20240105文件") == date(2024, 1, 5)
    assert _parse_date_text("无日期") is None
    assert _parse_date_text(None) is None
    assert _parse_date_text("2024-13-40") is None  # 非法日期回落


def test_build_document_id_known_patterns_and_fallback() -> None:
    assert (
        _build_document_id("nmpa", "https://x/news/12345.html", "t") == "nmpa:12345"
    )
    assert _build_document_id("nmpa", "https://x/998.html", "t") == "nmpa:998"
    assert (
        _build_document_id("cde", "https://x/t2024_6789.htm", "t") == "cde:6789"
    )
    assert (
        _build_document_id("moa", "https://x/P03.docx", "t") == "moa:P03"
    )
    digest_id = _build_document_id("ivdc", "https://x/other/path", "标题")
    assert digest_id.startswith("ivdc:") and len(digest_id.split(":")[1]) == 16
    # 同一 url+title 稳定
    assert digest_id == _build_document_id("ivdc", "https://x/other/path", "标题")


def test_cde_resolve_max_pages_bounds_and_env(monkeypatch) -> None:
    assert CdeCrawlerAdapter._resolve_max_pages(10) == 3
    assert CdeCrawlerAdapter._resolve_max_pages(0) == 1
    assert CdeCrawlerAdapter._resolve_max_pages(2) == 2
    monkeypatch.setenv("REGULATORY_TRACKER_CDE_MAX_PAGES", "5")
    assert CdeCrawlerAdapter._resolve_max_pages(None) == 3
    monkeypatch.setenv("REGULATORY_TRACKER_CDE_MAX_PAGES", "abc")
    assert CdeCrawlerAdapter._resolve_max_pages(None) == 1


def test_cde_to_crawled_record_maps_and_embeds_raw() -> None:
    adapter = CdeCrawlerAdapter.__new__(CdeCrawlerAdapter)
    normalized = {
        "document_id": "d-1",
        "title": "指导原则",
        "original_url": "https://cde/x",
        "publish_date": date(2024, 1, 1),
        "summary": "摘要",
    }
    rec = adapter._to_crawled_record(normalized, {"raw": 1})
    assert rec.source_site == "cde"
    assert rec.document_id == "d-1"
    assert rec.title == "指导原则"
    assert rec.raw_data["raw"] == 1
    assert rec.raw_data["normalized_record"] == normalized
