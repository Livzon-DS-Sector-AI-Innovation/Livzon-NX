from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.modules.hr import service
from app.modules.hr.schemas import (
    TeamCreate,
    TeamUpdate,
    TrainingLedgerCreate,
    TrainingLedgerUpdate,
)


class _NestedTransaction:
    """同时支持 `async with` 与 `await` 两种用法的 savepoint 桩。"""

    async def __aenter__(self) -> _NestedTransaction:
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


def _department(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "name": "质量部",
        "code": "QA",
        "description": "质量管理",
        "leader_name": "张三",
        "parent_id": None,
        "sort_order": 1,
        "headcount": 10,
        "current_count": 8,
        "responsibilities": None,
        "category": "职能",
        "feishu_open_department_id": None,
        "is_deleted": False,
        "created_at": datetime(2026, 8, 20),
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_department_sync_updates_rebinds_creates_and_cleans_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 部门飞书同步改由人事专属应用拉取：隔离 DB 凭证解析
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )
    root = _department(
        name="总经办",
        code="ROOT",
        feishu_open_department_id="ou-root",
        current_count=1,
    )
    unbound = _department(name="质量部", code="QA", feishu_open_department_id=None)
    stale = _department(
        name="历史集团部门",
        code="STALE",
        feishu_open_department_id="ou-stale",
    )
    repo = SimpleNamespace(
        list_all_departments=AsyncMock(return_value=[root, unbound, stale]),
        update=AsyncMock(),
        create=AsyncMock(),
    )
    result = SimpleNamespace(scalar=lambda: 0, scalar_one_or_none=lambda: None)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        flush=AsyncMock(),
        rollback=AsyncMock(),
        begin_nested=lambda: _NestedTransaction(),
    )
    instance = service.DepartmentService.__new__(service.DepartmentService)
    instance.repo = repo
    instance.session = session
    instance._feishu = None

    feishu_rows = [
        {
            "department_id": "ou-root",
            "name": "总经办",
            "member_count": 2,
            "order": 3,
            "leader_user_id": "u-root",
        },
        {
            "department_id": "ou-quality",
            "name": "质量部",
            "parent_department_id": "ou-root",
            "member_count": 9,
            "order": 4,
            "leader_user_id": "u-quality",
        },
        {
            "department_id": "ou-warehouse",
            "name": "仓储部",
            "parent_department_id": "ou-root",
            "member_count": 5,
            "order": 5,
            "leader_user_id": "u-warehouse",
        },
        {"department_id": None, "name": "无效记录"},
    ]
    monkeypatch.setattr(
        "app.core.redis.cache_get",
        AsyncMock(return_value=json.dumps(feishu_rows, ensure_ascii=False)),
    )
    monkeypatch.setattr("app.core.redis.cache_set", AsyncMock())
    contact = SimpleNamespace(
        get_user_name=AsyncMock(
            side_effect=lambda user_id: {
                "u-root": "根负责人",
                "u-quality": "质量负责人",
                "u-warehouse": "仓储负责人",
            }.get(user_id)
        )
    )
    monkeypatch.setattr(
        "app.modules.hr.feishu.contact.FeishuContact",
        lambda *args, **kwargs: contact,
    )

    stats = await instance.sync_departments_from_feishu()

    assert stats["total"] == 4
    assert stats["failed"] == 1
    assert stats["created"] == 1
    assert stats["updated"] >= 1
    assert unbound.feishu_open_department_id == "ou-quality"
    assert unbound.parent_id == root.id
    assert repo.create.await_count == 1
    assert session.flush.await_count == 1


