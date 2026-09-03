from __future__ import annotations

import json
import subprocess
from datetime import date, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from openpyxl import Workbook

from app.core.exceptions import AppException
from app.modules.hr import api


class _Payload:
    def __init__(
        self, values: dict[str, object] | None = None, **attrs: object
    ) -> None:
        self._values = values or {}
        for key, value in self._values.items():
            setattr(self, key, value)
        for key, value in attrs.items():
            setattr(self, key, value)

    def model_dump(self, **_kwargs: object) -> dict[str, object]:
        return dict(self._values)


class _ResponseModel:
    def __init__(self, **values: object) -> None:
        self.values = values

    @classmethod
    def model_validate(cls, value: object) -> _ResponseModel:
        return cls(value=value)

    def model_dump(self, **_kwargs: object) -> dict[str, object]:
        return self.values


class _Result:
    def __init__(self, values: list[object] | None = None, one: object = None) -> None:
        self.values = values or []
        self.one = one

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.values

    def scalar_one_or_none(self) -> object:
        return self.one


class _Db:
    def __init__(self, results: list[_Result] | None = None) -> None:
        self.results = list(results or [])
        self.added: list[object] = []
        self.execute_calls = 0

    async def execute(self, _statement: object) -> _Result:
        self.execute_calls += 1
        return self.results.pop(0) if self.results else _Result()

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, _value: object) -> None:
        return None

    async def get(self, _model: object, _identifier: object) -> object:
        return None


def _patch_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "TrainingLedgerResponse",
        "TrainingLedgerPageResponse",
        "AnnualTrainingPlanResponse",
        "AnnualTrainingPlanItemResponse",
        "PlanAttachmentResponse",
        "PlanAttachmentSectionResponse",
        "AttachmentPreview",
        "EmployeeResponse",
        "TrainingContentUsedOut",
        "TrainingSessionOut",
        "TrainingDocumentOut",
    ):
        if hasattr(api, name):
            monkeypatch.setattr(api, name, _ResponseModel)


