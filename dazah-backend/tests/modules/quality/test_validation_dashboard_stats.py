"""验证仪表盘统计与"近期待再验证"测试。

覆盖：
- 文本到期日期解析器 _parse_validation_due_date 的各格式与无效输入
- 完成状态判断 _is_validation_completed
- 统计函数 get_validation_statistics_from_feishu（年度聚合/year_from/阈值/
  排除已完成/未绑定年度/真异常）
- 明细函数 list_validation_revalidation_upcoming_from_feishu（年度聚合/分页）
- 飞书统计与明细端点的 AsyncClient 集成测试
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.modules.quality.service import quality_feishu_pages as pages


def _item(
    record_id: str,
    *,
    validation_type: str = "process_validation",
    status: str = "进行中",
    planned_end_date: object | None = None,
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "validation_type": validation_type,
        "status": status,
        "planned_end_date": planned_end_date,
        "title": "确认名称",
    }


def _mock_year_list(
    monkeypatch: pytest.MonkeyPatch,
    by_year: dict[int, list[dict[str, object]]],
    *,
    raise_year: int | None = None,
) -> None:
    """按年度 mock list_validation_records_from_feishu；raise_year 模拟未绑定年度。"""

    async def fake(db: object, **kwargs: object) -> dict[str, object]:
        year = kwargs.get("year")
        if raise_year is not None and year == raise_year:
            raise pages.AppException(message="未绑定")
        items = by_year.get(year, [])
        return {
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": kwargs.get("page_size", 10000),
        }

    monkeypatch.setattr(pages, "list_validation_records_from_feishu", fake)


# ── _parse_validation_due_date ──


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026.02", date(2026, 2, 1)),
        ("2026.02.15", date(2026, 2, 15)),
        ("2026/02/15", date(2026, 2, 15)),
        ("2026-02", date(2026, 2, 1)),
        ("2026-02-15", date(2026, 2, 15)),
        ("2026年2月", date(2026, 2, 1)),
        ("2026年2月15日", date(2026, 2, 15)),
        ("20260215", date(2026, 2, 15)),
        ("2026", date(2026, 1, 1)),
        (date(2026, 3, 4), date(2026, 3, 4)),
        (datetime(2026, 3, 4, 12, 0, tzinfo=UTC), date(2026, 3, 4)),
    ],
)
def test_parse_validation_due_date_supported_shapes(
    raw: object, expected: date
) -> None:
    assert pages._parse_validation_due_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "  ", "abc", "2026.99", "99.01", "not-a-date", "2026-13-40"],
)
def test_parse_validation_due_date_invalid_returns_none(raw: object) -> None:
    assert pages._parse_validation_due_date(raw) is None


# ── _is_validation_completed ──


@pytest.mark.parametrize(
    "status",
    ["完成", "已完成", "completed", "Completed", "finished", "done", " 完成 "],
)
def test_is_validation_completed_recognizes_done_statuses(status: object) -> None:
    assert pages._is_validation_completed(status) is True


@pytest.mark.parametrize(
    "status",
    [None, "", "进行中", "未完成", "待完成", "pending", "in progress"],
)
def test_is_validation_completed_marks_others_incomplete(status: object) -> None:
    assert pages._is_validation_completed(status) is False


# ── 统计函数（年度聚合） ──


@pytest.mark.anyio
async def test_statistics_aggregates_years_and_counts_upcoming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = date.today()
    near = (today + timedelta(days=10)).isoformat()
    far = (today + timedelta(days=60)).isoformat()
    done_near = (today + timedelta(days=5)).isoformat()
    _mock_year_list(
        monkeypatch,
        {
            2024: [
                _item("r1", planned_end_date=near),  # 未完成，30 天内
                _item("r2", status="完成", planned_end_date=done_near),  # 已完成不计
            ],
            2025: [
                _item("r3", planned_end_date=far),  # 未完成，60 天外
                _item("r4", planned_end_date="2026.02"),  # 未完成，已过期文本日期
                _item("r5", planned_end_date=None),  # 无到期时间
                _item("r6", planned_end_date="abc"),  # 无法解析
            ],
        },
    )

    stats = await pages.get_validation_statistics_from_feishu(
        SimpleNamespace(), days=30
    )
    # 2024 的 r1 + 2025 的 r4（过期未完成）= 2
    assert stats["total"] == 6
    assert stats["revalidationUpcoming"] == 2

    stats_90 = await pages.get_validation_statistics_from_feishu(
        SimpleNamespace(), days=90
    )
    # r1 + r3 + r4 = 3
    assert stats_90["revalidationUpcoming"] == 3

    by_year = {s["year"]: s for s in stats["year_summaries"]}
    assert by_year[2024]["total"] == 2
    assert by_year[2024]["completed"] == 1
    assert by_year[2025]["total"] == 4
    assert by_year[2026]["total"] == 0
    assert by_year[2026]["completed"] == 0


@pytest.mark.anyio
async def test_statistics_respects_year_from_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_year_list(
        monkeypatch,
        {
            2024: [_item("r1")],
            2025: [_item("r2")],
            2026: [_item("r3")],
        },
    )
    stats = await pages.get_validation_statistics_from_feishu(
        SimpleNamespace(), year_from=2025
    )
    assert stats["total"] == 2
    years = [s["year"] for s in stats["year_summaries"]]
    assert years == [2025, 2026, 2027, 2028]


@pytest.mark.anyio
async def test_statistics_distributions_breakdown_by_type_and_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_year_list(
        monkeypatch,
        {
            2024: [
                _item("r1", validation_type="process_validation", status="进行中"),
                _item("r2", validation_type="equipment_qualification", status="完成"),
            ],
            2025: [
                _item("r3", validation_type="process_validation", status="进行中"),
            ],
        },
    )
    stats = await pages.get_validation_statistics_from_feishu(SimpleNamespace())
    assert stats["total"] == 3
    by_type = {
        item["validation_type"]: item["count"]
        for item in stats["typeDistribution"]
    }
    assert by_type["process_validation"] == 2
    assert by_type["equipment_qualification"] == 1
    by_status = {item["status"]: item["count"] for item in stats["statusDistribution"]}
    assert by_status["进行中"] == 2
    assert by_status["完成"] == 1


@pytest.mark.anyio
async def test_statistics_treats_unbound_year_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_year_list(
        monkeypatch,
        {2024: [_item("r1")]},
        raise_year=2025,
    )
    stats = await pages.get_validation_statistics_from_feishu(SimpleNamespace())
    assert stats["total"] == 1
    by_year = {s["year"]: s for s in stats["year_summaries"]}
    assert by_year[2025]["total"] == 0


@pytest.mark.anyio
async def test_statistics_does_not_swallow_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(db: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("provider down")

    monkeypatch.setattr(pages, "list_validation_records_from_feishu", boom)
    with pytest.raises(RuntimeError, match="provider down"):
        await pages.get_validation_statistics_from_feishu(SimpleNamespace())


# ── 明细函数（年度聚合） ──


@pytest.mark.anyio
async def test_upcoming_detail_aggregates_years_and_paginates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upcoming_deadline = (date.today() + timedelta(days=30)).isoformat()
    captured: list[dict[str, object]] = []

    async def fake_list(db: object, **kwargs: object) -> dict[str, object]:
        captured.append(kwargs)
        year = kwargs.get("year")
        if year == 2024:
            items = [
                _item("r1", planned_end_date="2026.05"),
                # 已完成 r2 模拟列表 service 在 exclude_completed 下的过滤
                _item("r2", status="完成", planned_end_date="2026.02"),
            ]
        elif year == 2025:
            items = [
                _item("r3", planned_end_date="2026.03"),
            ]
        else:
            items = []
        # 模拟列表 service 的 exclude_completed 行为
        from app.modules.quality.service.quality_feishu_pages import (
            _is_validation_completed,
        )

        items = [
            item for item in items if not _is_validation_completed(item.get("status"))
        ]
        return {
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": kwargs.get("page_size", 10000),
        }

    monkeypatch.setattr(pages, "list_validation_records_from_feishu", fake_list)
    result = await pages.list_validation_revalidation_upcoming_from_feishu(
        SimpleNamespace(), days=30, page=1, page_size=10
    )
    # 已完成 r2 由 fake 直接过滤（真实实现用 exclude_completed 传给列表），
    # 聚合后仅 r1、r3
    assert result["total"] == 2
    assert {item["record_id"] for item in result["items"]} == {"r1", "r3"}
    # 每次调用都带上 planned_end_date_to 与 exclude_completed
    for call in captured:
        assert call["planned_end_date_to"] == upcoming_deadline
        assert call["exclude_completed"] is True


@pytest.mark.anyio
async def test_upcoming_detail_respects_year_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_years: list[int] = []

    async def fake_list(db: object, **kwargs: object) -> dict[str, object]:
        seen_years.append(kwargs.get("year"))
        return {"items": [], "total": 0, "page": 1, "page_size": 20}

    monkeypatch.setattr(pages, "list_validation_records_from_feishu", fake_list)
    await pages.list_validation_revalidation_upcoming_from_feishu(
        SimpleNamespace(), days=30, year_from=2026, page=1, page_size=10
    )
    assert seen_years == [2026, 2027, 2028]


# ── API 集成测试 ──


@pytest.mark.anyio
async def test_feishu_statistics_endpoint_forwards_days_and_year_from(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.quality.api import validation as validation_api

    captured: dict[str, object] = {}

    async def _fake_stats(db: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "total": 0,
            "typeDistribution": [],
            "statusDistribution": [],
            "executionDistribution": [],
            "revalidationUpcoming": 0,
            "year_summaries": [],
        }

    monkeypatch.setattr(
        validation_api, "get_validation_statistics_from_feishu", _fake_stats
    )
    resp = await client.get(
        "/api/v1/quality/feishu/statistics/validations",
        params={"days": 60, "year_from": 2025},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["revalidationUpcoming"] == 0
    assert captured["days"] == 60
    assert captured["year_from"] == 2025


@pytest.mark.anyio
async def test_feishu_statistics_endpoint_validates_params(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.quality.api import validation as validation_api

    called = False

    async def _fake_stats(db: object, **kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(
        validation_api, "get_validation_statistics_from_feishu", _fake_stats
    )
    resp = await client.get(
        "/api/v1/quality/feishu/statistics/validations", params={"days": 0}
    )
    assert resp.status_code == 422
    assert called is False


@pytest.mark.anyio
async def test_revalidation_upcoming_endpoint_returns_paginated_rows(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.quality.api import validation as validation_api

    captured: dict[str, object] = {}

    async def _fake_upcoming(db: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "items": [{"record_id": "r1", "title": "纯化水系统再验证"}],
            "total": 1,
            "page": 1,
            "page_size": 10,
        }

    monkeypatch.setattr(
        validation_api,
        "list_validation_revalidation_upcoming_from_feishu",
        _fake_upcoming,
    )
    resp = await client.get(
        "/api/v1/quality/feishu/validations/revalidation-upcoming",
        params={"days": 30, "year_from": 2025, "page": 1, "page_size": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["record_id"] == "r1"
    assert captured["days"] == 30
    assert captured["year_from"] == 2025
    assert captured["page"] == 1
    assert captured["page_size"] == 10
