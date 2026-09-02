from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import DuplicateException, NotFoundException
from app.modules.hr import service as hr_service

SimpleNamespace: Any = _SimpleNamespace


class Dump:
    def __init__(self: Any, **values: Any) -> None:
        self.values = values
        for key, value in values.items():
            setattr(self, key, value)

    def model_dump(self: Any, **kwargs: Any) -> Any:
        excluded = kwargs.get("exclude", set())
        return {key: value for key, value in self.values.items() if key not in excluded}


def _bare(service_type: Any, **dependencies: Any) -> Any:
    service = service_type.__new__(service_type)
    for name, dependency in dependencies.items():
        setattr(service, name, dependency)
    return service


def _employee(**overrides: Any) -> Any:
    values = {
        "id": uuid4(),
        "employee_number": "E001",
        "name": "张三",
        "department": "生产部",
        "sub_department": None,
        "position": "操作员",
        "hire_date": date(2025, 1, 1),
        "status": "在职",
        "phone": None,
        "feishu_open_id": None,
        "feishu_record_id": None,
        "created_at": datetime.utcnow(),
    }
    for field in (
        "email",
        "gender",
        "native_place",
        "political_status",
        "marital_status",
        "education",
        "classification",
        "major",
        "id_card",
        "bank_account",
        "training_id",
        "domain_account",
        "team",
        "job_category",
        "level",
        "qualification_type",
        "household_type",
        "status_category",
        "id_card_expiry",
        "contract_type",
        "id_card_address",
        "current_address",
        "emergency_contact_phone",
        "emergency_contact_relation",
        "transfer_history",
        "qualifications",
        "remarks",
        "work_start_date",
        "factory_entry_date",
        "livo_entry_date",
        "graduation_date",
        "contract_start_date",
        "contract_end_date",
        "contract_start_2",
        "contract_end_2",
        "contract_start_3",
        "contract_end_3",
        "contract_start_4",
        "contract_end_4",
        "birth_year",
        "birth_month",
        "birth_day",
    ):
        values[field] = None
    values.update(overrides)
    return SimpleNamespace(**values)


def test_hr_feishu_parsers_cover_types_dates_and_cleanup() -> Any:
    assert hr_service._extract_text([{"text": "A"}]) == "A"
    assert hr_service._extract_text({"text": "B"}) == "B"
    assert hr_service._extract_text({"value": [{"text": "C"}]}) == "C"
    assert hr_service._extract_text(None) == ""
    assert hr_service._extract_text(12) == "12"
    assert hr_service._extract_number(2.9) == 2
    assert hr_service._extract_number({"value": ["3"]}) == 3
    assert hr_service._extract_number("3") is None
    assert hr_service._ms_to_date(0) is None
    assert hr_service._ms_to_date(1_700_000_000_000) is not None

    record = {
        "record_id": "rec-1",
        "updated_time": "2026-01-01T00:00:00Z",
        "fields": {
            "工号": [{"text": "E001"}],
            "姓名": {"text": "张三"},
            "部门": "生产部",
            "职位": "操作员",
            "职称／职业资格": ["A"],
            "备注": ["B"],
            "年": 1990,
            "月": {"value": [1]},
            "日": 2,
            "进厂时间": 1_700_000_000_000,
            "手机": "13800000000",
        },
    }
    parsed = hr_service._parse_feishu_record(record)
    assert parsed["employee_number"] == "E001"
    assert parsed["hire_date"] is not None
    assert parsed["qualifications"] == ["A"]
    assert parsed["feishu_synced_at"] == date(2026, 1, 1)
    assert (
        hr_service._parse_feishu_record(
            {"record_id": "bad", "updated_time": "invalid"}
        )["feishu_synced_at"]
        is not None
    )
    assert (
        hr_service._parse_feishu_record({"record_id": "none"})["feishu_synced_at"]
        is not None
    )


