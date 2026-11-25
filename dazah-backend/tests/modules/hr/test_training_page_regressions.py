import json
from datetime import UTC, date, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from docx import Document
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import error_response
from app.modules.hr import api
from app.modules.hr import practical_exam_document_generator as practical
from app.modules.hr.models import (
    Employee,
    NewEmployeeTrainingPlan,
    PositionTrainingList,
    TrainingImportMapping,
    TrainingLedger,
    TrainingSession,
)
from app.platform.identity.deps import get_current_user, require_module_view
from app.platform.identity.models import Department, User
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput

NEW_EMPLOYEE = "hr:training:new-employee-training"
SIGN_IN = "hr:training:sign-in-sheet"
POSITION_TRAINING = "hr:training:position-training"
LEDGER = "hr:training:training-ledger"
PLANS = "/api/v1/hr/new-employee-training/plans/manual-add"
CANDIDATES = "/api/v1/hr/new-employee-training/employee-candidates"
NOTIFICATION = "/api/v1/hr/training-notification"
PRACTICAL = "/api/v1/hr/training-practical-exam"
SIGN_IN_EMPLOYEES = "/api/v1/hr/training-sign-in/employees"
CONFLICTS = "/api/v1/hr/training-ledgers/check-conflict"
IMPORT = "/api/v1/hr/training-ledgers/import-confirm"


def _app(db, user):
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/hr",
        dependencies=[Depends(require_module_view("hr"))],
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )

    @app.exception_handler(AppException)
    async def app_error(request: Request, exc: AppException) -> JSONResponse:
        return error_response(exc.message, exc.detail_msg, exc.status_code)

    return app


@pytest.fixture
async def training_scope(db_session, monkeypatch):
    suffix = uuid4().hex[:10]
    own, other = f"本部-{suffix}", f"其他部-{suffix}"
    own_id, other_id = f"own-{suffix}", f"other-{suffix}"
    user = User(
        name="培训经办人",
        username=f"training-{suffix}",
        role="user",
        status="active",
        auth_source="local",
    )
    db_session.add_all(
        [
            user,
            Department(feishu_department_id=own_id, name=own),
            Department(feishu_department_id=other_id, name=other),
        ]
    )
    await db_session.flush()
    grants = [
        EffectivePageGrantOut(
            page_key=key,
            module_code="hr",
            permissions=["access", "query", "operate"],
            sensitive_actions=["bulk_import"] if key == LEDGER else [],
            data_scope=PageDataScopeInput(
                scope_type="departments", department_ids=[dept_id]
            ),
            source="user",
        )
        for key, dept_id in [
            (NEW_EMPLOYEE, own_id),
            (POSITION_TRAINING, own_id),
            (SIGN_IN, other_id),
            (LEDGER, other_id),
        ]
    ]
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=grants)
    )
    return _app(db_session, user), own, other, suffix


@pytest.mark.asyncio
async def test_training_department_positions_available_only_to_reviewed_pages(
    db_session, training_scope
):
    app, own, other, _ = training_scope
    db_session.add_all(
        [
            PositionTrainingList(department=own, position="操作员"),
            PositionTrainingList(department=other, position="其他岗位"),
        ]
    )
    await db_session.flush()
    path = "/api/v1/hr/position-training-lists/departments"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for page in (NEW_EMPLOYEE, POSITION_TRAINING):
            result = await client.get(
                f"{path}/{own}/positions", headers={"X-Dazah-Page-Key": page}
            )
            assert result.status_code == 200
            assert result.json()["data"] == ["操作员"]
        forbidden = await client.get(
            f"{path}/{other}/positions", headers={"X-Dazah-Page-Key": NEW_EMPLOYEE}
        )
        assert forbidden.status_code == 403
        unbound = await client.get(
            f"{path}/{other}/positions", headers={"X-Dazah-Page-Key": SIGN_IN}
        )
        assert unbound.status_code == 403


