from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import DuplicateException, NotFoundException
from app.modules.hr import service
from app.modules.hr.schemas import (
    DepartmentCreate,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeUpdate,
)


def _employee(**overrides: object) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "employee_number": "E001",
        "name": "张三",
        "department": "质量部",
        "sub_department": "QA",
        "team": "一组",
        "position": "质量员",
        "job_category": "技术",
        "level": "初级",
        "employment_type": "正式",
        "qualifications": ["GMP"],
        "qualification_type": "工程师",
        "certificate_number": "C-1",
        "certificate_review_date": date(2026, 8, 20),
        "gender": "男",
        "ethnic_group": "汉",
        "native_place": "广东",
        "political_status": "党员",
        "marital_status": "未婚",
        "health_status": "健康",
        "household_type": "城镇",
        "status_category": "在职",
        "birth_year": 1990,
        "birth_month": 1,
        "birth_day": 2,
        "age": 36,
        "work_start_date": date(2012, 1, 1),
        "factory_entry_date": date(2020, 1, 1),
        "livo_entry_date": date(2020, 1, 1),
        "hire_date": date(2020, 1, 1),
        "graduation_date": date(2012, 6, 1),
        "work_years": 14,
        "factory_tenure": "6年",
        "company_tenure": "6年",
        "education": "本科",
        "degree": "学士",
        "classification": "全日制",
        "school": "大学",
        "major": "化学",
        "id_card": "440000000000000000",
        "id_card_expiry": "2030-01-01",
        "id_card_address": "广东",
        "current_address": "珠海",
        "contract_type": "固定期限",
        "contract_start_date": date(2024, 1, 1),
        "contract_end_date": date(2027, 1, 1),
        "contract_start_2": None,
        "contract_end_2": None,
        "contract_start_3": None,
        "contract_end_3": None,
        "contract_start_4": None,
        "contract_end_4": None,
        "contract_start_5": None,
        "contract_end_5": None,
        "contract_start_6": None,
        "contract_end_6": None,
        "contract_opinion": None,
        "dept_leader_name": None,
        "phone": "13800000000",
        "email": "a@example.com",
        "emergency_contact_name": "李四",
        "emergency_contact_phone": "13900000000",
        "emergency_contact_relation": "家属",
        "bank_account": "6222",
        "training_id": "T-1",
        "archive_number": "A-1",
        "domain_account": "zhangsan",
        "work_experience_1": "经历一",
        "work_experience_2": None,
        "work_experience_3": None,
        "work_experience_4": None,
        "transfer_history": None,
        "remarks": ["重点培养"],
        "status": "在职",
        "probation_status": "已转正",
        "planned_probation_date": None,
        "probation_effective_date": None,
        "last_working_day": None,
        "offboarding_type": None,
        "offboarding_reason": None,
        "feishu_record_id": None,
        "feishu_open_id": None,
        "feishu_synced_at": None,
        "created_at": datetime(2026, 8, 20),
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _NestedTransaction:
    async def __aenter__(self) -> "_NestedTransaction":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def __await__(self):
        # 立即完成的生成器：await 直接得到 self，无事件循环依赖
        if False:
            yield
        return self

    commit = AsyncMock()
    rollback = AsyncMock()


def _employee_service() -> service.EmployeeService:
    instance = service.EmployeeService.__new__(service.EmployeeService)
    instance.session = SimpleNamespace()
    instance.repo = SimpleNamespace(
        get_by_id=AsyncMock(),
        get_by_employee_number=AsyncMock(),
        get_stats=AsyncMock(return_value={"total": 1}),
        create=AsyncMock(),
        update=AsyncMock(),
        soft_delete=AsyncMock(),
        list_employees=AsyncMock(return_value=([], 0)),
        list_contract_expiring=AsyncMock(return_value=([], 0)),
        count_total=AsyncMock(return_value=3),
        count_synced=AsyncMock(return_value=2),
        delete_not_in_feishu=AsyncMock(return_value=1),
        upsert_by_employee_number=AsyncMock(),
    )
    instance._feishu = None
    return instance


def test_employee_mapping_helpers_cover_fallbacks_and_timestamps() -> None:
    raw = service._parse_feishu_record(
        {
            "record_id": "r1",
            "updated_time": "2026-08-20T08:00:00Z",
            "fields": {
                "序号": {"value": [3]},
                "工号": "E001",
                "姓名": [{"text": "张三"}],
                "一级部门": "质量部",
                "职务|岗位": "质量员",
                "技能证书": ["GMP"],
                "入职日期": "2026-08-20",
                "首次签订合同日期": 1_750_000_000_000,
                "合同截止日期（2）": "2027/08/20",
                "在职状态": "在职",
            },
        }
    )
    assert raw["employee_number"] == "E001"
    assert raw["seq_number"] == 3
    assert raw["department"] == "质量部"
    assert raw["qualifications"] == ["GMP"]
    assert raw["status"] == "在职"
    assert raw["feishu_synced_at"] == date(2026, 8, 20)
    assert (
        service._parse_feishu_record({"updated_time": "bad", "fields": {}})["status"]
        == "在职"
    )

    obj = _employee()
    mapped = service.EmployeeService.__new__(
        service.EmployeeService
    )._to_bitable_fields(obj)
    assert mapped["姓名"] == "张三"
    assert mapped["工号"] == "E001"
    assert mapped["技能证书"] == ["GMP"]
    assert mapped["参加工作时间"]
    assert "空字段" not in mapped


