"""法规雷达编排逻辑测试（抓取与 AI 均为 mock，不联网）。"""

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.modules.safety.models import RegulationRadarRun
from app.modules.safety.service import regulation_radar


@pytest.fixture(autouse=True)
async def _clean_runs(db_session):
    from app.modules.safety.models import SafetyKnowledgeArticle

    yield
    await db_session.execute(delete(RegulationRadarRun))
    # 版本核查测试会创建带 feishu_record_id 的知识行（服务内部 commit，需显式清理）
    await db_session.execute(
        delete(SafetyKnowledgeArticle).where(
            SafetyKnowledgeArticle.feishu_record_id.in_(["rec-std", "rec-cur"])
        )
    )
    await db_session.commit()


def _table_rows(names: list[str]) -> list[dict]:
    return [
        {
            "record_id": f"rec{i}",
            "no": f"{i:03d}",
            "name": n,
            "link": f"https://example.gov.cn/{i}",
            "promulgation_date": None,
        }
        for i, n in enumerate(names)
    ]


def _item(title: str, days_ago: int | None = 10, semantics: str = "publish",
          site: str = "生态环境部·规章库"):
    from app.modules.safety.crawler.types import CrawledRegulation

    pub = date.today() - timedelta(days=days_ago) if days_ago is not None else None
    return CrawledRegulation(
        site_code="test",
        site_name=site,
        title=title,
        url=f"https://example.gov.cn/{abs(hash(title)) % 10**8}",
        publish_date=pub,
        date_semantics=semantics,
    )


@pytest.fixture
def radar_env(monkeypatch):
    """mock 抓取与 AI，隔离外部依赖。"""

    state = {"table_rows": [], "crawled": [], "ai_keep_all": True, "ai_error": None}

    async def _fake_table(client, table_id):
        return state["table_rows"]

    async def _fake_collect(specs=None):

        outcome = regulation_radar.RadarOutcome(sites_total=1)
        items = tuple(state["crawled"])
        return items, outcome

    async def _fake_ai(titles):
        if state["ai_error"]:
            return [False] * len(titles), state["ai_error"]
        return [state["ai_keep_all"]] * len(titles), None

    async def _fake_analyze(client, item):
        return {
            "category": "一安全类",
            "issuer": "应急管理部",
            "implement_date": None,
            "summary": "测试要点总结",
        }

    monkeypatch.setattr(regulation_radar, "fetch_table_rows", _fake_table)
    monkeypatch.setattr(regulation_radar, "collect_all_sites", _fake_collect)
    monkeypatch.setattr(regulation_radar, "_ai_relevance_filter", _fake_ai)
    monkeypatch.setattr(regulation_radar, "_analyze_regulation", _fake_analyze)
    # 飞书客户端 mock：记录写入
    writes: list[dict] = []

    class _FakeClient:
        async def create_record(self, fields, table_id=None):
            writes.append(fields)
            return f"rec-new-{len(writes)}"

    updates: list[dict] = []

    class _FakeClient:
        async def create_record(self, fields, table_id=None):
            writes.append(fields)
            return f"rec-new-{len(writes)}"

        async def update_record(self, record_id, fields, table_id=None):
            updates.append({"record_id": record_id, "fields": fields})
            return True

        async def upload_media(self, file_bytes, file_name, parent_type=None):
            return f"tok-{len(file_bytes)}"

    monkeypatch.setattr(
        regulation_radar, "SafetyBitableClient", lambda **kw: _FakeClient()
    )
    state["writes"] = writes
    state["updates"] = updates
    return state


async def _load_settings_ok(db_session, monkeypatch):
    async def _fake(db):
        class _S:
            knowledge_app_token = "tok"
            knowledge_table_id = "tbl"
            is_enabled = True
            radar_notify_enabled = False
            radar_notify_chat_ids: list = []
            radar_notify_user_ids: list = []

        return _S()

    monkeypatch.setattr(regulation_radar, "_load_settings", _fake)