@pytest.mark.asyncio
async def test_employee_crud_duplicate_and_feishu_failures(monkeypatch: Any) -> Any:
    repo: Any = AsyncMock()
    bitable: Any = AsyncMock()
    feishu: Any = AsyncMock()
    service = _bare(
        hr_service.EmployeeService, repo=repo, bitable=bitable, feishu=feishu
    )
    employee_id = uuid4()
    repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await service.get_employee(employee_id)
    repo.get_by_employee_number.return_value = None
    with pytest.raises(NotFoundException):
        await service.get_employee_by_number("missing")

    repo.get_by_employee_number.return_value = _employee()
    with pytest.raises(DuplicateException):
        await service.create_employee(
            cast(Any, Dump)(
                employee_number="E001",
                name="张三",
                department="生产部",
                sub_department=None,
                position="操作员",
                hire_date=date.today(),
                phone=None,
            )
        )

    created = _employee()
    repo.get_by_employee_number.return_value = None
    repo.create.return_value = created
    bitable.create.return_value = "rec-1"
    assert (
        await service.create_employee(
            cast(Any, Dump)(
                employee_number="E001",
                name="张三",
                department="生产部",
                sub_department=None,
                position="操作员",
                hire_date=date.today(),
                phone=None,
            )
        )
        is created
    )
    assert created.feishu_record_id == "rec-1"

    repo.get_by_id.return_value = created
    repo.get_by_employee_number.return_value = _employee(id=uuid4())
    with pytest.raises(DuplicateException):
        await service.update_employee(
            employee_id, cast(Any, Dump)(employee_number="E002")
        )

    repo.get_by_employee_number.return_value = None
    repo.update.return_value = created
    monkeypatch.setattr(
        service,
        "_sync_single_to_feishu",
        AsyncMock(side_effect=RuntimeError("offline")),
    )
    assert (
        await service.update_employee(employee_id, cast(Any, Dump)(position="主管"))
        is created
    )
    assert created.position == "主管"

    created.feishu_record_id = "rec-delete"
    bitable.delete.side_effect = RuntimeError("offline")
    await service.delete_employee(employee_id)
    repo.soft_delete.assert_awaited_once_with(created)

    created.feishu_record_id = None
    bitable.delete.side_effect = None
    feishu.sync_employee_deleted.side_effect = RuntimeError("offline")
    await service.delete_employee(employee_id)

    repo.list_employees.return_value = ([created], 1)
    assert (
        await service.list_employees(
            department="生产部",
            status="在职",
            keyword="张",
            page=2,
            page_size=5,
            sort_by="name",
            sort_order="asc",
        )
    )[1] == 1


@pytest.mark.asyncio
async def test_employee_approval_notification_and_sync_paths(monkeypatch: Any) -> Any:
    repo: Any = AsyncMock()
    bitable: Any = AsyncMock()
    service = _bare(
        hr_service.EmployeeService, repo=repo, bitable=bitable, feishu=AsyncMock()
    )
    repo.get_by_employee_number.return_value = None
    with pytest.raises(NotFoundException):
        await service.approve_employee("missing")
    repo.get_by_employee_number.return_value = _employee(status="在职")
    with pytest.raises(DuplicateException):
        await service.approve_employee("E001")

    pending = _employee(status="待审批")
    repo.get_by_employee_number.return_value = pending
    repo.update.return_value = pending
    monkeypatch.setattr(
        service,
        "_sync_single_to_feishu",
        AsyncMock(side_effect=RuntimeError("offline")),
    )
    assert await service.approve_employee("E001") is pending
    assert pending.status == "在职"

    employee_with_open_id = _employee(feishu_open_id="ou-1")
    employee_without_open_id = _employee(
        employee_number="E002", name="李四", feishu_open_id=None
    )
    repo.get_by_employee_number.side_effect = [
        employee_with_open_id,
        employee_without_open_id,
        None,
    ]
    im: Any = AsyncMock()
    im.send_text_message.side_effect = RuntimeError("send failed")
    import app.modules.hr.feishu.im as im_module

    # notify_training 现按 HR 专属应用凭证构造 FeishuIM（需 session + 凭据 helper）
    monkeypatch.setattr(im_module, "FeishuIM", lambda *creds: im)
    monkeypatch.setattr(
        hr_service,
        "get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_app", "hr_secret")),
    )
    service.session = AsyncMock()
    result = await service.notify_training(
        cast(Any, Dump)(
            employee_numbers=["E001", "E002", "E003"],
            subject="GMP",
            training_date=date(2026, 1, 1),
            training_time_start="09:00",
            training_time_end="10:00",
            location=None,
            trainer=None,
            content="内容",
        )
    )
    # sync_from_feishu 的 legacy bitable 分支以“无 session”为路由条件
    del service.session
    assert result["sent"] == 0
    assert result["failed"] == 3
    assert {item["reason"] for item in result["details"]} >= {
        "send failed",
        "数据库中缺少 feishu_open_id，请先同步",
        "未找到员工",
    }

    now = datetime.utcnow()
    bitable.client.search_records.return_value = [
        {"record_id": "blank", "fields": {}},
        {"record_id": "new", "fields": {"工号": "E001"}},
        {"record_id": "old", "fields": {"工号": "E002"}},
        {"record_id": "bad", "fields": {"工号": "E003"}},
    ]
    repo.get_by_employee_number.side_effect = [
        _employee(created_at=now),
        _employee(created_at=now - timedelta(days=1)),
        RuntimeError("db"),
    ]
    stats = await service.sync_from_feishu()
    assert stats == {"created": 1, "updated": 1, "failed": 2, "total": 4}

    repo.count_total.return_value = 5
    repo.count_synced.return_value = 3
    status = await service.get_sync_status()
    assert (status.local_total, status.feishu_total, status.unsynced_count) == (5, 3, 2)


