"""Reviewed exceptions must survive recalculation and never enter valid totals."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.energy.ledger_models import EnergyUsageFact
from app.modules.energy.ledger_reviews import (
    ReviewPeriod,
    UsageReview,
    apply_usage_review,
    load_usage_reviews,
    pending_metrics,
    save_usage_reviews,
)
from app.modules.energy.ledger_schemas import RuleDefinition, RuleTerm, UsageRow
from app.modules.energy.ledger_service import EnergyLedgerService


def review() -> UsageReview:
    return UsageReview(
        dataset="冰水量",
        column=14,
        periods=[
            ReviewPeriod(
                start_date=date(2026, 7, 26),
                end_date=date(2026, 7, 26),
                reason="底码跳变与手填用量冲突，待确认",
                source="飞书在线原表 N31",
                reported_values={"2026-07-26": Decimal("28674")},
            )
        ],
    )


def rule(code: str, sheet: str, column: int, dependency: str) -> RuleDefinition:
    return RuleDefinition(
        code=code,
        name=code,
        category="chilled_water",
        department="能源",
        unit="m³",
        active_from=date(2026, 1, 1),
        enabled=True,
        source_sheet=sheet,
        source_column=column,
        terms=[RuleTerm(metric_key=dependency, coefficient=1)],
    )


def test_review_is_date_bounded_and_propagates_to_every_dependent() -> None:
    definitions = {
        "rule:ice": rule("ice", "冰水量", 14, "point:counter"),
        "rule:workshop": rule("workshop", "101车间", 7, "rule:ice"),
        "rule:total": rule("total", "日总量", 9, "rule:workshop"),
        "rule:unrelated": rule("unrelated", "冰水量", 12, "point:other"),
    }
    pending = pending_metrics(date(2026, 7, 26), definitions, [review()])
    assert set(pending) == {"rule:ice", "rule:workshop", "rule:total"}
    assert pending_metrics(date(2026, 7, 25), definitions, [review()]) == {}
    assert pending_metrics(date(2026, 7, 27), definitions, [review()]) == {}


def test_review_retains_calculation_original_value_and_reason_without_mutation() -> (
    None
):
    row = UsageRow(
        id=uuid4(),
        metric_key="rule:ice",
        usage_date=date(2026, 7, 26),
        name="冰水",
        category="chilled_water",
        department="能源",
        unit="m³",
        workshop="",
        report_scope="plant",
        quantity_kind="volume",
        temperature="7℃",
        calculated_value=Decimal("2049315"),
        effective_value=Decimal("2049315"),
        status="complete",
        provenance={"reading_values": ["316278", "2365593"]},
    )
    marked = apply_usage_review(row, review().evidence_on(row.usage_date))
    assert marked.status == "pending_review" and marked.effective_value is None
    assert marked.calculated_value == Decimal("2049315")
    assert marked.provenance["reading_values"] == ["316278", "2365593"]
    assert marked.provenance["review"][0]["reported_value"] == "28674"
    assert "手填" in marked.provenance["review"][0]["reason"]
    assert row.status == "complete" and row.effective_value == Decimal("2049315")
    assert "review" not in row.provenance


def test_temperature_review_preserves_confirmed_early_interval() -> None:
    item = UsageReview(
        dataset="201-2车间",
        column=6,
        periods=[
            ReviewPeriod(
                start_date=date(2026, 7, 12),
                end_date=date(2026, 7, 31),
                reason="7℃字段引用-5℃来源",
                source="F17=冰水量!E17",
            )
        ],
    )
    definitions = {"rule:cold": rule("cold", "201-2车间", 6, "point:water")}
    assert pending_metrics(date(2026, 7, 11), definitions, [item]) == {}
    assert "rule:cold" in pending_metrics(date(2026, 7, 12), definitions, [item])
    assert pending_metrics(date(2026, 8, 1), definitions, [item]) == {}


def test_review_rejects_inverted_range_and_values_outside_range() -> None:
    with pytest.raises(ValidationError):
        ReviewPeriod(
            start_date=date(2026, 7, 26),
            end_date=date(2026, 7, 25),
            reason="冲突",
            source="原表",
        )
    with pytest.raises(ValidationError):
        ReviewPeriod(
            start_date=date(2026, 7, 26),
            end_date=date(2026, 7, 26),
            reason="冲突",
            source="原表",
            reported_values={"2026-07-27": 1},
        )


@pytest.mark.asyncio
async def test_reporting_route_excludes_pending_and_preserves_zero() -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.modules.energy.ledger_api import ledger_service, router

    definition = rule("ice", "冰水量", 14, "point:counter")
    definition.report_scope = "plant"
    facts = [
        EnergyUsageFact(
            id=uuid4(),
            metric_key="rule:ice",
            usage_date=date(2026, 7, day),
            definition=definition.model_dump(mode="json"),
            calculated_value=Decimal(value),
            effective_value=Decimal(value),
            status="complete",
            provenance={},
        )
        for day, value in [(25, "0"), (26, "2049315"), (27, "29915")]
    ]
    db = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: facts),
                SimpleNamespace(all=lambda: []),
            ]
        )
    )
    service = EnergyLedgerService(db)
    service._usage_reviews = [review()]
    service.definitions_on = AsyncMock(return_value=({}, {"rule:ice": (1, definition)}))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/energy")
    app.dependency_overrides[ledger_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/energy/reporting",
            params={
                "start_date": "2026-07-25",
                "end_date": "2026-07-27",
                "report_scope": "plant",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert Decimal(data["totals"][0]["value"]) == Decimal("29915")
        assert data["totals"][0]["available_count"] == 2
        assert data["totals"][0]["expected_count"] == 3
        assert Decimal(data["distribution"][0]["value"]) == Decimal("29915")
        assert Decimal(data["period_metrics"][0]["value"]) == Decimal("29915")
        assert data["period_metrics"][0]["status"] == "partial"
        assert data["quality_counts"]["pending_review"] == 1
        pending = next(row for row in data["rows"] if row["usage_date"] == "2026-07-26")
        assert (
            pending["status"] == "pending_review" and pending["effective_value"] is None
        )
        assert Decimal(pending["calculated_value"]) == Decimal("2049315")
        assert pending["provenance"]["review"][0]["reported_value"] == "28674"
        assert (
            next(row for row in data["trend"] if row["usage_date"] == "2026-07-26")[
                "value"
            ]
            is None
        )
        assert (
            Decimal(
                next(row for row in data["rows"] if row["usage_date"] == "2026-07-25")[
                    "effective_value"
                ]
            )
            == 0
        )
        invalid = await client.get(
            "/api/v1/energy/reporting",
            params={"start_date": "invalid", "end_date": "2026-07-27"},
        )
        assert invalid.status_code == 422
    assert facts[1].effective_value == Decimal("2049315")


@pytest.mark.asyncio
async def test_unconfigured_cell_preserves_review_reason() -> None:
    from app.modules.energy.ledger_workbook import EnergyWorkbookService

    workbook = EnergyWorkbookService(EnergyLedgerService(SimpleNamespace()))
    workbook.loaded = (2026, 7)
    workbook.headers["203-2车间"] = ["日期", "饮用水", "电"]
    workbook.reviews = [
        UsageReview(
            dataset="203-2车间",
            column=3,
            periods=[
                ReviewPeriod(
                    start_date=date(2026, 7, 1),
                    end_date=date(2026, 7, 31),
                    reason="无分配依据",
                    source="飞书原表电量列为空",
                )
            ],
        )
    ]
    report = await workbook.report(2026, 7, "203-2车间")
    cell = report.rows[0].cells["3"]
    assert cell.status == "pending_review" and cell.value is None
    assert cell.provenance["review"][0]["reason"] == "无分配依据"
    assert report.available_count == 0


@pytest.mark.asyncio
async def test_latest_review_can_clear_an_old_period_without_deleting_history() -> None:
    cleared = review().model_copy(update={"periods": []})
    records = [
        SimpleNamespace(entity_id="same", payload=item.model_dump(mode="json"))
        for item in [cleared, review()]
    ]
    service = EnergyLedgerService(
        SimpleNamespace(
            scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: records))
        )
    )
    assert await load_usage_reviews(service) == [cleared]
    assert len(records) == 2


@pytest.mark.asyncio
async def test_rebuild_retains_calculation_but_excludes_pending_value() -> None:
    from app.modules.energy.ledger_calculations import Calculation

    db = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
        add=Mock(),
        flush=AsyncMock(),
    )
    service = EnergyLedgerService(db)
    service.evaluate = AsyncMock(
        return_value=[
            (
                "rule:ice",
                rule("ice", "冰水量", 14, "point:counter"),
                Calculation(Decimal("2049315"), "pending_review", {"review": []}),
            )
        ]
    )
    await service.rebuild({date(2026, 7, 26)})
    fact = db.add.call_args.args[0]
    assert fact.calculated_value == Decimal("2049315")
    assert fact.effective_value is None and fact.status == "pending_review"


@pytest.mark.asyncio
async def test_review_write_requires_manager_and_cannot_target_raw_counters() -> None:
    from app.core.exceptions import AppException

    db = SimpleNamespace(add=Mock(), flush=AsyncMock())
    service = EnergyLedgerService(db)
    service.require_manager = AsyncMock(side_effect=AppException(403, "需要权限"))
    with pytest.raises(AppException):
        await save_usage_reviews(service, [review()], "核对")
    db.add.assert_not_called()
    service.require_manager = AsyncMock()
    service.repo.serialize_write = AsyncMock()
    raw = review().model_copy(update={"dataset": "冰水码"})
    with pytest.raises(AppException):
        await save_usage_reviews(service, [raw], "核对")
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_ratio_filter_cannot_bypass_a_review_on_its_hidden_source() -> None:
    numerator = rule("num", "冰水量", 14, "point:counter")
    denominator = rule("den", "冰水量", 12, "point:other")
    ratio = rule("ratio", "日总量", 5, "rule:num")
    ratio.operation = "ratio"
    ratio.quantity_kind = "ratio"
    ratio.terms = [
        RuleTerm(metric_key=key, coefficient=1) for key in ["rule:num", "rule:den"]
    ]
    fact = EnergyUsageFact(
        id=uuid4(),
        metric_key="rule:ratio",
        usage_date=date(2026, 7, 26),
        definition=ratio.model_dump(mode="json"),
        calculated_value=Decimal("0.5"),
        effective_value=Decimal("0.5"),
        status="complete",
        provenance={"terms": [term.model_dump(mode="json") for term in ratio.terms]},
    )
    db = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [fact]),
                SimpleNamespace(all=lambda: []),
            ]
        ),
        scalar=AsyncMock(),
    )
    service = EnergyLedgerService(db)
    service._usage_reviews = [review()]
    service.definitions_on = AsyncMock(
        return_value=(
            {},
            {
                "rule:num": (1, numerator),
                "rule:den": (1, denominator),
                "rule:ratio": (1, ratio),
            },
        )
    )
    result = await service.report(
        date(2026, 7, 26), date(2026, 7, 26), metric_key="rule:ratio"
    )
    assert result.rows[0].status == "pending_review"
    assert result.period_metrics[0].value is None
    db.scalar.assert_not_called()


@pytest.mark.asyncio
async def test_usage_review_routes_save_and_clear(db_session) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.modules.energy.ledger_api import ledger_service, router
    from app.platform.identity.models import User

    actor = User(
        id=uuid4(),
        username="review-" + uuid4().hex,
        name="能源复核员",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(actor)
    await db_session.flush()
    service = EnergyLedgerService(db_session, actor)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/energy")
    app.dependency_overrides[ledger_service] = lambda: service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.put(
                "/api/v1/energy/usage-reviews",
                json={"reviews": [review().model_dump(mode="json")], "reason": "复核"},
            )
            assert created.status_code == 200, created.text
            assert created.json()["data"][0]["periods"][0]["reason"] == (
                "底码跳变与手填用量冲突，待确认"
            )
            listed = await client.get("/api/v1/energy/usage-reviews")
            assert listed.status_code == 200
            assert len(listed.json()["data"]) == 1
            cleared = await client.put(
                "/api/v1/energy/usage-reviews",
                json={
                    "reviews": [
                        review()
                        .model_copy(update={"periods": []})
                        .model_dump(mode="json")
                    ],
                    "reason": "确认完成",
                },
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["data"] == []
    finally:
        app.dependency_overrides.clear()