@pytest.mark.asyncio
async def test_training_scope_plan_and_attachment_routes_cover_success_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4(), name="测试用户", is_superuser=True)
    _patch_responses(monkeypatch)
    db = _Db()
    service = SimpleNamespace(
        list_records=AsyncMock(return_value=([], 0)),
        list_by_department=AsyncMock(return_value=([], 0)),
        create_record=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        check_conflict=AsyncMock(return_value={"has_conflict": False}),
        list_training_departments=AsyncMock(return_value=["质量部", "生产部"]),
        list_custom_training_departments=AsyncMock(return_value=["质量部"]),
        add_custom_training_department=AsyncMock(return_value={"name": "质量部"}),
        delete_custom_training_department=AsyncMock(return_value=True),
        list_dept_mappings=AsyncMock(return_value=[]),
        create_dept_mapping=AsyncMock(return_value={"id": "mapping"}),
        update_dept_mapping=AsyncMock(return_value={"id": "mapping"}),
        delete_dept_mapping=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        api, "_resolve_visible_scope", AsyncMock(return_value={"质量部"})
    )
    monkeypatch.setattr(
        api, "_assert_dept_in_scope", AsyncMock(return_value={"质量部"})
    )

    def api_success(**kwargs: object) -> dict[str, object]:
        return kwargs

    monkeypatch.setattr(api, "success_response", api_success)
    monkeypatch.setattr(api, "paginated_response", api_success)
    monkeypatch.setattr(
        "app.platform.identity.rbac.resolve_user_permissions",
        AsyncMock(return_value={"*"}),
    )

    await api.list_training_ledgers(
        employee_number=None,
        department=None,
        date_from=None,
        date_to=None,
        session_id=None,
        page_params=SimpleNamespace(page=1, page_size=20),
        db=db,
        service=service,
        current_user=user,
    )
    await api.list_training_ledgers(
        employee_number=None,
        department="质量部",
        date_from=None,
        date_to=None,
        session_id=None,
        page_params=SimpleNamespace(page=1, page_size=20),
        db=db,
        service=service,
        current_user=user,
    )
    await api.list_training_ledgers(
        employee_number=None,
        department=None,
        date_from=None,
        date_to=None,
        session_id=uuid4(),
        page_params=SimpleNamespace(page=1, page_size=20),
        db=db,
        service=service,
        current_user=user,
    )
    await api.create_training_ledger(_Payload(), service=service, current_user=user)
    await api.check_training_conflict(
        _Payload(
            training_date=date.today(),
            time_start="09:00",
            time_end="10:00",
            instructor="讲师",
            trainees="张三",
            exclude_session_id=None,
        ),
        service=service,
        current_user=user,
    )
    assert (
        await api.list_training_departments(db=db, service=service, current_user=user)
    )["data"] == ["质量部"]
    assert (
        await api.list_custom_training_departments(
            db=db, service=service, current_user=user
        )
    )["data"] == ["质量部"]
    await api.add_custom_training_department(
        _Payload({"name": "质量部"}), service=service, current_user=user
    )
    await api.delete_custom_training_department(
        "质量部", service=service, current_user=user
    )
    await api.list_training_dept_mappings(service=service, current_user=user)
    await api.create_training_dept_mapping(
        _Payload(), db=db, service=service, current_user=user
    )
    await api.update_training_dept_mapping(
        uuid4(), _Payload(), db=db, service=service, current_user=user
    )
    await api.delete_training_dept_mapping(
        uuid4(), db=db, service=service, current_user=user
    )

    dept = SimpleNamespace(
        id=uuid4(),
        parent_id=None,
        name="质量部",
        leader_name="负责人",
        sort_order=1,
    )
    config = SimpleNamespace(
        id=uuid4(),
        department_id=dept.id,
        department_name="质量部",
        direct_leader_name="负责人",
        direct_leader_open_id=None,
        manager_name=None,
        manager_open_id=None,
        director_name=None,
        director_open_id=None,
        vp_name=None,
        vp_open_id=None,
        sort_order=1,
        is_deleted=False,
    )
    approval_db = _Db([_Result([dept]), _Result([config])])
    await api.list_dept_approval_configs(db=approval_db, current_user=user)
    names_resp = await api.list_dept_approval_config_names(
        db=_Db([_Result([("质量部",), ("质量部",), ("生产部",)])]),
        current_user=user,
    )
    # 接口内 dict.fromkeys 去重保序；SQL 层 order_by 排序（mock 不执行 SQL）
    assert names_resp["data"] == ["质量部", "生产部"]
    create_db = _Db()
    await api.create_dept_approval_config(
        _Payload({"department_id": dept.id, "department_name": "质量部"}),
        db=create_db,
        current_user=user,
    )
    await api.update_dept_approval_config(
        config.id,
        _Payload({"manager_name": "经理"}),
        db=_Db([_Result(one=config)]),
        current_user=user,
    )
    await api.delete_dept_approval_config(
        config.id,
        db=_Db([_Result(one=config)]),
        current_user=user,
    )
    await api.init_dept_approval_configs_from_departments(
        db=_Db([_Result([dept]), _Result(one=None)]), current_user=user
    )

    scope = SimpleNamespace(
        user_id=user.id,
        visible_depts=["质量部"],
        updated_at=datetime.now(),
        is_deleted=False,
    )
    await api.list_dept_scopes(db=_Db([_Result()]), current_user=user)
    await api.get_dept_scope(
        str(user.id), db=_Db([_Result(one=scope)]), current_user=user
    )
    await api.delete_dept_scope(
        str(user.id), db=_Db([_Result(one=scope)]), current_user=user
    )

    page_service = SimpleNamespace(
        list_pages_with_department=AsyncMock(return_value=[]),
        create_page=AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(),
                employee_number="1",
                employee_name="张三",
                created_at=None,
                updated_at=None,
            )
        ),
    )
    await api.list_training_ledger_pages(service=page_service, current_user=user)
    await api.create_training_ledger_page(
        _Payload(), service=page_service, current_user=user
    )

    plan_service = SimpleNamespace(
        list_plans=AsyncMock(return_value=([], 0)),
        create_plan=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        get_plan=AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(), department="质量部", year=2026, plan_level="公司级"
            )
        ),
        update_plan=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        delete_plan=AsyncMock(),
        import_from_docx=AsyncMock(return_value={"imported_count": 0}),
    )
    item_service = SimpleNamespace(
        list_items=AsyncMock(return_value=[]),
        batch_update_items=AsyncMock(return_value=[]),
    )
    await api.list_annual_training_plans(
        2026, "质量部", SimpleNamespace(page=1, page_size=20), db, plan_service, user
    )
    await api.create_annual_training_plan(_Payload(), plan_service, user)
    await api.get_annual_training_plan(uuid4(), plan_service, user)
    await api.update_annual_training_plan(uuid4(), _Payload(), plan_service, user)
    await api.delete_annual_training_plan(uuid4(), plan_service, user)
    await api.list_annual_training_plan_items(uuid4(), item_service, user)
    await api.batch_update_annual_training_plan_items(
        uuid4(), _Payload(), item_service, user
    )
    assert (
        api._generate_annual_plan_excel(
            {"year": 2026, "department": "质量部"},
            [{"month": "一季度", "duration_hours": 2, "confirm_date": "2026-01-01"}],
        )
        .getbuffer()
        .nbytes
        > 0
    )

    attachment = SimpleNamespace(
        id=uuid4(), file_name="培训.pdf", created_at=None, updated_at=None
    )
    attachment_service = SimpleNamespace(
        list_by_plan=AsyncMock(return_value=[attachment]),
        upload=AsyncMock(return_value=attachment),
        get=AsyncMock(return_value=attachment),
        read_data=lambda _item: b"pdf",
        delete=AsyncMock(),
        mark_ledger_imported=AsyncMock(return_value=1),
        list_sections=AsyncMock(return_value=[]),
        preview_section=AsyncMock(return_value={"text": "preview"}),
        preview_attachment=AsyncMock(return_value={"text": "preview"}),
    )
    await api.list_plan_attachments(uuid4(), attachment_service, user)
    monkeypatch.setattr(
        api, "read_upload_secure", AsyncMock(return_value=("培训.pdf", b"pdf"))
    )
    await api.upload_plan_attachments(
        uuid4(),
        [UploadFile(filename="培训.pdf", file=BytesIO(b"pdf"))],
        attachment_service,
        user,
    )
    response = await api.download_plan_attachment(uuid4(), attachment_service, user)
    assert response.media_type == "application/octet-stream"
    await api.delete_plan_attachment(uuid4(), attachment_service, user)
    await api.mark_attachments_ledger_imported(
        _Payload(attrs=None, ids=[uuid4()]), attachment_service, user
    )
    await api.list_plan_attachment_sections(uuid4(), attachment_service, user)
    await api.preview_plan_attachment_section(uuid4(), attachment_service, user)
    await api.preview_plan_attachment(uuid4(), attachment_service, user)