@pytest.mark.asyncio
async def test_employee_bitable_mapping_and_create_update_sync(monkeypatch: Any) -> Any:
    repo: Any = AsyncMock()
    bitable: Any = AsyncMock()
    service = _bare(
        hr_service.EmployeeService, repo=repo, bitable=bitable, feishu=AsyncMock()
    )
    all_dates = date(2026, 1, 1)
    employee = _employee(
        qualifications=["GMP"],
        remarks=["备注"],
        work_start_date=all_dates,
        factory_entry_date=all_dates,
        livo_entry_date=all_dates,
        graduation_date=all_dates,
        contract_start_date=all_dates,
        contract_end_date=all_dates,
        contract_start_2=all_dates,
        contract_end_2=all_dates,
        contract_start_3=all_dates,
        contract_end_3=all_dates,
        contract_start_4=all_dates,
        contract_end_4=all_dates,
        birth_year=1990,
        birth_month=1,
        birth_day=2,
    )
    fields = service._to_bitable_fields(employee)
    assert fields["工号"] == "E001"
    assert fields["职称／职业资格"] == ["GMP"]
    assert fields["第一次合同起点时间"] > 0
    assert fields["年"] == 1990

    employee.feishu_record_id = "rec-1"
    assert await service._sync_single_to_feishu(employee) == "rec-1"
    bitable.update.assert_awaited_once()

    employee.feishu_record_id = None
    bitable.create.return_value = "rec-2"
    assert await service._sync_single_to_feishu(employee) == "rec-2"
    repo.update.assert_awaited()


@pytest.mark.asyncio
async def test_department_team_and_offboarding_transaction_boundaries() -> Any:
    department_id = uuid4()
    department: Any = SimpleNamespace(id=department_id, code="D1", name="生产部")

    department_repo: Any = AsyncMock()
    department_feishu: Any = AsyncMock()
    department_service = _bare(
        hr_service.DepartmentService,
        repo=department_repo,
        feishu=department_feishu,
    )
    department_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await department_service.get_department(department_id)
    department_repo.get_by_code.return_value = department
    with pytest.raises(DuplicateException):
        await department_service.create_department(
            cast(Any, Dump)(code="D1", name="生产部")
        )

    department_repo.get_by_code.return_value = None
    department_repo.create.return_value = department
    department_feishu.sync_department_created.side_effect = RuntimeError("offline")
    assert (
        await department_service.create_department(
            cast(Any, Dump)(code="D1", name="生产部")
        )
        is department
    )

    department_repo.get_by_id.return_value = department
    department_repo.get_by_code.return_value = SimpleNamespace(id=uuid4())
    with pytest.raises(DuplicateException):
        await department_service.update_department(
            department_id, cast(Any, Dump)(code="D2")
        )
    department_repo.get_by_code.return_value = None
    department_repo.update.return_value = department
    department_feishu.sync_department_updated.side_effect = RuntimeError("offline")
    assert (
        await department_service.update_department(
            department_id, cast(Any, Dump)(name="质量部")
        )
        is department
    )
    department_feishu.sync_department_deleted.side_effect = RuntimeError("offline")
    await department_service.delete_department(department_id)
    department_repo.soft_delete.assert_awaited()
    department_repo.list_departments.return_value = ([department], 1)
    assert (
        await department_service.list_departments(keyword="部", page=2, page_size=3)
    )[1] == 1

    team_repo: Any = AsyncMock()
    team_service = _bare(
        hr_service.TeamService,
        repo=team_repo,
        department_repo=department_repo,
    )
    team_id = uuid4()
    team: Any = SimpleNamespace(id=team_id, department_id=department_id)
    team_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await team_service.get_team(team_id)
    department_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await team_service.create_team(
            cast(Any, Dump)(name="一班", department_id=department_id)
        )
    department_repo.get_by_id.return_value = department
    team_repo.create.return_value = team
    assert (
        await team_service.create_team(
            cast(Any, Dump)(name="一班", department_id=department_id)
        )
        is team
    )
    team_repo.get_by_id.return_value = team
    department_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await team_service.update_team(team_id, cast(Any, Dump)(department_id=uuid4()))
    team_repo.update.return_value = team
    assert await team_service.update_team(team_id, cast(Any, Dump)(name="二班")) is team
    await team_service.delete_team(team_id)
    team_repo.list_teams.return_value = ([team], 1)
    assert (
        await team_service.list_teams(
            department_id=department_id, keyword="班", page=1, page_size=10
        )
    )[1] == 1

    off_repo: Any = AsyncMock()
    employee_repo: Any = AsyncMock()
    off_feishu: Any = AsyncMock()
    off_service = _bare(
        hr_service.OffboardingRecordService,
        repo=off_repo,
        employee_repo=employee_repo,
        feishu=off_feishu,
    )
    record_id = uuid4()
    off_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await off_service.get_record(record_id)
    employee_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await off_service.create_record(
            cast(Any, Dump)(employee_id=uuid4(), offboarding_date=date.today())
        )
    employee = _employee()
    record: Any = SimpleNamespace(id=record_id, employee_id=employee.id)
    employee_repo.get_by_id.return_value = employee
    off_repo.create.return_value = record
    off_feishu.sync_offboarding_created.side_effect = RuntimeError("offline")
    assert (
        await off_service.create_record(
            cast(Any, Dump)(employee_id=employee.id, offboarding_date=date.today())
        )
        is record
    )
    assert employee.status == "离职"
    off_repo.get_by_id.return_value = record
    off_repo.update.return_value = record
    off_feishu.sync_offboarding_updated.side_effect = RuntimeError("offline")
    assert (
        await off_service.update_record(record_id, cast(Any, Dump)(reason="个人原因"))
        is record
    )
    await off_service.delete_record(record_id)
    off_repo.list_records.return_value = ([record], 1)
    assert (
        await off_service.list_records(
            employee_id=employee.id, keyword="个人", page=1, page_size=5
        )
    )[1] == 1