@pytest.mark.asyncio
async def test_employee_crud_sync_and_status_compatibility() -> None:
    instance = _employee_service()
    employee = _employee()
    instance.repo.get_by_id.return_value = employee
    instance.repo.get_by_employee_number.return_value = None
    instance.repo.create.side_effect = lambda value: value
    instance.repo.update.side_effect = lambda value: value
    bitable = SimpleNamespace(
        create=AsyncMock(return_value="feishu-r1"),
        update=AsyncMock(),
        delete=AsyncMock(),
        find_by_employee_number=AsyncMock(return_value=None),
    )
    instance._get_bitable = AsyncMock(return_value=bitable)
    created = await instance.create_employee(
        EmployeeCreate(
            employee_number="E002",
            name="李四",
            department="生产部",
            position="操作员",
            hire_date=date(2026, 8, 20),
        )
    )
    assert isinstance(created, tuple)
    assert created[0].status == "在职"
    assert created[1] == "success"
    assert bitable.create.await_count == 1

    instance.repo.get_by_employee_number.return_value = employee
    with pytest.raises(DuplicateException):
        await instance.create_employee(
            EmployeeCreate(
                employee_number="E001",
                name="重复",
                department="质量部",
                position="质量员",
                hire_date=date(2026, 8, 20),
            )
        )

    instance.repo.get_by_employee_number.return_value = employee
    employee.status = "待审批"
    instance._sync_single_to_feishu = AsyncMock(return_value="feishu-r1")
    approved = await instance.approve_employee("E001")
    assert approved.status == "在职"
    employee.status = "在职"
    with pytest.raises(DuplicateException):
        await instance.approve_employee("E001")

    instance.repo.get_by_id.return_value = employee
    updated = await instance.update_employee(
        employee.id,
        EmployeeUpdate(name="新姓名", employee_number=""),
    )
    assert isinstance(updated, tuple)
    assert employee.name == "新姓名"
    assert employee.employee_number is None
    employee.feishu_record_id = "feishu-r1"
    assert (await instance.delete_employee(employee.id)) == "success"
    assert bitable.delete.await_count == 1

    instance.repo.get_by_id.return_value = None
    instance.repo.get_by_employee_number.return_value = None
    with pytest.raises(NotFoundException):
        await instance.get_employee(uuid4())
    with pytest.raises(NotFoundException):
        await instance.get_employee_by_number("missing")

    assert await instance.get_employee_stats() == {"total": 1}
    assert await instance.list_employees(keyword="张") == ([], 0)
    assert await instance.list_contract_expiring(date.today(), date.today()) == ([], 0)
    assert (await instance.get_sync_status()).unsynced_count == 1


