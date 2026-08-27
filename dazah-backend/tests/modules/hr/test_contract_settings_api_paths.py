from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.hr import contract_settings_api as api
from app.modules.hr.contract_settings_schemas import (
    ApprovalConfigUpdate,
    DeptRecipientCreate,
    ReminderConfigUpdate,
)


class _Result:
    def __init__(self, values: list[object] | None = None, scalar: int = 0) -> None:
        self.values = values or []
        self.scalar_value = scalar
        self.rowcount = scalar

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.values

    def scalar(self) -> int:
        return self.scalar_value


def _config(config_id=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=config_id or uuid4(),
        entity_code="offboarding",
        entity_label="离职管理",
        module_group="人事",
        reminder_type="offboarding_due",
        reminder_label="离职提醒",
        reminder_days=[30, 15, 7],
        recipient_open_ids=["u1"],
        dept_notify_enabled=True,
        trigger_frequency="monthly",
        trigger_day=1,
        trigger_hour=9,
        notify_hours=24,
        message_template="提醒",
        sign_clerk_open_ids=[],
        sign_clerk_names=[],
        sign_reminder_days=7,
        is_enabled=True,
        sort_order=1,
    )


def _approval(config_id=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=config_id or uuid4(),
        entity_code="offboarding",
        entity_label="离职管理",
        module_group="人事",
        role="hr",
        role_label="人事",
        approver_open_ids=["u1"],
        approver_names=["张三"],
        deadline_days=3,
        sort_order=1,
    )


def _recipient(config_id) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        reminder_config_id=config_id,
        department="质量部",
        recipient_open_ids=["u1"],
        recipient_names=["张三"],
        use_dept_leader=True,
    )


@pytest.mark.asyncio
async def test_contract_settings_crud_and_job_status_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "_require_user", Mock())
    user = SimpleNamespace(id=uuid4())
    config = _config()
    approval = _approval()
    recipient = _recipient(config.id)
    service = SimpleNamespace(
        ensure_default_offboarding_config=AsyncMock(return_value=config),
        list_reminder_configs=AsyncMock(return_value=[config]),
        update_reminder_config=AsyncMock(return_value=config),
        list_approval_configs=AsyncMock(return_value=[approval]),
        update_approval_config=AsyncMock(return_value=approval),
        list_dept_recipients=AsyncMock(return_value=[recipient]),
        upsert_dept_recipient=AsyncMock(return_value=recipient),
        delete_dept_recipient=AsyncMock(),
    )
    response = await api.list_reminder_configs(user, service)
    assert response.status_code == 200
    response = await api.update_reminder_config(
        config.id, ReminderConfigUpdate(is_enabled=False), user, service
    )
    assert response.status_code == 200
    response = await api.list_approval_configs(user, service)
    assert response.status_code == 200
    response = await api.update_approval_config(
        approval.id, ApprovalConfigUpdate(deadline_days=5), user, service
    )
    assert response.status_code == 200
    response = await api.list_dept_recipients(config.id, user, service)
    assert response.status_code == 200
    response = await api.batch_save_dept_recipients(
        config.id,
        [
            DeptRecipientCreate(
                reminder_config_id="ignored",
                department="质量部",
                recipient_open_ids=["u2"],
            )
        ],
        user,
        service,
    )
    assert response.status_code == 200
    response = await api.delete_dept_recipient(recipient.id, user, service)
    assert response.status_code == 200

    import app.core.jobs as jobs

    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=False))
    monkeypatch.setattr(jobs, "submit_job", AsyncMock())
    response = await api.sync_hr_members(user)
    assert response.status_code == 200
    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=True))
    response = await api.sync_hr_members(user)
    assert response.status_code == 200
    monkeypatch.setattr(jobs, "get_job_status", AsyncMock(return_value=None))
    response = await api.get_members_sync_status(user)
    assert response.status_code == 200
    monkeypatch.setattr(
        jobs, "get_job_status", AsyncMock(return_value={"state": "completed"})
    )
    response = await api.get_members_sync_status(user)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_contract_settings_member_filters_templates_and_bulk_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(api, "_require_user", Mock())
    user = SimpleNamespace(id=uuid4())
    now = datetime.now(UTC)
    member = SimpleNamespace(
        id=uuid4(),
        name="张三",
        open_id="ou-1",
        department="质量部",
        employee_no="E1",
        mobile="13800000000",
        email="z@example.com",
        enterprise_email=None,
        job_title="质量员",
        gender="男",
        avatar_url=None,
        status="1",
        status_changed_at=now,
        synced_at=now,
        is_deleted=False,
    )

    import app.modules.hr.api as hr_api

    monkeypatch.setattr(hr_api, "_resolve_visible_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(hr_api, "_assert_dept_in_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(api, "_sync_feishu_members_background", AsyncMock())
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Result([member]), _Result([member])])
    )
    response = await api.list_hr_members(False, user, db)
    assert response.status_code == 200

    monkeypatch.setattr(api, "_sync_feishu_members", AsyncMock())
    db.execute = AsyncMock(side_effect=[_Result([]), _Result([member])])
    response = await api.list_hr_members(True, user, db)
    assert response.status_code == 200

    dept = SimpleNamespace(id="d1", name="质量部", parent_id=None, sort_order=1)
    monkeypatch.setattr(
        api,
        "_department_display_map",
        AsyncMock(return_value=({"质量部": "质量部"}, {"质量部": 1})),
    )
    db.execute = AsyncMock(side_effect=[_Result(scalar=1), _Result([member])])
    response = await api.list_feishu_members(
        user, db, page=1, page_size=20, keyword="质量", department="质量部", status="1"
    )
    assert response.status_code == 200
    db.execute = AsyncMock(side_effect=[_Result([("质量部",)]), _Result([dept])])
    response = await api.list_feishu_member_departments(user, db)
    assert response.status_code == 200

    template_path = tmp_path / "offboarding.docx"
    monkeypatch.setattr(api, "OFFBOARDING_TEMPLATE_PATH", template_path)
    monkeypatch.setattr(
        api, "read_upload_secure", AsyncMock(return_value=("模板.docx", b"docx"))
    )
    response = await api.upload_offboarding_template(
        SimpleNamespace(filename="模板.docx"), user
    )
    assert response.status_code == 200 and template_path.read_bytes() == b"docx"
    response = await api.get_offboarding_template_info(user)
    assert response.status_code == 200

    db.execute = AsyncMock(
        side_effect=[_Result(scalar=2), _Result([uuid4()]), _Result(scalar=2)]
    )
    db.commit = AsyncMock()
    response = await api.delete_reminders_by_entity("onboarding,offboarding", user, db)
    assert response.status_code == 200
    db.execute = AsyncMock(return_value=_Result(scalar=3))
    response = await api.delete_approvals_by_entity("recruitment", user, db)
    assert response.status_code == 200
