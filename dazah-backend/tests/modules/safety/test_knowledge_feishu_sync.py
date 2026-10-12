"""安全知识库 EHS 法规库镜像同步与附件读取测试。"""

from typing import Any

import pytest
from sqlalchemy import delete, select

from app.core.exceptions import AppException
from app.core.llm.encryption import encrypt_api_key
from app.modules.safety.models import (
    SafetyFeishuAppSettings,
    SafetyKnowledgeArticle,
)
from app.modules.safety.service import knowledge_feishu


class _FakeBitableClient:
    """替代 SafetyBitableClient，返回预置记录。"""

    instances: list["_FakeBitableClient"] = []
    records: list[dict[str, Any]] = []
    attachment_bytes: bytes | None = b"pdf-content"

    def __init__(self, app_token: str | None = None, table_id: str | None = None):
        self.app_token = app_token
        self.table_id = table_id
        self.downloaded: list[str] = []
        _FakeBitableClient.instances.append(self)

    async def search_records(self, table_id=None, *, page_size=100, **kwargs):
        return _FakeBitableClient.records

    async def download_attachment(self, file_token, extra=None):
        self.downloaded.append(file_token)
        return _FakeBitableClient.attachment_bytes


def _sample_record(record_id: str, **overrides) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "法规编号": [{"text": "001", "type": "text"}],
        "法律法规及标准名称": [{"text": "《安全生产法》", "type": "text"}],
        "法规类别": "安全类",
        "颁布机关": [{"text": "全国人大", "type": "text"}],
        "颁布修订日期": 1623254400000,
        "实施日期": 1630425600000,
        "法规状态": "现行有效",
        "法规链接": {
            "link": "https://example.gov.cn/law",
            "text": "官网",
            "type": "url",
        },
        "核心要点总结": [{"text": "要点内容", "type": "text"}],
        "备注": [{"text": "备注内容", "type": "text"}],
        "附件": [
            {"file_token": "tokA", "name": "001_安全生产法.pdf", "size": 100},
            {"file_token": "tokB", "name": "附件2.docx", "size": 200},
        ],
    }
    fields.update(overrides)
    return {"record_id": record_id, "fields": fields}


async def _seed_settings(db_session) -> SafetyFeishuAppSettings:
    row = SafetyFeishuAppSettings(
        app_id="cli_test",
        app_secret=encrypt_api_key("secret"),
        bitable_app_token="hazardToken",
        bitable_hazard_table_id="tblHazard",
        knowledge_app_token="knowledgeToken",
        knowledge_table_id="tblKnowledge",
        is_enabled=True,
    )
    db_session.add(row)
    await db_session.commit()
    return row


@pytest.fixture(autouse=True)
async def _clean_tables(db_session):
    yield
    await db_session.execute(delete(SafetyKnowledgeArticle))
    await db_session.execute(delete(SafetyFeishuAppSettings))
    await db_session.commit()


@pytest.fixture(autouse=True)
def _disable_attachment_cache(monkeypatch):
    """测试直连 fetcher，避免磁盘/内存缓存跨用例串扰。"""
    from app.platform.integrations.feishu.attachment_cache import AttachmentCache

    monkeypatch.setattr(
        knowledge_feishu,
        "get_attachment_cache",
        lambda: AttachmentCache(
            enabled=False, cache_dir="", max_memory_mb=1, max_disk_mb=1, ttl_seconds=1
        ),
    )


@pytest.fixture
def fake_client(monkeypatch):
    _FakeBitableClient.instances = []
    _FakeBitableClient.records = []
    monkeypatch.setattr(
        knowledge_feishu, "SafetyBitableClient", _FakeBitableClient
    )
    return _FakeBitableClient


async def _get_articles(db_session) -> list[SafetyKnowledgeArticle]:
    result = await db_session.execute(
        select(SafetyKnowledgeArticle).where(
            SafetyKnowledgeArticle.is_deleted.is_(False)
        )
    )
    return list(result.scalars().all())


# ── 字段解析 ──


def test_join_text_handles_segments_str_and_none():
    assert knowledge_feishu._join_text([{"text": "a"}, {"text": "b"}]) == "ab"
    assert knowledge_feishu._join_text("直传") == "直传"
    assert knowledge_feishu._join_text(None) == ""


def test_ms_to_datetime_converts_and_rejects_garbage():
    parsed = knowledge_feishu._ms_to_datetime(1623254400000)
    assert parsed is not None and parsed.tzinfo is not None
    assert knowledge_feishu._ms_to_datetime("abc") is None
    assert knowledge_feishu._ms_to_datetime(None) is None


def test_build_article_values_maps_all_ehs_fields():
    values = knowledge_feishu._build_article_values(_sample_record("rec1")["fields"])
    assert values["article_no"] == "001"
    assert values["title"] == "《安全生产法》"
    assert values["regulation_category"] == "安全类"
    assert values["category"] == "laws_regulations"
    assert values["source"] == "全国人大"
    assert values["regulation_link"] == "https://example.gov.cn/law"
    assert values["regulation_status"] == "现行有效"
    assert values["summary"] == "要点内容"
    assert values["notes"] == "备注内容"
    assert values["promulgation_date"] is not None
    assert values["implement_date"] is not None
    assert [a["file_token"] for a in values["feishu_attachments"]] == ["tokA", "tokB"]


