from __future__ import annotations

from datetime import date
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.hr import repository, training_dept_resolver

SimpleNamespace: Any = _SimpleNamespace


class _Result:
    def __init__(self: Any, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self: Any) -> Any:
        return self.value

    def scalar_one(self: Any) -> Any:
        return self.value

    def scalar(self: Any) -> Any:
        return 1

    def scalars(self: Any) -> Any:
        return self

    def all(self: Any) -> Any:
        return self.value if isinstance(self.value, list) else [self.value]

    def first(self: Any) -> Any:
        return self.value


def _session(value: Any) -> Any:
    return SimpleNamespace(
        execute=AsyncMock(return_value=_Result(value)),
        add=Mock(),
        flush=AsyncMock(),
        refresh=AsyncMock(),
    )


@pytest.mark.anyio
async def test_department_repository_crud_and_filtered_lists() -> None:
    obj: Any = SimpleNamespace(is_deleted=False)
    session = _session(obj)
    repo = repository.DepartmentRepository(session)
    assert await repo.get_by_id(uuid4()) is obj
    assert await repo.get_by_code("QA") is obj
    assert await repo.get_by_feishu_open_department_id("od1") is obj
    rows, total = await repo.list_departments(
        keyword="质量", parent_id=uuid4(), leader_name="张", page=2, page_size=5
    )
    assert rows == [obj] and total == 1
    assert await repo.list_all_departments() == [obj]
    assert await repo.create(obj) is obj  # type: ignore[arg-type]
    assert await repo.update(obj) is obj
    await repo.soft_delete(obj)
    assert obj.is_deleted is True


@pytest.mark.anyio
async def test_team_repository_crud_and_filters() -> None:
    obj: Any = SimpleNamespace(is_deleted=False)
    session = _session(obj)
    repo = repository.TeamRepository(session)
    assert await repo.get_by_id(uuid4()) is obj
    rows, total = await repo.list_teams(department_id=uuid4(), keyword="班组")
    assert rows == [obj] and total == 1
    assert await repo.create(obj) is obj  # type: ignore[arg-type]
    assert await repo.update(obj) is obj
    await repo.soft_delete(obj)
    assert obj.is_deleted is True


@pytest.mark.anyio
async def test_offboarding_repository_crud_and_filters() -> None:
    obj: Any = SimpleNamespace(is_deleted=False)
    session = _session(obj)
    repo = repository.OffboardingRecordRepository(session)
    assert await repo.get_by_id(uuid4()) is obj
    rows, total = await repo.list_records(
        employee_id=uuid4(), keyword="张", dept_alias_set={"质量部"}
    )
    assert rows == [obj] and total == 1
    assert await repo.create(obj) is obj  # type: ignore[arg-type]
    assert await repo.update(obj) is obj
    assert await repo.get_by_feishu_record_id("rec1") is obj
    assert await repo.list_all() == [obj]
    await repo.soft_delete(obj)
    assert obj.is_deleted is True


@pytest.mark.anyio
async def test_position_transfer_repository_crud_and_filters() -> None:
    obj: Any = SimpleNamespace(is_deleted=False)
    session = _session(obj)
    repo = repository.PositionTransferRecordRepository(session)
    assert await repo.get_by_id(uuid4()) is obj
    rows, total = await repo.list_records(
        employee_id=uuid4(),
        approval_status="pending",
        keyword="张",
        dept_alias_set={"QA"},
    )
    assert rows == [obj] and total == 1
    assert await repo.create(obj) is obj  # type: ignore[arg-type]
    assert await repo.update(obj) is obj
    assert await repo.get_by_feishu_record_id("rec1") is obj
    assert await repo.list_all_with_feishu_id() == [obj]
    await repo.soft_delete(obj)
    assert obj.is_deleted is True


