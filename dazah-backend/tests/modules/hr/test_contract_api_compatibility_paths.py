"""Coverage for the compatibility contract approval and export endpoints."""

import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class _Result:
    def __init__(self, one: object | None = None) -> None:
        self.one = one

    def scalar_one_or_none(self) -> object | None:
        return self.one


def _app_credentials_row() -> SimpleNamespace:
    """测试用 HrFeishuAppSettings 行（已启用 + 有效凭证）。"""
    return SimpleNamespace(
        app_id="cli_hr_test", app_secret="enc-hr-secret", is_enabled=True
    )


def _contract_record(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "employee_number": "E-100",
        "name": "合同员工",
        "gender": "男",
        "dept_level1": "质量部",
        "dept_level2": "检验组",
        "position": "检验员",
        "job_level": "初级",
        "domain_account": "contract-user",
        "id_card": "440000000000000000",
        "id_card_expiry": "2035-01-01",
        "archive_number": "A-100",
        "contract_sequence": "第二次",
        "contract_start_1": date(2022, 1, 1),
        "contract_end_1": date(2024, 1, 1),
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
        "dept_leader_name": "部门负责人",
        "contract_opinion": None,
        "approval_status": "approved",
        "supervisor_name": "分管领导",
        "supervisor_open_id": "ou-supervisor",
        "dept_approved_at": datetime(2026, 8, 1),
        "supervisor_approved_at": datetime(2026, 8, 2),
        "signed_status": "待签署",
        "signed_at": None,
        "sign_reminded_at": None,
        "feishu_record_id": None,
        "feishu_synced_at": None,
        "created_at": datetime(2026, 7, 1),
        "updated_at": datetime(2026, 7, 1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _employee(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "gender": "男",
        "department": "质量部",
        "sub_department": "检验组",
        "position": "检验员",
        "level": "初级",
        "domain_account": "contract-user",
        "id_card": "440000000000000000",
        "id_card_expiry": "2035-01-01",
        "archive_number": "A-100",
        "contract_start_date": date(2022, 1, 1),
        "contract_end_date": date(2024, 1, 1),
        "contract_start_2": date(2024, 1, 2),
        "contract_end_2": "2026/01/01",
        "contract_start_3": None,
        "contract_end_3": None,
        "contract_start_4": None,
        "contract_end_4": None,
        "contract_start_5": None,
        "contract_end_5": "2028-01-01",
        "contract_start_6": None,
        "contract_end_6": "bad-date",
        "employee_number": "E-100",
        "name": "合同员工",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def test_compute_renew_sequence_and_create_record_cover_legacy_dates() -> None:
    from app.modules.hr import contract_api

    assert contract_api._compute_renew_seq(None) == 0
    assert (
        contract_api._compute_renew_seq(
            _employee(contract_end_5="2029/01/01", contract_end_6="bad")
        )
        == 5
    )
    assert (
        contract_api._compute_renew_seq(
            _employee(contract_end_5="bad", contract_end_6="2030-01-01")
        )
        == 6
    )


@pytest.mark.asyncio
async def test_create_contract_record_copies_employee_and_sequence() -> None:
    from app.modules.hr import contract_api

    db = MagicMock()
    db.flush = AsyncMock()
    record = await contract_api._create_contract_record(
        db,
        _employee(),
        "E-100",
        "合同员工",
        "部门负责人",
        renew=True,
    )

    assert record.employee_number == "E-100"
    assert record.gender == "男"
    assert record.contract_end_2 == "2026/01/01"
    assert record.contract_sequence == "第六次"
    db.add.assert_called_once_with(record)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_renew_contract_writes_date_fields_and_syncs_both_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.hr import contract_api
    from app.modules.hr.contract_schemas import ContractRenewRequest

    record = _contract_record(contract_sequence="第二次")
    employee = _employee()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(record), _result(employee)])
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    class _Response:
        @classmethod
        def model_validate(cls, value: object) -> "_Response":
            instance = cls()
            instance.value = value
            return instance

        def model_dump(self, *, mode: str) -> dict[str, str]:
            del mode
            return {"employee_number": self.value.employee_number}

    monkeypatch.setattr(contract_api, "ContractManagementResponse", _Response)
    with patch("app.modules.hr.contract_sync_service.ContractSyncService") as sync_cls:
        sync_cls.return_value.push_create = AsyncMock()
        with patch("app.modules.hr.service.EmployeeService") as employee_service_cls:
            employee_service_cls.return_value._sync_single_to_feishu = AsyncMock()
            response = await contract_api.renew_contract(
                record.id,
                ContractRenewRequest(start_date="2026-09-01", end_date="2029-08-31"),
                db=db,
                current_user=object(),
            )

    assert record.contract_start_2 == date(2026, 9, 1)
    assert record.contract_end_2 == "2029-08-31"
    assert employee.contract_start_2 == date(2026, 9, 1)
    assert employee.contract_end_2 == date(2029, 8, 31)
    assert json.loads(response.body)["data"]["employee_number"] == "E-100"
    db.commit.assert_awaited_once()
    sync_cls.return_value.push_create.assert_awaited_once_with(record)


@pytest.mark.asyncio
async def test_renew_contract_rejects_missing_invalid_and_unknown_dates() -> None:
    from app.core.exceptions import AppException
    from app.modules.hr import contract_api
    from app.modules.hr.contract_schemas import ContractRenewRequest

    for request in (
        ContractRenewRequest.model_construct(start_date="", end_date=""),
        ContractRenewRequest(start_date="not-a-date", end_date="2029-01-01"),
    ):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_result(_contract_record()))
        with pytest.raises(AppException):
            await contract_api.renew_contract(
                uuid4(), request, db=db, current_user=object()
            )

    record = _contract_record(contract_sequence="未知")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(record))
    with pytest.raises(AppException):
        await contract_api.renew_contract(
            record.id,
            ContractRenewRequest(start_date="2026-09-01", end_date="2029-08-31"),
            db=db,
            current_user=object(),
        )