@pytest.mark.asyncio
async def test_hr_email_and_recruitment_routes_cover_success_and_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4(), name="测试用户", is_superuser=True)
    monkeypatch.setattr(api, "success_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(api, "paginated_response", lambda **kwargs: kwargs)
    settings = {
        "HR_MAIL_IMAP_HOST": "imap.test",
        "HR_MAIL_IMAP_USER": "user",
        "HR_MAIL_FETCH_ENABLED": "true",
        "HR_MAIL_FETCH_SCHEDULE_HOURS": "[1, 2]",
        "HR_MAIL_LAST_FETCHED_COUNT": "2",
        "HR_MAIL_FETCH_INTERVAL_HOURS": "2",
    }

    async def get_setting(_module: str, key: str, default: str = "") -> str:
        return settings.get(key, default)

    set_setting = AsyncMock()
    monkeypatch.setattr("app.shared.config_reader.get_module_setting", get_setting)
    monkeypatch.setattr("app.shared.config_reader.set_module_setting", set_setting)
    monkeypatch.setattr("app.core.llm.encrypt_api_key", lambda value: f"enc:{value}")
    config = await api.get_email_config(session=SimpleNamespace(), current_user=user)
    assert config["data"]["fetch_enabled"] is True
    await api.update_email_config(
        _Payload(
            {
                "imap_host": "imap.new",
                "imap_pass": "secret",
                "fetch_enabled": False,
                "fetch_schedule_hours": [3],
            }
        ),
        session=SimpleNamespace(),
        current_user=user,
    )
    monkeypatch.setattr(api, "_require_user", lambda _user: None)
    await api.test_email_config(session=SimpleNamespace(), current_user=user)
    monkeypatch.setattr(api, "submit_job", AsyncMock(return_value="job-1"))
    assert (await api.trigger_mail_fetch({}, user))["data"]["job_id"] == "job-1"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="", returncode=0),
    )
    assert (await api.browse_folder(user))["data"]["path"] is None

    job_service = SimpleNamespace(
        list_jobs=AsyncMock(return_value=([], 0)),
        create_job=AsyncMock(return_value={"record_id": "job", "title": "职位"}),
        get_job=AsyncMock(return_value={"record_id": "job", "title": "职位"}),
        update_job=AsyncMock(return_value={"record_id": "job", "title": "职位"}),
        list_candidates=AsyncMock(return_value=([], 0)),
        batch_analyze=AsyncMock(return_value={"total": 1, "success": 1}),
        get_candidate=AsyncMock(return_value={"record_id": "c", "name": "候选人"}),
        update_candidate=AsyncMock(return_value={"record_id": "c", "name": "候选人"}),
        delete_candidate=AsyncMock(),
    )
    for name in ("JobPostingResponse", "CandidateResponse", "OnboardingResponse"):
        if hasattr(api, name):
            monkeypatch.setattr(api, name, _ResponseModel)
    await api.list_jobs(None, 1, 20, job_service, user)
    await api.create_job(_Payload(), job_service, user)
    await api.get_job("job", job_service, user)
    await api.update_job("job", _Payload(), job_service, user)
    await api.list_candidates(None, None, None, None, 1, 20, job_service, user)
    await api.sync_candidates_from_feishu(job_service, user)
    await api.batch_ai_analyze_candidates({"candidate_ids": ["c"]}, job_service, user)
    await api.get_candidate("c", job_service, user)
    await api.update_candidate("c", _Payload(), job_service, user)
    await api.delete_candidate("c", job_service, user)

    onboarding_service = SimpleNamespace(
        list_onboarding=AsyncMock(return_value=([{"name": "张三"}], 1)),
        create_from_interview=AsyncMock(return_value={"id": "onboarding"}),
        get_onboarding=AsyncMock(return_value={"name": "张三"}),
        update_onboarding=AsyncMock(return_value={"name": "张三"}),
        delete_onboarding=AsyncMock(),
    )
    monkeypatch.setattr(api, "_resolve_visible_scope", AsyncMock(return_value=None))
    assert (await api.get_onboarding_names(onboarding_service))["data"] == ["张三"]
    await api.list_onboarding_records(
        None, 1, 20, SimpleNamespace(), onboarding_service, user
    )
    await api.create_onboarding_from_interview(
        {"candidate_id": "c"}, onboarding_service, user
    )
    await api.delete_onboarding_record_recruitment("r", onboarding_service, user)
    await api.get_onboarding_record_recruitment("r", onboarding_service, user)
    await api.update_onboarding_record_recruitment(
        "r", _Payload(), onboarding_service, user
    )


