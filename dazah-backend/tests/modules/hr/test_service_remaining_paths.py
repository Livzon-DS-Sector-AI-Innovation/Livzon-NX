from __future__ import annotations

from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.hr import service
from app.modules.hr.schemas import EmployeeCreate, OffboardingRecordCreate


@pytest.mark.asyncio
async def test_employee_create_without_session_and_feishu_failure() -> None:
    instance = service.EmployeeService.__new__(service.EmployeeService)
    employee = SimpleNamespace(status="在职", feishu_record_id=None)
    instance.repo = SimpleNamespace(
        get_by_employee_number=AsyncMock(return_value=None),
        create=AsyncMock(return_value=employee),
        update=AsyncMock(),
    )
    instance._get_bitable = AsyncMock(side_effect=RuntimeError("feishu down"))
    result = await instance.create_employee(
        EmployeeCreate(
            employee_number="",
            name="新员工",
            department="质量部",
            position="专员",
            hire_date=date(2026, 8, 26),
        )
    )
    assert result is employee
    assert employee.status == "在职"


@pytest.mark.asyncio
async def test_offboarding_create_updates_employee_and_sends_materials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employee = SimpleNamespace(
        id=uuid4(), status="在职", name="张三", feishu_open_id="ou-1"
    )
    repo = SimpleNamespace(
        create=AsyncMock(side_effect=lambda value: value), update=AsyncMock()
    )
    employee_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=employee), update=AsyncMock()
    )
    instance = service.OffboardingRecordService.__new__(
        service.OffboardingRecordService
    )
    instance.repo = repo
    instance.employee_repo = employee_repo
    instance.session = SimpleNamespace()
    instance._sync_to_feishu = AsyncMock()
    notification = AsyncMock()
    monkeypatch.setattr(
        "app.modules.hr.feishu.notification.send_user_card", notification
    )
    # 离职材料卡片改由人事专属应用发送：隔离 DB 凭证解析
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )

    result = await instance.create_record(
        OffboardingRecordCreate(
            employee_id=employee.id,
            name="张三",
            employee_number="E001",
            offboarding_date=date(2026, 8, 26),
            offboarding_type="辞职",
        )
    )
    assert result.employee_id == employee.id
    # 离职语义重构：创建「在职」状态的离职台账不联动改员工状态；
    # 仅当 status=离职 时才转抄员工档案并软删员工
    assert employee.status == "在职"
    assert notification.await_count == 1
    assert result.materials_sent is True

    # 离职联动分支：status=离职 → 员工同步离职 + 软删
    employee_repo.soft_delete = AsyncMock()
    employee2 = SimpleNamespace(
        id=uuid4(), status="在职", name="李四", feishu_open_id="ou-2"
    )
    employee_repo.get_by_id.return_value = employee2
    instance._snapshot_employee = AsyncMock()
    departed = await instance.create_record(
        OffboardingRecordCreate(
            employee_id=employee2.id,
            name="李四",
            employee_number="E002",
            offboarding_date=date(2026, 8, 26),
            offboarding_type="辞职",
            status="离职",
        )
    )
    assert departed.status == "离职"
    assert employee2.status == "离职"
    employee_repo.soft_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_termination_certificate_upload_and_missing_employee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = SimpleNamespace(
        employee_id=uuid4(), completed_date=None, status=None, hire_date=None,
        name="张三", employee_number="E001",
    )
    employee = SimpleNamespace(
        name="张三",
        gender="男",
        id_card="ID",
        hire_date=date(2020, 1, 2),
        current_address="珠海",
    )
    repo = SimpleNamespace(update=AsyncMock())
    instance = service.OffboardingRecordService.__new__(
        service.OffboardingRecordService
    )
    instance.repo = repo
    instance.employee_repo = SimpleNamespace(
        get_by_id_include_deleted=AsyncMock(return_value=employee),
        get_by_employee_number_include_deleted=AsyncMock(return_value=None),
    )
    instance.get_record = AsyncMock(return_value=record)
    monkeypatch.setattr(
        "app.modules.hr.offboarding_document_generator.generate_termination_notice",
        lambda data: BytesIO(b"docx"),
    )
    monkeypatch.setattr("app.core.storage.is_enabled", lambda: True)
    upload = Mock()
    monkeypatch.setattr("app.core.storage.upload_object", upload)

    output, filename, updated = await instance.generate_termination_certificate(uuid4())
    assert output.getvalue() == b"docx"
    assert filename.startswith("张三_")
    # 离职语义重构：完成通知单不再回写交接状态，仅记录完成日期
    assert updated.completed_date is not None
    upload.assert_called_once()

    # 离职语义重构：员工已软删/未关联时回退离职台账快照字段，仍可生成通知单
    instance.employee_repo.get_by_id_include_deleted.return_value = None
    output2, filename2, updated2 = await instance.generate_termination_certificate(
        uuid4()
    )
    assert output2.getvalue() == b"docx"
    assert filename2.startswith("张三_")


