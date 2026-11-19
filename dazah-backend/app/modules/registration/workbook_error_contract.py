"""Public validation failures for registration workbook imports."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import AppException


class RegistrationWorkbookErrorCode(StrEnum):
    UNREADABLE = "REGISTRATION_WORKBOOK_UNREADABLE"
    TEMPLATE_MISMATCH = "REGISTRATION_WORKBOOK_TEMPLATE_MISMATCH"
    CERTIFICATE_NAME_REQUIRED = "REGISTRATION_WORKBOOK_CERTIFICATE_NAME_REQUIRED"


class RegistrationWorkbookErrorDetail(BaseModel):
    error_code: RegistrationWorkbookErrorCode


class RegistrationWorkbookErrorResponse(BaseModel):
    code: int
    message: str
    detail: RegistrationWorkbookErrorDetail | str | None = None


def workbook_validation_error(
    code: RegistrationWorkbookErrorCode, message: str
) -> AppException:
    return AppException(422, message, detail={"error_code": code.value})


def workbook_import_errors(
    *extra_codes: RegistrationWorkbookErrorCode,
) -> dict[int | str, dict[str, Any]]:
    codes = (
        RegistrationWorkbookErrorCode.UNREADABLE,
        RegistrationWorkbookErrorCode.TEMPLATE_MISMATCH,
        *extra_codes,
    )
    return {
        400: {"description": "上传文件为空或不符合文件校验要求"},
        401: {"description": "登录已失效"},
        403: {"description": "没有批量导入权限"},
        413: {"description": "文件超过上传大小限制"},
        422: {
            "model": RegistrationWorkbookErrorResponse,
            "description": f"请求校验失败。业务错误码：{', '.join(codes)}",
        },
    }
