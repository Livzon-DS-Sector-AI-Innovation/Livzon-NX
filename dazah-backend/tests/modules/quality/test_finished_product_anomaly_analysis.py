"""成品异常 AI 分类服务单元测试（mock llm_client 与飞书列表，不触库不连网）。"""

from __future__ import annotations

from datetime import datetime, timezone
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

    def scalars(self) -> "_FakeResult":
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
        created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
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
                {"items": [{"id": "rec-1", "product": "霉酚酸", "anomaly_type": "杂质异常"}]},
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
    cached_2026 = [
        _cached_row(2026, items_2026[0], product="霉酚酸", anomaly_type="杂质异常")
    ]

    async def _load(db, year, ids):
        return {i["record_id"]: {"content_hash": "", "payload": {}, "status": "x", "created_at": None} for i in []} if year != 2026 else {
            "rec-1": {
                "content_hash": svc._content_hash(
                    svc._record_snapshot(items_2026[0], 2026)
                ),
                "payload": {"product": "霉酚酸", "anomaly_type": "杂质异常"},
                "status": "completed",
                "created_at": datetime(2026, 9, 8, tzinfo=timezone.utc),
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