@pytest.mark.asyncio
async def test_department_sync_prefers_top_dept_with_children_as_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """parent_id 数据异常（多个顶层部门）时，同步根必须选有子部门的顶层，
    而不是 next() 碰到的第一个叶子顶层，否则 BFS 只能拉到残缺子树。"""
    leaf_root = _department(
        name="车队",
        code="LEAF",
        feishu_open_department_id="od-leaf",
    )
    real_root = _department(
        name="丽珠集团（宁夏）制药有限公司",
        code="ROOT",
        feishu_open_department_id="od-real-root",
    )
    child = _department(
        name="质量管理部",
        code="QM",
        feishu_open_department_id="od-qm",
        parent_id=real_root.id,
    )
    repo = SimpleNamespace(
        list_all_departments=AsyncMock(
            return_value=[leaf_root, real_root, child]
        ),
        update=AsyncMock(),
        create=AsyncMock(),
    )
    result = SimpleNamespace(scalar=lambda: 0, scalar_one_or_none=lambda: None)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        flush=AsyncMock(),
        rollback=AsyncMock(),
        begin_nested=lambda: _NestedTransaction(),
    )
    instance = service.DepartmentService.__new__(service.DepartmentService)
    instance.repo = repo
    instance.session = session
    instance._feishu = None

    monkeypatch.setattr(
        "app.core.redis.cache_get", AsyncMock(return_value=None)
    )
    cache_set = AsyncMock()
    monkeypatch.setattr("app.core.redis.cache_set", cache_set)
    captured_root: dict[str, str] = {}

    async def _fake_get_all_departments(root_department_id: str) -> list[dict]:
        captured_root["root"] = root_department_id
        return [
            {
                "department_id": "od-real-root",
                "name": "丽珠集团（宁夏）制药有限公司",
                "member_count": 1,
                "order": 0,
            },
            {
                "department_id": "od-qm",
                "name": "质量管理部",
                "parent_department_id": "od-real-root",
                "member_count": 3,
                "order": 1,
            },
        ]

    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_all_departments",
        _fake_get_all_departments,
    )
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )

    await instance.sync_departments_from_feishu()

    assert captured_root["root"] == "od-real-root"


@pytest.mark.asyncio
async def test_department_sync_empty_tree_aborts_without_caching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """飞书树拉取为空时必须中止同步且不得写缓存，防止空结果污染 24h 缓存。"""
    root = _department(
        name="丽珠集团（宁夏）制药有限公司",
        code="ROOT",
        feishu_open_department_id="od-real-root",
    )
    repo = SimpleNamespace(
        list_all_departments=AsyncMock(return_value=[root]),
        update=AsyncMock(),
        create=AsyncMock(),
    )
    session = SimpleNamespace(
        execute=AsyncMock(),
        flush=AsyncMock(),
        rollback=AsyncMock(),
        begin_nested=lambda: _NestedTransaction(),
    )
    instance = service.DepartmentService.__new__(service.DepartmentService)
    instance.repo = repo
    instance.session = session
    instance._feishu = None

    monkeypatch.setattr(
        "app.core.redis.cache_get", AsyncMock(return_value=None)
    )
    cache_set = AsyncMock()
    monkeypatch.setattr("app.core.redis.cache_set", cache_set)

    async def _fake_get_all_departments(root_department_id: str) -> list[dict]:
        return []

    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_all_departments",
        _fake_get_all_departments,
    )
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )

    with pytest.raises(AppException) as exc_info:
        await instance.sync_departments_from_feishu()

    assert exc_info.value.status_code == 502
    cache_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_department_sync_keeps_root_not_in_bfs_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """飞书 BFS 树从根的下级开始、不含根本身：陈旧清理不得把同步根误删，
    否则会连带解除全部一级部门的父级引用、摧毁整棵层级树。"""
    root = _department(
        name="丽珠集团（宁夏）制药有限公司",
        code="ROOT",
        feishu_open_department_id="od-real-root",
    )
    level1 = _department(
        name="质量管理部",
        code="QM",
        feishu_open_department_id="od-qm",
        parent_id=root.id,
    )
    repo = SimpleNamespace(
        list_all_departments=AsyncMock(return_value=[root, level1]),
        update=AsyncMock(),
        create=AsyncMock(),
    )
    result = SimpleNamespace(scalar=lambda: 0, scalar_one_or_none=lambda: None)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        flush=AsyncMock(),
        rollback=AsyncMock(),
        begin_nested=lambda: _NestedTransaction(),
    )
    instance = service.DepartmentService.__new__(service.DepartmentService)
    instance.repo = repo
    instance.session = session
    instance._feishu = None

    feishu_rows = [
        {
            "department_id": "od-qm",
            "name": "质量管理部",
            "member_count": 3,
            "order": 1,
            "leader_user_id": "",
        },
    ]
    monkeypatch.setattr(
        "app.core.redis.cache_get",
        AsyncMock(return_value=json.dumps(feishu_rows, ensure_ascii=False)),
    )
    cache_set = AsyncMock()
    monkeypatch.setattr("app.core.redis.cache_set", cache_set)
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )

    await instance.sync_departments_from_feishu()

    # 根不在树里但必须保留，且一级部门的父级引用不被解除
    assert root.is_deleted is False
    assert level1.parent_id == root.id