@pytest.mark.anyio
async def test_annual_plan_and_item_repositories() -> None:
    obj: Any = SimpleNamespace(is_deleted=False)
    session = _session(obj)
    plans = repository.AnnualTrainingPlanRepository(session)
    assert await plans.get_by_id(uuid4()) is obj
    assert await plans.get_by_year_and_department(2026, "质量部") is obj
    rows, total = await plans.list_plans(year=2026, department="质量", page=2)
    assert rows == [obj] and total == 1
    rows, total = await plans.list_plans(dept_alias_set={"质量部"})
    assert rows == [obj] and total == 1
    assert await plans.create(obj) is obj  # type: ignore[arg-type]
    assert await plans.update(obj) is obj
    await plans.soft_delete(obj)
    assert obj.is_deleted is True

    obj.is_deleted = False
    items = repository.AnnualTrainingPlanItemRepository(session)
    assert await items.list_items(uuid4()) == [obj]  # type: ignore[comparison-overlap]
    assert await items.get_by_id(uuid4()) is obj
    assert await items.create(obj) is obj  # type: ignore[arg-type]
    assert await items.update(obj) is obj  # type: ignore[arg-type]
    await items.delete(obj)  # type: ignore[arg-type]
    assert obj.is_deleted is True
    await items.delete_by_plan_id(uuid4())


@pytest.mark.anyio
async def test_attachment_and_section_repositories() -> None:
    obj: Any = SimpleNamespace(is_deleted=False)
    session = _session(obj)
    attachments = repository.PlanAttachmentRepository(session)
    assert await attachments.list_by_plan(uuid4()) == [obj]
    assert await attachments.get_by_id(uuid4()) is obj
    assert await attachments.create(obj) is obj  # type: ignore[arg-type]
    await attachments.soft_delete(obj)
    assert obj.is_deleted is True

    sections = repository.PlanAttachmentSectionRepository(session)
    assert await sections.list_by_plan(uuid4()) == [obj]  # type: ignore[comparison-overlap]
    assert await sections.list_by_attachment(uuid4()) == [obj]  # type: ignore[comparison-overlap]
    assert await sections.get_by_id(uuid4()) is obj
    assert await sections.create(obj) is obj  # type: ignore[arg-type]
    await sections.soft_delete_by_attachment(uuid4())


@pytest.mark.anyio
async def test_training_page_personnel_and_contract_repositories() -> None:
    obj: Any = SimpleNamespace(
        id=uuid4(), is_deleted=False, personnel=[], remarks=None, config_name="A"
    )
    session = _session(obj)
    pages = repository.TrainingLedgerPageRepository(session)
    assert await pages.list_pages() == [obj]
    assert await pages.get_by_employee_number("E001") is obj
    session.execute.return_value = SimpleNamespace(all=lambda: [(obj, "质量部")])
    assert await pages.list_pages_with_department() == [(obj, "质量部")]
    session.execute.return_value = _Result(obj)
    assert await pages.create(obj) is obj  # type: ignore[arg-type]

    configs = repository.TrainingPersonnelConfigRepository(session)
    assert await configs.list_configs(level="部门级", department="质量部") == [obj]  # type: ignore[comparison-overlap]
    assert await configs.get_by_key("部门级", None, "A") is obj
    assert await configs.get_by_key("部门级", "质量部", "A") is obj
    assert await configs.get_by_id(uuid4()) is obj
    assert await configs.create(obj) is obj  # type: ignore[arg-type]
    updated = await configs.update_fields(
        obj,  # type: ignore[arg-type]
        personnel=[{"name": "张三"}],
        remarks="重点",
        config_name="B",
    )
    assert updated is obj and obj.config_name == "B"  # type: ignore[attr-defined]
    await configs.soft_delete(obj)  # type: ignore[arg-type]
    assert obj.is_deleted is True

    contracts = repository.ContractManagementRepository(session)
    assert await contracts.list_new_hires(  # type: ignore[comparison-overlap]
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 31)
    ) == [obj]


@pytest.mark.anyio
async def test_employee_repository_crud_full_filter_set_and_counts() -> None:
    employee: Any = SimpleNamespace(employee_number="E001", is_deleted=False)
    session = _session(employee)
    repo = repository.EmployeeRepository(session)
    assert await repo.get_by_id(uuid4()) is employee
    assert await repo.get_by_employee_number("E001") is employee
    assert await repo.get_by_name("张三") is employee
    assert await repo.get_employee_number_map() == {"E001": employee}
    assert await repo.get_max_seq_number() == 1
    rows, total = await repo.list_employees(
        dept_alias_set={"质量部"},
        sub_department="QA",
        status="在职",
        keyword="张",
        team="A班",
        position="专员",
        job_category="管理",
        level="P1",
        gender="男",
        education="本科",
        political_status="群众",
        marital_status="已婚",
        status_category="正式",
        age_min=18,
        age_max=60,
        birth_year_min=1966,
        birth_year_max=2008,
        hire_date_after=date(2020, 1, 1),
        hire_date_before=date(2026, 12, 31),
        factory_entry_date_after=date(2020, 1, 1),
        factory_entry_date_before=date(2026, 12, 31),
        work_start_date_after=date(2010, 1, 1),
        work_start_date_before=date(2026, 12, 31),
        sort_by="name",
        sort_order="asc",
    )
    assert rows == [employee] and total == 1
    assert await repo.list_recent_entries(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        dept_alias_set={"质量部"},
    ) == [employee]
    assert await repo.create(employee) is employee  # type: ignore[arg-type]
    assert await repo.update(employee) is employee
    assert await repo.count_total() == 1
    assert await repo.count_synced() == 1
    await repo.soft_delete(employee)
    assert employee.is_deleted is True