@pytest.mark.asyncio
async def test_onboarding_and_departure_sync_boundaries(monkeypatch: Any) -> Any:
    now = datetime.utcnow()
    for service_type, datasource_module_name in (
        (hr_service.OnboardingRecordService, "onboarding_datasource"),
        (hr_service.DepartureRecordService, "departure_datasource"),
    ):
        repo: Any = AsyncMock()
        bitable: Any = AsyncMock()
        service = _bare(service_type, repo=repo, bitable=bitable)
        record_id = uuid4()
        repo.get_by_id.return_value = None
        with pytest.raises(NotFoundException):
            await service.get_record(record_id)

        raw = [
            {"record_id": "missing-id"},
            {"record_id": "new"},
            {"record_id": "old"},
            {"record_id": "bad"},
        ]
        bitable.client.search_records.return_value = raw
        values = iter(
            [
                {"feishu_record_id": None},
                {
                    "feishu_record_id": "new",
                    "name": "N",
                    "department": "D",
                    "hire_date": date.today(),
                },
                {
                    "feishu_record_id": "old",
                    "name": "N",
                    "department": "D",
                    "hire_date": date.today(),
                },
            ]
        )

        class Parsed:
            @classmethod
            def from_api(cls: Any, item: Any) -> Any:
                if item["record_id"] == "bad":
                    raise ValueError("bad")
                return SimpleNamespace(to_dict=lambda: next(values))

        module = __import__(
            f"app.modules.hr.feishu.{datasource_module_name}",
            fromlist=["placeholder"],
        )
        target = (
            "OnboardingRecord"
            if service_type is hr_service.OnboardingRecordService
            else "DepartureRecord"
        )
        monkeypatch.setattr(module, target, Parsed)
        repo.get_by_feishu_record_id.side_effect = [
            SimpleNamespace(created_at=now),
            SimpleNamespace(created_at=now - timedelta(days=1)),
        ]
        stats = await service.sync_from_feishu()
        assert stats["created"] == 1
        assert stats["updated"] == 1
        assert stats["failed"] == 2

        repo.count_total.return_value = 6
        repo.count_synced.return_value = 4
        status = await service.get_sync_status()
        assert status.unsynced_count == 2


