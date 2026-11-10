"""Workbook metadata, automatic calculations and energy reporting."""

from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.energy.ledger_basis import build_report_basis
from app.modules.energy.ledger_calculations import (
    Calculation,
    Observation,
    active_on,
    calculate_point,
    calculate_rule,
    next_month,
    validate_graph,
)
from app.modules.energy.ledger_fields import (
    canonical_sheet,
    definition_key,
    definition_label,
    normalize_label,
)
from app.modules.energy.ledger_models import (
    EnergyCalculationRule,
    EnergyLedgerRevision,
    EnergyMeterPoint,
    EnergyReading,
    EnergyUsageFact,
    LedgerBase,
)
from app.modules.energy.ledger_reconciliation import (
    source_comparison,
    source_result_review,
)
from app.modules.energy.ledger_repository import EnergyLedgerRepository
from app.modules.energy.ledger_reviews import (
    apply_usage_review,
    load_usage_reviews,
    pending_metrics,
    review_provenance,
)
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    MeterResponse,
    PeriodMetric,
    ReportDistribution,
    ReportResponse,
    ReportTotal,
    ReportTrend,
    RevisionResponse,
    RuleDefinition,
    RuleResponse,
    UsageReview,
    UsageRow,
)
from app.modules.energy.ledger_source_policy import manual_input_allowed
from app.modules.energy.ledger_sources import MonthlySource, load_monthly_source
from app.platform.identity.models import User
from app.platform.identity.page_permissions import PagePermissionService

CALCULATION_POLICY = "same-day-formulas-v2-source-review"


PointDefinitions = dict[str, tuple[UUID, int, MeterDefinition]]
RuleDefinitions = dict[str, tuple[int, RuleDefinition]]


@dataclass
class _EvaluationInputs:
    """One report's inputs; never retained across requests or reading writes."""

    points: PointDefinitions
    rules: RuleDefinitions
    observations: dict[UUID, dict[date, Observation]]
    order: list[str]
    labels: dict[str, str]


def json_payload(value: BaseModel) -> dict[str, JsonValue]:
    return value.model_dump(mode="json")


def usable_usage(row: UsageRow) -> bool:
    return row.effective_value is not None and row.status in {"complete", "adjusted"}


def affected_dates(reading_date: date, point: MeterDefinition) -> set[date]:
    if point.reading_type == "direct":
        return {reading_date}
    if point.frequency == "monthly":
        previous = reading_date.replace(day=1) - timedelta(days=1)
        current = reading_date.replace(
            day=monthrange(reading_date.year, reading_date.month)[1]
        )
        return {previous, current}
    return {reading_date - timedelta(days=1), reading_date}


