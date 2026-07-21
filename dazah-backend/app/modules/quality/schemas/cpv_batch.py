"""CPV Batch schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

DataType = Literal["CPP", "CQA"]


class CpvBatchResponse(BaseModel):
    """批次响应"""

    id: uuid.UUID
    product_id: uuid.UUID
    batch_no: str
    production_date: date
    data_type: str
    source: str
    import_task_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CpvBatchWideResponse(BaseModel):
    """批次宽表响应（参数值展开）"""

    id: uuid.UUID
    batch_no: str
    production_date: date
    data_type: str
    source: str
    parameters: dict[str, dict]  # {param_name: {value, is_abnormal, lower_limit, upper_limit}}
    has_abnormal: bool = False

    model_config = {"from_attributes": True}