@pytest.mark.asyncio
async def test_export_contract_approval_results_builds_workbook() -> None:
    from app.modules.hr import contract_api

    approved = _contract_record(
        approval_status="approved", supervisor_approved_at=datetime(2026, 8, 2)
    )
    rejected = _contract_record(
        employee_number="E-101",
        approval_status="rejected",
        supervisor_approved_at=None,
        dept_approved_at=None,
        contract_end_5="2027/12/31",
    )
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [approved, rejected]
    db.execute = AsyncMock(return_value=result)

    with patch(
        "app.modules.hr.api._assert_dept_in_scope", new_callable=AsyncMock
    ) as scope:
        scope.return_value = None
        response = await contract_api.export_contract_approval_results(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            department="质量",
            result="approved",
            db=db,
            current_user=object(),
        )

    assert response.media_type.startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert "filename*=" in response.headers["content-disposition"]
    assert response.body_iterator is not None


@pytest.mark.asyncio
async def test_update_contract_approval_card_covers_department_and_supervisor_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.hr import contract_api

    # 凭证解析（P5 后 update_contract_approval_card 内部开库查人事凭证）：
    # 隔离为固定凭证，避免依赖测试库中 HrFeishuAppSettings 的实际状态
    class _Ctx:
        def __init__(self) -> None:
            self.execute = AsyncMock(return_value=_Result(one=_app_credentials_row()))

        async def __aenter__(self) -> "_Ctx":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr("app.core.database.async_session_factory", lambda: _Ctx())
    monkeypatch.setattr(
        "app.modules.hr.feishu_settings_service.decrypt_api_key",
        lambda _value: "hr-secret-plain",
    )

    cache_values = {
        "hr:contract:card:质量部:msgid": "msg-dept",
        "hr:contract:card:质量部:emps": (
            '{"title":"合同提醒","content":"请处理","emps":['
            '{"employee_number":"E-100","employee_name":"合同员工",'
            '"leader_name":"负责人"},{"employee_number":"E-101",'
            '"employee_name":"另一员工","leader_name":"负责人"}]}'
        ),
    }

    async def cache_get(key: str) -> str | None:
        return cache_values.get(key)

    update_card = AsyncMock()
    monkeypatch.setattr("app.core.redis.cache_get", cache_get)
    monkeypatch.setattr("app.modules.hr.feishu.notification.update_card", update_card)
    await contract_api.update_contract_approval_card(
        "E-100", "合同员工", "approve", "dept", "质量部"
    )
    assert update_card.await_args.args[0] == "msg-dept"
    assert any(
        "已同意续签" in str(item) for item in update_card.await_args.args[1]["elements"]
    )

    cache_values["hr:contract:supervisor_card:E-100:msgid"] = "msg-supervisor"
    await contract_api.update_contract_approval_card(
        "E-100", "合同员工", "reject", "supervisor", "质量部"
    )
    assert update_card.await_count == 2
    assert update_card.await_args.args[1]["header"]["template"] == "red"

    cache_values.clear()
    await contract_api.update_contract_approval_card(
        "E-100", "合同员工", "approve", "supervisor", "质量部"
    )


@pytest.mark.asyncio
async def test_contract_background_tasks_notify_hr_and_supervisor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.hr import contract_api

    # 结果/签署卡片改由人事专属应用发送：隔离 DB 凭证解析
    monkeypatch.setattr(
        "app.modules.hr.feishu_settings_service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )

    record = _contract_record(
        approval_status="approved", supervisor_open_id="ou-supervisor"
    )
    config = SimpleNamespace(
        id=uuid4(),
        is_deleted=False,
        recipient_open_ids=["ou-hr"],
        sign_clerk_open_ids=["ou-clerk"],
    )
    dept_lookup = MagicMock()
    dept_lookup.scalar_one_or_none.return_value = None
    config_result = MagicMock()
    config_result.scalars.return_value.all.return_value = [config]
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[_result(record), config_result, dept_lookup]
    )

    class _Factory:
        async def __aenter__(self) -> MagicMock:
            return session

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr("app.core.database.async_session_factory", lambda: _Factory())
    send_card = AsyncMock()
    monkeypatch.setattr("app.modules.hr.feishu.notification.send_user_card", send_card)
    await contract_api._send_contract_result_task("E-100")
    assert [call.kwargs["open_id"] for call in send_card.await_args_list] == [
        "ou-hr",
        "ou-clerk",
    ]

    supervisor_session = MagicMock()
    supervisor_session.execute = AsyncMock(return_value=_result(record))

    class _SupervisorFactory:
        async def __aenter__(self) -> MagicMock:
            return supervisor_session

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "app.core.database.async_session_factory", lambda: _SupervisorFactory()
    )
    send_supervisor = AsyncMock(return_value="msg-supervisor")
    monkeypatch.setattr(
        "app.modules.hr.feishu.notification.send_user_card_with_message_id",
        send_supervisor,
    )
    cache_set = AsyncMock()
    monkeypatch.setattr("app.core.redis.cache_set", cache_set)
    record.approval_status = "supervisor_pending"
    await contract_api._send_supervisor_card_task("E-100")
    send_supervisor.assert_awaited_once()
    cache_set.assert_awaited_once()