async def test_new_relevant_regulation_is_counted(db_session, radar_env, monkeypatch):
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["crawled"] = [_item("危险化学品重大危险源辨识（2026年版）", days_ago=5)]

    res = await regulation_radar.run_radar(db_session, dry_run=True)
    assert res["new_count"] == 1
    assert res["items"][0]["action"] == "new"
    assert res["dry_run"] is True
    # 干跑不写飞书
    assert not radar_env["writes"]


async def test_known_regulation_is_skipped(db_session, radar_env, monkeypatch):
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["table_rows"] = _table_rows(["《安全生产法》"])
    radar_env["crawled"] = [_item("中华人民共和国安全生产法", days_ago=5)]

    res = await regulation_radar.run_radar(db_session, dry_run=True)
    assert res["new_count"] == 0
    assert res["skipped_count"] >= 1


async def test_old_items_outside_window_are_skipped(db_session, radar_env, monkeypatch):
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["crawled"] = [
        _item("三年前的旧法规", days_ago=800),
        _item("未来实施日期的条目", days_ago=None),
    ]

    res = await regulation_radar.run_radar(db_session, dry_run=True)
    assert res["new_count"] == 0


async def test_implement_semantics_skipped_for_new(db_session, radar_env, monkeypatch):
    """标准库（实施日期语义）不作为新法规来源，避免日期语义混淆。"""
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["crawled"] = [_item("某排放标准", days_ago=5, semantics="implement")]

    res = await regulation_radar.run_radar(db_session, dry_run=True)
    assert res["new_count"] == 0


async def test_ai_irrelevant_items_are_dropped_on_real_run(
    db_session, radar_env, monkeypatch
):
    """真实写入模式：AI 判为不相关的候选被丢弃，不写飞书。"""
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["cand_date"] = None
    radar_env["crawled"] = [
        _item("摩托车污染物排放限值", days_ago=3),
        _item("危险化学品重大危险源辨识", days_ago=4),
    ]
    # AI 只保留第二条
    async def _ai_selective(titles):
        return ["摩托车污染物排放限值" not in t for t in titles], None

    monkeypatch.setattr(regulation_radar, "_ai_relevance_filter", _ai_selective)

    res = await regulation_radar.run_radar(db_session, dry_run=False)
    assert res["new_count"] == 1
    assert res["items"][0]["name"] == "危险化学品重大危险源辨识"
    assert len(radar_env["writes"]) == 1


async def test_ai_failure_writes_nothing(db_session, radar_env, monkeypatch):
    """AI 不可用时宁可不写，也不污染表格；批次记 partial 并带错误。"""
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["crawled"] = [_item("某新法规", days_ago=3)]
    radar_env["ai_error"] = "LLM 未配置"
    async def _fail_analyze(client, item):
        return None

    monkeypatch.setattr(regulation_radar, "_analyze_regulation", _fail_analyze)

    res = await regulation_radar.run_radar(db_session, dry_run=False)
    assert res["new_count"] == 0
    assert not radar_env["writes"]
    assert any("AI" in e for e in res["errors"])


async def test_batch_limit_caps_new_regulations(db_session, radar_env, monkeypatch):
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["crawled"] = [
        _item(f"某法规第{i}号", days_ago=i + 1) for i in range(30)
    ]

    res = await regulation_radar.run_radar(db_session, dry_run=True)
    assert res["new_count"] == regulation_radar.MAX_NEW_PER_RUN


async def test_run_record_persisted_with_status(db_session, radar_env, monkeypatch):
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["crawled"] = [_item("某新法规", days_ago=3)]

    await regulation_radar.run_radar(db_session, dry_run=True)
    from sqlalchemy import func, select

    count = (
        await db_session.execute(func.count(RegulationRadarRun.id))
    ).scalar_one()
    assert count == 1
    row = (
        await db_session.execute(select(RegulationRadarRun))
    ).scalar_one()
    assert row.status == "success"
    assert row.trigger == "manual"
    assert row.dry_run is True
    items = json.loads(json.dumps(row.items))
    assert items[0]["action"] == "new"