@pytest.mark.asyncio
async def test_departure_training_pages_and_annual_plan_boundaries() -> Any:
    record_id = uuid4()
    record: Any = SimpleNamespace(id=record_id)
    repo: Any = AsyncMock()
    departure = _bare(hr_service.DepartureRecordService, repo=repo, bitable=AsyncMock())
    repo.get_by_id.return_value = record
    repo.create.return_value = record
    repo.update.return_value = record
    assert await departure.create_record(cast(Any, Dump)(name="张三")) is record
    assert (
        await departure.update_record(record_id, cast(Any, Dump)(reason="原因"))
        is record
    )
    await departure.delete_record(record_id)
    repo.list_records.return_value = ([record], 1)
    assert (
        await departure.list_records(
            department="D",
            offboarding_type="辞职",
            keyword="张",
            page=1,
            page_size=5,
        )
    )[1] == 1

    ledger_repo: Any = AsyncMock()
    ledger = _bare(hr_service.TrainingLedgerService, repo=ledger_repo)
    ledger_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await ledger.get_record(record_id)
    ledger_repo.create.return_value = record
    assert await ledger.create_record(cast(Any, Dump)(employee_number="E1")) is record
    ledger_repo.get_by_id.return_value = record
    ledger_repo.update.return_value = record
    assert await ledger.update_record(record_id, cast(Any, Dump)(trainer="T")) is record
    await ledger.delete_record(record_id)
    ledger_repo.list_records.return_value = ([record], 1)
    assert (
        await ledger.list_records(
            employee_number="E1",
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 2),
            page=1,
            page_size=10,
        )
    )[1] == 1
    ledger_repo.get_by_source.return_value = record
    assert (
        await ledger.create_from_notification(
            employee_number="E1",
            training_date=date.today(),
            training_subject="GMP",
            training_method=None,
            trainer=None,
            source_id="source",
        )
        is record
    )
    ledger_repo.get_by_source.return_value = None
    assert (
        await ledger.create_from_notification(
            employee_number="E1",
            training_date=date.today(),
            training_subject="GMP",
            training_method=None,
            trainer=None,
        )
        is record
    )

    page_repo: Any = AsyncMock()
    page_service = _bare(hr_service.TrainingLedgerPageService, repo=page_repo)
    page_repo.list_pages.return_value = [record]
    page_repo.list_pages_with_department.return_value = [(record, "D")]
    assert await page_service.list_pages() == [record]
    assert await page_service.list_pages_with_department() == [(record, "D")]
    page_repo.get_by_employee_number.return_value = record
    with pytest.raises(DuplicateException):
        await page_service.create_page(cast(Any, Dump)(employee_number="E1"))
    page_repo.get_by_employee_number.return_value = None
    page_repo.create.return_value = record
    assert (
        await page_service.create_page(cast(Any, Dump)(employee_number="E1")) is record
    )

    plan_id = uuid4()
    plan: Any = SimpleNamespace(id=plan_id, name="P")
    plan_repo: Any = AsyncMock()
    item_repo: Any = AsyncMock()
    plan_service = _bare(
        hr_service.AnnualTrainingPlanService,
        repo=plan_repo,
        item_repo=item_repo,
    )
    plan_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await plan_service.get_plan(plan_id)
    plan_repo.get_by_year_and_department.return_value = plan
    with pytest.raises(DuplicateException):
        await plan_service.create_plan(cast(Any, Dump)(year=2026, department="D"))
    plan_repo.get_by_year_and_department.return_value = None
    plan_repo.create.return_value = plan
    assert (
        await plan_service.create_plan(cast(Any, Dump)(year=2026, department="D"))
        is plan
    )
    plan_repo.get_by_id.return_value = plan
    plan_repo.update.return_value = plan
    assert await plan_service.update_plan(plan_id, cast(Any, Dump)(name="new")) is plan
    await plan_service.delete_plan(plan_id)
    plan_repo.list_plans.return_value = ([plan], 1)
    assert (
        await plan_service.list_plans(year=2026, department="D", page=1, page_size=5)
    )[1] == 1

    item_service = _bare(
        hr_service.AnnualTrainingPlanItemService,
        repo=item_repo,
        plan_repo=plan_repo,
    )
    item_repo.list_items.return_value = [record]
    assert await item_service.list_items(plan_id) == [record]
    plan_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await item_service.batch_update_items(plan_id, cast(Any, Dump)(items=[]))
    plan_repo.get_by_id.return_value = plan
    item_repo.create.side_effect = [
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
    ]
    result = await item_service.batch_update_items(
        plan_id,
        cast(Any, Dump)(
            items=[
                cast(Any, Dump)(month="1月", sort_order=9),
                cast(Any, Dump)(month="2月", sort_order=9),
            ]
        ),
    )
    assert len(result) == 2
    item_repo.delete_by_plan_id.assert_awaited_once_with(plan_id)
