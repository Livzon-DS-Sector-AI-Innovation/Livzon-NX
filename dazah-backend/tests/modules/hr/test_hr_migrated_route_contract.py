from collections.abc import AsyncIterator
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response

from app.core import jobs, redis
from app.core.database import get_db
from app.core.exceptions import AppException, DuplicateException
from app.main import app
from app.modules.hr import api, position_training_api, training_dept_resolver
from app.modules.hr.feishu_settings_service import HrFeishuNotConfigured
from app.modules.hr.service import (
    PositionTransferRecordService,
)
from app.platform.identity.deps import get_current_user

RECORD_ID = UUID("00000000-0000-0000-0000-000000000001")
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _paths(prefix: str) -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(prefix)
    }


def test_migrated_hr_contract_routes_are_mounted() -> None:
    paths = _paths("/api/v1/hr")

    assert "/api/v1/hr/contracts" in paths
    assert "/api/v1/hr/annual-training-plans/{plan_id}/attachments" in paths
    preview_path = "/api/v1/hr/annual-training-plan-attachments/{attachment_id}/preview"
    assert preview_path in paths
    assert "/api/v1/hr/training-attachment" in paths
    assert "/api/v1/hr/email/upload-offer-template" in paths


@pytest.fixture
async def hr_http() -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    # Exercise the real routes and response handlers with isolated dependencies.
    router_app = FastAPI(exception_handlers=app.exception_handlers)
    router_app.include_router(api.router, prefix="/api/v1/hr")
    router_app.dependency_overrides[get_db] = lambda: None
    router_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=RECORD_ID
    )
    async with AsyncClient(
        transport=ASGITransport(app=router_app), base_url="http://test"
    ) as http:
        yield router_app, http


def assert_error(
    response: Response, status: int, error_code: str | None = None
) -> None:
    assert response.status_code == status, response.text
    payload = response.json()
    assert payload["code"] == status
    if error_code is None:
        assert (
            not isinstance(payload.get("detail"), dict)
            or "error_code" not in payload["detail"]
        )
    else:
        assert payload["detail"] == {"error_code": error_code}


async def test_create_and_delete_annual_plan_error_codes(hr_http) -> None:
    router_app, http = hr_http
    service = SimpleNamespace(
        create_plan=AsyncMock(
            side_effect=DuplicateException("年度培训计划", "计划标识")
        ),
        delete_plan=AsyncMock(),
    )
    router_app.dependency_overrides[api.get_annual_training_plan_service] = lambda: (
        service
    )

    response = await http.post(
        "/api/v1/hr/annual-training-plans", json={"year": 2026, "department": "质量部"}
    )
    assert_error(response, 409, "HR_ANNUAL_PLAN_DUPLICATE")

    url = f"/api/v1/hr/annual-training-plans/{RECORD_ID}"
    router_app.dependency_overrides[get_current_user] = lambda: None
    assert_error(await http.delete(url), 401)

    def forbid() -> None:
        raise AppException(status_code=403, message="未获得当前高风险业务动作授权")

    router_app.dependency_overrides[get_current_user] = forbid
    assert_error(await http.delete(url), 403)
    service.delete_plan.assert_not_awaited()


@pytest.mark.parametrize(
    ("plan_level", "error_code"),
    [
        ("部门级", "HR_ANNUAL_PLAN_DEPARTMENT_MISSING"),
        ("公司级", "HR_ANNUAL_PLAN_ITEMS_MISSING"),
    ],
)
async def test_annual_plan_import_codes(hr_http, plan_level, error_code) -> None:
    _, http = hr_http
    content = BytesIO()
    Document().save(content)
    response = await http.post(
        "/api/v1/hr/annual-training-plans/import",
        params={"year": 2026, "plan_level": plan_level},
        files={"file": ("年度计划.docx", content.getvalue(), DOCX_MIME)},
    )
    assert_error(response, 400, error_code)


@pytest.mark.parametrize(
    ("filename", "parser_result", "status", "error_code"),
    [
        (
            "清单.docx",
            ValueError("Word 解析器诊断"),
            400,
            "HR_POSITION_TRAINING_TEMPLATE_INVALID",
        ),
        (
            "清单.docx",
            {"department": "", "items": []},
            400,
            "HR_POSITION_TRAINING_DATA_MISSING",
        ),
        ("清单.doc", None, 415, None),
    ],
)
async def test_position_training_import_codes(
    hr_http, monkeypatch, filename, parser_result, status, error_code
) -> None:
    _, http = hr_http
    monkeypatch.setattr(
        position_training_api,
        "read_upload_secure",
        AsyncMock(return_value=(filename, b"word")),
    )
    monkeypatch.setattr(
        training_dept_resolver,
        "resolve_training_department",
        AsyncMock(return_value=""),
    )

    def parse_document(_content):
        if isinstance(parser_result, Exception):
            raise parser_result
        return parser_result

    monkeypatch.setattr(position_training_api, "_parse_import_docx", parse_document)
    response = await http.post(
        "/api/v1/hr/position-training-lists/import",
        files={"file": (filename, b"word", DOCX_MIME)},
    )
    assert_error(response, status, error_code)


