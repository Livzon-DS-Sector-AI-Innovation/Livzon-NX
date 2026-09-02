from __future__ import annotations

import imaplib
import smtplib
import subprocess
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.exceptions import AppException
from app.modules.hr import api


class _Result:
    def __init__(
        self,
        values: list[object] | None = None,
        one: object | None = None,
        first: object | None = None,
        scalar: object | None = None,
    ) -> None:
        self.values = values or []
        self.one = one
        self._first = first
        self._scalar = scalar

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.values

    def first(self) -> object | None:
        return self._first

    def scalar_one_or_none(self) -> object | None:
        return self.one if self.one is not None else self._scalar

    def scalar(self) -> object | None:
        return self._scalar


class _SessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), name="测试用户", is_superuser=True)


def _response(**kwargs: object) -> dict[str, object]:
    return kwargs


@pytest.mark.asyncio
async def test_hr_scope_guards_factories_and_approver_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    monkeypatch.setattr(api, "_require_user", Mock())
    permissions = AsyncMock(return_value={"hr:write"})
    monkeypatch.setattr(
        "app.platform.identity.rbac.resolve_user_permissions", permissions
    )
    await api._assert_hr_write(SimpleNamespace(), user)

    permissions.return_value = set()
    with pytest.raises(AppException, match="403"):
        await api._assert_hr_write(SimpleNamespace(), user)

    session = SimpleNamespace()
    for factory in (
        api.get_employee_service,
        api.get_department_service,
        api.get_offboarding_service,
        api.get_onboarding_service,
        api.get_departure_service,
        api.get_team_service,
        api.get_training_ledger_service,
        api.get_training_ledger_page_service,
        api.get_employee_training_list_service,
        api.get_annual_training_plan_service,
        api.get_annual_training_plan_item_service,
        api.get_plan_attachment_service,
        api.get_position_transfer_service,
        api.get_training_personnel_config_service,
    ):
        assert factory(session) is not None

    config = SimpleNamespace(
        manager_name=None,
        direct_leader_name=None,
        manager_open_id=None,
        direct_leader_open_id=None,
        director_name="总监",
        director_open_id=None,
    )
    department = SimpleNamespace(leader_name="部门负责人")
    responses = iter(
        [
            _Result(first=config),
            _Result(first=department),
            _Result(scalar="ou-leader"),
            _Result(scalar="ou-director"),
        ]
    )

    async def execute(_statement: object) -> _Result:
        return next(responses)

    approvers = await api._resolve_contract_approvers(
        SimpleNamespace(execute=execute), "质量部"
    )
    assert approvers == ("部门负责人", "ou-leader", "总监", "ou-director")


@pytest.mark.asyncio
async def test_contract_expiry_background_task_covers_empty_skips_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    monkeypatch.setattr(api, "_require_user", Mock())
    monkeypatch.setattr(api, "success_response", _response)

    import app.modules.hr.feishu.notification as notification

    import app.core.database as database
    import app.core.jobs as jobs
    import app.core.redis as redis
    import app.modules.hr.contract_api as contract_api
    import app.modules.hr.contract_service as contract_service
    import app.modules.hr.service as hr_service

    session = SimpleNamespace(flush=AsyncMock(), commit=AsyncMock())
    monkeypatch.setattr(
        database, "async_session_factory", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=False))
    callbacks: list[object] = []

    async def submit(callback: object, **_kwargs: object) -> None:
        callbacks.append(callback)

    monkeypatch.setattr(jobs, "submit_job", submit)
    cache_set = AsyncMock()
    monkeypatch.setattr(redis, "cache_set", cache_set)

    empty_service = SimpleNamespace(
        list_contract_expiring=AsyncMock(return_value=([], 0))
    )
    monkeypatch.setattr(hr_service, "EmployeeService", lambda _session: empty_service)
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value=None))
    await api.push_contract_expiring_notify(
        {"start_date": "2026-08-01", "end_date": "2026-08-31"}, user
    )
    empty_result = await callbacks.pop()()  # type: ignore[misc]
    assert empty_result["total_expiring"] == 0  # type: ignore[index]

    skipped = [
        {"employee_number": "E-APPROVED", "department": "质量部"},
        {"employee_number": "E-PUSHED", "department": "质量部"},
    ]
    populated_service = SimpleNamespace(
        list_contract_expiring=AsyncMock(return_value=(skipped, 2))
    )
    monkeypatch.setattr(
        hr_service, "EmployeeService", lambda _session: populated_service
    )

    async def cache_get(key: str) -> str | None:
        if "approved:E-APPROVED" in key:
            return "1"
        if "pushed:E-PUSHED" in key:
            return "1"
        return None

    monkeypatch.setattr(redis, "cache_get", cache_get)
    await api.push_contract_expiring_notify(payload=None, current_user=user)
    skip_result = await callbacks.pop()()  # type: ignore[misc]
    assert skip_result["skipped_approved"] == 1  # type: ignore[index]
    assert skip_result["skipped_pushed"] == 1  # type: ignore[index]

    employee = {"employee_number": "E-FAIL", "name": "张三", "department": "质量部"}
    populated_service.list_contract_expiring.return_value = ([employee], 1)
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(
        api,
        "_resolve_contract_approvers",
        AsyncMock(return_value=("部门经理", "ou-manager", None, None)),
    )
    monkeypatch.setattr(
        contract_service,
        "ContractService",
        lambda _session: SimpleNamespace(
            sync_from_contract_expiry=AsyncMock(
                return_value=SimpleNamespace(approval_status="approved")
            )
        ),
    )
    monkeypatch.setattr(
        contract_api,
        "build_contract_approval_actions",
        lambda *_args, **_kwargs: {"tag": "button"},
    )
    monkeypatch.setattr(
        notification, "send_user_card_with_message_id", AsyncMock(return_value=None)
    )
    await api.push_contract_expiring_notify(payload={}, current_user=user)
    failed_result = await callbacks.pop()()  # type: ignore[misc]
    assert failed_result["failed"] == 1  # type: ignore[index]
    assert cache_set.await_count >= 1