@pytest.mark.anyio
async def test_employee_repository_upsert_delete_maps_groups_and_distinct_values() -> (
    None
):
    employee: Any = SimpleNamespace(
        employee_number="E001", name="旧姓名", is_deleted=False, status="在职"
    )
    session = _session(employee)
    repo = repository.EmployeeRepository(session)
    repo.get_by_employee_number_include_deleted = AsyncMock(  # type: ignore[method-assign]
        return_value=employee
    )
    updated = await repo.upsert_by_employee_number(
        {"employee_number": "E001", "name": "新姓名"}
    )
    assert updated.name == "新姓名"
    repo.get_by_employee_number_include_deleted.return_value = None  # type: ignore[attr-defined]
    created = await repo.upsert_by_employee_number(
        {"employee_number": "E002", "name": "李四"}
    )
    assert created.employee_number == "E002"
    assert await repo.delete_not_in_feishu(set()) == 0
    session.execute.return_value = SimpleNamespace(rowcount=2)
    assert await repo.delete_not_in_feishu({"rec1"}) == 2

    session.execute.return_value = SimpleNamespace(all=lambda: [("E001", "rec1")])
    assert await repo.get_feishu_record_map() == {"E001": "rec1"}
    assert await repo.group_count("missing") == []
    assert await repo.get_distinct_values("missing") == []
    session.execute.return_value = SimpleNamespace(
        all=lambda: [("质量部", 3), (None, 1)]
    )
    assert await repo.group_count("department", status="在职") == [
        {"value": "质量部", "count": 3}
    ]
    session.execute.return_value = SimpleNamespace(all=lambda: [("质量部",), (None,)])
    assert await repo.get_distinct_values("department", keyword="张") == ["质量部"]


@pytest.mark.anyio
async def test_employee_statistics_assemble_all_distributions() -> None:
    emp = SimpleNamespace(
        employee_number="E001",
        name="张三",
        department="质量部",
        position="QA",
        status="在职",
        is_deleted=False,
        contract_end_date=date(2026, 9, 1),
        contract_end_2=None,
        contract_end_3=None,
        contract_end_4=None,
        contract_end_5=None,
        contract_end_6=None,
    )
    results = [
        SimpleNamespace(scalar=lambda: 5),
        SimpleNamespace(all=lambda: [("在职", 4), ("离职", 1)]),
        SimpleNamespace(all=lambda: [("质量部", 5)]),
        SimpleNamespace(all=lambda: [("本科", 3)]),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [emp])),
    ]
    session: Any = SimpleNamespace(execute=AsyncMock(side_effect=results))
    stats = await repository.EmployeeRepository(session).get_stats({"质量部"})
    assert stats["total"] == 5
    assert stats["status_distribution"] == {"在职": 4, "离职": 1}
    assert stats["department_distribution"] == [{"department": "质量部", "count": 5}]
    assert stats["education_distribution"] == {"本科": 3}
    assert stats["contract_expiring_count"] == 1
    assert stats["contract_expiring_list"][0]["employee_number"] == "E001"


@pytest.mark.anyio
async def test_employee_statistics_parses_string_contract_end_5() -> None:
    """合同到期取 6 个合同字段最晚非空日期：contract_end_5 为字符串时需解析。"""
    emp = SimpleNamespace(
        employee_number="E002",
        name="李四",
        department="质量部",
        position="QA",
        status="在职",
        is_deleted=False,
        contract_end_date=date(2026, 8, 1),
        contract_end_2=None,
        contract_end_3=None,
        contract_end_4=None,
        contract_end_5="2026/09/15",
        contract_end_6=None,
    )
    results = [
        SimpleNamespace(scalar=lambda: 1),
        SimpleNamespace(all=lambda: []),
        SimpleNamespace(all=lambda: [("质量部", 1)]),
        SimpleNamespace(all=lambda: []),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [emp])),
    ]
    session: Any = SimpleNamespace(execute=AsyncMock(side_effect=results))
    stats = await repository.EmployeeRepository(session).get_stats({"质量部"})
    assert stats["contract_expiring_count"] == 1
    assert stats["contract_expiring_list"][0]["employee_number"] == "E002"
    assert stats["contract_expiring_list"][0]["contract_end_date"] == "2026-09-15"