@pytest.mark.asyncio
async def test_sign_in_employee_directory_returns_only_scoped_minimal_fields(
    db_session, training_scope
):
    app, own, other, suffix = training_scope
    db_session.add_all(
        [
            Employee(
                name=f"甲-{suffix}",
                employee_number=f"a-{suffix}",
                department=own,
                sub_department=other,
                position="操作员",
                hire_date=date(2026, 1, 1),
            ),
            Employee(
                name=f"乙-{suffix}",
                employee_number=f"b-{suffix}",
                department=other,
                position="操作员",
                hire_date=date(2026, 1, 1),
            ),
            Employee(
                name=f"范围外-{suffix}",
                employee_number=f"c-{suffix}",
                department=other,
                sub_department=own,
                position="操作员",
                hire_date=date(2026, 1, 1),
            ),
        ]
    )
    await db_session.flush()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        pages = [
            await client.get(
                SIGN_IN_EMPLOYEES,
                headers={"X-Dazah-Page-Key": SIGN_IN},
                params={"page": page, "page_size": 1},
            )
            for page in (1, 2)
        ]
        unrelated = await client.get(
            SIGN_IN_EMPLOYEES, headers={"X-Dazah-Page-Key": LEDGER}
        )
        assert unrelated.status_code == 403
        employee_archive = await client.get(
            "/api/v1/hr/employees", headers={"X-Dazah-Page-Key": SIGN_IN}
        )
        assert employee_archive.status_code == 403
    assert all(p.status_code == 200 and p.json()["meta"]["total"] == 2 for p in pages)
    assert {p.json()["data"][0]["name"] for p in pages} == {
        f"甲-{suffix}",
        f"乙-{suffix}",
    }
    assert all(
        set(p.json()["data"][0]) == {"name", "department", "sub_department"}
        for p in pages
    )