@pytest.mark.asyncio
async def test_team_service_validates_department_and_delegates_crud() -> None:
    department = _department(id=uuid4())
    team = SimpleNamespace(id=uuid4(), department_id=department.id, name="一组")
    repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=team),
        create=AsyncMock(side_effect=lambda value: value),
        update=AsyncMock(side_effect=lambda value: value),
        soft_delete=AsyncMock(),
        list_teams=AsyncMock(return_value=([team], 1)),
    )
    department_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=department))
    instance = service.TeamService.__new__(service.TeamService)
    instance.repo = repo
    instance.department_repo = department_repo

    created = await instance.create_team(
        TeamCreate(name="一组", department_id=department.id)
    )
    assert created.name == "一组"
    updated = await instance.update_team(team.id, TeamUpdate(name="二组"))
    assert updated.name == "二组"
    assert await instance.list_teams(department_id=department.id) == ([team], 1)
    await instance.delete_team(team.id)
    repo.soft_delete.assert_awaited_once_with(team)

    department_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await instance.create_team(TeamCreate(name="无部门", department_id=uuid4()))
    with pytest.raises(NotFoundException):
        await instance.update_team(team.id, TeamUpdate(department_id=uuid4()))
    repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await instance.get_team(team.id)


def _offboarding_record(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "employee_id": uuid4(),
        "seq_number": 1,
        "employee_number": "1001",
        "name": "张三",
        "domain_account": "zhangsan",
        "gender": "男",
        "ethnic_group": "汉",
        "native_place": "广东",
        "political_status": "党员",
        "marital_status": "未婚",
        "health_status": "健康",
        "household_type": "城镇",
        "status_category": "正式",
        "birth_year": 1990,
        "birth_month": 1,
        "birth_day": 2,
        "age": 36,
        "id_card": "440000000000000000",
        "id_card_expiry": "2030-01-01",
        "current_address": "珠海",
        "phone": "13800000000",
        "email": "a@example.com",
        "emergency_contact_name": "李四",
        "emergency_contact_phone": "13900000000",
        "emergency_contact_relation": "家属",
        "department": "质量部",
        "sub_department": "QA",
        "position": "质量员",
        "level": "初级",
        "employment_type": "正式",
        "probation_status": "已转正",
        "probation_effective_date": date(2021, 1, 1),
        "hire_date": date(2020, 1, 1),
        "work_start_date": date(2012, 1, 1),
        "factory_entry_date": date(2020, 1, 1),
        "work_years": "14",
        "offboarding_date": date(2026, 8, 20),
        "offboarding_type": "辞职",
        "reason": "个人原因",
        "status": "在职",
        "education": "本科",
        "degree": "学士",
        "major": "化学",
        "school": "大学",
        "graduation_date": date(2012, 6, 1),
        "qualification_type": "工程师",
        "qualifications": ["GMP", "安全员"],
        "certificate_number": "C-1",
        "certificate_review_date": date(2027, 1, 1),
        "contract_start_date": date(2024, 1, 1),
        "contract_end_date": date(2027, 1, 1),
        "contract_end_2": "2029-01-01",
        "contract_end_3": None,
        "contract_end_4": None,
        "contract_end_5": None,
        "contract_start_2": date(2027, 1, 2),
        "contract_start_3": "2029-01-02",
        "contract_start_4": None,
        "contract_start_5": None,
        "contract_start_6": None,
        "work_experience_1": "经历一",
        "work_experience_2": None,
        "work_experience_3": None,
        "work_experience_4": None,
        "archive_number": "A-1",
        "notes": "备注",
        "feishu_record_id": None,
        "feishu_synced_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_offboarding_feishu_mapping_create_update_delete_and_list() -> None:
    record = _offboarding_record()
    employee = SimpleNamespace(
        status="离职",
        planned_probation_date=date(2026, 9, 1),
    )
    client = SimpleNamespace(
        create_record=AsyncMock(return_value={"record_id": "off-1"}),
        update_record=AsyncMock(),
        delete_record=AsyncMock(),
    )
    repo = SimpleNamespace(
        update=AsyncMock(),
        list_records=AsyncMock(return_value=([record], 1)),
        soft_delete=AsyncMock(),
    )
    instance = service.OffboardingRecordService.__new__(
        service.OffboardingRecordService
    )
    instance.repo = repo
    instance._get_offboarding_bitable = AsyncMock(return_value=(client, "tbl-off"))

    await instance._sync_to_feishu(record, employee, is_create=True)
    assert record.feishu_record_id == "off-1"
    assert repo.update.await_count == 1
    fields = client.create_record.await_args.args[1]
    assert fields["姓名"] == "张三"
    assert fields["出生年月"] == "1990-01-02"
    assert fields["技能证书"] == "GMP、安全员"

    record.feishu_record_id = "off-1"
    await instance._sync_to_feishu(record, employee, is_create=False)
    client.update_record.assert_awaited_once()
    await instance._delete_from_feishu(record)
    client.delete_record.assert_awaited_once_with("tbl-off", "off-1")
    await instance._delete_from_feishu(_offboarding_record(feishu_record_id=None))
    assert await instance.list_records(employee_id=record.employee_id) == ([record], 1)


@pytest.mark.asyncio
async def test_offboarding_sync_from_feishu_upserts_and_marks_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setting = SimpleNamespace(app_token="app", base_table_id="tbl")
    execute_result = SimpleNamespace(scalar_one_or_none=lambda: setting)
    stale = SimpleNamespace(feishu_record_id="off-old", is_deleted=False)
    employee = SimpleNamespace(id=uuid4())
    record = {
        "record_id": "off-1",
        "fields": {
            "工号": "1001",
            "姓名": "张三",
            "最后工作日": "2026-08-20",
            "职称／职业资格": ["GMP"],
        },
    }
    client = SimpleNamespace(search_records=AsyncMock(return_value=[record, {}]))
    monkeypatch.setattr(
        "app.modules.hr.feishu.bitable.BitableClient", lambda **_kwargs: client
    )
    monkeypatch.setattr(
        service,
        "get_hr_feishu_app_credentials",
        AsyncMock(return_value=("id", "secret")),
    )
    repo = SimpleNamespace(
        get_by_employee_number=AsyncMock(return_value=employee),
        get_by_feishu_record_id=AsyncMock(return_value=None),
        list_all=AsyncMock(return_value=[stale]),
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=execute_result),
        add=Mock(),
        commit=AsyncMock(),
    )
    instance = service.OffboardingRecordService.__new__(
        service.OffboardingRecordService
    )
    instance.session = session
    instance.repo = repo
    instance.employee_repo = SimpleNamespace(
        get_by_employee_number=repo.get_by_employee_number
    )

    stats = await instance.sync_from_feishu()
    assert stats == {"created": 1, "updated": 0, "deleted": 1, "failed": 1, "total": 2}
    session.add.assert_called_once()
    assert stale.is_deleted is True
    session.commit.assert_awaited_once()