@pytest.mark.anyio
async def test_employee_contract_expiry_selects_latest_contract_and_paginates() -> None:
    employee: Any = SimpleNamespace(
        id=uuid4(),
        employee_number="E001",
        name="张三",
        department="质量部",
        sub_department="QA",
        position="专员",
        contract_end_date=date(2026, 8, 1),
        contract_start_date=date(2025, 8, 1),
        contract_end_2=date(2026, 9, 1),
        contract_start_2=date(2025, 9, 1),
        contract_end_3=None,
        contract_start_3=None,
        contract_end_4=None,
        contract_start_4=None,
        contract_end_5="2026/10/01",
        contract_start_5="2025/10/01",
        contract_end_6="invalid",
        contract_start_6=None,
    )
    session: Any = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: _Result([employee]))
        )
    )
    rows, total = await repository.EmployeeRepository(session).list_contract_expiring(
        "2026-09-01",  # type: ignore[arg-type]
        "2026-10-31",  # type: ignore[arg-type]
        department="质量",
        page=1,
        page_size=10,
    )
    assert total == 1
    assert rows[0]["contract_sequence"] == 5
    assert rows[0]["contract_sign_date"] == "2025-10-01"


@pytest.mark.anyio
async def test_training_ledger_repository_crud_lists_and_batch_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: Any = SimpleNamespace(id=uuid4(), is_deleted=False, session_id=None)
    session = _session(record)
    session.get = AsyncMock(return_value=None)
    repo = repository.TrainingLedgerRepository(session)
    assert await repo.get_by_id(uuid4()) is record
    rows, total = await repo.list_records(
        employee_number="E001",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        session_id=uuid4(),
        dept_alias_set={"质量部"},
        sort_order="asc",
    )
    assert rows == [record] and total == 1
    assert await repo.list_all_for_employee_list() == [record]
    assert await repo.list_by_date(date(2026, 8, 20)) == [record]
    assert await repo.create(record) is record  # type: ignore[arg-type]
    assert await repo.update(record) is record
    assert await repo.get_by_source("notification", "n1") is record
    await repo.soft_delete(record)
    assert record.is_deleted is True
    assert repo.bare201_hidden_when_split() is not None
    monkeypatch.setattr(
        training_dept_resolver,
        "ledger_dept_read_family",
        AsyncMock(return_value={"201二车间（MC）", "201二车间"}),
    )
    monkeypatch.setattr(
        training_dept_resolver,
        "training_dept_aliases_of",
        AsyncMock(return_value=["201二车间（MC）", "201二车间", "201二车间（霉酚酸）", "201三车间"]),
    )
    rows, total = await repo.list_by_department("201二车间（MC）")
    assert rows == [record] and total == 1
    await repo.mark_owner_deleted(uuid4(), uuid4())
    session.execute.return_value = SimpleNamespace(rowcount=3)
    assert (
        await repo.sync_by_session_id(
            session_id=uuid4(), exclude_id=uuid4(), update_data={"trainer": "张老师"}
        )
        == 3
    )
    assert (
        await repo.sync_by_session_id(
            session_id=uuid4(), exclude_id=uuid4(), update_data={}
        )
        == 0
    )


@pytest.mark.anyio
async def test_training_departments_merge_configs_custom_rows_and_mappings() -> None:
    mapping_rows = [
        SimpleNamespace(source_name="QA", target_name="质量部", mapping_type="alias"),
        SimpleNamespace(source_name="冻结", target_name=None, mapping_type="exclude"),
        SimpleNamespace(
            source_name="研发部", target_name=None, mapping_type="force_show"
        ),
    ]
    session: Any = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [("QA",), ("冻结",)]),
                SimpleNamespace(
                    all=lambda: [("生产部", [{"name": "李四", "department": "动力部"}])]
                ),
                SimpleNamespace(all=lambda: [("自定义部",)]),
            ]
        ),
        add=Mock(),
        flush=AsyncMock(),
    )
    repo = repository.TrainingLedgerRepository(session)
    repo.list_dept_mappings = AsyncMock(return_value=mapping_rows)  # type: ignore[method-assign]
    assert await repo.list_all_training_departments() == [
        "动力部",
        "生产部",
        "研发部",
        "自定义部",
        "质量部",
    ]