async def test_missing_settings_blocks_radar(db_session, radar_env, monkeypatch):
    from app.core.exceptions import AppException

    async def _fake_none(db):
        raise AppException(message="未配置飞书应用凭证")

    monkeypatch.setattr(regulation_radar, "_load_settings", _fake_none)
    with pytest.raises(AppException):
        await regulation_radar.run_radar(db_session, dry_run=True)


async def test_obsolete_standard_detected(db_session, radar_env, monkeypatch):
    """标准号在国标库中标记为废止 → 记录版本变化。"""
    from datetime import UTC

    from app.modules.safety.crawler.types import CrawledRegulation
    from app.modules.safety.models import SafetyKnowledgeArticle

    row = SafetyKnowledgeArticle(
        title="某化工标准 GB 9999-2010",
        article_no="GB 9999-2010",
        feishu_record_id="rec-std",
        status="published",
    )
    db_session.add(row)
    await db_session.commit()

    async def _fake_search(core_no):
        return [
            CrawledRegulation(
                site_code="openstd_gb",
                site_name="国家标准全文公开系统",
                title=f"某化工标准 {core_no}-2010",
                url="https://openstd.samr.gov.cn/x",
                standard_no=f"{core_no}-2010",
                version_status="obsolete",
            ),
            CrawledRegulation(
                site_code="openstd_gb",
                site_name="国家标准全文公开系统",
                title=f"某化工标准 {core_no}-2025",
                url="https://openstd.samr.gov.cn/y",
                standard_no=f"{core_no}-2025",
                version_status="current",
                publish_date=datetime.now(UTC).date() - timedelta(days=30),
            ),
        ]

    monkeypatch.setattr(regulation_radar, "search_standard", _fake_search)

    changes = await regulation_radar.check_standard_versions(db_session, limit=20)
    assert any(c["action"] == "obsolete" for c in changes)
    await db_session.refresh(row)
    assert row.version_status == "obsolete"
    assert row.version_checked_at is not None
    # 新版本也应被提示
    assert any("替代版本" in (c.get("reason") or "") for c in changes)


async def test_current_standard_no_change_reported(db_session, radar_env, monkeypatch):

    from app.modules.safety.crawler.types import CrawledRegulation
    from app.modules.safety.models import SafetyKnowledgeArticle

    row = SafetyKnowledgeArticle(
        title="某检测方法标准 GB 8888-2015",
        article_no="GB 8888-2015",
        feishu_record_id="rec-cur",
        status="published",
    )
    db_session.add(row)
    await db_session.commit()

    async def _fake_search(core_no):
        # 同号仍现行 → 无变化
        return [
            CrawledRegulation(
                site_code="openstd_gb",
                site_name="国家标准全文公开系统",
                title=f"某检测方法标准 {core_no}-2015",
                url="https://openstd.samr.gov.cn/x",
                standard_no=f"{core_no}-2015",
                version_status="current",
            ),
        ]

    monkeypatch.setattr(regulation_radar, "search_standard", _fake_search)

    changes = await regulation_radar.check_standard_versions(db_session, limit=20)
    assert changes == []
    await db_session.refresh(row)
    assert row.version_status == "current"
    assert row.version_checked_at is not None


