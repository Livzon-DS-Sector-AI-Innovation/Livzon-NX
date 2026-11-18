"""Public failures for work permit approval transitions."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import AppException


class WorkPermitSubmitErrorCode(StrEnum):
    TIME_INVALID = "SAFETY_WORK_PERMIT_TIME_INVALID"
    CERTIFICATE_INVALID = "SAFETY_WORK_PERMIT_CERTIFICATE_INVALID"
    APPROVER_REQUIRED = "SAFETY_WORK_PERMIT_APPROVER_REQUIRED"


class WorkPermitSubmitErrorDetail(BaseModel):
    error_code: WorkPermitSubmitErrorCode


class WorkPermitReviewErrorResponse(BaseModel):
    code: int
    message: str
    detail: str | None = None


class WorkPermitSubmitErrorResponse(BaseModel):
    code: int
    message: str
    detail: WorkPermitSubmitErrorDetail | str | None = None


def submit_validation_error(
    code: WorkPermitSubmitErrorCode, message: str
) -> AppException:
    return AppException(422, message, detail={"error_code": code.value})


WORK_PERMIT_REVIEW_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "登录已失效"},
    403: {"description": "没有操作权限"},
    404: {"description": "作业票不存在"},
    409: {"description": "作业票或审批节点的当前状态不允许该操作"},
    422: {"model": WorkPermitReviewErrorResponse, "description": "请求校验失败"},
}

WORK_PERMIT_SUBMIT_ERRORS: dict[int | str, dict[str, Any]] = {
    **WORK_PERMIT_REVIEW_ERRORS,
    423: {"description": "作业票正在提交"},
    422: {
        "model": WorkPermitSubmitErrorResponse,
        "description": "请求校验失败。业务错误码："
        + ", ".join(WorkPermitSubmitErrorCode),
    },
}