@pytest.mark.asyncio
async def test_hr_email_config_connection_offer_and_folder_error_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user = _user()
    monkeypatch.setattr(api, "_require_user", Mock())
    monkeypatch.setattr(api, "success_response", _response)

    settings = {
        "HR_MAIL_IMAP_HOST": "imap.test",
        "HR_MAIL_IMAP_PORT": "993",
        "HR_MAIL_IMAP_USER": "imap-user",
        "HR_MAIL_IMAP_PASS": "enc-imap",
        "HR_MAIL_SMTP_HOST": "smtp.test",
        "HR_MAIL_SMTP_PORT": "465",
        "HR_MAIL_SMTP_USER": "smtp-user",
        "HR_MAIL_SMTP_PASS": "enc-smtp",
        "HR_MAIL_FETCH_SCHEDULE_HOURS": "not-json",
    }

    async def get_setting(_module: str, key: str, default: str = "") -> str:
        return settings.get(key, default)

    set_setting = AsyncMock()
    monkeypatch.setattr("app.shared.config_reader.get_module_setting", get_setting)
    monkeypatch.setattr("app.shared.config_reader.set_module_setting", set_setting)
    config = await api.get_email_config(SimpleNamespace(), user)
    assert config["data"]["fetch_schedule_hours"] == []  # type: ignore[index]

    monkeypatch.setattr(
        "app.core.llm.encrypt_api_key", lambda value: f"encrypted:{value}"
    )
    payload = SimpleNamespace(
        model_dump=lambda **_kwargs: {
            "imap_host": "imap-new",
            "imap_pass": "new-pass",
            "smtp_pass": "",
            "fetch_enabled": False,
            "fetch_schedule_hours": [2, 14],
            "watch_dir": str(tmp_path),
        }
    )
    await api.update_email_config(payload, SimpleNamespace(), user)
    assert any(
        call.args[2] == "HR_MAIL_IMAP_PASS" for call in set_setting.await_args_list
    )
    assert any(
        call.args[2] == "HR_MAIL_FETCH_SCHEDULE_HOURS"
        for call in set_setting.await_args_list
    )

    class _Mail:
        def login(self, _user: str, _password: str) -> None:
            return None

        def logout(self) -> None:
            return None

    class _Smtp:
        def login(self, _user: str, _password: str) -> None:
            return None

        def quit(self) -> None:
            return None

    monkeypatch.setattr(imaplib, "IMAP4_SSL", Mock(return_value=_Mail()))
    monkeypatch.setattr(smtplib, "SMTP_SSL", Mock(return_value=_Smtp()))
    monkeypatch.setattr(
        "app.core.llm.decrypt_api_key", lambda value: value.replace("enc-", "")
    )
    tested = await api.test_email_config(SimpleNamespace(), user)
    assert tested["data"] == {"imap": "success", "smtp": "success"}  # type: ignore[index]

    mail_sender = __import__(
        "app.modules.hr.mail_sender", fromlist=["send_email_with_template"]
    )
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(mail_sender, "send_email_with_template", sender)
    monkeypatch.setattr(
        "app.shared.config_reader.get_module_setting",
        AsyncMock(return_value=""),
    )
    offer_payload = SimpleNamespace(
        candidate_id="candidate-1",
        to_email="candidate@example.com",
        subject="面试结果通知",
        body="您好",
    )
    await api.send_offer_email(offer_payload, SimpleNamespace(), user)
    sender.assert_awaited_once_with(
        to_email="candidate@example.com",
        subject="面试结果通知",
        html_body="您好",
        attachment_path=None,
    )
    sender.return_value = False
    with pytest.raises(AppException, match="邮件发送失败"):
        await api.send_offer_email(offer_payload, SimpleNamespace(), user)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        api,
        "read_upload_secure",
        AsyncMock(return_value=("offer.pdf", b"%PDF-test")),
    )
    await api.upload_offer_template(
        UploadFile(filename="offer.pdf", file=BytesIO(b"%PDF-test")),
        SimpleNamespace(),
        user,
    )
    stored = tmp_path / "templates" / "hr" / "offer" / "offer_template.pdf"
    assert stored.read_bytes() == b"%PDF-test"

    monkeypatch.setattr(
        "app.shared.config_reader.get_module_setting",
        AsyncMock(return_value=str(stored)),
    )
    template = await api.get_offer_template(SimpleNamespace(), user)
    assert template["data"]["has_template"] is True  # type: ignore[index]

    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(return_value=SimpleNamespace(stdout="relative/path", returncode=0)),
    )
    with pytest.raises(AppException, match="绝对路径"):
        await api.browse_folder(user)
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(side_effect=subprocess.TimeoutExpired("python", 60)),
    )
    with pytest.raises(AppException, match="超时"):
        await api.browse_folder(user)