@pytest.mark.asyncio
async def test_sign_in_conflict_check_filters_deleted_and_out_of_scope_sessions(
    db_session, training_scope
):
    app, own, other, suffix = training_scope
    session_date = date(2032, 1, 11)
    values = {
        "training_date": session_date,
        "time_start": "09:00",
        "time_end": "10:00",
        "instructor": f"经办人-{suffix}",
    }
    visible = TrainingSession(**values, topic="有效培训", department=other)
    db_session.add_all(
        [
            visible,
            TrainingSession(
                **values, topic="已删培训", department=other, is_deleted=True
            ),
            TrainingSession(**values, topic="范围外培训", department=own),
            TrainingLedger(
                training_date=session_date,
                training_datetime="25:00~26:00",
                training_subject="旧资料中的非法时间",
                teaching_dept=other,
                employee_number="",
            ),
        ]
    )
    await db_session.flush()
    payload = {**values, "training_date": str(session_date)}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for page in (SIGN_IN, LEDGER):
            response = await client.post(
                CONFLICTS, json=payload, headers={"X-Dazah-Page-Key": page}
            )
            assert response.status_code == 200
            conflicts = response.json()["data"]["instructor_conflicts"]
            assert [conflict["training_name"] for conflict in conflicts] == ["有效培训"]
        headers = {"X-Dazah-Page-Key": SIGN_IN}
        excluded = await client.post(
            CONFLICTS,
            headers=headers,
            json={
                **payload,
                "exclude_session_id": str(visible.id),
            },
        )
        assert (
            excluded.status_code == 200
            and excluded.json()["data"]["has_conflict"] is False
        )
        for invalid in (
            {"time_start": "25:00"},
            {"time_end": "08:59"},
            {"time_end": "09:00"},
            {"exclude_session_id": "invalid-id"},
        ):
            rejected = await client.post(
                CONFLICTS, json={**payload, **invalid}, headers=headers
            )
            assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_manual_add_matches_only_visible_employee_and_rejects_other_department(
    db_session, training_scope
):
    app, own, other, suffix = training_scope
    name = f"同名员工-{suffix}"
    visible = Employee(
        name=name,
        employee_number=f"a-{suffix}",
        department=own,
        position="档案岗位",
        hire_date=date(2024, 3, 2),
        status="在职",
    )
    hidden = Employee(
        name=name,
        employee_number=f"b-{suffix}",
        department=own,
        sub_department=other,
        position="其他岗位",
        hire_date=date(2025, 2, 1),
        status="在职",
    )
    db_session.add_all([visible, hidden])
    await db_session.flush()
    headers = {"X-Dazah-Page-Key": NEW_EMPLOYEE}
    body = {
        "name": name,
        "department": own,
        "position": "手填岗位",
        "hire_date": "2026-01-01",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(PLANS, headers=headers, json=body)
        assert response.status_code == 200, response.json()
        data = response.json()["data"]
        assert (data["employee_id"], data["position"], data["hire_date"]) == (
            str(visible.id),
            "档案岗位",
            "2024-03-02",
        )
        candidates = await client.get(
            CANDIDATES, params={"name": name}, headers=headers
        )
        assert candidates.status_code == 200
        assert candidates.json()["data"] == [
            {
                "id": str(visible.id),
                "name": name,
                "department": own,
                "sub_department": None,
                "position": "档案岗位",
                "hire_date": "2024-03-02",
                "employee_number": visible.employee_number,
            }
        ]
        assert (
            await client.get(
                CANDIDATES, params={"name": name}, headers={"X-Dazah-Page-Key": SIGN_IN}
            )
        ).status_code == 403
        inaccessible = await client.post(
            PLANS, headers=headers, json={**body, "employee_id": str(hidden.id)}
        )
        assert inaccessible.status_code == 404
        outside = await client.post(
            PLANS,
            headers=headers,
            json={**body, "name": "新员工", "department": own, "sub_department": other},
        )
        assert outside.status_code == 403
    plans = (
        await db_session.scalars(
            select(NewEmployeeTrainingPlan).where(
                NewEmployeeTrainingPlan.employee_id.in_([visible.id, hidden.id])
            )
        )
    ).all()
    assert [plan.employee_id for plan in plans] == [visible.id]


@pytest.mark.asyncio
async def test_notice_exports_and_creates_ledger_only_for_employee_in_sign_in_scope(
    db_session, training_scope
):
    app, own, other, suffix = training_scope
    visible = Employee(
        name=f"范围内-{suffix}",
        employee_number="110001372",
        department=own,
        sub_department=other,
        position="操作员",
        hire_date=date(2024, 3, 2),
        status="在职",
    )
    hidden = Employee(
        name=f"范围外-{suffix}",
        employee_number="110000673",
        department=own,
        position="操作员",
        hire_date=date(2025, 2, 1),
        status="在职",
    )
    db_session.add_all([visible, hidden])
    await db_session.flush()
    ledger = AsyncMock()
    app.dependency_overrides[api.get_training_ledger_service] = lambda: SimpleNamespace(
        repo=SimpleNamespace(session=db_session),
        create_from_notification=ledger,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            NOTIFICATION,
            headers={"X-Dazah-Page-Key": SIGN_IN},
            json={
                "department": other,
                "subject": "培训主题",
                "training_date": "2026-11-24",
                "trainee_names": [visible.name, hidden.name, other, visible.name],
            },
        )
    assert response.status_code == 200
    assert "培训主题" in "".join(
        p.text for p in Document(BytesIO(response.content)).paragraphs
    )
    ledger.assert_awaited_once()
    assert ledger.await_args.kwargs["employee_number"] == visible.employee_number


def _document_bytes(doc):
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


@pytest.mark.asyncio
async def test_training_ledger_import_validates_all_sheets_before_writing(
    db_session, training_scope
):
    app, own, other, suffix = training_scope
    workbook = Workbook()
    main = workbook.active
    main.title = "培训"
    main.append(["培训内容", "培训日期", "备注"])
    subject = f"台账验证-{suffix}"
    main.append([subject, date(2026, 11, 24), "测试"])
    other_sheet = workbook.create_sheet("复核")
    other_sheet.append(["培训内容", "培训日期"])
    other_sheet.append([subject, date(2026, 11, 25)])
    content = _document_bytes(workbook)
    main_config = {
        "name": "培训",
        "header_row": 1,
        "mapping": {
            "0": "training_content",
            "1": "training_date",
        },
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def submit(sheets, department=other):
            return await client.post(
                IMPORT,
                headers={"X-Dazah-Page-Key": LEDGER},
                data={"department": department, "sheets": json.dumps(sheets)},
                files={"file": ("ledger.xlsx", content)},
            )

        for invalid in (
            {"mapping": {"abc": "training_content"}},
            {"mapping": {"-1": "training_content"}},
            {"mapping": {"2": "training_content"}},
            {"mapping": {"0": "unknown_field"}},
            {"mapping": {"0": "training_content", "1": "training_content"}},
            {"header_row": 99},
            {"name": "不存在"},
        ):
            response = await submit(
                [main_config, {**main_config, "name": "复核", **invalid}]
            )
            assert response.status_code == 400
            assert (
                response.json()["detail"]["error_code"]
                == "HR_TRAINING_IMPORT_MAPPING_INVALID"
            )
        rejected = await submit([main_config], department=own)
        assert rejected.status_code == 403
        empty = await submit([{**main_config, "mapping": {"2": "remarks"}}])
        assert empty.status_code == 400
        assert empty.json()["detail"]["error_code"] == "HR_TRAINING_IMPORT_NO_ROWS"
        statements = (
            select(TrainingLedger.id).where(TrainingLedger.training_subject == subject),
            select(TrainingImportMapping.id).where(
                TrainingImportMapping.department == other
            ),
        )
        for statement in statements:
            assert (await db_session.scalars(statement)).first() is None
        valid = await submit([main_config])
        assert valid.status_code == 200
        assert valid.json()["data"]["created"] == 1
        for statement in statements:
            assert len((await db_session.scalars(statement)).all()) == 1


@pytest.mark.asyncio
async def test_training_ledger_preview_discards_invalid_remembered_columns(
    db_session, training_scope
):
    from app.modules.hr.training_import_ai import header_fingerprint

    app, _, other, _ = training_scope
    workbook = Workbook()
    sheet = workbook.active
    headers = ["培训内容", "培训日期", "授课人", "备注"]
    sheet.append(headers)
    sheet.append(["基础培训", date(2026, 11, 24), "测试讲师", "测试"])
    invalid_mapping = TrainingImportMapping(
        department=other,
        header_fingerprint=header_fingerprint(headers),
        header_row=1,
        mapping_json=json.dumps({"-1": "training_content"}),
        confirmed_at=datetime.now(UTC),
        used_count=7,
    )
    db_session.add(invalid_mapping)
    await db_session.flush()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/hr/training-ledgers/import-preview",
            headers={"X-Dazah-Page-Key": LEDGER},
            params={"department": other},
            files={"file": ("ledger.xlsx", _document_bytes(workbook))},
        )
    assert response.status_code == 200
    result = response.json()["data"]["sheets"][0]
    assert result["source"] == "rule"
    assert result["mapping"]["0"] == "training_content"
    assert result["data_row_count"] == 1
    assert invalid_mapping.used_count == 7


@pytest.mark.asyncio
async def test_practical_import_validates_structure_before_replacing_template(
    tmp_path, monkeypatch
):
    imported = tmp_path / "practical.docx"
    monkeypatch.setattr(practical, "_imported_template_path", lambda: imported)
    app = _app(None, SimpleNamespace(role="admin"))
    headers = {"X-Dazah-Page-Key": SIGN_IN}
    template = Document(practical._find_template())
    template.tables[0].rows[2].cells[5].text = "2026-11-24"
    template.tables[0].rows[3].cells[0].text = "核对运行记录"
    valid = _document_bytes(template)
    short = Document()
    short.add_table(rows=2, cols=4)
    merged = Document(practical._find_template())
    merged.tables[0].rows[1].cells[4].merge(merged.tables[0].rows[1].cells[5])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        accepted = await client.post(
            f"{PRACTICAL}/import",
            headers=headers,
            files={"file": ("valid.docx", valid)},
        )
        assert accepted.status_code == 200
        assert accepted.json()["data"] == {
            "description": "核对运行记录",
            "training_date": "2026-11-24",
        }
        for invalid in (short, merged):
            rejected = await client.post(
                f"{PRACTICAL}/import",
                headers=headers,
                files={"file": ("bad.docx", _document_bytes(invalid))},
            )
            assert rejected.status_code == 400
            assert (
                rejected.json()["detail"]["error_code"]
                == "HR_PRACTICAL_EXAM_TEMPLATE_INVALID"
            )
            assert "APP13" in rejected.json()["message"]
            assert imported.read_bytes() == valid
        payload = {
            "training_date": "2026-11-24",
            "persons": [{"name": "测试员工", "department": "测试部"}],
        }
        exported = await client.post(
            f"{PRACTICAL}/export", headers=headers, json=payload
        )
        assert exported.status_code == 200
        with ZipFile(BytesIO(exported.content)) as archive:
            doc = Document(BytesIO(archive.read(archive.namelist()[0])))
        assert doc.tables[0].rows[1].cells[5].text.strip() == "测试员工"
        assert doc.tables[0].rows[3].cells[0].text.strip() == "核对运行记录"
        imported.write_bytes(_document_bytes(short))
        legacy = await client.post(f"{PRACTICAL}/export", headers=headers, json=payload)
        assert legacy.status_code == 400
        assert (
            legacy.json()["detail"]["error_code"]
            == "HR_PRACTICAL_EXAM_TEMPLATE_INVALID"
        )
