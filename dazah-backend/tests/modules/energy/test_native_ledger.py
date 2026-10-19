from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.main import app
from app.modules.energy.ledger_calculations import (
    Calculation,
    Observation,
    calculate_point,
    calculate_rule,
    validate_graph,
)
from app.modules.energy.ledger_imports import inspect_xlsx, parse_source_date
from app.modules.energy.ledger_models import EnergyLedgerRevision, EnergyPeriodLock
from app.modules.energy.ledger_schemas import (
    AdjustmentWrite,
    EntryPlanDefinition,
    EntrySubmission,
    EntryValue,
    MeterDefinition,
    MeterWrite,
    PlanWrite,
    RuleDefinition,
    RuleTerm,
    RuleWrite,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.modules.energy.ledger_template import extract_template
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

DAY = date(2026, 7, 1)


def test_historical_rule_can_preserve_a_not_yet_effective_dependency() -> None:
    rule = RuleDefinition(
        code="historical_total",
        name="历史汇总",
        category="drinking_water",
        department="101车间",
        unit="m3",
        active_from=DAY,
        terms=[RuleTerm(metric_key="rule:future_source")],
        enabled=False,
    )
    with pytest.raises(ValueError, match="来源不存在"):
        validate_graph({}, {"rule:historical_total": rule})
    assert validate_graph({}, {"rule:historical_total": rule}, allow_missing=True) == [
        "rule:historical_total"
    ]
    result = calculate_rule(rule, {})
    assert result.value is None
    assert result.status == "missing_dependency"


def point(**updates: object) -> MeterDefinition:
    return MeterDefinition.model_validate(
        {
            "code": "water",
            "name": "101车间水表",
            "category": "drinking_water",
            "area": "101",
            "department": "101车间",
            "unit": "m3",
            "active_from": DAY,
            "enabled": True,
            "report_scope": "source",
            **updates,
        }
    )


def test_counter_uses_next_day_and_preserves_zero() -> None:
    with pytest.raises(ValueError, match="直接用量按日填写"):
        point(reading_type="direct", frequency="monthly")
    meter = point(multiplier="10")
    result = calculate_point(
        meter,
        DAY,
        {
            DAY: Observation(Decimal(100), 1),
            DAY + timedelta(days=1): Observation(Decimal(100), 2),
        },
    )
    assert result is not None and result.value == 0 and result.status == "complete"
    result = calculate_point(
        meter,
        DAY,
        {
            DAY: Observation(Decimal(100), 1),
            DAY + timedelta(days=1): Observation(Decimal("101.2"), 2),
        },
    )
    assert result is not None and result.value == Decimal(12)
    assert result.provenance["reading_dates"] == ["2026-07-01", "2026-07-02"]


def test_missing_gap_is_not_allocated_to_a_day() -> None:
    result = calculate_point(
        point(),
        DAY,
        {
            DAY: Observation(Decimal(100), 1),
            DAY + timedelta(days=2): Observation(Decimal(120), 1),
        },
    )
    assert (
        result is not None
        and result.value is None
        and result.status == "missing_reading"
    )


def test_monthly_counter_only_emits_actual_month_interval() -> None:
    meter = point(frequency="monthly")
    readings = {
        DAY: Observation(Decimal(100), 1),
        date(2026, 8, 1): Observation(Decimal(160), 1),
    }
    assert calculate_point(meter, DAY, readings) is None
    result = calculate_point(meter, date(2026, 7, 31), readings)
    assert result is not None and result.value == 60
    assert result.provenance["interval_end"] == "2026-08-01"


def test_rollback_requires_meter_event_and_does_not_take_absolute_value() -> None:
    readings = {
        DAY: Observation(Decimal(100), 1),
        DAY + timedelta(days=1): Observation(Decimal(10), 1),
    }
    result = calculate_point(point(), DAY, readings)
    assert (
        result is not None
        and result.value is None
        and result.status == "reading_rollback"
    )
    readings[DAY + timedelta(days=1)] = Observation(
        Decimal(10),
        1,
        {
            "kind": "replacement",
            "previous_final": "110",
            "new_initial": "0",
            "reason": "换表",
        },
    )
    result = calculate_point(point(), DAY, readings)
    assert result is not None and result.value == 20


def test_rule_missing_zero_denominator_and_decimal_sum() -> None:
    rule = RuleDefinition(
        code="total",
        name="全厂水量",
        category="drinking_water",
        unit="m3",
        department="101车间",
        active_from=DAY,
        terms=[RuleTerm(metric_key="point:water", coefficient=Decimal(2))],
    )
    assert calculate_rule(rule, {}).value is None
    assert calculate_rule(
        rule, {"point:water": Calculation(Decimal("0.1"), "complete", {})}
    ).value == Decimal("0.2")
    ratio = rule.model_copy(
        update={
            "quantity_kind": "ratio",
            "operation": "ratio",
            "terms": [
                RuleTerm(metric_key="point:water"),
                RuleTerm(metric_key="point:water"),
            ],
        }
    )
    assert (
        calculate_rule(
            ratio, {"point:water": Calculation(Decimal(0), "complete", {})}
        ).status
        == "zero_denominator"
    )


def test_graph_rejects_cycles_units_and_duplicate_aggregation() -> None:
    meter = point(report_scope="detail")
    rule = RuleDefinition(
        code="total",
        name="车间水量",
        category="drinking_water",
        unit="m3",
        department="101车间",
        active_from=DAY,
        enabled=True,
        terms=[RuleTerm(metric_key="point:water")],
    )
    with pytest.raises(ValueError, match="同一汇总"):
        validate_graph({"point:water": meter}, {"rule:total": rule})
    rule = rule.model_copy(update={"unit": "t"})
    with pytest.raises(ValueError, match="单位"):
        validate_graph({"point:water": point()}, {"rule:total": rule})
    cycle = rule.model_copy(
        update={"enabled": False, "terms": [RuleTerm(metric_key="rule:total")]}
    )
    with pytest.raises(ValueError, match="循环"):
        validate_graph({}, {"rule:total": cycle})


def test_shared_meter_requires_allocation_and_large_calculations_stay_visible() -> None:
    rules = {
        "rule:first": RuleDefinition(
            code="first",
            name="一车间",
            category="drinking_water",
            unit="m3",
            department="101车间",
            active_from=DAY,
            enabled=True,
            terms=[RuleTerm(metric_key="point:water")],
        ),
        "rule:second": RuleDefinition(
            code="second",
            name="二车间",
            category="drinking_water",
            unit="m3",
            department="101车间",
            active_from=DAY,
            enabled=True,
            terms=[RuleTerm(metric_key="point:water")],
        ),
    }
    with pytest.raises(ValueError, match="重复统计"):
        validate_graph({"point:water": point()}, rules)
    for rule in rules.values():
        rule.terms[0].coefficient = Decimal("0.5")
    assert len(validate_graph({"point:water": point()}, rules)) == 2
    large = calculate_point(
        point(multiplier="10000000000000000000"),
        DAY,
        {
            DAY: Observation(Decimal(0), 1),
            DAY + timedelta(days=1): Observation(Decimal(100), 1),
        },
    )
    assert large is not None and large.value is None and large.status == "out_of_range"


@pytest.mark.asyncio
async def test_monthly_workshop_result_is_not_spread_into_daily_usage(
    native_service: EnergyLedgerService,
) -> None:
    service = native_service
    meter = await service.save_meter(
        MeterWrite(definition=point(code="monthly_" + uuid4().hex, frequency="monthly"))
    )
    await service.save_rule(
        RuleWrite(
            definition=RuleDefinition(
                code="month_result_" + uuid4().hex,
                name="车间月用水",
                category="drinking_water",
                unit="m3",
                department="101车间",
                frequency="monthly",
                active_from=DAY,
                enabled=True,
                terms=[RuleTerm(metric_key="point:" + meter.definition.code)],
            )
        )
    )
    assert service.actor_id
    await service.save_plan(
        PlanWrite(
            definition=EntryPlanDefinition(
                name="月度水表", point_ids=[meter.id], owner_ids=[service.actor_id]
            )
        )
    )
    for day, value in ((DAY, 100), (date(2026, 8, 1), 160)):
        task = await service.task((await service.generate_tasks(day))[0].id)
        await service.submit(
            task.id,
            EntrySubmission(
                values=[
                    EntryValue(
                        reading_id=task.items[0].id, version=0, value=Decimal(value)
                    )
                ]
            ),
        )
    report = await service.report(DAY, date(2026, 7, 31))
    assert report.status == "complete" and report.total_count == 1
    assert report.rows[0].usage_date == date(2026, 7, 31)
    assert report.rows[0].effective_value == 60


def workbook_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "饮用水码"
    sheet.append(["日期", "101车间", "101车间"])
    sheet.append(["7/1", 100, 200])
    sheet.append(["7/2", 110, 215])
    output = workbook.create_sheet("饮用水量")
    output.append(["日期", "101车间"])
    output.append(["7/1", "='饮用水码'!B3-'饮用水码'!B2"])
    workshop = workbook.create_sheet("101车间")
    workshop.append(["日期", "饮用水", "大罐数量"])
    workshop.append(["7/1", "='饮用水量'!B2", 1])
    target = BytesIO()
    workbook.save(target)
    return target.getvalue()


def test_import_preview_no_cache_and_disabled_template_without_tank() -> None:
    payload = inspect_xlsx(workbook_bytes(), 2026)
    draft = extract_template(payload)
    assert len(draft.meters) == 2
    assert draft.meters[0].code != draft.meters[1].code
    assert all(not meter.enabled for meter in draft.meters)
    assert any(rule.workshop == "101车间" for rule in draft.rules)
    assert all("大罐数量" not in rule.name for rule in draft.rules)
    assert all(rule.terms for rule in draft.rules)
    assert parse_source_date("7/1", 2025) == date(2025, 7, 1)


@pytest.fixture
async def native_service(db_session: AsyncSession) -> EnergyLedgerService:
    actor = User(
        id=uuid4(),
        username="native-" + uuid4().hex,
        name="能源测试管理员",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(actor)
    await db_session.flush()
    return EnergyLedgerService(db_session, actor)


@pytest.mark.asyncio
async def test_effective_date_gap_remains_visible_in_historical_calculation(
    native_service: EnergyLedgerService,
) -> None:
    suffix = uuid4().hex
    meter = point(code="future_meter_" + suffix, active_from=DAY + timedelta(days=1))
    await native_service.save_meter(MeterWrite(definition=meter))
    source = RuleDefinition(
        code="future_rule_" + suffix,
        name="后日生效来源",
        category=meter.category,
        department=meter.department,
        unit=meter.unit,
        active_from=DAY + timedelta(days=1),
        terms=[RuleTerm(metric_key="point:" + meter.code)],
        enabled=True,
        report_scope="source",
    )
    await native_service.save_rule(RuleWrite(definition=source))
    total = source.model_copy(
        update={
            "code": "earlier_total_" + suffix,
            "name": "历史汇总",
            "active_from": DAY,
            "terms": [RuleTerm(metric_key="rule:" + source.code)],
        }
    )
    await native_service.save_rule(RuleWrite(definition=total))
    outputs = await native_service.evaluate(DAY)
    result = next(value for key, _, value in outputs if key == "rule:" + total.code)
    assert result.status == "missing_dependency"
    assert result.value is None
    assert result.provenance["source_details"][0]["value"] is None


async def setup_plan(service: EnergyLedgerService) -> tuple[str, str]:
    meter = await service.save_meter(
        MeterWrite(definition=point(code="w_" + uuid4().hex))
    )
    assert service.actor_id is not None
    plan = await service.save_plan(
        PlanWrite(
            definition=EntryPlanDefinition(
                name="水表组", point_ids=[meter.id], owner_ids=[service.actor_id]
            )
        )
    )
    return str(meter.id), str(plan.id)


@pytest.mark.asyncio
async def test_native_submit_recalculate_correct_conflict_and_sealed_boundary(
    native_service: EnergyLedgerService,
) -> None:
    service = native_service
    await setup_plan(service)
    tasks = await service.generate_tasks(DAY)
    assert len(await service.generate_tasks(DAY)) == 1
    first = await service.task(tasks[0].id)
    await service.submit(
        first.id,
        EntrySubmission(
            values=[
                EntryValue(reading_id=first.items[0].id, version=0, value=Decimal(100))
            ],
            draft=True,
        ),
    )
    assert (await service.task(first.id)).completed_count == 0
    first = await service.task(first.id)
    await service.submit(
        first.id,
        EntrySubmission(
            values=[
                EntryValue(reading_id=first.items[0].id, version=1, value=Decimal(100))
            ]
        ),
    )
    following = await service.task(
        (await service.generate_tasks(DAY + timedelta(days=1)))[0].id
    )
    await service.submit(
        following.id,
        EntrySubmission(
            values=[
                EntryValue(
                    reading_id=following.items[0].id, version=0, value=Decimal(112)
                )
            ]
        ),
    )
    report = await service.report(DAY, DAY, report_scope="source")
    assert report.status == "complete" and report.rows[0].effective_value == 12
    with pytest.raises(AppException) as conflict:
        await service.submit(
            first.id,
            EntrySubmission(
                values=[
                    EntryValue(
                        reading_id=first.items[0].id, version=0, value=Decimal(99)
                    )
                ],
                reason="核对",
            ),
        )
    assert conflict.value.status_code == 409
    await service.submit(
        following.id,
        EntrySubmission(
            values=[
                EntryValue(
                    reading_id=following.items[0].id, version=1, value=Decimal(115)
                )
            ],
            reason="抄写更正",
        ),
    )
    assert (await service.report(DAY, DAY, report_scope="source")).rows[
        0
    ].effective_value == 15
    service.db.add(
        EnergyPeriodLock(month="2026-07", locked=True, version=1, snapshot=[])
    )
    await service.db.flush()
    with pytest.raises(AppException) as sealed:
        await service.submit(
            following.id,
            EntrySubmission(
                values=[
                    EntryValue(
                        reading_id=following.items[0].id, version=2, value=Decimal(116)
                    )
                ],
                reason="更正",
            ),
        )
    assert sealed.value.status_code == 409
    revisions = list(
        (
            await service.db.scalars(
                select(EnergyLedgerRevision).where(
                    EnergyLedgerRevision.entity_id == following.items[0].id
                )
            )
        ).all()
    )
    assert len(revisions) == 2 and revisions[-1].reason == "抄写更正"


@pytest.mark.asyncio
async def test_adjustment_zero_propagates_to_dependent_workshop(
    native_service: EnergyLedgerService,
) -> None:
    service = native_service
    meter = await service.save_meter(
        MeterWrite(
            definition=point(code="direct_" + uuid4().hex, reading_type="direct")
        )
    )
    rule = await service.save_rule(
        RuleWrite(
            definition=RuleDefinition(
                code="derived_" + uuid4().hex,
                name="101车间水量",
                category="drinking_water",
                unit="m3",
                department="101车间",
                active_from=DAY,
                enabled=True,
                terms=[RuleTerm(metric_key="point:" + meter.definition.code)],
            )
        )
    )
    assert service.actor_id
    await service.save_plan(
        PlanWrite(
            definition=EntryPlanDefinition(
                name="直接用量", point_ids=[meter.id], owner_ids=[service.actor_id]
            )
        )
    )
    task = await service.task(
        (await service.generate_tasks(DAY + timedelta(days=1)))[0].id
    )
    await service.submit(
        task.id,
        EntrySubmission(
            values=[
                EntryValue(reading_id=task.items[0].id, version=0, value=Decimal(12))
            ]
        ),
    )
    await service.adjust(
        AdjustmentWrite(
            metric_key="point:" + meter.definition.code,
            usage_date=DAY,
            mode="override",
            value=Decimal(0),
            reason="核对原始记录后更正",
        )
    )
    report = await service.report(DAY, DAY)
    assert report.rows[0].metric_key == "rule:" + rule.definition.code
    assert report.rows[0].effective_value == 0
    assert report.totals[0].value == 0


@pytest.mark.asyncio
async def test_native_real_routes_validation_submission_and_permissions(
    native_service: EnergyLedgerService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = native_service
    await setup_plan(service)
    task = await service.task((await service.generate_tasks(DAY))[0].id)

    async def user() -> User:
        assert service.actor
        return service.actor

    async def database():
        yield service.db

    @asynccontextmanager
    async def fake_admission(kind: str):
        yield

    # The request business path stays real; the external Redis release barrier is fake.
    monkeypatch.setattr(
        "app.core.maintenance_middleware.business_activity", fake_admission
    )

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Dazah-Page-Key": "energy:entry"},
        ) as client:
            response = await client.get(f"/api/v1/energy/entry-tasks/{task.id}")
            assert response.status_code == 200, response.text
            invalid = await client.post(
                f"/api/v1/energy/entry-tasks/{task.id}/submit",
                json={
                    "values": [
                        {
                            "reading_id": str(task.items[0].id),
                            "version": 0,
                            "value": "-1",
                        }
                    ]
                },
            )
            assert invalid.status_code == 422
            success = await client.post(
                f"/api/v1/energy/entry-tasks/{task.id}/submit",
                json={
                    "values": [
                        {
                            "reading_id": str(task.items[0].id),
                            "version": 0,
                            "value": "0",
                        }
                    ],
                    "source": "feishu",
                },
            )
            assert (
                success.status_code == 200
                and success.json()["data"]["completed_count"] == 1
            )
            stale = await client.post(
                f"/api/v1/energy/entry-tasks/{task.id}/submit",
                json={
                    "values": [
                        {
                            "reading_id": str(task.items[0].id),
                            "version": 0,
                            "value": "1",
                        }
                    ]
                },
            )
            assert stale.status_code == 409
            bad_date = await client.get(
                "/api/v1/energy/reporting",
                headers={"X-Dazah-Page-Key": "energy:reports"},
                params={"start_date": "2026-08-01", "end_date": "2026-07-01"},
            )
            assert bad_date.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_report_missing_dates_remain_visible_and_department_scope_fails_closed(
    native_service: EnergyLedgerService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    from app.platform.identity.data_scope import DepartmentScope

    service = native_service
    await setup_plan(service)
    report = await service.report(DAY, DAY + timedelta(days=2), report_scope="source")
    assert report.status == "pending" and report.total_count == 3
    assert all(row.effective_value is None for row in report.rows)
    monkeypatch.setattr(
        service,
        "scope",
        AsyncMock(return_value=DepartmentScope(department_names={"其他部门"})),
    )
    restricted = await service.report(DAY, DAY, report_scope="source")
    assert not restricted.rows and not restricted.totals


@pytest.mark.asyncio
async def test_non_owner_cannot_open_or_submit_forwarded_task(
    native_service: EnergyLedgerService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    service = native_service
    await setup_plan(service)
    task = await service.task((await service.generate_tasks(DAY))[0].id)
    outsider = User(
        id=uuid4(), username="outsider", name="其他员工", role="user", status="active"
    )
    restricted = EnergyLedgerService(service.db, outsider)
    monkeypatch.setattr(restricted, "is_manager", AsyncMock(return_value=False))
    with pytest.raises(AppException) as denied:
        await restricted.task(task.id)
    assert denied.value.status_code == 403
    with pytest.raises(AppException) as denied_write:
        await restricted.submit(
            task.id,
            EntrySubmission(
                values=[
                    EntryValue(reading_id=task.items[0].id, version=0, value=Decimal(0))
                ]
            ),
        )
    assert denied_write.value.status_code == 403


@pytest.mark.asyncio
async def test_import_conflict_does_not_overwrite_and_repeat_is_idempotent(
    native_service: EnergyLedgerService,
) -> None:
    from app.modules.energy.ledger_imports import confirm_import, preview_import
    from app.modules.energy.ledger_models import EnergyReading
    from app.modules.energy.ledger_schemas import ImportConfirm, ImportMapping

    service = native_service
    meter = await service.save_meter(
        MeterWrite(definition=point(code="import_" + uuid4().hex))
    )
    batch = await preview_import(service, workbook_bytes(), 2026)
    request = ImportConfirm(
        mappings=[ImportMapping(sheet="饮用水码", column=2, point_id=meter.id)],
        reason="核对历史抄表",
    )
    imported = await confirm_import(service, batch.id, request)
    assert imported.status == "imported" and imported.payload["imported_count"] == 2
    original_usage = next(
        value
        for key, _, value in await service.evaluate(DAY)
        if key == "point:" + meter.definition.code
    )
    assert original_usage.value == Decimal(10)
    assert original_usage.provenance["late"] is False

    imported_readings = list((await service.db.scalars(select(EnergyReading))).all())
    assert imported_readings and all(
        row.source == "import" for row in imported_readings
    )
    again = await confirm_import(service, batch.id, request)
    assert again.payload["imported_count"] == 2
    readings = list(
        (
            await service.db.scalars(
                select(EnergyReading).where(EnergyReading.point_id == meter.id)
            )
        ).all()
    )
    assert len(readings) == 2
    readings[0].value = Decimal(101)
    await service.db.flush()
    with pytest.raises(AppException) as conflict:
        await confirm_import(
            service, batch.id, request.model_copy(update={"reason": "再次核对"})
        )
    assert conflict.value.status_code == 409 and readings[0].value == 101


@pytest.mark.asyncio
async def test_ratio_period_recalculates_from_numerators_and_denominators(
    native_service: EnergyLedgerService,
) -> None:
    service = native_service
    numerator = await service.save_meter(
        MeterWrite(definition=point(code="n_" + uuid4().hex, reading_type="direct"))
    )
    denominator = await service.save_meter(
        MeterWrite(definition=point(code="d_" + uuid4().hex, reading_type="direct"))
    )
    await service.save_rule(
        RuleWrite(
            definition=RuleDefinition(
                code="ratio_" + uuid4().hex,
                name="占比",
                category="drinking_water",
                unit="比例",
                quantity_kind="ratio",
                operation="ratio",
                department="101车间",
                active_from=DAY,
                enabled=True,
                terms=[
                    RuleTerm(metric_key="point:" + numerator.definition.code),
                    RuleTerm(metric_key="point:" + denominator.definition.code),
                ],
            )
        )
    )
    assert service.actor_id
    await service.save_plan(
        PlanWrite(
            definition=EntryPlanDefinition(
                name="占比组",
                point_ids=[numerator.id, denominator.id],
                owner_ids=[service.actor_id],
            )
        )
    )
    for index, numbers in enumerate(((10, 20), (10, 100)), 1):
        task = await service.task(
            (await service.generate_tasks(DAY + timedelta(days=index)))[0].id
        )
        amounts = {numerator.id: numbers[0], denominator.id: numbers[1]}
        await service.submit(
            task.id,
            EntrySubmission(
                values=[
                    EntryValue(
                        reading_id=item.id,
                        version=item.version,
                        value=Decimal(amounts[item.point_id]),
                    )
                    for item in task.items
                ]
            ),
        )
    report = await service.report(DAY, DAY + timedelta(days=1))
    assert report.status == "complete"
    assert report.period_metrics[0].value == Decimal(20) / Decimal(120)
    assert not report.totals


@pytest.mark.asyncio
async def test_bot_timeout_retry_keeps_delivery_key_and_updates_card(
    native_service: EnergyLedgerService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    import httpx

    from app.modules.energy.ledger_models import EnergyNotificationRun
    from app.modules.energy.ledger_notifications import deliver_notifications, save_bot
    from app.modules.energy.ledger_schemas import BotDefinition, BotWrite
    from app.platform.integrations.feishu.im import FeishuMessageSendResult

    service = native_service
    await setup_plan(service)
    monkeypatch.setattr(
        "app.modules.energy.ledger_notifications.encrypt_secret",
        lambda value: "encrypted-for-test",
    )
    monkeypatch.setattr(
        "app.modules.energy.ledger_notifications.decrypt_secret",
        lambda value: "fake-secret",
    )
    monkeypatch.setattr(
        "app.modules.energy.ledger_notifications.FeishuAuth.get_tenant_access_token",
        AsyncMock(return_value="fake-token"),
    )
    monkeypatch.setattr(
        "app.modules.energy.ledger_notifications.notification_recipient_for_user",
        AsyncMock(return_value=("employee-test", "user_id")),
    )
    sender = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout"),
            FeishuMessageSendResult(ok=True, message_id="test-message"),
        ]
    )
    monkeypatch.setattr(
        "app.modules.energy.ledger_notifications.send_feishu_message", sender
    )
    updater = AsyncMock(
        return_value=FeishuMessageSendResult(ok=True, message_id="test-message")
    )
    monkeypatch.setattr(
        "app.modules.energy.ledger_notifications.update_feishu_message", updater
    )
    config = await save_bot(
        service.db,
        BotWrite(
            definition=BotDefinition(
                app_id="app-test", base_url="https://energy.example", enabled=True
            ),
            app_secret="fake-secret",
        ),
        service.actor_id,
    )
    assert config.secret_configured and config.version == 1
    task = (await service.generate_tasks(DAY))[0]
    now = datetime.now(UTC)
    await deliver_notifications(service.db, now)
    run = await service.db.scalar(
        select(EnergyNotificationRun).where(EnergyNotificationRun.task_id == task.id)
    )
    assert run is not None and run.status == "retry" and run.attempts == 1
    assert run.next_attempt_at
    await deliver_notifications(service.db, run.next_attempt_at + timedelta(seconds=1))
    assert run.status == "sent" and run.attempts == 2
    assert (
        sender.call_args_list[0].kwargs["uuid"]
        == sender.call_args_list[1].kwargs["uuid"]
    )
    content = sender.call_args_list[1].kwargs["content"]
    assert "source=feishu" in content and "fake-secret" not in content
    detail = await service.task(task.id)
    await service.submit(
        task.id,
        EntrySubmission(
            values=[
                EntryValue(reading_id=detail.items[0].id, version=0, value=Decimal(100))
            ]
        ),
    )
    await deliver_notifications(service.db, now + timedelta(minutes=10))
    updater.assert_awaited_once()
    assert "1/1" in updater.call_args.kwargs["content"]


@pytest.mark.asyncio
async def test_snapshot_import_retains_archive_and_excludes_calculated_totals(
    native_service: EnergyLedgerService,
) -> None:
    from app.modules.energy.ledger_imports import preview_snapshot_import
    from app.modules.energy.ledger_schemas import SnapshotImportRequest
    from app.modules.energy.models import (
        EnergySheetSnapshot,
        EnergySnapshotRow,
        EnergyWorkbookSheet,
    )

    service = native_service
    sheet = EnergyWorkbookSheet(
        id=uuid4(), document_id=uuid4(), external_sheet_id="sheet-test", title="电量"
    )
    snapshot = EnergySheetSnapshot(
        id=uuid4(),
        sheet_id=sheet.id,
        sync_run_id=uuid4(),
        snapshot_number=1,
        content_hash="fake-hash",
        header_values=["日期", "总计", "101车间"],
        row_count=1,
    )
    row = EnergySnapshotRow(
        id=uuid4(),
        snapshot_id=snapshot.id,
        row_index=2,
        values=["7/1", 100, 40],
        row_hash="fake-row",
    )
    service.db.add_all([sheet, snapshot, row])
    await service.db.flush()
    result = await preview_snapshot_import(
        service, SnapshotImportRequest(snapshot_ids=[snapshot.id], year=2026)
    )
    assert result.payload["source_snapshot_ids"] == [str(snapshot.id)]
    sheets = result.payload["sheets"]
    assert isinstance(sheets, list) and isinstance(sheets[0], dict)
    assert sheets[0]["cells"] == [
        {"date": "2026-07-01", "column": 3, "value": "40", "cell": "row-2-col-3"}
    ]
    assert row.values == ["7/1", 100, 40]