@pytest.mark.asyncio
async def test_hr_training_session_document_content_and_exam_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user = _user()
    monkeypatch.setattr(api, "_require_user", Mock())
    monkeypatch.setattr(api, "success_response", _response)

    record = SimpleNamespace(
        id=uuid4(),
        score_summary=None,
        ledger_assessment_method=None,
        session_id=uuid4(),
    )
    repo = SimpleNamespace(
        update=AsyncMock(), sync_by_session_id=AsyncMock(return_value=2)
    )
    service = SimpleNamespace(get_record=AsyncMock(return_value=record), repo=repo)
    exam_payload = SimpleNamespace(
        record_id=record.id,
        scores=[
            SimpleNamespace(name="张三", score=95),
            SimpleNamespace(name="李四", score=88),
        ],
    )
    confirmed = await api.confirm_exam_scores(exam_payload, service)
    assert confirmed.data["synced_count"] == 2
    assert record.ledger_assessment_method == "笔试"

    class _Db:
        def __init__(
            self, results: list[_Result], existing: object | None = None
        ) -> None:
            self.results = iter(results)
            self.existing = existing
            self.added: list[object] = []
            self.flush = AsyncMock()

        async def execute(self, _statement: object) -> _Result:
            return next(self.results)

        async def get(self, _model: object, _identifier: object) -> object | None:
            return self.existing

        def add(self, value: object) -> None:
            self.added.append(value)

    content_db = _Db(
        [_Result(one=SimpleNamespace(entry_name="重复")), _Result(one=None)]
    )
    content_body = SimpleNamespace(
        items=[
            SimpleNamespace(name=" 重复 ", code="A", attachment_id=None),
            SimpleNamespace(name=" 新条目 ", code="B", attachment_id=None),
            SimpleNamespace(name="   ", code="C", attachment_id=None),
        ]
    )
    marked = await api.mark_training_content_used(content_body, content_db, user)
    assert "1 个" in marked["message"]
    assert len(content_db.added) == 1

    session_id = uuid4()
    new_body = SimpleNamespace(
        id=None,
        model_dump=lambda **_kwargs: {"topic": "GMP培训", "department": "质量部"},
    )
    session_db = _Db([])
    created = await api.upsert_training_session(new_body, session_db, user)
    assert created["data"]["id"]  # type: ignore[index]
    existing = SimpleNamespace(id=session_id, topic="旧主题", department="旧部门")
    update_body = SimpleNamespace(
        id=session_id,
        model_dump=lambda **_kwargs: {"topic": "新主题"},
    )
    updated = await api.upsert_training_session(
        update_body, _Db([], existing=existing), user
    )
    assert updated["data"]["id"] == str(session_id)  # type: ignore[index]
    assert existing.topic == "新主题"

    document = SimpleNamespace(id=uuid4(), payload={}, title="旧")
    document_body = SimpleNamespace(
        session_id=session_id,
        doc_type="evaluation",
        title="新",
        payload={"score": 90},
    )
    updated_doc = await api.upsert_training_document(
        document_body, _Db([_Result(one=document)]), user
    )
    assert updated_doc["data"]["id"] == str(document.id)  # type: ignore[index]
    assert document.payload == {"score": 90}
    created_doc = await api.upsert_training_document(
        document_body, _Db([_Result(one=None)]), user
    )
    assert created_doc["data"]["id"]  # type: ignore[index]

    monkeypatch.setattr(
        api,
        "read_upload_secure",
        AsyncMock(return_value=("questions.docx", b"docx-bytes")),
    )
    monkeypatch.setattr(
        api, "parse_practical_exam_questions", Mock(return_value={"items": []})
    )
    imported_path = tmp_path / "imported.docx"
    imported_path.write_bytes(b"")
    monkeypatch.setattr(
        "app.modules.hr.practical_exam_document_generator._imported_template_path",
        lambda: imported_path,
    )
    imported = await api.import_practical_exam_questions(
        UploadFile(filename="questions.docx", file=BytesIO(b"docx-bytes")), user
    )
    assert imported["data"] == {"items": []}
