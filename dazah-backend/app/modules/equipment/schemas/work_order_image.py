"""Work order image schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WorkOrderImageResponse(BaseModel):
    """工单图片响应"""

    id: uuid.UUID
    work_order_id: uuid.UUID
    file_name: str
    file_size: int | None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


WORK_ORDER_IMAGE_LIMIT = "EQUIPMENT_WORK_ORDER_IMAGE_LIMIT"


class WorkOrderImageLimitDetail(BaseModel):
    error_code: Literal["EQUIPMENT_WORK_ORDER_IMAGE_LIMIT"]


class WorkOrderImageUploadError(BaseModel):
    code: int
    message: str
    detail: WorkOrderImageLimitDetail | str | None = None