def _position_record(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "employee_name": "张三",
        "employee_number": "1001",
        "department_before": "质量部",
        "original_position": "质量员",
        "apply_department": "仓储部",
        "apply_position": "主管",
        "effective_date": date(2026, 9, 1),
        "transfer_reason": "组织调整",
        "contact_phone": "13800000000",
        "applicant_confirmation_text": "本人确认",
        "applicant_signature": "张三",
        "applicant_confirmation_date": date(2026, 8, 20),
        "approval_status": "草稿",
        "approver": None,
        "approval_date": None,
        "approval_flow": {
            "steps": [
                {
                    "node": "origin_manager",
                    "status": "approved",
                    "opinion": "同意",
                    "signer": "经理",
                    "date": "2026.08.20",
                },
                {
                    "node": "target_manager",
                    "status": "approved",
                    "opinion": "接收",
                    "signer_open_id": "ou-manager",
                    "date": "bad-date",
                },
            ]
        },
        "remarks": None,
        "feishu_record_id": None,
        "feishu_synced_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_position_transfer_mapping_sync_and_approval_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _position_record()
    client = SimpleNamespace(
        create_record=AsyncMock(return_value={"record_id": "move-1"}),
        update_record=AsyncMock(),
        delete_record=AsyncMock(),
        search_records=AsyncMock(return_value=[]),
    )
    instance = service.PositionTransferRecordService.__new__(
        service.PositionTransferRecordService
    )
    instance._get_position_bitable = AsyncMock(return_value=(client, "tbl-move"))
    instance._get_open_id_by_name = AsyncMock(return_value="ou-applicant")
    instance.repo = SimpleNamespace(update=AsyncMock(), create=AsyncMock())

    fields = await instance._build_feishu_fields(record)
    assert fields["申请人"] == "张三"
    assert fields["申请人签名"] == [{"id": "ou-applicant"}]
    assert fields["原部门/经理总监意见"] == "同意"
    assert fields["接收部门/经理总监签名"] == [{"id": "ou-manager"}]
    assert "接收部门经理/总监日期" not in fields

    await instance._sync_to_feishu(record, is_create=True)
    assert record.feishu_record_id == "move-1"
    record.feishu_record_id = "move-1"
    await instance._sync_to_feishu(record, is_create=False)
    client.update_record.assert_awaited_once()
    await instance._delete_from_feishu(record)
    client.delete_record.assert_awaited_once_with("tbl-move", "move-1")

    instance._get_position_bitable = AsyncMock(return_value=None)
    with pytest.raises(AppException):
        await instance.sync_from_feishu()
    monkeypatch.setattr(
        instance,
        "_get_position_bitable",
        AsyncMock(return_value=(client, "tbl-move")),
    )
    client.search_records.return_value = [
        {
            "record_id": "move-2",
            "fields": {
                "申请人": "李四",
                "原部门": "生产部",
                "原职位": "操作员",
                "申请部门": "质量部",
                "申请职位": "质量员",
                "生效日期": "2026-09-01",
            },
        }
    ]
    local = SimpleNamespace(
        feishu_record_id="move-old", is_deleted=False, employee_name="旧"
    )
    instance.repo.get_by_feishu_record_id = AsyncMock(return_value=None)
    instance.repo.list_all_with_feishu_id = AsyncMock(return_value=[local])
    instance.repo.create = AsyncMock()
    stats = await instance.sync_from_feishu()
    assert stats["created"] == 1
    assert stats["deleted"] == 1
    assert local.is_deleted is True


@pytest.mark.asyncio
async def test_legacy_record_service_sync_status_and_failure_paths() -> None:
    repo = SimpleNamespace(
        upsert_by_feishu_record_id=AsyncMock(),
        get_by_feishu_record_id=AsyncMock(
            return_value=SimpleNamespace(created_at=datetime.now())
        ),
        count_total=AsyncMock(return_value=3),
        count_synced=AsyncMock(return_value=2),
    )
    bitable = SimpleNamespace(
        table_id="tbl",
        client=SimpleNamespace(
            search_records=AsyncMock(
                return_value=[
                    {"record_id": "r1"},
                    {"record_id": ""},
                    {"record_id": "r2"},
                ]
            ),
        ),
    )
    instance = service._LegacyFeishuRecordService()
    instance.repo = repo
    instance.bitable = bitable
    instance._parse_feishu_record = AsyncMock(
        side_effect=[
            {"feishu_record_id": "r1", "name": "张三"},
            {"feishu_record_id": None},
            RuntimeError("bad record"),
        ]
    )
    stats = await instance.sync_from_feishu()
    assert stats == {"created": 1, "updated": 0, "failed": 2, "total": 3}
    status = await instance.get_sync_status()
    assert status.local_total == 3
    assert status.unsynced_count == 1
    repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException):
        await instance.get_record(uuid4())