@pytest.mark.asyncio
async def test_employee_sync_and_notification_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 飞书 IM/同步改由人事专属应用执行：隔离 DB 凭证解析
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )
    instance = _employee_service()
    instance.session = SimpleNamespace(
        begin_nested=lambda: _NestedTransaction(),
    )
    employee = _employee(feishu_record_id=None)
    instance.bitable = SimpleNamespace(
        table_id="tbl",
        client=SimpleNamespace(search_records=AsyncMock(return_value=[])),
    )
    del instance.session
    instance.repo.get_by_employee_number.return_value = None
    result = await instance.sync_from_feishu()
    assert result["total"] == 0

    instance = _employee_service()
    instance.session = SimpleNamespace(
        begin_nested=lambda: _NestedTransaction(),
    )
    instance.session.rollback = AsyncMock()
    employee.created_at = datetime(2026, 8, 20)
    current_bitable = SimpleNamespace(
        table_id="tbl",
        client=SimpleNamespace(
            search_records=AsyncMock(
                return_value=[
                    {"record_id": "r1", "fields": {"工号": "E001", "姓名": "张三"}},
                    {"record_id": "r2", "fields": {"姓名": "无工号"}},
                ]
            )
        ),
        update=AsyncMock(),
        find_by_employee_number=AsyncMock(
            return_value=SimpleNamespace(record_id="existing")
        ),
    )
    instance._get_bitable = AsyncMock(return_value=current_bitable)
    instance.session.rollback = AsyncMock()
    instance.repo.get_by_employee_number.return_value = employee
    result = await instance.sync_from_feishu()
    assert result["total"] == 2
    assert result["skipped"] == 1
    assert result["deleted"] == 1

    instance.repo.get_by_id.return_value = employee
    employee.feishu_record_id = None
    instance._sync_single_to_feishu = (
        service.EmployeeService._sync_single_to_feishu.__get__(instance)
    )
    assert await instance.sync_to_feishu(employee.id) == "existing"

    payload = SimpleNamespace(
        employee_numbers=["E001", "missing"],
        training_time_start="09:00",
        training_time_end="10:00",
        subject="安全培训",
        training_date=date(2026, 8, 20),
        location=None,
        trainer=None,
        content="重点",
    )
    employee.feishu_open_id = None
    monkeypatch.setattr(
        "app.modules.hr.feishu.im.FeishuIM",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    instance.repo.get_by_employee_number.side_effect = [employee, None]
    result = await instance.notify_training(payload)
    assert result["failed"] == 2


def _department(**overrides: object) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "name": "质量部",
        "code": "QA",
        "description": None,
        "leader_name": "张三",
        "parent_id": None,
        "sort_order": 1,
        "headcount": 5,
        "current_count": 3,
        "responsibilities": None,
        "category": "职能",
        "feishu_open_department_id": "ou-qa",
        "created_at": datetime(2026, 8, 20),
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _department_service() -> service.DepartmentService:
    instance = service.DepartmentService.__new__(service.DepartmentService)
    instance.session = SimpleNamespace()
    instance.repo = SimpleNamespace(
        get_by_id=AsyncMock(),
        get_by_code=AsyncMock(return_value=None),
        create=AsyncMock(),
        update=AsyncMock(),
        soft_delete=AsyncMock(),
        list_departments=AsyncMock(return_value=([], 0)),
        list_all_departments=AsyncMock(return_value=[]),
    )
    instance._feishu = None
    return instance


@pytest.mark.asyncio
async def test_department_tree_crud_and_org_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 部门树/飞书通讯录改由人事专属应用执行：隔离 DB 凭证解析
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )
    instance = _department_service()
    feishu = SimpleNamespace(
        sync_department_created=AsyncMock(),
        sync_department_updated=AsyncMock(),
        sync_department_deleted=AsyncMock(),
    )
    instance._ensure_feishu_creds = AsyncMock(return_value=feishu)
    department = _department()
    instance.repo.create.side_effect = lambda value: value
    created = await instance.create_department(
        DepartmentCreate(name="质量部", code="QA", leader_name="张三")
    )
    assert created.name == "质量部"
    instance.repo.get_by_id.return_value = department
    instance.repo.update.side_effect = lambda value: value
    updated = await instance.update_department(
        department.id, DepartmentUpdate(name="质量管理部", parent_id=None)
    )
    assert updated.name == "质量管理部"
    await instance.delete_department(department.id)
    assert feishu.sync_department_deleted.await_count == 1
    assert await instance.list_departments(keyword="质量") == ([], 0)

    root = _department(
        name="总经办", code="ADMIN", sort_order=1, feishu_open_department_id="ou-root"
    )
    child = _department(name="质量部", parent_id=root.id, code="QA", sort_order=2)
    instance.repo.list_all_departments.return_value = [child, root]
    tree = await instance.get_department_tree()
    assert tree[0]["name"] == "总经办"
    assert tree[0]["children"][0]["name"] == "质量部"

    contact = SimpleNamespace(
        get_department_users=AsyncMock(
            return_value=[
                {
                    "employee_no": "E1",
                    "name": "张三",
                    "open_id": "ou1",
                    "job_title": "主管",
                },
                {"name": "公共账号"},
            ]
        )
    )
    monkeypatch.setattr(
        "app.modules.hr.feishu.contact.FeishuContact",
        lambda *args, **kwargs: contact,
    )
    org = await instance.get_org_tree()
    assert org[0]["children"]
    assert org[0]["children"][0]["children"][0]["type"] == "employee"

    instance.repo.get_by_code.return_value = department
    with pytest.raises(DuplicateException):
        await instance.create_department(DepartmentCreate(name="重复", code="QA"))
    instance.repo.get_by_id.return_value = department
    instance.repo.get_by_code.return_value = _department(id=uuid4())
    with pytest.raises(DuplicateException):
        await instance.update_department(department.id, DepartmentUpdate(code="OTHER"))


def test_department_tree_handles_empty_and_unlinked_nodes() -> None:
    assert service.DepartmentService._build_dept_tree([]) == []
    orphan = _department(parent_id=uuid4())
    assert service.DepartmentService._build_dept_tree([orphan]) == [orphan]
