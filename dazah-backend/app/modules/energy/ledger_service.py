"""Native energy business rules, transactions, responsibility and reporting."""

from calendar import monthrange
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from pydantic import BaseModel, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.energy.ledger_calculations import (
    Calculation,
    Observation,
    active_on,
    calculate_point,
    calculate_rule,
    next_month,
    validate_graph,
)
from app.modules.energy.ledger_models import (
    EnergyAdjustment,
    EnergyCalculationRule,
    EnergyEntryPlan,
    EnergyEntryTask,
    EnergyLedgerRevision,
    EnergyMeterPoint,
    EnergyPeriodLock,
    EnergyReading,
    EnergyUsageFact,
    LedgerBase,
)
from app.modules.energy.ledger_repository import EnergyLedgerRepository
from app.modules.energy.ledger_schemas import (
    AdjustmentWrite,
    EntryItemResponse,
    EntryPlanDefinition,
    EntrySubmission,
    LockResponse,
    LockWrite,
    MeterDefinition,
    MeterResponse,
    MeterWrite,
    PeriodMetric,
    PlanResponse,
    PlanWrite,
    ReadingException,
    ReportDistribution,
    ReportResponse,
    ReportTotal,
    ReportTrend,
    RevisionResponse,
    RuleDefinition,
    RuleResponse,
    RuleWrite,
    TaskResponse,
    UsageRow,
)
from app.modules.energy.ledger_source_policy import manual_input_allowed
from app.platform.identity.data_scope import (
    DepartmentScope,
    resolve_user_department_scope,
)
from app.platform.identity.models import User
from app.platform.identity.page_permissions import PagePermissionService


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

    async def scope(self) -> DepartmentScope:
        if self.actor is None:
            raise AppException(401, "请先登录")
        return await resolve_user_department_scope(self.db, self.actor)

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
        scope = await self.scope()
        return [
            MeterResponse(id=item.id, version=item.version, definition=definition)
            for item in await self.repo.all(EnergyMeterPoint)
            if scope.allows(
                (
                    definition := MeterDefinition.model_validate(item.definition)
                ).department
            )
        ]

    async def rules(self) -> list[RuleResponse]:
        scope = await self.scope()
        return [
            RuleResponse(id=item.id, version=item.version, definition=definition)
            for item in await self.repo.all(EnergyCalculationRule)
            if scope.allows(
                (
                    definition := RuleDefinition.model_validate(item.definition)
                ).department
            )
        ]

    async def _configuration_change(self, start: date) -> None:
        last = await self.db.scalar(
            select(EnergyPeriodLock.month)
            .where(EnergyPeriodLock.locked.is_(True))
            .order_by(EnergyPeriodLock.month.desc())
            .limit(1)
        )
        if last and start <= date.fromisoformat(last + "-01").replace(
            day=monthrange(int(last[:4]), int(last[5:]))[1]
        ):
            raise AppException(
                409, "配置生效日期涉及已封账月份，请先解锁或选择未来生效日期"
            )

    async def save_meter(
        self, payload: MeterWrite, record_id: UUID | None = None
    ) -> MeterResponse:
        await self.require_manager()
        await self.repo.serialize_write()
        await self._configuration_change(payload.definition.active_from)
        existing = (
            await self.repo.get(EnergyMeterPoint, record_id) if record_id else None
        )
        if existing and (
            existing.version != payload.version
            or existing.code != payload.definition.code
        ):
            raise AppException(409, "版本已变更或计量点编号被修改，请刷新")
        if existing and not payload.reason:
            raise AppException(422, "修改配置须填写原因")
        duplicate = await self.db.scalar(
            select(EnergyMeterPoint).where(
                EnergyMeterPoint.code == payload.definition.code
            )
        )
        if duplicate and duplicate != existing:
            raise AppException(409, "计量点编号已存在")
        if not existing and len(await self.repo.all(EnergyMeterPoint)) >= 500:
            raise AppException(409, "计量点上限为 500 个")
        points = {
            "point:" + item.code: MeterDefinition.model_validate(item.definition)
            for item in await self.repo.all(EnergyMeterPoint)
        }
        points["point:" + payload.definition.code] = payload.definition
        rules = {
            "rule:" + item.code: RuleDefinition.model_validate(item.definition)
            for item in await self.repo.all(EnergyCalculationRule)
        }
        try:
            validate_graph(points, rules)
        except ValueError as exc:
            raise AppException(422, str(exc)) from exc
        item = existing or EnergyMeterPoint(
            id=uuid4(),
            code=payload.definition.code,
            version=0,
            created_by=self.actor_id,
        )
        item.version += 1
        item.definition = json_payload(payload.definition)
        item.updated_by = self.actor_id
        self.db.add(item)
        self.revision("meter", item, item.version, item.definition, payload.reason)
        await self.db.flush()
        await self.rebuild_existing(payload.definition.active_from)
        return MeterResponse(
            id=item.id, version=item.version, definition=payload.definition
        )

    async def save_rule(
        self, payload: RuleWrite, record_id: UUID | None = None
    ) -> RuleResponse:
        await self.require_manager()
        await self.repo.serialize_write()
        await self._configuration_change(payload.definition.active_from)
        existing = (
            await self.repo.get(EnergyCalculationRule, record_id) if record_id else None
        )
        if existing and (
            existing.version != payload.version
            or existing.code != payload.definition.code
        ):
            raise AppException(409, "规则版本已变更或编号被修改，请刷新")
        if existing and not payload.reason:
            raise AppException(422, "修改规则须填写原因")
        duplicate = await self.db.scalar(
            select(EnergyCalculationRule).where(
                EnergyCalculationRule.code == payload.definition.code
            )
        )
        if duplicate and duplicate != existing:
            raise AppException(409, "规则编号已存在")
        points = {
            "point:" + item.code: MeterDefinition.model_validate(item.definition)
            for item in await self.repo.all(EnergyMeterPoint)
        }
        rules = {
            "rule:" + item.code: RuleDefinition.model_validate(item.definition)
            for item in await self.repo.all(EnergyCalculationRule)
        }
        rules["rule:" + payload.definition.code] = payload.definition
        try:
            validate_graph(points, rules)
        except ValueError as exc:
            raise AppException(422, str(exc)) from exc
        item = existing or EnergyCalculationRule(
            id=uuid4(),
            code=payload.definition.code,
            version=0,
            created_by=self.actor_id,
        )
        item.version += 1
        item.definition = json_payload(payload.definition)
        item.updated_by = self.actor_id
        self.db.add(item)
        self.revision("rule", item, item.version, item.definition, payload.reason)
        await self.db.flush()
        await self.rebuild_existing(payload.definition.active_from)
        return RuleResponse(
            id=item.id, version=item.version, definition=payload.definition
        )

    async def plans(self) -> list[PlanResponse]:
        manager = await self.is_manager()
        items = []
        for item in await self.repo.all(EnergyEntryPlan):
            definition = EntryPlanDefinition.model_validate(item.definition)
            if manager or self.actor_id in definition.owner_ids:
                items.append(
                    PlanResponse(
                        id=item.id, version=item.version, definition=definition
                    )
                )
        return items

    async def save_plan(
        self, payload: PlanWrite, record_id: UUID | None = None
    ) -> PlanResponse:
        await self.require_manager()
        await self.repo.serialize_write()
        from app.platform.identity.public_api import list_active_user_options

        owners = {person.id for person in await list_active_user_options(self.db)}
        if not set(payload.definition.owner_ids).issubset(owners):
            raise AppException(422, "责任人不存在或已停用")
        for point_id in payload.definition.point_ids:
            await self.repo.get(EnergyMeterPoint, point_id)
        for other in await self.repo.all(EnergyEntryPlan):
            definition = EntryPlanDefinition.model_validate(other.definition)
            if (
                other.id != record_id
                and definition.enabled
                and payload.definition.enabled
                and set(definition.point_ids) & set(payload.definition.point_ids)
            ):
                raise AppException(409, "计量点已分配给其他启用的填报计划")
        item = (
            await self.repo.get(EnergyEntryPlan, record_id)
            if record_id
            else EnergyEntryPlan(id=uuid4(), version=0, created_by=self.actor_id)
        )
        if item.version != payload.version:
            raise AppException(409, "填报计划版本已变更")
        item.version += 1
        item.definition = json_payload(payload.definition)
        item.updated_by = self.actor_id
        self.db.add(item)
        self.revision("plan", item, item.version, item.definition, payload.reason)
        await self.db.flush()
        return PlanResponse(
            id=item.id, version=item.version, definition=payload.definition
        )

    async def generate_tasks(
        self, day: date, *, scheduled: bool = False, publish_clock: str | None = None
    ) -> list[EnergyEntryTask]:
        if not scheduled:
            await self.require_manager()
        await self.repo.serialize_write()
        tasks: list[EnergyEntryTask] = []
        dated_points, _ = await self.definitions_on(day)
        previous_points, _ = await self.definitions_on(day - timedelta(days=1))
        points = {
            item[0]: item[2]
            for item in [*previous_points.values(), *dated_points.values()]
        }
        created_days: set[date] = set()
        for plan in await self.repo.all(EnergyEntryPlan):
            definition = EntryPlanDefinition.model_validate(plan.definition)
            if not definition.enabled:
                continue
            if scheduled and publish_clock and definition.publish_time > publish_clock:
                continue
            existing = await self.repo.task_for(plan.id, day)
            if existing:
                tasks.append(existing)
                continue
            due = [
                (point_id, points[point_id])
                for point_id in definition.point_ids
                if point_id in points
                and manual_input_allowed(
                    points[point_id].source_sheet,
                    points[point_id].name,
                    points[point_id].reading_type,
                    points[point_id].category,
                )
                and (
                    active_on(
                        points[point_id],
                        day - timedelta(days=1)
                        if points[point_id].reading_type == "direct"
                        else day,
                    )
                    or (
                        points[point_id].reading_type == "counter"
                        and active_on(points[point_id], day - timedelta(days=1))
                    )
                )
                and (points[point_id].frequency == "daily" or day.day == 1)
            ]
            if not due:
                continue
            await self.repo.assert_unlocked({day, day - timedelta(days=1)})
            task = EnergyEntryTask(
                id=uuid4(),
                plan_id=plan.id,
                task_date=day,
                definition={**json_payload(definition), "plan_version": plan.version},
                created_by=self.actor_id,
            )
            self.db.add(task)
            for point_id, point in due:
                reading_day = (
                    day - timedelta(days=1) if point.reading_type == "direct" else day
                )
                created_days.update(affected_dates(reading_day, point))
                self.db.add(
                    EnergyReading(
                        id=uuid4(),
                        point_id=point_id,
                        task_id=task.id,
                        reading_date=reading_day,
                        version=0,
                        exception={},
                        source="platform",
                        created_by=self.actor_id,
                    )
                )
            tasks.append(task)
        await self.db.flush()
        if created_days:
            await self.rebuild(created_days)
        from app.modules.energy.ledger_notifications import enqueue_task_notifications

        for task in tasks:
            await enqueue_task_notifications(self.db, task, "initial")
        return tasks

    async def task(self, task_id: UUID) -> TaskResponse:
        task = await self.repo.get(EnergyEntryTask, task_id)
        plan = EntryPlanDefinition.model_validate(
            {
                key: value
                for key, value in task.definition.items()
                if key != "plan_version"
            }
        )
        # Current assignment revokes former owners' write/read capability immediately.
        current = EntryPlanDefinition.model_validate(
            (await self.repo.get(EnergyEntryPlan, task.plan_id)).definition
        )
        if not await self.is_manager() and self.actor_id not in current.owner_ids:
            raise AppException(403, "当前任务未分配给您")
        items: list[EntryItemResponse] = []
        for reading in await self.repo.task_readings(task_id):
            point = MeterDefinition.model_validate(
                (await self.repo.get(EnergyMeterPoint, reading.point_id)).definition
            )
            previous = await self.db.scalar(
                select(EnergyReading)
                .where(
                    EnergyReading.point_id == reading.point_id,
                    EnergyReading.reading_date < reading.reading_date,
                    EnergyReading.value.is_not(None),
                )
                .order_by(EnergyReading.reading_date.desc())
                .limit(1)
            )
            estimate = None
            if reading.draft_value is not None:
                if point.reading_type == "direct":
                    estimate = reading.draft_value * point.multiplier
                elif (
                    previous
                    and previous.value is not None
                    and previous.reading_date
                    == reading.reading_date - timedelta(days=1)
                    and reading.draft_value >= previous.value
                ):
                    estimate = (reading.draft_value - previous.value) * point.multiplier
            items.append(
                EntryItemResponse(
                    id=reading.id,
                    point_id=reading.point_id,
                    name=point.name,
                    category=point.category,
                    unit=point.unit,
                    precision=point.precision,
                    multiplier=point.multiplier,
                    reading_type=point.reading_type,
                    frequency=point.frequency,
                    reading_date=reading.reading_date,
                    value=reading.value,
                    draft_value=reading.draft_value,
                    previous_value=previous.value if previous else None,
                    previous_date=previous.reading_date if previous else None,
                    version=reading.version,
                    submitted_at=reading.submitted_at,
                    estimated_usage=estimate,
                    exception=ReadingException.model_validate(reading.exception)
                    if reading.exception
                    else None,
                )
            )
        return TaskResponse(
            id=task.id,
            task_date=task.task_date,
            name=plan.name,
            owner_ids=current.owner_ids,
            deadline_time=plan.deadline_time,
            total_count=len(items),
            completed_count=sum(item.value is not None for item in items),
            items=items,
        )

    async def tasks(
        self,
        start: date,
        end: date,
        page: int = 1,
        page_size: int = 30,
        mine: bool = False,
    ) -> tuple[list[TaskResponse], int]:
        self.validate_range(start, end)
        query = select(EnergyEntryTask).where(
            EnergyEntryTask.task_date.between(start, end)
        )
        if not await self.is_manager() or mine:
            owned = [
                plan.id
                for plan in await self.repo.all(EnergyEntryPlan)
                if self.actor_id
                in EntryPlanDefinition.model_validate(plan.definition).owner_ids
            ]
            query = query.where(EnergyEntryTask.plan_id.in_(owned))
        from sqlalchemy import func

        count = (
            await self.db.scalar(select(func.count()).select_from(query.subquery()))
            or 0
        )
        items = (
            await self.db.scalars(
                query.order_by(EnergyEntryTask.task_date.desc(), EnergyEntryTask.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return [await self.task(item.id) for item in items], count

    async def submit(
        self, task_id: UUID, payload: EntrySubmission, *, imported: bool = False
    ) -> TaskResponse:
        if imported:
            await self.require_manager()
        source = "import" if imported else payload.source
        await self.repo.serialize_write()
        await self.task(task_id)
        readings = {item.id: item for item in await self.repo.task_readings(task_id)}
        if all(
            entry.reading_id in readings
            and readings[entry.reading_id].version == entry.version + 1
            and readings[entry.reading_id].updated_by == self.actor_id
            and (
                readings[entry.reading_id].draft_value
                if payload.draft
                else readings[entry.reading_id].value
            )
            == entry.value
            and (
                entry.exception is None
                or readings[entry.reading_id].exception == json_payload(entry.exception)
            )
            for entry in payload.values
        ):
            return await self.task(task_id)
        days: set[date] = set()
        for entry in payload.values:
            reading = readings.get(entry.reading_id)
            if reading is None:
                raise AppException(403, "填写项不属于当前任务")
            if entry.version != reading.version:
                raise AppException(409, "数据已被其他人修改，请刷新后重新核对")
            point = MeterDefinition.model_validate(
                (await self.repo.get(EnergyMeterPoint, reading.point_id)).definition
            )
            if not manual_input_allowed(
                point.source_sheet, point.name, point.reading_type, point.category
            ):
                raise AppException(
                    422, "原始来源或计量口径配置冲突，自动计算字段不能人工填写"
                )
            if entry.value != entry.value.quantize(Decimal(1).scaleb(-point.precision)):
                raise AppException(
                    422, f"{point.name} 最多保留 {point.precision} 位小数"
                )
            if reading.value is not None and not payload.draft and not payload.reason:
                raise AppException(422, "更正已生效数据必须填写原因")
            if entry.exception and not await self.is_manager():
                raise AppException(403, "换表、复位或回绕记录须由能源管理员填写")
            days.update(affected_dates(reading.reading_date, point))
        await self.repo.assert_unlocked(days)
        for entry in payload.values:
            reading = readings[entry.reading_id]
            previous: dict[str, JsonValue] = {
                "value": str(reading.value) if reading.value is not None else None,
                "version": reading.version,
            }
            reading.version += 1
            reading.updated_by = self.actor_id
            reading.draft_value = entry.value if payload.draft else None
            if not payload.draft:
                reading.value = entry.value
                reading.submitted_at = datetime.now(UTC)
                reading.source = source
                reading.exception = (
                    json_payload(entry.exception)
                    if entry.exception
                    else reading.exception
                )
            self.revision(
                "reading",
                reading,
                reading.version,
                {
                    "before": previous,
                    "value": str(entry.value),
                    "draft": payload.draft,
                    "source": source,
                    "exception": reading.exception,
                },
                payload.reason,
            )
        await self.db.flush()
        if not payload.draft:
            await self.rebuild(days)
            from app.modules.energy.ledger_notifications import (
                enqueue_task_notifications,
            )

            await enqueue_task_notifications(
                self.db,
                await self.repo.get(EnergyEntryTask, task_id),
                "progress:"
                + str(
                    uuid5(
                        NAMESPACE_URL,
                        ":".join(
                            f"{item.reading_id}-{readings[item.reading_id].version}"
                            for item in payload.values
                        ),
                    )
                ),
            )
        return await self.task(task_id)

    async def definitions_on(
        self, day: date
    ) -> tuple[
        dict[str, tuple[UUID, int, MeterDefinition]],
        dict[str, tuple[int, RuleDefinition]],
    ]:
        points: dict[str, tuple[UUID, int, MeterDefinition]] = {}
        rules: dict[str, tuple[int, RuleDefinition]] = {}
        history = list(
            (
                await self.db.scalars(
                    select(EnergyLedgerRevision)
                    .where(EnergyLedgerRevision.entity_kind.in_(["meter", "rule"]))
                    .order_by(EnergyLedgerRevision.version)
                )
            ).all()
        )
        for revision in history:
            if revision.entity_kind == "meter":
                point = MeterDefinition.model_validate(revision.payload)
                key = "point:" + point.code
                if point.active_from <= day and (
                    key not in points
                    or (point.active_from, revision.version)
                    >= (points[key][2].active_from, points[key][1])
                ):
                    points[key] = (revision.entity_id, revision.version, point)
            else:
                rule = RuleDefinition.model_validate(revision.payload)
                key = "rule:" + rule.code
                if rule.active_from <= day and (
                    key not in rules
                    or (rule.active_from, revision.version)
                    >= (rules[key][1].active_from, rules[key][0])
                ):
                    rules[key] = (revision.version, rule)
        return points, rules

    async def evaluate(
        self, day: date
    ) -> list[tuple[str, MeterDefinition | RuleDefinition, Calculation]]:
        points, rules = await self.definitions_on(day)
        ids = [item[0] for item in points.values()]
        reading_rows = (
            await self.db.scalars(
                select(EnergyReading).where(
                    EnergyReading.point_id.in_(ids),
                    EnergyReading.reading_date.between(
                        day.replace(day=1), next_month(day)
                    ),
                    EnergyReading.value.is_not(None),
                )
            )
        ).all()
        observations: dict[UUID, dict[date, Observation]] = defaultdict(dict)
        tasks = {
            task.id: task
            for task in (
                await self.db.scalars(
                    select(EnergyEntryTask).where(
                        EnergyEntryTask.id.in_({row.task_id for row in reading_rows})
                    )
                )
            ).all()
        }
        for row in reading_rows:
            if row.value is not None:
                task = tasks.get(row.task_id)
                deadline = (
                    datetime.combine(
                        task.task_date,
                        time.fromisoformat(str(task.definition["deadline_time"])),
                        tzinfo=ZoneInfo("Asia/Shanghai"),
                    )
                    if task
                    else None
                )
                observations[row.point_id][row.reading_date] = Observation(
                    row.value,
                    row.version,
                    row.exception,
                    # Import time does not establish when historical staff
                    # actually took or submitted the original reading.
                    bool(
                        row.source != "import"
                        and deadline
                        and row.submitted_at
                        and row.submitted_at > deadline
                    ),
                )
        calculated: dict[str, Calculation] = {}
        outputs: list[tuple[str, MeterDefinition | RuleDefinition, Calculation]] = []
        adjustments = await self.adjustments_on(day)

        def effective(key: str, result: Calculation) -> Calculation:
            adjustment = adjustments.get(key)
            if adjustment is None:
                return result
            value = (
                adjustment.value
                if adjustment.mode == "override"
                else (
                    result.value + adjustment.value
                    if result.value is not None
                    else None
                )
            )
            return Calculation(
                value,
                "adjusted" if value is not None else result.status,
                {
                    **result.provenance,
                    "adjustment": {
                        "id": str(adjustment.id),
                        "mode": adjustment.mode,
                        "value": str(adjustment.value),
                        "reason": adjustment.reason,
                    },
                },
            )

        for key, (point_id, version, point) in points.items():
            result = calculate_point(point, day, observations[point_id])
            if result is not None:
                result.provenance["configuration_version"] = version
                calculated[key] = effective(key, result)
                outputs.append((key, point, result))
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
        for key in order:
            version, rule = rules[key]
            if active_on(rule, day) and (
                rule.frequency == "daily"
                or day.day == monthrange(day.year, day.month)[1]
            ):
                result = calculate_rule(rule, calculated)
                result.provenance["configuration_version"] = version
                result.provenance["source_details"] = [
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
                calculated[key] = effective(key, result)
                outputs.append((key, rule, result))
        return outputs

    async def adjustments_on(self, day: date) -> dict[str, EnergyAdjustment]:
        records = await self.db.scalars(
            select(EnergyAdjustment)
            .where(
                EnergyAdjustment.usage_date == day,
                EnergyAdjustment.is_deleted.is_(False),
            )
            .order_by(EnergyAdjustment.created_at.desc(), EnergyAdjustment.id.desc())
        )
        latest: dict[str, EnergyAdjustment] = {}
        for item in records:
            latest.setdefault(item.metric_key, item)
        return latest

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
        await self.repo.assert_unlocked(days)
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
            adjustments = await self.adjustments_on(day)
            for key, definition, result in outputs:
                active_keys.add(key)
                item = existing.get(key) or EnergyUsageFact(
                    id=uuid4(), metric_key=key, usage_date=day, created_by=self.actor_id
                )
                adjustment = adjustments.get(key)
                item.calculated_value = result.value
                item.effective_value = result.value
                item.status = result.status
                item.definition = json_payload(definition)
                item.provenance = result.provenance
                item.is_deleted = False
                if adjustment:
                    item.effective_value = (
                        adjustment.value
                        if adjustment.mode == "override"
                        else (
                            result.value + adjustment.value
                            if result.value is not None
                            else None
                        )
                    )
                    item.status = (
                        "adjusted"
                        if item.effective_value is not None
                        else result.status
                    )
                    item.provenance = {
                        **result.provenance,
                        "adjustment": {
                            "id": str(adjustment.id),
                            "mode": adjustment.mode,
                            "value": str(adjustment.value),
                            "reason": adjustment.reason,
                        },
                    }
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
        page: int = 1,
        page_size: int = 100,
        include_all: bool = False,
    ) -> ReportResponse:
        self.validate_range(start, end)
        scope = await self.scope()
        query = select(EnergyUsageFact).where(
            EnergyUsageFact.usage_date.between(start, end),
            EnergyUsageFact.is_deleted.is_(False),
        )
        if not scope.is_all:
            query = query.where(
                EnergyUsageFact.definition["department"].astext.in_(
                    scope.department_names
                )
            )
        if metric_key:
            query = query.where(EnergyUsageFact.metric_key == metric_key)
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
        seen = {(row.metric_key, row.usage_date) for row in rows}
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            points, rules = await self.definitions_on(day)
            definitions: dict[str, MeterDefinition | RuleDefinition] = {
                **{key: item[2] for key, item in points.items()},
                **{key: item[1] for key, item in rules.items()},
            }
            for key, definition in definitions.items():
                if (
                    (key, day) in seen
                    or not active_on(definition, day)
                    or not scope.allows(definition.department)
                ):
                    continue
                if (
                    definition.frequency == "monthly"
                    and day.day != monthrange(day.year, day.month)[1]
                ):
                    continue
                if metric_key and key != metric_key:
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
                        if item.effective_value is not None
                    ),
                    Decimal(0),
                )
                if any(item.effective_value is not None for item in items)
                else None,
                expected_count=len(items),
                available_count=sum(usable_usage(item) for item in items),
            )
            for key, items in groups.items()
        ]
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
                if item.effective_value is not None
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
                    terms = row.provenance.get("terms")
                    if not isinstance(terms, list) or len(terms) != 2:
                        usable = False
                        break
                    components: list[Decimal] = []
                    for term in terms:
                        if not isinstance(term, dict):
                            usable = False
                            break
                        fact = await self.db.scalar(
                            select(EnergyUsageFact).where(
                                EnergyUsageFact.metric_key == str(term["metric_key"]),
                                EnergyUsageFact.usage_date == row.usage_date,
                                EnergyUsageFact.is_deleted.is_(False),
                            )
                        )
                        if (
                            fact is None
                            or fact.effective_value is None
                            or not scope.allows(str(fact.definition["department"]))
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
                    else "zero_denominator"
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
            if all(usable_usage(row) for row in rows if row.usage_date == day)
        ]
        missing = sum(row.effective_value is None for row in rows)
        invalid = sum(not usable_usage(row) for row in rows)
        # Task progress uses assignment scope; never disclose other departments' work.
        task_query = (
            select(EnergyReading)
            .join(EnergyMeterPoint, EnergyMeterPoint.id == EnergyReading.point_id)
            .where(EnergyReading.reading_date.between(start, end))
        )
        if not scope.is_all:
            task_query = task_query.where(
                EnergyMeterPoint.definition["department"].astext.in_(
                    scope.department_names
                )
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
        )

    async def trace(self, fact_id: UUID) -> UsageRow:
        item = await self.repo.get(EnergyUsageFact, fact_id)
        if not (await self.scope()).allows(str(item.definition["department"])):
            raise AppException(403, "无权查看该计量范围")
        return self.usage_row(item)

    async def adjust(self, payload: AdjustmentWrite) -> UsageRow:
        await self.require_manager()
        await self.repo.serialize_write()
        await self.repo.assert_unlocked({payload.usage_date})
        fact = await self.db.scalar(
            select(EnergyUsageFact).where(
                EnergyUsageFact.metric_key == payload.metric_key,
                EnergyUsageFact.usage_date == payload.usage_date,
                EnergyUsageFact.is_deleted.is_(False),
            )
        )
        if fact is None:
            raise AppException(404, "待调整的用量结果不存在")
        if payload.mode == "delta" and fact.calculated_value is None:
            raise AppException(422, "原计算值缺失，不能执行增减量调整")
        proposed = (
            payload.value
            if payload.mode == "override"
            else (fact.calculated_value or Decimal(0)) + payload.value
        )
        if abs(proposed) >= Decimal("1e20"):
            raise AppException(422, "调整后的用量超出计量范围")
        if proposed < 0 and fact.definition.get("report_scope") != "check":
            raise AppException(422, "实际用量不能调整为负数，差值请使用核对指标")
        old = (
            await self.db.scalars(
                select(EnergyAdjustment).where(
                    EnergyAdjustment.metric_key == payload.metric_key,
                    EnergyAdjustment.usage_date == payload.usage_date,
                    EnergyAdjustment.is_deleted.is_(False),
                )
            )
        ).all()
        for item in old:
            item.is_deleted = True
        adjustment = EnergyAdjustment(
            id=uuid4(),
            **payload.model_dump(),
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(adjustment)
        self.revision(
            "adjustment", adjustment, 1, json_payload(payload), payload.reason
        )
        await self.db.flush()
        await self.rebuild({payload.usage_date})
        return self.usage_row(fact)

    async def locks(self) -> list[LockResponse]:
        await self.require_manager()
        return [
            LockResponse(month=item.month, locked=item.locked, version=item.version)
            for item in await self.repo.all(EnergyPeriodLock)
        ]

    async def set_lock(self, month: str, payload: LockWrite) -> LockResponse:
        await self.require_manager()
        await self.repo.serialize_write()
        try:
            start = date.fromisoformat(month + "-01")
        except ValueError as exc:
            raise AppException(422, "月份格式应为 YYYY-MM") from exc
        item = await self.repo.month_lock(month)
        if item.version != payload.version:
            raise AppException(409, "封账版本已变更")
        if payload.locked:
            end = next_month(start) - timedelta(days=1)
            if end >= datetime.now(ZoneInfo("Asia/Shanghai")).date():
                raise AppException(409, "月份尚未结束，不能封账")
            await self.rebuild(
                {start + timedelta(days=i) for i in range((end - start).days + 1)}
            )
            report = await self.report(start, end, report_scope="all", include_all=True)
            if report.status != "complete":
                raise AppException(
                    409, "该月存在缺失用量，补齐或通过有依据的调整处理后才能封账"
                )
            item.snapshot = [json_payload(row) for row in report.rows]
        item.locked = payload.locked
        item.version += 1
        item.updated_by = self.actor_id
        self.revision(
            "period",
            item,
            item.version,
            {
                "month": month,
                "locked": item.locked,
                "snapshot_count": len(item.snapshot),
            },
            payload.reason,
        )
        await self.db.flush()
        return LockResponse(month=month, locked=item.locked, version=item.version)

    async def history(self, kind: str, entity_id: UUID) -> list[RevisionResponse]:
        if kind == "reading":
            reading = await self.repo.get(EnergyReading, entity_id)
            await self.task(reading.task_id)
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