@pytest.mark.asyncio
async def test_training_ledger_create_update_delete_conflict_and_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid4()
    session_result = SimpleNamespace(scalar_one_or_none=lambda: "质量部")
    repo = SimpleNamespace(
        create=AsyncMock(side_effect=lambda value: value),
        get_by_id=AsyncMock(),
        update=AsyncMock(),
        sync_by_session_id=AsyncMock(),
        mark_owner_deleted=AsyncMock(),
        soft_delete=AsyncMock(),
        delete_all_by_department=AsyncMock(return_value=2),
        list_by_date=AsyncMock(),
        get_by_source=AsyncMock(return_value=None),
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=session_result),
        get=AsyncMock(return_value=SimpleNamespace(department="质量部")),
    )
    instance = service.TrainingLedgerService.__new__(service.TrainingLedgerService)
    instance.session = session
    instance.repo = repo
    monkeypatch.setattr(
        "app.modules.hr.training_dept_resolver.split_ledger_departments",
        AsyncMock(side_effect=lambda _session, name: [name]),
    )

    created = await instance.create_record(
        TrainingLedgerCreate(
            training_date=date(2026, 8, 20),
            training_subject="GMP 培训",
            instructor="王老师",
            teaching_dept="原部门",
            involved_depts="质量部、生产部",
            ledger_department="质量部",
            session_id=session_id,
        )
    )
    assert created.teaching_dept == "质量部"
    assert created.second_level_status == "pending"
    assert repo.create.await_count == 2

    record = SimpleNamespace(
        id=uuid4(),
        session_id=session_id,
        ledger_department="质量部",
        training_datetime="2026.08.20 09:00~10:00",
        training_date=date(2026, 8, 20),
        training_subject="GMP",
        training_content="内容",
        instructor="王老师",
        trainer="王老师",
        teaching_dept="质量部",
        trainees="张三、李四",
        score_summary="张三:95",
        ledger_assessment_method="考试",
        remarks=None,
    )
    repo.get_by_id.return_value = record
    updated = await instance.update_record(
        record.id,
        TrainingLedgerUpdate(training_content="更新内容", assessment_result="合格"),
    )
    assert updated.training_content == "更新内容"
    repo.sync_by_session_id.assert_awaited_once()
    await instance.delete_record(record.id)
    repo.mark_owner_deleted.assert_awaited_once_with(
        session_id=session_id, exclude_id=record.id
    )
    repo.soft_delete.assert_awaited_once_with(record)
    assert await instance.delete_by_department("质量部") == 2

    ledger = SimpleNamespace(
        training_datetime="2026.08.20 09:00~10:00",
        training_subject="台账培训",
        instructor="王老师",
        teaching_dept="质量部",
        trainees="张三、李四",
        training_date=date(2026, 8, 20),
    )
    session_training = SimpleNamespace(
        id=uuid4(),
        time_start="09:30",
        time_end="10:30",
        topic="会话培训",
        department="生产部",
        instructor="王老师",
        employee_names=["张三"],
    )
    repo.list_by_date.return_value = [ledger]
    session.execute.return_value = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [session_training])
    )
    conflict = await instance.check_conflict(
        date(2026, 8, 20), "09:15", "10:15", "王老师", ["张三"]
    )
    assert conflict["has_conflict"] is True
    assert conflict["instructor_conflicts"]
    assert conflict["trainee_conflicts"]

    repo.get_by_source.return_value = SimpleNamespace(id=uuid4())
    existing = await instance.create_from_notification(
        employee_number="1001",
        training_date=date(2026, 8, 20),
        training_subject="通知培训",
        training_method="线上",
        trainer="王老师",
        source_id="notice-1",
    )
    assert existing is repo.get_by_source.return_value


