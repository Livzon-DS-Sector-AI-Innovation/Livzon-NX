"""质量模块共享人员目录 API 路由。

数据源为人事管理-飞书联系人（hr_feishu_members），供质量模块各表单的
人员下拉与部门下拉共用（与验证模块人员选择器同源）。
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.service.person_directory import get_person_options
from app.shared.schemas import ApiResponseEnvelope

router = APIRouter()


@router.get(
    "/person-options",
    summary="获取质量模块人员选择候选（人事管理-飞书联系人）",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def list_person_options(
    keyword: str | None = Query(None, description="姓名关键词（可选）"),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    items = await get_person_options(db, keyword=keyword, limit=limit)
    return success_response(data=items)
