"""Public error codes for HR actions that need a specific recovery message."""

from enum import StrEnum
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.exceptions import AppException
from app.core.response import success_response
from app.shared.schemas import ApiResponseEnvelope


class HrBusinessErrorCode(StrEnum):
    HR_ANNUAL_PLAN_DUPLICATE = "HR_ANNUAL_PLAN_DUPLICATE"
    HR_ANNUAL_PLAN_DEPARTMENT_MISSING = "HR_ANNUAL_PLAN_DEPARTMENT_MISSING"
    HR_ANNUAL_PLAN_ITEMS_MISSING = "HR_ANNUAL_PLAN_ITEMS_MISSING"
    HR_ANNUAL_PLAN_ATTACHMENT_COUNT_EXCEEDED = (
        "HR_ANNUAL_PLAN_ATTACHMENT_COUNT_EXCEEDED"
    )
    HR_POSITION_TRAINING_TEMPLATE_INVALID = "HR_POSITION_TRAINING_TEMPLATE_INVALID"
    HR_POSITION_TRAINING_DATA_MISSING = "HR_POSITION_TRAINING_DATA_MISSING"
    HR_POSITION_TRANSFER_NOT_DRAFT = "HR_POSITION_TRANSFER_NOT_DRAFT"
    HR_POSITION_TRANSFER_NOT_SUBMITTED = "HR_POSITION_TRANSFER_NOT_SUBMITTED"
    HR_POSITION_TRANSFER_APPROVAL_COMPLETED = "HR_POSITION_TRANSFER_APPROVAL_COMPLETED"
    HR_POSITION_TRANSFER_FEISHU_NOT_CONFIGURED = (
        "HR_POSITION_TRANSFER_FEISHU_NOT_CONFIGURED"
    )
    HR_FEISHU_CONTACT_NOT_CONFIGURED = "HR_FEISHU_CONTACT_NOT_CONFIGURED"


class HrBusinessErrorDetail(BaseModel):
    error_code: HrBusinessErrorCode


class HrBusinessErrorResponse(BaseModel):
    code: int
    message: str
    detail: HrBusinessErrorDetail | str | None = None


class HrBusinessError(AppException):
    def __init__(
        self, status_code: int, message: str, error_code: HrBusinessErrorCode
    ) -> None:
        super().__init__(status_code, message, detail={"error_code": error_code.value})


def hr_error_response(*codes: HrBusinessErrorCode) -> dict[str, Any]:
    return {
        "model": HrBusinessErrorResponse,
        "description": (
            f"可能的业务错误码：{', '.join(codes)}。通用错误可不带业务错误码。"
        ),
    }


class HrSyncJobStatus(BaseModel):
    state: str
    progress: str
    result: Any = None
    detail: HrBusinessErrorDetail | None = None


class HrSyncJobStatusEnvelope(ApiResponseEnvelope[HrSyncJobStatus]):
    """Status of an accepted sync, including any known failure of the job itself."""


def hr_sync_status_response(status: dict[str, Any] | None) -> JSONResponse:
    public_status = dict(
        status or {"state": "idle", "progress": "无同步任务", "result": None}
    )
    detail = public_status.pop("detail", None)
    if public_status["state"] == "failed":
        public_status["progress"] = "同步失败"
        if isinstance(detail, dict):
            code = detail.get("error_code")
            if isinstance(code, str) and code in HrBusinessErrorCode:
                public_status["detail"] = {"error_code": code}
    data = HrSyncJobStatus.model_validate(public_status)
    return success_response(data=data.model_dump(mode="json", exclude_unset=True))