@pytest.mark.asyncio
async def test_employee_training_list_import_summary_and_mutations() -> None:
    configured = [
        SimpleNamespace(
            id=uuid4(),
            department="质量部",
            name="张三",
            employee_number="1001",
            source="manual",
        ),
        SimpleNamespace(
            id=uuid4(),
            department="质量部",
            name="公用账号",
            employee_number=None,
            source="feishu",
        ),
    ]
    member = SimpleNamespace(
        id=uuid4(),
        department="质量部",
        name="李四",
        employee_number="1002",
        source="manual",
    )
    ledger = SimpleNamespace(
        trainees="张三、李四",
        training_date=date(2026, 8, 20),
        session_id=uuid4(),
        training_datetime="09:00~10:00",
        training_content="GMP",
        score_summary="张三:95",
        ledger_assessment_method="考试",
        remarks="通过",
    )
    member_repo = SimpleNamespace(
        list_by_department=AsyncMock(return_value=configured),
        upsert_member=AsyncMock(return_value=member),
        get_by_id=AsyncMock(return_value=member),
        soft_delete=AsyncMock(),
    )
    employee_repo = SimpleNamespace(
        list_by_department_for_auto=AsyncMock(
            return_value=[("张三", "1001"), ("王五", "1005")]
        )
    )
    ledger_repo = SimpleNamespace(
        list_all_for_employee_list=AsyncMock(return_value=[ledger, ledger])
    )
    instance = service.EmployeeTrainingListService.__new__(
        service.EmployeeTrainingListService
    )
    instance.member_repo = member_repo
    instance.employee_repo = employee_repo
    instance.ledger_repo = ledger_repo
    instance.session = SimpleNamespace(flush=AsyncMock())

    members = await instance.list_employee_members("质量部")
    assert [item["name"] for item in members] == ["张三", "王五"]
    summary = await instance.list_employee_training_summary("质量部")
    assert summary[0]["record_count"] == 1
    records = await instance.get_employee_training_records("张三")
    assert records[0]["personal_score"] == "95"
    added = await instance.add_member("质量部", "赵六", "1006")
    assert added["name"] == "李四"
    await instance.remove_member(member.id)
    member_repo.soft_delete.assert_awaited_once_with(member)
    renamed = await instance.update_member_name(member.id, "李四改名")
    assert renamed["name"] == "李四改名"


