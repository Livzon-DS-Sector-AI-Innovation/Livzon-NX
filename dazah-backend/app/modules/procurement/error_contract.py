"""Public failures for procurement imports and approval actions."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import AppException


class ProcurementErrorCode(StrEnum):
    INVALID_TABLE = "PROCUREMENT_IMPORT_TABLE_INVALID"
    ITEMS_MISSING = "PROCUREMENT_SUBMIT_ITEMS_MISSING"
    AMOUNT_MISMATCH = "PROCUREMENT_SUBMIT_AMOUNT_MISMATCH"


class ProcurementErrorDetail(BaseModel):
    error_code: ProcurementErrorCode


class ProcurementErrorResponse(BaseModel):
    code: int
    message: str
    detail: ProcurementErrorDetail | str | None = None


class ProcurementOperationError(ValueError):
    def __init__(
        self, status: int, message: str, code: ProcurementErrorCode | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code

    def as_http_error(self) -> AppException:
        detail = {"error_code": self.code.value} if self.code else None
        return AppException(self.status, str(self), detail=detail)


def procurement_error_response(*codes: ProcurementErrorCode) -> dict[str, Any]:
    return {
        "model": ProcurementErrorResponse,
        "description": f"请求校验失败。业务错误码：{', '.join(codes)}",
    }
