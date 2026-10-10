"""Owner-only metadata lookup; this endpoint never replays a business operation."""

import asyncio
import json
from collections.abc import Awaitable
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from redis.exceptions import RedisError

from app.core.maintenance_middleware import receipt_key
from app.core.redis import redis_client
from app.platform.identity.deps import require_current_user
from app.platform.identity.models import User

router = APIRouter()


class OperationReceipt(BaseModel):
    method: str
    path: str
    state: Literal["unknown", "completed", "rejected"]
    http_status: int | None = None
    updated_at: float


class OperationResult(BaseModel):
    operation_id: UUID
    receipts: list[OperationReceipt]


@router.get(
    "/operations/{operation_id}",
    response_model=OperationResult,
    summary="查询本人操作的处理结果",
)
async def get_operation_result(
    operation_id: UUID, user: User = Depends(require_current_user)
) -> OperationResult:
    try:
        async with asyncio.timeout(3):
            values = await cast(
                Awaitable[list[str]],
                redis_client.hvals(receipt_key(str(user.id), str(operation_id))),
            )
    except (RedisError, TimeoutError) as exc:
        raise HTTPException(
            503, "操作结果暂不可查询，请保留操作编号，不要重复提交"
        ) from exc
    if not values:
        raise HTTPException(
            404, "未找到操作记录，不能据此判断操作未执行，请核对业务数据"
        )
    try:
        return OperationResult(
            operation_id=operation_id,
            receipts=[
                OperationReceipt.model_validate(json.loads(value)) for value in values
            ],
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(503, "操作记录暂无法校验，请勿重复提交") from exc
