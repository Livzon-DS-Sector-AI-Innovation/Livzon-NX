"""成品异常 AI 分类服务单元测试（mock llm_client 与飞书列表，不触库不连网）。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.modules.quality.service.finished_product_anomaly_analysis as svc
from app.core.llm import LLMConfigError, LLMRateLimitError


def _item(record_id: str, desc: str, *, product: str | None = None) -> dict:
    item = {"record_id": record_id, "不合格项目描述": desc, "数据来源": "IC"}
    if product is not None:
        item["涉及产品"] = [{"name": product}]
    return item


class _FakeResult:
    def __init__(self, values: list) -> None:
        self._values = values

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list:
        return self._values


class _FakeDB:
    def __init__(self, cached_rows: list | None = None) -> None:
        self.added: list = []
        self.commits = 0
        self._cached = cached_rows or []

    async def execute(self, stmt, *args, **kwargs) -> _FakeResult:
        return _FakeResult(self._cached)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def _cached_row(
    year: int,
    item: dict,
    *,
    product: str = "霉酚酸",
    anomaly_type: str = "杂质异常",
    status: str = "completed",
) -> SimpleNamespace:
    """从与页面列表完全相同的 item 派生缓存行，保证 content_hash 一致。"""
    snapshot = svc._record_snapshot(item, year)
    return SimpleNamespace(
        input_snapshot={
            "record_id": str(item.get("record_id")),
            "content_hash": svc._content_hash(snapshot),
        },
        output_payload={
            "product": product,
            "anomaly_type": anomaly_type,
            "reason": "测试依据",
        },
        status=status,
        created_at=datetime(2026, 9, 8, tzinfo=UTC),
    )


def _patch_pages(monkeypatch: pytest.MonkeyPatch, items: list[dict]) -> list[tuple]:
    calls: list[tuple] = []

    async def _list(db, entity_code, keyword=None, page=1, page_size=200):
        calls.append((entity_code, page, page_size))
        if page == 1:
            return {
                "items": items,
                "total": len(items),
                "page": 1,
                "page_size": page_size,
                "table_configured": True,
            }
        return {
            "items": [],
            "total": len(items),
            "page": page,
            "page_size": page_size,
            "table_configured": True,
        }

    monkeypatch.setattr(svc, "list_bitable_feishu_records", _list)
    return calls


def _patch_llm(monkeypatch: pytest.MonkeyPatch, chat_json: AsyncMock) -> AsyncMock:
    monkeypatch.setattr(
        svc,
        "get_config",
        AsyncMock(return_value=SimpleNamespace(model_name="q-test")),
    )
    monkeypatch.setattr(type(svc.llm_client), "chat_json", chat_json)
    return chat_json


@pytest.mark.asyncio
async def test_classify_year_writes_completed_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        _item("rec-1", "杂质RRT=1.98-2.01高于标准", product="MC（霉酚酸）"),
        _item("rec-2", "残渣0.53%不合格（标准≤0.5%）", product="TY（色氨酸）"),
    ]
    _patch_pages(monkeypatch, items)
    chat_mock = _patch_llm(
        monkeypatch,
        AsyncMock(
            return_value={
                "items": [
                    {
                        "id": "rec-1",
                        "product": "霉酚酸",
                        "anomaly_type": "杂质异常",
                        "reason": "成品干粉杂质超标",
                    },
                    {
                        "id": "rec-2",
                        "product": "色氨酸",
                        "anomaly_type": "检验结果超标（OOS）",
                        "reason": "残渣超出标准",
                    },
                ]
            }
        ),
    )
    db = _FakeDB()
    summary = await svc.classify_year(db, 2026)

    assert summary["analyzed"] == 2
    assert summary["skipped"] == 0
    assert summary["failed"] == 0
    assert len(db.added) == 2
    assert all(log.status == "completed" for log in db.added)
    assert db.commits == 1
    chat_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_classify_year_skips_unchanged_cached_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_item("rec-1", "杂质RRT=1.98-2.01高于标准", product="MC（霉酚酸）")]
    _patch_pages(monkeypatch, items)
    chat_mock = _patch_llm(monkeypatch, AsyncMock())
    cached = [_cached_row(2026, items[0])]
    db = _FakeDB(cached_rows=cached)

    summary = await svc.classify_year(db, 2026)

    assert summary["skipped"] == 1
    assert summary["analyzed"] == 0
    assert db.added == []
    chat_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_enum_values_fall_back_to_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_item("rec-1", "描述")]
    _patch_pages(monkeypatch, items)
    _patch_llm(
        monkeypatch,
        AsyncMock(
            return_value={
                "items": [
                    {
                        "id": "rec-1",
                        "product": "不明白色粉末",
                        "anomaly_type": "不知道",
                        "reason": "x",
                    }
                ]
            }
        ),
    )
    db = _FakeDB()
    summary = await svc.classify_year(db, 2026)
    log = db.added[0]
    assert summary["analyzed"] == 1
    assert log.output_payload["product"] == svc.PRODUCT_OTHER
    assert log.output_payload["anomaly_type"] == svc.ANOMALY_TYPE_OTHER


@pytest.mark.asyncio
async def test_rate_limit_retry_then_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_item("rec-1", "描述")]
    _patch_pages(monkeypatch, items)
    chat_mock = _patch_llm(
        monkeypatch,
        AsyncMock(
            side_effect=[
                LLMRateLimitError("429"),
                {
                    "items": [
                        {
                            "id": "rec-1",
                            "product": "霉酚酸",
                            "anomaly_type": "杂质异常",
                        }
                    ]
                },
            ]
        ),
    )
    monkeypatch.setattr(svc.asyncio, "sleep", AsyncMock())
    db = _FakeDB()

    summary = await svc.classify_year(db, 2026)

    assert summary["analyzed"] == 1
    assert summary["failed"] == 0
    assert chat_mock.await_count == 2


@pytest.mark.asyncio
async def test_no_config_marks_batch_failed_without_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_item("rec-1", "描述"), _item("rec-2", "描述2")]
    _patch_pages(monkeypatch, items)
    monkeypatch.setattr(
        svc, "get_config", AsyncMock(side_effect=LLMConfigError("no config"))
    )
    chat_mock = AsyncMock()
    monkeypatch.setattr(type(svc.llm_client), "chat_json", chat_mock)
    db = _FakeDB()

    summary = await svc.classify_year(db, 2026)

    assert summary["failed"] == 2
    assert summary["last_error"] == "no_config"
    assert db.added == []
    chat_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_dashboard_aggregation_counts_product_and_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items_2026 = [_item("rec-1", "杂质高于标准", product="MC（霉酚酸）")]
    items_2025 = [_item("rec-25", "甲醇溶解性中有不溶白色颗粒")]

    async def _items(db, year):
        if year == 2026:
            return items_2026
        if year == 2025:
            return items_2025
        return []

    monkeypatch.setattr(svc, "_list_year_items", _items)
    async def _load(db, year, ids):
        if year != 2026:
            return {
                i["record_id"]: {
                    "content_hash": "",
                    "payload": {},
                    "status": "x",
                    "created_at": None,
                }
                for i in []
            }
        return {
            "rec-1": {
                "content_hash": svc._content_hash(
                    svc._record_snapshot(items_2026[0], 2026)
                ),
                "payload": {"product": "霉酚酸", "anomaly_type": "杂质异常"},
                "status": "completed",
                "created_at": datetime(2026, 9, 8, tzinfo=UTC),
            }
        }

    monkeypatch.setattr(svc, "_load_cached_classifications", _load)
    db = _FakeDB()

    data = await svc.get_dashboard_aggregation(db, None)

    assert data["total"] == 2
    assert data["analyzed"] == 1
    assert data["unclassified"] == 1
    products = {item["product"]: item for item in data["products"]}
    assert products["霉酚酸"]["count"] == 1
    assert products["霉酚酸"]["types"][0]["type"] == "杂质异常"
    # 2025 记录未分析：无涉及产品字段、无产品附件列 → 待分析
    assert products.get("待分析", {}).get("count") == 1
    type_totals = {item["type"]: item["count"] for item in data["type_totals"]}
    assert type_totals["杂质异常"] == 1
    assert type_totals["待分析"] == 1


@pytest.mark.asyncio
async def test_product_hint_from_2025_attachment_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = {
        "record_id": "rec-25",
        "不合格项目": "甲醇溶解性中有不溶白色颗粒",
        "洛伐他汀": [{"name": "lft.jpeg", "file_token": "ft"}],
    }
    assert svc._product_hint(item, 2025) == "洛伐他汀"
    item2 = {
        "record_id": "rec-26",
        "不合格项目描述": "残渣超标",
        "涉及产品": [{"name": "TY（色氨酸）"}],
    }
    # 带代码前缀的原文归一到标准产品名
    assert svc._product_hint(item2, 2026) == "色氨酸"


def test_canonicalize_product_variants() -> None:
    assert svc._canonicalize_product("MC（霉酚酸）") == "霉酚酸"
    assert svc._canonicalize_product("FA（L-苯丙氨酸）") == "L-苯丙氨酸"
    assert svc._canonicalize_product("LN（美伐他汀）") == "美伐他汀"
    assert svc._canonicalize_product("FE（芬苯达唑粉）") == "芬苯达唑粉"
    assert svc._canonicalize_product("USMC-M-2502004") == "霉酚酸"
    assert svc._canonicalize_product("霉酚酸") == "霉酚酸"
    assert svc._canonicalize_product("不明粉末") == ""


@pytest.mark.asyncio
async def test_unconfigured_year_table_raises_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.exceptions import AppException

    async def _list(db, entity_code, keyword=None, page=1, page_size=200):
        return {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": page_size,
            "table_configured": False,
        }

    monkeypatch.setattr(svc, "list_bitable_feishu_records", _list)
    db = _FakeDB()
    with pytest.raises(AppException) as exc_info:
        await svc.classify_year(db, 2027)
    assert exc_info.value.status_code == 400


# ── 未关闭看板 ─────────────────────────────────────────────


def _open_item(
    record_id: str, closed: str | None, investigation, desc: str = "残渣超标"
) -> dict:
    item = _item(record_id, desc)
    if closed is not None:
        item["是否结案"] = closed
    if investigation is not None:
        item["调查结果说明"] = investigation
    return item


@pytest.mark.asyncio
async def test_dashboard_open_stats_uses_and_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        # 未结案但有调查报告 → 不计
        _open_item("rec-a", "否", [{"file_token": "t"}]),
        # 已结案但缺调查报告 → 不计
        _open_item("rec-b", "是", []),
        # 两者均缺 → 计入
        _open_item("rec-c", None, None),
        # 已结案且有报告 → 不计
        _open_item("rec-d", "是", [{"file_token": "t2"}]),
    ]

    async def _items(db, year):
        return items

    monkeypatch.setattr(svc, "_list_year_items", _items)
    monkeypatch.setattr(svc, "_load_cached_classifications", AsyncMock(return_value={}))
    monkeypatch.setattr(
        svc, "get_config", AsyncMock(return_value=SimpleNamespace(model_name="q"))
    )
    data = await svc.get_dashboard_aggregation(_FakeDB(), 2026)
    assert data["open_count"] == 1
    assert data["by_year_open"] == [{"year": 2026, "open_count": 1, "total": 4}]
    ids = {row["id"] for row in data["open_recent"]}
    assert ids == {"rec-c"}
    rec_c = data["open_recent"][0]
    assert rec_c["desc"] == "残渣超标"
    # 三桶构成字段已随 AND 口径删除
    assert "open_missing_close" not in data


def test_is_open_record_semantics() -> None:
    # AND 口径（2026-09-09 用户修订）：有报告或已结案任占其一即不算未关闭
    has_report = [{"file_token": "t"}]
    assert svc._is_open_record({"是否结案": "是", "调查结果说明": has_report}) is False
    assert svc._is_open_record({"是否结案": "否", "调查结果说明": has_report}) is False
    assert svc._is_open_record({"是否结案": "是", "调查结果说明": []}) is False
    assert svc._is_open_record({"是否结案": "否", "调查结果说明": []}) is True
    assert svc._is_open_record({}) is True


# ── 导出 / 导入 ─────────────────────────────────────────────


def _log(entity_id, snapshot, payload, model="q-test", status="completed"):
    return SimpleNamespace(
        entity_id=entity_id,
        input_snapshot=snapshot,
        output_payload=payload,
        model_name=model,
        status=status,
    )


@pytest.mark.asyncio
async def test_export_classifications_dedups_latest_rows() -> None:
    import uuid as uuid_lib

    eid = uuid_lib.uuid4()
    newer = _log(
        eid,
        {"year": 2026, "record_id": "rec-1", "content_hash": "h2"},
        {"product": "霉酚酸", "anomaly_type": "杂质异常", "reason": "RRT 超标"},
    )
    older = _log(
        eid,
        {"year": 2026, "record_id": "rec-1", "content_hash": "h1"},
        {"product": "霉酚酸", "anomaly_type": "旧口径"},
    )
    db = _FakeDB(cached_rows=[newer, older])
    payload = await svc.export_classifications(db)
    assert payload["count"] == 1
    row = payload["rows"][0]
    assert row["record_id"] == "rec-1"
    assert row["content_hash"] == "h2"
    assert row["anomaly_type"] == "杂质异常"


@pytest.mark.asyncio
async def test_import_recomputes_hash_and_skips_existing() -> None:
    import uuid as uuid_lib

    target_uuid = uuid_lib.uuid5(svc._UUID_NAMESPACE, "2026:rec-1")
    snapshot = {
        "year": 2026,
        "record_id": "rec-9",
        "desc": "残渣0.53%不合格",
        "product_hint": "",
        "source": "QC",
    }
    expected_hash = svc._content_hash(snapshot)
    rows = [
        {**snapshot, "content_hash": "SNAPSHOT-HASH-FROM-SOURCE-ENV",
         "product": "色氨酸",
         "anomaly_type": "检验结果超标（OOS）",
         "reason": "超标准"},
        {"year": 2026, "record_id": "rec-1", "content_hash": "whatever",
         "product": "霉酚酸", "anomaly_type": "杂质异常"},  # 已存在 → skip
    ]
    db = _FakeDB(cached_rows=[target_uuid])
    result = await svc.import_classifications_from_rows(db, rows)
    assert result == {"imported": 1, "skipped": 1}
    log = db.added[0]
    # 导出行自带 hash（导出时由源环境快照算得）→ 原样携带，保证导入环境去重匹配不重跑
    assert log.input_snapshot["content_hash"] == "SNAPSHOT-HASH-FROM-SOURCE-ENV"
    # 手工行无 hash 时以行内快照重算兜底
    row_no_hash = {
        **snapshot,
        "product": "色氨酸",
        "anomaly_type": "检验结果超标（OOS）",
    }
    db2 = _FakeDB()
    await svc.import_classifications_from_rows(db2, [row_no_hash])
    assert db2.added[0].input_snapshot["content_hash"] == expected_hash


@pytest.mark.asyncio
async def test_import_rejects_bad_rows() -> None:
    from app.core.exceptions import AppException

    with pytest.raises(AppException):
        await svc.import_classifications_from_rows(
            _FakeDB(), [{"year": 1999, "record_id": "x", "anomaly_type": "杂质异常"}]
        )
    with pytest.raises(AppException):
        await svc.import_classifications_from_rows(_FakeDB(), [{"rows": "bad"}] * 1200)