async def test_attachment_count_error_has_a_code_but_size_does_not(
    hr_http, monkeypatch
) -> None:
    _, http = hr_http
    path = f"/api/v1/hr/annual-training-plans/{RECORD_ID}/attachments"
    files = [
        ("files", (f"附件{n}.pdf", b"%PDF-1.4", "application/pdf"))
        for n in range(api.MAX_UPLOAD_FILES + 1)
    ]
    assert_error(
        await http.post(path, files=files),
        400,
        "HR_ANNUAL_PLAN_ATTACHMENT_COUNT_EXCEEDED",
    )

    monkeypatch.setattr(
        api, "get_settings", lambda: SimpleNamespace(MAX_UPLOAD_SIZE_MB=0)
    )
    assert_error(await http.post(path, files=files[:1]), 413)


@pytest.mark.parametrize(
    ("operation", "flow", "locked", "status", "error_code"),
    [
        ("submit", None, False, 409, "HR_POSITION_TRANSFER_NOT_DRAFT"),
        ("submit", None, True, 423, None),
        (
            "approve-node",
            {"current_step": 1, "steps": [{}]},
            False,
            409,
            "HR_POSITION_TRANSFER_APPROVAL_COMPLETED",
        ),
        ("approve-node", None, True, 423, None),
        ("reject-node", None, False, 409, "HR_POSITION_TRANSFER_NOT_SUBMITTED"),
    ],
)
async def test_approval_distinguishes_state_conflicts_from_generic_lock(
    hr_http, monkeypatch, operation, flow, locked, status, error_code
) -> None:
    router_app, http = hr_http
    record = SimpleNamespace(approval_status="审批中", approval_flow=flow)
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: record)
        ),
    )
    service = PositionTransferRecordService(session)
    monkeypatch.setattr(
        redis, "cache_get", AsyncMock(return_value="1" if locked else None)
    )
    monkeypatch.setattr(redis, "cache_set", AsyncMock())
    monkeypatch.setattr(redis.redis_client, "delete", AsyncMock())
    router_app.dependency_overrides[api.get_position_transfer_service] = lambda: service

    response = await http.post(
        f"/api/v1/hr/position-transfers/{RECORD_ID}/{operation}", json={}
    )
    assert_error(response, status, error_code)


async def test_position_transfer_sync_reports_missing_feishu_config(
    hr_http, monkeypatch
) -> None:
    router_app, http = hr_http
    service = PositionTransferRecordService(None)
    get_config = AsyncMock(side_effect=[None, HrFeishuNotConfigured()])
    monkeypatch.setattr(service, "_get_position_bitable", get_config)
    router_app.dependency_overrides[api.get_position_transfer_service] = lambda: service

    for _ in range(2):
        response = await http.post("/api/v1/hr/position-transfers/sync-from-feishu")
        assert_error(response, 503, "HR_POSITION_TRANSFER_FEISHU_NOT_CONFIGURED")


@pytest.mark.parametrize(
    "path,task_id",
    [
        ("departments/sync-status", "hr:sync:departments"),
        ("hr-settings/hr-members/sync-status", "hr:sync:feishu-members"),
    ],
)
async def test_sync_status_returns_public_detail_and_hides_internal_progress(
    hr_http, monkeypatch, path, task_id
) -> None:
    _, http = hr_http
    failed = {"state": "failed", "progress": "失败: 内部请求详情", "result": None}
    detail = {"error_code": "HR_FEISHU_CONTACT_NOT_CONFIGURED"}
    get_status = AsyncMock(
        side_effect=[
            {**failed, "detail": detail},
            failed,
            {**failed, "detail": {"error_code": "HR_FUTURE_ERROR"}},
            None,
        ]
    )
    monkeypatch.setattr(api, "get_job_status", get_status)
    monkeypatch.setattr(jobs, "get_job_status", get_status)
    url = f"/api/v1/hr/{path}"

    for public_detail in ({"detail": detail}, {}, {}):
        response = await http.get(url)
        assert response.status_code == 200
        assert response.json()["data"] == {
            **failed,
            "progress": "同步失败",
            **public_detail,
        }
        get_status.assert_awaited_with(task_id)
    assert (await http.get(url)).json()["data"] == {
        "state": "idle",
        "progress": "无同步任务",
        "result": None,
    }


def test_hr_errors_are_documented_in_openapi() -> None:
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    paths = spec["paths"]
    create = paths["/api/v1/hr/annual-training-plans"]["post"]
    conflict = create["responses"]["409"]
    assert "HR_ANNUAL_PLAN_DUPLICATE" in conflict["description"]
    assert conflict["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HrBusinessErrorResponse",
    }
    detail = schemas["HrBusinessErrorDetail"]
    assert detail["required"] == ["error_code"]
    assert (
        detail["properties"]["error_code"]["$ref"]
        == "#/components/schemas/HrBusinessErrorCode"
    )

    status = paths["/api/v1/hr/hr-settings/hr-members/sync-status"]["get"]["responses"][
        "200"
    ]
    assert status["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HrSyncJobStatusEnvelope",
    }