class EnergyLedgerService:
    def __init__(self, db: AsyncSession, actor: User | None = None) -> None:
        self.db = db
        self.actor = actor
        self.repo = EnergyLedgerRepository(db)
        self._usage_reviews: list[UsageReview] | None = None
        self._monthly_sources: dict[tuple[int, int], MonthlySource | None] = {}
        self._rule_aliases: dict[str, str] = {}

    async def monthly_source(self, day: date) -> MonthlySource | None:
        period = day.year, day.month
        if period not in self._monthly_sources:
            source = await load_monthly_source(self.db, *period, await self.meters())
            if source is not None:
                source.workbook.set_reviews(await self.usage_reviews())
            self._monthly_sources[period] = source
        return self._monthly_sources[period]

    async def usage_reviews(self) -> list[UsageReview]:
        if self._usage_reviews is None:
            self._usage_reviews = await load_usage_reviews(self)
        return self._usage_reviews

    @property
    def actor_id(self) -> UUID | None:
        return self.actor.id if self.actor else None

    async def is_manager(self) -> bool:
        if self.actor is None:
            return False
        if self.actor.role == "admin":
            return True
        grants = await PagePermissionService().effective_grants(
            self.db, user=self.actor
        )
        return any(
            grant.page_key == "energy:settings" and "operate" in grant.permissions
            for grant in grants
        )

    async def require_manager(self) -> None:
        if not await self.is_manager():
            raise AppException(403, "需要能源配置管理操作权限")

    def revision(
        self,
        kind: str,
        item: LedgerBase,
        version: int,
        payload: dict[str, JsonValue],
        reason: str,
    ) -> None:
        self.db.add(
            EnergyLedgerRevision(
                entity_kind=kind,
                entity_id=item.id,
                version=version,
                payload=payload,
                reason=reason,
                created_by=self.actor_id,
                updated_by=self.actor_id,
            )
        )

    async def meters(self) -> list[MeterResponse]:
        selected: dict[tuple[str, int | str], MeterResponse] = {}
        for item in await self.repo.all(EnergyMeterPoint):
            definition = MeterDefinition.model_validate(item.definition)
            if not manual_input_allowed(
                definition.source_sheet,
                definition.name,
                definition.reading_type,
                definition.category,
            ):
                continue
            key = (definition.source_sheet, definition.source_column or definition.code)
            if key in selected:
                continue
            selected[key] = MeterResponse(
                id=item.id,
                version=item.version,
                definition=definition.model_copy(
                    update={
                        "enabled": True,
                        "active_from": date(2000, 1, 1),
                        "active_to": None,
                    }
                ),
            )
        return list(selected.values())

    async def rules(self) -> list[RuleResponse]:
        selected: dict[tuple[str, str, str, str, str], RuleResponse] = {}
        aliases: dict[str, str] = {}
        for item in await self.repo.all(EnergyCalculationRule):
            definition = RuleDefinition.model_validate(item.definition)
            identity = (
                definition_key(definition)
                if definition.source_sheet and definition.source_column
                else definition.code,
                definition.category,
                definition.unit,
                definition.quantity_kind,
                definition.temperature,
            )
            existing = selected.get(identity)
            if existing is not None:
                aliases["rule:" + definition.code] = "rule:" + existing.definition.code
                continue
            selected[identity] = RuleResponse(
                id=item.id,
                version=item.version,
                definition=definition.model_copy(
                    update={
                        "enabled": True,
                        "active_from": date(2000, 1, 1),
                        "active_to": None,
                    }
                ),
            )
        self._rule_aliases = aliases
        rows = list(selected.values())
        for row in rows:
            sheet_name = canonical_sheet(row.definition.source_sheet)
            label = normalize_label(definition_label(row.definition))
            row.definition = row.definition.model_copy(
                update={
                    "terms": [
                        term.model_copy(
                            update={
                                "metric_key": aliases.get(
                                    term.metric_key, term.metric_key
                                )
                            }
                        )
                        for term in row.definition.terms
                    ],
                    **(
                        {"name": f"{sheet_name}·{label}"}
                        if row.definition.source_sheet and "·" in row.definition.name
                        else {}
                    ),
                }
            )
        return rows

    async def definitions_on(
        self, day: date
    ) -> tuple[
        dict[str, tuple[UUID, int, MeterDefinition]],
        dict[str, tuple[int, RuleDefinition]],
    ]:
        # Definitions are workbook metadata, no longer user-managed active periods.
        points = {
            "point:" + item.definition.code: (
                item.id,
                item.version,
                item.definition.model_copy(
                    update={
                        "enabled": True,
                        "active_from": date(2000, 1, 1),
                        "active_to": None,
                    }
                ),
            )
            for item in await self.meters()
        }
        rules = {
            "rule:" + item.definition.code: (
                item.version,
                item.definition.model_copy(
                    update={
                        "enabled": True,
                        "active_from": date(2000, 1, 1),
                        "active_to": None,
                    }
                ),
            )
            for item in await self.rules()
        }
        physical = {
            (item.definition.source_sheet, item.definition.source_column): item
            for item in await self.meters()
            if item.definition.source_column
        }
        for item in await self.repo.all(EnergyMeterPoint):
            raw = MeterDefinition.model_validate(item.definition)
            if raw.source_column is None:
                continue
            canonical = physical.get((raw.source_sheet, raw.source_column))
            if canonical is not None:
                points["point:" + raw.code] = (
                    canonical.id,
                    canonical.version,
                    raw.model_copy(
                        update={
                            "enabled": True,
                            "active_from": date(2000, 1, 1),
                            "active_to": None,
                        }
                    ),
                )
        return points, rules

    async def _evaluation_inputs(
        self,
        start: date,
        end: date,
        points: PointDefinitions,
        rules: RuleDefinitions,
        *,
        metric_keys: set[str] | None = None,
    ) -> _EvaluationInputs:
        if metric_keys is not None:
            required = set(metric_keys)
            pending = list(required)
            while pending:
                key = pending.pop()
                if key not in rules:
                    continue
                for term in rules[key][1].terms:
                    if term.metric_key not in required:
                        required.add(term.metric_key)
                        pending.append(term.metric_key)
            points = {key: item for key, item in points.items() if key in required}
            rules = {key: item for key, item in rules.items() if key in required}
        ids = [item[0] for item in points.values()]
        reading_rows = (
            await self.db.scalars(
                select(EnergyReading).where(
                    EnergyReading.point_id.in_(ids),
                    EnergyReading.reading_date.between(
                        start.replace(day=1), next_month(end)
                    ),
                    EnergyReading.value.is_not(None),
                    EnergyReading.is_deleted.is_(False),
                )
            )
        ).all()
        observations: dict[UUID, dict[date, Observation]] = defaultdict(dict)
        for row in reading_rows:
            if row.value is not None:
                observations[row.point_id][row.reading_date] = Observation(
                    row.value,
                    row.version,
                    row.exception,
                )
        # Expired/disabled sources remain absent during evaluation.
        try:
            order = validate_graph(
                {
                    key: value[2].model_copy(update={"enabled": False})
                    for key, value in points.items()
                },
                {
                    key: value[1].model_copy(update={"enabled": False})
                    for key, value in rules.items()
                },
                # A dependency can begin later than a historical report date.
                # Keep its result missing; configuration writes remain strict.
                allow_missing=True,
            )
        except ValueError as exc:
            raise AppException(409, "历史计算配置无效，请核对来源与规则版本") from exc
        return _EvaluationInputs(
            points=points,
            rules=rules,
            observations=observations,
            order=order,
            labels={
                **{key: item[2].name for key, item in points.items()},
                **{key: item[1].name for key, item in rules.items()},
            },
        )

    async def evaluate(
        self, day: date, *, inputs: _EvaluationInputs | None = None
    ) -> list[tuple[str, MeterDefinition | RuleDefinition, Calculation]]:
        if inputs is None:
            points, rules = await self.definitions_on(day)
            inputs = await self._evaluation_inputs(day, day, points, rules)
        points, rules = inputs.points, inputs.rules
        source = await self.monthly_source(day)
        calculated: dict[str, Calculation] = {}
        outputs: list[tuple[str, MeterDefinition | RuleDefinition, Calculation]] = []
        for key, (point_id, version, point) in points.items():
            result = calculate_point(point, day, inputs.observations[point_id])
            if result is not None:
                result.provenance["configuration_version"] = version
                calculated[key] = result
                outputs.append((key, point, result))
        for key in inputs.order:
            version, rule = rules[key]
            if active_on(rule, day) and (
                rule.frequency == "daily"
                or day.day == monthrange(day.year, day.month)[1]
            ):
                result = calculate_rule(rule, calculated)
                components = [
                    f"{term.coefficient} × "
                    f"{inputs.labels.get(term.metric_key, term.metric_key)}"
                    for term in rule.terms
                ]
                result.provenance["formula"] = (
                    " / " if rule.operation == "ratio" else " + "
                ).join(components)
                if source is not None and rule.source_column:
                    reference = source.workbook.reference_on(rule, day)
                    if reference:
                        result.provenance.update(
                            reference={
                                **reference,
                                "source_batch_id": str(source.batch_id),
                            },
                            business_key=reference["business_key"],
                            business_sheet=canonical_sheet(rule.source_sheet),
                            business_name=reference["business_name"],
                            source_column=reference["source_column"],
                        )
                result.provenance["configuration_version"] = version
                source_details: list[JsonValue] = [
                    {
                        "name": points[term.metric_key][2].name
                        if term.metric_key in points
                        else rules[term.metric_key][1].name
                        if term.metric_key in rules
                        else term.metric_key,
                        "coefficient": str(term.coefficient),
                        "value": str(calculated[term.metric_key].value)
                        if term.metric_key in calculated
                        and calculated[term.metric_key].value is not None
                        else None,
                        "evidence": calculated[term.metric_key].provenance
                        if term.metric_key in calculated
                        else {},
                    }
                    for term in rule.terms
                ]
                result.provenance["source_details"] = source_details
                calculated[key] = result
                outputs.append((key, rule, result))
        source_reviews: list[UsageReview] = []
        comparisons: dict[str, dict[str, JsonValue]] = {}
        if source is not None:
            for key, definition, result in outputs:
                if not isinstance(definition, RuleDefinition):
                    continue
                original = source.workbook.business_cell(definition, day)
                comparison = source_comparison(result, original)
                if comparison is not None:
                    comparisons[key] = comparison
                review = source_result_review(day, definition, result, original)
                if review is not None:
                    source_reviews.append(review)
        pending = pending_metrics(
            day,
            {
                **{key: item[2] for key, item in points.items()},
                **{key: item[1] for key, item in rules.items()},
            },
            [*await self.usage_reviews(), *source_reviews],
        )
        return [
            (
                key,
                definition,
                Calculation(
                    result.value,
                    "pending_review" if key in pending else result.status,
                    {
                        **(
                            review_provenance(result.provenance, pending[key])
                            if key in pending
                            else result.provenance
                        ),
                        "calculation_policy": CALCULATION_POLICY,
                        "calculation_date": day.isoformat(),
                        **(
                            {"source_comparison": comparisons[key]}
                            if key in pending and key in comparisons
                            else {}
                        ),
                    },
                ),
            )
            for key, definition, result in outputs
        ]

    async def calculated_rows(
        self, day: date, *, inputs: _EvaluationInputs | None = None
    ) -> dict[str, UsageRow]:
        """Read-time recalculation also invalidates facts from older policies."""
        return {
            key: UsageRow(
                id=uuid5(NAMESPACE_URL, f"energy:{key}:{day}"),
                metric_key=key,
                usage_date=day,
                name=definition.name,
                category=definition.category,
                unit=definition.unit,
                workshop=definition.workshop,
                department=definition.department,
                report_scope=definition.report_scope,
                quantity_kind=definition.quantity_kind,
                temperature=definition.temperature,
                calculated_value=result.value,
                effective_value=None
                if result.status == "pending_review"
                else result.value,
                status=result.status,
                provenance={**result.provenance, "unmaterialized": True},
            )
            for key, definition, result in await self.evaluate(day, inputs=inputs)
        }

    async def rebuild_existing(self, start: date) -> None:
        days = set(
            (
                await self.db.scalars(
                    select(EnergyUsageFact.usage_date)
                    .where(EnergyUsageFact.usage_date >= start)
                    .distinct()
                )
            ).all()
        )
        if len(days) > 366:
            raise AppException(409, "配置影响超过一年，请按期间调整配置")
        await self.rebuild(days)

    async def rebuild(self, days: set[date]) -> None:
        self._monthly_sources.clear()
        for day in sorted(days):
            outputs = await self.evaluate(day)
            existing = {
                item.metric_key: item
                for item in (
                    await self.db.scalars(
                        select(EnergyUsageFact).where(EnergyUsageFact.usage_date == day)
                    )
                ).all()
            }
            active_keys: set[str] = set()
            for key, definition, result in outputs:
                active_keys.add(key)
                item = existing.get(key) or EnergyUsageFact(
                    id=uuid4(), metric_key=key, usage_date=day, created_by=self.actor_id
                )
                item.calculated_value = result.value
                item.effective_value = (
                    None if result.status == "pending_review" else result.value
                )
                item.status = result.status
                item.definition = json_payload(definition)
                item.provenance = result.provenance
                item.is_deleted = False
                item.updated_by = self.actor_id
                self.db.add(item)
            for key, item in existing.items():
                if key not in active_keys:
                    item.is_deleted = True
            await self.db.flush()

    @staticmethod
    def validate_range(start: date, end: date) -> None:
        if start > end or (end - start).days > 365:
            raise AppException(422, "查询日期须按先后顺序且最多覆盖一年")

    @staticmethod
    def usage_row(item: EnergyUsageFact) -> UsageRow:
        definition = item.definition
        return UsageRow(
            id=item.id,
            metric_key=item.metric_key,
            usage_date=item.usage_date,
            name=str(definition["name"]),
            category=MeterDefinition.model_validate(definition).category
            if item.metric_key.startswith("point:")
            else RuleDefinition.model_validate(definition).category,
            unit=str(definition["unit"]),
            workshop=str(definition.get("workshop", "")),
            department=str(definition["department"]),
            report_scope=MeterDefinition.model_validate(definition).report_scope
            if item.metric_key.startswith("point:")
            else RuleDefinition.model_validate(definition).report_scope,
            quantity_kind=str(definition.get("quantity_kind", "volume")),
            temperature=str(definition.get("temperature", "")),
            calculated_value=item.calculated_value,
            effective_value=item.effective_value,
            status=item.status,
            provenance=item.provenance,
        )

    async def report(
        self,
        start: date,
        end: date,
        *,
        report_scope: str = "detail",
        workshop: str | None = None,
        category: str | None = None,
        metric_key: str | None = None,
        metric_keys: set[str] | None = None,
        page: int = 1,
        page_size: int = 100,
        include_all: bool = False,
        include_basis: bool = False,
    ) -> ReportResponse:
        self.validate_range(start, end)
        query = select(EnergyUsageFact).where(
            EnergyUsageFact.usage_date.between(start, end),
            EnergyUsageFact.is_deleted.is_(False),
        )
        if metric_key:
            query = query.where(EnergyUsageFact.metric_key == metric_key)
        if metric_keys is not None:
            query = query.where(EnergyUsageFact.metric_key.in_(metric_keys))
        if report_scope != "all" and not metric_key:
            query = query.where(
                EnergyUsageFact.definition["report_scope"].astext == report_scope
            )
        if workshop:
            query = query.where(
                EnergyUsageFact.definition["workshop"].astext == workshop
            )
        if category:
            query = query.where(
                EnergyUsageFact.definition["category"].astext == category
            )
        facts = list(
            (
                await self.db.scalars(
                    query.order_by(
                        EnergyUsageFact.usage_date.desc(), EnergyUsageFact.metric_key
                    ).limit(100001)
                )
            ).all()
        )
        if len(facts) > 100000:
            raise AppException(422, "结果过多，请缩小日期或筛选范围")
        rows = [self.usage_row(item) for item in facts]
        reviews = await self.usage_reviews()
        day_reviews: dict[date, dict[str, list[dict[str, JsonValue]]]] = {}
        seen = {(row.metric_key, row.usage_date) for row in rows}
        basis_definitions: dict[date, dict[str, MeterDefinition | RuleDefinition]] = {}
        # Metadata is date-independent; active periods are checked per day below.
        points, rules = await self.definitions_on(start)
        definitions: dict[str, MeterDefinition | RuleDefinition] = {
            **{key: item[2] for key, item in points.items()},
            **{key: item[1] for key, item in rules.items()},
        }
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            day_reviews[day] = pending_metrics(day, definitions, reviews)
            basis_definitions[day] = definitions
            for key, definition in definitions.items():
                if (key, day) in seen or not active_on(definition, day):
                    continue
                if (
                    definition.frequency == "monthly"
                    and day.day != monthrange(day.year, day.month)[1]
                ):
                    continue
                if metric_key and key != metric_key:
                    continue
                if metric_keys is not None and key not in metric_keys:
                    continue
                if (
                    report_scope != "all"
                    and not metric_key
                    and definition.report_scope != report_scope
                ):
                    continue
                if (category and definition.category != category) or (
                    workshop and definition.workshop != workshop
                ):
                    continue
                rows.append(
                    UsageRow(
                        id=uuid5(NAMESPACE_URL, f"energy:{key}:{day}"),
                        metric_key=key,
                        usage_date=day,
                        name=definition.name,
                        category=definition.category,
                        unit=definition.unit,
                        workshop=definition.workshop,
                        department=definition.department,
                        report_scope=definition.report_scope,
                        quantity_kind=definition.quantity_kind,
                        temperature=definition.temperature,
                        calculated_value=None,
                        effective_value=None,
                        status="missing_reading"
                        if key.startswith("point:")
                        else "missing_dependency",
                        provenance={"unmaterialized": True},
                    )
                )
        rows = [
            row
            for row in rows
            if self._rule_aliases.get(row.metric_key, row.metric_key) == row.metric_key
        ]
        evaluated: dict[date, dict[str, UsageRow]] = {}
        inputs: _EvaluationInputs | None = None

        async def current_rows(day: date) -> dict[str, UsageRow]:
            nonlocal inputs
            if day not in evaluated:
                if inputs is None:
                    inputs = await self._evaluation_inputs(
                        start, end, points, rules, metric_keys=metric_keys
                    )
                evaluated[day] = await self.calculated_rows(day, inputs=inputs)
            return evaluated[day]

        for index, row in enumerate(rows):
            if (
                row.provenance.get("calculation_policy") != CALCULATION_POLICY
                or "source_cell" in row.provenance
            ):
                fresh = (await current_rows(row.usage_date)).get(row.metric_key)
                if fresh is not None:
                    provenance = dict(fresh.provenance)
                    if not row.provenance.get("unmaterialized"):
                        provenance.pop("unmaterialized", None)
                    row = fresh.model_copy(
                        update={"id": row.id, "provenance": provenance}
                    )
                else:
                    row = row.model_copy(
                        update={
                            "calculated_value": None,
                            "effective_value": None,
                            "status": "unconfigured",
                            "provenance": {
                                "calculation_policy": CALCULATION_POLICY,
                                "reason": "当前没有对应的计算规则，历史结果仅保留存档",
                            },
                        }
                    )
            rows[index] = apply_usage_review(
                row, day_reviews[row.usage_date].get(row.metric_key, [])
            )
        rows.sort(key=lambda row: (row.usage_date, row.metric_key), reverse=True)
        if len(rows) > 100000:
            raise AppException(422, "结果过多，请缩小查询范围")
        groups: dict[tuple[str, str, str, str], list[UsageRow]] = defaultdict(list)
        for row in rows:
            if row.quantity_kind != "ratio":
                groups[
                    (row.category, row.unit, row.quantity_kind, row.temperature)
                ].append(row)
        totals = [
            ReportTotal(
                category=items[0].category,
                unit=key[1],
                quantity_kind=key[2],
                temperature=key[3],
                value=sum(
                    (
                        item.effective_value
                        for item in items
                        if usable_usage(item) and item.effective_value is not None
                    ),
                    Decimal(0),
                )
                if any(usable_usage(item) for item in items)
                else None,
                expected_count=len(items),
                available_count=sum(usable_usage(item) for item in items),
            )
            for key, items in groups.items()
        ]
        if include_basis:
            basis_facts: dict[date, dict[str, UsageRow]] = {}
            for total, items in zip(totals, groups.values(), strict=True):
                by_day: dict[date, list[UsageRow]] = defaultdict(list)
                for item in items:
                    by_day[item.usage_date].append(item)
                complete_dates = [
                    day
                    for day, daily_items in by_day.items()
                    if all(usable_usage(item) for item in daily_items)
                ]
                # Show evidence for the same complete day as the card. If none is
                # complete, expose the latest available/expected day as incomplete.
                available_dates = [
                    day
                    for day, daily_items in by_day.items()
                    if any(item.effective_value is not None for item in daily_items)
                ]
                basis_day = max(complete_dates or available_dates or list(by_day))
                if basis_day not in basis_facts:
                    basis_facts[basis_day] = await current_rows(basis_day)
                total.basis = build_report_basis(
                    basis_day,
                    [item.metric_key for item in by_day[basis_day]],
                    basis_definitions[basis_day],
                    basis_facts[basis_day],
                )
        daily: dict[tuple[date, str, str, str, str], list[UsageRow]] = defaultdict(list)
        workshops: dict[tuple[str, str, str, str, str], list[UsageRow]] = defaultdict(
            list
        )
        metrics: dict[str, list[UsageRow]] = defaultdict(list)
        for row in rows:
            metrics[row.metric_key].append(row)
            if row.quantity_kind != "ratio":
                daily[
                    (
                        row.usage_date,
                        row.category,
                        row.unit,
                        row.quantity_kind,
                        row.temperature,
                    )
                ].append(row)
                workshops[
                    (
                        row.workshop or "公共区域",
                        row.category,
                        row.unit,
                        row.quantity_kind,
                        row.temperature,
                    )
                ].append(row)

        def sum_values(items: list[UsageRow]) -> Decimal | None:
            numbers = [
                item.effective_value
                for item in items
                if usable_usage(item) and item.effective_value is not None
            ]
            return sum(numbers, Decimal(0)) if numbers else None

        trend = [
            ReportTrend(
                usage_date=key[0],
                category=items[0].category,
                unit=key[2],
                quantity_kind=key[3],
                temperature=key[4],
                value=sum_values(items),
                expected_count=len(items),
                available_count=sum(usable_usage(item) for item in items),
            )
            for key, items in sorted(daily.items())
        ]
        distribution = [
            ReportDistribution(
                workshop=key[0],
                category=items[0].category,
                unit=key[2],
                quantity_kind=key[3],
                temperature=key[4],
                value=sum_values(items),
                expected_count=len(items),
                available_count=sum(usable_usage(item) for item in items),
            )
            for key, items in workshops.items()
        ]
        period_metrics: list[PeriodMetric] = []
        for key, items in metrics.items():
            value = sum_values(items)
            status = (
                "complete" if all(usable_usage(item) for item in items) else "partial"
            )
            if items[0].quantity_kind == "ratio":
                # Recompute period ratios from corresponding source quantities.
                numerator, denominator = Decimal(0), Decimal(0)
                usable = True
                for row in items:
                    if not usable_usage(row) and row.status != "not_applicable":
                        usable = False
                        break
                    terms = row.provenance.get("terms")
                    if not isinstance(terms, list) or len(terms) != 2:
                        usable = False
                        break
                    components: list[Decimal] = []
                    for term in terms:
                        if not isinstance(term, dict):
                            usable = False
                            break
                        fact = (await current_rows(row.usage_date)).get(
                            str(term["metric_key"])
                        )
                        if (
                            fact is None
                            or fact.effective_value is None
                            or fact.status not in {"complete", "adjusted"}
                            or str(term["metric_key"]) in day_reviews[row.usage_date]
                        ):
                            usable = False
                            break
                        components.append(
                            fact.effective_value * Decimal(str(term["coefficient"]))
                        )
                    if len(components) != 2:
                        usable = False
                        break
                    numerator += components[0]
                    denominator += components[1]
                value = numerator / denominator if usable and denominator else None
                if value is not None and items[0].unit == "%":
                    value *= 100
                status = (
                    "complete"
                    if value is not None
                    else "missing_dependency"
                    if not usable
                    else "not_applicable"
                )
            period_metrics.append(
                PeriodMetric(
                    metric_key=key,
                    name=items[0].name,
                    unit=items[0].unit,
                    value=value,
                    status=status,
                    quantity_kind=items[0].quantity_kind,
                )
            )
        complete_days = [
            day
            for day in {row.usage_date for row in rows}
            if all(
                usable_usage(row) or row.status == "not_applicable"
                for row in rows
                if row.usage_date == day
            )
        ]
        missing = sum(
            row.effective_value is None and row.status != "not_applicable"
            for row in rows
        )
        invalid = sum(
            not usable_usage(row) and row.status != "not_applicable" for row in rows
        )
        task_query = select(EnergyReading).where(
            EnergyReading.reading_date.between(start, end)
        )
        entries = list((await self.db.scalars(task_query)).all())
        return ReportResponse(
            start_date=start,
            end_date=end,
            status="pending"
            if not rows or missing == len(rows)
            else "partial"
            if invalid
            else "complete",
            rows=rows
            if include_all
            else rows[(page - 1) * page_size : page * page_size],
            totals=totals
            if metric_key or report_scope not in {"all", "source", "check"}
            else [],
            trend=trend
            if metric_key or report_scope not in {"all", "source", "check"}
            else [],
            distribution=distribution
            if metric_key or report_scope not in {"all", "source", "check"}
            else [],
            period_metrics=period_metrics,
            total_count=len(rows),
            latest_complete_date=max(complete_days) if complete_days else None,
            entry_total=len(entries),
            entry_completed=sum(item.value is not None for item in entries),
            quality_counts=dict(
                Counter(
                    row.status
                    for row in rows
                    if not usable_usage(row) and row.status != "not_applicable"
                )
            ),
        )

    async def trace(self, fact_id: UUID) -> UsageRow:
        item = await self.repo.get(EnergyUsageFact, fact_id)
        fresh = (await self.calculated_rows(item.usage_date)).get(item.metric_key)
        if fresh is None:
            raise AppException(409, "该计算字段已不存在，请刷新报表")
        provenance = dict(fresh.provenance)
        provenance.pop("unmaterialized", None)
        return fresh.model_copy(update={"id": item.id, "provenance": provenance})

    async def history(self, kind: str, entity_id: UUID) -> list[RevisionResponse]:
        if kind == "reading":
            await self.repo.get(EnergyReading, entity_id)
        else:
            await self.require_manager()
        items = (
            await self.db.scalars(
                select(EnergyLedgerRevision)
                .where(
                    EnergyLedgerRevision.entity_kind == kind,
                    EnergyLedgerRevision.entity_id == entity_id,
                )
                .order_by(EnergyLedgerRevision.created_at.desc())
                .limit(200)
            )
        ).all()
        return [
            RevisionResponse.model_validate(item, from_attributes=True)
            for item in items
        ]
