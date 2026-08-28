"""Contract tests for global API exception and response mappings."""

import json
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.exceptions import (
    AppException,
    DuplicateException,
    ForbiddenException,
    NotFoundException,
)
from app.core.response import error_response, paginated_response, success_response
from app.main import (
    app_exception_handler,
    database_integrity_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


def _request(method: str = "GET", path: str = "/api/v1/test") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 123),
            "scheme": "http",
        }
    )


def _body(response: Any) -> dict[str, Any]:
    return json.loads(response.body)  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_app_exception_handler_preserves_status_and_safe_detail() -> None:
    response = await app_exception_handler(
        _request(),
        AppException(
            status_code=409,
            message="状态冲突",
            detail={"field": "version"},
        ),
    )
    assert response.status_code == 409
    assert _body(response) == {
        "code": 409,
        "message": "状态冲突",
        "detail": {"field": "version"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "detail"),
    [
        (400, "请求错误"),
        (401, "需要登录"),
        (403, "权限不足"),
        (404, "资源不存在"),
        (409, "状态冲突"),
        (422, "参数错误"),
        (429, "请求过于频繁"),
        (502, "上游服务错误"),
        (503, "服务暂不可用"),
        (504, "上游服务超时"),
    ],
)
async def test_http_exception_handler_keeps_error_schema(
    status_code: Any,
    detail: Any,
) -> None:
    response = await http_exception_handler(
        _request(),
        StarletteHTTPException(status_code=status_code, detail=detail),
    )
    assert response.status_code == status_code
    assert _body(response) == {
        "code": status_code,
        "message": detail,
    }


@pytest.mark.asyncio
async def test_validation_handler_flattens_field_errors() -> None:
    error = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", "name"),
                "msg": "Field required",
                "input": {},
            },
            {
                "type": "greater_than",
                "loc": ("body", "page_size"),
                "msg": "Input should be greater than 0",
                "input": 0,
            },
        ]
    )
    response = await validation_exception_handler(_request("POST"), error)
    assert response.status_code == 422
    body = _body(response)
    assert body["code"] == 422
    assert body["message"] == "请求参数校验失败"
    assert "name: Field required" in body["detail"]
    assert "page_size: Input should be greater than 0" in body["detail"]


@pytest.mark.asyncio
async def test_integrity_error_maps_to_conflict_without_database_detail() -> None:
    response = await database_integrity_exception_handler(
        _request("POST", "/api/v1/resources"),
        IntegrityError(
            "INSERT INTO secret_table",
            {"password": "must-not-leak"},
            Exception("duplicate secret"),
        ),
    )
    assert response.status_code == 409
    body = _body(response)
    assert body == {
        "code": 409,
        "message": "数据状态冲突，请刷新后重试",
    }
    assert "secret" not in response.body.decode()  # type: ignore[union-attr]


def test_domain_exception_types_have_expected_contracts() -> None:
    missing = NotFoundException("用户", "user-id")
    duplicate = DuplicateException("工号", "E1")
    forbidden = ForbiddenException()
    assert (missing.status_code, missing.message) == (
        404,
        "用户(user-id)不存在",
    )
    assert duplicate.status_code == 409
    assert duplicate.detail_msg == "工号: E1 已被使用"
    assert forbidden.status_code == 403


def test_response_helpers_keep_common_envelope() -> None:
    success = success_response(
        data={"id": "one"},
        message="created",
        status_code=201,
    )
    assert _body(success) == {
        "code": 201,
        "message": "created",
        "data": {"id": "one"},
        "meta": None,
    }
    paginated = paginated_response(
        data=[{"id": "one"}],
        page=2,
        page_size=20,
        total=21,
    )
    assert _body(paginated)["meta"] == {
        "page": 2,
        "page_size": 20,
        "total": 21,
    }
    assert _body(error_response(message="bad", status_code=400)) == {
        "code": 400,
        "message": "bad",
    }