@pytest.mark.anyio
async def test_legacy_feishu_repositories_crud_upsert_and_filtered_lists() -> None:
    obj: Any = SimpleNamespace(feishu_record_id="rec1", is_deleted=False)
    session = _session(obj)
    onboarding = repository.OnboardingRecordRepository(session)
    assert await onboarding.get_by_id(uuid4()) is obj
    assert await onboarding.get_by_feishu_record_id("rec1") is obj
    assert await onboarding.create(obj) is obj
    assert await onboarding.update(obj) is obj
    assert await onboarding.count_total() == 1
    assert await onboarding.count_synced() == 1
    rows, total = await onboarding.list_records(
        department="质量部",
        position="QA",
        is_employed="是",
        keyword="张",
        sort_order="asc",
    )
    assert rows == [obj] and total == 1
    onboarding.get_by_feishu_record_id = AsyncMock(return_value=obj)  # type: ignore[method-assign]
    assert (
        await onboarding.upsert_by_feishu_record_id(
            {"feishu_record_id": "rec1", "name": "张三", "empty": None}
        )
        is obj
    )
    with pytest.raises(ValueError):
        await onboarding.upsert_by_feishu_record_id({})
    await onboarding.soft_delete(obj)
    assert obj.is_deleted is True

    departure = repository.DepartureRecordRepository(session)
    rows, total = await departure.list_records(  # type: ignore[assignment]
        department="质量部", offboarding_type="辞职", keyword="张", sort_order="asc"
    )
    assert rows == [obj] and total == 1


@pytest.mark.anyio
async def test_training_member_repository_reactivates_and_creates() -> None:
    member: Any = SimpleNamespace(
        id=uuid4(), is_deleted=True, employee_number=None, source="feishu"
    )
    session = _session(member)
    repo = repository.EmployeeTrainingListRepository(session)
    assert await repo.list_by_department("质量部") == [member]
    assert await repo.list_all() == [member]
    assert await repo.get_by_department_name("质量部", "张三") is member
    assert await repo.get_any_by_department_name("质量部", "张三") is member
    assert await repo.get_by_id(member.id) is member  # type: ignore[union-attr]
    repo.get_any_by_department_name = AsyncMock(return_value=member)  # type: ignore[method-assign]
    updated = await repo.upsert_member("质量部", "张三", "E001", "manual")
    assert updated.is_deleted is False
    assert updated.employee_number == "E001"
    assert updated.source == "manual"
    repo.get_any_by_department_name.return_value = None
    created = await repo.upsert_member("质量部", "李四", None, "manual")
    assert created.name == "李四"
    await repo.soft_delete(created)
    assert created.is_deleted is True


@pytest.mark.anyio
async def test_training_import_and_custom_department_repository_operations() -> None:
    obj: Any = SimpleNamespace(id=uuid4(), is_deleted=False)
    session = _session(obj)
    imports = repository.TrainingImportMappingRepository(session)
    assert await imports.get_by_dept_fingerprint("质量部", "abc") is obj
    assert await imports.create(obj) is obj  # type: ignore[arg-type]
    assert await imports.update(obj) is obj

    training = repository.TrainingLedgerRepository(session)
    session.execute.return_value = SimpleNamespace(all=lambda: [("质量部",)])
    assert await training.list_custom_training_departments() == ["质量部"]
    created = await training.add_custom_training_department("研发部")
    assert created.name == "研发部"
    session.execute.return_value = _Result(obj)
    assert await training.delete_custom_training_department("研发部") is True
    assert obj.is_deleted is True
    session.execute.return_value = _Result(None)
    assert await training.delete_custom_training_department("不存在") is False
    session.execute.return_value = _Result(obj)
    assert await training.get_dept_mapping(uuid4()) is obj
    mapping = await training.create_dept_mapping(
        {
            "source_name": "QA",
            "target_name": "质量部",
            "match_level": "exact",
            "mapping_type": "alias",
        }
    )
    await training.delete_dept_mapping(mapping)
    assert mapping.is_deleted is True
