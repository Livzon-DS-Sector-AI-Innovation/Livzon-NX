"""Exercise HR compatibility endpoints with their real request/response logic."""

import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from openpyxl import Workbook


def _upload_bytes() -> bytes:
    workbook = Workbook()
    workbook.active.title = "部门一"
    workbook.create_sheet("部门二")
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


@pytest.mark.asyncio
async def test_import_training_ledger_supports_all_sheets_and_reports_unknown_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.hr import api

    monkeypatch.setattr(
        api,
        "read_upload_secure",
        AsyncMock(return_value=("training.xlsx", _upload_bytes())),
    )

    def header_map(ws: object) -> tuple[int, dict[int, str]]:
        if getattr(ws, "title") == "部门一":
            return 2, {1: "培训日期", 2: "培训内容", 3: "培训对象", 4: "授课人"}
        return 2, {1: "培训日期", 2: "培训内容", 3: "培训对象", 4: "授课人"}

    monkeypatch.setattr(api, "_read_excel_header_map", header_map)
    import_rows = AsyncMock(side_effect=[2, 1])
    monkeypatch.setattr(api, "_import_rows_with_mapping", import_rows)
    service = SimpleNamespace()

    result = await api.import_training_ledger_by_dept(
        file=SimpleNamespace(filename="training.xlsx"),
        department="质量部",
        all_sheets=True,
        service=service,
        current_user=object(),
    )
    assert json.loads(result.body)["data"]["created"] == 3
    assert import_rows.await_count == 2

    with pytest.raises(api.AppException, match="工作表"):
        await api.import_training_ledger_by_dept(
            file=SimpleNamespace(filename="training.xlsx"),
            department="质量部",
            sheet_name="不存在",
            all_sheets=False,
            service=service,
            current_user=object(),
        )


@pytest.mark.asyncio
async def test_sync_onboarding_to_employee_resolves_numeric_feishu_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.hr import api

    onboarding_service = SimpleNamespace(
        get_onboarding=AsyncMock(
            return_value={
                "name": "新员工",
                "department": "质量部",
                "level": "检验员",
                "onboard_date": "bad-date",
            }
        )
    )
    bitable_client = SimpleNamespace(
        search_records=AsyncMock(
            return_value=[
                {"record_id": "other", "fields": {"姓名": "其他", "工号": "1"}},
                {
                    "record_id": "matched",
                    "fields": {"姓名": [{"text": "新员工"}], "工号": 1002},
                },
            ]
        )
    )
    bitable_repo = SimpleNamespace(_get_client=AsyncMock(return_value=bitable_client))
    monkeypatch.setattr(
        "app.modules.hr.recruitment_repository.RecruitmentBitableRepo",
        lambda: bitable_repo,
    )
    employee = SimpleNamespace(id=uuid4())
    employee_repo = SimpleNamespace(get_by_name=AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.modules.hr.repository.EmployeeRepository", lambda _db: employee_repo
    )
    employee_service = SimpleNamespace(
        create_employee=AsyncMock(return_value=(employee, "success"))
    )
    contract_service = SimpleNamespace(
        sync_from_onboarding=AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    )
    monkeypatch.setattr(
        "app.modules.hr.contract_service.ContractService",
        lambda _db: contract_service,
    )

    result = await api.sync_onboarding_to_employee(
        "onboarding-1",
        onboarding_service=onboarding_service,
        employee_service=employee_service,
        db=SimpleNamespace(),
        current_user=object(),
    )
    body = json.loads(result.body)
    assert body["data"]["employee_number"] == "1002"
    assert body["data"]["contract_synced"] is True
    employee_service.create_employee.assert_awaited_once()
    contract_service.sync_from_onboarding.assert_awaited_once()

    onboarding_service.get_onboarding.return_value = {"department": "质量部"}
    with pytest.raises(api.AppException, match="缺少姓名"):
        await api.sync_onboarding_to_employee(
            "missing-name",
            onboarding_service=onboarding_service,
            employee_service=employee_service,
            db=SimpleNamespace(),
            current_user=object(),
        )


@pytest.mark.asyncio
async def test_sync_onboarding_rejects_missing_feishu_and_duplicate_local_employee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.hr import api

    onboarding = SimpleNamespace(
        get_onboarding=AsyncMock(
            return_value={"name": "重复员工", "department": "人事部"}
        )
    )
    no_client = SimpleNamespace(_get_client=AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.modules.hr.recruitment_repository.RecruitmentBitableRepo",
        lambda: no_client,
    )
    with pytest.raises(api.AppException, match="飞书连接"):
        await api.sync_onboarding_to_employee(
            "no-client",
            onboarding_service=onboarding,
            employee_service=SimpleNamespace(),
            db=SimpleNamespace(),
            current_user=object(),
        )

    client = SimpleNamespace(
        search_records=AsyncMock(
            return_value=[{"fields": {"姓名": "重复员工", "工号": "E-2"}}]
        )
    )
    duplicate_repo = SimpleNamespace(_get_client=AsyncMock(return_value=client))
    monkeypatch.setattr(
        "app.modules.hr.recruitment_repository.RecruitmentBitableRepo",
        lambda: duplicate_repo,
    )
    local_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    )
    monkeypatch.setattr(
        "app.modules.hr.repository.EmployeeRepository", lambda _db: local_repo
    )
    with pytest.raises(api.AppException, match="已存在员工档案"):
        await api.sync_onboarding_to_employee(
            "duplicate",
            onboarding_service=onboarding,
            employee_service=SimpleNamespace(),
            db=SimpleNamespace(),
            current_user=object(),
        )


@pytest.mark.asyncio
async def test_candidate_resume_file_returns_authenticated_docx_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.hr import api

    client = SimpleNamespace(
        search_records=AsyncMock(
            return_value=[
                {
                    "record_id": "candidate-1",
                    "fields": {
                        "简历附件": [{"file_token": "token-1", "name": "简历.docx"}]
                    },
                }
            ]
        )
    )
    repo = SimpleNamespace(_get_client=AsyncMock(return_value=client))
    monkeypatch.setattr(
        "app.modules.hr.recruitment_repository.RecruitmentBitableRepo",
        lambda: repo,
    )
    feishu = SimpleNamespace(download_file=AsyncMock(return_value=b"docx-bytes"))
    monkeypatch.setattr("app.modules.hr.feishu.client.FeishuClient", lambda: feishu)

    response = await api.get_candidate_resume_file("candidate-1", object())
    assert response.media_type.endswith("wordprocessingml.document")
    assert "filename*=" in response.headers["content-disposition"]
    feishu.download_file.assert_awaited_once_with("token-1")

    client.search_records.return_value = []
    with pytest.raises(api.NotFoundException):
        await api.get_candidate_resume_file("missing", object())


@pytest.mark.asyncio
async def test_candidate_resume_file_rejects_unconfigured_or_missing_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.hr import api

    no_client = SimpleNamespace(_get_client=AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.modules.hr.recruitment_repository.RecruitmentBitableRepo",
        lambda: no_client,
    )
    with pytest.raises(api.AppException, match="未配置"):
        await api.get_candidate_resume_file("candidate", object())

    client = SimpleNamespace(
        search_records=AsyncMock(
            return_value=[{"record_id": "candidate", "fields": {"简历附件": []}}]
        )
    )
    repo = SimpleNamespace(_get_client=AsyncMock(return_value=client))
    monkeypatch.setattr(
        "app.modules.hr.recruitment_repository.RecruitmentBitableRepo",
        lambda: repo,
    )
    with pytest.raises(api.AppException, match="没有简历附件"):
        await api.get_candidate_resume_file("candidate", object())
