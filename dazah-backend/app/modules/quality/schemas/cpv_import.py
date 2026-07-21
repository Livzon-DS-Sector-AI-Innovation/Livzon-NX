"""CPV Import schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ImportMode = Literal["create", "update", "overwrite"]
ImportStatus = Literal["pending", "processing", "completed", "failed"]


class CpvImportPreviewRequest(BaseModel):
    """导入预览请求"""

    product_id: uuid.UUID = Field(..., description="产品ID")
    data_type: Literal["CPP", "CQA"] = Field(..., description="数据类型")
    import_mode: ImportMode = Field(default="create", description="导入模式")


class CpvImportPreviewResponse(BaseModel):
    """导入预览响应"""

    total_rows: int
    valid_rows: int
    error_rows: list[dict]  # [{row_number, error_message, row_data}]
    matched_parameters: list[str]  # 匹配到的参数名称
    unmatched_columns: list[str]  # 未匹配的列名


class CpvImportConfirmRequest(BaseModel):
    """导入确认请求"""

    product_id: uuid.UUID = Field(..., description="产品ID")
    data_type: Literal["CPP", "CQA"] = Field(..., description="数据类型")
    import_mode: ImportMode = Field(default="create", description="导入模式")
    file_name: str = Field(..., description="文件名")
    skip_errors: bool = Field(default=False, description="跳过错误行")


class CpvImportTaskResponse(BaseModel):
    """导入任务响应"""

    id: uuid.UUID
    file_name: str
    product_id: uuid.UUID
    data_type: str
    import_mode: str
    status: str
    total_rows: int
    success_rows: int
    failed_rows: int
    error_details: dict | None
    created_at: datetime
    created_by: uuid.UUID | None

    model_config = {"from_attributes": True}