@pytest.mark.asyncio
async def test_position_transfer_notifications_and_approval_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = service.PositionTransferRecordService.__new__(
        service.PositionTransferRecordService
    )
    instance.session = SimpleNamespace()
    # 岗位调动审批卡片改由人事专属应用发送：隔离 DB 凭证解析
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )
    record = SimpleNamespace(
        id=uuid4(),
        employee_name="张三",
        department_before="质量部",
        apply_department="生产部",
        original_position="质量员",
        apply_position="操作员",
        approval_flow={
            "current_step": 0,
            "steps": [
                {
                    "node": "hr",
                    "label": "人力",
                    "signer": "李四",
                    "signer_open_id": "ou-1",
                }
            ],
        },
        feishu_approval_message_id=None,
    )
    monkeypatch.setattr("app.core.redis.cache_get", AsyncMock(return_value=None))
    cache_set = AsyncMock()
    monkeypatch.setattr("app.core.redis.cache_set", cache_set)
    send_card = AsyncMock(return_value="msg-1")
    monkeypatch.setattr(
        "app.modules.hr.feishu.notification.send_user_card_with_message_id",
        send_card,
    )
    await instance._notify_next_approver(record)
    assert record.feishu_approval_message_id == "msg-1"
    cache_set.assert_awaited_once()

    monkeypatch.setattr("app.core.redis.cache_get", AsyncMock(return_value="sent"))
    await instance._notify_next_approver(record)
    record.approval_flow = {
        "current_step": 2,
        "steps": [record.approval_flow["steps"][0]],
    }
    await instance._notify_next_approver(record)
    record.approval_flow = {"current_step": 0, "steps": [{"signer": "李四"}]}
    await instance._notify_next_approver(record)

    class _Result:
        def __init__(self, rows: list[object], scalar_value: int = 0) -> None:
            self.rows = rows
            self.scalar_value = scalar_value

        def scalar(self) -> int:
            return self.scalar_value

        def scalars(self) -> _Result:
            return self

        def all(self) -> list[object]:
            return self.rows

    my_record = SimpleNamespace(id=uuid4())
    instance.session.execute = AsyncMock(
        side_effect=[_Result([], 1), _Result([my_record])]
    )
    records, total = await instance.list_approvals(
        current_user=SimpleNamespace(name="张三", feishu_open_id="ou-1"),
        tab="my_applications",
    )
    assert records == [my_record] and total == 1

    pending = SimpleNamespace(
        approval_flow={
            "current_step": 0,
            "steps": [{"signer_open_id": "ou-1", "status": "pending"}],
        }
    )
    approved = SimpleNamespace(
        approval_flow={
            "current_step": 1,
            "steps": [{"signer": "李四", "status": "approved"}],
        }
    )
    instance.session.execute = AsyncMock(return_value=_Result([pending, approved]))
    records, total = await instance.list_approvals(
        current_user=SimpleNamespace(name="李四", feishu_open_id="ou-1"),
        tab="pending_approval",
    )
    assert records == [pending] and total == 1
    records, total = await instance.list_approvals(
        current_user=SimpleNamespace(name="李四", feishu_open_id="other"),
        tab="approved",
    )
    assert records == [approved] and total == 1
