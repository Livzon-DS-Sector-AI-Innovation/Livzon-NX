"""Public errors shared by change, CAPA and deviation Word imports."""

from typing import Any, Literal

from pydantic import BaseModel

INVALID_IMPORT_DOCUMENT = "QUALITY_IMPORT_INVALID_DOCUMENT"


class QualityImportErrorDetail(BaseModel):
    error_code: Literal["QUALITY_IMPORT_INVALID_DOCUMENT"]


class QualityImportErrorResponse(BaseModel):
    code: int
    message: str
    detail: QualityImportErrorDetail | str


QUALITY_IMPORT_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"description": "导入文件超过大小限制"},
    415: {"description": "需要 .docx 格式的 Word 文档"},
    422: {
        "model": QualityImportErrorResponse,
        "description": (
            "请求校验失败，或 Word 文档无法解析（QUALITY_IMPORT_INVALID_DOCUMENT）"
        ),
    },
}