@pytest.mark.asyncio
async def test_hr_import_export_public_create_and_candidate_notice_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4(), name="测试用户", is_superuser=True)
    db = _Db()
    monkeypatch.setattr(api, "success_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(api, "paginated_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(api, "_require_user", lambda _user: user)
    monkeypatch.setattr(api, "_assert_dept_in_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(api, "_assert_hr_write", AsyncMock())

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "培训记录"
    worksheet.append(["姓名", "培训日期", "培训内容", "培训时长（h）", "授课人"])
    worksheet.append(["张三", "2026-08-20", "GMP培训", "2", "李老师"])
    file_buffer = BytesIO()
    workbook.save(file_buffer)
    workbook_bytes = file_buffer.getvalue()

    class _MappingRepo:
        def __init__(self) -> None:
            self.created: list[object] = []

        async def get_by_dept_fingerprint(
            self, _department: str, _fingerprint: str
        ) -> None:
            return None

        async def update(self, _item: object) -> None:
            return None

        async def create(self, item: object) -> object:
            self.created.append(item)
            return item

    mapping_repo = _MappingRepo()
    monkeypatch.setattr(api, "_get_import_mapping_repo", lambda _session: mapping_repo)
    monkeypatch.setattr(
        api,
        "read_upload_secure",
        AsyncMock(return_value=("training.xlsx", workbook_bytes)),
    )

    preview = await api.preview_training_import(
        UploadFile(filename="training.xlsx", file=BytesIO(workbook_bytes)),
        "质量部",
        db,
        user,
    )
    assert preview["data"]["sheets"][0]["data_row_count"] == 1  # type: ignore[index]
    assert preview["data"]["sheets"][0]["mapping"]  # type: ignore[index]

    monkeypatch.setattr(api, "_import_rows_with_mapping", AsyncMock(return_value=1))
    confirmed = await api.confirm_training_import(
        UploadFile(filename="training.xlsx", file=BytesIO(workbook_bytes)),
        "质量部",
        json.dumps(
            [
                {
                    "name": "培训记录",
                    "header_row": 1,
                    "mapping": {
                        "1": "employee_name",
                        "2": "training_date",
                        "3": "training_subject",
                        "4": "duration_hours",
                    },
                }
            ],
            ensure_ascii=False,
        ),
        service=SimpleNamespace(),
        session=db,
        current_user=user,
    )
    assert confirmed["data"]["created"] == 1  # type: ignore[index]
    assert len(mapping_repo.created) == 1
    with pytest.raises(AppException, match="sheets 参数格式错误"):
        await api.confirm_training_import(
            UploadFile(filename="training.xlsx", file=BytesIO(workbook_bytes)),
            "质量部",
            "not-json",
            service=SimpleNamespace(),
            session=db,
            current_user=user,
        )

    employee = SimpleNamespace(id=uuid4(), name="公开员工", feishu_record_id=None)

    class _EmployeeRepo:
        existing: object | None = None

        def __init__(self, _session: object) -> None:
            pass

        async def get_by_name(self, _name: str) -> object | None:
            return self.existing

        async def create(self, record: object) -> object:
            for key, value in vars(employee).items():
                setattr(record, key, value)
            return record

        async def update(self, record: object) -> object:
            return record

    monkeypatch.setattr("app.modules.hr.repository.EmployeeRepository", _EmployeeRepo)
    monkeypatch.setattr(api, "EmployeeResponse", _ResponseModel)
    bitable = SimpleNamespace(
        create=AsyncMock(return_value="feishu-record-1"),
    )
    employee_service = SimpleNamespace(
        _get_bitable=AsyncMock(return_value=bitable),
        _to_bitable_fields=Mock(return_value={"姓名": "公开员工"}),
    )
    public_result = await api.create_employee_public(
        api.EmployeePublicCreate(
            name="公开员工",
            department="质量部",
            position="质量员",
            hire_date=date(2026, 8, 20),
        ),
        service=employee_service,
        db=db,
    )
    assert public_result["status_code"] == 201
    assert public_result["meta"]["feishu_sync_status"] == "success"  # type: ignore[index]
    assert bitable.create.await_count == 1
    _EmployeeRepo.existing = SimpleNamespace(id=uuid4())
    with pytest.raises(AppException, match="已存在员工档案"):
        await api.create_employee_public(
            api.EmployeePublicCreate(
                name="重复员工",
                department="质量部",
                position="质量员",
                hire_date=date(2026, 8, 20),
            ),
            service=employee_service,
            db=db,
        )

    notice_service = SimpleNamespace(
        get_candidate=AsyncMock(
            return_value={
                "name": "候选人",
                "interview_status": "已安排",
                "email": "candidate@example.com",
                "department": "质量部",
                "job_position": "质量员",
            }
        )
    )
    push_result = {
        "scene_code": "interview_notice",
        "scene_label": "面试通知",
        "email_sent": True,
        "email_recipient": "candidate@example.com",
        "feishu_sent": False,
        "feishu_recipients": [],
        "feishu_errors": ["provider details must not leak"],
    }
    monkeypatch.setattr(
        api,
        "PushSettingsService",
        lambda _db: SimpleNamespace(
            send_notice_for_candidate=AsyncMock(return_value=push_result)
        ),
    )
    notice = await api.send_candidate_notice_compat(
        "candidate-1",
        api.SendNoticeRequest(scene_code="interview_notice"),
        db=db,
        service=notice_service,
        current_user=user,
    )
    assert notice["data"]["email_sent"] is True  # type: ignore[index]
    assert notice["data"]["feishu_errors"] == ["飞书发送失败"]  # type: ignore[index]
    with pytest.raises(AppException, match="不支持的通知场景"):
        await api.send_candidate_notice_compat(
            "candidate-1",
            api.SendNoticeRequest(scene_code="unknown"),
            db=db,
            service=notice_service,
            current_user=user,
        )


@pytest.mark.asyncio
async def test_hr_contract_expiry_task_and_training_exports_cover_real_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4(), name="测试用户", is_superuser=True)
    monkeypatch.setattr(api, "success_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(api, "_require_user", lambda _user: user)
    monkeypatch.setattr(api, "_assert_dept_in_scope", AsyncMock(return_value=None))

    submitted: dict[str, object] = {}

    async def submit_job(callback: object, **kwargs: object) -> None:
        submitted["callback"] = callback
        submitted.update(kwargs)

    import app.core.database as database
    import app.core.jobs as jobs
    import app.core.redis as redis
    import app.modules.hr.contract_api as contract_api_module
    import app.modules.hr.contract_service as contract_service_module
    import app.modules.hr.feishu.notification as notification
    import app.modules.hr.service as hr_service_module

    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=False))
    monkeypatch.setattr(jobs, "submit_job", submit_job)
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value=None))
    cache_set = AsyncMock()
    monkeypatch.setattr(redis, "cache_set", cache_set)

    employee = {
        "employee_number": "E-001",
        "name": "张三",
        "department": "质量部",
        "contract_sequence": 2,
        "contract_end_date": date(2026, 9, 1),
    }
    session = SimpleNamespace(flush=AsyncMock(), commit=AsyncMock())

    class _SessionContext:
        async def __aenter__(self) -> SimpleNamespace:
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(database, "async_session_factory", lambda: _SessionContext())
    monkeypatch.setattr(
        hr_service_module,
        "EmployeeService",
        lambda _session: SimpleNamespace(
            list_contract_expiring=AsyncMock(return_value=([employee], 1))
        ),
    )
    monkeypatch.setattr(
        api,
        "_resolve_contract_approvers",
        AsyncMock(return_value=("部门经理", "ou-manager", "分管领导", "ou-supervisor")),
    )
    monkeypatch.setattr(
        contract_service_module,
        "ContractService",
        lambda _session: SimpleNamespace(
            sync_from_contract_expiry=AsyncMock(
                return_value=SimpleNamespace(approval_status="dept_pending")
            )
        ),
    )
    monkeypatch.setattr(
        contract_api_module,
        "build_contract_approval_actions",
        lambda *_args, **_kwargs: {"tag": "button"},
    )
    monkeypatch.setattr(
        notification,
        "send_user_card_with_message_id",
        AsyncMock(return_value="msg-1"),
    )
    import app.modules.hr.feishu_settings_service as feishu_settings_module

    monkeypatch.setattr(
        feishu_settings_module,
        "get_hr_feishu_app_credentials",
        AsyncMock(return_value=("cli_hr_test", "hr_secret_plain")),
    )
    await api.push_contract_expiring_notify(payload={}, current_user=user)
    callback = submitted["callback"]
    assert callable(callback)
    result = await callback()  # type: ignore[misc]
    assert result["pushed"] == 1
    assert result["auto_created_renewals"] == 1
    assert cache_set.await_count >= 1

    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=True))
    running = await api.push_contract_expiring_notify(payload={}, current_user=user)
    assert running["data"]["state"] == "running"  # type: ignore[index]

    monkeypatch.setattr(
        api,
        "_template_config",
        {"header_row": 3, "total_rows": 4, "title_text": "合同检查"},
    )
    export_service = SimpleNamespace(
        list_contract_expiring=AsyncMock(
            return_value=(
                [
                    {
                        "name": "张三",
                        "department": "质量部",
                        "sub_department": "QA",
                        "contract_end_date": date(2026, 9, 1),
                    },
                    {
                        "name": "李四",
                        "department": "生产部",
                        "sub_department": "一车间",
                        "contract_end_date": "2026-09-02",
                    },
                ],
                2,
            )
        )
    )
    exported = await api.export_contract_expiring(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 9, 30),
        service=export_service,
        current_user=user,
    )
    assert (
        exported.media_type
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    training_service = SimpleNamespace(
        get_employee_training_records=AsyncMock(
            return_value=[{"training_date": "2026-08-20", "training_subject": "GMP"}]
        ),
        list_employee_members=AsyncMock(
            return_value=[{"name": "张三"}, {"name": "李四"}]
        ),
    )
    from app.modules.hr import (
        employee_training_list_document_generator as training_generator,
    )

    monkeypatch.setattr(
        training_generator,
        "generate_employee_training_list",
        Mock(return_value=BytesIO(b"xlsx")),
    )
    single = await api.export_employee_training_list(
        department="质量部",
        name="张三",
        date_from=None,
        date_to=None,
        db=SimpleNamespace(),
        service=training_service,
        current_user=user,
    )
    whole_dept = await api.export_employee_training_list(
        department="质量部",
        name=None,
        date_from=None,
        date_to=None,
        db=SimpleNamespace(),
        service=training_service,
        current_user=user,
    )
    assert single.media_type.endswith("spreadsheetml.sheet")
    assert whole_dept.media_type == "application/zip"