@pytest.mark.asyncio
async def test_position_transfer_approval_submit_approve_reject_and_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _position_record(approval_status="草稿", approval_flow=None)
    query_result = SimpleNamespace(scalar_one_or_none=lambda: record)
    session = SimpleNamespace(execute=AsyncMock(return_value=query_result))
    repo = SimpleNamespace(update=AsyncMock(side_effect=lambda value: value))
    instance = service.PositionTransferRecordService.__new__(
        service.PositionTransferRecordService
    )
    instance.session = session
    instance.repo = repo

    async def resolve(_record: object, node: str) -> tuple[str | None, str | None]:
        if node == "applicant":
            return "张三", None
        if node.endswith("manager"):
            return "部门经理", "ou-manager"
        return None, None

    instance._resolve_approver = AsyncMock(side_effect=resolve)
    instance._sync_to_feishu = AsyncMock()
    instance._notify_next_approver = AsyncMock()
    submitted = await instance._do_submit_for_approval(
        record.id,
        SimpleNamespace(is_supervisor_level=False, custom_approvers={}),
    )
    assert submitted.approval_status == "待审批"
    assert submitted.approval_flow["steps"][0]["status"] == "approved"
    assert any(step["status"] == "pending" for step in submitted.approval_flow["steps"])
    instance._sync_to_feishu.assert_awaited_once()
    instance._notify_next_approver.assert_awaited_once()

    approved = await instance._do_approve_current_node(
        record.id, SimpleNamespace(opinion="同意")
    )
    assert any(
        step["status"] == "approved" and step["opinion"] == "同意"
        for step in approved.approval_flow["steps"]
    )

    record.approval_flow = {
        "current_step": 0,
        "steps": [
            {
                "node": "applicant",
                "status": "pending",
                "signer": "张三",
                "signer_open_id": "",
            }
        ],
    }
    record.approval_status = "待审批"
    finished = await instance._do_approve_current_node(
        record.id, SimpleNamespace(opinion="同意")
    )
    assert finished.approval_status == "已通过"

    record.approval_flow = {
        "current_step": 0,
        "steps": [
            {
                "node": "applicant",
                "status": "pending",
                "signer": "张三",
                "signer_open_id": "",
            }
        ],
    }
    instance._notify_applicant_rejected = AsyncMock()
    rejected = await instance.reject_current_node(
        record.id, SimpleNamespace(opinion="补充材料")
    )
    assert rejected.approval_status == "已拒绝"
    instance._notify_applicant_rejected.assert_awaited_once_with(record)

    config = SimpleNamespace(
        manager_name="经理",
        manager_open_id="ou-manager",
        direct_leader_name="直属",
        direct_leader_open_id="ou-direct",
        director_name="总监",
        director_open_id="ou-director",
        vp_name="分管领导",
        vp_open_id="ou-vp",
    )
    instance._get_dept_approval_config = AsyncMock(return_value=config)
    assert await service.PositionTransferRecordService._resolve_approver(
        instance, record, "origin_manager"
    ) == (
        "经理",
        "ou-manager",
    )
    assert await service.PositionTransferRecordService._resolve_approver(
        instance, record, "origin_direct_leader"
    ) == (
        "直属",
        "ou-direct",
    )
    assert await service.PositionTransferRecordService._resolve_approver(
        instance, record, "applicant"
    ) == ("张三", None)
    instance._get_dept_approval_config = AsyncMock(return_value=None)
    assert await service.PositionTransferRecordService._resolve_approver(
        instance, record, "origin_manager"
    ) == (None, None)
