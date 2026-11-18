from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.main import app
from app.modules.registration.api import validation_audit as api
from app.modules.registration.service.validation_audit import ValidationAuditService


@pytest.fixture
async def audit_http(monkeypatch):
    prefix = "/api/v1/registration/validation-audit"
    test_app = FastAPI(exception_handlers=app.exception_handlers)
    test_app.include_router(api.router, prefix=prefix)
    test_app.dependency_overrides[get_db] = lambda: None
    service = ValidationAuditService.__new__(ValidationAuditService)
    task = SimpleNamespace(id=uuid4(), audit_mode="protocol")
    service.get_task = AsyncMock(return_value=task)
    service.file_repo = SimpleNamespace(
        list_by_task_id=AsyncMock(return_value=[]), update_parse_result=AsyncMock()
    )
    service.task_repo = SimpleNamespace(update=AsyncMock())
    monkeypatch.setattr(api, "ValidationAuditService", lambda _: service)
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client, f"{prefix}/tasks/{task.id}", service, task


async def test_validation_import_http_errors_and_mixed_batch(
    audit_http, monkeypatch
) -> None:
    client, path, service, task = audit_http
    monkeypatch.setattr(api, "MAX_UPLOAD_FILES", 1)
    valid = ("files", ("ok.pdf", b"%PDF-1.4 test", "application/pdf"))
    invalid = ("files", ("bad.txt", b"text", "text/plain"))
    service.save_uploaded_file = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid4(), original_filename="ok.pdf", file_size=13
        )
    )
    rejected = await client.post(
        f"{path}/files", data={"file_type": "report"}, files=[valid, invalid]
    )
    assert rejected.status_code == rejected.json()["code"] == 400
    assert rejected.json()["detail"] == {"error_code": "VALIDATION_AUDIT_FILE_LIMIT"}

    monkeypatch.setattr(api, "MAX_UPLOAD_FILES", 20)
    mixed = await client.post(
        f"{path}/files", data={"file_type": "report"}, files=[valid, invalid]
    )
    assert mixed.status_code == 200
    success, failure = mixed.json()["data"]
    assert success["status"] == "success"
    assert failure == {
        "status": "failed",
        "filename": "bad.txt",
        "status_code": 415,
        "error": "文件格式不受支持",
    }
    service.save_uploaded_file.assert_awaited_once_with(
        task, "ok.pdf", b"%PDF-1.4 test", "report"
    )


async def test_validation_audit_prerequisites_and_parse_failure(
    audit_http, monkeypatch
) -> None:
    client, path, service, task = audit_http
    parse = await client.post(f"{path}/parse")
    assert parse.status_code == parse.json()["code"] == 409
    assert parse.json()["detail"] == {"error_code": "VALIDATION_AUDIT_NO_FILES"}
    audit = await client.post(f"{path}/audit")
    assert audit.status_code == audit.json()["code"] == 409
    assert audit.json()["detail"] == {"error_code": "VALIDATION_AUDIT_NO_FILES"}
    service.task_repo.update.assert_not_awaited()

    pending = SimpleNamespace(
        id=uuid4(), parse_status="pending", file_path="invalid.docx"
    )
    service.file_repo.list_by_task_id.return_value = [pending]

    not_parsed = await client.post(f"{path}/audit")
    assert not_parsed.status_code == not_parsed.json()["code"] == 409
    assert not_parsed.json()["detail"] == {
        "error_code": "VALIDATION_AUDIT_NO_PARSED_FILES"
    }

    def invalid_document(*args, **kwargs):
        raise ValueError("internal parser details")

    monkeypatch.setattr(
        "app.modules.registration.service.validation_audit.DocumentParser.extract_text",
        invalid_document,
    )
    unreadable = await client.post(f"{path}/parse")
    assert unreadable.status_code == unreadable.json()["code"] == 422
    assert unreadable.json()["detail"] == {
        "error_code": "VALIDATION_AUDIT_FILE_UNREADABLE"
    }
    assert "internal parser details" not in unreadable.text

    task.audit_mode = "protocol_report"
    service.file_repo.list_by_task_id.return_value = [
        SimpleNamespace(
            parse_status="completed", parsed_text="fixture", file_type="protocol"
        )
    ]
    cross = await client.post(f"{path}/audit")
    assert cross.status_code == cross.json()["code"] == 409
    assert cross.json()["detail"] == {
        "error_code": "VALIDATION_AUDIT_CROSS_FILES_REQUIRED"
    }


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (LLMRateLimitError("private"), 429),
        (LLMOutputError("private"), 502),
        (LLMConfigError("private"), 503),
        (LLMProviderError("private"), 503),
    ],
)
async def test_validation_audit_dependency_errors_use_http_status(
    audit_http, failure, status
) -> None:
    client, path, service, _ = audit_http
    service.file_repo.list_by_task_id.return_value = [
        SimpleNamespace(parse_status="completed", parsed_text="fixture")
    ]
    service._audit_protocol = AsyncMock(side_effect=failure)
    response = await client.post(f"{path}/audit")
    assert response.status_code == response.json()["code"] == status
    assert "detail" not in response.json()
    assert "private" not in response.text
    service._audit_protocol.assert_awaited_once()