async def test_revision_updates_table_row(db_session, radar_env, monkeypatch):
    """修订法规：直接更新表格对应行的日期与链接。"""

    await _load_settings_ok(db_session, monkeypatch)
    # 表里记录日期 2025-03-14（毫秒时间戳）
    ms = int(datetime(2025, 3, 14, tzinfo=UTC).timestamp() * 1000)
    radar_env["table_rows"] = [
        {
            "record_id": "rec-law",
            "no": "001",
            "name": "《危险化学品安全法》",
            "link": "https://old.example.gov.cn/1",
            "promulgation_date": ms,
        }
    ]
    radar_env["crawled"] = [_item("中华人民共和国危险化学品安全法", days_ago=1)]

    res = await regulation_radar.run_radar(db_session, dry_run=False)
    assert res["revised_count"] == 1
    assert len(radar_env["updates"]) == 1
    upd = radar_env["updates"][0]
    assert upd["record_id"] == "rec-law"
    assert "颁布修订日期" in upd["fields"]
    assert "法规链接" in upd["fields"]
    item = next(i for i in res["items"] if i["action"] == "revised")
    assert item["table_updated"] is True


async def test_new_items_get_sequential_numbers(db_session, radar_env, monkeypatch):
    """新法规编号沿用表格顺序号递进（163 → 164、165）。"""
    await _load_settings_ok(db_session, monkeypatch)
    radar_env["table_rows"] = _table_rows(["法规甲", "法规乙"])[:1] + [
        {"record_id": "r2", "no": "163", "name": "法规丙", "link": "x"}
    ]
    radar_env["crawled"] = [
        _item("新法规一号", days_ago=2),
        _item("新法规二号", days_ago=3),
    ]

    res = await regulation_radar.run_radar(db_session, dry_run=False)
    assert res["new_count"] == 2
    nos = [w.get("法规编号") for w in radar_env["writes"]]
    assert nos == ["164", "165"]


async def test_notify_respects_config_and_targets(db_session, monkeypatch):
    """通知按开关与目标发送；未启用静默跳过不报错。"""
    sent_to: list[str] = []

    async def _fake_group(
        chat_id, title, content, elements=None, header_template="orange"
    ):
        sent_to.append(f"group:{chat_id}")
        return "msg-1"

    async def _fake_user(open_id, title, content, elements=None, id_type="open_id"):
        sent_to.append(f"user:{open_id}")
        return True

    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_group_card", _fake_group
    )
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_user_card", _fake_user
    )

    async def _fake_settings(db):
        class _S:
            radar_notify_enabled = False
            radar_notify_chat_ids: list = []
            radar_notify_user_ids: list = []
            knowledge_app_token = "tok"
            knowledge_table_id = "tbl"
            is_enabled = True

        return _S()

    monkeypatch.setattr(regulation_radar, "_load_settings", _fake_settings)

    # 未启用 → 静默跳过
    sent, errors = await regulation_radar.send_radar_notifications(
        db_session, summary_lines=["x"], new_count=1, revised_count=0
    )
    assert sent == 0 and not errors and not sent_to

    # 启用 + 配置群/个人 → 各发一条
    async def _fake_settings(db):
        class _S:
            radar_notify_enabled = True
            radar_notify_chat_ids = ["oc_group1"]
            radar_notify_user_ids = ["ou_user1"]
            knowledge_app_token = "tok"
            knowledge_table_id = "tbl"
            is_enabled = True

        return _S()

    monkeypatch.setattr(regulation_radar, "_load_settings", _fake_settings)
    sent, errors = await regulation_radar.send_radar_notifications(
        db_session, summary_lines=["新法规 X"], new_count=1, revised_count=0
    )
    assert sent == 2 and not errors
    assert "group:oc_group1" in sent_to and "user:ou_user1" in sent_to


async def test_test_notification_requires_targets(db_session, monkeypatch):
    """启用但未配置目标时，测试发送给出明确错误。"""
    from app.core.exceptions import AppException

    async def _fake_settings(db):
        class _S:
            radar_notify_enabled = True
            radar_notify_chat_ids: list = []
            radar_notify_user_ids: list = []
            knowledge_app_token = "tok"
            knowledge_table_id = "tbl"
            is_enabled = True

        return _S()

    monkeypatch.setattr(regulation_radar, "_load_settings", _fake_settings)
    with pytest.raises(AppException) as exc_info:
        await regulation_radar.send_test_notification(db_session)
    assert "未配置通知目标" in str(exc_info.value.message)