def test_parse_link_rejects_dangerous_schemes():
    assert knowledge_feishu._parse_link(
        {"link": "https://ok.example/law"}
    ) == "https://ok.example/law"
    assert knowledge_feishu._parse_link({"link": "http://a.com"}) == "http://a.com"
    # 危险协议与垃圾值一律丢弃，防止前端 href 存储型 XSS
    assert knowledge_feishu._parse_link({"link": "javascript:alert(1)"}) == ""
    assert knowledge_feishu._parse_link("JAVASCRIPT:alert(1)") == ""
    assert knowledge_feishu._parse_link({"link": "data:text/html,x"}) == ""
    assert knowledge_feishu._parse_link({"link": ""}) == ""
    assert knowledge_feishu._parse_link(None) == ""


def test_build_article_values_standard_category_maps_to_standards():
    values = knowledge_feishu._build_article_values(
        _sample_record("rec1", **{"法规类别": "标准类"})["fields"]
    )
    assert values["category"] == "standards"


def test_build_article_values_title_fallback():
    values = knowledge_feishu._build_article_values(
        {"法规类别": "安全类", "法规编号": [{"text": "9"}]}
    )
    assert values["title"]  # 缺名称时兜底非空


# ── 同步 ──


async def test_sync_requires_settings(db_session, fake_client):
    with pytest.raises(AppException):
        await knowledge_feishu.sync_knowledge_from_feishu(db_session)


async def test_sync_requires_knowledge_binding(db_session, fake_client):
    row = await _seed_settings(db_session)
    row.knowledge_app_token = None
    await db_session.commit()
    with pytest.raises(AppException) as exc_info:
        await knowledge_feishu.sync_knowledge_from_feishu(db_session)
    assert "EHS 法规库" in str(exc_info.value.message)


async def test_sync_creates_updates_and_removes(db_session, fake_client):
    settings = await _seed_settings(db_session)

    # 第一次：两条记录创建
    fake_client.records = [_sample_record("recA"), _sample_record("recB")]
    result = await knowledge_feishu.sync_knowledge_from_feishu(db_session)
    assert result["created"] == 2 and result["updated"] == 0
    articles = await _get_articles(db_session)
    assert len(articles) == 2

    # 第二次：一条更新字段、一条消失（软删）、一条新增
    fake_client.records = [
        _sample_record("recA", **{"法规状态": "已废止"}),
        _sample_record("recC"),
    ]
    result = await knowledge_feishu.sync_knowledge_from_feishu(db_session)
    assert result["created"] == 1 and result["updated"] == 1 and result["removed"] == 1
    visible = await _get_articles(db_session)
    assert {a.feishu_record_id for a in visible} == {"recA", "recC"}
    updated = next(a for a in visible if a.feishu_record_id == "recA")
    assert updated.regulation_status == "已废止"

    # 手工创建的本地文章不受同步影响
    db_session.add(SafetyKnowledgeArticle(title="本地手册", status="draft"))
    await db_session.commit()
    fake_client.records = [_sample_record("recA")]
    await knowledge_feishu.sync_knowledge_from_feishu(db_session)
    visible = await _get_articles(db_session)
    assert len(visible) == 2  # recA + 本地手册

    await db_session.refresh(settings)
    assert settings.knowledge_last_sync_status == "success"
    assert settings.knowledge_last_synced_at is not None


async def test_sync_bad_row_isolated_and_marked_partial(db_session, fake_client):
    settings = await _seed_settings(db_session)
    bad_record = {
        "record_id": "recBad",
        "fields": {
            "法律法规及标准名称": [{"text": "坏行", "type": "text"}],
            # 超长编号违反 String(100) 约束，验证坏行隔离不中断整体同步
            "法规编号": [{"text": "X" * 200, "type": "text"}],
        },
    }
    fake_client.records = [_sample_record("recOk"), bad_record]
    result = await knowledge_feishu.sync_knowledge_from_feishu(db_session)
    assert result["created"] == 1 and result["failed"] == 1
    await db_session.refresh(settings)
    assert settings.knowledge_last_sync_status == "partial"


# ── 附件 ──


async def test_get_knowledge_attachment_validates_token(db_session, fake_client):
    await _seed_settings(db_session)
    db_session.add(
        SafetyKnowledgeArticle(
            title="t",
            feishu_record_id="recA",
            feishu_attachments=[{"file_token": "tokA", "name": "a.pdf", "size": 1}],
        )
    )
    await db_session.commit()

    content, ctype, name = await knowledge_feishu.get_knowledge_attachment(
        db_session, "recA", "tokA"
    )
    assert content == b"pdf-content"
    assert name == "a.pdf"
    assert ctype == "application/pdf"

    with pytest.raises(AppException):
        await knowledge_feishu.get_knowledge_attachment(db_session, "recA", "tokOther")
    with pytest.raises(AppException):
        await knowledge_feishu.get_knowledge_attachment(
            db_session, "recMissing", "tokA"
        )


async def test_get_knowledge_attachment_fetch_failure_raises_502(
    db_session, fake_client
):
    await _seed_settings(db_session)
    db_session.add(
        SafetyKnowledgeArticle(
            title="t",
            feishu_record_id="recA",
            feishu_attachments=[{"file_token": "tokA", "name": "a.pdf"}],
        )
    )
    await db_session.commit()
    fake_client.attachment_bytes = None
    with pytest.raises(AppException) as exc_info:
        await knowledge_feishu.get_knowledge_attachment(db_session, "recA", "tokA")
    assert exc_info.value.status_code == 502
